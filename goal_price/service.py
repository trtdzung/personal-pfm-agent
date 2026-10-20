"""Two steps for "Chưa rõ? Để M-You ước tính": a form to tick, then a researched price. The model only writes the form and
EXTRACTS price points from search snippets; every number is checked against the snippet text and the proposal itself
(median, range, wording) is computed here in code."""

from __future__ import annotations

import asyncio
import logging
import os
import statistics
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from goal_suggest import guard
from goal_suggest.service import _unwrap

from . import research
from .contracts import Estimate, PriceEstimateRequest, PriceEstimateResponse, Question, Source

logger = logging.getLogger("goal_price.service")

_PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_MODEL = "google/gemma-4-31b-it"
MODEL_TIMEOUT_SECONDS = 45.0
MIN_POINTS = 2
MIN_VND, MAX_VND = 5_000_000, 500_000_000_000
LABELS = {
    "car": "xe ô tô",
    "house": "nhà ở (căn hộ, nhà phố, đất)",
    "travel": "chuyến du lịch",
    "education": "học phí",
    "wedding": "đám cưới",
    "retirement": "quỹ nghỉ hưu",
    "emergency": "quỹ dự phòng",
    "other": "sản phẩm",
}

# Used when the model cannot produce a valid form: the same questions every time, per template.
_AREA = ["Dưới 50 m²", "50–70 m²", "70–100 m²", "Trên 100 m²"]
FALLBACK_QUESTIONS: dict[str, list[Question]] = {
    "house": [
        Question(id="q1", title="Loại hình", options=["Căn hộ chung cư", "Nhà phố", "Nhà đất / đất nền"]),
        Question(id="q2", title="Khu vực", options=["Hà Nội", "TP. Hồ Chí Minh", "Đà Nẵng", "Tỉnh khác"]),
        Question(id="q3", title="Diện tích", options=_AREA),
        Question(id="q4", title="Tình trạng", options=["Mới", "Đã qua sử dụng"]),
    ],
    "car": [
        Question(id="q1", title="Loại xe", options=["Xe nhỏ (hạng A/B)", "Sedan", "SUV / Crossover", "Xe 7 chỗ"]),
        Question(id="q2", title="Nhiên liệu", options=["Xăng", "Điện", "Hybrid"]),
        Question(id="q3", title="Tình trạng", options=["Xe mới", "Xe đã qua sử dụng"]),
    ],
}
_GENERIC_FALLBACK = [Question(id="q1", title="Mức độ", options=["Tiết kiệm", "Trung bình", "Cao cấp"])]


class _Form(BaseModel):
    questions: list[Question]


class _Point(BaseModel):
    source: int
    quote: str
    value_vnd: int
    per_m2: bool = False


class _Extraction(BaseModel):
    area_m2: float | None = None
    points: list[_Point]


Generator = Callable[[str, str], Any]
Searcher = Callable[..., list[research.Snippet]]


def generate_with_llm(schema: type[BaseModel]) -> Generator:
    def run(system: str, human: str) -> Any:
        from llm import default_model  # lazy: needs langchain_openai

        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=MODEL_TIMEOUT_SECONDS, max_retries=0)
        model = model.model_copy(update={"model_name": os.environ.get("GOAL_PRICE_MODEL") or os.environ.get("GOAL_SUGGEST_MODEL") or DEFAULT_MODEL})
        try:
            structured = model.with_structured_output(schema, method="function_calling", include_raw=True)
        except TypeError:
            structured = model.with_structured_output(schema, include_raw=True)
        return _unwrap(structured.invoke([("system", system), ("human", human)]))

    return run


def _request_text(req: PriceEstimateRequest) -> str:
    lines = [f"Loại mục tiêu: {LABELS.get(req.template, LABELS['other'])}."]
    if req.description and req.description.strip():
        lines.append(f"Khách mô tả: {' '.join(req.description.split())}")
    for qid, chosen in (req.answers or {}).items():
        if chosen:
            lines.append(f"{qid}: {', '.join(chosen)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- step 1: the form


def _clean_form(form: _Form) -> list[Question] | None:
    questions: list[Question] = []
    for i, q in enumerate(form.questions[:4], 1):
        options = [" ".join(o.split()) for o in q.options if o and o.strip()]
        options = list(dict.fromkeys(o for o in options if len(o) <= 40))[:6]
        title = " ".join(q.title.split())
        if title and len(options) >= 2:
            questions.append(Question(id=f"q{i}", title=title[:80], options=options, multi=q.multi))
    return questions or None


def build_questions(req: PriceEstimateRequest, generate: Generator) -> tuple[list[Question], str | None]:
    """(form, reason). The model's form when valid, else the fixed one for the template (reason says why)."""
    try:
        raw = generate((_PROMPTS / "questions.md").read_text(encoding="utf-8"), f"<yeu_cau>\n{_request_text(req)}\n</yeu_cau>")
        questions = _clean_form(raw if isinstance(raw, _Form) else _Form.model_validate(raw))
        if questions:
            return questions, None
        reason = "empty_form"
    except Exception as exc:  # timeout, schema, network, missing key...
        logger.warning("goal_price form failed: %s", type(exc).__name__)
        reason = f"model_failed:{type(exc).__name__}"
    return FALLBACK_QUESTIONS.get(req.template, _GENERIC_FALLBACK), reason


# ---------------------------------------------------------------- step 2: the price


def queries_for(req: PriceEstimateRequest) -> list[str]:
    chosen = [c for options in (req.answers or {}).values() for c in options]
    subject = " ".join([LABELS.get(req.template, LABELS["other"]).split(" (")[0], *chosen, (req.description or "").strip()]).strip()
    return [f"giá {subject} 2026", f"bảng giá {subject} mới nhất"]


def _round(vnd: float) -> int:
    step = 1_000_000 if vnd < 100_000_000 else 5_000_000 if vnd < 1_000_000_000 else 10_000_000
    return int(round(vnd / step) * step)


def _money(vnd: int) -> str:
    if vnd >= 1_000_000_000:
        return f"{vnd / 1_000_000_000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " tỷ đồng"
    return f"{vnd // 1_000_000} triệu đồng"


def verified_totals(extraction: _Extraction, snippets: list[research.Snippet]) -> list[tuple[int, research.Snippet]]:
    """(total price in VND, snippet) for every point the snippet text really supports. A point is dropped when its quote is not
    in the snippet, the quote does not contain the number, or it is per m² and the area is unknown."""
    area = extraction.area_m2 if extraction.area_m2 and 10 <= extraction.area_m2 <= 5000 else None
    seen: set[tuple[int, int]] = set()
    totals: list[tuple[int, research.Snippet]] = []
    for p in extraction.points:
        if not 1 <= p.source <= len(snippets):
            continue
        snippet = snippets[p.source - 1]
        quote = " ".join(p.quote.split())
        if not quote or quote not in snippet.text or str(p.value_vnd) not in guard.number_keys(quote):
            continue
        if p.per_m2 and area is None:
            continue
        total = int(p.value_vnd * area) if p.per_m2 else p.value_vnd
        if not MIN_VND <= total <= MAX_VND or (p.source, total) in seen:
            continue
        seen.add((p.source, total))
        totals.append((total, snippet))
    return totals


def propose(totals: list[tuple[int, research.Snippet]]) -> Estimate | None:
    if len(totals) < MIN_POINTS:
        return None
    values = sorted(t for t, _ in totals)
    if len(values) >= 4:
        quartiles = statistics.quantiles(values, n=4)
        low, high = quartiles[0], quartiles[2]
    else:
        low, high = values[0], values[-1]
    amount, low, high = _round(statistics.median(values)), _round(low), _round(high)
    used = list(dict.fromkeys(s.url for _, s in totals))
    sources = [Source(title=next(s.title for _, s in totals if s.url == url)[:120], url=url) for url in used[:5]]
    summary = f"Tham khảo {len(values)} mức giá từ {len(used)} nguồn trên web: khoảng {_money(low)} đến {_money(high)}."
    return Estimate(amount=amount, low=low, high=high, summary=summary, sources=sources)


def research_price(req: PriceEstimateRequest, generate: Generator, search: Searcher) -> tuple[Estimate | None, str | None]:
    snippets: list[research.Snippet] = []
    try:
        for query in queries_for(req):
            for s in search(query, refresh=req.refresh):
                if all(s.url != seen.url for seen in snippets):
                    snippets.append(s)
    except research.ResearchUnavailable as exc:
        return None, f"search_unavailable:{exc}"
    if not snippets:
        return None, "no_results"
    listing = "\n".join(f"[{i}] {s.title}: {s.text}" for i, s in enumerate(snippets, 1))
    human = f"<yeu_cau>\n{_request_text(req)}\n</yeu_cau>\n<ket_qua_tim_kiem>\n{listing}\n</ket_qua_tim_kiem>"
    try:
        raw = generate((_PROMPTS / "extract.md").read_text(encoding="utf-8"), human)
        extraction = raw if isinstance(raw, _Extraction) else _Extraction.model_validate(raw)
    except Exception as exc:
        logger.warning("goal_price extraction failed: %s", type(exc).__name__)
        return None, f"model_failed:{type(exc).__name__}"
    estimate = propose(verified_totals(extraction, snippets))
    return (estimate, None) if estimate else (None, "not_enough_prices")


async def run(
    req: PriceEstimateRequest,
    *,
    form_generator: Generator | None = None,
    extract_generator: Generator | None = None,
    search: Searcher | None = None,
    timeout: float = MODEL_TIMEOUT_SECONDS * 2 + 40,
) -> PriceEstimateResponse:
    """Never raises for model or search trouble: that comes back as `degraded` with a reason."""
    if req.answers is None:
        questions, reason = await asyncio.to_thread(build_questions, req, form_generator or generate_with_llm(_Form))
        return PriceEstimateResponse(questions=questions, reason=reason)
    try:
        estimate, reason = await asyncio.wait_for(
            asyncio.to_thread(research_price, req, extract_generator or generate_with_llm(_Extraction), search or research.search), timeout
        )
    except asyncio.TimeoutError:
        return PriceEstimateResponse(reason="timeout", degraded=True)
    if estimate is None:
        return PriceEstimateResponse(reason=reason, degraded=True)
    return PriceEstimateResponse(estimate=estimate)

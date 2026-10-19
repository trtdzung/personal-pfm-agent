"""Narration: LLM writes sentences, code decides whether they may be shown.

The model never sees numbers and never writes one: its sentences may only contain named placeholders
(`{monthly_needed}`...) that pfm fills from the engine. Any violation -> the fixed template for that
verdict/plan/action is used instead, so the customer always gets a safe sentence.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from . import trace
from .contracts import (
    DialogueAction,
    FallbackReason,
    NarrateBlock,
    NarrateRequest,
    NarrateResponse,
    Verdict,
)
from .narration_templates import PLACEHOLDERS, PLAN_TEXT, VERDICT_TEXT, say_text

logger = logging.getLogger("goal_coach.narration")

_PROMPTS = Path(__file__).parent / "prompts"
MAX_TEXT_LEN = 280
DEFAULT_TIMEOUT_SECONDS = 2.5  # pfm waits 2 s; a slower model is not worth showing

# Words no sentence may contain (blame, guarantees, products / investments). Matched on lowercase text.
_GLOBAL_BANNED: tuple[str, ...] = (
    "lãng phí", "phung phí", "hoang phí", "tiêu hoang", "đáng trách", "lỗi của bạn", "tại bạn",
    "lợi nhuận", "sinh lời", "lãi suất", "cam kết", "bảo đảm", "đảm bảo",
    "cổ phiếu", "chứng khoán", "trái phiếu", "quỹ đầu tư", "đầu tư", "bitcoin", "crypto", "vàng",
    "bảo hiểm", "vay", "thẻ tín dụng", "sản phẩm",
)
# Extra words that contradict the engine's verdict (tone must match the numbers).
_VERDICT_BANNED: dict[Verdict, tuple[str, ...]] = {
    "feasible": ("không khả thi", "chưa khả thi", "không thể", "không đủ", "vượt", "thiếu", "rất khó", "bất khả"),
    "stretch": ("dễ dàng", "thoải mái", "dư dả", "chắc chắn", "không khả thi", "không thể"),
    "not_feasible": ("dễ dàng", "thoải mái", "dư dả", "hoàn toàn khả thi", "chắc chắn đạt", "tin vui"),
    "unknown": ("khả thi", "chắc chắn", "dễ dàng", "thoải mái", "không thể"),
}
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
_FORMAT_CHARS = re.compile(r"[*#`_<>\n\r\t|]")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def validate_text(text: str, *, verdict: Verdict | None, converse: bool) -> str | None:
    """Return the reason a sentence is rejected, or None when it may be shown."""
    if not text or len(text) > MAX_TEXT_LEN:
        return "length"
    if re.search(r"\d", text):
        return "digit"
    stripped = _PLACEHOLDER_RE.sub("", text)
    if _FORMAT_CHARS.search(stripped):
        return "format"
    if "{" in stripped or "}" in stripped:
        return "brace"
    if any(name not in PLACEHOLDERS for name in _PLACEHOLDER_RE.findall(text)):
        return "placeholder"
    low = _norm(text)
    if any(w in low for w in _GLOBAL_BANNED):
        return "banned_word"
    if verdict and any(w in low for w in _VERDICT_BANNED[verdict]):
        return "tone"
    questions = text.count("?")
    if converse and questions != 1:
        return "question_count"
    if not converse and questions > 1:
        return "question_count"
    return None


def _expected_ids(req: NarrateRequest) -> list[str]:
    if req.mode == "converse":
        return ["say"]
    return ["verdict", *[f"plan:{p}" for p in req.plan_ids]]


def _safe_name(name: str | None) -> str | None:
    """Goal names come from the customer: keep only short digit-free ones in the prompt/templates."""
    if not name or len(name) > 40 or re.search(r"[\d\n\r{}<>*#`]", name):
        return None
    return name.strip() or None


def template_blocks(req: NarrateRequest) -> list[NarrateBlock]:
    """The fixed sentences for this request (always valid)."""
    if req.mode == "converse":
        assert req.action is not None
        return [NarrateBlock(id="say", kind="say", text=say_text(req.action, _safe_name(req.facts.goal_name)))]
    assert req.verdict is not None
    blocks = [NarrateBlock(id="verdict", kind="verdict", text=VERDICT_TEXT[req.verdict])]
    for plan_id in req.plan_ids:
        blocks.append(NarrateBlock(id=f"plan:{plan_id}", kind="plan", plan_id=plan_id, text=PLAN_TEXT[(plan_id, req.verdict)]))
    return blocks


class _LLMBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str


class _LLMOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[_LLMBlock]


Generator = Callable[[NarrateRequest], dict[str, str]]


def generate_with_llm(req: NarrateRequest) -> dict[str, str]:
    """Ask the model for sentences per block id. Raises on any failure (caller falls back)."""
    from .nlu import structured_model, unwrap  # lazy: needs langchain_openai

    timeout = float(os.environ.get("GOAL_COACH_NARRATE_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    system = (_PROMPTS / "rm_persona_v1.md").read_text(encoding="utf-8") + "\n\n" + (_PROMPTS / "narrate_v1.md").read_text(encoding="utf-8")
    data = {
        "mode": req.mode,
        "ids": _expected_ids(req),
        "verdict": req.verdict,
        "plan_ids": req.plan_ids,
        "action": req.action,
        "category_names": [n for n in req.category_names if not re.search(r"\d", n)],
        "data_quality": req.data_quality,
        "goal_name": _safe_name(req.facts.goal_name),
        "history": [t.model_dump() for t in req.history],
    }
    human = "<du_lieu>\n" + json.dumps(data, ensure_ascii=False) + "\n</du_lieu>"
    parsed, err = unwrap(structured_model(_LLMOut, timeout).invoke([("system", system), ("human", human)]))
    if err:
        raise ValueError(err)
    out = parsed if isinstance(parsed, _LLMOut) else _LLMOut.model_validate(parsed)
    return {b.id: b.text.strip() for b in out.blocks}


def _from_llm(req: NarrateRequest, texts: dict[str, str]) -> list[NarrateBlock] | None:
    """Validated blocks, or None when anything is missing or rejected."""
    expected = _expected_ids(req)
    if set(texts) != set(expected):
        trace.add("rejected", {"id": None, "reason": "ids", "got": sorted(texts), "expected": expected})
        return None
    converse = req.mode == "converse"
    blocks: list[NarrateBlock] = []
    for bid in expected:
        reason = validate_text(texts[bid], verdict=req.verdict, converse=converse)
        if reason:
            logger.warning("narration rejected id=%s reason=%s", bid, reason)
            trace.add("rejected", {"id": bid, "reason": reason, "text": trace.text(texts[bid])})
            return None
        if converse:
            blocks.append(NarrateBlock(id=bid, kind="say", text=texts[bid]))
        elif bid == "verdict":
            blocks.append(NarrateBlock(id=bid, kind="verdict", text=texts[bid]))
        else:
            blocks.append(NarrateBlock(id=bid, kind="plan", plan_id=bid.split(":", 1)[1], text=texts[bid]))  # type: ignore[arg-type]
    return blocks


def _masked(text: str, goal_name: str | None) -> str:
    """Shown sentence for the trace; the goal name (customer's words) is masked outside full mode."""
    return text if trace.full() or not goal_name else text.replace(goal_name, "<goal_name>")


def narrate(req: NarrateRequest, *, request_id: str, generate: Generator | None = None) -> NarrateResponse:
    """LLM sentences when they pass validation, else the fixed templates. Never raises for model trouble."""
    started = time.monotonic()
    reason: FallbackReason | None = None
    blocks: list[NarrateBlock] | None = None
    if os.environ.get("GOAL_COACH_NARRATE", "on").lower() == "off":
        reason = "flag_off"
    else:
        try:
            blocks = _from_llm(req, (generate or generate_with_llm)(req))
            if blocks is None:
                reason = "invalid"
        except Exception as exc:  # timeout, schema, network...
            logger.warning("narration model failed: %s", type(exc).__name__)
            trace.note(model_error=type(exc).__name__)
            reason = "model_error"
    source = "llm" if blocks is not None else "template"
    shown = blocks if blocks is not None else template_blocks(req)
    trace.note(
        mode=req.mode, verdict=req.verdict, action=req.action, plan_ids=req.plan_ids,
        data_quality=req.data_quality, history_turns=len(req.history),
        source=source, fallback_reason=reason,
        blocks=[{"id": b.id, "text": _masked(b.text, req.facts.goal_name)} for b in shown],
    )
    logger.info(
        "goal_coach narrate request_id=%s user_id=%s mode=%s source=%s reason=%s latency_ms=%d",
        request_id, req.user_id, req.mode, source, reason, int((time.monotonic() - started) * 1000),
    )
    return NarrateResponse(
        request_id=request_id,
        source=source,
        fallback_reason=reason,
        blocks=shown,
    )


__all__ = ["narrate", "validate_text", "template_blocks", "DialogueAction"]

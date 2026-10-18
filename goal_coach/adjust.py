"""Edit-by-words: turn "lùi 6 tháng" / "giảm 100 triệu" into a normalised adjustment of the current draft.

Code first (regex + deterministic parsers); the LLM only reads sentences code cannot. Every number is
re-parsed from verbatim evidence, same rule as slots.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from .contracts import AdjustExtraction, Adjustment, AdjustKind, CurrentDraft
from .evidence import evidence_in
from .fast_path import _amount_spans, _horizon
from .parsing import parse_amount, parse_horizon

MAX_EXTEND_MONTHS = 240

_EXTEND_VERB = re.compile(r"(?<!\w)(?:lùi|dời|kéo dài|gia hạn|trễ|chậm|thêm)(?!\w)")
_REDUCE_VERB = re.compile(r"(?<!\w)(?:giảm|hạ|bớt|rút bớt)(?!\w)")
_TO_WORD = re.compile(r"(?<!\w)(?:xuống|còn|về)(?!\w)")
_SAVINGS_USE = re.compile(r"(?<!\w)(?:dùng|lấy|rút|chuyển)(?!\w)[^.]*?tiết kiệm|tiết kiệm[^.]*?(?<!\w)(?:dùng|lấy|rút)(?!\w)")
_MONTHLY = re.compile(r"(?:mỗi|một|/|\bhằng|\bhàng)\s*tháng|/tháng|tháng\s*góp")
_SAVE_VERB = re.compile(r"(?<!\w)(?:góp|để dành|dành|tiết kiệm|nạp)(?!\w)")

Extractor = Callable[[str], AdjustExtraction]


def _fast(text: str) -> tuple[AdjustKind, int, bool, str] | None:
    """(kind, number, is_delta, evidence) when the sentence is plainly one edit, else None."""
    src = unicodedata.normalize("NFC", text)
    t = src.lower()
    if len(t) != len(src):
        return None
    spans, ambiguous = _amount_spans(t)
    if ambiguous or len(spans) > 1:
        return None
    if _SAVINGS_USE.search(t) and len(spans) == 1:
        s, e, v = spans[0]
        return "use_savings_amount", v, False, src[s:e]
    if _MONTHLY.search(t) and _SAVE_VERB.search(t) and len(spans) == 1:
        s, e, v = spans[0]
        return "raise_saving_to", v, False, src[s:e]
    if _EXTEND_VERB.search(t) and not spans:
        hs, _ = _horizon(t)
        if hs:
            ev = src[hs[0]:hs[1]]
            parsed = parse_horizon(ev)
            if parsed and "months" in parsed:
                return "extend_months", int(parsed["months"]), False, ev
        return None
    if _REDUCE_VERB.search(t) and len(spans) == 1:
        s, e, v = spans[0]
        return "reduce_amount_to", v, not _TO_WORD.search(t), src[s:e]
    return None


def _from_llm(text: str, extract: Extractor) -> tuple[AdjustKind, int, bool, str] | None:
    """Model reading; accepted only if the quoted evidence is in the sentence and parses to the same number."""
    ext = extract(text)
    if not ext.is_adjustment or ext.kind is None or ext.value is None or not evidence_in(ext.evidence, text):
        return None
    if ext.kind == "extend_months":
        parsed = parse_horizon(ext.evidence)
        ok = parsed is not None and parsed.get("months") == ext.value
    else:
        ok = parse_amount(ext.evidence) == ext.value
    return (ext.kind, ext.value, ext.is_delta, ext.evidence) if ok else None


def normalize(kind: AdjustKind, value: int, is_delta: bool, evidence: str, current: CurrentDraft) -> Adjustment | None:
    """Apply sanity rules against the current draft; None when the edit makes no sense."""
    target, opening = current.target_amount, current.opening_amount
    if kind == "extend_months":
        ok = 1 <= value <= MAX_EXTEND_MONTHS and (current.months is None or current.months + value <= 600)
        return Adjustment(kind=kind, value=value, evidence=evidence) if ok else None
    if kind == "reduce_amount_to":
        new = target - value if is_delta else value
        return Adjustment(kind=kind, value=new, evidence=evidence) if opening < new < target else None
    if kind == "raise_saving_to":
        return Adjustment(kind=kind, value=value, evidence=evidence) if 0 < value <= target else None
    # use_savings_amount
    return Adjustment(kind=kind, value=value, evidence=evidence) if 0 < value and opening + value < target else None


def read_adjustment(text: str, current: CurrentDraft, extract: Extractor | None = None) -> tuple[Adjustment | None, bool]:
    """(adjustment or None, llm_used). Raises nlu.ModelUnavailableError only when the model was needed and failed."""
    fast = _fast(text)
    llm_used = False
    if fast is None and extract is not None:
        fast, llm_used = _from_llm(text, extract), True
    if fast is None:
        return None, llm_used
    kind, value, is_delta, evidence = fast
    return normalize(kind, value, is_delta, evidence, current), llm_used

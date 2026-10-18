"""Evidence checks: every LLM slot must quote the customer and match the deterministic parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .contracts import MAX_AMOUNT_VND, MAX_NAME_LEN, GoalExtraction
from .parsing import parse_amount, parse_horizon

_TRAIL_PUNCT = " \t\r\n.,;:!?…\"'“”"


def normalize(text: str) -> str:
    """Collapse whitespace, lowercase, drop trailing punctuation."""
    return re.sub(r"\s+", " ", text).strip(_TRAIL_PUNCT).lower().strip(_TRAIL_PUNCT)


def evidence_in(evidence: str, source: str) -> bool:
    ev = normalize(evidence)
    return bool(ev) and ev in normalize(source)


def clean_name(value: str) -> str | None:
    """Trim + capitalise; None if empty, too long, or it contains an amount."""
    name = re.sub(r"\s+", " ", value).strip()
    if not name or len(name) > MAX_NAME_LEN:
        return None
    if re.search(r"\d", name) and parse_amount(name) is not None:
        return None
    return name[0].upper() + name[1:]


@dataclass
class Verified:
    """Slots that survived the checks, plus why others were dropped."""

    is_goal: bool = False
    name: tuple[str, str] | None = None  # (value, evidence)
    target_amount: tuple[int, str] | None = None
    opening_amount: tuple[int, str] | None = None
    horizon: tuple[dict[str, int | str], str] | None = None
    flexibility: tuple[str, str] | None = None
    unclear: set[str] = field(default_factory=set)  # {"amount_unclear", "horizon_unclear"}


def verify(ext: GoalExtraction, source: str) -> Verified:
    """Check `ext` against the text it was extracted from."""
    out = Verified(is_goal=ext.is_savings_goal)

    if ext.name and evidence_in(ext.name.evidence, source):
        name = clean_name(ext.name.value)
        if name:
            out.name = (name, ext.name.evidence)

    ta = ext.target_amount
    if ta:
        if (
            evidence_in(ta.evidence, source)
            and 0 < ta.value_vnd <= MAX_AMOUNT_VND
            and parse_amount(ta.evidence) == ta.value_vnd
        ):
            out.target_amount = (ta.value_vnd, ta.evidence)
        else:
            out.unclear.add("amount_unclear")

    oa = ext.opening_amount
    if (
        oa
        and evidence_in(oa.evidence, source)
        and 0 < oa.value_vnd <= MAX_AMOUNT_VND
        and parse_amount(oa.evidence) == oa.value_vnd
    ):
        out.opening_amount = (oa.value_vnd, oa.evidence)  # a bad opening amount is simply dropped

    h = ext.horizon
    if h:
        parsed = parse_horizon(h.evidence) if evidence_in(h.evidence, source) else None
        claimed: dict[str, int | str] | None = None
        if (h.months is None) != (h.target_month is None):
            claimed = {"months": h.months} if h.months is not None else {"target_month": h.target_month}  # type: ignore[dict-item]
        if parsed is not None and parsed == claimed:
            out.horizon = (parsed, h.evidence)
        else:
            out.unclear.add("horizon_unclear")

    f = ext.flexibility
    if f and evidence_in(f.evidence, source):
        out.flexibility = (f.value, f.evidence)

    return out

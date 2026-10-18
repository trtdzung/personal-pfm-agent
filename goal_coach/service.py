"""One conversation turn: normalise answers -> NLU -> verify -> policy -> response."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from .contracts import (
    AmountSlot,
    CoachRequest,
    CoachResponse,
    FlexibilitySlot,
    GoalExtraction,
    Horizon,
    HorizonSlot,
    NameSlot,
    Slots,
)
from .evidence import Verified, clean_name, verify
from .nlu import extract as default_extract
from .parsing import parse_amount, parse_horizon
from .policy import decide
from .questions import parse_option

logger = logging.getLogger("goal_coach.service")

Extractor = Callable[[str], GoalExtraction]
_ZERO_WORDS = {"0", "không", "chưa", "chưa có", "không có", "chua co", "khong co"}
_ALL_SLOTS = ("name", "target_amount", "horizon", "flexibility", "opening_amount")


def new_request_id() -> str:
    return "gc_" + uuid.uuid4().hex[:12]


def _set(slots: Slots, slot: str, value: object, source: str, evidence: str | None) -> None:
    if slot == "name":
        slots.name = NameSlot(value=str(value), source=source, evidence=evidence)  # type: ignore[arg-type]
    elif slot in ("target_amount", "opening_amount"):
        setattr(slots, slot, AmountSlot(value=int(value), source=source, evidence=evidence))  # type: ignore[arg-type]
    elif slot == "horizon":
        h = value if isinstance(value, Horizon) else Horizon(**value)  # type: ignore[arg-type]
        slots.horizon = HorizonSlot(value=h, source=source, evidence=evidence)  # type: ignore[arg-type]
    elif slot == "flexibility":
        slots.flexibility = FlexibilitySlot(value=value, source=source, evidence=evidence)  # type: ignore[arg-type]


def _apply_verified(slots: Slots, v: Verified, only: set[str], source: str) -> None:
    for slot in only:
        item = getattr(v, slot)
        if item is not None:
            _set(slots, slot, item[0], source, item[1])


def _text_answer_direct(slot: str, text: str) -> object | None:
    """Parser-first handling of a typed answer. None -> needs the NLU."""
    if slot == "target_amount":
        return parse_amount(text)
    if slot == "opening_amount":
        if text.strip().lower() in _ZERO_WORDS:
            return 0
        return parse_amount(text)
    if slot == "horizon":
        return parse_horizon(text)
    if slot == "name":
        return clean_name(text)
    return None


def run_turn(
    req: CoachRequest,
    *,
    request_id: str | None = None,
    extract: Extractor | None = None,
) -> CoachResponse:
    """Run one turn. Raises nlu.ModelUnavailableError when the model fails."""
    started = time.monotonic()
    request_id = request_id or new_request_id()
    extract = extract or default_extract
    slots = Slots()
    answered: set[str] = set()
    unclear: set[str] = set()
    is_goal = False

    # 1) answers (later answers win). Options go straight in; typed text is parser-first.
    for ans in req.answers:
        if ans.source == "option":
            val = parse_option(ans.slot, ans.value)
            if val is not None:
                _set(slots, ans.slot, val, "answer", None)
                answered.add(ans.slot)
            continue
        val = _text_answer_direct(ans.slot, ans.value)
        if val is not None:
            _set(slots, ans.slot, val, "answer", ans.value if ans.slot != "name" else None)
            answered.add(ans.slot)
            continue
        if ans.slot == "name":
            continue
        v = verify(extract(ans.value), ans.value)  # NLU only for the slot that was asked
        item = getattr(v, ans.slot)
        if item is not None:
            _set(slots, ans.slot, item[0], "answer", item[1])
            answered.add(ans.slot)
        else:
            unclear |= v.unclear & {"amount_unclear" if ans.slot == "target_amount" else "horizon_unclear"}

    # 2) original sentence, only if some slot still has to come from it
    missing = {s for s in _ALL_SLOTS if s not in answered}
    if missing:
        v = verify(extract(req.request), req.request)
        is_goal = v.is_goal
        _apply_verified(slots, v, missing, "request")
        if slots.target_amount is None and "target_amount" in missing:
            unclear |= v.unclear & {"amount_unclear"}
        if slots.horizon is None and "horizon" in missing:
            unclear |= v.unclear & {"horizon_unclear"}
    else:
        is_goal = True
    unclear = {u for u in unclear if (u == "amount_unclear" and slots.target_amount is None)
               or (u == "horizon_unclear" and slots.horizon is None)}

    # 3) policy
    d = decide(slots, is_goal=is_goal, unclear=unclear, answers_count=len(req.answers))
    resp = CoachResponse(
        request_id=request_id,
        status=d.status,  # type: ignore[arg-type]
        slots=slots,
        draft=d.draft,
        question=d.question,
        message_code=d.message_code,
    )
    logger.info(
        "goal_coach request_id=%s user_id=%s status=%s message_code=%s answers=%d latency_ms=%d",
        request_id, req.user_id, resp.status, resp.message_code, len(req.answers),
        int((time.monotonic() - started) * 1000),
    )
    logger.debug("goal_coach request_id=%s text=%r", request_id, req.request)
    return resp

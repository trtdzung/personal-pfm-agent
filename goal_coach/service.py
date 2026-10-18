"""One conversation turn: normalise answers -> NLU -> verify -> policy -> response."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from .contracts import (
    AdjustExtraction,
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
from .adjust import read_adjustment
from .evidence import Verified, clean_name, verify
from .fast_path import FastResult, fast_extract
from .nlu import extract as default_extract
from .nlu import extract_adjust as default_extract_adjust
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


def _understand(
    text: str, missing: set[str], req: CoachRequest, extract: Extractor
) -> tuple[Verified, bool]:
    """Read the original sentence: code first, LLM only for what code cannot settle.

    Returns (verified slots, llm_used). Slots found by code win over the model's.
    """
    fast = fast_extract(text)
    amount_known = "target_amount" not in missing or fast.amount is not None
    horizon_known = "horizon" not in missing or fast.horizon is not None
    need_llm = (
        fast.injection
        or (fast.ambiguous_amount and "target_amount" in missing)
        or (fast.ambiguous_horizon and "horizon" in missing)
        or (fast.unit_word_no_amount and "target_amount" in missing)
        or (not req.answers and not fast.goal_hint)  # goal / out-of-scope needs the model
        or ("name" in missing and fast.name is None and amount_known and horizon_known)
    )
    v = verify(extract(text), text) if need_llm else Verified(is_goal=True)
    if need_llm and not v.is_goal and not fast.goal_hint:
        return v, True  # model says "not a goal": code-found numbers must not turn it into one
    _overlay(v, fast)
    return v, need_llm


def _overlay(v: Verified, fast: FastResult) -> None:
    """Code-found slots replace the model's (code wins on conflict)."""
    if fast.amount is not None:
        v.target_amount = fast.amount
        v.unclear.discard("amount_unclear")
    if fast.opening is not None:
        v.opening_amount = fast.opening
    if fast.horizon is not None:
        v.horizon = fast.horizon
        v.unclear.discard("horizon_unclear")
    elif fast.horizon_relative and v.horizon is None:
        v.unclear.add("horizon_unclear")
    if fast.flexibility is not None:
        v.flexibility = fast.flexibility
    if fast.name is not None and v.name is None:
        v.name = fast.name  # model names are only used when code found none
    if fast.goal_hint:
        v.is_goal = True


def _adjust_turn(
    req: CoachRequest, request_id: str, extract_adjust: Callable[[str], AdjustExtraction], started: float
) -> CoachResponse:
    """The customer is editing a draft by words: one normalised adjustment, or "not understood"."""
    assert req.current_draft is not None
    adj, llm_used = read_adjustment(req.request, req.current_draft, extract_adjust)
    resp = (
        CoachResponse(request_id=request_id, status="adjust", slots=Slots(), message_code="adjust_ready", adjustment=adj)
        if adj
        else CoachResponse(request_id=request_id, status="out_of_scope", slots=Slots(), message_code="adjust_unclear")
    )
    logger.info(
        "goal_coach request_id=%s user_id=%s status=%s message_code=%s kind=%s llm=%s latency_ms=%d",
        request_id, req.user_id, resp.status, resp.message_code, adj.kind if adj else None, llm_used,
        int((time.monotonic() - started) * 1000),
    )
    return resp


def run_turn(
    req: CoachRequest,
    *,
    request_id: str | None = None,
    extract: Extractor | None = None,
    extract_adjust: Callable[[str], AdjustExtraction] | None = None,
) -> CoachResponse:
    """Run one turn. Raises nlu.ModelUnavailableError when the model fails."""
    started = time.monotonic()
    request_id = request_id or new_request_id()
    if req.current_draft is not None:
        return _adjust_turn(req, request_id, extract_adjust or default_extract_adjust, started)
    extract = extract or default_extract
    slots = Slots()
    answered: set[str] = set()
    unclear: set[str] = set()
    is_goal = False
    llm_used = False

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
        v, llm_used = _understand(req.request, missing, req, extract)
        is_goal = v.is_goal
        _apply_verified(slots, v, missing, "request")
        if slots.target_amount is None and "target_amount" in missing:
            unclear |= v.unclear & {"amount_unclear"}
        if slots.horizon is None and "horizon" in missing:
            unclear |= v.unclear & {"horizon_unclear"}
    else:
        is_goal = True
    if slots.opening_amount and slots.target_amount and slots.opening_amount.value >= slots.target_amount.value:
        slots.opening_amount = None  # inconsistent: ask again (or fall back to 0)
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
        "goal_coach request_id=%s user_id=%s status=%s message_code=%s answers=%d llm=%s latency_ms=%d",
        request_id, req.user_id, resp.status, resp.message_code, len(req.answers), llm_used,
        int((time.monotonic() - started) * 1000),
    )
    logger.debug("goal_coach request_id=%s text=%r", request_id, req.request)
    return resp

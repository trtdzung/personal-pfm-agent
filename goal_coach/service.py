"""One conversation turn: normalise answers -> NLU -> verify -> policy -> response."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from . import trace
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
from .evidence import Verified, clean_name, name_from_answer, verify
from .fast_path import FastResult, fast_extract, find_flexibility
from .nlu import ModelUnavailableError
from .nlu import extract as default_extract
from .nlu import extract_adjust as default_extract_adjust
from .parsing import parse_amount, parse_horizon
from .policy import decide
from .questions import parse_option
from .smalltalk import reply as smalltalk_reply
from .tone import say

logger = logging.getLogger("goal_coach.service")

Extractor = Callable[[str], GoalExtraction]
_ZERO_WORDS = {"0", "không", "chưa", "chưa có", "không có", "chua co", "khong co"}
_ALL_SLOTS = ("name", "target_amount", "horizon", "flexibility", "opening_amount")


def new_request_id() -> str:
    return "gc_" + uuid.uuid4().hex[:12]


def _set(slots: Slots, slot: str, value: object, source: str, evidence: str | None) -> None:
    if slot == "name":
        slots.name = NameSlot(value=clean_name(str(value)) or str(value), source=source, evidence=evidence)  # type: ignore[arg-type]
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
        return name_from_answer(text)
    if slot == "flexibility":  # typed instead of a chip: "dung han", "lùi được"
        found = find_flexibility(text)
        return found[0] if found else None
    return None


def _code_slots(fast: FastResult) -> set[str]:
    found = {"target_amount": fast.amount, "opening_amount": fast.opening, "horizon": fast.horizon,
             "flexibility": fast.flexibility, "name": fast.name}
    return {k for k, v in found.items() if v is not None}


def _understand(
    text: str, missing: set[str], req: CoachRequest, extract: Extractor
) -> tuple[Verified, bool, set[str]]:
    """Read the original sentence: code first, LLM only for what code cannot settle.

    Returns (verified slots, llm_used, slots code found). Slots found by code win over the model's.
    """
    fast = fast_extract(text)
    amount_known = "target_amount" not in missing or fast.amount is not None
    horizon_known = "horizon" not in missing or fast.horizon is not None
    checks = {
        "injection": fast.injection,
        "ambiguous_amount": fast.ambiguous_amount and "target_amount" in missing,
        "ambiguous_horizon": fast.ambiguous_horizon and "horizon" in missing,
        "unit_word_no_amount": fast.unit_word_no_amount and "target_amount" in missing,
        "no_goal_hint": not req.answers and not fast.goal_hint,  # goal / out-of-scope needs the model
        "name_missing": "name" in missing and fast.name is None and amount_known and horizon_known,
    }
    reasons = [k for k, hit in checks.items() if hit]
    need_llm = bool(reasons)
    code_found = _code_slots(fast)
    trace.note(code_slots=sorted(code_found), llm_reasons=reasons, horizon_relative=fast.horizon_relative)
    ext = extract(text) if need_llm else None
    v = verify(ext, text) if ext is not None else Verified(is_goal=True)
    if need_llm:
        trace.note(llm_verified={"is_goal": v.is_goal, "unclear": sorted(v.unclear),
                                 "slots": [k for k in _ALL_SLOTS if getattr(v, k) is not None]})
    if need_llm and not v.is_goal and not fast.goal_hint:
        return v, True, set()  # model says "not a goal": code-found numbers must not turn it into one
    conflict = (
        ext is not None and ext.target_amount is not None and fast.amount is not None
        and ext.target_amount.value_vnd != fast.amount[0]
    )
    _overlay(v, fast)
    if conflict:  # code and model read different amounts ("6 tháng chi tiêu, mỗi tháng 15 triệu"): ask, don't guess
        v.target_amount = None
        v.unclear.add("amount_unclear")
        code_found.discard("target_amount")
        trace.note(amount_conflict=True)
    return v, need_llm, code_found


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
    trace.note(
        request=trace.text(req.request),
        current_draft=req.current_draft.model_dump(),
        llm_used=llm_used,
        status=resp.status,
        message_code=resp.message_code,
        adjustment=None if adj is None else {"kind": adj.kind, "value": adj.value},
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
    origin: dict[str, str] = {}  # slot -> option | answer_code | answer_llm | request_code | request_llm

    # 1) answers (later answers win, so only the last one per slot is read: an earlier, not understood
    #    answer is not sent to the model again). Options go straight in; typed text is parser-first.
    last_per_slot = {ans.slot: i for i, ans in enumerate(req.answers)}
    for i, ans in enumerate(req.answers):
        if last_per_slot[ans.slot] != i:
            continue
        if ans.source == "option":
            val = parse_option(ans.slot, ans.value)
            if val is not None:
                _set(slots, ans.slot, val, "answer", None)
                answered.add(ans.slot)
                origin[ans.slot] = "option"
            continue
        val = _text_answer_direct(ans.slot, ans.value)
        if val is not None:
            _set(slots, ans.slot, val, "answer", ans.value if ans.slot != "name" else None)
            answered.add(ans.slot)
            origin[ans.slot] = "answer_code"
            continue
        if ans.slot == "name":
            try:  # a long sentence: let the model find the name in it; any model trouble -> policy default
                v = verify(extract(ans.value), ans.value)
            except ModelUnavailableError:
                continue
        else:
            v = verify(extract(ans.value), ans.value)  # NLU only for the slot that was asked
        item = getattr(v, ans.slot)
        if item is not None:
            _set(slots, ans.slot, item[0], "answer", item[1])
            answered.add(ans.slot)
            origin[ans.slot] = "answer_llm"
        else:
            unclear |= v.unclear & {"amount_unclear" if ans.slot == "target_amount" else "horizon_unclear"}

    # 2) original sentence, only if some slot still has to come from it
    missing = {s for s in _ALL_SLOTS if s not in answered}
    if missing:
        v, llm_used, code_found = _understand(req.request, missing, req, extract)
        is_goal = v.is_goal
        _apply_verified(slots, v, missing, "request")
        for s in missing:
            if getattr(slots, s) is not None:
                origin[s] = "request_code" if s in code_found else "request_llm"
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
    # `req.context` only shapes chips here; it is never passed to the extractor (the model never sees figures).
    asked: dict[str, int] = {}
    for ans in req.answers:
        asked[ans.slot] = asked.get(ans.slot, 0) + 1
    d = decide(slots, is_goal=is_goal, unclear=unclear, answers_count=len(req.answers), context=req.context, asked=asked)
    if d.question is not None:
        if len(req.answers) == 0:
            captured = {k for k, o in origin.items() if o.startswith("request")}
        else:
            last = req.answers[-1].slot  # later answers win: a set answer-origin means the last one was understood
            captured = {last} if origin.get(last, "").startswith(("option", "answer")) else set()
        d.question = d.question.model_copy(update={"text": say(d.question.text, req, slots, captured)})
    resp = CoachResponse(
        request_id=request_id,
        status=d.status,  # type: ignore[arg-type]
        slots=slots,
        draft=d.draft,
        question=d.question,
        message_code=d.message_code,
        reply=smalltalk_reply(req) if d.status == "out_of_scope" else None,
    )
    _trace_turn(req, resp, origin, unclear, llm_used)
    logger.info(
        "goal_coach request_id=%s user_id=%s status=%s message_code=%s answers=%d llm=%s latency_ms=%d",
        request_id, req.user_id, resp.status, resp.message_code, len(req.answers), llm_used,
        int((time.monotonic() - started) * 1000),
    )
    logger.debug("goal_coach request_id=%s text=%r", request_id, req.request)
    return resp


def _slot_value(slots: Slots, name: str) -> object:
    item = getattr(slots, name)
    if item is None:
        return None
    if name == "name":
        return trace.text(item.value)  # the customer's words
    return item.value.to_wire() if name == "horizon" else item.value


def _trace_turn(req: CoachRequest, resp: CoachResponse, origin: dict[str, str], unclear: set[str], llm_used: bool) -> None:
    q = resp.question
    trace.note(
        turn=len(req.answers),
        request=trace.text(req.request),
        answers=[{"slot": a.slot, "source": a.source, "value": a.value if a.source == "option" else trace.text(a.value)}
                 for a in req.answers],
        has_context=req.context is not None,
        llm_used=llm_used,
        status=resp.status,
        message_code=resp.message_code,
        slots={s: {"value": _slot_value(resp.slots, s), "origin": origin.get(s)}
               for s in _ALL_SLOTS if getattr(resp.slots, s) is not None},
        unclear=sorted(unclear),
        question=None if q is None else {
            "slot": q.slot, "code": q.code, "text": q.text,
            "options": [o.label for o in q.options], "hint": q.hint.code if q.hint else None,
        },
        draft=None if resp.draft is None else {**resp.draft.model_dump(mode="json"), "name": trace.text(resp.draft.name)},
    )

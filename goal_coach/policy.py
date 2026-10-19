"""Deterministic conversation policy: which question next, or are we done."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import AmountSlot, CoachContext, Draft, MessageCode, NameSlot, Question, Slots
from .questions import REASK_TEXT, get_question, personalise, stuck_question

MAX_QUESTIONS = 3
MAX_ASKS = 2  # a slot is asked at most twice by text; then chips only (amount/horizon) or a default (name, opening)
DEFAULT_NAME = "Mục tiêu tiết kiệm"
_REQUIRED: tuple[tuple[str, MessageCode], ...] = (
    ("target_amount", "need_amount"),
    ("horizon", "need_horizon"),
    ("name", "need_name"),
    ("flexibility", "need_flexibility"),
)


@dataclass
class Decision:
    status: str  # draft | need_info | out_of_scope
    message_code: MessageCode
    question: Question | None = None
    draft: Draft | None = None


def decide(
    slots: Slots,
    *,
    is_goal: bool,
    unclear: set[str],
    answers_count: int,
    context: CoachContext | None = None,
    asked: dict[str, int] | None = None,
) -> Decision:
    """`answers_count` = questions already answered; also the number of turns spent.

    `asked[slot]` = answers already given for that slot (a re-ask means the last one was not understood).
    """
    asked = asked or {}
    if slots.name is None and asked.get("name", 0) >= 1:
        slots.name = NameSlot(value=DEFAULT_NAME, source="answer")  # editable in the review form
    if slots.opening_amount is None and asked.get("opening_amount", 0) >= MAX_ASKS:
        slots.opening_amount = AmountSlot(value=0, source="answer")
    if (
        answers_count == 0
        and not is_goal
        and slots.target_amount is None
        and slots.horizon is None
        and not unclear
    ):
        return Decision("out_of_scope", "not_a_goal")

    turns_left = answers_count < MAX_QUESTIONS
    for slot, code in _REQUIRED:
        if getattr(slots, slot) is not None:
            continue
        reasked = asked.get(slot, 0) >= 1  # the last answer for it was not understood: say it differently
        if slot == "target_amount" and ("amount_unclear" in unclear or reasked):
            code = "amount_unclear"
        if slot == "horizon" and ("horizon_unclear" in unclear or reasked):
            code = "horizon_unclear"
        q = personalise(get_question(code), slots, context)
        if not turns_left:
            q = q.model_copy(update={"allow_free_text": True})  # pfm suggests "Tự nhập"
        if slot in ("target_amount", "horizon") and asked.get(slot, 0) >= MAX_ASKS:
            q = stuck_question(q)  # third time: chips only
        elif slot in REASK_TEXT and asked.get(slot, 0) == 1:
            q = q.model_copy(update={"text": REASK_TEXT[slot]})  # second time: other words
        return Decision("need_info", code, question=q)

    assert slots.name and slots.target_amount and slots.horizon and slots.flexibility
    opening = slots.opening_amount.value if slots.opening_amount else None
    if opening is not None and opening >= slots.target_amount.value:
        opening = None
        slots.opening_amount = None  # inconsistent: ask again (or fall back to 0)
    if opening is None and turns_left:
        return Decision("need_info", "need_opening", question=personalise(get_question("need_opening"), slots, context))

    draft = Draft(
        name=slots.name.value,
        target_amount=slots.target_amount.value,
        horizon=slots.horizon.value,
        flexibility=slots.flexibility.value,
        opening_amount=opening or 0,
    )
    return Decision("draft", "draft_ready", draft=draft)

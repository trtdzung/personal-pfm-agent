"""Deterministic conversation policy: which question next, or are we done."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import Draft, MessageCode, Question, Slots
from .questions import get_question

MAX_QUESTIONS = 3
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


def decide(slots: Slots, *, is_goal: bool, unclear: set[str], answers_count: int) -> Decision:
    """`answers_count` = questions already answered; also the number of turns spent."""
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
        if slot == "target_amount" and "amount_unclear" in unclear:
            code = "amount_unclear"
        if slot == "horizon" and "horizon_unclear" in unclear:
            code = "horizon_unclear"
        q = get_question(code)
        if not turns_left:
            q = q.model_copy(update={"allow_free_text": True})  # pfm suggests "Tự nhập"
        return Decision("need_info", code, question=q)

    assert slots.name and slots.target_amount and slots.horizon and slots.flexibility
    opening = slots.opening_amount.value if slots.opening_amount else None
    if opening is not None and opening >= slots.target_amount.value:
        opening = None
        slots.opening_amount = None  # inconsistent: ask again (or fall back to 0)
    if opening is None and turns_left:
        return Decision("need_info", "need_opening", question=get_question("need_opening"))

    draft = Draft(
        name=slots.name.value,
        target_amount=slots.target_amount.value,
        horizon=slots.horizon.value,
        flexibility=slots.flexibility.value,
        opening_amount=opening or 0,
    )
    return Decision("draft", "draft_ready", draft=draft)

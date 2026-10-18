"""Fixed question catalog (Vietnamese). The LLM never writes questions."""

from __future__ import annotations

from .contracts import MessageCode, Question, QuestionOption, SlotName

# code -> (slot, text, [(label, value)], allow_free_text)
# Option values are machine-readable so source="option" answers skip the LLM:
#   target_amount / opening_amount: VND integer as string; horizon: "months:N";
#   flexibility: "fixed" | "flexible".
_CATALOG: dict[str, tuple[SlotName, str, list[tuple[str, str]], bool]] = {
    "need_amount": (
        "target_amount",
        "Bạn cần khoảng bao nhiêu tiền cho mục tiêu này?",
        [("50 triệu", "50000000"), ("100 triệu", "100000000"),
         ("300 triệu", "300000000"), ("500 triệu", "500000000")],
        True,
    ),
    "need_horizon": (
        "horizon",
        "Bạn muốn đạt mục tiêu trong bao lâu?",
        [("6 tháng", "months:6"), ("1 năm", "months:12"),
         ("3 năm", "months:36"), ("5 năm", "months:60")],
        True,
    ),
    "need_name": ("name", "Bạn đặt tên mục tiêu là gì?", [], True),
    "need_flexibility": (
        "flexibility",
        "Nếu chậm một chút, có thể lùi hạn không?",
        [("Có thể lùi", "flexible"), ("Phải đúng hạn", "fixed")],
        False,
    ),
    "need_opening": (
        "opening_amount",
        "Bạn đã để dành sẵn bao nhiêu cho mục tiêu này?",
        [("Chưa có", "0")],
        True,
    ),
    "amount_unclear": (
        "target_amount",
        "Mình chưa chắc số tiền, bạn nhập lại giúp (vd 600 triệu)?",
        [],
        True,
    ),
    "horizon_unclear": (
        "horizon",
        "Mình chưa chắc thời hạn, bạn chọn giúp?",
        [("6 tháng", "months:6"), ("1 năm", "months:12"),
         ("3 năm", "months:36"), ("5 năm", "months:60")],
        True,
    ),
}

QUESTION_CODES: tuple[str, ...] = tuple(_CATALOG)


def get_question(code: MessageCode) -> Question:
    """Build the catalog question for `code` (KeyError if not a question code)."""
    slot, text, options, free = _CATALOG[code]
    return Question(
        slot=slot,
        code=code,
        text=text,
        options=[QuestionOption(label=l, value=v) for l, v in options],
        allow_free_text=free,
    )


def parse_option(slot: SlotName, value: str) -> int | str | dict[str, int] | None:
    """Normalise a source="option" answer value; None if it is not a known option."""
    v = value.strip()
    if slot in ("target_amount", "opening_amount"):
        return int(v) if v.isdigit() else None
    if slot == "horizon":
        if v.startswith("months:") and v[7:].isdigit() and 1 <= int(v[7:]) <= 600:
            return {"months": int(v[7:])}
        return None
    if slot == "flexibility":
        return v if v in ("fixed", "flexible") else None
    return None

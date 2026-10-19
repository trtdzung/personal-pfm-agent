"""Fixed question catalog (Vietnamese). The LLM never writes questions."""

from __future__ import annotations

from .contracts import CoachContext, MessageCode, Question, QuestionHint, QuestionOption, SlotName, Slots

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


# ---------------------------------------------------------------- personalisation (code only)

_COMFORT = 0.7  # a pace using 70% of the surplus feels sustainable
_FAR_BEYOND_MONTHS = 120
_MAX_MONTHS = 600
_ROUND = 1_000_000
_SAVINGS_SHARE = 0.3


def fmt_vnd(n: int) -> str:
    """Compact amount, same style as the app ("2,5 tỷ", "600 triệu")."""
    if n >= 10**9:
        return f"{n / 10**9:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " tỷ"
    if n >= 10**6:
        return f"{n / 10**6:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " triệu"
    return f"{n:,}".replace(",", ".")


def fmt_months(n: int) -> str:
    years, months = divmod(n, 12)
    if years == 0:
        return f"{months} tháng"
    return f"{years} năm" if months == 0 else f"{years} năm {months} tháng"


def _months_for(amount: int, monthly: float) -> int:
    return max(1, min(_MAX_MONTHS, -(-amount // max(1, int(monthly)))))


def _horizon_question(q: Question, amount: int, ctx: CoachContext) -> Question:
    surplus = ctx.surplus
    if surplus is None:
        return q
    if surplus <= 0:
        return q.model_copy(update={"hint": QuestionHint(code="no_surplus")})
    fast = _months_for(amount, surplus)
    comfy = _months_for(amount, surplus * _COMFORT)
    slow = min(_MAX_MONTHS, int(comfy * 1.5))
    if fast > _FAR_BEYOND_MONTHS:  # no sensible pace to suggest: keep the generic chips and warn early
        return q.model_copy(update={"hint": QuestionHint(code="far_beyond", months=fast)})
    hint = None
    picks: list[tuple[int, str]] = []
    for months, tag in ((fast, "nhanh nhất"), (comfy, "vừa sức"), (slow, "nhẹ nhàng")):
        if months not in [m for m, _ in picks]:
            picks.append((months, tag))
    options = [QuestionOption(label=f"{fmt_months(m)} · {tag}", value=f"months:{m}") for m, tag in picks]
    return q.model_copy(update={"options": options, "hint": hint})


def _opening_question(q: Question, amount: int, ctx: CoachContext) -> Question:
    options = list(q.options)  # "Chưa có" stays first
    for jar in sorted(ctx.jars, key=lambda j: -j.spendable)[:2]:
        value = min(jar.spendable, amount - 1)
        if value > 0:
            options.append(QuestionOption(label=f"Lấy từ hũ {jar.label[:20]} ({fmt_vnd(value)})", value=str(value)))
    if ctx.savings_balance:
        value = min(int(ctx.savings_balance * _SAVINGS_SHARE) // _ROUND * _ROUND, amount - 1)
        if value >= _ROUND:
            options.append(QuestionOption(label=f"Dùng tiết kiệm ({fmt_vnd(value)})", value=str(value)))
    return q.model_copy(update={"options": options[:6]})


def personalise(q: Question, slots: Slots, ctx: CoachContext | None) -> Question:
    """Shape chips and early warnings from the customer's figures. No context -> the catalog question."""
    if ctx is None or slots.target_amount is None:
        return q
    amount = slots.target_amount.value
    if q.code in ("need_horizon", "horizon_unclear"):
        return _horizon_question(q, amount, ctx)
    if q.code == "need_opening":
        return _opening_question(q, amount, ctx)
    return q

"""When the first message is not a goal: answer like a person, then offer goals that fit the customer's money.

Code only. Figures come from pfm's `context` (average monthly surplus, savings), never from a model.
"""

from __future__ import annotations

import re

from .contracts import CoachContext, CoachReply, CoachRequest, ReplyKind
from .parsing import fold
from .questions import fmt_vnd
from .tone import address, render

_CUES: list[tuple[ReplyKind, re.Pattern[str]]] = [
    ("frustrated", re.compile(r"cung nhac|may moc|robot|(?<!\w)haiz|chan qua|kho chiu|sao cu|bat (?:toi|minh|em) dat")),
    ("advice", re.compile(
        r"goi y|tu van|tai chinh|nen tiet kiem|nen de danh|chua biet|khong biet|muc tieu gi|bat dau tu dau"
        r"|giup (?:toi|minh|em|anh|chi)|lam sao|the nao|nen lam gi|so du|chi tieu")),
    ("greeting", re.compile(r"^\W*(?:xin\s+)?(?:chao|hello|hi|alo|hey)(?!\w)")),
]
_GREETING = re.compile(r"^\W*(?:xin\s+)?(?:chao|hello|hi|alo|hey)(?!\w)")

_TEXT = {
    "greeting": "Chào {you}! {Me} là M-You, giúp {you} lên kế hoạch để dành tiền cho những điều {you} muốn. "
                "{You} đang nghĩ tới điều gì? Chưa nghĩ ra thì thử một gợi ý bên dưới nhé.",
    "frustrated": "Xin lỗi {you} nhé! {You} cứ nói tự nhiên như nhắn tin, ví dụ “đi Nhật cuối năm sau tầm 80 triệu”, "
                  "phần nào còn thiếu {me} sẽ hỏi thêm. Hoặc bấm thử một gợi ý bên dưới.",
    "other": "Phần này {me} chưa hỗ trợ ở đây, {me} chuyên giúp lập kế hoạch để dành tiền thôi. "
             "{You} kể thử một điều muốn dành tiền, hoặc chọn gợi ý bên dưới nhé.",
}
_SHARE = 0.3  # a third of the surplus: comfortable for most people


def classify(text: str) -> ReplyKind:
    f = fold(text)
    return next((kind for kind, rx in _CUES if rx.search(f)), "other")


def _round_m(v: float) -> int:
    """Rounded to a friendly figure: 5 million below 100 million, 10 million above."""
    step = 5_000_000 if v < 100_000_000 else 10_000_000
    return max(step, int(round(v / step)) * step)


def suggestions(ctx: CoachContext | None) -> list[str]:
    """Ready-to-send goal sentences; sized from the surplus when pfm sent it."""
    s = ctx.surplus if ctx else None
    if not s or s <= 0:
        return ["Quỹ dự phòng 20 triệu trong 1 năm", "Du lịch 10 triệu trong 6 tháng", "Mua laptop 20 triệu trong 1 năm"]
    monthly = s * _SHARE
    return [
        f"Quỹ dự phòng {fmt_vnd(_round_m(monthly * 12))} trong 1 năm",
        f"Du lịch {fmt_vnd(_round_m(monthly * 6))} trong 6 tháng",
        f"Mua xe {fmt_vnd(_round_m(s * 0.5 * 36))} trong 3 năm",
    ]


def _advice_text(ctx: CoachContext | None) -> str:
    if not ctx or ctx.surplus is None:
        return ("{Me} chưa xem được số liệu thu chi của {you}, nhưng có thể bắt đầu từ vài mục tiêu phổ biến bên dưới. "
                "{You} bấm thử, hoặc kể điều {you} muốn dành tiền nhé.")
    if ctx.surplus <= 0:
        return ("Mấy tháng gần đây thu và chi của {you} gần như ngang nhau, nên {me} gợi ý bắt đầu nhỏ thôi. "
                "Một quỹ dự phòng nhỏ là bước đầu tốt nhất. {You} chọn thử nhé.")
    parts = [f"Mấy tháng gần đây, mỗi tháng {{you}} còn dư trung bình khoảng {fmt_vnd(ctx.surplus)}"]
    if ctx.savings_balance:
        parts.append(f", và đang có {fmt_vnd(ctx.savings_balance)} tiết kiệm")
    parts.append(f". Để riêng khoảng {fmt_vnd(_round_m(ctx.surplus * _SHARE))} mỗi tháng là vừa sức mà vẫn thoải mái chi tiêu. "
                 "Vài mục tiêu hợp với mức này, {you} bấm thử hoặc kể mục tiêu riêng nhé.")
    return "".join(parts)


def reply(req: CoachRequest) -> CoachReply:
    kind = classify(req.request)
    you, me = address([req.request])
    text = _advice_text(req.context) if kind == "advice" else _TEXT[kind]
    if kind in ("advice", "other", "frustrated") and _GREETING.search(fold(req.request)):
        text = "Chào {you}! " + text
    return CoachReply(kind=kind, text=render(text, you, me)[:400], suggestions=suggestions(req.context))

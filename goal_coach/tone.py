"""How the coach sounds: address the customer the way they talk, acknowledge what they just said.

Code only (no LLM, no added latency). Figures in the lead-in come from the verified slots, never from a model.
Catalog questions carry {you}/{You}/{me}/{Me}; `render` fills them in.
"""

from __future__ import annotations

import re
import zlib

from .contracts import CoachRequest, Horizon, Slots
from .parsing import fold
from .questions import fmt_months, fmt_vnd

MAX_TEXT = 200  # Question.text limit

# Customer refers to themself as anh/chị/cô/chú/bác -> address them so; the coach is "em" / "cháu".
_SELF_RE = re.compile(
    r"(?<!\w)(anh|chị|cô|chú|bác)\s+(?:muốn|định|cần|có|đang|tính|đã|chỉ|sẽ|mới|vẫn|thì|không|chưa|nói|bảo|đặt|để|"
    r"dành|tiết|mua|xây|đi|lo|sợ|nghĩ|thấy|hỏi|chọn|lấy|cứ)(?!\w)"
)
_ME_FOR = {"anh": "em", "chị": "em", "cô": "cháu", "chú": "cháu", "bác": "cháu"}

_CUES: list[tuple[str, re.Pattern[str]]] = [
    ("frustrated", re.compile(r"sao cu hoi|hoi mai|hoi lai|hoi di hoi lai|bi loi|loi roi|bot ngoc|ngoc vay|buc|da noi|noi roi|bao nhieu lan|lam an kieu gi|(?<!\w)lag(?!\w)|vua bao|vua noi")),
    ("worried", re.compile(r"(?<!\w)lo (?:qua|lam|khong)|khong biet co (?:noi|duoc|lam duoc)|kho lam|chac kho|khong noi|(?<!\w)so (?:khong|la)|kho qua")),
    ("thanks", re.compile(r"cam on|thank|thanks")),
    ("greeting", re.compile(r"^(?:\W*(?:em|ad|ban|anh|chi|co|chu|bac)\s+)?\W*(?:chao|hello|hi|alo)(?!\w)")),
]
_PREFIX = {
    "frustrated": "Xin lỗi {you} nhé, {me} hỏi hơi kỹ một chút.",
    "worried": "{You} đừng lo quá, mình tính từng bước là sẽ rõ thôi.",
    "thanks": "Dạ không có gì ạ.",
    "greeting": "Chào {you}!",
}

_SUMMARY = ["{summary}, {me} ghi lại rồi nhé.", "{summary}, nghe hay đấy!", "Được rồi, {summary}."]
_START = ["Hay quá, {me} cùng {you} lên kế hoạch nhé.", "Được, mình cùng bắt đầu nhé."]
_ACK = {
    "target_amount": ["{amount}, {me} ghi nhận nhé.", "Được, {amount}."],
    "horizon": ["{horizon} nhé.", "Ok, {horizon}."],
    "name": ["Tên “{name}” nghe hay đấy.", "Được, mục tiêu “{name}”."],
    "flexible": ["Vậy mình có chút linh hoạt về thời gian.", "Ok, thời gian có thể co giãn một chút."],
    "fixed": ["Rõ rồi, {me} sẽ tính để kịp đúng hạn.", "Ok, mình bám đúng hạn nhé."],
    "opening": ["Có sẵn {amount} là khởi đầu tốt rồi.", "{amount} sẵn có, tốt quá."],
    "opening_zero": ["Chưa có cũng không sao, mình bắt đầu từ bây giờ.", "Không sao, mình bắt đầu từ con số không nhé."],
}


def address(texts: list[str]) -> tuple[str, str]:
    """(you, me) from how the customer talks; ("bạn", "mình") by default."""
    for t in texts:
        m = _SELF_RE.search(t.lower())
        if m:
            return m.group(1), _ME_FOR[m.group(1)]
    return "bạn", "mình"


def _lit(s: str) -> str:
    """A customer/figure value placed into a template: braces must not look like placeholders."""
    return s.replace("{", "(").replace("}", ")")


def render(text: str, you: str, me: str) -> str:
    return text.format(you=you, You=you.capitalize(), me=me, Me=me.capitalize())


def _horizon_text(h: Horizon) -> str:
    if h.months is not None:
        return f"trong {fmt_months(h.months)}"
    y, m = (h.target_month or "").split("-")
    return f"đến tháng {int(m)}/{y}"


def _pick(options: list[str], seed: str) -> str:
    return options[zlib.crc32(seed.encode()) % len(options)]


def _mood(text: str) -> str | None:
    f = fold(text)
    return next((name for name, rx in _CUES if rx.search(f)), None)


def _summary(slots: Slots) -> str | None:
    """"mua xe 600 triệu trong 3 năm" -- needs a name or an amount to sound like the customer's goal."""
    if not slots.name and not slots.target_amount:
        return None
    parts = []
    if slots.name:
        name = _lit(slots.name.value)
        parts.append(name[0].lower() + name[1:] if name[1:2].islower() else name)  # keep "SH", "iPhone"
    if slots.target_amount:
        parts.append(fmt_vnd(slots.target_amount.value))
    if slots.horizon:
        parts.append(_horizon_text(slots.horizon.value))
    if not parts:
        return None
    return " ".join(parts)


def _ack(slot: str, slots: Slots) -> list[str] | None:
    if slot == "target_amount" and slots.target_amount:
        return [x.replace("{amount}", fmt_vnd(slots.target_amount.value)) for x in _ACK["target_amount"]]
    if slot == "horizon" and slots.horizon:
        return [x.replace("{horizon}", _horizon_text(slots.horizon.value)) for x in _ACK["horizon"]]
    if slot == "name" and slots.name:
        return [x.replace("{name}", _lit(slots.name.value)) for x in _ACK["name"]]
    if slot == "flexibility" and slots.flexibility:
        return _ACK[slots.flexibility.value]
    if slot == "opening_amount" and slots.opening_amount is not None:
        v = slots.opening_amount.value
        return [x.replace("{amount}", fmt_vnd(v)) for x in _ACK["opening"]] if v else _ACK["opening_zero"]
    return None


def say(question: str, req: CoachRequest, slots: Slots, captured: set[str]) -> str:
    """Question text as the customer sees it: [mood reply] [acknowledgement] question, in their address form.

    `captured`: slots filled from what the customer said or picked in THIS turn.
    """
    customer_texts = [req.request] + [a.value for a in req.answers if a.source == "text"]
    you, me = address(customer_texts)
    turn = len(req.answers)
    last_text = req.request if turn == 0 else (req.answers[-1].value if req.answers[-1].source == "text" else "")
    seed = f"{req.request}|{turn}"

    mood = _mood(last_text) if last_text else None
    if mood == "greeting" and turn > 0:
        mood = None
    prefix = _PREFIX[mood] if mood else ""

    lead = ""
    if turn == 0:
        summary = _summary(slots) if captured else None
        lead = _pick(_SUMMARY, seed).replace("{summary}", summary) if summary else _pick(_START, seed)
    elif req.answers[-1].slot in captured:
        acks = _ack(req.answers[-1].slot, slots)
        lead = _pick(acks, seed) if acks else ""
    lead = lead[:1].upper() + lead[1:]

    for parts in ((prefix, lead, question), (prefix, question), (question,)):
        text = render(" ".join(p for p in parts if p), you, me)
        if len(text) <= MAX_TEXT:
            return text
    return render(question, you, me)[:MAX_TEXT]

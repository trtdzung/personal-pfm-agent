"""Deterministic guardrails around `POST /chat`: rule-based on purpose (no extra model call, no latency/cost,
easy to audit). Input side: profanity in the customer's message, secrets the customer pastes (card number, OTP,
CVV, password, national id). Output side: profanity, leaked secrets / other customers' ids / the system prompt,
and promises a bank must not make ("đảm bảo lợi nhuận", "chắc chắn được duyệt")."""

import re
import unicodedata
from dataclasses import dataclass, field

MASK = "[đã ẩn]"

PROFANITY_REPLY = (
    "Mình rất sẵn lòng hỗ trợ bạn, nhưng mong bạn dùng ngôn từ lịch sự nhé. "
    "Bạn cần mình giúp gì về tài chính hôm nay?"
)
SENSITIVE_INPUT_NOTE = (
    "Lưu ý: M-You đã ẩn thông tin nhạy cảm bạn vừa gửi. Vì an toàn, bạn vui lòng không gửi số thẻ, "
    "mã OTP, CVV, mật khẩu hay số giấy tờ tùy thân trong khung chat."
)
UNSAFE_OUTPUT_REPLY = "Xin lỗi, mình chưa thể trả lời nội dung này. Bạn có thể hỏi lại theo cách khác được không?"
OVERPROMISE_NOTE = (
    "Lưu ý: mọi khoản tiết kiệm, đầu tư hay vay đều có điều kiện và rủi ro riêng; bạn vui lòng xem "
    "thông tin chính thức tại app MSB hoặc hỏi tư vấn viên."
)

# Unambiguous once diacritics are stripped (also catches the way people type without them).
_ASCII_TERMS = ["dit", "ditme", "dume", "du ma", "du me", "dm", "dmm", "dcm", "dkm", "dmcs", "dcl",
                "vcl", "vkl", "vl", "clm", "cmm", "may ngu", "thang ngu", "do ngu", "con ngu"]
# Only meaningful WITH diacritics: stripped, "lồn"/"cặc"/"buồi"/"ngu" collide with "lớn"/"các"/"buổi"/"ngủ".
_DIACRITIC_TERMS = ["địt", "đụ", "đéo", "cặc", "lồn", "buồi", "cứt", "đĩ", "ngu", "khốn nạn", "mất dạy", "súc vật",
                    # "chó" alone is a pet; only the insult forms count.
                    "thằng chó", "đồ chó", "chó đẻ", "chó chết", "chó má", "óc chó", "lũ chó", "bọn chó",
                    "đứa chó", "đồ con chó", "ngu như chó"]


def _terms_regex(terms: list[str]) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in terms) + r")(?!\w)")


_ASCII_RE = _terms_regex(_ASCII_TERMS)
_DIACRITIC_RE = _terms_regex(_DIACRITIC_TERMS)
_SPELLED_OUT = re.compile(r"\b(?:\w[ .\-_*]+)+\w\b")
_LEET = str.maketrans({"!": "i", "@": "a", "$": "s", "0": "o", "1": "i", "3": "e"})


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").replace("đ", "d")


def _unleet(text: str) -> str:
    return " ".join(tok.translate(_LEET) if any(c.isalpha() for c in tok) else tok for tok in text.split())


def contains_profanity(text: str) -> bool:
    lowered = unicodedata.normalize("NFC", text).lower()
    squashed = _SPELLED_OUT.sub(lambda m: re.sub(r"[ .\-_*]+", "", m.group()), lowered)
    return any(
        _DIACRITIC_RE.search(view) or _ASCII_RE.search(_unleet(_strip_marks(view)))
        for view in (lowered, squashed)
    )


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_VALUE_PATTERNS = [
    # OTP / CVV / PIN code followed by its digits.
    re.compile(r"(?i)\b(?:otp|cvv|cvc|mã\s*pin)\b[^\d\n]{0,20}?(?<!\d)(\d{3,8})(?!\d)"),
    # "mật khẩu ... là X" -- requires the "là"/":"/"=" so "đổi mật khẩu thế nào" is untouched.
    re.compile(r"(?i)(?:mật\s*khẩu|password|passcode)\s*(?:của\s+tôi\s*)?(?:là|:|=)\s*(\S+)"),
    # National id numbers (9-digit CMND / 12-digit CCCD).
    re.compile(r"(?i)\b(?:cccd|cmnd|cmt|căn\s*cước(?:\s*công\s*dân)?|chứng\s*minh(?:\s*nhân\s*dân)?)\b"
               r"[^\d\n]{0,25}?(?<!\d)(\d{12}|\d{9})(?!\d)"),
]


def mask_sensitive_input(text: str) -> tuple[str, bool]:
    found = False

    def card(match: re.Match[str]) -> str:
        nonlocal found
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found = True
            return MASK
        return match.group()

    text = _CARD_RE.sub(card, text)
    for pattern in _VALUE_PATTERNS:
        def value(match: re.Match[str]) -> str:
            nonlocal found
            found = True
            return match.group()[: match.start(1) - match.start()] + MASK

        text = pattern.sub(value, text)
    return text, found


@dataclass
class OutputVerdict:
    text: str
    reasons: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.reasons)


_PROMPT_MARKERS = ["## quy tắc cứng", "## bạn có sẵn những gì", "## khi có skill áp dụng", "## nguyên tắc chung"]
_API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}|\bBearer\s+[A-Za-z0-9._\-]{20,}")
_CIF_RE = re.compile(r"\bCIF_\d+\b")
_OVERPROMISE = [
    "đảm bảo lợi nhuận", "đảm bảo sinh lời", "đảm bảo có lãi", "cam kết lợi nhuận", "cam kết sinh lời",
    "chắc chắn có lãi", "chắc chắn sinh lời", "chắc chắn được duyệt", "chắc chắn được vay",
    "an toàn tuyệt đối", "không có rủi ro", "không rủi ro", "không lo lỗ", "chắc chắn không lỗ", "không bao giờ lỗ",
]
_OVERPROMISE_RE = re.compile("|".join(re.escape(p) for p in _OVERPROMISE))
_NEGATION_RE = re.compile(r"(?<!\w)(?:không|chưa|đừng|chẳng|chớ)(?!\w)")


def _drop_overpromising_sentences(text: str) -> tuple[str, bool]:
    parts = re.split(r"(?<=[.!?])(\s+)", text)
    kept, dropped = [], False
    for i in range(0, len(parts), 2):
        sentence, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        lowered = sentence.lower()
        match = _OVERPROMISE_RE.search(lowered)
        if match and not _NEGATION_RE.search(lowered[max(0, match.start() - 30):match.start()]):
            dropped = True
            continue
        kept.append(sentence + sep)
    return "".join(kept).strip(), dropped


def sanitize_output(text: str, user_id: str) -> OutputVerdict:
    if contains_profanity(text):
        return OutputVerdict(UNSAFE_OUTPUT_REPLY, ["profanity"])
    lowered = text.lower()
    if any(marker in lowered for marker in _PROMPT_MARKERS):
        return OutputVerdict(UNSAFE_OUTPUT_REPLY, ["system_prompt_leak"])

    reasons: list[str] = []
    cleaned, secret = mask_sensitive_input(text)
    cleaned, n_keys = _API_KEY_RE.subn(MASK, cleaned)
    cleaned = _CIF_RE.sub(lambda m: m.group() if m.group() == user_id else MASK, cleaned)
    if secret or n_keys or cleaned != text:
        reasons.append("sensitive_data")
    cleaned, promised = _drop_overpromising_sentences(cleaned)
    if promised:
        cleaned = f"{cleaned}\n\n{OVERPROMISE_NOTE}".strip()
        reasons.append("overpromise")
    return OutputVerdict(cleaned if reasons else text, reasons)

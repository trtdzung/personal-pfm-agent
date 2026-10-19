"""Deterministic egress checks; reject rather than repair unsafe model output."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from collections.abc import Iterable
from guardrails import mask_sensitive_input
from .contracts import CaseResponse, ChatSignalResponse, EducateResponse, InterveneResponse


class GuardViolation(ValueError):
    pass


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").replace("đ", "d")


NUMBER = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")


def _number(token: str) -> Decimal:
    parts = re.split(r"[.,]", token)
    if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
        token = "".join(parts)
    else:
        token = token.replace(",", ".")
    try:
        return Decimal(token)
    except InvalidOperation as exc:
        raise GuardViolation("invalid_number") from exc


def _value(match: re.Match[str], text: str) -> Decimal:
    value = _number(match.group())
    suffix = _plain(text[match.end():match.end()+15]).lstrip()
    for unit, multiplier in [("ty", 1000000000), ("trieu", 1000000), ("nghin", 1000), ("ngan", 1000), ("k", 1000)]:
        if re.match(r"^" + unit + r"(?!\w)", suffix):
            return value * multiplier
    return value / 100 if suffix.startswith("%") else value


def known_numbers(facts: object) -> set[Decimal]:
    out: set[Decimal] = set()
    def visit(value: object) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            number = Decimal(str(value))
            if number.is_finite():
                out.add(number)
        elif isinstance(value, str):
            out.update(_value(m, value) for m in NUMBER.finditer(value))
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(facts)
    return out


def validate_text(text: str, facts: object, *, max_length: int = 1600) -> None:
    if len(text) > max_length:
        raise GuardViolation("too_long")
    plain = _plain(text)
    if re.search(r"https?\s*:|www\.|\b[\w-]+\.(?:com|vn|net|org|io)\b|```|\[[^]]+\]\(", plain):
        raise GuardViolation("link_or_code")
    # Only a quoted scam keyword may contain the phrase 'tài khoản an toàn'.
    checked = re.sub(r'''["'“‘]tai khoan an toan["'”’]''', "", plain)
    if "an toan" in checked or "khong phai lua dao" in plain:
        raise GuardViolation("unsafe_reassurance")
    solicitation = re.sub(r"\b(?:khong(?: bao gio)?|dung)\s+(?:gui|cung cap|nhap|cho|doc|noi|xac nhan)", "NEGATED", plain)
    if re.search(r"(?:gui|cung cap|nhap|cho|doc|noi|xac nhan).{0,50}(?:otp|mat khau|ma pin|cvv)|(?:otp|mat khau).{0,30}(?:la gi|bao nhieu)", solicitation):
        raise GuardViolation("secret_request")
    if mask_sensitive_input(text)[1]:
        raise GuardViolation("secret_leak")
    allowed = known_numbers(facts)
    if any(_value(match, text) not in allowed for match in NUMBER.finditer(text)):
        raise GuardViolation("unsupported_number")


def validate_diagnosis(proposals: Iterable[str], text: str) -> None:
    allowed = {"callback", "emergency_lock", "case", "none"}
    if any(item not in allowed for item in proposals):
        raise GuardViolation("invalid_proposal")
    if re.search(r"tiep tuc chuyen", _plain(text)):
        raise GuardViolation("suggests_continue")


_SCAN_RANKS = {"none": 0, "suspicious": 1, "danger": 2}


_CASE_LABELS = ("thời gian", "số tiền", "tài khoản và ngân hàng nhận", "kẻ gian liên lạc qua kênh nào", "ảnh chụp tin nhắn")
_CASE_KEYS = ("time", "amount", "recipient", "channel", "image")


def validate_case(output: CaseResponse, answers: list[str], facts: object) -> None:
    """The next question must be the first unanswered field; a dossier copies those answers."""
    if len(answers) != 5:
        raise GuardViolation("unknown_case")
    missing = next((i for i, value in enumerate(answers) if not value.strip()), None)
    spoken = " ".join(part for part in (output.next_question, output.guidance) if part)
    if output.dossier is not None:
        spoken += " " + " ".join(getattr(output.dossier, key) for key in _CASE_KEYS)
    if re.search(r"data:image|base64", spoken, re.I):
        raise GuardViolation("image_payload")
    validate_text(spoken, facts, max_length=4000)
    if missing is not None:
        if output.dossier is not None or output.guidance or not output.next_question:
            raise GuardViolation("early_dossier")
        if _plain(_CASE_LABELS[missing]) not in _plain(output.next_question or ""):
            raise GuardViolation("wrong_question")
        return
    if output.next_question is not None or output.dossier is None or not output.guidance:
        raise GuardViolation("missing_dossier")
    if "co quan cong an" not in _plain(output.guidance or ""):
        raise GuardViolation("missing_guidance")
    for key, value in zip(_CASE_KEYS, answers):
        if getattr(output.dossier, key) != value:
            raise GuardViolation("dossier_mismatch")


def validate_educate(output: EducateResponse, article_id: str, allowed_chips: Iterable[str], facts: object) -> None:
    if output.article_id != article_id:
        raise GuardViolation("wrong_article")
    if len(output.summary) != 3 or any(not line.strip() for line in output.summary):
        raise GuardViolation("summary_length")
    permitted = set(allowed_chips)
    if any(chip not in permitted for chip in output.chips):
        raise GuardViolation("invalid_chip")
    validate_text(" ".join(output.summary), facts, max_length=600)


def validate_chat_signal(output: ChatSignalResponse, allowed_ids: Iterable[str]) -> None:
    """Playbook id must come from this turn's search. SC1 only while a scam is in progress."""
    if output.playbook is not None and output.playbook not in set(allowed_ids):
        raise GuardViolation("unknown_playbook")
    if output.suggest_sc1 and not output.scam_in_progress:
        raise GuardViolation("sc1_without_scam")


def validate_scan(level: str, rule_level: str, text: str, facts: object) -> None:
    if rule_level not in _SCAN_RANKS or level not in _SCAN_RANKS or _SCAN_RANKS[level] < _SCAN_RANKS[rule_level]:
        raise GuardViolation("lowered_level")
    validate_text(text, facts)


def validate_intervention(output: InterveneResponse, rule_level: str, allowed_chips: Iterable[str], facts: object) -> None:
    ranks = {"green": 0, "yellow": 1, "red": 2}
    if rule_level not in ranks or ranks[output.level] < ranks[rule_level]:
        raise GuardViolation("lowered_level")
    permitted = set(allowed_chips)
    if any(chip not in permitted for chip in output.chips):
        raise GuardViolation("invalid_chip")
    validate_text(output.message + " " + (output.question or ""), facts)

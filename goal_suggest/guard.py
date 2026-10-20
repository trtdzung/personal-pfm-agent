"""Code decides whether the model's wording may be shown: numbers only from the data, short text, no promises."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# The mock card holds ~150 characters on top and ~90 in the coloured box; these are the hard ceilings.
MAX_OBSERVATION_LEN = 320
MAX_SUGGESTION_LEN = 140
# The question is sent to the chat as if the customer typed it when they tap "Chi tiết".
MAX_QUESTION_LEN = 200

# A number with "." / "," separators, optionally followed by "triệu" / "tỷ" (also spelled "tỉ").
_NUMBER_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)*)(?:\s*(triệu|tỷ|tỉ)(?![\w]))?", re.IGNORECASE)
_SCALE = {"triệu": Decimal(10**6), "tỷ": Decimal(10**9), "tỉ": Decimal(10**9)}
# Promises the model may not make.
_PROMISES = ("chắc chắn", "đảm bảo", "cam kết", "100%", "không rủi ro", "không có rủi ro", "lãi chắc")
_MARKUP = re.compile(r"[*#\n`]")


def _digits(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", "").replace("-", "").lstrip("0") or "0"


def _scaled(raw: str, unit: str) -> Decimal | None:
    groups = re.split(r"[.,]", raw)
    if len(groups) > 1 and len(groups[-1]) != 3:
        number = "".join(groups[:-1]) + "." + groups[-1]
    else:
        number = "".join(groups)
    try:
        return Decimal(number) * _SCALE[unit.lower()]
    except InvalidOperation:
        return None


def number_keys(text: str) -> list[str]:
    """Comparison keys (digits only, "triệu"/"tỷ" expanded) of every number written in `text`."""
    keys: list[str] = []
    for match in _NUMBER_RE.finditer(text):
        raw, unit = match.group(1), match.group(2)
        if unit:
            value = _scaled(raw, unit)
            if value is not None:
                keys.append(_digits(value))
                continue
        keys.append(re.sub(r"[.,]", "", raw).lstrip("0") or "0")
    return keys


def check(observation: str, suggestion: str, question: str, *, data_text: str) -> str | None:
    """None when the wording may be shown, else the reason it is rejected. `data_text` is the text the model was given:
    every number it writes must already be in it."""
    if not observation.strip() or not suggestion.strip() or not question.strip():
        return "empty"
    if len(observation) > MAX_OBSERVATION_LEN:
        return "observation_too_long"
    if len(suggestion) > MAX_SUGGESTION_LEN:
        return "suggestion_too_long"
    if len(question) > MAX_QUESTION_LEN:
        return "question_too_long"
    if not question.rstrip().endswith("?"):
        return "question_not_a_question"
    joined = f"{observation} {suggestion} {question}"
    if _MARKUP.search(joined):
        return "markup"
    lowered = joined.lower()
    if any(p in lowered for p in _PROMISES):
        return "promise"
    allowed = set(number_keys(data_text))
    unknown = [k for k in number_keys(joined) if k not in allowed]
    if unknown:
        return f"number_not_in_data:{unknown[0]}"
    return None

"""Code decides whether the model's wording may be shown: numbers only from facts, known actions, short text."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation

MAX_TITLE_LEN = 60
MAX_BODY_LEN = 220

# A number with "." / "," separators, optionally followed by "triệu" / "tỷ" (also spelled "tỉ").
_NUMBER_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)*)(?:\s*(triệu|tỷ|tỉ)(?!\w))?", re.IGNORECASE)
_SCALE = {"triệu": Decimal(10**6), "tỷ": Decimal(10**9), "tỉ": Decimal(10**9)}


def _digits(value: Decimal) -> str:
    """Comparison key: the digits of the value without separators or leading zeros ("45.5" -> "455")."""
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", "").replace("-", "").lstrip("0") or "0"


def _scaled(raw: str, unit: str) -> Decimal | None:
    """`raw` before "triệu"/"tỷ": a last group that is not 3 digits is the decimal part ("12,5 triệu")."""
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
    """Comparison keys of every number written in `text`."""
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


def allowed_keys(facts: Mapping[str, int | float | str]) -> set[str]:
    """Keys of every number the facts hold: numeric values, plus numbers written inside string values."""
    keys: set[str] = set()
    for value in facts.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            try:
                keys.add(_digits(Decimal(str(value))))
            except InvalidOperation:
                continue
        elif isinstance(value, str):
            keys.update(number_keys(value))
    return keys


def check(
    title: str,
    body: str,
    action_ids: Iterable[str],
    *,
    facts: Mapping[str, int | float | str],
    allowed_action_ids: Iterable[str],
) -> str | None:
    """None when the wording may be shown, else the reason it is rejected."""
    if not title.strip() or not body.strip():
        return "empty"
    if len(title) > MAX_TITLE_LEN:
        return "title_too_long"
    if len(body) > MAX_BODY_LEN:
        return "body_too_long"
    if not set(action_ids) <= set(allowed_action_ids):
        return "unknown_action"
    allowed = allowed_keys(facts)
    for key in number_keys(title) + number_keys(body):
        if key not in allowed:
            return "number_not_in_facts"
    return None

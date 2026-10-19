"""Deterministic Vietnamese amount / horizon parsers. Pure, stdlib only."""

from __future__ import annotations

import re
import unicodedata
from fractions import Fraction

_UNITS: dict[str, int] = {
    "tỷ": 10**9, "tỉ": 10**9, "ty": 10**9,
    "tỏi": 10**9,
    "triệu": 10**6, "trieu": 10**6, "tr": 10**6, "củ": 10**6, "cu": 10**6,
    "nghìn": 10**3, "nghin": 10**3, "ngàn": 10**3, "ngan": 10**3, "k": 10**3,
}
_UNIT_ALT = "|".join(sorted(_UNITS, key=len, reverse=True))
_HALF = r"(?:\s*(?:rưỡi|ruỡi|ruoi))?"

_NUM_UNIT_RE = re.compile(
    rf"(?<![\w.,/\-−])(\d+(?:[.,]\d+)*)\s*({_UNIT_ALT})(?!\w)({_HALF})"
)
_TAIL_RE = re.compile(r"\s+(\d{1,3})(?![\d\w/.,])(\s*\w+)?")
_PLAIN_RE = re.compile(r"(?<![\w.,/\-−])(\d{1,3}(?:[.,]\d{3})+|\d{4,})(?![\w.,/])")
_TIME_WORDS = ("năm", "tháng", "nam", "thang")

_WORD_NUMS: dict[str, int] = {
    "một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "sáu": 6,
    "bảy": 7, "tám": 8, "chín": 9, "mười": 10, "mười một": 11, "mười hai": 12,
}
_WORD_ALT = "|".join(sorted(_WORD_NUMS, key=len, reverse=True))


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower().strip()


def fold(text: str) -> str:
    """Lowercase without diacritics ("Tháng" -> "thang", "đ" -> "d")."""
    t = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return unicodedata.normalize("NFC", "".join(c for c in t if unicodedata.category(c) != "Mn"))


# Typed without diacritics ("50 trieu trong 12 thang"): put the accents back on the words the parsers know.
_ACCENTS = {
    "thang": "tháng", "nam": "năm", "trieu": "triệu", "ty": "tỷ", "ti": "tỉ", "nghin": "nghìn", "ngan": "ngàn",
    "ruoi": "rưỡi", "nua": "nửa", "tram": "trăm", "muoi": "mươi", "mot": "một", "bon": "bốn", "sau": "sáu",
    "bay": "bảy", "tam": "tám", "chin": "chín", "lam": "lăm",
}
_ACCENT_RE = re.compile(r"(?<!\w)(" + "|".join(sorted(_ACCENTS, key=len, reverse=True)) + r")(?!\w)")


def _restore_accents(t: str) -> str:
    """Only for text with no diacritics at all, so "từ tháng 3" is never touched."""
    if t != fold(t):
        return t
    return _ACCENT_RE.sub(lambda m: _ACCENTS[m.group(1)], t)


# Vietnamese number words right before a unit ("ba mươi lăm triệu", "mười tám tháng") -> digits.
_DIGIT_WORDS = {"một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "lăm": 5, "nhăm": 5,
                "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9}
_NUM_WORD = r"(?:một|mốt|hai|ba|bốn|tư|năm|lăm|nhăm|sáu|bảy|bẩy|tám|chín|mười|mươi|trăm|linh|lẻ|rưỡi)"
_WORD_RUN_RE = re.compile(
    rf"(?<!\w)((?:{_NUM_WORD}\s+)*{_NUM_WORD})\s+(tỷ|tỉ|triệu|củ|nghìn|ngàn|tháng|năm)(?!\w)"
)


def _words_value(words: list[str]) -> int | None:
    """[hundreds trăm] [tens mươi | mười | linh] [units]; None when it is not one such number."""
    hundreds = tens = units = None
    i = 0
    if len(words) >= 2 and words[1] == "trăm" and words[0] in _DIGIT_WORDS:
        hundreds, i = _DIGIT_WORDS[words[0]], 2
        if i < len(words) and words[i] == "rưỡi":
            return hundreds * 100 + 50 if i == len(words) - 1 else None
    if i < len(words) and words[i] == "mười":
        tens, i = 1, i + 1
    elif i < len(words) and words[i] in ("linh", "lẻ"):
        tens, i = 0, i + 1
    elif i + 1 < len(words) and words[i + 1] == "mươi" and words[i] in _DIGIT_WORDS:
        tens, i = _DIGIT_WORDS[words[i]], i + 2
    if i < len(words) and words[i] in _DIGIT_WORDS:
        units, i = _DIGIT_WORDS[words[i]], i + 1
    if i != len(words) or (hundreds is None and tens is None and units is None):
        return None
    return (hundreds or 0) * 100 + (tens or 0) * 10 + (units or 0)


def _words_to_digits(t: str) -> str:
    def sub(m: re.Match[str]) -> str:
        v = _words_value(m.group(1).split())
        return f"{v} {m.group(2)}" if v else m.group(0)
    return _WORD_RUN_RE.sub(sub, t)


_EN_UNITS = re.compile(r"(?<=\d)\s*(months?|years?|yrs?)(?!\w)")


def _prep(text: str) -> str:
    """What the parsers read: NFC lowercase, accents restored, number words as digits, "24 months" -> "24 tháng"."""
    t = _words_to_digits(_restore_accents(_norm(text)))
    return _EN_UNITS.sub(lambda m: " tháng" if m.group(1).startswith("month") else " năm", t)


# "15 triệu nhân 6 tháng": a calculation, not an amount the customer stated.
_ARITHMETIC = re.compile(r"(?<!\w)(?:nhân|chia|cộng|trừ|nhan|cong|tru|lần)(?!\w)|[×*]|(?<![a-zà-ỹ])x(?=\s*\d)")


def _num_to_fraction(raw: str, has_unit: bool) -> Fraction | None:
    """'1,2' -> 6/5; '1.200' with a unit -> 1200 (thousands separator)."""
    parts = re.split(r"[.,]", raw)
    if len(parts) == 1:
        return Fraction(int(raw))
    if len(parts) == 2 and not (has_unit and len(parts[1]) == 3):
        return Fraction(int(parts[0])) + Fraction(int(parts[1]), 10 ** len(parts[1]))
    if all(len(p) == 3 for p in parts[1:]):
        return Fraction(int("".join(parts)))
    return None


def parse_amount(text: str) -> int | None:
    """Return a VND amount, or None if unclear / more than one amount."""
    t = _prep(text)
    if not t or "trăm" in t or _ARITHMETIC.search(t):
        return None
    matches = list(_NUM_UNIT_RE.finditer(t))
    if matches:
        # Reject plain numbers next to unit amounts (e.g. "5 tr và 600000000").
        for m in _PLAIN_RE.finditer(t):
            if not any(u.start() <= m.start() < u.end() for u in matches) and not _is_time_context(t, m):
                return None
        return _combine_unit_matches(t, matches)
    plain = [m for m in _PLAIN_RE.finditer(t) if not _is_time_context(t, m)]
    if len(plain) != 1:
        return None
    val = _num_to_fraction(plain[0].group(1), False)
    if val is None or val < 1000 or val.denominator != 1:
        return None
    return int(val)


def _is_time_context(t: str, m: re.Match[str]) -> bool:
    before = t[: m.start()].rstrip()
    after = t[m.end():].lstrip()
    return before.endswith(("năm", "tháng", "/")) or after.startswith(_TIME_WORDS)


def _combine_unit_matches(t: str, matches: list[re.Match[str]]) -> int | None:
    total = Fraction(0)
    last_mult: int | None = None
    prev_end = 0
    for i, m in enumerate(matches):
        mult = _UNITS[m.group(2)]
        if i > 0:
            gap = t[prev_end:m.start()].strip()
            if gap not in ("", "và") or last_mult is None or mult >= last_mult:
                return None
        base = _num_to_fraction(m.group(1), True)
        if base is None:
            return None
        part = base * mult
        if m.group(3).strip():
            part += Fraction(mult, 2)
        end = m.end()
        # "1 tỷ 2" -> 1.2 tỷ ; "1 tỷ 200" -> 1 tỷ 200 triệu (only after the last match)
        if i == len(matches) - 1 and mult >= 10**6 and not m.group(3).strip():
            tail = _TAIL_RE.match(t, end)
            if tail and not (tail.group(2) or "").strip().startswith(_TIME_WORDS):
                digits = tail.group(1)
                if len(digits) == 1:
                    part += Fraction(int(digits) * mult, 10)
                elif len(digits) == 3:
                    part += Fraction(int(digits) * mult, 1000)
                else:
                    return None
                end = tail.start(1) + len(digits)
        total += part
        last_mult = mult
        prev_end = end
    if total.denominator != 1 or total <= 0:
        return None
    return int(total)


# ---------------------------------------------------------------- horizon

_ABS_MONTH_RES = (
    re.compile(r"(?<![\w/])tháng\s*(\d{1,2})\s*(?:[/\-.]|\s+năm\s+)\s*(\d{4})(?!\d)"),
    re.compile(r"(?<![\w/])(\d{1,2})\s*[/\-]\s*(\d{4})(?!\d)"),
)
_ABS_YEAR_RE = re.compile(r"(?<!\w)năm\s*(\d{4})(?!\d)")
_REL_RE = re.compile(
    rf"(?<![\w.,/])(\d+(?:[.,]\d+)?|{_WORD_ALT})\s*(năm|tháng)(?!\w)(\s*rưỡi)?"
)
_HALF_YEAR_RE = re.compile(r"(?<!\w)(?:nửa|nua)\s*năm(?!\w)")


def _qty(raw: str) -> Fraction | None:
    if raw in _WORD_NUMS:
        return Fraction(_WORD_NUMS[raw])
    return _num_to_fraction(raw, False)


def parse_horizon(text: str) -> dict[str, int | str] | None:
    """Return {"months": n} | {"target_month": "YYYY-MM"} | None."""
    t = _prep(text)
    if not t:
        return None
    absolute: list[str] = []
    abs_spans: list[tuple[int, int]] = []
    for rx in _ABS_MONTH_RES:
        for m in rx.finditer(t):
            month, year = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12 and 1900 <= year <= 2200:
                absolute.append(f"{year:04d}-{month:02d}")
                abs_spans.append(m.span())
    if not absolute:
        for m in _ABS_YEAR_RE.finditer(t):
            year = int(m.group(1))
            if 1900 <= year <= 2200:
                absolute.append(f"{year:04d}-12")
    # "tháng 12 năm 2027": the "12 năm" inside a date is not a duration.
    rel = [m for m in _REL_RE.finditer(t) if not any(s <= m.start() < e for s, e in abs_spans)]
    half = list(_HALF_YEAR_RE.finditer(t))
    if absolute:
        if rel or half or len(set(absolute)) != 1:
            return None
        return {"target_month": absolute[0]}
    if half and not rel:
        return {"months": 6} if len(half) == 1 else None
    if half or not rel or len(rel) > 2:
        return None
    months = Fraction(0)
    seen: list[str] = []
    for m in rel:
        q = _qty(m.group(1))
        if q is None:
            return None
        unit = m.group(2)
        seen.append(unit)
        months += q * (12 if unit == "năm" else 1)
        if m.group(3):
            if unit != "năm":
                return None
            months += 6
    if len(rel) == 2:
        # Allow only "N năm M tháng", adjacent.
        if seen != ["năm", "tháng"] or t[rel[0].end():rel[1].start()].strip() not in ("", "và"):
            return None
    if months.denominator != 1 or not 1 <= months <= 600:
        return None
    return {"months": int(months)}

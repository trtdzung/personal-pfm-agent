"""Code-only extraction run before the LLM. Every slot carries a verbatim evidence snippet.

Pure and stdlib-only. When the sentence is clear, the service skips the model entirely;
anything ambiguous is flagged so the LLM (still evidence-checked) decides.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .parsing import (
    _ABS_MONTH_RES,
    _ABS_YEAR_RE,
    _HALF_YEAR_RE,
    _NUM_UNIT_RE,
    _PLAIN_RE,
    _REL_RE,
    _TAIL_RE,
    _TIME_WORDS,
    _is_time_context,
    _num_to_fraction,
    parse_amount,
    parse_horizon,
)

_MIN_PLAIN_AMOUNT = 100_000  # smaller bare numbers are more likely years / counts
_UNIT_WORD = re.compile(r"(?<!\w)(tỷ|tỉ|triệu|củ|nghìn|ngàn)(?!\w)")

_OPEN_BEFORE = re.compile(
    r"(?:đã|đang|hiện|hiện đang|hiện đã)\s+(?:có|tiết kiệm được|để dành được|dành dụm được|gom được|góp được)"
    r"\s*(?:sẵn\s*)?(?:khoảng\s*|tầm\s*|cỡ\s*)?$"
)
_OPEN_AFTER = re.compile(r"^\s*(?:có\s*)?sẵn|^\s*rồi")

_FIXED = re.compile(
    r"không\s+(?:thể\s+|được\s+)?(?:lùi|trễ|chậm|muộn)|phải\s+kịp|đúng\s+hạn|bắt\s+buộc|nhất\s+định\s+phải|không\s+được\s+trễ"
)
_FLEX = re.compile(
    r"không\s+gấp|không\s+vội|(?:có\s+thể|được)\s+lùi|lùi\s+được|linh\s+hoạt|thong\s+thả"
    r"|(?:chậm|trễ|muộn)\s+(?:một\s+|chút\s+)?chút(?:\s+cũng\s+được)?|(?:nếu\s+)?(?:chậm|trễ|muộn)\s+cũng\s+được"
)

_RELATIVE_TIME = re.compile(
    r"(?<!\w)(?:sang\s+năm|năm\s+(?:sau|tới|nay|ngoái|kia)|tháng\s+(?:sau|tới)|tết|(?:cuối|đầu|giữa)\s+năm)(?!\w)"
)

_GOAL_CUE = re.compile(
    r"(?<!\w)(?:tiết kiệm|để dành|dành dụm|tích lũy|gom|mua|xây|sắm|sửa|du lịch|đám cưới|cưới|học phí|quỹ|đặt cọc)(?!\w)"
)
_NEGATIVE_CUE = re.compile(
    r"cổ phiếu|đầu tư|chứng khoán|coin|crypto|chuyển|số dư|trả nợ|rút|nạp|vay|lãi suất|biếu|vàng"
)
_INJECTION_CUE = re.compile(r"bỏ qua|hướng dẫn|chỉ dẫn|ignore|system|prompt|instruction")

_NAME_START = re.compile(
    r"(?<!\w)(?:mua|xây|sắm|sửa|đi|du lịch|học phí|học|đám cưới|cưới|đặt cọc|mở|quỹ)(?!\w)"
)
_NAME_FOR = re.compile(r"(?:tiết kiệm|để dành|dành dụm|tích lũy)\s+(?:tiền\s+)?(?:để|cho)\s+(.+)$")
_NAME_FILLER = {
    "khoảng", "tầm", "cỡ", "hết", "là", "với", "giá", "trị", "trong", "vào", "cần", "có", "được", "đến",
    "chừng", "khoảng chừng", "dự", "định", "và", "mà", "thì", "cho", "mất", "hơn", "gần",
}


@dataclass
class FastResult:
    """What code alone could read from one sentence."""

    amount: tuple[int, str] | None = None
    opening: tuple[int, str] | None = None
    horizon: tuple[dict[str, int | str], str] | None = None
    flexibility: tuple[str, str] | None = None
    name: tuple[str, str] | None = None
    horizon_relative: bool = False  # "cuối năm sau": needs today's date -> ask again
    ambiguous_amount: bool = False
    ambiguous_horizon: bool = False
    unit_word_no_amount: bool = False  # money words but nothing parseable
    injection: bool = False
    goal_hint: bool = False  # confident enough that this is a savings goal


def find_flexibility(text: str) -> tuple[str, str] | None:
    """('fixed'|'flexible', evidence) from keywords; None when absent or contradictory."""
    t = unicodedata.normalize("NFC", text).lower()
    fixed = _FIXED.search(t)
    rest = _FIXED.sub(" ", t) if fixed else t
    flex = _FLEX.search(rest)
    if fixed and flex:
        return None
    if fixed:
        return ("fixed", text_slice(text, t, fixed))
    if flex:
        # `rest` can shift offsets only when `fixed` matched, which returned above.
        return ("flexible", text_slice(text, t, flex))
    return None


def text_slice(original: str, lowered: str, m: re.Match[str]) -> str:
    """Slice of the original text for a match found on its lowercase copy."""
    nfc = unicodedata.normalize("NFC", original)
    return nfc[m.start():m.end()] if len(nfc) == len(lowered) else lowered[m.start():m.end()]


def _amount_spans(t: str) -> tuple[list[tuple[int, int, int]], bool]:
    """(start, end, vnd) spans plus an 'ambiguous' flag."""
    spans: list[tuple[int, int, int]] = []
    ambiguous = False
    matches = list(_NUM_UNIT_RE.finditer(t))
    i = 0
    while i < len(matches):
        best: tuple[int, int, int] | None = None
        for j in range(len(matches) - 1, i - 1, -1):
            ends = [matches[j].end()]
            tail = _TAIL_RE.match(t, matches[j].end())
            if tail and not (tail.group(2) or "").strip().startswith(_TIME_WORDS):
                ends.insert(0, tail.start(1) + len(tail.group(1)))
            for e in ends:
                v = parse_amount(t[matches[i].start():e])
                if v is not None:
                    best = (j, e, v)
                    break
            if best:
                break
        if best is None:
            return [], True
        j, e, v = best
        spans.append((matches[i].start(), e, v))
        i = j + 1
    for m in _PLAIN_RE.finditer(t):
        if any(s <= m.start() < e for s, e, _ in spans) or _is_time_context(t, m):
            continue
        val = _num_to_fraction(m.group(1), False)
        if val is None or val.denominator != 1:
            ambiguous = True
            continue
        if 1900 <= val <= 2200:
            continue  # looks like a year
        if val < _MIN_PLAIN_AMOUNT:
            ambiguous = True
            continue
        spans.append((m.start(), m.end(), int(val)))
    spans.sort()
    return spans, ambiguous


def _horizon(t: str) -> tuple[tuple[int, int] | None, bool]:
    """Union span of horizon expressions; second value is True when they cannot be combined."""
    found: list[re.Match[str]] = []
    for rx in (*_ABS_MONTH_RES, _ABS_YEAR_RE, _REL_RE, _HALF_YEAR_RE):
        found.extend(rx.finditer(t))
    if not found:
        return None, False
    return (min(m.start() for m in found), max(m.end() for m in found)), False


def _name(src: str, t: str, first_span_start: int | None) -> tuple[str, str] | None:
    prefix = src[:first_span_start] if first_span_start is not None else src
    phrase = ""
    m_for = _NAME_FOR.search(t[: len(prefix)])
    if m_for:
        phrase = src[m_for.start(1): len(prefix)].strip()
    else:
        m = _NAME_START.search(t[: len(prefix)])
        if m:
            phrase = src[m.start(): len(prefix)].strip()
    words = phrase.strip(" ,.;:!?").split()
    while words and words[-1].lower() in _NAME_FILLER:
        words.pop()
    if not 2 <= len(words) <= 5 or any(re.search(r"\d", w) for w in words):
        return None
    out = " ".join(words)
    return (out, out)


def fast_extract(text: str) -> FastResult:
    """Read amount, opening, horizon, flexibility and (conservatively) name from `text`."""
    out = FastResult()
    src = unicodedata.normalize("NFC", text)
    t = src.lower()
    if len(t) != len(src):  # exotic casing that changes length: let the LLM handle it
        out.injection = True
        return out
    out.injection = bool(_INJECTION_CUE.search(t))

    spans, out.ambiguous_amount = _amount_spans(t)
    targets: list[tuple[int, int, int]] = []
    openings: list[tuple[int, int, int]] = []
    for s, e, v in spans:
        before = t[max(0, s - 30):s]
        if _OPEN_BEFORE.search(before) or _OPEN_AFTER.match(t[e:e + 12]):
            openings.append((s, e, v))
        else:
            targets.append((s, e, v))
    if len(targets) == 1:
        s, e, v = targets[0]
        out.amount = (v, src[s:e])
    elif len(targets) > 1:
        out.ambiguous_amount = True
    if len(openings) == 1:
        s, e, v = openings[0]
        out.opening = (v, src[s:e])
    elif len(openings) > 1:
        out.ambiguous_amount = True
    if not spans and not out.ambiguous_amount and _UNIT_WORD.search(t):
        out.unit_word_no_amount = True

    hs, _ = _horizon(t)
    if hs is not None:
        span_text = src[hs[0]:hs[1]]
        parsed = parse_horizon(span_text)
        if parsed is not None:
            out.horizon = (parsed, span_text)
        else:
            out.ambiguous_horizon = True
    elif _RELATIVE_TIME.search(t):
        out.horizon_relative = True

    out.flexibility = find_flexibility(src)

    starts = [s for s, _, _ in targets] + ([hs[0]] if hs else [])
    out.name = _name(src, t, min(starts) if starts else None)

    have = (out.amount is not None) + (out.horizon is not None)
    if not out.injection and not _NEGATIVE_CUE.search(t):
        out.goal_hint = have == 2 or (have == 1 and bool(_GOAL_CUE.search(t)))
    return out

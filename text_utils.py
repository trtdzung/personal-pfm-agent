import datetime
import json
import logging
import math
import re

logger = logging.getLogger("personal-card-agent")

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_STRAY_THINK_TAG_RE = re.compile(r"</?think>")
_FENCED_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```", re.DOTALL)
_FENCE_MARKER_RE = re.compile(r"```[a-zA-Z0-9_-]*")
_BLANK_RUN_RE = re.compile(r"\n{3,}")
_VALID_CHART_TYPES = {"bar", "line", "pie"}
# The 10 default expense categories every pfm customer has. Not the whole story: a customer can also create
# their own (id `c_<slug>`), so a category id is valid when it is a default OR looks like a custom one. That is a
# SHAPE check; whether this customer really has it is checked from `get_categories` (ui_guard.py) and by pfm.
_VALID_EXPENSE_CATEGORIES = {
    "housing",
    "utilities",
    "subscriptions",
    "insurance",
    "dining",
    "transport",
    "shopping",
    "groceries",
    "entertainment",
    "health",
}


_CUSTOM_CATEGORY_RE = re.compile(r"^c_[a-z0-9][a-z0-9_-]*$")


def _is_valid_category_id(value: object) -> bool:
    return isinstance(value, str) and (value in _VALID_EXPENSE_CATEGORIES or bool(_CUSTOM_CATEGORY_RE.match(value)))


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks some OpenAI-compatible
    endpoints (e.g. GLM served via GreenNode's MaaS) leave inline in the
    message content instead of a separate reasoning_content field -- along
    with any stray unmatched <think>/</think> tag left behind."""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _STRAY_THINK_TAG_RE.sub("", text)
    return text.strip()


# The model (a multilingual LLM answering in Vietnamese) occasionally slips a word in another script
# into a sentence -- seen in production-like runs: "远远 chưa đạt mục tiêu", "trả全额". Vietnamese uses
# Latin letters only, so any character from these scripts is a glitch. Checked by script range rather
# than a blocklist of words: it is not always Chinese, and a range check costs ~20 µs per answer.
_FOREIGN_SCRIPT_CLASS = (
    "\u0400-\u052f"  # Cyrillic (+ supplement)
    "\u0590-\u06ff"  # Hebrew, Arabic
    "\u0e00-\u0e7f"  # Thai
    "\u1100-\u11ff"  # Hangul jamo
    "\u3040-\u30ff"  # Hiragana, Katakana
    "\u3100-\u312f"  # Bopomofo
    "\u3130-\u318f\uac00-\ud7af"  # Hangul
    "\u3200-\u32ff"  # enclosed CJK
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"  # CJK ideographs
    "\U00020000-\U0002fa1f"  # CJK extensions
    "\u3000-\u303f"  # CJK punctuation (fullwidth ASCII punctuation is converted first)
)
_FOREIGN_RUN_RE = re.compile(f"(?P<pre>[ \\t]*)(?P<run>[{_FOREIGN_SCRIPT_CLASS}]+)")
_CJK_PUNCTUATION = {0x3001: ", ", 0x3002: ". ", 0x3000: " "}
# "，" -> ", " (with a space: the model writes it glued to the next word); brackets stay unspaced.
_FULLWIDTH_TO_ASCII = {
    code: (chr(code - 0xFEE0) + " " if chr(code - 0xFEE0) in ",.;:!?" else chr(code - 0xFEE0))
    for code in range(0xFF01, 0xFF5F)
}
_WORD_CHAR = re.compile(r"\w")


def strip_foreign_script(text: str) -> str:
    """Remove stray non-Latin-script characters (CJK, Hangul, Kana, Cyrillic, Thai, Arabic, Hebrew) that
    the model sometimes drops into a Vietnamese answer, keeping the sentence readable.

    Fullwidth punctuation (",", ":", ".") becomes its ASCII form instead of vanishing, and a removed run
    leaves at most one space so words on either side do not fuse. Only apply it to the assistant's
    answer text -- never to text the user typed, tool output, or the ui-json block. Text without such
    characters is returned unchanged (identical string).
    """
    translated = text.translate({**_FULLWIDTH_TO_ASCII, **_CJK_PUNCTUATION})
    if not _FOREIGN_RUN_RE.search(translated) and translated == text:
        return text
    text = translated
    removed = "".join(m.group("run") for m in _FOREIGN_RUN_RE.finditer(text))

    def _drop(match: re.Match) -> str:
        pre = match.group("pre")
        after = text[match.end()] if match.end() < len(text) else "\n"
        if after in ",.;:!?)" or after.isspace():
            return ""  # "tháng 全额." -> "tháng." / "đạt,远远 chưa" -> "đạt, chưa": what follows already separates
        before = text[match.start() - 1] if match.start() > 0 else "\n"
        if not pre and _WORD_CHAR.match(before):
            return " "  # "trả全额nợ" -> "trả nợ": glued on both sides, keep the words apart
        return pre  # "abc 全额def" -> "abc def"

    cleaned = _FOREIGN_RUN_RE.sub(_drop, text)
    cleaned = re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", cleaned)  # "đạt,  chưa" -> "đạt, chưa" (never touches indentation)
    if removed:
        logger.warning("stripped %d foreign-script character(s) from an answer: %r", len(removed), removed[:20])
    return cleaned.strip()


def extract_final_text(content: object) -> str:
    """Pull just the final answer text out of a message's content.

    Reasoning-capable models (e.g. gpt-5.5, GLM) return content as a list of
    blocks (reasoning + text) instead of a plain string, or as a plain
    string with a stray <think>...</think> block inline -- this returns
    only the actual answer text, not raw reasoning/ids/tags.
    """
    if isinstance(content, str):
        return _strip_think_tags(content)
    if isinstance(content, list):
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if texts:
            return _strip_think_tags("\n".join(texts))
    return str(content)


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_valid_chart(raw: dict) -> bool:
    """Validate a parsed chart payload (raw["type"] == "chart") per
    docs/chart-output-rules.md Part B. Pure validation only -- no
    normalizing/auto-fixing a payload that doesn't pass (e.g. trimming an
    over-long `series` for `pie`): the correct format is the model's
    responsibility (see the prompt in
    skills/project/data-visualization/SKILL.md); anything that fails here
    means the whole block is dropped (`ui: None`), not patched up.
    """
    chart_type = raw.get("chart_type")
    if chart_type not in _VALID_CHART_TYPES:
        return False

    labels = raw.get("labels")
    if not isinstance(labels, list) or not labels or not all(isinstance(label, str) for label in labels):
        return False

    series = raw.get("series")
    if not isinstance(series, list) or not series:
        return False

    for item in series:
        if not isinstance(item, dict):
            return False
        name = item.get("name")
        data = item.get("data")
        if not isinstance(name, str):
            return False
        if not isinstance(data, list) or not data or not all(_is_finite_number(v) for v in data):
            return False
        if len(data) != len(labels):
            return False

    # A "pie" chart is single-series by definition -- SKILL.md tells the
    # model to emit exactly 1, and a payload with more than 1 is rejected
    # outright rather than silently trimmed to series[0].
    if chart_type == "pie" and len(series) != 1:
        return False

    return True


def _is_valid_transfer_form(raw: dict) -> bool:
    """Validate a parsed transfer_form payload (raw["type"] ==
    "transfer_form"). Pure validation only -- same "no auto-fixing" rule as
    _is_valid_chart (see skills/project/transfer-form/SKILL.md for the
    model-facing rules this mirrors). This is a *display-only* proposal --
    the customer taps a real bank confirmation flow to actually transfer
    money, this repo never executes anything -- but the amount/recipient
    still have to be real enough that a customer isn't misled into
    confirming a bogus transfer.

    Two distinct shapes share this one `type` (see
    backend_docs/pfm-read-api.md for the beneficiary_id shape):

    - Case A, card-debt payment: `recipient` + `account_number` -- the
      recipient is always "MSB" itself here, so the model states it plainly
      instead of looking it up.
    - Case B, transfer to a saved beneficiary: `beneficiary_id` (must be an
      `id` from `query_beneficiaries()`, never a name/account the model
      invented) + `category` (a valid category id, see _is_valid_category_id) -- `pfm`
      looks up the real name/account/bank itself from `beneficiary_id`, so
      this repo must never emit `recipient`/`account_number` for this case.

    Both shapes require `amount` (positive, finite) and `note`.
    """
    amount = raw.get("amount")
    if not _is_finite_number(amount) or amount <= 0:
        return False

    # The bank transfer's actual content/message field ("nội dung chuyển
    # khoản") -- required, not just an internal explanation, since the
    # customer's real transfer needs this filled in.
    note = raw.get("note")
    if not isinstance(note, str) or not note:
        return False

    beneficiary_id = raw.get("beneficiary_id")
    if beneficiary_id is not None:
        # Case B: beneficiary_id present means this must be the new
        # pfm-lookup shape -- recipient/account_number must NOT also be
        # present (the model must never emit both shapes at once, and must
        # never supply a real account number itself in this case).
        if not isinstance(beneficiary_id, str) or not beneficiary_id:
            return False
        if "recipient" in raw or "account_number" in raw:
            return False
        category = raw.get("category")
        if not _is_valid_category_id(category):
            return False
        return True

    # Case A: legacy recipient/account_number shape (card-debt payment).
    recipient = raw.get("recipient")
    if not isinstance(recipient, str) or not recipient:
        return False

    account_number = raw.get("account_number")
    if not isinstance(account_number, str) or not account_number:
        return False

    return True


def _is_valid_category_ids(value: object) -> bool:
    """`category_ids` of a jar: a list (may be empty) of distinct category ids (see _is_valid_category_id).

    Distinct because pfm keeps one category in exactly one jar; a repeat inside one
    payload can only be a model slip.
    """
    return (
        isinstance(value, list)
        and all(_is_valid_category_id(c) for c in value)
        and len(set(value)) == len(value)
    )


def _has_jar_basics(raw: dict) -> bool:
    """Fields create_jar and edit_jar share: a name, a positive monthly limit, a reason."""
    jar_name = raw.get("jar_name")
    if not isinstance(jar_name, str) or not jar_name:
        return False

    allocation_amount = raw.get("allocation_amount")
    if not _is_finite_number(allocation_amount) or allocation_amount <= 0:
        return False

    reason = raw.get("reason")
    return isinstance(reason, str) and bool(reason)


def _is_valid_create_jar(raw: dict) -> bool:
    """Validate a parsed create_jar payload (raw["type"] == "create_jar").
    Pure validation only -- same "no auto-fixing" rule as _is_valid_chart
    (see skills/project/spending-jar/SKILL.md for the model-facing rules
    this mirrors, docs/jars/create-edit-jar.md for the contract). Display-only
    proposal -- the jar is created by pfm when the customer confirms, this
    repo never executes anything.

    `category_ids` is required (an empty list is fine: a jar with no
    category). There is no `jar_id`: pfm generates it, so a payload carrying
    one is a model slip and is dropped.

    `initial_balance` is required too (backend_docs B2, since 2026-09-23): the
    money moved into the new jar, a whole number of VND >= 0 (0 is valid). pfm
    drops a create_jar without it and never reads the gap as 0, so an agent that
    leaves it out only produces a form the customer never sees. Whether it fits
    the "Chờ phân bổ" (`allocationHeadroom`) is pfm's check, like the other numbers.
    """
    if "jar_id" in raw:
        return False
    if not _has_jar_basics(raw):
        return False
    balance = raw.get("initial_balance")
    if not _is_finite_number(balance) or balance < 0 or balance != int(balance):
        return False
    return _is_valid_category_ids(raw.get("category_ids"))


def _is_valid_edit_jar(raw: dict) -> bool:
    """Validate a parsed edit_jar payload (raw["type"] == "edit_jar").

    The jar is identified by `jar_id` (the `id` from `get_jar_summary`), never
    by name -- pfm ignores an id it does not know. `category_ids`, when
    present, is the jar's FULL new category list; leaving it out means "do not
    change categories".
    """
    jar_id = raw.get("jar_id")
    if not isinstance(jar_id, str) or not jar_id:
        return False
    if not _has_jar_basics(raw):
        return False
    return "category_ids" not in raw or _is_valid_category_ids(raw["category_ids"])


# The unallocated money ("Chưa phân bổ") a rebalance may draw from; never a jar id.
_POOL_SOURCE_ID = "pool"


def _valid_allocations(allocations: object, forbidden: set[str]) -> bool:
    """`[{"to_jar_id": str, "amount": number > 0}]`, non-empty: each receiving jar once, never one of `forbidden`
    (the pool, and for a jar-to-jar move the giving jar itself)."""
    if not isinstance(allocations, list) or not allocations:
        return False
    receivers: set[str] = set()
    for allocation in allocations:
        if not isinstance(allocation, dict):
            return False
        receiver = allocation.get("to_jar_id")
        if not isinstance(receiver, str) or not receiver or receiver in forbidden or receiver in receivers:
            return False
        receivers.add(receiver)
        amount = allocation.get("amount")
        if not _is_finite_number(amount) or amount <= 0:
            return False
    return True


def _is_valid_rebalance_jars(raw: dict) -> bool:
    """Validate a parsed rebalance_jars payload (raw["type"] == "rebalance_jars"): ONE jar (`from_jar_id`) gives
    money to one or more other jars (`allocations`, the same shape distribute_amount uses). Since 2026-09-24; the
    older shape (`target_jar_id`/`shortfall`/`moves`: one jar receiving from many sources) is no longer accepted.

    Shape only: the giving jar is a real-looking jar id (never `"pool"`, that is distribute_amount's source), each
    receiving jar appears once and is not the giving jar, amounts are positive. Whether the giver has that much
    (`spendable`) and whether the ids exist is checked from the summary the agent read (ui_guard.py,
    jar_checks.py) and again by pfm.
    """
    source = raw.get("from_jar_id")
    if not isinstance(source, str) or not source or source == _POOL_SOURCE_ID:
        return False
    if not _valid_allocations(raw.get("allocations"), {_POOL_SOURCE_ID, source}):
        return False
    reason = raw.get("reason")
    return isinstance(reason, str) and bool(reason)


def _is_valid_distribute_amount(raw: dict) -> bool:
    """Validate a parsed distribute_amount payload (raw["type"] == "distribute_amount"): share the "Chưa phân bổ"
    (unallocated) money into several jars. The pool is the implicit source, so `allocations` only names the
    receiving jars.

    Shape only, like the other jar forms: positive amounts, each jar once, a real-looking jar id (never `"pool"`,
    that is the source). Whether the total fits in the pool and whether the ids exist is checked from the summary
    the agent read (ui_guard.py, jar_checks.py) and again by pfm.
    """
    if not _valid_allocations(raw.get("allocations"), {_POOL_SOURCE_ID}):
        return False
    reason = raw.get("reason")
    return isinstance(reason, str) and bool(reason)


_MIN_CLARIFY_OPTIONS = 2
_MAX_CLARIFY_OPTIONS = 4
_MIN_CLARIFY_QUESTIONS = 1
_MAX_CLARIFY_QUESTIONS = 4


def _is_valid_clarify_question(raw: object) -> bool:
    """One entry of `questions`: `{question: str, options: [str, ...]}`, nothing else."""
    if not isinstance(raw, dict) or set(raw) != {"question", "options"}:
        return False
    question = raw["question"]
    if not isinstance(question, str) or not question:
        return False
    options = raw["options"]
    if not isinstance(options, list) or not (_MIN_CLARIFY_OPTIONS <= len(options) <= _MAX_CLARIFY_OPTIONS):
        return False
    seen: set[str] = set()
    for option in options:
        if not isinstance(option, str) or not option or option in seen:
            return False
        seen.add(option)
    return True


def _is_valid_clarify_options(raw: dict) -> bool:
    """Validate a parsed clarify_options payload (raw["type"] == "clarify_options"). A cross-cutting
    widget any skill can emit instead of an open-ended follow-up question when there are 1-4 independent
    decisions, each with 2-4 concrete, mutually exclusive choices grounded in real data (see
    skills/project/clarify-options/SKILL.md).

    Schema v3 (2026-09-23): `questions` is a list (matching the AskUserQuestion tool's own `questions`
    array), always used even for a single question, so there is exactly one shape to get right. Each
    question's `question`/`options` live together (schema v2's fix, kept: server.py clears `answer` to ""
    whenever this type is valid, so nothing is ever shown twice). `options` stays a plain list of strings:
    the old `{id, label}` object shape is gone, because `id` was never read back by the agent (only the
    tapped string ever reaches the next turn as a plain chat message) and the model kept reinventing its
    name (`value`, `text`) instead of leaving it alone -- removing the unused field removes that failure
    mode.
    """
    questions = raw.get("questions")
    if not isinstance(questions, list) or not (_MIN_CLARIFY_QUESTIONS <= len(questions) <= _MAX_CLARIFY_QUESTIONS):
        return False
    if not all(_is_valid_clarify_question(q) for q in questions):
        return False
    return set(raw) == {"type", "questions"}


# --- goals ("Mục tiêu", pfm goals-v2) ---------------------------------------------------------------------------------
# Same "no auto-fixing" rule as the jar forms; every form lists its keys, so a field of pfm's own action (or a stray one)
# is a model slip and drops the form. Whether an id exists / a date is after pfm's today is `ui_guard`'s and pfm's check.

_GOAL_TEMPLATES = {"car", "house", "travel", "education", "emergency", "wedding", "retirement", "other"}
_GOAL_FLEXIBILITIES = {"date_fixed", "date_flexible", "amount_flexible"}
_HAND_VALUED_ASSETS = {"house", "car", "motorbike", "other"}
_MARKET_ASSETS = {"gold", "stock", "external_fund"}
_ACCRUING_ASSETS = {"deposit", "bond"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_whole_money(value: object, minimum: int = 1) -> bool:
    return _is_finite_number(value) and value == int(value) and value >= minimum


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_percent(value: object) -> bool:
    return _is_finite_number(value) and 0 <= value <= 100


def _has_goal_reason(raw: dict) -> bool:
    return _non_empty_str(raw.get("reason"))


_MONTHLY_DAY_MAX = 28  # pfm sets the auto-debit on day 1..28


def _has_valid_monthly_plan(raw: dict) -> bool:
    """`monthly_amount` and `monthly_day` (the monthly saving plan = pfm's auto-debit) are both present or both absent."""
    has_amount, has_day = "monthly_amount" in raw, "monthly_day" in raw
    if has_amount != has_day:
        return False
    if not has_amount:
        return True
    day = raw["monthly_day"]
    return _is_whole_money(raw["monthly_amount"]) and isinstance(day, int) and not isinstance(day, bool) and 1 <= day <= _MONTHLY_DAY_MAX


def _is_valid_create_goal(raw: dict) -> bool:
    # `flexibility` is no longer asked for (pfm treats every goal as flexible); it is still accepted so an old habit does not drop the form.
    required = {"type", "goal_name", "template", "target_amount", "target_date", "initial_deposit", "reason"}
    if not required <= set(raw) or not set(raw) <= required | {"flexibility", "monthly_amount", "monthly_day"}:
        return False
    return (
        _non_empty_str(raw["goal_name"])
        and raw["template"] in _GOAL_TEMPLATES
        and _is_whole_money(raw["target_amount"])
        and _is_iso_date(raw["target_date"])
        and ("flexibility" not in raw or raw["flexibility"] in _GOAL_FLEXIBILITIES)
        and _is_whole_money(raw["initial_deposit"], 0)
        and _has_valid_monthly_plan(raw)
        and _has_goal_reason(raw)
    )


def _is_valid_edit_goal(raw: dict) -> bool:
    if not set(raw) <= {"type", "goal_id", "goal_name", "new_target_date", "new_target_amount", "monthly_amount", "monthly_day", "reason"}:
        return False
    if not ({"new_target_date", "new_target_amount", "monthly_amount"} & set(raw)):
        return False
    if not _has_valid_monthly_plan(raw):
        return False
    if "new_target_date" in raw and not _is_iso_date(raw["new_target_date"]):
        return False
    if "new_target_amount" in raw and not _is_whole_money(raw["new_target_amount"]):
        return False
    return _non_empty_str(raw.get("goal_id")) and _non_empty_str(raw.get("goal_name")) and _has_goal_reason(raw)


def _is_valid_close_goal(raw: dict) -> bool:
    return set(raw) == {"type", "goal_id", "goal_name", "reason"} and all(_non_empty_str(raw[k]) for k in ("goal_id", "goal_name", "reason"))


def _is_valid_accrual(value: object) -> bool:
    if not isinstance(value, dict) or not set(value) <= {"principal", "rate_pa", "start_date", "maturity_date"}:
        return False
    if not ({"principal", "rate_pa", "start_date"} <= set(value)):
        return False
    if not (_is_whole_money(value["principal"]) and _is_finite_number(value["rate_pa"]) and value["rate_pa"] >= 0 and _is_iso_date(value["start_date"])):
        return False
    if "maturity_date" in value:
        return _is_iso_date(value["maturity_date"]) and value["maturity_date"] >= value["start_date"]
    return True


def _is_valid_add_asset(raw: dict) -> bool:
    category = raw.get("category")
    common = {"type", "goal_id", "category", "asset_name", "count_percent", "reason", "institution"}
    if category in _HAND_VALUED_ASSETS:
        allowed, specific = common | {"value"}, _is_whole_money(raw.get("value"))
    elif category in _MARKET_ASSETS:
        allowed = common | {"instrument_id", "quantity"}
        quantity = raw.get("quantity")
        specific = _non_empty_str(raw.get("instrument_id")) and _is_finite_number(quantity) and quantity > 0
    elif category in _ACCRUING_ASSETS:
        allowed, specific = common | {"accrual"}, _is_valid_accrual(raw.get("accrual"))
    else:
        return False
    if not set(raw) <= allowed or not specific:
        return False
    if "institution" in raw and not isinstance(raw["institution"], str):
        return False
    return _non_empty_str(raw.get("goal_id")) and _non_empty_str(raw.get("asset_name")) and _is_percent(raw.get("count_percent")) and _has_goal_reason(raw)


def _is_valid_edit_asset(raw: dict) -> bool:
    if not (_non_empty_str(raw.get("asset_id")) and _non_empty_str(raw.get("asset_name")) and _has_goal_reason(raw)):
        return False
    change, base = raw.get("change"), {"type", "asset_id", "asset_name", "change", "reason"}
    if change == "revalue":
        if not set(raw) <= base | {"value", "count_percent"} or not _is_whole_money(raw.get("value")):
            return False
        return "count_percent" not in raw or _is_percent(raw["count_percent"])
    if change == "quantity":
        return set(raw) == base | {"quantity"} and _is_finite_number(raw["quantity"]) and raw["quantity"] > 0
    if change == "remove":
        return set(raw) == base
    return False


# Dispatch table: ui block "type" -> validator. Add an entry here (and a new
# _is_valid_<type> function above) for each new widget type -- every type
# shares the same ```ui-json fence and the same envelope shape
# {"type": ..., ...type-specific fields}.
_UI_VALIDATORS = {
    "chart": _is_valid_chart,
    "transfer_form": _is_valid_transfer_form,
    "create_jar": _is_valid_create_jar,
    "edit_jar": _is_valid_edit_jar,
    "rebalance_jars": _is_valid_rebalance_jars,
    "distribute_amount": _is_valid_distribute_amount,
    "clarify_options": _is_valid_clarify_options,
    "create_goal": _is_valid_create_goal,
    "edit_goal": _is_valid_edit_goal,
    "close_goal": _is_valid_close_goal,
    "add_asset": _is_valid_add_asset,
    "edit_asset": _is_valid_edit_asset,
}


def _is_valid_ui(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    validator = _UI_VALIDATORS.get(raw.get("type"))
    return validator is not None and validator(raw)


def is_valid_ui(raw: object) -> bool:
    """Public form of the ui shape check, for code that builds a `ui` itself (jar_endpoint.py)."""
    return _is_valid_ui(raw)


def _find_json_objects(text: str) -> list[tuple[int, int, object]]:
    """Find every top-level JSON object literal embedded in `text`.

    Scans left to right for '{' and attempts a real JSON decode from each
    position (via json.JSONDecoder.raw_decode, so nested braces/strings are
    handled correctly, not naive brace-counting). This is intentionally
    fence-agnostic: it finds an embedded ui-json object whether or not the
    model wrapped it in a ```ui-json fence, closed the fence properly, or
    used the exact expected label -- SKILL.md tells the model to use that
    fence, but a model formatting slip must never let raw JSON leak into a
    customer-facing answer (see docs/chart-output-rules.md Part B,
    generalized: "answer must never contain raw JSON" is the hard
    requirement, the fence is just the model-facing convention for it).
    Matches don't overlap -- once an object is found, scanning resumes
    after it.
    """
    decoder = json.JSONDecoder()
    found: list[tuple[int, int, object]] = []
    pos = 0
    length = len(text)
    while pos < length:
        brace = text.find("{", pos)
        if brace == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, brace)
        except json.JSONDecodeError:
            pos = brace + 1
            continue
        found.append((brace, end, obj))
        pos = end
    return found


def extract_ui_block(text: str) -> tuple[str, dict | None]:
    """Pull any agent-emitted UI widget JSON out of an answer's text.

    This is the generic envelope for any agent-emitted UI widget (chart
    today; transfer_form/set_budget/etc. later -- see todo.md's "Roadmap
    PFM" section) -- every type shares one top-level `{"type": ..., ...}`
    shape, split out into the `ui` field instead of leaving raw JSON in the
    text a customer reads. The model's output is never trusted as-is
    (docs/chart-output-rules.md Part B, generalized to every type): a
    missing block, invalid JSON, an unknown `type`, or a payload that fails
    that type's validation all leave `ui` as None -- a model formatting
    mistake should never break /chat.

    Two passes, both fully independent of whether the model followed the
    ```ui-json convention correctly (a real production incident showed the
    model sometimes skips the fence entirely and just appends raw JSON --
    see docs/api.md's breaking-change note):

    1. Strip every fenced code block (any/no language label) outright, and
       try to parse+validate its content as JSON. This app has no
       legitimate use for code fences other than a ui-json block, so an
       *unparseable* fenced block still gets removed wholesale (the
       requirement is "answer never contains raw JSON", not "only valid
       JSON gets removed").
    2. On what's left, scan for bare (unfenced) JSON objects the model
       forgot to fence -- same removal rule.

    Every embedded JSON object found (fenced or not, valid or not) is
    stripped from the returned text -- only the first one that validates
    becomes `ui`.
    """
    ui: dict | None = None
    found_anything = False

    def _consume_fenced(match: re.Match) -> str:
        nonlocal ui, found_anything
        found_anything = True
        try:
            obj = json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("Dropping ui block: fenced content is not valid JSON: %r", match.group(1))
            return ""
        if ui is None:
            if _is_valid_ui(obj):
                ui = obj
            else:
                logger.warning("Dropping ui block: payload failed validation: %r", obj)
        return ""

    remaining = _FENCED_BLOCK_RE.sub(_consume_fenced, text)

    objects = _find_json_objects(remaining)
    if objects:
        found_anything = True
        pieces = []
        last_end = 0
        for start, end, obj in objects:
            pieces.append(remaining[last_end:start])
            last_end = end
            if ui is None and _is_valid_ui(obj):
                ui = obj
            elif ui is None:
                logger.warning("Dropping ui block: payload failed validation: %r", obj)
        pieces.append(remaining[last_end:])
        remaining = "".join(pieces)

    if not found_anything:
        return text, None

    # Best-effort cleanup of leftover ```-fence markers (e.g. an unclosed
    # fence) and the blank-line runs left behind where the JSON used to
    # be -- cosmetic, not required for correctness (the JSON itself is
    # already gone above).
    remaining = _FENCE_MARKER_RE.sub("", remaining)
    remaining = _BLANK_RUN_RE.sub("\n\n", remaining)

    return remaining.strip(), ui

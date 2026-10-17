import json
import logging
import math
import re

logger = logging.getLogger("personal-card-agent")

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_STRAY_THINK_TAG_RE = re.compile(r"</?think>")
_UI_BLOCK_RE = re.compile(r"```ui-json\s*\n(.*?)\n```", re.DOTALL)
_VALID_CHART_TYPES = {"bar", "line", "pie"}


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks some OpenAI-compatible
    endpoints (e.g. GLM served via GreenNode's MaaS) leave inline in the
    message content instead of a separate reasoning_content field -- along
    with any stray unmatched <think>/</think> tag left behind."""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _STRAY_THINK_TAG_RE.sub("", text)
    return text.strip()


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
    """
    recipient = raw.get("recipient")
    if not isinstance(recipient, str) or not recipient:
        return False

    account_number = raw.get("account_number")
    if not isinstance(account_number, str) or not account_number:
        return False

    amount = raw.get("amount")
    if not _is_finite_number(amount) or amount <= 0:
        return False

    # The bank transfer's actual content/message field ("nội dung chuyển
    # khoản") -- required, not just an internal explanation, since the
    # customer's real transfer needs this filled in.
    note = raw.get("note")
    if not isinstance(note, str) or not note:
        return False

    return True


# Dispatch table: ui block "type" -> validator. Add an entry here (and a new
# _is_valid_<type> function above) for each new widget type -- every type
# shares the same ```ui-json fence and the same envelope shape
# {"type": ..., ...type-specific fields}.
_UI_VALIDATORS = {
    "chart": _is_valid_chart,
    "transfer_form": _is_valid_transfer_form,
}


def _is_valid_ui(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    validator = _UI_VALIDATORS.get(raw.get("type"))
    return validator is not None and validator(raw)


def extract_ui_block(text: str) -> tuple[str, dict | None]:
    """Pull an optional ```ui-json fenced block out of an answer's text.

    This is the generic envelope for any agent-emitted UI widget (chart
    today; transfer_form/set_budget/etc. later -- see todo.md's "Roadmap
    PFM" section) -- every type shares one fence marker and one top-level
    `{"type": ..., ...}` shape, split out into the `ui` field instead of
    leaving raw JSON in the text a customer reads. The model's output is
    never trusted as-is (docs/chart-output-rules.md Part B, generalized to
    every type): a missing block, invalid JSON, an unknown `type`, or a
    payload that fails that type's validation all leave `ui` as None -- a
    model formatting mistake should never break /chat, and raw JSON must
    never leak into the text a customer reads regardless of whether it
    validated.
    """
    matches = list(_UI_BLOCK_RE.finditer(text))
    if not matches:
        return text, None

    remaining = _UI_BLOCK_RE.sub("", text).strip()

    raw_block = matches[0].group(1)
    try:
        raw = json.loads(raw_block)
    except json.JSONDecodeError:
        logger.warning("Dropping ui block: not valid JSON: %r", raw_block)
        return remaining, None

    if not _is_valid_ui(raw):
        logger.warning("Dropping ui block: payload failed validation: %r", raw)
        return remaining, None

    return remaining, raw

import json
import logging
import math
import re

logger = logging.getLogger("personal-card-agent")

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_STRAY_THINK_TAG_RE = re.compile(r"</?think>")
_CHART_BLOCK_RE = re.compile(r"```chart-json\s*\n(.*?)\n```", re.DOTALL)
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


def _is_valid_chart(raw: object) -> bool:
    """Validate a parsed chart-json payload per docs/chart-output-rules.md
    Part B. Pure validation only -- no normalizing/auto-fixing a payload
    that doesn't pass (e.g. trimming an over-long `series` for `pie`): the
    correct format is the model's responsibility (see the prompt in
    skills/project/data-visualization/SKILL.md); anything that fails here
    means the whole chart is dropped (`chart: None`), not patched up.
    """
    if not isinstance(raw, dict):
        return False

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


def extract_chart_block(text: str) -> tuple[str, dict | None]:
    """Pull an optional ```chart-json fenced block out of an answer's text.

    The data-visualization skill (skills/project/data-visualization/SKILL.md)
    instructs the model to append this block when a chart is warranted --
    this splits it out into a separate `chart` field instead of leaving raw
    JSON in the text a customer reads. The model's output is never trusted
    as-is (docs/chart-output-rules.md Part B): a missing block, invalid
    JSON, or a payload that fails validation all leave `chart` as None --
    a model formatting mistake should never break /chat, and raw JSON must
    never leak into the text a customer reads regardless of whether it
    validated.
    """
    matches = list(_CHART_BLOCK_RE.finditer(text))
    if not matches:
        return text, None

    remaining = _CHART_BLOCK_RE.sub("", text).strip()

    raw_block = matches[0].group(1)
    try:
        raw = json.loads(raw_block)
    except json.JSONDecodeError:
        logger.warning("Dropping chart: chart-json block is not valid JSON: %r", raw_block)
        return remaining, None

    if not _is_valid_chart(raw):
        logger.warning("Dropping chart: chart-json payload failed validation: %r", raw)
        return remaining, None

    return remaining, raw

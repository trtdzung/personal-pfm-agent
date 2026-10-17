import re

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_STRAY_THINK_TAG_RE = re.compile(r"</?think>")


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

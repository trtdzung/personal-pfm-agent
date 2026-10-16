def extract_final_text(content: object) -> str:
    """Pull just the final answer text out of a message's content.

    Reasoning-capable models (e.g. gpt-5.5) return content as a list of
    blocks (reasoning + text) instead of a plain string -- this returns
    only the text block(s), not the raw list with reasoning/ids/etc.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if texts:
            return "\n".join(texts)
    return str(content)

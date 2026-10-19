"""Reuse the established secret masker before text reaches a model."""
from guardrails import mask_sensitive_input


def redact_text(text: str) -> str:
    return mask_sensitive_input(text)[0]


def redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items() if key not in {"attachments", "base64"}}
    return value

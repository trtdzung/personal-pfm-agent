"""LLM-based slot extraction (NLU only). Output is schema-bound; code verifies it later."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .contracts import GoalExtraction

logger = logging.getLogger("goal_coach.nlu")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_v1.md"
_MAX_ATTEMPTS = 2  # first try + one retry with the error described


class ModelUnavailableError(RuntimeError):
    """The model failed or timed out after all attempts."""


def _wrap(text: str) -> str:
    return f"<du_lieu_khach_hang>\n{text}\n</du_lieu_khach_hang>"


def extract(text: str) -> GoalExtraction:
    """Extract slots from one customer utterance. Raises ModelUnavailableError."""
    # Imported here: `llm` needs langchain_openai, which not every env has.
    from llm import default_model

    system = _PROMPT_PATH.read_text(encoding="utf-8")
    try:
        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=20, max_retries=0)
        try:
            structured = model.with_structured_output(GoalExtraction, method="function_calling")
        except TypeError:
            structured = model.with_structured_output(GoalExtraction)
    except Exception as exc:  # config / construction failure
        logger.error("nlu model setup failed: %s", type(exc).__name__)
        raise ModelUnavailableError("model setup failed") from exc

    messages: list[tuple[str, str]] = [("system", system), ("human", _wrap(text))]
    last_error = "unknown"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = structured.invoke(messages)
            if raw is None:
                raise ValueError("model returned no structured output")
            result = raw if isinstance(raw, GoalExtraction) else GoalExtraction.model_validate(raw)
            logger.info("nlu ok attempts=%d", attempt)
            return result
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            logger.warning("nlu attempt %d failed: %s", attempt, type(exc).__name__)
            messages = [
                ("system", system),
                ("human", _wrap(text)),
                ("human", f"Lần trước đầu ra không đúng khuôn ({last_error}). Hãy trả lại đúng khuôn."),
            ]
    logger.error("nlu failed after %d attempts", _MAX_ATTEMPTS)
    raise ModelUnavailableError(last_error)

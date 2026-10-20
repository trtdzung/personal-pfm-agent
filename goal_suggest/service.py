"""Reads the customer's data, lets the model (gemma) write ONE insight for ONE goal, and shows it only if `guard` agrees."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import data, digest, guard
from .contracts import GoalSuggestionRequest, GoalSuggestionResponse, Insight

logger = logging.getLogger("goal_suggest.service")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
# Own model for this feature (the rest of the agent keeps LLM_MODEL). Override with GOAL_SUGGEST_MODEL.
DEFAULT_MODEL = "google/gemma-4-31b-it"
MODEL_TIMEOUT_SECONDS = 45.0
MAX_ATTEMPTS = 2  # first try + one retry that says why the first was rejected


class LLMOut(BaseModel):
    observation: str
    suggestion: str
    question: str


Generator = Callable[[list[tuple[str, str]]], Any]
Collector = Callable[[str], dict]


def _unwrap(raw: Any) -> Any:
    """`include_raw=True` result: the parsed object, else the raw tool-call arguments. Raises when neither exists."""
    if isinstance(raw, dict) and "parsed" in raw and "raw" in raw:
        if raw.get("parsed") is not None:
            return raw["parsed"]
        message = raw.get("raw")
        for call in getattr(message, "tool_calls", None) or []:
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
            if isinstance(args, dict):
                return args
        # gemma sometimes answers in plain text: the object, maybe inside a ```json fence.
        found = _json_in(getattr(message, "content", None))
        if found is not None:
            return found
        raise ValueError(f"no structured output: {raw.get('parsing_error')!r}")
    return raw


def _json_in(content: Any) -> dict | None:
    """The first JSON object in a text answer (a ```json fence, or bare), else None."""
    if not isinstance(content, str):
        return None
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(content[start : end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def generate_with_llm(messages: list[tuple[str, str]]) -> Any:
    from llm import default_model  # lazy: needs langchain_openai

    model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=MODEL_TIMEOUT_SECONDS, max_retries=0)
    model = model.model_copy(update={"model_name": os.environ.get("GOAL_SUGGEST_MODEL") or DEFAULT_MODEL})
    try:
        structured = model.with_structured_output(LLMOut, method="function_calling", include_raw=True)
    except TypeError:
        structured = model.with_structured_output(LLMOut, include_raw=True)
    return _unwrap(structured.invoke(messages))


def _wrap(text: str) -> str:
    return f"<du_lieu_khach_hang>\n{text}\n</du_lieu_khach_hang>"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _build_messages(system: str, text: str, rejected: str | None) -> list[tuple[str, str]]:
    messages = [("system", system), ("human", _wrap(text))]
    if rejected:
        messages.append(
            (
                "human",
                f"Lần trước bị từ chối vì: {rejected}. Viết lại ngắn hơn: chỉ dùng số có trong dữ liệu, ô trên tối đa "
                f"{guard.MAX_OBSERVATION_LEN} ký tự, ô gợi ý tối đa {guard.MAX_SUGGESTION_LEN} ký tự, câu hỏi tối đa {guard.MAX_QUESTION_LEN} ký tự và kết thúc bằng dấu ?, không định dạng, "
                "không dùng các từ chắc chắn / đảm bảo / cam kết.",
            )
        )
    return messages


def _generate_sync(generate: Generator, text: str) -> tuple[LLMOut | None, str | None]:
    """Up to MAX_ATTEMPTS model calls; the first wording `guard` accepts wins. (insight, None) or (None, reason)."""
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    rejected: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = generate(_build_messages(system, text, rejected))
            out = raw if isinstance(raw, LLMOut) else LLMOut.model_validate(raw)
        except Exception as exc:  # timeout, schema, network, missing key...
            rejected = f"đầu ra không đúng khuôn ({type(exc).__name__})"
            logger.warning("goal_suggest attempt %d failed: %s", attempt, type(exc).__name__)
            continue
        observation, suggestion, question = _clean(out.observation), _clean(out.suggestion), _clean(out.question)
        reason = guard.check(observation, suggestion, question, data_text=text)
        if reason is None:
            return out.model_copy(update={"observation": observation, "suggestion": suggestion, "question": question}), None
        logger.warning("goal_suggest attempt %d rejected: %s", attempt, reason)
        rejected = reason
    return None, rejected or "model_failed"


async def suggest(
    req: GoalSuggestionRequest,
    *,
    generate: Generator | None = None,
    collect: Collector | None = None,
    timeout: float = MODEL_TIMEOUT_SECONDS * MAX_ATTEMPTS + 15,
) -> GoalSuggestionResponse:
    """Raises `data.DataUnavailable` (pfm unreadable), `digest.GoalNotFound` / `digest.GoalAmbiguous`. Model trouble is
    never an error: it comes back as `insight: null` with the reason."""
    raw = await asyncio.to_thread(collect or data.collect, req.user_id)
    goal, text, fingerprint = digest.build_full(raw, req.goal_id, req.goal_name)
    if req.previous_fingerprint and req.previous_fingerprint == fingerprint:
        return GoalSuggestionResponse(insight=None, fingerprint=fingerprint, unchanged=True)
    try:
        out, reason = await asyncio.wait_for(asyncio.to_thread(_generate_sync, generate or generate_with_llm, text), timeout)
    except asyncio.TimeoutError:
        return GoalSuggestionResponse(insight=None, reason="timeout", degraded=True, fingerprint=fingerprint)
    if out is None:
        return GoalSuggestionResponse(insight=None, reason=reason, degraded=True, fingerprint=fingerprint)
    insight = Insight(
        goal_id=goal["id"],
        goal_name=goal["name"],
        observation=out.observation,
        suggestion=out.suggestion,
        question=out.question,
    )
    return GoalSuggestionResponse(insight=insight, fingerprint=fingerprint)

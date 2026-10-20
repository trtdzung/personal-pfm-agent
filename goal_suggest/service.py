"""LLM words the cards, `guard` decides whether each may be shown; anything wrong falls back to pfm's own wording."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import guard
from .contracts import GoalSuggestionsRequest, GoalSuggestionsResponse, Signal, SuggestionOut

logger = logging.getLogger("goal_suggest.service")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
TIMEOUT_SECONDS = 20.0


class _LLMCard(BaseModel):
    signal_id: str
    title: str
    body: str
    action_ids: list[str] = []


class _LLMOut(BaseModel):
    suggestions: list[_LLMCard]


Generator = Callable[[GoalSuggestionsRequest, list[Signal]], list[_LLMCard]]


def ordered_signals(req: GoalSuggestionsRequest) -> list[Signal]:
    return sorted(req.signals, key=lambda s: s.rank)  # stable: equal ranks keep pfm's order


def _unwrap(raw: Any) -> Any:
    """`include_raw=True` result: the parsed object, else the raw tool-call arguments. Raises when neither exists."""
    if isinstance(raw, dict) and "parsed" in raw and "raw" in raw:
        if raw.get("parsed") is not None:
            return raw["parsed"]
        for call in getattr(raw.get("raw"), "tool_calls", None) or []:
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
            if isinstance(args, dict):
                return args
        raise ValueError(f"no structured output: {raw.get('parsing_error')!r}")
    return raw


def generate_with_llm(req: GoalSuggestionsRequest, signals: list[Signal]) -> list[_LLMCard]:
    """One model call for every card. Raises on any failure (caller falls back)."""
    from llm import default_model  # lazy: needs langchain_openai

    model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=TIMEOUT_SECONDS, max_retries=0)
    try:
        structured = model.with_structured_output(_LLMOut, method="function_calling", include_raw=True)
    except TypeError:
        structured = model.with_structured_output(_LLMOut, include_raw=True)
    data = {
        "today": req.today,
        "customer": req.customer.model_dump(),
        "goals": [g.model_dump() for g in req.goals],
        "signals": [s.model_dump() for s in signals],
        "feedback": [f.model_dump() for f in req.feedback],
    }
    human = "<du_lieu>\n" + json.dumps(data, ensure_ascii=False) + "\n</du_lieu>"
    parsed = _unwrap(structured.invoke([("system", _PROMPT_PATH.read_text(encoding="utf-8")), ("human", human)]))
    out = parsed if isinstance(parsed, _LLMOut) else _LLMOut.model_validate(parsed)
    return out.suggestions


def _fallback(signal: Signal) -> SuggestionOut:
    return SuggestionOut(
        signal_id=signal.id,
        title=signal.fallback.title,
        body=signal.fallback.body,
        action_ids=[a.id for a in signal.allowed_actions],
    )


def assemble(signals: list[Signal], cards: list[_LLMCard] | None) -> GoalSuggestionsResponse:
    """Exactly one card per signal, in `signals` order. `cards=None` = the model failed: all fallbacks, degraded."""
    if cards is None:
        return GoalSuggestionsResponse(suggestions=[_fallback(s) for s in signals], degraded=True)
    by_id: dict[str, _LLMCard] = {}
    for card in cards:
        by_id.setdefault(card.signal_id, card)
    out: list[SuggestionOut] = []
    for signal in signals:
        card = by_id.get(signal.id)
        if card is None:
            logger.warning("goal_suggest signal=%s kind=%s: no card from model", signal.id, signal.kind)
            out.append(_fallback(signal))
            continue
        title, body = card.title.strip(), card.body.strip()
        action_ids = list(dict.fromkeys(card.action_ids))
        reason = guard.check(
            title, body, action_ids, facts=signal.facts, allowed_action_ids=[a.id for a in signal.allowed_actions]
        )
        if reason:
            logger.warning("goal_suggest signal=%s kind=%s rejected: %s", signal.id, signal.kind, reason)
            out.append(_fallback(signal))
            continue
        out.append(SuggestionOut(signal_id=signal.id, title=title, body=body, action_ids=action_ids))
    return GoalSuggestionsResponse(suggestions=out, degraded=False)


async def suggest(
    req: GoalSuggestionsRequest, *, generate: Generator | None = None, timeout: float = TIMEOUT_SECONDS
) -> GoalSuggestionsResponse:
    """Never raises for model trouble: error or timeout -> every signal's fallback with `degraded: true`."""
    signals = ordered_signals(req)
    if not signals:
        return GoalSuggestionsResponse(suggestions=[])
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(generate or generate_with_llm, req, signals), timeout)
        cards = [c if isinstance(c, _LLMCard) else _LLMCard.model_validate(c) for c in raw]
    except Exception as exc:  # timeout, schema, network, missing key...
        logger.warning("goal_suggest model failed: %s", type(exc).__name__)
        cards = None
    return assemble(signals, cards)

"""LLM-based slot extraction (NLU only). Output is schema-bound; code verifies it later."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from .contracts import GoalExtraction
from .fast_path import find_flexibility
from .parsing import parse_amount, parse_horizon

logger = logging.getLogger("goal_coach.nlu")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_v1.md"
_MAX_ATTEMPTS = 2  # first try + one retry with the error described
# Time budget for the whole extraction (all attempts). A retry only starts if enough is left.
BUDGET_SECONDS = 8.0
_MIN_RETRY_SECONDS = 2.5
# Own model for this feature (the rest of the agent keeps LLM_MODEL). Override with GOAL_COACH_MODEL.
DEFAULT_MODEL = "google/gemma-4-31b-it"

_NULLISH = {"", "null", "none", "nil", "n/a", "undefined", "{}", "[]"}


class ModelUnavailableError(RuntimeError):
    """The model failed or timed out after all attempts."""


def _wrap(text: str) -> str:
    return f"<du_lieu_khach_hang>\n{text}\n</du_lieu_khach_hang>"


# ---------------------------------------------------------------- tolerant coercion


def _null(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH) or v == {} or v == []


def _to_int(v: Any) -> int | None:
    """int from 600000000 / 6e8 / '600000000' / '600.000.000' / '600 triệu'."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(round(v)) if v == v else None
    if not isinstance(v, str):
        return None
    s = v.strip().replace(" ", "")
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        return int(re.sub(r"[.,]", "", s))
    if re.fullmatch(r"\d+\.0+", s):
        return int(s.split(".")[0])
    return parse_amount(v)


def _bool(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in {"true", "yes", "có", "1"}
    return bool(v)


def _coerce_amount(v: Any) -> dict[str, Any] | None:
    if _null(v):
        return None
    if isinstance(v, dict):
        raw = next((v[k] for k in ("value_vnd", "value", "amount") if not _null(v.get(k))), None)
        value = _to_int(raw)
        evidence = v.get("evidence")
        if value is None:
            return None
        return {"value_vnd": value, "evidence": "" if _null(evidence) else str(evidence)}
    value = _to_int(v)
    if value is None:
        return None
    return {"value_vnd": value, "evidence": v if isinstance(v, str) else ""}


def _coerce_horizon(v: Any) -> dict[str, Any] | None:
    if _null(v):
        return None
    if isinstance(v, str):
        parsed = parse_horizon(v)
        return {
            "months": parsed.get("months") if parsed else None,
            "target_month": parsed.get("target_month") if parsed else None,
            "evidence": v,
        }
    if not isinstance(v, dict):
        return None
    months = v.get("months")
    if isinstance(months, str):
        months = _to_int(months)
    elif isinstance(months, float):
        months = int(months)
    elif _null(months) or isinstance(months, bool):
        months = None
    tm = v.get("target_month")
    tm = None if _null(tm) else str(tm).strip()
    evidence = v.get("evidence")
    return {"months": months, "target_month": tm, "evidence": "" if _null(evidence) else str(evidence)}


def _coerce_flex(v: Any, text: str) -> dict[str, Any] | None:
    if _null(v):
        return None
    evidence = ""
    if isinstance(v, dict):
        evidence = "" if _null(v.get("evidence")) else str(v["evidence"])
        v = v.get("value")
    if not isinstance(v, str):
        return None
    word = v.strip().lower()
    if word in {"flexible", "linh hoạt", "có thể lùi"}:
        value = "flexible"
    elif word in {"fixed", "cố định", "đúng hạn", "phải đúng hạn"}:
        value = "fixed"
    else:
        return None
    if not evidence:  # a bare string carries no quote: recover it from the sentence
        found = find_flexibility(text)
        if found and found[0] == value:
            evidence = found[1]
    return {"value": value, "evidence": evidence}


def coerce_extraction(data: Any, text: str) -> GoalExtraction:
    """Repair the usual small-model slips, then validate. Raises on anything still invalid."""
    if isinstance(data, GoalExtraction):
        return data
    if not isinstance(data, dict):
        raise ValueError("model output is not an object")
    out: dict[str, Any] = {"is_savings_goal": _bool(data.get("is_savings_goal"))}
    name = data.get("name")
    if not _null(name):
        if isinstance(name, dict):
            value = name.get("value")
            evidence = name.get("evidence")
            if not _null(value):
                out["name"] = {"value": str(value), "evidence": "" if _null(evidence) else str(evidence)}
        elif isinstance(name, str):
            out["name"] = {"value": name, "evidence": name}
    for key in ("target_amount", "opening_amount"):
        item = _coerce_amount(data.get(key))
        if item:
            out[key] = item
    horizon = _coerce_horizon(data.get("horizon"))
    if horizon:
        out["horizon"] = horizon
    flex = _coerce_flex(data.get("flexibility"), text)
    if flex:
        out["flexibility"] = flex
    return GoalExtraction.model_validate(out)


def _unwrap(raw: Any) -> tuple[Any, str | None]:
    """Handle `include_raw=True` results: prefer parsed, else the raw tool-call arguments."""
    if isinstance(raw, dict) and "parsed" in raw and "raw" in raw:
        if raw.get("parsed") is not None:
            return raw["parsed"], None
        msg = raw.get("raw")
        for call in getattr(msg, "tool_calls", None) or []:
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
            if isinstance(args, dict):
                return args, None
        err = raw.get("parsing_error")
        return None, f"{type(err).__name__}: {err}" if err else "no structured output"
    return raw, None


# ---------------------------------------------------------------- model call


def _structured(timeout: float):  # type: ignore[no-untyped-def]
    # Imported here: `llm` needs langchain_openai, which not every env has.
    from llm import default_model

    model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=timeout, max_retries=0)
    # Same client config as the platform default, only the model name differs.
    model = model.model_copy(update={"model_name": os.environ.get("GOAL_COACH_MODEL") or DEFAULT_MODEL})
    try:
        return model.with_structured_output(GoalExtraction, method="function_calling", include_raw=True)
    except TypeError:
        return model.with_structured_output(GoalExtraction, include_raw=True)


def extract(text: str) -> GoalExtraction:
    """Extract slots from one customer utterance. Raises ModelUnavailableError."""
    started = time.monotonic()
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    messages: list[tuple[str, str]] = [("system", system), ("human", _wrap(text))]
    last_error = "unknown"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        remaining = BUDGET_SECONDS - (time.monotonic() - started)
        if attempt > 1 and remaining < _MIN_RETRY_SECONDS:
            logger.warning("nlu retry skipped: %.1fs left", remaining)
            break
        try:
            structured = _structured(max(1.0, remaining))
            data, err = _unwrap(structured.invoke(messages))
            if err:
                raise ValueError(err)
            result = coerce_extraction(data, text)
            logger.info("nlu ok attempts=%d ms=%d", attempt, int((time.monotonic() - started) * 1000))
            return result
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            logger.warning("nlu attempt %d failed: %s", attempt, type(exc).__name__)
            messages = [
                ("system", system),
                ("human", _wrap(text)),
                ("human", f"Lần trước đầu ra không đúng khuôn ({last_error}). Hãy trả lại đúng khuôn."),
            ]
    logger.error("nlu failed (%s)", last_error[:80])
    raise ModelUnavailableError(last_error)

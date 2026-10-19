"""Per-turn trace: one JSON record per request, keyed by the conversation it belongs to.

Modes (env GOAL_COACH_TRACE):
  basic (default) -- what happened (path, slot origins, codes, timings), no customer text, no model output.
  full            -- also the customer's words, raw model output and rejected sentences. Dev/eval only.
  off             -- nothing.
The record goes to the `goal_coach.trace` logger; GOAL_COACH_TRACE_FILE also appends it to a JSONL file.

Code records facts with `note()` / `add()` while the request runs; both are no-ops when no trace is active.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("goal_coach.trace")
_current: ContextVar["Trace | None"] = ContextVar("goal_coach_trace", default=None)
_file_lock = threading.Lock()


def mode() -> str:
    m = os.environ.get("GOAL_COACH_TRACE", "basic").lower()
    return m if m in ("basic", "full", "off") else "basic"


def full() -> bool:
    """True when customer text and model output may be recorded."""
    return mode() == "full"


class Trace:
    def __init__(self, kind: str, request_id: str, conversation_id: str | None, user_id: str | None) -> None:
        self.started = time.monotonic()
        self.data: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": kind,
            "conversation_id": conversation_id,
            "request_id": request_id,
            "user_id": user_id,
        }

    def emit(self) -> None:
        self.data["latency_ms"] = int((time.monotonic() - self.started) * 1000)
        line = json.dumps(self.data, ensure_ascii=False, default=str)
        logger.info(line)
        path = os.environ.get("GOAL_COACH_TRACE_FILE")
        if path:
            try:
                with _file_lock, open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError as exc:
                logger.warning("trace file write failed: %s", type(exc).__name__)


@contextmanager
def start(kind: str, request_id: str, conversation_id: str | None, user_id: str | None) -> Iterator[Trace | None]:
    """Collect one request's trace; emitted on exit, also when the request fails."""
    if mode() == "off":
        yield None
        return
    t = Trace(kind, request_id, conversation_id, user_id)
    token = _current.set(t)
    try:
        yield t
    except BaseException as exc:
        t.data["error"] = type(exc).__name__
        raise
    finally:
        _current.reset(token)
        t.emit()


def note(**fields: Any) -> None:
    t = _current.get()
    if t is not None:
        t.data.update(fields)


def add(key: str, item: Any) -> None:
    """Append to a list field (e.g. one entry per model call)."""
    t = _current.get()
    if t is not None:
        t.data.setdefault(key, []).append(item)


def text(value: str | None) -> str | None:
    """The value in full mode, else None (customer words / model output stay out of basic traces)."""
    return value if full() else None

"""Request-local tool trace: names, timings and status only, no customer values."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from typing import Iterator
from .contracts import TraceEntry

_current: ContextVar[list[TraceEntry] | None] = ContextVar("fraud_trace", default=None)


@contextmanager
def start() -> Iterator[list[TraceEntry]]:
    entries: list[TraceEntry] = []
    token = _current.set(entries)
    try:
        yield entries
    finally:
        _current.reset(token)


@contextmanager
def tool(name: str) -> Iterator[dict[str, str]]:
    started = monotonic()
    status = {"result": "ok"}
    try:
        yield status
    except Exception:
        status["result"] = "error"
        raise
    finally:
        entries = _current.get()
        if entries is not None and len(entries) < 30:
            entries.append(TraceEntry(tool=name, elapsed_ms=max(0, int((monotonic()-started)*1000)), result=status["result"]))

"""Request-scoped cache wrapper for AgentBaseMemoryEvents' underlying event fetch.

Root cause this works around (see todo.md's performance investigation, and
docs/incidents/2026-09-13-greennode-memory-checkpointer-perf.md for the
full writeup): LangGraph's `get_state()`/`invoke()` walk the checkpoint
history one `checkpointer.get_tuple()` call at a time (the `messages`
channel uses a reducer, so no single checkpoint carries the full
materialized list -- LangGraph has to combine writes across the checkpoint
chain). That's expected LangGraph behavior, and LangGraph treats
`get_tuple()` as a cheap, indexed lookup safe to call many times per
request. The actual bug is that `AgentBaseMemoryEvents.get_tuple()`
re-fetches AND re-deserializes *all* accumulated events from GreenNode
Memory over the network on every single one of those calls, instead of
reusing what it already fetched moments earlier in the same logical
operation -- on a thread with ~110 checkpoints/~460 events this measured
as 111 network round-trips (~0.55-1.0s each) for a single `/chat` request,
~65s total, even though a single fetch-all-events call only takes ~1s.

## Why request-scoped, not time-based (TTL)

An earlier version of this wrapper used a flat 2-second TTL. That works
but is a guess: too short and it can't tell whether "2 seconds passed"
means "still the same request" or "a new one slipped in"; too long and it
risks serving stale data across genuinely separate requests. The fix here
is deterministic instead of time-based: `invalidate(checkpointer,
session_id, actor_id)` is called explicitly by every request handler in
server.py right before it reads or writes that thread (`POST /chat`,
`GET /chat/history`, `DELETE /chat/history`), guaranteeing the *first*
fetch in that request is always genuinely fresh. Every other
`get_tuple()` call LangGraph makes for the rest of that same request then
hits the cache -- correct, because nothing else in this single-threaded
Python call can mutate the thread's events mid-request (this request's own
writes happen via `put()`, which does not touch this cache, only after all
the reads that use it). No guessing about "how many seconds is one
request" required.

A generous fallback TTL (`DEFAULT_FALLBACK_TTL_SECONDS`) still guards any
call site that forgets to invalidate -- it bounds worst-case staleness,
but `invalidate()` at the start of every real request is the actual
correctness mechanism, not this TTL.

This is a workaround for a third-party package's (`greennode-agent-bridge`)
inefficiency, not a fix to it -- report upstream if a real fix ships
there, and revert this patch then.
"""

import time
from typing import Any, Callable

DEFAULT_FALLBACK_TTL_SECONDS = 60.0

_CACHE_ATTR = "_checkpointer_events_cache"


class _CheckpointEventsCache:
    """Callable replacement for `checkpoint_event_client.get_events` that
    caches by (session_id, actor_id, limit, max_results) until explicitly
    invalidated (or the fallback TTL lapses, for callers that never
    invalidate)."""

    def __init__(self, original_get_events: Callable, fallback_ttl_seconds: float):
        self._original_get_events = original_get_events
        self._fallback_ttl_seconds = fallback_ttl_seconds
        self._entries: dict[tuple, tuple[float, Any]] = {}

    def __call__(self, session_id, actor_id, limit=100, max_results=100):
        key = (session_id, actor_id, limit, max_results)
        now = time.monotonic()
        cached = self._entries.get(key)
        if cached is not None and now - cached[0] < self._fallback_ttl_seconds:
            return cached[1]
        result = self._original_get_events(session_id, actor_id, limit, max_results)
        self._entries[key] = (now, result)
        return result

    def invalidate(self, session_id: str, actor_id: str) -> None:
        stale_keys = [k for k in self._entries if k[0] == session_id and k[1] == actor_id]
        for key in stale_keys:
            del self._entries[key]


def patch_get_events_with_cache(
    checkpointer: Any, fallback_ttl_seconds: float = DEFAULT_FALLBACK_TTL_SECONDS
) -> None:
    """Wrap `checkpointer.checkpoint_event_client.get_events` with the
    request-scoped cache described above, in place. No-op if `checkpointer`
    doesn't look like `AgentBaseMemoryEvents` (e.g. `InMemorySaver` in
    tests/notebooks) -- safe to call unconditionally on any checkpointer.
    """
    client = getattr(checkpointer, "checkpoint_event_client", None)
    if client is None:
        return

    cache = _CheckpointEventsCache(client.get_events, fallback_ttl_seconds)
    client.get_events = cache
    setattr(checkpointer, _CACHE_ATTR, cache)


def invalidate(checkpointer: Any, session_id: str, actor_id: str) -> None:
    """Drop any cached fetch for this specific thread, so the very next
    read is guaranteed to hit the network instead of a stale cache entry.

    Call this at the start of handling any request that reads or writes
    the given thread's history (before `agent.invoke()`, `agent.get_state()`,
    or `checkpointer.delete_thread()`). No-op if `checkpointer` was never
    patched (e.g. `InMemorySaver`) -- safe to call unconditionally.
    """
    cache = getattr(checkpointer, _CACHE_ATTR, None)
    if cache is not None:
        cache.invalidate(session_id, actor_id)

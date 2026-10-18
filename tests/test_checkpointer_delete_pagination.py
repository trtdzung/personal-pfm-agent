"""Regression tests for checkpointer_delete_pagination.py.

Guards the bug found while testing `DELETE /chat/history` against real
GreenNode AgentBase Memory: a thread with more than one page (100) of
events came back with 2 messages still present after "successful"
deletion. Root cause and full mechanism: checkpointer_delete_pagination.py.

No network anywhere here -- `_FakeMemoryClient` mirrors the real service's
offset-based pagination closely enough to reproduce it: deleting an item
shifts everything after it back by one.
"""

import threading
import time
from types import SimpleNamespace
from typing import Any

from greennode_agent_bridge.langgraph.memory.helpers import AgentBaseEventClient, EventSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from checkpointer_delete_pagination import patch_delete_events_reads_page_one_every_time


class _FakeMemoryClient:
    """In-memory stand-in for `greennode_agentbase.memory.MemoryClient`. Unlike the
    minimal fakes in the other checkpointer_* tests, `list_events` here mimics real
    offset-based pagination precisely: it slices the CURRENT (post-deletion) list, so
    deleting page 1 genuinely shifts what used to be on page 2 back onto page 1 --
    exactly the behavior the real service exhibited."""

    def __init__(self):
        self.events: dict[tuple[str, str], list[Any]] = {}
        self._counter = 0
        self._lock = threading.Lock()  # deletes may run concurrently once patched

    def create_event(self, *, id, actorId, sessionId, request):
        with self._lock:
            self._counter += 1
            self.events.setdefault((sessionId, actorId), []).append(
                SimpleNamespace(id=f"event-{self._counter}", payload=request.payload)
            )

    def list_events(self, *, id, actorId, sessionId, page, size):
        with self._lock:
            items = list(self.events.get((sessionId, actorId), []))
        start = (page - 1) * size
        return SimpleNamespace(
            list_data=items[start : start + size],
            total_page=max(1, (len(items) + size - 1) // size),
        )

    def delete_event(self, *, id, actorId, sessionId, eventId):
        with self._lock:
            for key, items in self.events.items():
                self.events[key] = [e for e in items if e.id != eventId]


def _client_with_events(n: int) -> tuple[_FakeMemoryClient, AgentBaseEventClient]:
    memory_client = _FakeMemoryClient()
    for i in range(n):
        memory_client.create_event(
            id="mem-1",
            actorId="CIF_0001",
            sessionId="t1",
            request=SimpleNamespace(payload=SimpleNamespace(type="other", binary_data=None)),
        )
    event_client = AgentBaseEventClient(
        "mem-1", EventSerializer(JsonPlusSerializer()), memory_client=memory_client
    )
    return memory_client, event_client


def test_the_original_pagination_leaves_events_behind_past_one_page():
    """The exact, unmodified logic from `AgentBaseEventClient.delete_events()`
    (see checkpointer_delete_pagination.py's docstring for the annotated original),
    kept independent of the live (module-patched) class method so this reproduces the
    bug regardless of whether some other test already applied the fix (it is applied
    process-wide and persists for the rest of the session, same as this repo's other
    checkpointer_*.py patches)."""
    from greennode_agent_bridge.langgraph.memory.helpers import retry_with_backoff

    def original_buggy_delete_events(self, session_id, actor_id):
        page = 1
        size = 100
        while True:
            response = retry_with_backoff(
                lambda: self.memory_client.list_events(
                    id=self.memory_id, actorId=actor_id, sessionId=session_id, page=page, size=size
                )
            )
            events_list = response.list_data or []
            if not events_list:
                break
            for event in events_list:
                if event.id:
                    self.memory_client.delete_event(
                        id=self.memory_id, actorId=actor_id, sessionId=session_id, eventId=event.id
                    )
            if page >= (response.total_page or 1):
                break
            page += 1

    memory_client, event_client = _client_with_events(250)  # 3 pages of 100
    original_buggy_delete_events(event_client, "t1", "CIF_0001")

    assert memory_client.events[("t1", "CIF_0001")] != []  # the bug: something survives


def test_the_patch_deletes_every_event_across_many_pages():
    patch_delete_events_reads_page_one_every_time()
    memory_client, event_client = _client_with_events(250)  # 3 pages of 100

    event_client.delete_events("t1", "CIF_0001")

    assert memory_client.events[("t1", "CIF_0001")] == []


def test_the_patch_handles_an_empty_thread():
    patch_delete_events_reads_page_one_every_time()
    memory_client, event_client = _client_with_events(0)

    event_client.delete_events("t1", "CIF_0001")  # must not raise

    assert memory_client.events.get(("t1", "CIF_0001"), []) == []


def test_the_patch_handles_exactly_one_page():
    patch_delete_events_reads_page_one_every_time()
    memory_client, event_client = _client_with_events(37)

    event_client.delete_events("t1", "CIF_0001")

    assert memory_client.events[("t1", "CIF_0001")] == []


def test_the_patch_is_idempotent():
    patch_delete_events_reads_page_one_every_time()
    once = AgentBaseEventClient.delete_events
    patch_delete_events_reads_page_one_every_time()
    assert AgentBaseEventClient.delete_events is once


class _ConcurrencyTrackingFakeMemoryClient(_FakeMemoryClient):
    """Like `_FakeMemoryClient`, but `delete_event` holds the (thread-safe)
    lock briefly and records how many calls were in flight AT ONCE, so a
    test can prove deletes actually overlap instead of only checking the
    end result (which a sequential loop would also produce correctly)."""

    def __init__(self, hold_seconds: float = 0.02):
        super().__init__()
        self._hold_seconds = hold_seconds
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def delete_event(self, *, id, actorId, sessionId, eventId):
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        time.sleep(self._hold_seconds)
        super().delete_event(id=id, actorId=actorId, sessionId=sessionId, eventId=eventId)
        with self._lock:
            self._in_flight -= 1


def test_the_patch_deletes_events_within_a_page_concurrently_not_one_at_a_time():
    patch_delete_events_reads_page_one_every_time()
    memory_client = _ConcurrencyTrackingFakeMemoryClient(hold_seconds=0.02)
    for i in range(20):
        memory_client.create_event(
            id="mem-1", actorId="CIF_0001", sessionId="t1",
            request=SimpleNamespace(payload=SimpleNamespace(type="other", binary_data=None)),
        )
    event_client = AgentBaseEventClient(
        "mem-1", EventSerializer(JsonPlusSerializer()), memory_client=memory_client
    )

    t0 = time.time()
    event_client.delete_events("t1", "CIF_0001")
    elapsed = time.time() - t0

    assert memory_client.events[("t1", "CIF_0001")] == []
    assert memory_client.max_in_flight > 1, "deletes ran one at a time -- no speed-up"
    assert elapsed < 20 * 0.02, "took as long as fully sequential deletes would"


def test_the_patch_respects_a_configured_concurrency_limit():
    patch_delete_events_reads_page_one_every_time(max_workers=3)
    memory_client = _ConcurrencyTrackingFakeMemoryClient(hold_seconds=0.02)
    for i in range(20):
        memory_client.create_event(
            id="mem-1", actorId="CIF_0001", sessionId="t1",
            request=SimpleNamespace(payload=SimpleNamespace(type="other", binary_data=None)),
        )
    event_client = AgentBaseEventClient(
        "mem-1", EventSerializer(JsonPlusSerializer()), memory_client=memory_client
    )

    event_client.delete_events("t1", "CIF_0001")

    assert memory_client.events[("t1", "CIF_0001")] == []
    assert memory_client.max_in_flight <= 3

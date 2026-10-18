"""Regression tests for checkpointer_local_cache_race.py.

Guards a real, reproducible race found by soaking `AgentBaseMemoryEvents`
against real GreenNode AgentBase Memory: roughly 1 in 6 real, back-to-back
chat turns came back with the conversation looking freshly started (all
prior messages gone), with no relation to how long was waited between
turns. Root cause and full mechanism: checkpointer_local_cache_race.py.

No network anywhere here -- `_FakeMemoryClient` (same one
test_checkpointer_delta_snapshot.py uses) stores events in a dict in
exactly the shape the bridge's `AgentBaseEventClient` reads back;
`_RacyFakeMemoryClient` additionally drops one event from a specific
`list_events` call, standing in for the real service's transient gap.
"""

import base64
import json
from types import SimpleNamespace
from typing import Any

from greennode_agent_bridge.langgraph.memory.events import AgentBaseMemoryEvents

from checkpointer_local_cache_race import patch_merge_local_cache_into_fetch


class _FakeMemoryClient:
    """In-memory stand-in for `greennode_agentbase.memory.MemoryClient`,
    keyed by (session_id, actor_id) like the real service."""

    def __init__(self):
        self.events: dict[tuple[str, str], list[Any]] = {}
        self._counter = 0

    def create_event(self, *, id, actorId, sessionId, request):
        self._counter += 1
        self.events.setdefault((sessionId, actorId), []).append(
            SimpleNamespace(id=f"event-{self._counter}", payload=request.payload)
        )

    def list_events(self, *, id, actorId, sessionId, page, size):
        items = self.events.get((sessionId, actorId), [])
        start = (page - 1) * size
        return SimpleNamespace(
            list_data=items[start : start + size],
            total_page=max(1, (len(items) + size - 1) // size),
        )

    def delete_event(self, *, id, actorId, sessionId, eventId):
        for key, items in self.events.items():
            self.events[key] = [e for e in items if e.id != eventId]


def _event_type(item) -> str:
    """Decode a `_FakeMemoryClient` stored item's payload to read `event_type`,
    the same way the real bridge deserializes it."""
    raw = base64.b64decode(item.payload.binary_data).decode("utf-8")
    return json.loads(raw)["event_type"]


class _RacyFakeMemoryClient(_FakeMemoryClient):
    """Drops ONE already-stored event from a specific `list_events` call,
    simulating GreenNode's real transient gap: a `put()` writes several
    events over several separate HTTP calls (channel-data events, then the
    checkpoint event last), and a read landing in between can see the
    checkpoint but miss one of its own siblings."""

    def __init__(self, drop_event_type_on_call: dict[int, str]):
        super().__init__()
        self._drop_event_type_on_call = drop_event_type_on_call
        self._call_count = 0

    def list_events(self, *, id, actorId, sessionId, page, size):
        self._call_count += 1
        drop_type = self._drop_event_type_on_call.get(self._call_count)
        items = self.events.get((sessionId, actorId), [])
        if drop_type is not None:
            items = [e for e in items if _event_type(e) != drop_type]
        start = (page - 1) * size
        return SimpleNamespace(
            list_data=items[start : start + size],
            total_page=max(1, (len(items) + size - 1) // size),
        )

    def delete_event(self, *, id, actorId, sessionId, eventId):
        for key, items in self.events.items():
            self.events[key] = [e for e in items if e.id != eventId]


def _checkpoint(cp_id: str, parent_id: str | None, version: str) -> dict:
    return {
        "v": 4,
        "id": cp_id,
        "ts": "2026-09-13T00:00:00+00:00",
        "channel_values": {"messages": [f"state as of {cp_id}"]},
        "channel_versions": {"messages": version},
        "versions_seen": {},
    }


def _original_buggy_get_tuple(self: AgentBaseMemoryEvents, config):
    """The exact, unmodified decision logic from `AgentBaseMemoryEvents.get_tuple()`
    (see checkpointer_local_cache_race.py's docstring for the annotated original).
    Kept here, independent of the live (module-patched) class method, so this test
    reproduces the bug deterministically regardless of whether some other test in the
    suite already called `patch_merge_local_cache_into_fetch()` first (it is applied
    process-wide and persists for the rest of the session, same as every other patch
    in this repo's checkpointer_*.py modules)."""
    from greennode_agent_bridge.langgraph.memory.models import CheckpointerConfig

    checkpoint_config = CheckpointerConfig.from_runnable_config(dict(config))
    cache_key = self._cache_key(checkpoint_config.thread_id, checkpoint_config.actor_id)
    events = self.checkpoint_event_client.get_events(
        checkpoint_config.thread_id, checkpoint_config.actor_id, self.limit, self.max_results
    )
    checkpoints, writes_by_checkpoint, channel_data = self.processor.process_events(events)

    cached = self._get_cached(cache_key)
    latest_fetch = max(checkpoints.keys()) if checkpoints else None
    latest_local = max(cached[0].keys()) if cached and cached[0] else None
    if latest_fetch is not None and (latest_local is None or latest_fetch >= latest_local):
        self._local_cache.pop(cache_key, None)
    elif cached is not None and latest_local is not None:
        checkpoints, writes_by_checkpoint, channel_data = cached

    if not checkpoints:
        return None
    latest_checkpoint_id = max(checkpoints.keys())
    checkpoint_event = checkpoints[latest_checkpoint_id]
    writes = writes_by_checkpoint.get(checkpoint_event.checkpoint_id, [])
    return self.processor.build_checkpoint_tuple(checkpoint_event, writes, channel_data, checkpoint_config)


def test_a_fetch_that_merely_looks_fresh_enough_can_be_missing_the_latest_channel_data():
    """Documents the bug's exact trigger: the fetch's checkpoint id can equal the
    cache's (satisfying the original code's `latest_fetch >= latest_local`) while a
    sibling event of that SAME checkpoint -- the piece the bridge decides between
    trusting the fetch or the cache with -- is still missing from the fetch."""
    memory_client = _RacyFakeMemoryClient(drop_event_type_on_call={2: "channel_data"})
    checkpointer = AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)
    config = {"configurable": {"thread_id": "t1", "actor_id": "CIF_0001"}}

    checkpointer.put(config, _checkpoint("cp-1", None, "v1"), {}, {"messages": "v1"})
    _original_buggy_get_tuple(checkpointer, config)  # call #1: consumes the "fresh" list_events response

    # call #2 (below) is the one _RacyFakeMemoryClient makes incomplete: the checkpoint
    # event is still there (same id: "fetch looks fresh enough"), but the channel-data
    # event carrying the actual message content is missing.
    events = memory_client.events[("t1", "CIF_0001")]
    assert any(_event_type(e) == "channel_data" for e in events)  # sanity: it really exists

    tup_without_the_fix = _original_buggy_get_tuple(checkpointer, config)
    assert "messages" not in tup_without_the_fix.checkpoint["channel_values"]  # the bug: silently lost


def test_the_patch_keeps_the_locally_known_state_when_the_fetch_is_incomplete():
    # Patch FIRST: an unpatched get_tuple() call evicts the local cache as a side effect
    # (`self._local_cache.pop(cache_key, None)`) even when its own fetch was complete --
    # part of the bug -- which would defeat this test if it ran even one call unpatched.
    patch_merge_local_cache_into_fetch()
    memory_client = _RacyFakeMemoryClient(drop_event_type_on_call={1: "channel_data"})
    checkpointer = AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)
    config = {"configurable": {"thread_id": "t1", "actor_id": "CIF_0001"}}

    checkpointer.put(config, _checkpoint("cp-1", None, "v1"), {}, {"messages": "v1"})
    tup = checkpointer.get_tuple(config)  # call #1, the one the fake makes incomplete

    assert tup.checkpoint["channel_values"]["messages"] == ["state as of cp-1"]


def test_the_patch_still_picks_up_a_checkpoint_written_by_a_different_process():
    """The merge must not just freeze on the local cache -- a fetch that finds a
    genuinely NEWER checkpoint (e.g. written by another process, so this checkpointer's
    own local cache never saw it) must still be reflected."""
    memory_client = _FakeMemoryClient()
    writer = AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)
    config = {"configurable": {"thread_id": "t1", "actor_id": "CIF_0001"}}
    writer.put(config, _checkpoint("cp-1", None, "v1"), {}, {"messages": "v1"})

    patch_merge_local_cache_into_fetch()
    reader = AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)  # fresh instance, empty local cache
    tup = reader.get_tuple(config)

    assert tup is not None
    assert tup.checkpoint["channel_values"]["messages"] == ["state as of cp-1"]


def test_the_patch_merges_writes_for_the_same_checkpoint_without_duplicating_them():
    memory_client = _FakeMemoryClient()
    checkpointer = AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)
    config = {"configurable": {"thread_id": "t1", "actor_id": "CIF_0001", "checkpoint_id": "cp-1"}}
    checkpointer.put(config, _checkpoint("cp-1", None, "v1"), {}, {"messages": "v1"})
    checkpointer.put_writes(config, [("messages", "pending")], task_id="task-1")

    patch_merge_local_cache_into_fetch()
    checkpointer.get_tuple(config)  # populates the merged cache with this write
    tup = checkpointer.get_tuple(config)  # a second read must not duplicate it

    assert len(tup.pending_writes) == 1
    assert tup.pending_writes[0] == ("task-1", "messages", "pending")


def test_the_patch_is_idempotent():
    patch_merge_local_cache_into_fetch()
    once = AgentBaseMemoryEvents.get_tuple
    patch_merge_local_cache_into_fetch()
    assert AgentBaseMemoryEvents.get_tuple is once


def test_delete_thread_also_clears_the_local_cache_so_a_deleted_thread_stays_deleted():
    """Found while verifying the fix end-to-end: merging the local cache into every
    fetch (this module's whole point) means a stale-but-not-yet-TTL-expired local
    cache entry can resurrect a thread's messages after `delete_thread()` -- the
    remote events are gone, but nothing told `_local_cache` about the delete, and it
    keeps serving what it already had for up to its own 30s TTL. Deleting must drop
    the cache entry too, not just the remote events."""
    memory_client = _FakeMemoryClient()
    checkpointer = AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)
    config = {"configurable": {"thread_id": "t1", "actor_id": "CIF_0001"}}

    patch_merge_local_cache_into_fetch()
    checkpointer.put(config, _checkpoint("cp-1", None, "v1"), {}, {"messages": "v1"})
    checkpointer.get_tuple(config)  # populates _local_cache via the merge patch
    assert checkpointer._cache_key("t1", "CIF_0001") in checkpointer._local_cache  # sanity

    checkpointer.delete_thread("t1", "CIF_0001")

    assert checkpointer._cache_key("t1", "CIF_0001") not in checkpointer._local_cache
    assert checkpointer.get_tuple(config) is None  # not resurrected from the (now-cleared) cache


def test_multi_turn_thread_survives_a_racy_read_on_every_other_turn():
    """End-to-end on the real checkpointer, through a real LangGraph graph: a thread
    whose remote reads intermittently miss a sibling event of the latest checkpoint
    (like the real soak-test finding: wrong on roughly 1 in 6 turns) must still
    reconstruct the full conversation on every turn, not just the ones that happened
    to get a complete read."""
    from typing import Annotated, TypedDict

    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.graph import START, StateGraph
    from langgraph.graph.message import add_messages

    patch_merge_local_cache_into_fetch()

    class State(TypedDict):
        messages: Annotated[list, add_messages]

    def reply(state: State):
        return {"messages": [AIMessage(content=f"reply {len(state['messages'])}")]}

    # Every 3rd list_events call drops a channel-data event -- the exact shape of gap
    # the soak test's flip-flopping (correct, correct, correct, wrong, correct, ...) pointed at.
    memory_client = _RacyFakeMemoryClient(drop_event_type_on_call={i: "channel_data" for i in range(3, 60, 3)})
    graph = StateGraph(State)
    graph.add_node("reply", reply)
    graph.add_edge(START, "reply")
    app = graph.compile(checkpointer=AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client))

    config = {"configurable": {"thread_id": "t1", "actor_id": "CIF_0001"}}
    expected: list[str] = []
    for turn in range(1, 9):
        result = app.invoke({"messages": [HumanMessage(content=f"q{turn}")]}, config=config)
        expected += [f"q{turn}", f"reply {len(expected) + 1}"]
        assert [m.content for m in result["messages"]] == expected, f"lost history on turn {turn}"

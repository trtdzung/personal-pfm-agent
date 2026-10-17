"""Regression tests for checkpointer_delta_snapshot.py.

Guards the bug that made EVERY /chat request fail on a busy thread with
`NotImplementedError: Message as a sequence must be (role string, template)`:
`AgentBaseMemoryEvents` flattened `DeltaChannel`'s snapshot blob
(`_DeltaSnapshot(value=[...])`) into `[[...]]` while reading a checkpoint.
See checkpointer_delta_snapshot.py for the full mechanism.

No network anywhere here -- `_FakeMemoryClient` stores events in a dict in
exactly the shape the bridge's `AgentBaseEventClient` reads back.
"""

from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest
from greennode_agent_bridge.langgraph.memory import helpers as bridge_helpers
from greennode_agent_bridge.langgraph.memory.helpers import EventProcessor
from greennode_agent_bridge.langgraph.memory.models import (
    ChannelDataEvent,
    CheckpointerConfig,
    CheckpointEvent,
)
from langchain_core.messages import AIMessage, HumanMessage

from checkpointer_delta_snapshot import patch_preserve_delta_snapshots


class _SnapshotBlob(NamedTuple):
    """Stand-in for langgraph's private `_DeltaSnapshot` (same shape: a
    single-field namedtuple wrapping the accumulated channel value). Used so
    these tests also run against langgraph-checkpoint versions that predate
    `_DeltaSnapshot`; the end-to-end test below uses the real thing."""

    value: Any


def _build_tuple_for_channel_value(value: Any):
    """Run one `messages` channel value through the bridge's checkpoint read
    path and return the reconstructed `channel_values["messages"]`."""
    checkpoint_event = CheckpointEvent(
        checkpoint_id="cp-1",
        checkpoint_data={
            "v": 4,
            "id": "cp-1",
            "ts": "2026-09-13T00:00:00+00:00",
            "channel_versions": {"messages": "v1"},
            "versions_seen": {},
        },
        metadata={},
        thread_id="t1",
    )
    channel_data = {("messages", "v1"): value}
    result = EventProcessor.build_checkpoint_tuple(
        checkpoint_event,
        [],
        channel_data,
        CheckpointerConfig(thread_id="t1", actor_id="CIF_0001"),
    )
    return result.checkpoint["channel_values"]["messages"]


def test_delta_snapshot_blob_is_returned_unchanged():
    patch_preserve_delta_snapshots()
    messages = [HumanMessage(content="hello", id="m1"), AIMessage(content="hi", id="m2")]

    loaded = _build_tuple_for_channel_value(_SnapshotBlob(value=messages))

    # Unwrapping/flattening here is what broke reconstruction: DeltaChannel.
    # from_checkpoint stops recognising the blob and feeds a nested list to
    # the reducer.
    assert isinstance(loaded, _SnapshotBlob)
    assert loaded.value == messages


def test_plain_message_list_still_gets_orphan_tool_call_repair():
    """The patch must narrow the bridge's repair pass to plain lists, not
    disable it -- a pre-delta plain list value still gets its orphaned
    tool_call closed with a placeholder ToolMessage."""
    patch_preserve_delta_snapshots()
    messages = [
        HumanMessage(content="hello", id="m1"),
        AIMessage(
            content="",
            id="m2",
            tool_calls=[{"name": "read_file", "args": {}, "id": "call1"}],
        ),
    ]

    loaded = _build_tuple_for_channel_value(messages)

    assert isinstance(loaded, list)
    assert [type(m).__name__ for m in loaded] == ["HumanMessage", "AIMessage", "ToolMessage"]
    assert loaded[-1].tool_call_id == "call1"
    assert loaded[-1].status == "error"


def test_patch_is_idempotent():
    patch_preserve_delta_snapshots()
    once = bridge_helpers.patch_orphan_tool_calls
    patch_preserve_delta_snapshots()
    assert bridge_helpers.patch_orphan_tool_calls is once


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


def test_multi_turn_thread_survives_delta_snapshot_boundaries():
    """End-to-end on the real checkpointer: a thread that writes snapshot
    blobs and then keeps going must keep reconstructing its full history.

    `snapshot_frequency=2` compresses what deepagents hits at 50 updates to
    the `messages` channel, so a handful of turns crosses several snapshot
    boundaries -- the exact situation where every request on the default
    thread (`thread_id == user_id`) used to start failing.
    """
    delta = pytest.importorskip(
        "langgraph.channels.delta",
        reason="langgraph without DeltaChannel: nothing to guard against",
    )
    from typing import Annotated, TypedDict

    from deepagents._messages_reducer import _messages_delta_reducer
    from greennode_agent_bridge import AgentBaseMemoryEvents
    from langchain_core.messages import AnyMessage
    from langgraph.graph import START, StateGraph

    patch_preserve_delta_snapshots()

    class State(TypedDict):
        messages: Annotated[
            list[AnyMessage],
            delta.DeltaChannel(_messages_delta_reducer, snapshot_frequency=2),
        ]

    def reply(state: State):
        return {"messages": [AIMessage(content=f"reply {len(state['messages'])}")]}

    memory_client = _FakeMemoryClient()
    graph = StateGraph(State)
    graph.add_node("reply", reply)
    graph.add_edge(START, "reply")
    app = graph.compile(
        checkpointer=AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)
    )

    config = {"configurable": {"thread_id": "t1", "actor_id": "CIF_0001"}}
    expected: list[str] = []
    for turn in range(1, 9):
        result = app.invoke({"messages": [HumanMessage(content=f"q{turn}")]}, config=config)
        expected += [f"q{turn}", f"reply {len(expected) + 1}"]
        assert [m.content for m in result["messages"]] == expected, f"diverged on turn {turn}"

    # Fresh checkpointer instance: no in-process cache, so this reads the
    # whole history back out of the stored events alone.
    cold_app = graph.compile(
        checkpointer=AgentBaseMemoryEvents(memory_id="mem-1", memory_client=memory_client)
    )
    cold_state = cold_app.get_state(config)
    assert [m.content for m in cold_state.values["messages"]] == expected

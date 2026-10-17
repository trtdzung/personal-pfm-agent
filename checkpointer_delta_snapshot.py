"""Stop `AgentBaseMemoryEvents` from corrupting `DeltaChannel` snapshot blobs.

## The bug this works around

`greennode-agent-bridge`'s `AgentBaseMemoryEvents` ends every checkpoint
read with an orphan-tool-call repair pass (`helpers.patch_orphan_tool_calls`,
called from `EventProcessor.build_checkpoint_tuple`) that assumes
`checkpoint["channel_values"]["messages"]` is a plain `list[BaseMessage]`:

    if "messages" in channel_values and not has_interrupts:
        channel_values["messages"] = patch_orphan_tool_calls(channel_values["messages"])

Since langgraph 1.1 + deepagents 0.7, that assumption is wrong. deepagents'
state puts `messages` on a `DeltaChannel` (`deepagents/graph.py`:
`DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)`), which does
*not* store the message list in `channel_values` on every step. Instead it
stores nothing at all for most checkpoints (state is rebuilt by replaying
ancestor writes through the reducer) and, every 50th update to the channel,
one full snapshot blob wrapped in a `_DeltaSnapshot` namedtuple:
`channel_values["messages"] = _DeltaSnapshot(value=[msg, msg, ...])`.

`patch_orphan_tool_calls` iterates whatever it is handed. Handed a
`_DeltaSnapshot`, it iterates the namedtuple's single field and returns
`[[msg, msg, ...]]` -- the message list nested one level deeper inside a
plain list. `DeltaChannel.from_checkpoint` then no longer recognises it as
a snapshot, treats it as a pre-delta plain value, and hands that nested
list to the reducer as the accumulated state. The reducer sees
`state[0]` is a list rather than a `BaseMessage`, falls back to
`convert_to_messages()`, and dies:

    NotImplementedError: Message as a sequence must be (role string, template)
    (from: ValueError: too many values to unpack (expected 2))

## Why it looked like "corrupt old history"

Every request on the affected thread fails, no matter what the new question
is, because the crash happens while *loading* state -- and it only starts
happening once a thread is busy enough to have written a snapshot blob
(50 updates to the messages channel) and then moved past it. That is why
short-lived/fresh threads look fine, why the well-used default thread
(`thread_id == user_id`, see `_default_thread_id` in server.py) breaks, and
why `DELETE /chat/history` "fixes" it -- until the thread accumulates 50
more updates. See todo.md section 1.5, which previously recorded this as
suspected stale/old-format history; the real trigger is the snapshot blob,
which is written by the *current* versions.

## The fix

Only run the bridge's orphan-tool-call repair on values that really are a
plain `list`. Anything else (today: a `_DeltaSnapshot`) is passed through
untouched, exactly as stored, so `DeltaChannel.from_checkpoint` recognises
it and reconstruction proceeds normally.

Deliberately *not* done here: unwrapping the snapshot, repairing inside it,
and re-wrapping. A snapshot is a mid-chain seed, not the final state -- the
tool call that looks orphaned inside it is very often completed by a
`ToolMessage` in a later replayed write (snapshots land on superstep
boundaries, and the boundary right after the model node is exactly where a
tool call has no result yet). Injecting a placeholder "interrupted"
`ToolMessage` there would leave two `ToolMessage`s for one `tool_call_id`
after replay, which is worse than the gap it tries to close. Skipping the
repair for delta snapshots puts this checkpointer where every other
LangGraph saver already is: `InMemorySaver` and `PostgresSaver` do no
orphan repair at all.

This patches a third-party package's module-level function in place; it is
a workaround, not a fix to `greennode-agent-bridge` (latest release, 1.0.5,
still has it). Report upstream, and drop this module when a fixed release
ships.
"""

import logging
from typing import Any

from greennode_agent_bridge.langgraph.memory import helpers as _bridge_helpers

logger = logging.getLogger(__name__)

_PATCHED_MARKER = "_pca_delta_snapshot_safe"


def patch_preserve_delta_snapshots() -> None:
    """Make the bridge's orphan-tool-call repair skip non-`list` channel
    values (i.e. `DeltaChannel` snapshot blobs). Idempotent: safe to call on
    every `build_agent()`."""
    original = _bridge_helpers.patch_orphan_tool_calls
    if getattr(original, _PATCHED_MARKER, False):
        return

    def patch_orphan_tool_calls(messages: Any) -> Any:
        if not isinstance(messages, list):
            # A DeltaChannel snapshot blob (`_DeltaSnapshot` namedtuple) or
            # any other non-list stored representation: return it byte-for-byte
            # so DeltaChannel.from_checkpoint can still recognise it.
            logger.debug(
                "skipping orphan tool call repair for non-list messages blob: %s",
                type(messages).__name__,
            )
            return messages
        return original(messages)

    setattr(patch_orphan_tool_calls, _PATCHED_MARKER, True)
    _bridge_helpers.patch_orphan_tool_calls = patch_orphan_tool_calls

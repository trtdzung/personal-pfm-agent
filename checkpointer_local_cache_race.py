"""Stop `AgentBaseMemoryEvents.get_tuple()` from discarding its own correct
local cache in favour of a remote read that merely LOOKS fresh enough.

## The bug this works around

`AgentBaseMemoryEvents.put()` keeps an in-process cache (`self._local_cache`,
keyed by thread_id + actor_id) of every checkpoint/write/channel-data event
it has ever written, purely so a checkpointer that just wrote a thread can
read its own write back correctly ("read-your-writes"). `get_tuple()` is
supposed to fall back to that cache when the remote read looks stale:

    latest_fetch = max(checkpoints.keys()) if checkpoints else None
    latest_local = max(cached[0].keys()) if cached and cached[0] else None
    if latest_fetch is not None and (latest_local is None or latest_fetch >= latest_local):
        self._local_cache.pop(cache_key, None)          # trust the fetch
    elif cached is not None and latest_local is not None:
        checkpoints, writes_by_checkpoint, channel_data = cached  # trust the cache

The comparison only asks "does the fetch's newest *checkpoint id* look at
least as new as the cache's?" -- checkpoint ids are ULIDs, monotonically
increasing by wall-clock time regardless of whether the fetch is complete.
A single `put()` stores several events over several separate HTTP calls
(one `ChannelDataEvent` per changed channel, then the `CheckpointEvent`
itself, see `AgentBaseMemoryEvents.put()`); deepagents' state machine calls
`put()` upwards of a dozen times per turn (own measurement: 12+ checkpoints
for one chat turn). If the remote listing is read back before every sibling
event of the *latest* checkpoint has landed -- observed directly against
real GreenNode AgentBase Memory: raw event counts settle within ~1-2s, but
`get_tuple()`'s reconstructed message count was still wrong on roughly 1 in
6 real, back-to-back turns in a soak test, with no relation to elapsed
time -- the fetch's `checkpoints` dict can already contain the newest
checkpoint id (satisfying `latest_fetch >= latest_local`) while its
`channel_data`/`writes_by_checkpoint` for that very checkpoint are still
missing an entry. The code above discards the local cache -- which DOES
have that entry, because this same process just wrote it -- and returns an
incomplete reconstruction: `deepagents`' `DeltaChannel` sees no value for
`messages` on that checkpoint at all, and every subsequent call within the
process keeps re-fetching that same incomplete remote view (the local
cache was already evicted), silently forgetting the conversation until the
next `put()` happens to repopulate it. Doubles back on itself
unpredictably -- not a fixed-length delay -- because it depends on which
individual sibling event happened to lag on that particular read.

## Why this only bites checkpoint reconstruction, not the raw event count

A raw event *count* (`list_events` / `get_events`) can be fully populated
while `get_tuple()` still mis-reconstructs state, because reconstruction
also depends on EVERY checkpoint in the ancestor chain supplying the exact
`(channel, version)` pair its own `channel_versions` asks for (see
`EventProcessor.build_checkpoint_tuple`) -- a transient gap in any single
one of those siblings, anywhere in the chain, is enough.

## The fix

Never let a fetch (however "new" its latest checkpoint id looks) throw
away entries the local cache already has. Merge fetched checkpoints,
writes and channel data INTO the cached copy instead of choosing one side,
then write the merged result back to the cache. This is a strict
superset union: a fetch's own genuinely new data (e.g. checkpoints written
by a *different* process) is still picked up, and gets kept in the merged
cache from then on. The local cache is only ever *this* checkpointer
instance's own memory of what it already confirmed, so merging it in can
only make later reads more complete, never wrong -- unlike the current
strict either/or choice, which can regress a fully-correct picture back to
an incomplete one.

Deliberately **not** fixed here: `AgentBaseMemoryEvents.list()` (used for
`get_state_history`) reads the raw fetch with no cache fallback of any
kind -- the library's own `# TODO: room for caching here` marks this as a
known gap upstream. Out of scope: nothing in this repo calls `list()`
today (`/chat`'s history endpoint reads the live state via `get_state()`,
not the checkpoint list).

## A second bug this merge exposes: `delete_thread()` doesn't clear the cache

Making the local cache authoritative (merged into every fetch, per above)
has one consequence of its own: `delete_thread()` only deletes the remote
events -- it never touches `self._local_cache` -- so a thread just deleted
can still be read back exactly as it was, for as long as its cache entry's
own 30-second TTL has not lapsed, once this fix is applied. Found while
verifying `DELETE /chat/history` end-to-end against real GreenNode
AgentBase Memory: two quick chat turns, then delete, then an immediate
re-read still showed the "deleted" messages. This module also patches
`delete_thread()` to evict that thread's cache entry, so a delete is
immediately and reliably final.

This patches a third-party package's method in place (same convention as
`checkpointer_delta_snapshot.py`); it is a workaround, not a fix to
`greennode-agent-bridge` (latest release, 1.0.5, still has it). Report
upstream, and drop this module when a fixed release ships.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from greennode_agent_bridge.langgraph.memory.events import AgentBaseMemoryEvents
from greennode_agent_bridge.langgraph.memory.models import CheckpointerConfig

logger = logging.getLogger(__name__)

_PATCHED_MARKER = "_pca_merges_local_cache"


def _write_key(write: Any) -> tuple[str, str, str]:
    """Identify a `WriteItem` slot for de-duplication when merging two write
    lists for the same checkpoint (the fetch and the cache both list the
    same writes verbatim once both sides have caught up)."""
    return (write.task_id, write.channel, write.task_path)


def patch_merge_local_cache_into_fetch() -> None:
    """Replace `AgentBaseMemoryEvents.get_tuple` with a version that MERGES
    the local read-your-writes cache into every remote fetch instead of
    discarding it whenever the fetch's checkpoint id merely looks new
    enough. Idempotent: safe to call on every `build_agent()`."""
    if getattr(AgentBaseMemoryEvents.get_tuple, _PATCHED_MARKER, False):
        return

    def get_tuple(self: AgentBaseMemoryEvents, config):
        checkpoint_config = CheckpointerConfig.from_runnable_config(dict(config))
        cache_key = self._cache_key(checkpoint_config.thread_id, checkpoint_config.actor_id)

        events = self.checkpoint_event_client.get_events(
            checkpoint_config.thread_id,
            checkpoint_config.actor_id,
            self.limit,
            self.max_results,
        )
        fetched_checkpoints, fetched_writes, fetched_channel_data = self.processor.process_events(events)

        cached = self._get_cached(cache_key)
        if cached is None:
            checkpoints = fetched_checkpoints
            writes_by_checkpoint = dict(fetched_writes)
            channel_data = fetched_channel_data
        else:
            cached_checkpoints, cached_writes, cached_channel_data = cached
            checkpoints = {**cached_checkpoints, **fetched_checkpoints}
            writes_by_checkpoint = dict(cached_writes)
            for checkpoint_id, items in fetched_writes.items():
                existing = writes_by_checkpoint.get(checkpoint_id, [])
                seen = {_write_key(w) for w in existing}
                writes_by_checkpoint[checkpoint_id] = existing + [
                    w for w in items if _write_key(w) not in seen
                ]
            channel_data = {**cached_channel_data, **fetched_channel_data}

        if checkpoints:
            # Keep the cache as the merged (more complete) picture, not just the fetch.
            self._local_cache[cache_key] = (checkpoints, writes_by_checkpoint, channel_data, time.time())

        if not checkpoints:
            return None

        if checkpoint_config.checkpoint_id:
            checkpoint_event = checkpoints.get(checkpoint_config.checkpoint_id)
            if not checkpoint_event:
                return None
        else:
            latest_checkpoint_id = max(checkpoints.keys())
            checkpoint_event = checkpoints[latest_checkpoint_id]

        writes = writes_by_checkpoint.get(checkpoint_event.checkpoint_id, [])
        return self.processor.build_checkpoint_tuple(
            checkpoint_event, writes, channel_data, checkpoint_config
        )

    original_delete_thread = AgentBaseMemoryEvents.delete_thread

    def delete_thread(self: AgentBaseMemoryEvents, thread_id: str, actor_id: str = "") -> None:
        original_delete_thread(self, thread_id, actor_id)
        self._local_cache.pop(self._cache_key(thread_id, actor_id), None)

    setattr(get_tuple, _PATCHED_MARKER, True)
    AgentBaseMemoryEvents.get_tuple = get_tuple
    AgentBaseMemoryEvents.delete_thread = delete_thread

"""Stop `AgentBaseMemoryEvents.delete_thread()` from leaving events behind on
a thread with more than one page of events.

## The bug this works around

`AgentBaseEventClient.delete_events()` (called by `delete_thread()`) walks
pages forward while deleting:

    page = 1
    while True:
        response = list_events(..., page=page, size=100)
        events_list = response.list_data or []
        if not events_list:
            break
        for event in events_list:
            delete_event(...)
        if page >= (response.total_page or 1):
            break
        page += 1

Deleting every item on `page` shifts everything that WAS on `page + 1`
back into `page` (a normal offset-based list shrinks from the front as
items are removed). Advancing to `page + 1` next then skips exactly the
events that just shifted into the page that was already cleared -- for a
thread with 100 events per page, roughly half the SECOND page's events
survive every full pass, and so on for later pages. Verified directly
against real GreenNode AgentBase Memory: `DELETE /chat/history` on a
~300-event thread (created by a few dozen real chat turns) left 2
messages behind; a naive `list_events` + `delete_event` loop that always
re-reads page 1 (this module's fix) then found 1575 further leftover
events still on that same thread across repeated runs.

## The fix

Always re-list page 1 after deleting a page's worth of events, instead of
advancing to the next page number -- the same approach already used by
this repo's own manual cleanup scripts. Whatever shifted forward is caught
on the next iteration; the loop only stops once a `list_events` call
genuinely returns nothing.

## Also: deletes now run several at a time, not strictly one by one

Correctness fixed, `DELETE /chat/history` was still slow in its own right:
measured 85s for a thread of only 8 real chat turns (~415 events) against
real GreenNode AgentBase Memory, because the underlying SDK issues one
`delete_event` HTTP call per event with nothing else running concurrently.
Checked GreenNode's own API reference (`docs/agent-base/reference.md`) for
a batch/bulk-delete endpoint or a documented Memory rate limit first --
neither exists; per-event delete is the only documented way, and no
concurrency ceiling is published. Given that, this module deletes each
page's events through a small thread pool (`max_workers`, default 10)
instead of a plain `for` loop -- still one synchronous `DELETE
/chat/history` call from the caller's point of view (no background job),
just no longer serialising work that does not depend on itself. `size=100`
per page bounds how many deletes are ever in flight at once regardless of
`max_workers`. `retry_with_backoff`'s existing exponential backoff (already
used for `list_events`, now also wrapping each `delete_event`) is the
buffer against hitting an undocumented limit; drop `max_workers` back
toward 1 if that turns out to be too aggressive in practice.

This patches a third-party package's method in place (same convention as
checkpointer_delta_snapshot.py and checkpointer_local_cache_race.py); it is
a workaround, not a fix to `greennode-agent-bridge` (latest release, 1.0.5,
still has it). Report upstream, and drop this module when a fixed release
ships.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from greennode_agent_bridge.langgraph.memory.helpers import AgentBaseEventClient, retry_with_backoff

logger = logging.getLogger(__name__)

_PATCHED_MARKER = "_pca_deletes_every_page"
DEFAULT_MAX_WORKERS = 10  # conservative; no documented rate limit to size this against
_current_max_workers = [DEFAULT_MAX_WORKERS]  # single-item list: mutable cell the patched closure reads live


def patch_delete_events_reads_page_one_every_time(max_workers: int = DEFAULT_MAX_WORKERS) -> None:
    """Replace `AgentBaseEventClient.delete_events` with a version that never
    advances past page 1 (re-lists page 1 after every deletion round, so
    items shifted forward are not skipped -- see module docstring) and
    deletes each page's events through a bounded thread pool instead of one
    at a time. Idempotent -- safe to call on every `build_agent()` -- but
    `max_workers` is always applied, even on a call after the method was
    already patched (it updates the live concurrency, it does not need to
    re-wrap anything)."""
    _current_max_workers[0] = max_workers
    if getattr(AgentBaseEventClient.delete_events, _PATCHED_MARKER, False):
        return

    def delete_events(self: AgentBaseEventClient, session_id: str, actor_id: str) -> None:
        size = 100

        def _delete_one(event) -> None:
            if not event.id:
                return
            retry_with_backoff(
                lambda: self.memory_client.delete_event(
                    id=self.memory_id,
                    actorId=actor_id,
                    sessionId=session_id,
                    eventId=event.id,
                ),
                max_retries=self.max_retries,
                initial_backoff=self.initial_backoff,
                max_backoff=self.max_backoff,
            )

        while True:
            response = retry_with_backoff(
                lambda: self.memory_client.list_events(
                    id=self.memory_id,
                    actorId=actor_id,
                    sessionId=session_id,
                    page=1,
                    size=size,
                ),
                max_retries=self.max_retries,
                initial_backoff=self.initial_backoff,
                max_backoff=self.max_backoff,
            )

            events_list = response.list_data or []
            if not events_list:
                break

            with ThreadPoolExecutor(max_workers=_current_max_workers[0]) as pool:
                # list(...) forces every future to be awaited (and any exception re-raised)
                # before this page is considered done.
                list(pool.map(_delete_one, events_list))

    setattr(delete_events, _PATCHED_MARKER, True)
    AgentBaseEventClient.delete_events = delete_events

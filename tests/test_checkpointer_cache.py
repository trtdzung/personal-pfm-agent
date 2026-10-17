import time
from types import SimpleNamespace

from checkpointer_cache import invalidate, patch_get_events_with_cache


def test_patch_is_noop_when_checkpointer_has_no_checkpoint_event_client():
    checkpointer = SimpleNamespace()  # e.g. InMemorySaver has no such attribute
    patch_get_events_with_cache(checkpointer)  # must not raise


def test_invalidate_is_noop_when_checkpointer_was_never_patched():
    checkpointer = SimpleNamespace()
    invalidate(checkpointer, "thread-1", "CIF_0001")  # must not raise


def test_repeated_calls_within_one_request_hit_cache_not_the_real_fetch():
    calls = []

    class FakeClient:
        def get_events(self, session_id, actor_id, limit=100, max_results=100):
            calls.append((session_id, actor_id, limit, max_results))
            return ["event"]

    checkpointer = SimpleNamespace(checkpoint_event_client=FakeClient())
    patch_get_events_with_cache(checkpointer)

    for _ in range(5):
        result = checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")
        assert result == ["event"]

    assert len(calls) == 1, "expected only the first call to hit the real fetch"


def test_different_thread_or_actor_are_cached_separately():
    calls = []

    class FakeClient:
        def get_events(self, session_id, actor_id, limit=100, max_results=100):
            calls.append((session_id, actor_id))
            return [session_id]

    checkpointer = SimpleNamespace(checkpoint_event_client=FakeClient())
    patch_get_events_with_cache(checkpointer)

    r1 = checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")
    r2 = checkpointer.checkpoint_event_client.get_events("thread-2", "CIF_0001")
    assert r1 == ["thread-1"]
    assert r2 == ["thread-2"]
    assert len(calls) == 2


def test_invalidate_forces_the_next_call_to_hit_the_real_fetch():
    calls = []

    class FakeClient:
        def get_events(self, session_id, actor_id, limit=100, max_results=100):
            calls.append(1)
            return ["event"]

    checkpointer = SimpleNamespace(checkpoint_event_client=FakeClient())
    patch_get_events_with_cache(checkpointer)

    checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")
    checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")
    assert len(calls) == 1, "second call should have hit the cache"

    invalidate(checkpointer, "thread-1", "CIF_0001")
    checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")
    assert len(calls) == 2, "call right after invalidate() must be a real fetch"


def test_invalidate_only_drops_the_matching_thread():
    calls = []

    class FakeClient:
        def get_events(self, session_id, actor_id, limit=100, max_results=100):
            calls.append(session_id)
            return [session_id]

    checkpointer = SimpleNamespace(checkpoint_event_client=FakeClient())
    patch_get_events_with_cache(checkpointer)

    checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")
    checkpointer.checkpoint_event_client.get_events("thread-2", "CIF_0001")
    assert calls == ["thread-1", "thread-2"]

    invalidate(checkpointer, "thread-1", "CIF_0001")

    checkpointer.checkpoint_event_client.get_events("thread-2", "CIF_0001")  # still cached
    checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")  # forced fresh
    assert calls == ["thread-1", "thread-2", "thread-1"]


def test_fallback_ttl_still_expires_for_call_sites_that_never_invalidate():
    calls = []

    class FakeClient:
        def get_events(self, session_id, actor_id, limit=100, max_results=100):
            calls.append(1)
            return ["event"]

    checkpointer = SimpleNamespace(checkpoint_event_client=FakeClient())
    patch_get_events_with_cache(checkpointer, fallback_ttl_seconds=0.05)

    checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")
    time.sleep(0.1)
    checkpointer.checkpoint_event_client.get_events("thread-1", "CIF_0001")

    assert len(calls) == 2, "expected the cache entry to expire after fallback_ttl_seconds"

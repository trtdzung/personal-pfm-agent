import asyncio
import json

import pytest
from langchain_core.runnables.config import var_child_runnable_config

from middleware.seed_customer_context import (
    SeedCustomerContext,
    SESSION_FILE_PATH,
    UnknownCustomerError,
)


def _assert_seeds_customer_data(result: dict) -> None:
    assert "files" in result
    assert SESSION_FILE_PATH in result["files"]

    file_data = result["files"][SESSION_FILE_PATH]
    content = file_data["content"] if isinstance(file_data, dict) else file_data
    if isinstance(content, bytes):
        content = content.decode("utf-8")

    parsed = json.loads(content)
    assert "customer_id" in parsed["customer"]
    assert "transactions" in parsed


def test_before_agent_seeds_customer_data_file():
    # Sync hook: required for callers that use .invoke()/.stream() rather
    # than .ainvoke()/.astream() (e.g. deepagents' local create_deep_agent
    # invoked synchronously, as notebooks/try_agent.ipynb and
    # scripts/verify_agent.py both do). Missing this raised a real
    # TypeError ("No synchronous function provided to abefore_agent") the
    # first time this was run for real.
    middleware = SeedCustomerContext()
    result = middleware.before_agent(state={}, runtime=None)
    _assert_seeds_customer_data(result)


def test_abefore_agent_seeds_customer_data_file():
    middleware = SeedCustomerContext()
    result = asyncio.run(middleware.abefore_agent(state={}, runtime=None))
    _assert_seeds_customer_data(result)


def test_session_file_path_is_absolute():
    assert SESSION_FILE_PATH.startswith("/")


def test_before_agent_uses_default_customer_with_no_runnable_context():
    # No LangGraph run config at all (as in the two tests above) -- this is
    # agent.py's situation too, since its managed_deepagents deployment
    # doesn't set actor_id the way server.py does.
    middleware = SeedCustomerContext()
    result = middleware.before_agent(state={}, runtime=None)
    parsed = json.loads(result["files"][SESSION_FILE_PATH]["content"])
    assert parsed["customer"]["customer_id"] == "CIF_0001"


def test_before_agent_loads_correct_customer_by_actor_id():
    middleware = SeedCustomerContext()
    token = var_child_runnable_config.set({"configurable": {"actor_id": "CIF_0002"}})
    try:
        result = middleware.before_agent(state={}, runtime=None)
    finally:
        var_child_runnable_config.reset(token)

    parsed = json.loads(result["files"][SESSION_FILE_PATH]["content"])
    assert parsed["customer"]["customer_id"] == "CIF_0002"
    assert parsed["customer"]["full_name"] == "Trần Toàn"


def test_before_agent_raises_on_unknown_actor_id():
    middleware = SeedCustomerContext()
    token = var_child_runnable_config.set({"configurable": {"actor_id": "not-a-real-customer"}})
    try:
        with pytest.raises(UnknownCustomerError):
            middleware.before_agent(state={}, runtime=None)
    finally:
        var_child_runnable_config.reset(token)


# --- system-prompt injection: current date + customer data ---


class _FakeRequest:
    def __init__(self, system_prompt, files):
        self.system_prompt = system_prompt
        self.state = {"files": files}
        self.overridden = None

    def override(self, system_message):
        self.overridden = system_message.content
        return self


def _inject(monkeypatch, files, now):
    import middleware.seed_customer_context as mod

    monkeypatch.setattr(mod, "_today", lambda: now)
    request = _FakeRequest("BASE PROMPT", files)
    SeedCustomerContext()._inject_customer_data(request)
    return request.overridden


def test_inject_adds_vietnam_current_date_after_base_prompt(monkeypatch):
    from datetime import datetime

    from middleware.seed_customer_context import _VIETNAM_TZ

    prompt = _inject(monkeypatch, {}, datetime(2026, 9, 19, 8, 30, tzinfo=_VIETNAM_TZ))
    assert prompt.startswith("BASE PROMPT")
    assert "Thứ Bảy, 19/09/2026 (2026-09-19)" in prompt
    assert "KHÔNG tự đoán ngày" in prompt


def test_inject_date_is_present_even_when_no_customer_file(monkeypatch):
    from datetime import datetime

    from middleware.seed_customer_context import _VIETNAM_TZ

    prompt = _inject(monkeypatch, {}, datetime(2026, 1, 5, tzinfo=_VIETNAM_TZ))
    assert "05/01/2026" in prompt
    assert "Dữ liệu khách hàng hiện tại" not in prompt


def test_inject_keeps_customer_data_alongside_date(monkeypatch):
    from datetime import datetime

    from middleware.seed_customer_context import _VIETNAM_TZ

    files = {SESSION_FILE_PATH: {"content": '{"customer": {"customer_id": "CIF_0001"}}'}}
    prompt = _inject(monkeypatch, files, datetime(2026, 9, 19, tzinfo=_VIETNAM_TZ))
    assert "19/09/2026" in prompt
    assert "Dữ liệu khách hàng hiện tại" in prompt
    assert '"customer_id": "CIF_0001"' in prompt


def test_today_uses_vietnam_offset():
    from middleware.seed_customer_context import _VIETNAM_TZ, _today

    assert _today().utcoffset() == _VIETNAM_TZ.utcoffset(None)
    assert _today().utcoffset().total_seconds() == 7 * 3600

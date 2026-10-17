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

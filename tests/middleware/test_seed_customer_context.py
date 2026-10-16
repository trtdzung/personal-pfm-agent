import asyncio
import json

from middleware.seed_customer_context import SeedCustomerContext, SESSION_FILE_PATH


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

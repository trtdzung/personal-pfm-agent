from pathlib import Path

AGENT_PY = Path(__file__).resolve().parents[1] / "agent.py"


def _source() -> str:
    return AGENT_PY.read_text(encoding="utf-8")


def test_agent_module_imports_without_error():
    import agent  # noqa: F401 -- import failure is the test failure


def test_agent_renamed_to_personal_card_agent():
    assert 'name="personal-card-agent"' in _source()


def test_internet_search_tool_removed():
    assert "internet_search" not in _source()


def test_seed_customer_context_middleware_wired():
    assert "SeedCustomerContext()" in _source()

from pathlib import Path

INSTRUCTIONS = Path(__file__).resolve().parents[1] / "instructions.md"


def _text() -> str:
    return INSTRUCTIONS.read_text(encoding="utf-8")


def test_instructions_defines_info_only_role():
    assert "chỉ cung cấp thông tin và tư vấn" in _text()


def test_instructions_references_customer_data_file():
    assert "/customer_data.json" in _text()


def test_instructions_references_budget_memory_file():
    assert "/memories/agent/customer_budgets.json" in _text()


def test_instructions_warns_against_overwriting_whole_budget_file():
    assert "không ghi đè toàn bộ file" in _text()


def test_instructions_no_longer_describes_research_assistant():
    text = _text().lower()
    assert "careful research assistant" not in text
    assert "internet search" not in text

from pathlib import Path

# Expected total from data/customer_data.json ->
# monthly_spending_summary["2026-08"].total_vnd. Update this constant if the
# sample data changes.
EXPECTED_AUGUST_TOTAL_VND = 11324000


def test_answer_contains_correct_august_total():
    answer = Path("answer.md")
    assert answer.exists(), "expected the agent to create answer.md"
    text = answer.read_text()
    assert text.strip(), "answer.md should not be empty"

    normalized = text.replace(".", "").replace(",", "")
    assert str(EXPECTED_AUGUST_TOTAL_VND) in normalized, (
        f"expected answer.md to contain the August total "
        f"({EXPECTED_AUGUST_TOTAL_VND} VND), got: {text}"
    )

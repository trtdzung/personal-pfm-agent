from pathlib import Path

# Expected total from data/customer_data.json -> sum of
# monthly_spending_summary["2026-06"|"2026-07"|"2026-08"].by_category_vnd["Ăn uống"]
# = 3,100,000 + 3,450,000 + 2,900,000. Update this constant if the sample
# data changes. Deliberately NOT a single pre-aggregated field — this
# requires the agent to actually sum across three months.
EXPECTED_AUGUST_TOTAL_VND = 9450000


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

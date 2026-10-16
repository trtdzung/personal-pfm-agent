from pathlib import Path

# Expected transactions from data/customer_data.json, July 2026,
# amount_vnd > 2,000,000. Update this list if the sample data changes.
EXPECTED_MERCHANTS = ["Vietnam Airlines", "Điện Máy Xanh", "Lotte Mart"]


def test_answer_lists_all_large_july_transactions():
    answer = Path("answer.md")
    assert answer.exists(), "expected the agent to create answer.md"
    text = answer.read_text()
    assert text.strip(), "answer.md should not be empty"

    for merchant in EXPECTED_MERCHANTS:
        assert merchant in text, f"expected answer.md to mention {merchant}"

    # A July transaction close to but under the threshold — a meaningful
    # near-miss check, unlike a transaction far below the threshold.
    assert "Sushi Tokyo" not in text

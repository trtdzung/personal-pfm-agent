import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "customer_data.json"


def _load():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def test_customer_data_file_exists_and_valid_json():
    assert DATA_PATH.exists(), "expected data/customer_data.json to exist"
    data = _load()
    assert isinstance(data, dict)


def test_customer_data_has_required_top_level_keys():
    data = _load()
    for key in (
        "customer",
        "chat_memory_example",
        "cards",
        "statements",
        "monthly_spending_summary",
        "transactions",
    ):
        assert key in data, f"missing top-level key: {key}"


def test_customer_has_customer_id():
    data = _load()
    assert "customer_id" in data["customer"]


def test_monthly_totals_match_summed_transactions():
    data = _load()
    totals_by_month: dict[str, int] = {}
    counts_by_month: dict[str, int] = {}
    for txn in data["transactions"]:
        month = txn["date"][:7]
        totals_by_month[month] = totals_by_month.get(month, 0) + txn["amount_vnd"]
        counts_by_month[month] = counts_by_month.get(month, 0) + 1

    for month, summary in data["monthly_spending_summary"].items():
        if month.startswith("_"):
            continue
        assert totals_by_month[month] == summary["total_vnd"], (
            f"{month}: summed transactions {totals_by_month[month]} != "
            f"declared total_vnd {summary['total_vnd']}"
        )
        assert counts_by_month[month] == summary["transaction_count"], (
            f"{month}: summed transaction count {counts_by_month[month]} != "
            f"declared transaction_count {summary['transaction_count']}"
        )


def test_category_breakdown_sums_to_month_total():
    data = _load()
    for month, summary in data["monthly_spending_summary"].items():
        if month.startswith("_"):
            continue
        category_sum = sum(summary["by_category_vnd"].values())
        assert category_sum == summary["total_vnd"], (
            f"{month}: category breakdown sums to {category_sum} != "
            f"total_vnd {summary['total_vnd']}"
        )

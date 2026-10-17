import json
from pathlib import Path

import pytest

CUSTOMERS_DIR = Path(__file__).resolve().parents[2] / "data" / "customers"
CUSTOMER_IDS = ["CIF_0001", "CIF_0002", "CIF_0003"]


def _load(customer_id: str) -> dict:
    path = CUSTOMERS_DIR / f"{customer_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_customer_data_file_exists_and_valid_json(customer_id):
    path = CUSTOMERS_DIR / f"{customer_id}.json"
    assert path.exists(), f"expected data/customers/{customer_id}.json to exist"
    data = _load(customer_id)
    assert isinstance(data, dict)


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_customer_data_has_required_top_level_keys(customer_id):
    data = _load(customer_id)
    for key in (
        "customer",
        "chat_memory_example",
        "account",
        "jars",
        "cards",
        "statements",
        "monthly_spending_summary",
        "transactions",
    ):
        assert key in data, f"missing top-level key: {key}"


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_customer_has_customer_id_and_gender(customer_id):
    data = _load(customer_id)
    assert data["customer"]["customer_id"] == customer_id
    assert data["customer"]["gender"] in ("Nam", "Nữ")


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_monthly_totals_match_summed_transactions(customer_id):
    data = _load(customer_id)
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


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_category_breakdown_sums_to_month_total(customer_id):
    data = _load(customer_id)
    for month, summary in data["monthly_spending_summary"].items():
        if month.startswith("_"):
            continue
        category_sum = sum(summary["by_category_vnd"].values())
        assert category_sum == summary["total_vnd"], (
            f"{month}: category breakdown sums to {category_sum} != "
            f"total_vnd {summary['total_vnd']}"
        )


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_account_balance_is_a_non_negative_number(customer_id):
    data = _load(customer_id)
    account = data["account"]
    assert isinstance(account["account_number"], str) and account["account_number"]
    assert isinstance(account["balance_vnd"], (int, float)) and account["balance_vnd"] >= 0


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_jars_have_required_fields_and_positive_allocation(customer_id):
    data = _load(customer_id)
    jars = data["jars"]
    assert isinstance(jars, list)
    seen_names = set()
    for jar in jars:
        for key in ("jar_id", "jar_name", "allocation_amount_vnd", "created_on"):
            assert key in jar, f"jar missing field: {key}"
        assert isinstance(jar["allocation_amount_vnd"], (int, float)) and jar["allocation_amount_vnd"] > 0
        assert jar["jar_name"] not in seen_names, f"duplicate jar_name: {jar['jar_name']}"
        seen_names.add(jar["jar_name"])

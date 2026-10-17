import pytest
from langchain_core.runnables.config import var_child_runnable_config

from tools.customer_data_tools import (
    _MOCK_BENEFICIARIES,
    _MOCK_JARS,
    list_existing_jars,
    query_beneficiaries,
)

CUSTOMER_IDS = ["CIF_0001", "CIF_0002", "CIF_0003"]


def _invoke_with_actor(tool, actor_id: str) -> str:
    token = var_child_runnable_config.set({"configurable": {"actor_id": actor_id}})
    try:
        return tool.invoke({})
    finally:
        var_child_runnable_config.reset(token)


def test_list_existing_jars_returns_jars_for_correct_customer():
    result = _invoke_with_actor(list_existing_jars, "CIF_0001")
    assert "Giải trí" in result
    assert "600.000" in result or "600000" in result
    assert "Tiết kiệm khẩn cấp" in result


def test_list_existing_jars_reports_empty_list_for_customer_with_no_jars():
    result = _invoke_with_actor(list_existing_jars, "CIF_0003")
    assert "chưa có hũ chi tiêu nào" in result


def test_list_existing_jars_does_not_leak_another_customers_jars():
    result_0001 = _invoke_with_actor(list_existing_jars, "CIF_0001")
    result_0002 = _invoke_with_actor(list_existing_jars, "CIF_0002")
    assert "Hoá đơn" in result_0002
    assert "Hoá đơn" not in result_0001


def test_query_beneficiaries_returns_saved_beneficiary():
    result = _invoke_with_actor(query_beneficiaries, "CIF_0001")
    assert "Toàn" in result
    assert "00012000321" in result
    assert "Techcombank" in result


def test_query_beneficiaries_reports_empty_list_for_customer_with_none_saved():
    result = _invoke_with_actor(query_beneficiaries, "CIF_0002")
    assert "chưa lưu người nhận nào" in result


def test_list_existing_jars_falls_back_to_default_customer_with_no_context():
    # No LangGraph run config at all -- same fallback SeedCustomerContext
    # uses (DEFAULT_CUSTOMER_ID = "CIF_0001"), for callers like agent.py
    # that don't set actor_id.
    result = list_existing_jars.invoke({})
    assert "Giải trí" in result


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_mock_jars_has_entry_for_every_customer(customer_id):
    assert customer_id in _MOCK_JARS, f"_MOCK_JARS missing entry for {customer_id}"


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_mock_jars_have_required_fields_and_positive_allocation(customer_id):
    jars = _MOCK_JARS[customer_id]
    assert isinstance(jars, list)
    seen_names = set()
    for jar in jars:
        for key in ("jar_id", "jar_name", "allocation_amount_vnd", "created_on"):
            assert key in jar, f"jar missing field: {key}"
        assert isinstance(jar["allocation_amount_vnd"], (int, float)) and jar["allocation_amount_vnd"] > 0
        assert jar["jar_name"] not in seen_names, f"duplicate jar_name: {jar['jar_name']}"
        seen_names.add(jar["jar_name"])


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_mock_beneficiaries_has_entry_for_every_customer(customer_id):
    assert customer_id in _MOCK_BENEFICIARIES, f"_MOCK_BENEFICIARIES missing entry for {customer_id}"


@pytest.mark.parametrize("customer_id", CUSTOMER_IDS)
def test_mock_beneficiaries_have_required_fields(customer_id):
    beneficiaries = _MOCK_BENEFICIARIES[customer_id]
    assert isinstance(beneficiaries, list)
    seen_names = set()
    for beneficiary in beneficiaries:
        for key in ("name", "account_number", "bank_name"):
            assert key in beneficiary, f"beneficiary missing field: {key}"
            assert isinstance(beneficiary[key], str) and beneficiary[key]
        assert beneficiary["name"] not in seen_names, f"duplicate beneficiary name: {beneficiary['name']}"
        seen_names.add(beneficiary["name"])

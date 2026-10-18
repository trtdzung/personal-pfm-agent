import httpx
import pytest
from langchain_core.runnables.config import var_child_runnable_config

from tools.customer_data_tools import (
    _MOCK_JARS,
    PFM_BASE_URL,
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


# --- query_beneficiaries(): real HTTP call to the pfm backend, mocked here ---


def _fake_beneficiaries_response(payload, status_code=200):
    def _fake_get(url, params=None, timeout=None):
        assert url == f"{PFM_BASE_URL}/api/beneficiaries"
        return httpx.Response(status_code, json=payload, request=httpx.Request("GET", url))

    return _fake_get


def test_query_beneficiaries_returns_saved_beneficiaries(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_beneficiaries_response(
            [
                {
                    "id": "b_stable_lan",
                    "name": "Nguyễn Thị Lan",
                    "accountNumber": "19012345678901",
                    "bankName": "MSB",
                    "source": "mock",
                }
            ]
        ),
    )
    result = _invoke_with_actor(query_beneficiaries, "CIF_0001")
    assert "Nguyễn Thị Lan" in result
    assert "b_stable_lan" in result
    assert "19012345678901" in result
    assert "MSB" in result


def test_query_beneficiaries_reports_empty_list_when_none_saved(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_beneficiaries_response([]),
    )
    result = _invoke_with_actor(query_beneficiaries, "CIF_0002")
    assert "chưa lưu người nhận nào" in result


def test_query_beneficiaries_passes_actor_id_as_cif_query_param(monkeypatch):
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return httpx.Response(200, json=[], request=httpx.Request("GET", url))

    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_get)
    _invoke_with_actor(query_beneficiaries, "CIF_0003")
    assert captured["params"] == {"cif": "CIF_0003"}


def test_query_beneficiaries_returns_friendly_message_on_network_error(monkeypatch):
    def _raise(url, params=None, timeout=None):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise)
    result = _invoke_with_actor(query_beneficiaries, "CIF_0001")
    assert "Không thể lấy danh sách người nhận" in result

import httpx
from langchain_core.runnables.config import var_child_runnable_config

from tools.customer_data_tools import (
    PFM_BASE_URL,
    get_jar_summary,
    query_beneficiaries,
)


def _invoke_with_actor(tool, actor_id: str, args: dict | None = None) -> str:
    token = var_child_runnable_config.set({"configurable": {"actor_id": actor_id}})
    try:
        return tool.invoke(args or {})
    finally:
        var_child_runnable_config.reset(token)


# --- get_jar_summary(): 1:1 with GET /api/jar-summary?cif=&month= (mocked here) ---

# Shape of the real response, see backend_docs/pfm-read-api.md section A1.
_JAR_SUMMARY = {
    "month": "2026-09",
    "casaBalance": 16000000,
    "unallocated": 9514000,
    "allocationHeadroom": -1000000,
    "jars": [
        {
            "id": "food",
            "label": "Ăn uống",
            "categoryIds": ["dining", "groceries"],
            "role": "spending",
            "budgetLimit": 4000000,
            "spent": 1622000,
            "remaining": 2378000,
            "spendable": 2378000,
            "overLimit": False,
        },
        {
            "id": "lifestyle",
            "label": "Hưởng thụ",
            "categoryIds": ["entertainment"],
            "budgetLimit": 2500000,
            "spent": 2900000,
            "remaining": -400000,
            "spendable": 0,
            "overLimit": True,
        },
        {
            "id": "savings",
            "label": "Tiết kiệm",
            "categoryIds": [],
            "role": "goal",
            "budgetLimit": None,
            "spent": 0,
            "remaining": None,
            "spendable": None,
            "overLimit": False,
        },
    ],
}


def _fake_jar_summary_response(payload, status_code=200, captured=None):
    def _fake_get(url, params=None, timeout=None):
        assert url == f"{PFM_BASE_URL}/api/jar-summary"
        if captured is not None:
            captured["params"] = params
        return httpx.Response(status_code, json=payload, request=httpx.Request("GET", url))

    return _fake_get


def _summary_lines(result: str) -> dict[str, str]:
    """The per-jar lines of the tool output, keyed by jar id."""
    lines = {}
    for line in result.splitlines():
        for jar in _JAR_SUMMARY["jars"]:
            if f"id: {jar['id']} " in line + " ":
                lines[jar["id"]] = line
    return lines


def test_get_jar_summary_lists_every_jar_with_the_endpoint_fields(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY))
    result = _invoke_with_actor(get_jar_summary, "CIF_0001")
    food = _summary_lines(result)["food"]
    assert "Ăn uống" in food
    assert "role: spending" in food
    assert "dining" in food and "groceries" in food
    assert "budgetLimit: 4.000.000đ" in food
    assert "spent: 1.622.000đ" in food
    assert "remaining: 2.378.000đ" in food
    assert "spendable: 2.378.000đ" in food
    assert "overLimit: không" in food


def test_get_jar_summary_shows_the_global_numbers(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY))
    result = _invoke_with_actor(get_jar_summary, "CIF_0001")
    assert "month: 2026-09" in result
    assert "casaBalance: 16.000.000đ" in result
    assert "unallocated: 9.514.000đ" in result


def test_get_jar_summary_keeps_a_negative_headroom_negative(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY))
    result = _invoke_with_actor(get_jar_summary, "CIF_0001")
    assert "allocationHeadroom: -1.000.000đ" in result


def test_get_jar_summary_flags_an_over_limit_jar_and_keeps_its_negative_remaining(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY))
    lifestyle = _summary_lines(_invoke_with_actor(get_jar_summary, "CIF_0001"))["lifestyle"]
    assert "remaining: -400.000đ" in lifestyle
    assert "overLimit: có" in lifestyle
    assert "role" not in lifestyle  # a jar without a role is left as the endpoint sent it


def test_get_jar_summary_never_turns_null_into_zero(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY))
    savings = _summary_lines(_invoke_with_actor(get_jar_summary, "CIF_0001"))["savings"]
    assert "budgetLimit: chưa đặt" in savings
    assert "remaining: chưa biết" in savings
    assert "spendable: chưa biết" in savings
    assert "0đ" not in savings.replace("spent: 0đ", "")  # only the real `spent: 0` may read as zero


def test_get_jar_summary_null_casa_balance_is_unknown_not_zero(monkeypatch):
    payload = {**_JAR_SUMMARY, "casaBalance": None, "unallocated": None, "allocationHeadroom": None}
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(payload))
    result = _invoke_with_actor(get_jar_summary, "CIF_0001")
    assert "casaBalance: chưa biết" in result
    assert "allocationHeadroom: chưa biết" in result


def test_get_jar_summary_with_no_jars_still_reports_headroom(monkeypatch):
    payload = {**_JAR_SUMMARY, "jars": []}
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(payload))
    result = _invoke_with_actor(get_jar_summary, "CIF_0001")
    assert "chưa có hũ nào" in result
    assert "allocationHeadroom: -1.000.000đ" in result


def test_get_jar_summary_sends_the_actor_id_as_cif_and_no_month_by_default(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY, captured=captured)
    )
    _invoke_with_actor(get_jar_summary, "CIF_0002")
    assert captured["params"] == {"cif": "CIF_0002"}


def test_get_jar_summary_passes_a_valid_month_through(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY, captured=captured)
    )
    _invoke_with_actor(get_jar_summary, "CIF_0001", {"month": "2026-08"})
    assert captured["params"] == {"cif": "CIF_0001", "month": "2026-08"}


def test_get_jar_summary_rejects_a_malformed_month_without_calling_pfm(monkeypatch):
    def _must_not_be_called(url, params=None, timeout=None):
        raise AssertionError("pfm must not be called for an invalid month")

    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _must_not_be_called)
    result = _invoke_with_actor(get_jar_summary, "CIF_0001", {"month": "09/2026"})
    assert "YYYY-MM" in result


def test_get_jar_summary_customer_id_is_not_a_model_supplied_parameter():
    assert set(get_jar_summary.args) == {"month"}


def test_get_jar_summary_tells_the_model_not_to_guess_when_pfm_is_unreachable(monkeypatch):
    def _raise(url, params=None, timeout=None):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise)
    result = _invoke_with_actor(get_jar_summary, "CIF_0001")
    assert "Không thể đọc thông tin hũ" in result
    assert "đừng đoán số" in result.lower()


def test_get_jar_summary_treats_a_missing_endpoint_or_server_error_the_same_way(monkeypatch):
    # 404: the endpoint is new and may not be deployed yet; 500: pfm could not read its data.
    for status in (404, 500):
        monkeypatch.setattr(
            "tools.customer_data_tools.httpx.get",
            _fake_jar_summary_response({"error": "jar summary unavailable"}, status_code=status),
        )
        result = _invoke_with_actor(get_jar_summary, "CIF_0001")
        assert "Không thể đọc thông tin hũ" in result, status
        assert str(status) in result


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

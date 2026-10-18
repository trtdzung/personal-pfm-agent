import httpx
from langchain_core.runnables.config import var_child_runnable_config

from tools.customer_data_tools import (
    PFM_BASE_URL,
    fetch_account_summary,
    fetch_categories,
    fetch_jar_summary,
    fetch_live_account_snapshot,
    fetch_transactions_full,
    get_categories,
    get_jar_summary,
    query_beneficiaries,
    render_jar_summary,
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
    assert "role" not in food  # pfm has no jar roles any more
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


def test_get_jar_summary_ignores_a_stray_role_field_instead_of_teaching_the_model_about_roles(monkeypatch):
    payload = {**_JAR_SUMMARY, "jars": [{**_JAR_SUMMARY["jars"][0], "role": "goal"}]}
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(payload))
    result = _invoke_with_actor(get_jar_summary, "CIF_0001")
    assert "role" not in result and "goal" not in result


def _tool_call(name: str, args: dict | None = None) -> dict:
    return {"type": "tool_call", "name": name, "args": args or {}, "id": "call-1"}


def _invoke_as_tool_call(tool, actor_id: str, args: dict | None = None):
    token = var_child_runnable_config.set({"configurable": {"actor_id": actor_id}})
    try:
        return tool.invoke(_tool_call(tool.name, args))
    finally:
        var_child_runnable_config.reset(token)


def test_get_jar_summary_hands_the_raw_summary_to_the_server_as_the_tool_artifact(monkeypatch):
    # server.py checks the ids in an emitted ui against the summary read THIS turn (ui_guard.py)
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY))
    message = _invoke_as_tool_call(get_jar_summary, "CIF_0001")
    assert message.artifact == _JAR_SUMMARY
    assert "budgetLimit: 4.000.000đ" in message.content


def test_get_jar_summary_artifact_is_empty_when_pfm_failed(monkeypatch):
    def _raise(url, params=None, timeout=None):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise)
    message = _invoke_as_tool_call(get_jar_summary, "CIF_0001")
    assert message.artifact is None
    assert "Không thể đọc thông tin hũ" in message.content


# --- fetch_jar_summary / render_jar_summary: the tool's two halves, reused by POST /jar-rebalance ---------------


def test_fetch_jar_summary_takes_the_customer_id_explicitly_and_returns_the_payload(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY, captured=captured)
    )
    assert fetch_jar_summary("CIF_0002", "2026-08") == _JAR_SUMMARY
    assert captured["params"] == {"cif": "CIF_0002", "month": "2026-08"}


def test_fetch_jar_summary_raises_instead_of_hiding_a_failure(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get", _fake_jar_summary_response({"error": "x"}, status_code=500)
    )
    try:
        fetch_jar_summary("CIF_0001")
    except httpx.HTTPError:
        pass
    else:
        raise AssertionError("a failed read must raise, not return something that looks like an empty jar list")


def test_render_jar_summary_is_what_the_tool_shows_the_model():
    rendered = render_jar_summary(_JAR_SUMMARY)
    assert "casaBalance: 16.000.000đ" in rendered and "budgetLimit: 4.000.000đ" in rendered


# --- get_categories(): 1:1 with GET /api/categories?cif= ---------------------------------------------------

_CATEGORIES = [
    {"id": "dining", "label": "Ăn uống ngoài", "kind": "expense", "fixed": True},
    {"id": "c_cafe", "label": "Cà phê", "kind": "expense", "fixed": False},
    {"id": "transfer", "label": "Chuyển khoản", "kind": "transfer", "fixed": True},
]


def _fake_categories_response(payload, status_code=200, captured=None):
    def _fake_get(url, params=None, timeout=None):
        assert url == f"{PFM_BASE_URL}/api/categories"
        if captured is not None:
            captured["params"] = params
        return httpx.Response(status_code, json=payload, request=httpx.Request("GET", url))

    return _fake_get


def test_get_categories_lists_the_customers_own_categories_with_their_kind(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_categories_response(_CATEGORIES))
    result = _invoke_with_actor(get_categories, "CIF_0001")
    assert "id: dining" in result and "Ăn uống ngoài" in result
    assert "id: c_cafe" in result and "Cà phê" in result  # a category the customer created themselves
    assert "kind: expense" in result
    assert "id: transfer" in result and "kind: transfer" in result


def test_get_categories_sends_the_actor_id_as_cif_and_never_asks_for_archived_ones(monkeypatch):
    captured = {}
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_categories_response(_CATEGORIES, captured=captured))
    _invoke_with_actor(get_categories, "CIF_0003")
    assert captured["params"] == {"cif": "CIF_0003"}


def test_get_categories_hands_the_raw_list_to_the_server_as_the_tool_artifact(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_categories_response(_CATEGORIES))
    assert _invoke_as_tool_call(get_categories, "CIF_0001").artifact == _CATEGORIES


def test_get_categories_customer_id_is_not_a_model_supplied_parameter():
    assert set(get_categories.args) == set()


def test_get_categories_tells_the_model_not_to_guess_when_pfm_fails(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_categories_response({"error": "x"}, status_code=500),
    )
    message = _invoke_as_tool_call(get_categories, "CIF_0001")
    assert "Không thể đọc danh mục" in message.content and "đừng đoán" in message.content.lower()
    assert message.artifact is None


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


def test_the_tool_and_render_jar_summary_show_the_model_the_same_text(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _fake_jar_summary_response(_JAR_SUMMARY))
    assert _invoke_with_actor(get_jar_summary, "CIF_0001") == render_jar_summary(_JAR_SUMMARY)


# --- fetch_account_summary()/fetch_transactions_full()/fetch_categories(): raw fetch helpers used by
# middleware/seed_customer_context.py to seed live balance/transactions into the system prompt -----------


def _fake_url_response(expected_url_suffix, payload, status_code=200, captured=None):
    def _fake_get(url, params=None, timeout=None):
        assert url == f"{PFM_BASE_URL}{expected_url_suffix}"
        if captured is not None:
            captured["params"] = params
        return httpx.Response(status_code, json=payload, request=httpx.Request("GET", url))

    return _fake_get


def test_fetch_account_summary_returns_the_raw_dict(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_url_response("/api/account-summary", {"casaBalance": 21600000}),
    )
    assert fetch_account_summary("CIF_0001") == {"casaBalance": 21600000}


def test_fetch_account_summary_sends_cif_query_param(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_url_response("/api/account-summary", {"casaBalance": None}, captured=captured),
    )
    fetch_account_summary("CIF_0003")
    assert captured["params"] == {"cif": "CIF_0003"}


def test_fetch_account_summary_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_url_response("/api/account-summary", {"error": "x"}, status_code=500),
    )
    try:
        fetch_account_summary("CIF_0001")
    except httpx.HTTPError:
        pass
    else:
        raise AssertionError("expected httpx.HTTPError")


def test_fetch_transactions_full_returns_the_raw_list_with_from_to_params(monkeypatch):
    captured = {}
    payload = [{"id": "tx1", "amount": 1000}]
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_url_response("/api/transactions-full", payload, captured=captured),
    )
    assert fetch_transactions_full("CIF_0001", "2026-06-01", "2026-09-23") == payload
    assert captured["params"] == {"cif": "CIF_0001", "from": "2026-06-01", "to": "2026-09-23"}


def test_fetch_categories_returns_the_raw_list(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_url_response("/api/categories", _CATEGORIES),
    )
    assert fetch_categories("CIF_0001") == _CATEGORIES


# --- fetch_live_account_snapshot(): balance + transactions + monthly/category aggregate, all-or-nothing --


def _fake_snapshot_router(account_summary, transactions, categories, fail_url_substring=None):
    def _get(url, params=None, timeout=None):
        if fail_url_substring and fail_url_substring in url:
            raise httpx.ConnectError(f"boom: {url}", request=httpx.Request("GET", url))
        if url.endswith("/api/account-summary"):
            payload = account_summary
        elif url.endswith("/api/transactions-full"):
            payload = transactions
        elif url.endswith("/api/categories"):
            payload = categories
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    return _get


_LIVE_TRANSACTIONS = [
    {
        "id": "tx1",
        "postedAt": "2026-09-15T10:00:00.000Z",
        "amount": 215000,
        "direction": "debit",
        "type": "expense",
        "merchantName": "Highlands Coffee",
        "categoryId": "dining",
        "status": "posted",
        "hidden": False,
    },
    {
        "id": "tx2",
        "postedAt": "2026-09-10T10:00:00.000Z",
        "amount": 500000,
        "direction": "credit",
        "type": "refund",
        "merchantName": "Hoàn tiền Shopee",
        "categoryId": "shopping",
        "status": "posted",
        "hidden": False,
    },
    {
        "id": "tx3",
        "postedAt": "2026-08-20T10:00:00.000Z",
        "amount": 999000,
        "direction": "debit",
        "type": "expense",
        "merchantName": "Hidden one",
        "categoryId": "shopping",
        "status": "posted",
        "hidden": True,
    },
]
_LIVE_CATEGORIES = [
    {"id": "dining", "label": "Ăn uống", "kind": "expense"},
    {"id": "shopping", "label": "Mua sắm", "kind": "expense"},
]


def test_fetch_live_account_snapshot_translates_category_ids_to_vietnamese_labels(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_snapshot_router({"casaBalance": 21600000}, _LIVE_TRANSACTIONS, _LIVE_CATEGORIES),
    )
    snapshot = fetch_live_account_snapshot("CIF_0001", "2026-06-01", "2026-09-23")
    assert snapshot["balance_vnd"] == 21600000
    by_id = {t["id"]: t for t in snapshot["transactions"]}
    assert by_id["tx1"]["category"] == "Ăn uống"
    assert by_id["tx2"]["category"] == "Mua sắm"


def test_fetch_live_account_snapshot_excludes_hidden_transactions(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_snapshot_router({"casaBalance": 21600000}, _LIVE_TRANSACTIONS, _LIVE_CATEGORIES),
    )
    snapshot = fetch_live_account_snapshot("CIF_0001", "2026-06-01", "2026-09-23")
    assert {t["id"] for t in snapshot["transactions"]} == {"tx1", "tx2"}
    assert "2026-08" not in snapshot["monthly_spending_summary"]  # tx3 was the only August txn, hidden


def test_fetch_live_account_snapshot_nets_refunds_against_expenses_per_category_per_month(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_snapshot_router({"casaBalance": 21600000}, _LIVE_TRANSACTIONS, _LIVE_CATEGORIES),
    )
    snapshot = fetch_live_account_snapshot("CIF_0001", "2026-06-01", "2026-09-23")
    september = snapshot["monthly_spending_summary"]["2026-09"]
    assert september["by_category_vnd"] == {"Ăn uống": 215000, "Mua sắm": -500000}
    assert september["total_vnd"] == -285000
    assert september["transaction_count"] == 2


def test_fetch_live_account_snapshot_raises_when_any_of_the_3_calls_fails(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _fake_snapshot_router(
            {"casaBalance": 21600000},
            _LIVE_TRANSACTIONS,
            _LIVE_CATEGORIES,
            fail_url_substring="/api/transactions-full",
        ),
    )
    try:
        fetch_live_account_snapshot("CIF_0001", "2026-06-01", "2026-09-23")
    except httpx.HTTPError:
        pass
    else:
        raise AssertionError("expected httpx.HTTPError")

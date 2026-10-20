import asyncio
import json

import httpx
import pytest
from langchain_core.runnables.config import var_child_runnable_config

from middleware.seed_customer_context import (
    CUSTOMERS_DIR,
    SeedCustomerContext,
    SESSION_FILE_PATH,
    UnknownCustomerError,
)


def _raise_connect_error(*args, **kwargs):
    # simulates pfm being unreachable -- forces the all-or-nothing fallback to mock data, so tests that
    # don't care about the live-pfm path stay deterministic and don't hit the real network.
    raise httpx.ConnectError("pfm unreachable (test)")


def _pfm_router(account_summary=None, transactions=None, categories=None, fail_url_substring=None):
    """Fake httpx.get() dispatching the clock and live account snapshot calls by URL suffix."""

    def _get(url, params=None, timeout=None):
        if fail_url_substring and fail_url_substring in url:
            raise httpx.ConnectError(f"pfm unreachable (test): {url}")
        if url.endswith("/api/clock"):
            payload = {"today": "2026-09-15"}
        elif url.endswith("/api/account-summary"):
            payload = account_summary
        elif url.endswith("/api/transactions-full"):
            payload = transactions
        elif url.endswith("/api/categories"):
            payload = categories
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    return _get


def _assert_seeds_customer_data(result: dict) -> None:
    assert "files" in result
    assert SESSION_FILE_PATH in result["files"]

    file_data = result["files"][SESSION_FILE_PATH]
    content = file_data["content"] if isinstance(file_data, dict) else file_data
    if isinstance(content, bytes):
        content = content.decode("utf-8")

    parsed = json.loads(content)
    assert "customer_id" in parsed["customer"]
    assert "transactions" in parsed


def test_before_agent_seeds_customer_data_file(monkeypatch):
    # Sync hook: required for callers that use .invoke()/.stream() rather
    # than .ainvoke()/.astream() (e.g. deepagents' local create_deep_agent
    # invoked synchronously, as notebooks/try_agent.ipynb and
    # scripts/verify_agent.py both do). Missing this raised a real
    # TypeError ("No synchronous function provided to abefore_agent") the
    # first time this was run for real.
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise_connect_error)
    middleware = SeedCustomerContext()
    result = middleware.before_agent(state={}, runtime=None)
    _assert_seeds_customer_data(result)


def test_abefore_agent_seeds_customer_data_file(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise_connect_error)
    middleware = SeedCustomerContext()
    result = asyncio.run(middleware.abefore_agent(state={}, runtime=None))
    _assert_seeds_customer_data(result)


def test_session_file_path_is_absolute():
    assert SESSION_FILE_PATH.startswith("/")


def test_before_agent_uses_default_customer_with_no_runnable_context(monkeypatch):
    # No LangGraph run config at all (as in the two tests above) -- this is
    # agent.py's situation too, since its managed_deepagents deployment
    # doesn't set actor_id the way server.py does.
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise_connect_error)
    middleware = SeedCustomerContext()
    result = middleware.before_agent(state={}, runtime=None)
    parsed = json.loads(result["files"][SESSION_FILE_PATH]["content"])
    assert parsed["customer"]["customer_id"] == "CIF_0001"


def test_before_agent_loads_correct_customer_by_actor_id(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise_connect_error)
    middleware = SeedCustomerContext()
    token = var_child_runnable_config.set({"configurable": {"actor_id": "CIF_0002"}})
    try:
        result = middleware.before_agent(state={}, runtime=None)
    finally:
        var_child_runnable_config.reset(token)

    parsed = json.loads(result["files"][SESSION_FILE_PATH]["content"])
    assert parsed["customer"]["customer_id"] == "CIF_0002"
    assert parsed["customer"]["full_name"] == "Trần Toàn"


def test_before_agent_raises_on_unknown_actor_id(monkeypatch):
    monkeypatch.setattr("tools.customer_data_tools.httpx.get", _raise_connect_error)
    middleware = SeedCustomerContext()
    token = var_child_runnable_config.set({"configurable": {"actor_id": "not-a-real-customer"}})
    try:
        with pytest.raises(UnknownCustomerError):
            middleware.before_agent(state={}, runtime=None)
    finally:
        var_child_runnable_config.reset(token)


# --- live pfm data (balance/transactions/monthly_spending_summary) overriding the mock ------------------


_ACCOUNT_SUMMARY = {"casaBalance": 21600000}
_CATEGORIES_FOR_LIVE = [
    {"id": "dining", "label": "Ăn uống", "kind": "expense"},
    {"id": "shopping", "label": "Mua sắm", "kind": "expense"},
]
_TRANSACTIONS_FOR_LIVE = [
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
        "postedAt": "2026-09-01T10:00:00.000Z",
        "amount": 999000,
        "direction": "debit",
        "type": "expense",
        "merchantName": "Should not appear",
        "categoryId": "shopping",
        "status": "posted",
        "hidden": True,  # excluded, like jar-summary excludes hidden rows from its totals
    },
]


def test_before_agent_overrides_balance_and_transactions_with_live_pfm_data_when_all_3_calls_succeed(monkeypatch):
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _pfm_router(
            account_summary=_ACCOUNT_SUMMARY,
            transactions=_TRANSACTIONS_FOR_LIVE,
            categories=_CATEGORIES_FOR_LIVE,
        ),
    )
    middleware = SeedCustomerContext()
    result = middleware.before_agent(state={}, runtime=None)
    parsed = json.loads(result["files"][SESSION_FILE_PATH]["content"])

    assert parsed["account"]["balance_vnd"] == 21600000
    assert len(parsed["transactions"]) == 2  # the hidden one is excluded
    assert {t["id"] for t in parsed["transactions"]} == {"tx1", "tx2"}
    assert parsed["transactions"][0]["category"] in ("Ăn uống", "Mua sắm")  # translated, not the raw id

    summary = parsed["monthly_spending_summary"]["2026-09"]
    # net = 215.000 (expense) - 500.000 (refund) = -285.000; the hidden 999.000 expense is excluded
    assert summary["total_vnd"] == -285000
    assert summary["by_category_vnd"] == {"Ăn uống": 215000, "Mua sắm": -500000}
    assert summary["transaction_count"] == 2


def test_before_agent_falls_back_to_mock_entirely_when_any_one_of_the_3_pfm_calls_fails(monkeypatch):
    # account-summary succeeds but transactions-full fails -- must NOT end up with fresh balance next to
    # stale mock transactions; all 3 fields must come from the same (mock) source together.
    monkeypatch.setattr(
        "tools.customer_data_tools.httpx.get",
        _pfm_router(
            account_summary=_ACCOUNT_SUMMARY,
            transactions=_TRANSACTIONS_FOR_LIVE,
            categories=_CATEGORIES_FOR_LIVE,
            fail_url_substring="/api/transactions-full",
        ),
    )
    middleware = SeedCustomerContext()
    result = middleware.before_agent(state={}, runtime=None)
    parsed = json.loads(result["files"][SESSION_FILE_PATH]["content"])

    mock = json.loads((CUSTOMERS_DIR / "CIF_0001.json").read_text(encoding="utf-8"))
    assert parsed["account"]["balance_vnd"] == mock["account"]["balance_vnd"]  # NOT 21.600.000
    assert parsed["transactions"] == mock["transactions"]
    assert parsed["monthly_spending_summary"] == mock["monthly_spending_summary"]


# --- system-prompt injection: current date + customer data ---


class _FakeRequest:
    def __init__(self, system_prompt, files):
        self.system_prompt = system_prompt
        self.state = {"files": files}
        self.overridden = None

    def override(self, system_message):
        self.overridden = system_message.content
        return self


def _inject(monkeypatch, files, now):
    import middleware.seed_customer_context as mod

    monkeypatch.setattr(mod, "_today", lambda: now)
    request = _FakeRequest("BASE PROMPT", files)
    SeedCustomerContext()._inject_customer_data(request)
    return request.overridden


def test_inject_adds_vietnam_current_date_after_base_prompt(monkeypatch):
    from datetime import datetime

    from middleware.seed_customer_context import _VIETNAM_TZ

    prompt = _inject(monkeypatch, {}, datetime(2026, 9, 19, 8, 30, tzinfo=_VIETNAM_TZ))
    assert prompt.startswith("BASE PROMPT")
    assert "Thứ Bảy, 19/09/2026 (2026-09-19)" in prompt
    assert "KHÔNG tự đoán ngày" in prompt


def test_inject_date_is_present_even_when_no_customer_file(monkeypatch):
    from datetime import datetime

    from middleware.seed_customer_context import _VIETNAM_TZ

    prompt = _inject(monkeypatch, {}, datetime(2026, 1, 5, tzinfo=_VIETNAM_TZ))
    assert "05/01/2026" in prompt
    assert "Dữ liệu khách hàng hiện tại" not in prompt


def test_inject_keeps_customer_data_alongside_date(monkeypatch):
    from datetime import datetime

    from middleware.seed_customer_context import _VIETNAM_TZ

    files = {SESSION_FILE_PATH: {"content": '{"customer": {"customer_id": "CIF_0001"}}'}}
    prompt = _inject(monkeypatch, files, datetime(2026, 9, 19, tzinfo=_VIETNAM_TZ))
    assert "19/09/2026" in prompt
    assert "Dữ liệu khách hàng hiện tại" in prompt
    assert '"customer_id": "CIF_0001"' in prompt


def test_today_uses_vietnam_offset():
    from middleware.seed_customer_context import _VIETNAM_TZ, _today

    assert _today().utcoffset() == _VIETNAM_TZ.utcoffset(None)
    assert _today().utcoffset().total_seconds() == 7 * 3600

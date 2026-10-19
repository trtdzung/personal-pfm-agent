import httpx

from tools.security_tools import check_fraud_watchlist, check_official_channel, search_msb_promotions


def _fake_get(payload, status_code=200, calls=None):
    def fake(url, params=None, timeout=None):
        if calls is not None:
            calls.append({"url": url, "params": params})
        return httpx.Response(status_code, json=payload, request=httpx.Request("GET", url))

    return fake


def test_official_channel_says_official_with_the_matching_channel(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tools.security_tools.httpx.get",
        _fake_get({"official": True, "channel": {"type": "domain", "value": "msb.com.vn", "label": "Website chính thức"}}, calls=calls),
    )
    result = check_official_channel.invoke({"value": "https://ebank.msb.com.vn/login"})
    assert calls[0]["url"].endswith("/api/msb-reference/official-channels")
    assert calls[0]["params"] == {"value": "https://ebank.msb.com.vn/login"}
    assert "chính thức" in result and "msb.com.vn" in result


def test_official_channel_not_matching_is_not_called_fake(monkeypatch):
    monkeypatch.setattr("tools.security_tools.httpx.get", _fake_get({"official": False, "channel": None}))
    result = check_official_channel.invoke({"value": "msb-hoantien.com"})
    assert "không nằm trong danh sách kênh chính thức" in result
    assert "giả mạo" not in result  # absence from the list is evidence, not proof


def test_fraud_watchlist_hit_lists_the_reason_and_report_count(monkeypatch):
    payload = {"found": True, "entries": [{"type": "phone", "value": "0900000001", "reason": "Giả danh nhân viên ngân hàng", "reports": 41}], "note": "n"}
    monkeypatch.setattr("tools.security_tools.httpx.get", _fake_get(payload))
    result = check_fraud_watchlist.invoke({"value": "0900000001"})
    assert "Giả danh nhân viên ngân hàng" in result and "41" in result


def test_fraud_watchlist_miss_never_claims_safe(monkeypatch):
    monkeypatch.setattr("tools.security_tools.httpx.get", _fake_get({"found": False, "entries": [], "note": "n"}))
    result = check_fraud_watchlist.invoke({"value": "0912345678"})
    assert "không có trong danh sách" in result
    assert "không đồng nghĩa với an toàn" in result


def test_promotions_lists_status_and_dates(monkeypatch):
    calls = []
    payload = {"items": [{"name": "Hoàn tiền ăn uống", "status": "active", "startDate": "2026-09-01", "endDate": "2026-10-31", "officialUrl": "https://www.msb.com.vn/x"}]}
    monkeypatch.setattr("tools.security_tools.httpx.get", _fake_get(payload, calls=calls))
    result = search_msb_promotions.invoke({"query": "hoàn tiền"})
    assert calls[0]["params"] == {"q": "hoàn tiền"}
    assert "Hoàn tiền ăn uống" in result and "đang diễn ra" in result and "2026-10-31" in result


def test_promotions_empty_says_not_found_in_the_list(monkeypatch):
    monkeypatch.setattr("tools.security_tools.httpx.get", _fake_get({"items": []}))
    assert "không tìm thấy" in search_msb_promotions.invoke({"query": "trúng thưởng"}).lower()


def test_tools_report_an_outage_instead_of_guessing(monkeypatch):
    def boom(url, params=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("tools.security_tools.httpx.get", boom)
    for result in (
        check_official_channel.invoke({"value": "x.com"}),
        check_fraud_watchlist.invoke({"value": "0912345678"}),
        search_msb_promotions.invoke({"query": "a"}),
    ):
        assert "không tra cứu được" in result.lower()

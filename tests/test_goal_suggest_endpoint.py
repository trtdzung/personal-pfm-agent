"""POST /goal-suggestions qua FastAPI TestClient (auth X-API-Key, 200/422)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from goal_suggest import service as goal_suggest_service
from goal_suggest.api import router
from goal_suggest.service import _LLMCard

app = FastAPI()
app.include_router(router)
client = TestClient(app)
HEADERS = {"X-API-Key": "test-key"}

PAYLOAD = {
    "user_id": "CIF_0001",
    "today": "2026-10-17",
    "customer": {
        "monthly_income": 20_000_000,
        "monthly_surplus": None,
        "salary_day": 5,
        "risk_profile": "balanced",
    },
    "goals": [],
    "signals": [
        {
            "id": "sig-x",
            "goal_id": None,
            "kind": "insufficient_data",
            "rank": 0,
            "facts": {"salary_day": 5},
            "allowed_actions": [{"id": "a0", "label": "Xem hướng dẫn"}],
            "fallback": {"title": "Chưa đủ dữ liệu", "body": "Cần thêm giao dịch."},
        }
    ],
    "feedback": [{"kind": "insufficient_data", "goal_id": None, "ignored_count": 0}],
}


@pytest.fixture(autouse=True)
def auth(monkeypatch):
    monkeypatch.setenv("SERVER_API_KEY", "test-key")


def _must_not_call_llm(*_):
    raise AssertionError("must not call llm")


def test_missing_api_key_rejected(monkeypatch):
    monkeypatch.setattr(goal_suggest_service, "generate_with_llm", _must_not_call_llm)
    assert client.post("/goal-suggestions", json=PAYLOAD).status_code == 401


def test_wrong_api_key_rejected():
    assert (
        client.post(
            "/goal-suggestions",
            json=PAYLOAD,
            headers={"X-API-Key": "wrong"},
        ).status_code
        == 401
    )


def test_invalid_body_returns_422(monkeypatch):
    monkeypatch.setattr(goal_suggest_service, "generate_with_llm", _must_not_call_llm)
    bad = {**PAYLOAD, "user_id": ""}
    result = client.post("/goal-suggestions", json=bad, headers=HEADERS)
    assert result.status_code == 422
    assert result.json()["error"] == "invalid_request"


def test_valid_payload_returns_200_with_mocked_llm(monkeypatch):
    def fake_generate(req, signals):
        return [
            _LLMCard(
                signal_id=s.id,
                title=f"Ngày lương {s.facts['salary_day']}",
                body="Bổ sung dữ liệu để gợi ý tốt hơn.",
                action_ids=[a.id for a in s.allowed_actions],
            )
            for s in signals
        ]

    monkeypatch.setattr(goal_suggest_service, "generate_with_llm", fake_generate)
    result = client.post("/goal-suggestions", json=PAYLOAD, headers=HEADERS)
    assert result.status_code == 200
    body = result.json()
    assert body["degraded"] is False
    assert len(body["suggestions"]) == 1
    assert body["suggestions"][0]["signal_id"] == "sig-x"
    assert body["suggestions"][0]["title"] == "Ngày lương 5"
    assert body["suggestions"][0]["action_ids"] == ["a0"]


def test_llm_failure_still_200_degraded(monkeypatch):
    def boom(*_):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(goal_suggest_service, "generate_with_llm", boom)
    result = client.post("/goal-suggestions", json=PAYLOAD, headers=HEADERS)
    assert result.status_code == 200
    body = result.json()
    assert body["degraded"] is True
    assert body["suggestions"][0]["title"] == "Chưa đủ dữ liệu"
    assert body["suggestions"][0]["action_ids"] == ["a0"]

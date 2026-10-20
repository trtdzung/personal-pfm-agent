"""POST /goal-suggestions through a FastAPI TestClient: auth, validation, error mapping."""

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from goal_suggest import api
from goal_suggest.contracts import GoalSuggestionResponse, Insight
from goal_suggest.data import DataUnavailable
from goal_suggest.digest import GoalAmbiguous, GoalNotFound

app = FastAPI()
app.include_router(api.router)
client = TestClient(app)
HEADERS = {"X-API-Key": "test-key"}
BODY = {"user_id": "CIF_0001", "goal_name": "Mua xe"}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("SERVER_API_KEY", "test-key")


def stub(monkeypatch, result):
    async def fake(req):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(api, "suggest", fake)


def test_auth(monkeypatch):
    assert client.post("/goal-suggestions", json=BODY).status_code == 401
    assert client.post("/goal-suggestions", json=BODY, headers={"X-API-Key": "nope"}).status_code == 401
    monkeypatch.delenv("SERVER_API_KEY")
    assert client.post("/goal-suggestions", json=BODY, headers=HEADERS).status_code == 503


@pytest.mark.parametrize("body", [{}, {"user_id": "CIF_0001"}, {"goal_name": "x"}, {"user_id": "", "goal_name": "x"}])
def test_invalid_requests_are_422(body):
    resp = client.post("/goal-suggestions", json=body, headers=HEADERS)
    assert resp.status_code == 422 and resp.json()["error"] == "invalid_request"


def test_malformed_json_is_422():
    resp = client.post("/goal-suggestions", content=b"{", headers={**HEADERS, "content-type": "application/json"})
    assert resp.status_code == 422


def test_the_insight_is_returned_as_is(monkeypatch):
    insight = Insight(goal_id="goal-1", goal_name="Mua xe", observation="o", suggestion="s", question="q?")
    stub(monkeypatch, GoalSuggestionResponse(insight=insight))
    resp = client.post("/goal-suggestions", json=BODY, headers=HEADERS)
    assert resp.status_code == 200 and resp.json()["insight"]["observation"] == "o" and resp.json()["degraded"] is False


def test_model_trouble_is_a_200_without_an_insight(monkeypatch):
    stub(monkeypatch, GoalSuggestionResponse(insight=None, reason="promise", degraded=True))
    resp = client.post("/goal-suggestions", json=BODY, headers=HEADERS)
    assert resp.status_code == 200 and resp.json() == {"insight": None, "fingerprint": None, "unchanged": False, "reason": "promise", "degraded": True}


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [(GoalNotFound("x"), 404, "goal_not_found"), (GoalAmbiguous("goal-1, goal-8"), 409, "goal_ambiguous"), (DataUnavailable("HTTPError"), 503, "data_unavailable")],
)
def test_errors_are_mapped(monkeypatch, error, status, code):
    stub(monkeypatch, error)
    resp = client.post("/goal-suggestions", json=BODY, headers=HEADERS)
    assert resp.status_code == status and resp.json()["error"] == code

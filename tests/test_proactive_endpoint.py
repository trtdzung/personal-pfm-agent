import copy
import pytest
from fastapi.testclient import TestClient
import proactive_endpoint as endpoint

client = TestClient(endpoint.app)
HEADERS = {"X-API-Key": "test-key"}
PAYMENT = {"id": "payment:next7", "topic": "payment", "priority": 0, "severity": "urgent",
           "confidence": "recorded", "facts": {"minimum_due": 500000}, "title": "Sắp đến hạn", "body": "Xem lịch trả."}
BODY = {"snapshot_id": "a" * 64, "snapshot": {"schemaVersion": "2.0", "asOf": "2026-09-15",
        "timezone": "Asia/Ho_Chi_Minh", "currency": "VND", "dataQuality": {"mode": "demo"},
        "accounts": [{"balance": 1000000}], "candidates": [PAYMENT]}}

@pytest.fixture(autouse=True)
def auth(monkeypatch):
    monkeypatch.setenv("SERVER_API_KEY", "test-key")
    monkeypatch.setenv("AI_PLATFORM_API_KEY", "model-key-for-tests")

def draft(**patch):
    return endpoint.ProactiveDraft(**{"candidate_id": PAYMENT["id"], "title": "Sắp đến hạn thanh toán",
                                    "body": "Xem lại lịch trả đã ghi nhận.", **patch})

def test_auth_and_empty_candidates_do_not_call_model(monkeypatch):
    monkeypatch.setattr(endpoint, "propose", lambda _: pytest.fail("must not call model"))
    assert client.post("/proactive-insights", json=BODY).status_code == 401
    empty = copy.deepcopy(BODY)
    empty["snapshot"]["candidates"] = []
    assert client.post("/proactive-insights", json=empty, headers=HEADERS).status_code == 422

@pytest.mark.parametrize("patch", [{"title": "Trả 5 triệu"}, {"body": "Lãi suất ５%"},
                                  {"body": "HTTPs://bad.example"}, {"candidate_id": "invented"}])
def test_rejects_ungrounded_copy(monkeypatch, patch):
    monkeypatch.setattr(endpoint, "propose", lambda _: draft(**patch))
    assert client.post("/proactive-insights", json=BODY, headers=HEADERS).status_code == 502

def test_priority_cannot_be_downgraded(monkeypatch):
    body = copy.deepcopy(BODY)
    body["snapshot"]["candidates"].append({**PAYMENT, "id": "investment", "topic": "investment", "priority": 3})
    monkeypatch.setattr(endpoint, "propose", lambda _: draft(candidate_id="investment"))
    assert client.post("/proactive-insights", json=body, headers=HEADERS).status_code == 502

def test_full_snapshot_stateless_prompt_and_model_configuration(monkeypatch):
    captured = {}
    monkeypatch.setattr(endpoint, "default_model", lambda *a, **kw: captured.update(model=kw))
    class Writer:
        def invoke(self, payload, config):
            captured.update(message=payload["messages"][0].content, config=config)
            return {"structured_response": draft()}
    def create(**kwargs):
        captured.update(agent=kwargs)
        return Writer()
    monkeypatch.setattr(endpoint, "create_agent", create)
    result = client.post("/proactive-insights", json=BODY, headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["snapshot_id"] == BODY["snapshot_id"]
    assert '"accounts"' in captured["message"] and '1000000' in captured["message"]
    assert captured["agent"]["tools"] == []
    assert "checkpointer" not in captured["agent"]
    assert "Few-shot" in captured["agent"]["system_prompt"]
    assert captured["model"]["timeout"] == 15

def test_provider_error_is_redacted(monkeypatch):
    def fail(_):
        raise RuntimeError("secret snapshot data")
    monkeypatch.setattr(endpoint, "propose", fail)
    result = client.post("/proactive-insights", json=BODY, headers=HEADERS)
    assert result.status_code == 503
    assert "secret" not in result.text

def test_payload_limits(monkeypatch):
    monkeypatch.setattr(endpoint, "propose", lambda _: pytest.fail("must not call model"))
    duplicate = copy.deepcopy(BODY)
    duplicate["snapshot"]["candidates"].append(PAYMENT)
    assert client.post("/proactive-insights", json=duplicate, headers=HEADERS).status_code == 422
    large = copy.deepcopy(BODY)
    large["snapshot"]["large"] = "x" * 350000
    assert client.post("/proactive-insights", json=large, headers=HEADERS).status_code == 422

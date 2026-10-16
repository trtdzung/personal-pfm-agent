import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

os.environ["SERVER_API_KEY"] = "test-key-for-pytest"

import server  # noqa: E402


class _ToolCapableFakeChatModel(FakeListChatModel):
    """FakeListChatModel that tolerates bind_tools (deepagents always binds
    its built-in filesystem tools regardless of tools=[], so any fake model
    used with create_deep_agent needs to support this call)."""

    def bind_tools(self, tools, **kwargs):
        return self


def test_health_endpoint_requires_no_auth():
    client = TestClient(server.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_rejects_missing_api_key():
    client = TestClient(server.app)
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_chat_endpoint_rejects_wrong_api_key():
    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_chat_endpoint_returns_answer_with_correct_api_key(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["Đây là câu trả lời giả."])
    fake_agent = server.build_agent(model=fake_model)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Tháng này tôi đã chi tiêu bao nhiêu?", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Đây là câu trả lời giả."
    assert body["thread_id"] == "t1"


def test_chat_endpoint_generates_thread_id_when_omitted(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["ok"])
    fake_agent = server.build_agent(model=fake_model)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert response.json()["thread_id"]  # non-empty, some generated id


def test_server_refuses_to_start_without_server_api_key():
    env = dict(os.environ)
    env.pop("SERVER_API_KEY", None)
    env.setdefault("OPENAI_API_KEY", "sk-test-dummy-value")
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", "import server"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "SERVER_API_KEY" in result.stderr


def test_chat_endpoint_masks_internal_error_details(monkeypatch):
    class _RaisingAgent:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("secret internal detail")

    monkeypatch.setattr(server, "agent", _RaisingAgent())

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 500
    assert "secret internal detail" not in response.text

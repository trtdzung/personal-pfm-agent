import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel, GenericFakeChatModel
from langchain_core.messages import AIMessage

os.environ["SERVER_API_KEY"] = "test-key-for-pytest"
os.environ["MEMORY_ID"] = "test-memory-id-for-pytest"
os.environ["USER_PREFERENCE_STRATEGY_ID"] = "test-strategy-id-for-pytest"
os.environ["AI_PLATFORM_API_KEY"] = "test-ai-platform-key-for-pytest"

import server  # noqa: E402
import tools.memory_tools as memory_tools  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402


class _ToolCapableFakeChatModel(FakeListChatModel):
    """FakeListChatModel that tolerates bind_tools (deepagents always binds
    its built-in filesystem tools regardless of tools=[], so any fake model
    used with create_deep_agent needs to support this call)."""

    def bind_tools(self, tools, **kwargs):
        return self


class _ToolCallingFakeChatModel(GenericFakeChatModel):
    """GenericFakeChatModel that tolerates bind_tools, for tests that need
    the fake model to actually emit a tool_calls-bearing AIMessage (plain
    FakeListChatModel/_ToolCapableFakeChatModel can only return canned text,
    never a real tool call)."""

    def bind_tools(self, tools, **kwargs):
        return self


class _FakeMemoryClient:
    """Records insert/search calls instead of hitting the real GreenNode
    Memory API -- used to test remember_preference/recall_preference without
    real GREENNODE_CLIENT_ID/SECRET or network access."""

    def __init__(self, search_response=None):
        self.insert_calls: list[dict] = []
        self.search_calls: list[dict] = []
        self.search_response = search_response or []

    def insert_memory_records_directly(self, *, id, namespace, request):
        self.insert_calls.append({"id": id, "namespace": namespace, "request": request})

    def search_memory_records(self, *, id, namespace, request):
        self.search_calls.append({"id": id, "namespace": namespace, "request": request})
        return self.search_response


def test_health_endpoint_requires_no_auth():
    client = TestClient(server.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_rejects_missing_api_key():
    client = TestClient(server.app)
    response = client.post("/chat", json={"message": "hi", "user_id": "CIF_0001"})
    assert response.status_code == 401


def test_chat_endpoint_rejects_wrong_api_key():
    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0001"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_chat_endpoint_rejects_missing_user_id():
    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 422


def test_chat_endpoint_returns_answer_with_correct_api_key(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["Đây là câu trả lời giả."])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Tháng này tôi đã chi tiêu bao nhiêu?", "user_id": "CIF_0001", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Đây là câu trả lời giả."
    assert body["thread_id"] == "t1"
    assert body["ui"] is None


def test_chat_endpoint_splits_ui_json_chart_block_into_ui_field(monkeypatch):
    chart_answer = (
        "Tháng này bạn chi nhiều nhất cho Mua sắm.\n\n"
        '```ui-json\n{"type": "chart", "chart_type": "pie", "title": "Chi tiêu theo danh mục", '
        '"labels": ["Mua sắm", "Ăn uống"], "series": [{"name": "VND", "data": [16280000, 10500000]}]}\n```'
    )
    fake_model = _ToolCapableFakeChatModel(responses=[chart_answer])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Phân tích chi tiêu theo danh mục giúp tôi.", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Tháng này bạn chi nhiều nhất cho Mua sắm."
    assert "```ui-json" not in body["answer"]
    assert body["ui"] == {
        "type": "chart",
        "chart_type": "pie",
        "title": "Chi tiêu theo danh mục",
        "labels": ["Mua sắm", "Ăn uống"],
        "series": [{"name": "VND", "data": [16280000, 10500000]}],
    }


def test_chat_endpoint_splits_ui_json_transfer_form_block_into_ui_field(monkeypatch):
    # No tool call to simulate anymore -- the skill now tells the model to
    # verify available credit itself by reading /customer_data.json
    # (read_file, already always bound), not via a dedicated tool.
    transfer_answer = (
        "Kỳ sao kê đến hạn 10/07/2026, mức thanh toán tối thiểu là 910.000đ.\n\n"
        '```ui-json\n{"type": "transfer_form", "recipient": "MSB Visa Signature", '
        '"account_number": "card_001", "amount": 910000, '
        '"note": "Thanh toan du no the ky sao ke den han 2026-07-10"}\n```'
    )
    fake_model = _ToolCapableFakeChatModel(responses=[transfer_answer])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Tôi nên trả nợ thẻ Visa Signature bao nhiêu?", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Kỳ sao kê đến hạn 10/07/2026, mức thanh toán tối thiểu là 910.000đ."
    assert "```ui-json" not in body["answer"]
    assert body["ui"] == {
        "type": "transfer_form",
        "recipient": "MSB Visa Signature",
        "account_number": "card_001",
        "amount": 910000,
        "note": "Thanh toan du no the ky sao ke den han 2026-07-10",
    }


def test_chat_endpoint_defaults_thread_id_to_user_id_when_omitted(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["ok"])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert response.json()["thread_id"] == "CIF_0001"


def test_chat_history_rejects_missing_api_key():
    client = TestClient(server.app)
    response = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"})
    assert response.status_code == 401


def test_chat_history_empty_for_unknown_thread(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["ok"])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.get(
        "/chat/history",
        params={"user_id": "CIF_0001", "thread_id": "never-chatted-before"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert response.json() == {"thread_id": "never-chatted-before", "messages": []}


def test_chat_history_returns_prior_turns_for_same_thread(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["reply 1", "reply 2"])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    client.post("/chat", json={"message": "hello", "user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
    client.post("/chat", json={"message": "how are you", "user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)

    response = client.get(
        "/chat/history",
        params={"user_id": "CIF_0001", "thread_id": "t1"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "t1"
    assert body["messages"] == [
        {"role": "user", "content": "hello", "ui": None},
        {"role": "assistant", "content": "reply 1", "ui": None},
        {"role": "user", "content": "how are you", "ui": None},
        {"role": "assistant", "content": "reply 2", "ui": None},
    ]


def test_chat_history_includes_ui_for_a_past_turn_that_had_a_chart(monkeypatch):
    chart_answer = (
        "Tháng này bạn chi nhiều nhất cho Mua sắm.\n\n"
        '```ui-json\n{"type": "chart", "chart_type": "pie", "title": "Chi tiêu theo danh mục", '
        '"labels": ["Mua sắm", "Ăn uống"], "series": [{"name": "VND", "data": [16280000, 10500000]}]}\n```'
    )
    fake_model = _ToolCapableFakeChatModel(responses=[chart_answer])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    client.post(
        "/chat",
        json={"message": "Phân tích chi tiêu theo danh mục giúp tôi.", "user_id": "CIF_0001", "thread_id": "t1"},
        headers=headers,
    )

    response = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
    assert response.status_code == 200
    messages = response.json()["messages"]
    assistant_message = next(m for m in messages if m["role"] == "assistant")
    assert assistant_message["content"] == "Tháng này bạn chi nhiều nhất cho Mua sắm."
    assert "```ui-json" not in assistant_message["content"]
    assert assistant_message["ui"] == {
        "type": "chart",
        "chart_type": "pie",
        "title": "Chi tiêu theo danh mục",
        "labels": ["Mua sắm", "Ăn uống"],
        "series": [{"name": "VND", "data": [16280000, 10500000]}],
    }


def test_chat_history_defaults_thread_id_to_user_id_when_omitted(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["ok"])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    # No thread_id on either call -- both must resolve to the same default
    # thread (== user_id) for the GET to find what the POST wrote.
    client.post("/chat", json={"message": "hello", "user_id": "CIF_0001"}, headers=headers)

    response = client.get("/chat/history", params={"user_id": "CIF_0001"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "CIF_0001"
    assert body["messages"] == [
        {"role": "user", "content": "hello", "ui": None},
        {"role": "assistant", "content": "ok", "ui": None},
    ]


def test_delete_chat_history_defaults_thread_id_to_user_id_when_omitted(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["ok"])
    tracking_saver = _DeleteTrackingSaver()
    fake_agent = server.build_agent(model=fake_model, checkpointer=tracking_saver)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    client.post("/chat", json={"message": "hello", "user_id": "CIF_0001"}, headers=headers)

    response = client.delete("/chat/history", params={"user_id": "CIF_0001"}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"thread_id": "CIF_0001", "status": "deleted"}
    assert ("CIF_0001", "CIF_0001") in tracking_saver.deleted_calls


def test_delete_chat_history_rejects_missing_api_key():
    client = TestClient(server.app)
    response = client.delete("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"})
    assert response.status_code == 401


class _DeleteTrackingSaver(InMemorySaver):
    """InMemorySaver that accepts the actor_id positional arg on delete_thread
    (InMemorySaver.delete_thread only takes thread_id -- AgentBaseMemoryEvents.
    delete_thread(thread_id, actor_id="") takes both, which is the real
    interface server.py's DELETE /chat/history calls against) and records
    what it was called with, then actually deletes so the follow-up GET can
    verify the history is really gone."""

    def __init__(self):
        super().__init__()
        self.deleted_calls: list[tuple[str, str]] = []

    def delete_thread(self, thread_id, actor_id=""):
        self.deleted_calls.append((thread_id, actor_id))
        super().delete_thread(thread_id)


def test_delete_chat_history_removes_thread(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["reply 1"])
    tracking_saver = _DeleteTrackingSaver()
    fake_agent = server.build_agent(model=fake_model, checkpointer=tracking_saver)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    client.post("/chat", json={"message": "hello", "user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)

    before = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
    assert before.json()["messages"]  # has history before delete

    response = client.delete("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"thread_id": "t1", "status": "deleted"}
    assert ("t1", "CIF_0001") in tracking_saver.deleted_calls

    after = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
    assert after.json()["messages"] == []  # gone after delete


class _ActorIdRecordingGetTupleSaver(InMemorySaver):
    """InMemorySaver that records the actor_id each get_state() lookup requested.

    Same caveat as _ActorIdRecordingSaver below: InMemorySaver itself has no
    notion of actor_id and does NOT scope reads by it -- real isolation on a
    shared thread_id across different users is guaranteed by
    AgentBaseMemoryEvents (verified directly against its source: it builds
    its cache/lookup key from thread_id + actor_id together), not by this
    fake. This wrapper only proves server.py forwards user_id into
    get_state()'s actor_id, the part that's actually our code's job.
    """

    def __init__(self):
        super().__init__()
        self.actor_ids_seen: list[str | None] = []

    def get_tuple(self, config):
        self.actor_ids_seen.append(config.get("configurable", {}).get("actor_id"))
        return super().get_tuple(config)


def test_chat_history_passes_user_id_as_actor_id(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["ok"])
    recording_saver = _ActorIdRecordingGetTupleSaver()
    fake_agent = server.build_agent(model=fake_model, checkpointer=recording_saver)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.get(
        "/chat/history",
        params={"user_id": "CIF_0002", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert "CIF_0002" in recording_saver.actor_ids_seen


class _ActorIdRecordingSaver(InMemorySaver):
    """InMemorySaver that records the actor_id each checkpoint was saved under.

    InMemorySaver itself only keys on thread_id -- it has no notion of
    actor_id (that's an AgentBaseMemoryEvents-specific configurable key). This
    wrapper exists purely to assert that server.py threads request.user_id
    into config["configurable"]["actor_id"] on every agent.invoke() call.
    """

    def __init__(self):
        super().__init__()
        self.actor_ids_seen: list[str | None] = []

    def put(self, config, checkpoint, metadata, new_versions):
        self.actor_ids_seen.append(config.get("configurable", {}).get("actor_id"))
        return super().put(config, checkpoint, metadata, new_versions)


def test_chat_endpoint_passes_user_id_as_actor_id(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["ok"])
    recording_saver = _ActorIdRecordingSaver()
    fake_agent = server.build_agent(model=fake_model, checkpointer=recording_saver)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0002", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert "CIF_0002" in recording_saver.actor_ids_seen


def test_remember_preference_tool_inserts_under_actor_namespace(monkeypatch):
    fake_memory_client = _FakeMemoryClient()
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    messages = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "remember_preference", "args": {"fact": "Ngân sách ăn uống: 2 triệu/tháng"}, "id": "call1"}],
            ),
            AIMessage(content="Đã ghi nhớ giúp bạn."),
        ]
    )
    fake_model = _ToolCallingFakeChatModel(messages=messages)
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "ngân sách ăn uống của tôi là 2 triệu/tháng", "user_id": "CIF_0001", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert len(fake_memory_client.insert_calls) == 1
    call = fake_memory_client.insert_calls[0]
    assert call["id"] == "test-memory-id-for-pytest"
    assert call["namespace"] == "/strategies/test-strategy-id-for-pytest/actors/CIF_0001"
    assert call["request"].memory_records == ["Ngân sách ăn uống: 2 triệu/tháng"]


def test_recall_preference_tool_searches_under_actor_namespace(monkeypatch):
    from types import SimpleNamespace

    fake_memory_client = _FakeMemoryClient(search_response=[SimpleNamespace(memory="Ngân sách ăn uống: 2 triệu/tháng")])
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    messages = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "recall_preference", "args": {"query": "ngân sách ăn uống"}, "id": "call1"}],
            ),
            AIMessage(content="Ngân sách ăn uống của bạn là 2 triệu/tháng."),
        ]
    )
    fake_model = _ToolCallingFakeChatModel(messages=messages)
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "ngân sách ăn uống của tôi là bao nhiêu?", "user_id": "CIF_0001", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert len(fake_memory_client.search_calls) == 1
    call = fake_memory_client.search_calls[0]
    assert call["id"] == "test-memory-id-for-pytest"
    assert call["namespace"] == "/strategies/test-strategy-id-for-pytest/actors/CIF_0001"
    assert call["request"].query == "ngân sách ăn uống"
    assert response.json()["answer"] == "Ngân sách ăn uống của bạn là 2 triệu/tháng."


def test_recall_preference_tool_reports_no_match(monkeypatch):
    fake_memory_client = _FakeMemoryClient(search_response=[])
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    messages = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "recall_preference", "args": {"query": "ngân sách"}, "id": "call1"}],
            ),
            AIMessage(content="ok"),
        ]
    )
    fake_model = _ToolCallingFakeChatModel(messages=messages)
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "ngân sách của tôi là bao nhiêu?", "user_id": "CIF_0001", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    tool_messages = [
        m for m in fake_agent.get_state({"configurable": {"thread_id": "t1", "actor_id": "CIF_0001"}}).values["messages"]
        if type(m).__name__ == "ToolMessage"
    ]
    assert any("Không tìm thấy" in m.content for m in tool_messages)


def test_server_refuses_to_start_without_user_preference_strategy_id():
    env = dict(os.environ)
    env.pop("USER_PREFERENCE_STRATEGY_ID", None)
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", "import server"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "USER_PREFERENCE_STRATEGY_ID" in result.stderr


def test_server_refuses_to_start_without_server_api_key():
    env = dict(os.environ)
    env.pop("SERVER_API_KEY", None)
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


def test_server_refuses_to_start_without_memory_id():
    env = dict(os.environ)
    env.pop("MEMORY_ID", None)
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", "import server"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "MEMORY_ID" in result.stderr


def test_server_refuses_to_start_without_ai_platform_api_key():
    env = dict(os.environ)
    env.pop("AI_PLATFORM_API_KEY", None)
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", "import server"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "AI_PLATFORM_API_KEY" in result.stderr


def test_chat_endpoint_masks_internal_error_details(monkeypatch):
    class _RaisingAgent:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("secret internal detail")

    monkeypatch.setattr(server, "agent", _RaisingAgent())

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 500
    assert "secret internal detail" not in response.text

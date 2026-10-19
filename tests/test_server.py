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

    def __init__(self, search_response=None, list_response=None):
        self.insert_calls: list[dict] = []
        self.search_calls: list[dict] = []
        self.list_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self.search_response = search_response or []
        self.list_response = list_response or []

    def insert_memory_records_directly(self, *, id, namespace, request):
        self.insert_calls.append({"id": id, "namespace": namespace, "request": request})

    def search_memory_records(self, *, id, namespace, request):
        self.search_calls.append({"id": id, "namespace": namespace, "request": request})
        return self.search_response

    def list_memory_records(self, *, id, namespace, limit=None):
        self.list_calls.append({"id": id, "namespace": namespace, "limit": limit})
        return self.list_response

    def delete_memory_record(self, *, id, memoryRecordId):
        self.delete_calls.append({"id": id, "memoryRecordId": memoryRecordId})


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


def test_chat_endpoint_strips_stray_foreign_script_from_the_answer_only(monkeypatch):
    answer = (
        "Chỉ lãi khoảng 2,1 triệu,远远 chưa đạt mục tiêu.\n\n"
        '```ui-json\n{"type": "transfer_form", "amount": 500000, "beneficiary_name": "Trần 明", '
        '"memo": "Trả nợ", "category": "housing", "beneficiary_id": null}\n```'
    )
    fake_model = _ToolCapableFakeChatModel(responses=[answer])
    monkeypatch.setattr(server, "agent", server.build_agent(model=fake_model, checkpointer=InMemorySaver()))

    response = TestClient(server.app).post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    body = response.json()
    assert body["answer"] == "Chỉ lãi khoảng 2,1 triệu, chưa đạt mục tiêu."
    if body["ui"] is not None:  # the ui block is validated elsewhere; whatever it carries is not rewritten
        assert body["ui"].get("beneficiary_name") == "Trần 明"


def test_chat_history_cleans_assistant_turns_but_never_rewrites_what_the_user_typed(monkeypatch):
    fake_model = _ToolCapableFakeChatModel(responses=["Trả全额nợ trước nhé."])
    monkeypatch.setattr(server, "agent", server.build_agent(model=fake_model, checkpointer=InMemorySaver()))
    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    client.post("/chat", json={"message": "Chuyển tiền cho 王明", "user_id": "CIF_0001", "thread_id": "t9"}, headers=headers)
    body = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t9"}, headers=headers).json()
    assert body["messages"][0]["content"] == "Chuyển tiền cho 王明"
    assert body["messages"][1]["content"] == "Trả nợ trước nhé."


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


def test_chat_endpoint_splits_ui_json_create_jar_block_into_ui_field(monkeypatch):
    jar_answer = (
        "Mình đề xuất hũ Ăn uống 3.000.000đ/tháng.\n\n"
        '```ui-json\n{"type": "create_jar", "jar_name": "Ăn uống", "allocation_amount": 3000000, "initial_balance": 1000000, '
        '"category_ids": ["dining", "groceries"], '
        '"reason": "Trung bình chi tiêu Ăn uống 3 tháng gần nhất là ~3.045.000đ/tháng"}\n```'
    )
    fake_model = _ToolCapableFakeChatModel(responses=[jar_answer])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Tạo giúp tôi 1 hũ ăn uống hợp lý.", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Mình đề xuất hũ Ăn uống 3.000.000đ/tháng."
    assert "```ui-json" not in body["answer"]
    assert body["ui"] == {
        "type": "create_jar",
        "jar_name": "Ăn uống",
        "allocation_amount": 3000000,
        "initial_balance": 1000000,
        "category_ids": ["dining", "groceries"],
        "reason": "Trung bình chi tiêu Ăn uống 3 tháng gần nhất là ~3.045.000đ/tháng",
    }


def test_chat_endpoint_splits_ui_json_rebalance_jars_block_into_ui_field(monkeypatch):
    rebalance_answer = (
        "Mình đề xuất chuyển 500.000đ từ hũ Ăn uống sang hũ Hưởng thụ; bạn xem lại rồi xác nhận nhé.\n\n"
        '```ui-json\n{"type": "rebalance_jars", "from_jar_id": "food", '
        '"allocations": [{"to_jar_id": "lifestyle", "amount": 500000}], '
        '"reason": "Khách muốn chuyển 500.000đ từ hũ Ăn uống sang hũ Hưởng thụ"}\n```'
    )
    body = _chat_with_summary_read_then(monkeypatch, rebalance_answer)  # the model read the jars this turn
    assert "```ui-json" not in body["answer"]
    assert body["ui"]["type"] == "rebalance_jars"
    assert body["ui"]["from_jar_id"] == "food"
    assert body["ui"]["allocations"] == [{"to_jar_id": "lifestyle", "amount": 500000}]


def test_chat_drops_a_rebalance_from_a_jar_that_was_never_in_the_summary(monkeypatch):
    invented = (
        "Mình đề xuất lấy từ hũ Dự phòng.\n\n"
        '```ui-json\n{"type": "rebalance_jars", "from_jar_id": "du-phong", '
        '"allocations": [{"to_jar_id": "food", "amount": 500000}], "reason": "x"}\n```'
    )
    body = _chat_with_summary_read_then(monkeypatch, invented)
    assert body["ui"] is None and "Dự phòng" in body["answer"]


_JAR_SUMMARY_FOR_GUARD = {
    "month": "2026-09",
    "casaBalance": 18000000,
    "unallocated": 13044000,
    "allocationHeadroom": 1000000,
    "jars": [
        {"id": "food", "label": "Ăn uống", "categoryIds": ["dining"], "budgetLimit": 4000000, "spent": 2187000, "remaining": 1813000, "spendable": 1813000, "overLimit": False},
        {"id": "lifestyle", "label": "Hưởng thụ", "categoryIds": ["entertainment"], "budgetLimit": 2500000, "spent": 1204000, "remaining": 1296000, "spendable": 1296000, "overLimit": False},
    ],
}


def _chat_with_summary_read_then(monkeypatch, final_answer: str, read_summary: bool = True):
    """Run /chat with a fake model that (optionally) calls get_jar_summary and then answers `final_answer`."""
    import httpx
    import tools.customer_data_tools as customer_data_tools

    def _fake_get(url, params=None, timeout=None):
        return httpx.Response(200, json=_JAR_SUMMARY_FOR_GUARD, request=httpx.Request("GET", url))

    monkeypatch.setattr(customer_data_tools.httpx, "get", _fake_get)
    replies = []
    if read_summary:
        replies.append(AIMessage(content="", tool_calls=[{"name": "get_jar_summary", "args": {}, "id": "call1"}]))
    replies.append(AIMessage(content=final_answer))
    fake_agent = server.build_agent(model=_ToolCallingFakeChatModel(messages=iter(replies)), checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)
    response = TestClient(server.app).post(
        "/chat",
        json={"message": "Tăng hũ ăn uống lên 4,2 triệu", "user_id": "CIF_0001", "thread_id": "guard"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    return response.json()


def _edit_jar_answer(jar_id: str) -> str:
    return (
        "Hũ Ăn uống tăng lên 4.200.000đ/tháng.\n\n"
        '```ui-json\n{"type": "edit_jar", "jar_id": "' + jar_id + '", "jar_name": "Ăn uống", '
        '"allocation_amount": 4200000, "reason": "Khách yêu cầu tăng hạn mức"}\n```'
    )


def test_chat_keeps_an_edit_jar_whose_jar_id_was_in_the_summary_read_this_turn(monkeypatch):
    body = _chat_with_summary_read_then(monkeypatch, _edit_jar_answer("food"))
    assert body["ui"]["type"] == "edit_jar" and body["ui"]["jar_id"] == "food"


def test_chat_drops_an_edit_jar_with_an_invented_jar_id_but_keeps_the_answer(monkeypatch):
    body = _chat_with_summary_read_then(monkeypatch, _edit_jar_answer("an-uong"))
    assert body["ui"] is None
    assert "4.200.000đ" in body["answer"] and "ui-json" not in body["answer"]


def test_chat_drops_an_edit_jar_when_the_model_never_read_the_summary_this_turn(monkeypatch):
    body = _chat_with_summary_read_then(monkeypatch, _edit_jar_answer("food"), read_summary=False)
    assert body["ui"] is None


def test_chat_endpoint_keeps_the_lead_sentence_for_a_valid_clarify_options_block(monkeypatch):
    # schema v4 (2026-09-23): the question lives in ui.question, but `answer` is no longer cleared -- the
    # model's short lead sentence outside the fence is kept so the customer sees both.
    leaky_answer = (
        "Bạn đang có 2 hũ tên gần giống nhau.\n\n"
        '```ui-json\n{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", '
        '"options": ["Hũ Ăn uống nhà", "Hũ Ăn uống ngoài"]}]}\n```'
    )
    fake_model = _ToolCapableFakeChatModel(responses=[leaky_answer])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Tăng hạn mức hũ ăn uống thêm 200 nghìn giúp tôi.", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Bạn đang có 2 hũ tên gần giống nhau."
    assert body["ui"] == {
        "type": "clarify_options",
        "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", "options": ["Hũ Ăn uống nhà", "Hũ Ăn uống ngoài"]}],
    }


def test_chat_endpoint_leaves_answer_alone_when_clarify_options_is_invalid(monkeypatch):
    # an invalid clarify_options is dropped like any other malformed ui -- `answer` is left exactly as the
    # model wrote it (server no longer clears `answer` for clarify_options at all, valid or not)
    bad_answer = (
        "Bạn muốn tăng hạn mức hũ nào?\n\n"
        '```ui-json\n{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", '
        '"options": ["Hũ Ăn uống nhà"]}]}\n```'  # only 1 option -- invalid
    )
    fake_model = _ToolCapableFakeChatModel(responses=[bad_answer])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Tăng hạn mức hũ ăn uống thêm 200 nghìn giúp tôi.", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    body = response.json()
    assert body["ui"] is None
    assert body["answer"] == "Bạn muốn tăng hạn mức hũ nào?"


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


def test_chat_history_keeps_the_lead_sentence_for_a_clarify_options_turn(monkeypatch):
    # schema v4: `content` in history is the model's actual lead sentence (not cleared to ""), same as
    # what /chat returned live for that turn.
    clarify_answer = (
        "Mình cần hỏi thêm để xác định đúng hũ.\n\n"
        '```ui-json\n{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", '
        '"options": ["Hũ Ăn uống nhà", "Hũ Ăn uống ngoài"]}]}\n```'
    )
    fake_model = _ToolCapableFakeChatModel(responses=[clarify_answer])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    client.post(
        "/chat",
        json={"message": "Tăng hạn mức hũ ăn uống thêm 200 nghìn giúp tôi.", "user_id": "CIF_0001", "thread_id": "t1"},
        headers=headers,
    )

    response = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
    messages = response.json()["messages"]
    assistant_message = next(m for m in messages if m["role"] == "assistant")
    assert assistant_message["content"] == "Mình cần hỏi thêm để xác định đúng hũ."
    assert assistant_message["ui"] == {
        "type": "clarify_options",
        "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", "options": ["Hũ Ăn uống nhà", "Hũ Ăn uống ngoài"]}],
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


def test_delete_chat_history_works_against_a_real_inmemorysaver_not_only_the_test_double():
    # Regression: server.py's default checkpointer (`checkpointer or MemorySaver()`) is a genuine
    # `InMemorySaver`, whose `delete_thread(self, thread_id)` takes ONE positional argument -- unlike
    # AgentBaseMemoryEvents.delete_thread(thread_id, actor_id=""), which takes two. `_DeleteTrackingSaver`
    # below happens to accept both, which let this bug hide behind green tests: the endpoint called
    # `checkpointer.delete_thread(thread_id, user_id)` unconditionally and crashed with a `TypeError`
    # (caught and turned into a 500) against the real class. Uses the real `InMemorySaver`, no subclass.
    fake_model = _ToolCapableFakeChatModel(responses=["reply 1"])
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    server_module_agent = server.agent
    server.agent = fake_agent
    try:
        client = TestClient(server.app)
        headers = {"X-API-Key": "test-key-for-pytest"}
        client.post("/chat", json={"message": "hello", "user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)

        before = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
        assert before.json()["messages"]  # has history before delete

        response = client.delete("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
        assert response.status_code == 200, response.text

        after = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": "t1"}, headers=headers)
        assert after.json()["messages"] == []  # really gone, not just a 200 with nothing deleted
    finally:
        server.agent = server_module_agent


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


# Seen in production logs: GreenNode's MaaS host randomly rejects the model's OWN generated text with 403
# ModelArts.81011 "Output text May contain sensitive information" -- a transient, non-deterministic filter on
# the provider side, not a bug in this repo (also seen firing during real-model test runs of unrelated
# jar-rebalance flows). Verified empirically (not assumed): by the time this exception is raised, the
# customer's message is already checkpointed and the model node is the only pending task (`state.next ==
# ("model",)`), so `agent.invoke(None, config=...)` safely RESUMES that turn instead of resending the
# message -- it never duplicates the customer's turn in the thread's history.
from langchain_core.exceptions import ModelPermissionDeniedError


class _ChatState:
    def __init__(self, next):
        self.next = next
        self.values = {}


def test_chat_endpoint_resumes_once_after_the_content_filter_and_succeeds(monkeypatch):
    class _RetryingAgent:
        checkpointer = None  # see test_chat_endpoint_masks_internal_error_details's comment
        calls = 0

        def invoke(self, input, config):
            self.calls += 1
            if self.calls == 1:
                assert input is not None, "the first call sends the customer's actual message"
                raise ModelPermissionDeniedError("Error code: 403 - ModelArts.81011 Output text May contain sensitive information")
            assert input is None, "the retry must RESUME the checkpoint, not resend the message"
            return {"messages": [AIMessage(content="Trả lời sau khi thử lại.")]}

        def get_state(self, config):
            return _ChatState(next=("model",))

    fake_agent = _RetryingAgent()
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "Trả lời sau khi thử lại."
    assert fake_agent.calls == 2


def test_chat_endpoint_returns_503_when_the_retry_is_rejected_too(monkeypatch):
    class _StillRaisingAgent:
        checkpointer = None
        calls = 0

        def invoke(self, input, config):
            self.calls += 1
            raise ModelPermissionDeniedError("Error code: 403 - ModelArts.81011 Output text May contain sensitive information")

        def get_state(self, config):
            return _ChatState(next=("model",))

    fake_agent = _StillRaisingAgent()
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 503
    assert "ModelArts" not in response.text and "81011" not in response.text  # never leak the provider's raw detail
    assert fake_agent.calls == 2, "exactly one retry -- never loop, so the customer isn't stuck waiting"


def test_chat_endpoint_gives_up_without_resuming_when_there_is_no_pending_task(monkeypatch):
    # defensive: if the checkpoint somehow has nothing pending to resume, invoke(None, ...) would be a
    # meaningless no-op call, not a real retry -- go straight to 503 instead.
    class _NothingPendingAgent:
        checkpointer = None
        resume_calls = 0

        def invoke(self, input, config):
            if input is None:
                self.resume_calls += 1
            raise ModelPermissionDeniedError("Error code: 403 - ModelArts.81011 Output text May contain sensitive information")

        def get_state(self, config):
            return _ChatState(next=())

    fake_agent = _NothingPendingAgent()
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi", "user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 503
    assert fake_agent.resume_calls == 0


def test_chat_endpoint_masks_internal_error_details(monkeypatch):
    class _RaisingAgent:
        # /chat reads agent.checkpointer (to invalidate the request-scoped
        # events cache) before it calls invoke(), so the fake has to expose
        # one or the handler dies on AttributeError instead of exercising
        # the error masking this test is about. None is fine:
        # checkpointer_cache.invalidate() is a no-op for anything that was
        # never patched.
        checkpointer = None

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


# --- GET/DELETE /memory/preferences: surface the GreenNode Long-Term Memory "User Preference" facts
# remember_preference wrote, so pfm can show the customer what the agent remembered about them (and let
# them delete one) -- previously there was no way to read this back except via the model's own
# recall_preference tool call. -------------------------------------------------------------------------


def test_memory_preferences_endpoint_lists_records_under_actor_namespace(monkeypatch):
    from types import SimpleNamespace

    fake_memory_client = _FakeMemoryClient(
        list_response=[
            SimpleNamespace(id="rec-1", memory="Ngân sách ăn uống: 2 triệu/tháng", created_at="2026-09-23T11:38:30Z"),
        ]
    )
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    client = TestClient(server.app)
    response = client.get(
        "/memory/preferences",
        params={"user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert len(fake_memory_client.list_calls) == 1
    call = fake_memory_client.list_calls[0]
    assert call["id"] == "test-memory-id-for-pytest"
    assert call["namespace"] == "/strategies/test-strategy-id-for-pytest/actors/CIF_0001"
    body = response.json()
    assert body == {
        "user_id": "CIF_0001",
        "records": [
            {"id": "rec-1", "fact": "Ngân sách ăn uống: 2 triệu/tháng", "created_at": "2026-09-23T11:38:30Z"},
        ],
    }


def test_memory_preferences_endpoint_returns_empty_list_when_nothing_remembered(monkeypatch):
    fake_memory_client = _FakeMemoryClient(list_response=[])
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    client = TestClient(server.app)
    response = client.get(
        "/memory/preferences",
        params={"user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert response.json()["records"] == []


def test_memory_preferences_endpoint_rejects_missing_api_key():
    client = TestClient(server.app)
    response = client.get("/memory/preferences", params={"user_id": "CIF_0001"})
    assert response.status_code == 401


def test_delete_memory_preference_endpoint_deletes_owned_record(monkeypatch):
    from types import SimpleNamespace

    fake_memory_client = _FakeMemoryClient(
        list_response=[SimpleNamespace(id="rec-1", memory="Ngân sách ăn uống: 2 triệu/tháng", created_at=None)]
    )
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    client = TestClient(server.app)
    response = client.delete(
        "/memory/preferences/rec-1",
        params={"user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert response.json() == {"user_id": "CIF_0001", "record_id": "rec-1", "status": "deleted"}
    assert fake_memory_client.delete_calls == [{"id": "test-memory-id-for-pytest", "memoryRecordId": "rec-1"}]


def test_delete_memory_preference_endpoint_rejects_record_not_owned_by_this_user(monkeypatch):
    # The GreenNode delete API itself takes no actor/namespace scoping param (just a global record id),
    # so without this check a caller could pass any user_id + any other customer's record_id and delete
    # it -- list first under the caller's OWN namespace and refuse if the id isn't in there.
    from types import SimpleNamespace

    fake_memory_client = _FakeMemoryClient(list_response=[SimpleNamespace(id="rec-1", memory="...", created_at=None)])
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    client = TestClient(server.app)
    response = client.delete(
        "/memory/preferences/rec-other-customers",
        params={"user_id": "CIF_0001"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 404
    assert fake_memory_client.delete_calls == []


def test_delete_memory_preference_endpoint_rejects_missing_api_key():
    client = TestClient(server.app)
    response = client.delete("/memory/preferences/rec-1", params={"user_id": "CIF_0001"})
    assert response.status_code == 401


def test_memory_preferences_endpoints_handle_dict_records_like_the_real_client(monkeypatch):
    # The real MemoryClient.list_memory_records returns plain dicts, not objects.
    fake_memory_client = _FakeMemoryClient(
        list_response=[
            {"id": "rec-1", "memory": "Khách hàng thích đá banh", "score": None, "created_at": "2026-10-14T06:25:36Z", "updated_at": None},
        ]
    )
    monkeypatch.setattr(memory_tools, "memory_client", fake_memory_client)

    client = TestClient(server.app)
    headers = {"X-API-Key": "test-key-for-pytest"}
    listed = client.get("/memory/preferences", params={"user_id": "CIF_0001"}, headers=headers)
    assert listed.json()["records"] == [
        {"id": "rec-1", "fact": "Khách hàng thích đá banh", "created_at": "2026-10-14T06:25:36Z"}
    ]

    deleted = client.delete("/memory/preferences/rec-1", params={"user_id": "CIF_0001"}, headers=headers)
    assert deleted.status_code == 200
    assert fake_memory_client.delete_calls == [{"id": "test-memory-id-for-pytest", "memoryRecordId": "rec-1"}]


# --- guardrails on /chat (guardrails.py): profanity in, sensitive data in, unsafe text out ----------------


def _chat(message, monkeypatch, responses=("Đây là câu trả lời giả.",)):
    fake_model = _ToolCapableFakeChatModel(responses=list(responses))
    fake_agent = server.build_agent(model=fake_model, checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", fake_agent)
    response = TestClient(server.app).post(
        "/chat",
        json={"message": message, "user_id": "CIF_0001", "thread_id": "guard"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    return response, fake_agent


def test_chat_with_profanity_gets_a_polite_reply_and_never_reaches_the_agent(monkeypatch):
    response, fake_agent = _chat("địt mẹ app này", monkeypatch)
    assert response.status_code == 200
    body = response.json()
    assert "lịch sự" in body["answer"]
    assert body["ui"] is None
    assert fake_agent.get_state(config={"configurable": {"thread_id": "guard"}}).values == {}


def test_chat_masks_sensitive_input_before_the_agent_sees_it_and_warns_the_customer(monkeypatch):
    response, fake_agent = _chat("mã OTP là 482913, giúp tôi xem số dư", monkeypatch)
    assert response.status_code == 200
    assert "không gửi" in response.json()["answer"].lower()
    stored = fake_agent.get_state(config={"configurable": {"thread_id": "guard"}}).values["messages"]
    assert "482913" not in " ".join(str(m.content) for m in stored)


def test_chat_replaces_an_answer_that_contains_profanity(monkeypatch):
    response, _ = _chat("hi", monkeypatch, responses=("Bạn là đồ chó đẻ",))
    assert "chó" not in response.json()["answer"]

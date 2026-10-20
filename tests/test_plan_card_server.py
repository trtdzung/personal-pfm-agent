"""The server attaches the plan card built by `build_goal_plan_card`; the model only writes the short text."""
import copy
import json

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from starlette.testclient import TestClient

from tests.test_goal_plan_tools import ARGS
from tests.test_server import _ToolCallingFakeChatModel, server

HEADERS = {"X-API-Key": "test-key-for-pytest"}
CARD_CALL = {"name": "build_goal_plan_card", "args": {"goal_name": "Căn hộ", "goal_id": "goal-1", **ARGS}, "id": "c1"}


def _goals_read(*goals):
    listed = goals or (("goal-1", "accumulating"),)
    artifact = {"today": "2026-10-21", "goals": [{"id": g, "status": s, "hasActiveLoan": False} for g, s in listed], "assets": []}
    return ToolMessage(content="x", tool_call_id="g", name="get_goals", artifact=artifact)


def _run(monkeypatch, final_text, *, goals=None, thread="plan"):
    monkeypatch.setattr(server, "_fresh_goals_read", lambda user_id: goals or _goals_read())
    replies = iter([AIMessage(content="", tool_calls=[CARD_CALL]), AIMessage(content=final_text)])
    monkeypatch.setattr(server, "agent", server.build_agent(model=_ToolCallingFakeChatModel(messages=replies), checkpointer=InMemorySaver()))
    client = TestClient(server.app)
    body = client.post("/chat", json={"message": "gợi ý lộ trình", "user_id": "CIF_0001", "thread_id": thread}, headers=HEADERS).json()
    history = client.get("/chat/history", params={"user_id": "CIF_0001", "thread_id": thread}, headers=HEADERS).json()
    return body, history


def test_the_card_is_attached_even_though_the_model_wrote_only_text(monkeypatch):
    body, history = _run(monkeypatch, "Bạn nên chọn phương án khuyến nghị.")
    assert body["answer"] == "Bạn nên chọn phương án khuyến nghị."
    assert body["ui"]["type"] == "plan_roadmap" and body["ui"]["goal_id"] == "goal-1"
    # a reload of the conversation shows the same card under the same answer
    assistant = [m for m in history["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1 and assistant[0]["content"] == "Bạn nên chọn phương án khuyến nghị." and assistant[0]["ui"] == body["ui"]


def test_a_card_the_model_pasted_and_edited_is_replaced_by_the_tools_card(monkeypatch):
    plain, _ = _run(monkeypatch, "Ok.", thread="a")
    edited = copy.deepcopy(plain["ui"])
    edited["plans"][0]["headline"] = "Đạt mục tiêu ở tháng 1, đúng hạn"
    body, _ = _run(monkeypatch, "Ok.\n```ui-json\n" + json.dumps(edited, ensure_ascii=False) + "\n```", thread="b")
    assert body["ui"] == plain["ui"]


def test_a_card_for_a_goal_the_customer_does_not_have_is_dropped_with_a_note(monkeypatch):
    body, history = _run(monkeypatch, "Ok.", goals=_goals_read(("goal-9", "accumulating")), thread="c")
    assert body["ui"] is None and "chưa hiện được" in body["answer"]


def test_the_chat_still_answers_when_the_openai_model_is_down_and_glm_takes_over(monkeypatch):
    import httpx
    import openai

    import llm
    from tests.test_server import _ToolCapableFakeChatModel

    class _Down(_ToolCapableFakeChatModel):
        def _generate(self, *args, **kwargs):
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))

    model = llm.FallbackChatModel(primary=_Down(responses=["x"]), fallback=_ToolCapableFakeChatModel(responses=["Trả lời từ GLM."]))
    monkeypatch.setattr(server, "agent", server.build_agent(model=model, checkpointer=InMemorySaver()))
    response = TestClient(server.app).post("/chat", json={"message": "xin chào", "user_id": "CIF_0001", "thread_id": "fb"}, headers=HEADERS)
    assert response.status_code == 200 and response.json()["answer"] == "Trả lời từ GLM."

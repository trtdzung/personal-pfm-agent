"""/chat end to end for the goal forms: a fake model reads the goal tools, then answers with a ui-json block."""

import json
import os
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

os.environ["SERVER_API_KEY"] = "test-key-for-pytest"
os.environ["MEMORY_ID"] = "test-memory-id-for-pytest"
os.environ["USER_PREFERENCE_STRATEGY_ID"] = "test-strategy-id-for-pytest"
os.environ["AI_PLATFORM_API_KEY"] = "test-ai-platform-key-for-pytest"

import server  # noqa: E402
from tests.test_server import _ToolCallingFakeChatModel  # noqa: E402

WORLD = json.loads((Path(__file__).parent / "data" / "goals_v2_world.json").read_text(encoding="utf-8"))
HEADERS = {"X-API-Key": "test-key-for-pytest"}


def _fake_get(url, params=None, timeout=None):
    request = httpx.Request("GET", url)
    if url.endswith("/api/goals-v2"):
        return httpx.Response(200, json=WORLD, request=request)
    if url.endswith("/api/clock"):
        return httpx.Response(200, json={"today": "2026-09-15"}, request=request)
    raise httpx.ConnectError("not mocked", request=request)


def _chat(monkeypatch, reads: list[str], final: str, message="x"):
    monkeypatch.setattr(httpx, "get", _fake_get)
    replies = []
    if reads:
        replies.append(AIMessage(content="", tool_calls=[{"name": n, "args": {}, "id": f"c{i}"} for i, n in enumerate(reads)]))
    replies.append(AIMessage(content=final))
    agent = server.build_agent(model=_ToolCallingFakeChatModel(messages=iter(replies)), checkpointer=InMemorySaver())
    monkeypatch.setattr(server, "agent", agent)
    response = TestClient(server.app).post("/chat", json={"message": message, "user_id": "CIF_0001", "thread_id": "goal"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _block(ui: dict, lead="Mình đề xuất, bạn xem lại rồi xác nhận nhé.") -> str:
    return lead + "\n\n```ui-json\n" + json.dumps(ui, ensure_ascii=False) + "\n```"


CREATE = {"type": "create_goal", "goal_name": "Du lịch", "template": "travel", "target_amount": 30000000, "target_date": "2027-03-15",
          "flexibility": "date_flexible", "initial_deposit": 0, "reason": "Khách muốn đi du lịch"}
EDIT = {"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "new_target_date": "2028-03-31", "reason": "Khách muốn lùi hạn"}
ADD = {"type": "add_asset", "goal_id": "goal-1", "category": "stock", "asset_name": "Cổ phiếu ACB", "instrument_id": "stock-acb", "quantity": 500,
       "count_percent": 100, "reason": "Khách khai"}


def test_create_goal_is_returned_as_ui_when_get_goals_was_read(monkeypatch):
    body = _chat(monkeypatch, ["get_goals"], _block(CREATE))
    assert body["ui"] == CREATE and "ui-json" not in body["answer"]


def test_create_goal_with_a_date_not_after_the_systems_today_is_dropped(monkeypatch):
    body = _chat(monkeypatch, ["get_goals"], _block({**CREATE, "target_date": "2026-09-15"}))
    assert body["ui"] is None and "Mình đề xuất" in body["answer"]


def test_a_form_without_reading_the_goals_this_turn_is_dropped(monkeypatch):
    assert _chat(monkeypatch, [], _block(CREATE))["ui"] is None


def test_edit_goal_with_a_real_goal_id_passes_and_an_invented_one_is_dropped(monkeypatch):
    assert _chat(monkeypatch, ["get_goals"], _block(EDIT))["ui"] == EDIT
    assert _chat(monkeypatch, ["get_goals"], _block({**EDIT, "goal_id": "mua-xe"}))["ui"] is None


def test_add_asset_by_market_code_needs_the_market_read_this_turn(monkeypatch):
    assert _chat(monkeypatch, ["get_goals", "get_goal_market"], _block(ADD))["ui"] == ADD
    assert _chat(monkeypatch, ["get_goals"], _block(ADD))["ui"] is None
    assert _chat(monkeypatch, ["get_goals", "get_goal_market"], _block({**ADD, "instrument_id": "stock-xyz"}))["ui"] is None


def test_a_malformed_goal_form_is_dropped_by_the_shape_check_first(monkeypatch):
    body = _chat(monkeypatch, ["get_goals"], _block({**CREATE, "template": "boat"}))
    assert body["ui"] is None and "Mình đề xuất" in body["answer"]


def test_a_failed_read_leaves_no_form(monkeypatch):
    def broken(url, params=None, timeout=None):
        raise httpx.ConnectError("down", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", broken)
    agent = server.build_agent(
        model=_ToolCallingFakeChatModel(messages=iter([AIMessage(content="", tool_calls=[{"name": "get_goals", "args": {}, "id": "c"}]), AIMessage(content=_block(CREATE))])),
        checkpointer=InMemorySaver(),
    )
    monkeypatch.setattr(server, "agent", agent)
    body = TestClient(server.app).post("/chat", json={"message": "x", "user_id": "CIF_0001", "thread_id": "g2"}, headers=HEADERS).json()
    assert body["ui"] is None

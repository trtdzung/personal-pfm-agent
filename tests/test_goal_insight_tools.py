import copy
import json
from pathlib import Path

import httpx
from langchain_core.runnables.config import var_child_runnable_config

import tools.goal_insight_tools as git

FIXTURE = json.loads((Path(__file__).parent / "data" / "goals_v2_world.json").read_text(encoding="utf-8"))
CARD = {"observation": "Tài khoản mục tiêu có 5.000.000 VND nằm yên.", "suggestion": "Gửi tiết kiệm MSB 12 tháng.", "question": "Mình nên gửi tiết kiệm MSB thế nào?"}


def call(args=None, actor_id="CIF_0001"):
    token = var_child_runnable_config.set({"configurable": {"actor_id": actor_id}})
    try:
        return git.get_goal_insight.invoke({"name": "get_goal_insight", "args": args or {}, "id": "1", "type": "tool_call"})
    finally:
        var_child_runnable_config.reset(token)


def serve(monkeypatch, card=CARD):
    raw = {"snapshot": copy.deepcopy(FIXTURE), "jars": None, "accounts": None, "transactions": None, "categories": None, "preferences": None}
    monkeypatch.setattr(git.data, "collect", lambda cif: raw)
    monkeypatch.setattr(git, "stored_card", lambda cif, goal_id: card)


def test_the_chat_gets_the_card_the_customer_saw_and_the_figures_it_was_written_from(monkeypatch):
    serve(monkeypatch)
    result = call({"goal": "goal-1"})
    assert result.content.startswith("== THẺ M-YOU GỢI Ý ĐÃ HIỆN CHO KHÁCH")
    assert CARD["observation"] in result.content and CARD["question"] in result.content
    assert "== MỤC TIÊU ĐANG XÉT ==" in result.content and "== ĐIỂM ĐÁNG CHÚ Ý ĐÃ XÉT SẴN" in result.content
    assert result.artifact["goalId"] == "goal-1" and result.artifact["card"] == CARD


def test_a_goal_can_be_named_and_a_single_goal_needs_no_name(monkeypatch):
    serve(monkeypatch)
    assert call({"goal": "mua xe"}).artifact["goalId"] == "goal-1"
    assert call().artifact["goalId"] == "goal-1"


def test_without_a_stored_card_the_data_is_still_given(monkeypatch):
    serve(monkeypatch, card=None)
    result = call({"goal": "goal-1"})
    assert "Chưa có thẻ nào được lưu" in result.content and "== MỤC TIÊU ĐANG XÉT ==" in result.content and result.artifact["card"] is None


def test_unknown_or_ambiguous_goals_ask_instead_of_guessing(monkeypatch):
    serve(monkeypatch)
    missing = call({"goal": "goal-99"})
    assert missing.artifact is None and "đừng đoán" in missing.content
    monkeypatch.setattr(git.digest, "build_full", lambda *a, **k: (_ for _ in ()).throw(git.digest.GoalAmbiguous("goal-1, goal-8")))
    assert "nhiều mục tiêu" in call({"goal": "xe"}).content.lower()


def test_pfm_down_says_so_and_gives_no_artifact(monkeypatch):
    def boom(cif):
        raise git.data.DataUnavailable("HTTPError")

    monkeypatch.setattr(git.data, "collect", boom)
    result = call({"goal": "goal-1"})
    assert result.artifact is None and "đừng đoán" in result.content.lower()


def test_stored_card_reads_the_peek_endpoint_and_survives_failures(monkeypatch):
    seen = []

    def fake_get(url, params=None, timeout=None):
        seen.append((url, params))
        return httpx.Response(200, json={"insight": CARD, "refreshing": False}, request=httpx.Request("GET", url))

    monkeypatch.setattr(git.httpx, "get", fake_get)
    assert git.stored_card("CIF_0001", "goal-1") == CARD
    assert seen[0][0].endswith("/api/goals-v2/insight") and seen[0][1] == {"cif": "CIF_0001", "goalId": "goal-1", "peek": "1"}

    def down(url, params=None, timeout=None):
        raise httpx.ConnectError("x")

    monkeypatch.setattr(git.httpx, "get", down)
    assert git.stored_card("CIF_0001", "goal-1") is None


def test_two_goals_with_one_name_are_told_apart_by_the_deadline(monkeypatch):
    serve(monkeypatch)
    raw = git.data.collect("x")
    twin = copy.deepcopy(raw["snapshot"]["world"]["goals"][0])
    twin.update(id="goal-77", targetDate="2031-09-15")
    raw["snapshot"]["world"]["goals"].append(twin)
    monkeypatch.setattr(git.data, "collect", lambda cif: raw)
    assert call({"goal": "Mua xe hạn 15/09/2031"}).artifact["goalId"] == "goal-77"
    assert call({"goal": "Mua xe"}).artifact is None  # still ambiguous: the answer lists both ids and deadlines
    lines = call({"goal": "Mua xe"}).content
    assert "goal-1" in lines and "goal-77" in lines and "15/09/2031" in lines and "gọi lại với đúng id" in lines

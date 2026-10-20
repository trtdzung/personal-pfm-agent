import copy

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.test_goal_plan_card import FEASIBLE
from tools.goal_plan_card import build_card
from ui_guard import TurnFacts, read_turn_facts, ui_matches_facts

CARD = build_card(FEASIBLE, "Căn hộ 1,2 tỷ", "goal-1")


def _goals_msg(*goals):
    """The `get_goals` read of the turn (artifact shape of tools/goal_tools.py `summarize_goals`)."""
    listed = goals or (("goal-1", "accumulating"),)
    artifact = {"today": "2026-10-21", "goals": [{"id": gid, "status": status, "hasActiveLoan": False} for gid, status in listed], "assets": []}
    return ToolMessage(content="x", tool_call_id="g", name="get_goals", artifact=artifact)


def _turn(*tool_msgs):
    return [HumanMessage(content="lộ trình?"), AIMessage(content=""), *tool_msgs]


def _card_msg(artifact=CARD, i="1"):
    return ToolMessage(content="x", tool_call_id=i, name="build_goal_plan_card", artifact=artifact)


def test_a_card_without_the_tool_call_is_refused():
    facts = read_turn_facts(_turn())
    assert facts.plan_cards is None
    assert not ui_matches_facts(copy.deepcopy(CARD), facts)
    assert not ui_matches_facts(copy.deepcopy(CARD), TurnFacts(jar_summary=None, expense_category_ids=None))


def test_the_block_equal_to_the_tool_artifact_is_accepted():
    facts = read_turn_facts(_turn(_goals_msg(), _card_msg()))
    assert ui_matches_facts(copy.deepcopy(CARD), facts)


def test_one_edited_number_is_refused():
    facts = read_turn_facts(_turn(_goals_msg(), _card_msg()))
    edited = copy.deepcopy(CARD)
    edited["plans"][1]["metrics"][0]["value"] = "1 triệu"
    assert not ui_matches_facts(edited, facts)
    edited = copy.deepcopy(CARD)
    edited["plans"][0]["verdict"] = "recommended"
    assert not ui_matches_facts(edited, facts)


def test_any_card_built_this_turn_is_accepted_but_not_last_turns():
    other = build_card(FEASIBLE, "Xe", "goal-1")
    facts = read_turn_facts(_turn(_goals_msg(), _card_msg(CARD, "1"), _card_msg(other, "2")))
    assert ui_matches_facts(CARD, facts) and ui_matches_facts(other, facts)
    old = [HumanMessage(content="a"), _card_msg(), AIMessage(content="ok"), HumanMessage(content="b")]
    assert not ui_matches_facts(copy.deepcopy(CARD), read_turn_facts(old))


def test_a_failed_tool_call_gives_no_card():
    facts = read_turn_facts(_turn(ToolMessage(content="Tham số không hợp lệ", tool_call_id="1", name="build_goal_plan_card", artifact=None)))
    assert facts.plan_cards is None and not ui_matches_facts(copy.deepcopy(CARD), facts)


def test_the_goal_must_be_one_the_customer_really_has():
    card_msg = _card_msg()
    unknown = read_turn_facts(_turn(_goals_msg(("goal-9", "accumulating")), card_msg))
    assert not ui_matches_facts(copy.deepcopy(CARD), unknown)
    closed = read_turn_facts(_turn(_goals_msg(("goal-1", "closed")), card_msg))
    assert not ui_matches_facts(copy.deepcopy(CARD), closed)
    never_read = read_turn_facts(_turn(card_msg))
    assert not ui_matches_facts(copy.deepcopy(CARD), never_read)


def test_a_card_from_a_turn_that_skipped_get_goals_is_kept_when_a_fresh_read_has_the_goal(monkeypatch):
    import os

    for key, value in (("SERVER_API_KEY", "k"), ("MEMORY_ID", "m"), ("USER_PREFERENCE_STRATEGY_ID", "s"), ("AI_PLATFORM_API_KEY", "a")):
        os.environ.setdefault(key, value)
    import server

    messages = _turn(_card_msg())
    monkeypatch.setattr(server, "_fresh_goals_read", lambda user_id: _goals_msg(("goal-1", "accumulating")))
    assert server._ui_matches_turn(copy.deepcopy(CARD), messages, "CIF_0001")
    monkeypatch.setattr(server, "_fresh_goals_read", lambda user_id: _goals_msg(("goal-9", "accumulating")))
    assert not server._ui_matches_turn(copy.deepcopy(CARD), messages, "CIF_0001")
    monkeypatch.setattr(server, "_fresh_goals_read", lambda user_id: None)
    assert not server._ui_matches_turn(copy.deepcopy(CARD), messages, "CIF_0001")

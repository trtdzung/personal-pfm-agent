import copy

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.test_goal_plan_card import FEASIBLE
from tools.goal_plan_card import build_card
from ui_guard import TurnFacts, read_turn_facts, ui_matches_facts

CARD = build_card(FEASIBLE, "Căn hộ 1,2 tỷ")


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
    facts = read_turn_facts(_turn(_card_msg()))
    assert ui_matches_facts(copy.deepcopy(CARD), facts)


def test_one_edited_number_is_refused():
    facts = read_turn_facts(_turn(_card_msg()))
    edited = copy.deepcopy(CARD)
    edited["plans"][1]["metrics"][0]["value"] = "1 triệu"
    assert not ui_matches_facts(edited, facts)
    edited = copy.deepcopy(CARD)
    edited["plans"][0]["verdict"] = "recommended"
    assert not ui_matches_facts(edited, facts)


def test_any_card_built_this_turn_is_accepted_but_not_last_turns():
    other = build_card(FEASIBLE, "Xe")
    facts = read_turn_facts(_turn(_card_msg(CARD, "1"), _card_msg(other, "2")))
    assert ui_matches_facts(CARD, facts) and ui_matches_facts(other, facts)
    old = [HumanMessage(content="a"), _card_msg(), AIMessage(content="ok"), HumanMessage(content="b")]
    assert not ui_matches_facts(copy.deepcopy(CARD), read_turn_facts(old))


def test_a_failed_tool_call_gives_no_card():
    facts = read_turn_facts(_turn(ToolMessage(content="Tham số không hợp lệ", tool_call_id="1", name="build_goal_plan_card", artifact=None)))
    assert facts.plan_cards is None and not ui_matches_facts(copy.deepcopy(CARD), facts)

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tools.goal_tools import market_list, summarize_goals
from ui_guard import TurnFacts, read_turn_facts, ui_matches_facts

WORLD = json.loads((Path(__file__).parent / "data" / "goals_v2_world.json").read_text(encoding="utf-8"))
GOALS = summarize_goals(WORLD)
MARKET = {i["id"]: i for i in market_list(WORLD)}
FACTS = TurnFacts(jar_summary=None, expense_category_ids=None, goals=GOALS, market=MARKET)


def _goal(**changes):
    return {**GOALS, "goals": [{**GOALS["goals"][0], **changes}]}


def _facts(goals=GOALS):
    return TurnFacts(jar_summary=None, expense_category_ids=None, goals=goals, market=MARKET)


def test_facts_come_from_the_goal_tools_of_this_turn_only():
    old = [HumanMessage(content="a"), ToolMessage(content="x", tool_call_id="1", name="get_goals", artifact=GOALS), AIMessage(content="ok")]
    new = [*old, HumanMessage(content="b"), ToolMessage(content="m", tool_call_id="2", name="get_goal_market", artifact=list(MARKET.values()))]
    facts = read_turn_facts(new)
    assert facts.goals is None and set(facts.market) == set(MARKET)
    assert read_turn_facts(old[:2]).goals == GOALS


CREATE = {"type": "create_goal", "goal_name": "Du lịch", "template": "travel", "target_amount": 30000000, "target_date": "2027-03-01",
          "flexibility": "date_flexible", "initial_deposit": 0, "reason": "x"}
EDIT = {"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "new_target_date": "2028-01-31", "reason": "x"}
CLOSE = {"type": "close_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "reason": "x"}
ASSET = {"type": "add_asset", "goal_id": "goal-1", "category": "stock", "asset_name": "ACB", "instrument_id": "stock-acb", "quantity": 100, "count_percent": 100, "reason": "x"}
EDIT_ASSET = {"type": "edit_asset", "asset_id": "asset-4", "asset_name": "Xe máy", "change": "revalue", "value": 1, "reason": "x"}


def test_every_goal_form_is_refused_when_get_goals_was_not_read_this_turn():
    nothing = TurnFacts(jar_summary=None, expense_category_ids=None)
    for ui in (CREATE, EDIT, CLOSE, ASSET, EDIT_ASSET):
        assert not ui_matches_facts(ui, nothing), ui["type"]


def test_the_forms_that_match_what_was_read_pass():
    for ui in (CREATE, EDIT, CLOSE, ASSET, EDIT_ASSET):
        assert ui_matches_facts(ui, FACTS), ui["type"]


def test_create_goal_date_must_be_after_the_systems_today_not_the_real_one():
    assert ui_matches_facts({**CREATE, "target_date": "2026-09-16"}, FACTS)
    assert not ui_matches_facts({**CREATE, "target_date": "2026-09-15"}, FACTS)


def test_edit_and_close_need_a_known_goal_in_a_changeable_state():
    assert not ui_matches_facts({**EDIT, "goal_id": "goal-9"}, FACTS)
    assert not ui_matches_facts({**CLOSE, "goal_id": "mua-xe"}, FACTS)
    for status in ("closed", "completed"):
        assert not ui_matches_facts(EDIT, _facts(_goal(status=status))), status
    assert not ui_matches_facts({**EDIT, "new_target_date": "2026-09-15"}, FACTS)
    assert ui_matches_facts({k: v for k, v in EDIT.items() if k != "new_target_date"} | {"new_target_amount": 5}, FACTS)


def test_a_goal_with_an_open_loan_cannot_be_closed():
    assert not ui_matches_facts(CLOSE, _facts(_goal(hasActiveLoan=True)))
    assert not ui_matches_facts(CLOSE, _facts(_goal(status="closed")))


def test_add_asset_needs_a_known_goal_and_a_market_instrument_of_the_right_kind():
    assert not ui_matches_facts({**ASSET, "goal_id": "goal-9"}, FACTS)
    assert not ui_matches_facts({**ASSET, "instrument_id": "stock-xyz"}, FACTS)
    assert not ui_matches_facts({**ASSET, "category": "gold"}, FACTS)  # ACB is a stock
    assert not ui_matches_facts({**ASSET, "quantity": 1.5}, FACTS)  # shares come whole
    gold = {**ASSET, "category": "gold", "instrument_id": "gold-ring", "quantity": 1.5}
    assert ui_matches_facts(gold, FACTS)  # gold is sold by the fraction of a chỉ
    hand = {"type": "add_asset", "goal_id": "goal-1", "category": "house", "asset_name": "Nhà", "value": 1, "count_percent": 50, "reason": "x"}
    assert ui_matches_facts(hand, FACTS)
    assert not ui_matches_facts(hand, _facts(_goal(status="closed")))


def test_edit_asset_checks_the_asset_and_what_can_be_changed_on_it():
    assert not ui_matches_facts({**EDIT_ASSET, "asset_id": "asset-99"}, FACTS)
    assert not ui_matches_facts({**EDIT_ASSET, "asset_id": "asset-5"}, FACTS)  # gold is priced by the market: a typed value is overwritten
    assert not ui_matches_facts({**EDIT_ASSET, "asset_id": "asset-4", "change": "quantity", "quantity": 2}, FACTS)  # a motorbike has no quantity
    assert ui_matches_facts({"type": "edit_asset", "asset_id": "asset-6", "asset_name": "ACB", "change": "quantity", "quantity": 1500, "reason": "x"}, FACTS)
    assert not ui_matches_facts({"type": "edit_asset", "asset_id": "asset-6", "asset_name": "ACB", "change": "quantity", "quantity": 1500.5, "reason": "x"}, FACTS)
    assert ui_matches_facts({"type": "edit_asset", "asset_id": "asset-7", "asset_name": "VCB", "change": "remove", "reason": "x"}, FACTS)


def test_msb_products_cannot_be_changed_in_chat():
    world = json.loads(json.dumps(WORLD))
    world["world"]["assets"].append({"id": "asset-9", "goalId": "goal-1", "type": "msb", "category": "term_deposit", "productId": "td", "name": "TK MSB",
                                     "costBasis": 1, "value": 10, "valuationDate": "2026-09-15", "countPercent": 100, "source": "msb", "status": "held", "createdAt": "2026-09-01"})
    facts = _facts(summarize_goals(world))
    assert not ui_matches_facts({"type": "edit_asset", "asset_id": "asset-9", "asset_name": "TK MSB", "change": "remove", "reason": "x"}, facts)

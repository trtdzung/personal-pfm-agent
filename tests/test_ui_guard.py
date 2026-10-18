"""The server-side check of a `ui` against what the agent actually READ this turn (ui_guard.py).

backend_docs/pfm-read-api.md C2 found the model inventing a `jar_id` ("lien-thien", derived from a jar name)
and offering categories the customer does not have. The shape validators in text_utils cannot see that; only
the tool results of the current turn can."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ui_guard import TurnFacts, read_turn_facts, ui_matches_facts

SUMMARY = {
    "month": "2026-09",
    "casaBalance": 18000000,
    "unallocated": 13044000,
    "allocationHeadroom": 1000000,
    "jars": [
        {"id": "food", "label": "Ăn uống", "categoryIds": ["dining"], "budgetLimit": 4000000, "spent": 2187000, "remaining": 1813000, "spendable": 1813000, "overLimit": False},
        {"id": "lifestyle", "label": "Hưởng thụ", "categoryIds": ["entertainment"], "budgetLimit": 2500000, "spent": 1204000, "remaining": 1296000, "spendable": 1296000, "overLimit": False},
    ],
}
CATEGORIES = [
    {"id": "dining", "label": "Ăn uống ngoài", "kind": "expense", "fixed": True},
    {"id": "c_cafe", "label": "Cà phê", "kind": "expense", "fixed": False},
    {"id": "transfer", "label": "Chuyển khoản", "kind": "transfer", "fixed": True},
]


def _tool_message(name: str, artifact) -> ToolMessage:
    return ToolMessage(content="...", name=name, tool_call_id=f"id-{name}", artifact=artifact)


def _facts(summary=SUMMARY, categories=None) -> TurnFacts:
    return TurnFacts(jar_summary=summary, expense_category_ids=categories)


# --- read_turn_facts ------------------------------------------------------------------------------


def test_read_turn_facts_takes_the_artifacts_of_the_current_turn():
    messages = [
        HumanMessage("Tăng hũ ăn uống"),
        AIMessage("", tool_calls=[{"name": "get_jar_summary", "args": {}, "id": "1"}]),
        _tool_message("get_jar_summary", SUMMARY),
        _tool_message("get_categories", CATEGORIES),
        AIMessage("xong"),
    ]
    facts = read_turn_facts(messages)
    assert facts.jar_summary == SUMMARY
    assert facts.expense_category_ids == {"dining", "c_cafe"}  # the "transfer" kind is a system entry, not for jars


def test_read_turn_facts_ignores_what_an_earlier_turn_read():
    messages = [
        HumanMessage("turn 1"),
        _tool_message("get_jar_summary", SUMMARY),
        AIMessage("đề xuất tạo hũ mới"),
        HumanMessage("turn 2: sửa hũ đó"),
        AIMessage("không đọc lại gì"),
    ]
    facts = read_turn_facts(messages)
    assert facts.jar_summary is None and facts.expense_category_ids is None


def test_read_turn_facts_takes_the_latest_read_when_a_tool_ran_twice_in_one_turn():
    older = {**SUMMARY, "jars": SUMMARY["jars"][:1]}
    messages = [HumanMessage("q"), _tool_message("get_jar_summary", older), _tool_message("get_jar_summary", SUMMARY)]
    assert read_turn_facts(messages).jar_summary == SUMMARY


def test_read_turn_facts_treats_a_failed_read_as_not_read():
    messages = [HumanMessage("q"), _tool_message("get_jar_summary", None), _tool_message("get_categories", None)]
    facts = read_turn_facts(messages)
    assert facts.jar_summary is None and facts.expense_category_ids is None


# --- edit_jar / rebalance_jars: ids must come from the summary read this turn -----------------------------


def _edit(**overrides):
    return {"type": "edit_jar", "jar_id": "food", "jar_name": "Ăn uống", "allocation_amount": 4200000, "reason": "x", **overrides}


def _rebalance(**overrides):
    return {"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 500000, "moves": [{"from_jar_id": "pool", "amount": 500000}], "reason": "x", **overrides}


def test_edit_jar_with_a_jar_id_from_the_summary_is_kept():
    assert ui_matches_facts(_edit(), _facts())


def test_edit_jar_with_an_invented_jar_id_is_dropped():
    assert not ui_matches_facts(_edit(jar_id="lien-thien"), _facts())  # derived from a jar name, never listed


def test_edit_jar_is_dropped_when_the_summary_was_not_read_this_turn():
    assert not ui_matches_facts(_edit(), _facts(summary=None))


def test_rebalance_with_known_ids_and_the_pool_is_kept():
    ui = _rebalance(moves=[{"from_jar_id": "pool", "amount": 300000}, {"from_jar_id": "lifestyle", "amount": 200000}])
    assert ui_matches_facts(ui, _facts())


def test_rebalance_with_an_invented_target_or_source_is_dropped():
    assert not ui_matches_facts(_rebalance(target_jar_id="an-uong"), _facts())
    assert not ui_matches_facts(_rebalance(moves=[{"from_jar_id": "du-phong", "amount": 500000}]), _facts())


def test_rebalance_is_dropped_when_the_summary_was_not_read_this_turn():
    assert not ui_matches_facts(_rebalance(), _facts(summary=None))


# --- categories: only the customer's own expense categories --------------------------------------------------


def test_a_category_the_customer_created_is_accepted_when_it_is_in_their_list():
    ui = {"type": "create_jar", "jar_name": "Cà phê", "allocation_amount": 500000, "category_ids": ["c_cafe"], "reason": "x"}
    assert ui_matches_facts(ui, _facts(categories={"dining", "c_cafe"}))


def test_a_category_not_in_the_customers_list_is_dropped_for_create_edit_and_transfer():
    unknown = {"c_khong_co"}
    create = {"type": "create_jar", "jar_name": "A", "allocation_amount": 1, "category_ids": ["c_cafe", "c_khong_co"], "reason": "x"}
    assert not ui_matches_facts(create, _facts(categories={"dining", "c_cafe"}))
    assert not ui_matches_facts(_edit(category_ids=["c_khong_co"]), _facts(categories={"dining"}))
    transfer = {"type": "transfer_form", "beneficiary_id": "b1", "amount": 1, "note": "n", "category": next(iter(unknown))}
    assert not ui_matches_facts(transfer, _facts(categories={"dining"}))


def test_categories_are_left_to_pfm_when_get_categories_was_not_called():
    create = {"type": "create_jar", "jar_name": "A", "allocation_amount": 1, "category_ids": ["c_cafe"], "reason": "x"}
    assert ui_matches_facts(create, _facts(categories=None))


def test_a_card_debt_transfer_has_no_category_and_other_types_pass_through():
    card = {"type": "transfer_form", "recipient": "MSB", "account_number": "card_001", "amount": 1, "note": "n"}
    assert ui_matches_facts(card, _facts(summary=None, categories={"dining"}))
    chart = {"type": "chart", "chart_type": "bar", "title": "t", "labels": ["a"], "series": [{"name": "s", "data": [1]}]}
    assert ui_matches_facts(chart, _facts(summary=None))


# --- distribute_amount: every receiving jar must be one the agent read this turn --------------------------------


def _distribute(**overrides):
    return {"type": "distribute_amount", "allocations": [{"to_jar_id": "food", "amount": 100000}], "reason": "x", **overrides}


def test_distribute_amount_to_jars_in_the_summary_is_kept():
    ui = _distribute(allocations=[{"to_jar_id": "food", "amount": 1}, {"to_jar_id": "lifestyle", "amount": 2}])
    assert ui_matches_facts(ui, _facts())


def test_distribute_amount_to_an_invented_jar_is_dropped():
    assert not ui_matches_facts(_distribute(allocations=[{"to_jar_id": "du-lich", "amount": 1}]), _facts())


def test_distribute_amount_is_dropped_when_the_summary_was_not_read_this_turn():
    assert not ui_matches_facts(_distribute(), _facts(summary=None))

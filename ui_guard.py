"""Check an emitted `ui` against what the agent actually READ in the current turn.

The shape validators in `text_utils` cannot tell a real jar id from an invented one: backend_docs/pfm-read-api.md
C2 saw the model answer `edit_jar` with `jar_id: "lien-thien"` (made up from a jar name), for a jar that existed
only in the conversation, and offer categories the customer does not have. Only the tool results of this turn
know the truth, so `get_jar_summary` / `get_categories` hand their raw payload to the server as the tool
*artifact* and this module compares the `ui` against it.

Scope, on purpose: ids only ("does this jar/category exist for this customer?"). Whether a source can give that
much, whether the headroom is enough, whether the name is a duplicate -- pfm re-checks all of that with its own
numbers and drops the proposal (see the table in backend_docs/pfm-read-api.md, part C).
"""

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, ToolMessage

@dataclass(frozen=True)
class TurnFacts:
    """What the agent read in the current turn. `None` means the tool was not called (or failed)."""

    jar_summary: dict | None
    expense_category_ids: set[str] | None
    goals: dict | None = None  # `get_goals` artifact (tools/goal_tools.py `summarize_goals`)
    market: dict[str, dict] | None = None  # `get_goal_market` artifact by instrument id
    plan_cards: list[dict] | None = None  # artifacts of `build_goal_plan_card` this turn


def read_turn_facts(messages: list) -> TurnFacts:
    """Collect the artifacts of `get_jar_summary`/`get_categories` after the last human message.

    An earlier turn's read does not count: a jar the model saw (or proposed) last turn may have changed or
    never existed, and the skills tell the model to read again every turn.
    """
    summary: dict | None = None
    categories: list | None = None
    goals: dict | None = None
    market: list | None = None
    plan_cards: list[dict] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, ToolMessage) or message.artifact is None:
            continue
        # walking backwards: the first hit of each tool is the latest read
        if message.name == "get_jar_summary" and summary is None and isinstance(message.artifact, dict):
            summary = message.artifact
        elif message.name == "get_categories" and categories is None and isinstance(message.artifact, list):
            categories = message.artifact
        elif message.name == "get_goals" and goals is None and isinstance(message.artifact, dict):
            goals = message.artifact
        elif message.name == "get_goal_market" and market is None and isinstance(message.artifact, list):
            market = message.artifact
        elif message.name == "build_goal_plan_card" and isinstance(message.artifact, dict):
            plan_cards.append(message.artifact)
    expense_ids = None
    if categories is not None:
        expense_ids = {c["id"] for c in categories if isinstance(c, dict) and c.get("kind") == "expense" and "id" in c}
    market_by_id = None if market is None else {i["id"]: i for i in market if isinstance(i, dict) and "id" in i}
    return TurnFacts(jar_summary=summary, expense_category_ids=expense_ids, goals=goals, market=market_by_id, plan_cards=plan_cards or None)


def _jar_ids(summary: dict) -> set[str]:
    return {j["id"] for j in summary.get("jars") or [] if isinstance(j, dict) and "id" in j}


def _categories_known(category_ids: list, facts: TurnFacts) -> bool:
    # not read this turn -> nothing to compare with; the shape check already ran and pfm checks the rest
    return facts.expense_category_ids is None or all(c in facts.expense_category_ids for c in category_ids)


def is_goal_form(ui: dict) -> bool:
    """True for the cards bound to the customer's goals: the goal / asset forms (`create_goal`, `edit_goal`, ...) and the plan
    roadmap (it belongs to one goal). The customer is told to review and confirm them."""
    return isinstance(ui, dict) and (ui.get("type") in _GOAL_KINDS or ui.get("type") == "plan_roadmap")


def ui_matches_facts(ui: dict, facts: TurnFacts) -> bool:
    """True when every jar/category id in `ui` is one the agent read this turn."""
    kind = ui.get("type")
    if kind == "create_jar":
        return _categories_known(ui.get("category_ids", []), facts)
    if kind == "edit_jar":
        if facts.jar_summary is None or ui["jar_id"] not in _jar_ids(facts.jar_summary):
            return False
        return _categories_known(ui.get("category_ids", []), facts)
    if kind == "rebalance_jars":
        if facts.jar_summary is None:
            return False
        known = _jar_ids(facts.jar_summary)
        return ui["from_jar_id"] in known and all(a["to_jar_id"] in known for a in ui["allocations"])
    if kind == "distribute_amount":
        if facts.jar_summary is None:
            return False
        known = _jar_ids(facts.jar_summary)
        return all(a["to_jar_id"] in known for a in ui["allocations"])
    if kind == "transfer_form" and "category" in ui:
        return _categories_known([ui["category"]], facts)
    if kind in _GOAL_KINDS:
        return _goal_ui_matches(ui, facts)
    if kind == "plan_roadmap":
        # the card is built by code: only the exact block `build_goal_plan_card` returned this turn is real, and it must be
        # for a goal the customer really has (read this turn)
        if facts.plan_cards is None or ui not in facts.plan_cards or facts.goals is None:
            return False
        goal = next((g for g in facts.goals["goals"] if g["id"] == ui.get("goal_id")), None)
        return goal is not None and goal["status"] in _CHANGEABLE_STATUSES
    return True


# --- goals -----------------------------------------------------------------------------------------------------------
# Unlike the jar forms, a goal form is refused when `get_goals` was not read this turn: the date check needs pfm's today.

_GOAL_KINDS = {"create_goal", "edit_goal", "close_goal", "add_asset", "edit_asset"}
_CHANGEABLE_STATUSES = {"accumulating", "paused", "achieved", "repaying", "missed"}


def _goal_ui_matches(ui: dict, facts: TurnFacts) -> bool:
    goals = facts.goals
    if goals is None:
        return False
    today = goals["today"]
    by_goal = {g["id"]: g for g in goals["goals"]}
    kind = ui["type"]
    if kind == "create_goal":
        return ui["target_date"] > today
    if kind == "edit_goal":
        goal = by_goal.get(ui["goal_id"])
        if goal is None or goal["status"] not in _CHANGEABLE_STATUSES:
            return False
        return "new_target_date" not in ui or ui["new_target_date"] > today
    if kind == "close_goal":
        goal = by_goal.get(ui["goal_id"])
        return goal is not None and goal["status"] != "closed" and not goal["hasActiveLoan"]
    if kind == "add_asset":
        goal = by_goal.get(ui["goal_id"])
        if goal is None or goal["status"] == "closed":
            return False
        if ui["category"] in {"gold", "stock", "external_fund"}:
            instrument = (facts.market or {}).get(ui["instrument_id"])
            if instrument is None or instrument["kind"] != ui["category"]:
                return False
            return instrument["fractional"] or ui["quantity"] == int(ui["quantity"])
        return True
    # edit_asset
    asset = next((a for a in goals["assets"] if a["id"] == ui["asset_id"]), None)
    if asset is None or asset["readOnly"]:
        return False
    if ui["change"] == "revalue":
        return not asset["autoValued"]
    if ui["change"] == "quantity":
        if asset["quantity"] is None or asset["instrumentId"] is None:
            return False
        instrument = (facts.market or {}).get(asset["instrumentId"])
        return instrument is None or instrument["fractional"] or ui["quantity"] == int(ui["quantity"])
    return True

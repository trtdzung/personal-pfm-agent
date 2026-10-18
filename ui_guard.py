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


def read_turn_facts(messages: list) -> TurnFacts:
    """Collect the artifacts of `get_jar_summary`/`get_categories` after the last human message.

    An earlier turn's read does not count: a jar the model saw (or proposed) last turn may have changed or
    never existed, and the skills tell the model to read again every turn.
    """
    summary: dict | None = None
    categories: list | None = None
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
    expense_ids = None
    if categories is not None:
        expense_ids = {c["id"] for c in categories if isinstance(c, dict) and c.get("kind") == "expense" and "id" in c}
    return TurnFacts(jar_summary=summary, expense_category_ids=expense_ids)


def _jar_ids(summary: dict) -> set[str]:
    return {j["id"] for j in summary.get("jars") or [] if isinstance(j, dict) and "id" in j}


def _categories_known(category_ids: list, facts: TurnFacts) -> bool:
    # not read this turn -> nothing to compare with; the shape check already ran and pfm checks the rest
    return facts.expense_category_ids is None or all(c in facts.expense_category_ids for c in category_ids)


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
    return True

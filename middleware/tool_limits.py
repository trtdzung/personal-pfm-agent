"""Hard per-request caps on the lookup tools.

The investment flow used to make 5-10 tool calls per question (several MSB
product searches/reads plus news), even when the answer was just "pay your card
debt first". The skills now tell the model to decide first and look things up
only when needed, but a prompt is a request, not a guarantee -- these caps are
the guarantee. `exit_behavior="continue"` blocks an over-limit call with an
error ToolMessage and lets the run carry on, so the model answers with what it
already has instead of the run crashing.

`run_limit` counts calls within one invocation (one customer message), not
across the whole thread.
"""

from langchain.agents.middleware import ToolCallLimitMiddleware

TOOL_RUN_LIMITS = {
    "search_msb_knowledge": 2,
    "search_market_news": 1,
    "read_market_article": 2,
    "project_investment_growth": 2,
    "calculate_deposit_interest": 2,
    # once to read the jars, once more to compare another month; more means the model is looping
    "get_jar_summary": 2,
    "get_categories": 2,
    # goals: once to read, once more after a confirmed change; the market list may be narrowed a few times by name
    "get_goals": 2,
    "get_goal_market": 3,
    # one reading answers the card's question; again only for a different goal
    "get_goal_insight": 2,
    # computed once per proposal, again if the customer changes the amount / date
    "plan_monthly": 3,
    # a pasted message may carry a few links/numbers; more means the model is looping
    "check_official_channel": 4,
    "check_fraud_watchlist": 4,
    "search_msb_promotions": 2,
}


def tool_call_limits() -> list[ToolCallLimitMiddleware]:
    return [
        ToolCallLimitMiddleware(tool_name=name, run_limit=limit, exit_behavior="continue")
        for name, limit in TOOL_RUN_LIMITS.items()
    ]

from middleware.tool_limits import TOOL_RUN_LIMITS, tool_call_limits


def test_every_lookup_tool_has_a_per_request_cap():
    assert set(TOOL_RUN_LIMITS) == {
        "search_msb_knowledge",
        "search_market_news",
        "read_market_article",
        "project_investment_growth",
        "calculate_deposit_interest",
        "get_jar_summary",
        "get_categories",
        "check_official_channel",
        "check_fraud_watchlist",
        "search_msb_promotions",
    }
    assert all(limit >= 1 for limit in TOOL_RUN_LIMITS.values())


def test_news_lookups_are_capped_tighter_than_product_lookups():
    # news is background for advice, never the point of the answer
    assert TOOL_RUN_LIMITS["search_market_news"] == 1
    assert TOOL_RUN_LIMITS["search_msb_knowledge"] <= 2


def test_limits_are_per_run_and_continue_instead_of_crashing_the_run():
    middlewares = tool_call_limits()
    assert len(middlewares) == len(TOOL_RUN_LIMITS)
    assert len({m.name for m in middlewares}) == len(middlewares)  # unique names, required by the agent factory
    for m in middlewares:
        assert m.run_limit == TOOL_RUN_LIMITS[m.tool_name]
        assert m.thread_limit is None
        assert m.exit_behavior == "continue"

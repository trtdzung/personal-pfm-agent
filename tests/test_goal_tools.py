import json
from pathlib import Path

import httpx
import pytest
from langchain_core.runnables.config import var_child_runnable_config

import tools.goal_tools as goal_tools
from tools.goal_tools import asset_value, get_goal_market, get_goals, price_at, summarize_goals

FIXTURE = json.loads((Path(__file__).parent / "data" / "goals_v2_world.json").read_text(encoding="utf-8"))


def _call(tool, actor_id="CIF_0001"):
    token = var_child_runnable_config.set({"configurable": {"actor_id": actor_id}})
    try:
        return tool.invoke({"name": tool.name, "args": {}, "id": "1", "type": "tool_call"})
    finally:
        var_child_runnable_config.reset(token)


def _serve(monkeypatch, payload=None, status=200):
    seen = []

    def fake_get(url, params=None, timeout=None):
        seen.append((url, params))
        return httpx.Response(status, json=payload if payload is not None else FIXTURE, request=httpx.Request("GET", url))

    monkeypatch.setattr(goal_tools.httpx, "get", fake_get)
    return seen


def test_price_is_the_last_point_on_or_before_the_day_never_a_future_one():
    series = [{"date": "2026-09-11", "price": 100}, {"date": "2026-09-15", "price": 110}, {"date": "2026-09-16", "price": 999}]
    assert price_at(series, "2026-09-15", 0) == 110
    assert price_at(series, "2026-09-14", 0) == 100
    assert price_at(series, "2026-01-01", 0) == 100  # before the first point -> the first price
    assert price_at([], "2026-09-15", 0) == 0
    assert price_at(series, "2026-09-15", -10) == 99  # market shift
    assert price_at([{"date": "2026-09-15", "price": 0.5}], "2026-09-15", 0) == 1  # JS Math.round: .5 goes up


def test_quantity_assets_are_valued_by_price_and_deposits_by_simple_interest():
    market = {i["id"]: i for i in FIXTURE["market"]["instruments"]}
    gold = {"type": "declared", "instrumentId": "gold-ring", "quantity": 2, "value": 0, "status": "held"}
    assert asset_value(gold, "2026-09-15", market, 0) == 2 * 14010000
    deposit = {"type": "declared", "value": 50000000, "status": "held", "accrual": {"principal": 50000000, "ratePa": 5.2, "startDate": "2026-06-01", "maturityDate": "2027-06-01"}}
    assert asset_value(deposit, "2026-09-15", market, 0) == 50000000 + round(50000000 * 0.052 * 106 / 365)
    capped = {"type": "declared", "value": 1, "status": "held", "accrual": {"principal": 1000000, "ratePa": 10, "startDate": "2026-01-01", "maturityDate": "2026-07-01"}}
    assert asset_value(capped, "2026-09-15", market, 0) == 1000000 + round(1000000 * 0.10 * 181 / 365)
    by_hand = {"type": "declared", "value": 30000000, "status": "held"}
    assert asset_value(by_hand, "2026-09-15", market, 0) == 30000000
    assert asset_value({**by_hand, "status": "sold"}, "2026-09-15", market, 0) == 0


def test_summary_counts_cash_plus_the_counted_share_of_each_asset():
    summary = summarize_goals(FIXTURE)
    assert summary["today"] == "2026-09-15" and summary["mainBalance"] == FIXTURE["world"]["customer"]["mainCasaBalance"]
    (goal,) = summary["goals"]
    assert goal["id"] == "goal-1" and goal["balance"] == 5000000 and goal["status"] == "accumulating"
    by_id = {a["id"]: a for a in summary["assets"]}
    assert by_id["asset-5"]["value"] == 2 * 14010000  # gold: price before the first point is the first price
    assert by_id["asset-6"]["value"] == 1000 * 22100  # stock on the day, not the later price
    expected = 5000000 + 30000000 + 2 * 14010000 + round(1000 * 22100 * 0.8) + by_id["asset-7"]["value"]
    assert goal["value"] == expected and goal["valueIsApproximate"] is False


def test_a_liquid_asset_is_read_only_and_makes_the_total_approximate():
    world = json.loads(json.dumps(FIXTURE))
    world["world"]["assets"].append(
        {"id": "asset-9", "goalId": "goal-1", "type": "msb", "category": "term_deposit", "productId": "td", "name": "Tiết kiệm MSB", "costBasis": 1, "value": 10000000,
         "valuationDate": "2026-09-15", "countPercent": 100, "source": "msb", "status": "held", "createdAt": "2026-09-01"}
    )
    summary = summarize_goals(world)
    liquid = next(a for a in summary["assets"] if a["id"] == "asset-9")
    assert liquid["readOnly"] is True and summary["goals"][0]["valueIsApproximate"] is True
    assert all(a["readOnly"] is False for a in summary["assets"] if a["type"] == "declared")


def test_get_goals_reads_the_run_customers_goals_and_returns_text_plus_artifact(monkeypatch):
    seen = _serve(monkeypatch)
    result = _call(get_goals)
    assert result.artifact["goals"][0]["id"] == "goal-1"
    assert seen[0][0].endswith("/api/goals-v2") and seen[0][1] == {"cif": "CIF_0001"}
    body = result.content
    assert "Mua xe" in body and "goal-1" in body and "2026-09-15" in body and "asset-5" in body
    assert "16.396.000đ" in body  # main account balance appears
    assert "priceSeries" not in body and len(body) < 4000


def test_a_customer_without_goals_is_said_so_not_an_error(monkeypatch):
    empty = json.loads(json.dumps(FIXTURE))
    empty["world"].update(goals=[], accounts=[], assets=[])
    _serve(monkeypatch, empty)
    result = _call(get_goals)
    assert result.artifact is not None and result.artifact["goals"] == [] and "chưa có mục tiêu" in result.content.lower()


@pytest.mark.parametrize("status", [404, 500])
def test_a_failed_read_returns_no_artifact_and_a_do_not_guess_message(monkeypatch, status):
    _serve(monkeypatch, {"error": "x"}, status)
    result = _call(get_goals)
    assert result.artifact is None and "đừng đoán" in result.content.lower()


def test_get_goal_market_lists_one_current_price_per_instrument(monkeypatch):
    _serve(monkeypatch)
    result = _call(get_goal_market)
    ids = {i["id"] for i in result.artifact}
    assert ids == {"gold-ring", "stock-acb", "fund-ABBF"}
    acb = next(i for i in result.artifact if i["id"] == "stock-acb")
    assert acb["price"] == 22100 and acb["kind"] == "stock" and acb["unit"] == "cổ phiếu"
    assert "stock-acb" in result.content and "priceSeries" not in result.content


def test_get_goals_gives_the_plan_the_monthly_need_and_the_auto_debit():
    summary = summarize_goals(FIXTURE)
    goal = summary["goals"][0]
    assert goal["standingOrder"] == {"amount": 5000000, "dayOfMonth": 6, "active": True, "nextRunDate": "2026-10-06", "lastResult": "ok"}
    assert goal["phase"] == 1 and goal["requiredMonthly"] > 0 and goal["requiredMonthly"] % 1000 == 0
    assert summary["monthlySurplus"] == 16233333 and summary["salaryDay"] == 5
    text = goal_tools.render_goals(summary)
    assert "cần góp mỗi tháng" in text and "trích tự động: 5.000.000đ/tháng vào ngày 6" in text and "còn dư 16.233.333đ" in text


def test_a_goal_without_an_auto_debit_says_so():
    world = json.loads(json.dumps(FIXTURE))
    world["world"]["goals"][0].pop("standingOrder")
    assert "trích tự động: chưa cài" in goal_tools.render_goals(summarize_goals(world))


def test_phase_two_tracks_principal_plus_interest_and_the_instalment():
    world = json.loads(json.dumps(FIXTURE))
    goal = world["world"]["goals"][0]
    goal.update({"status": "repaying", "loanId": "loan-1"})
    world["world"]["loans"] = [{"id": "loan-1", "goalId": "goal-1", "principal": 100000000, "monthlyPayment": 1151000, "termMonths": 240, "prepaid": 0, "status": "active",
                                "schedule": [{"period": 1, "payment": 1151000, "status": "paid"}, {"period": 2, "payment": 1151000, "status": "upcoming"}, {"period": 3, "payment": 1151000, "status": "upcoming"}]}]
    summary = summarize_goals(world)
    g = summary["goals"][0]
    assert g["phase"] == 2 and g["progressTarget"] == 3 * 1151000 and g["requiredMonthly"] == 1151000
    assert g["progressValue"] == 1151000 + g["value"]
    assert "giai đoạn trả nợ" in goal_tools.render_goals(summary) and "(tiền trả nợ)" in goal_tools.render_goals(summary)


def test_the_old_asset_vocabulary_is_still_understood():
    world = json.loads(json.dumps(FIXTURE))
    for a in world["world"]["assets"]:
        a["type"] = "fixed"
    world["world"]["assets"].append({"id": "asset-9", "goalId": "goal-1", "type": "liquid", "category": "term_deposit", "name": "TK MSB", "value": 10, "countPercent": 100, "status": "held"})
    assets = {a["id"]: a for a in summarize_goals(world)["assets"]}
    assert assets["asset-9"]["readOnly"] is True and assets["asset-9"]["type"] == "msb"
    assert assets["asset-4"]["type"] == "declared"


def _plan(**kw):
    return goal_tools.build_plan(summarize_goals(FIXTURE), kw.get("amount", 0), kw.get("date", ""), kw.get("goal", ""), kw.get("deposit", 0))


def test_plan_for_a_new_goal_spreads_the_gap_over_the_months_rounded_up_to_the_thousand():
    text, plan = _plan(amount=90_000_000, date="2028-09-15", deposit=3_600_000)
    months = goal_tools.months_left("2026-09-15", "2028-09-15")
    assert plan["months"] == months and plan["gap"] == 86_400_000
    assert plan["monthly"] == -(-86_400_000 // months // 1) // 1000 * 1000 or plan["monthly"] % 1000 == 0
    assert plan["monthly"] * months >= plan["gap"] and (plan["monthly"] - 1000) * months < plan["gap"]
    assert 1 <= plan["suggestedDay"] <= 28 and "Cần góp mỗi tháng" in text


def test_plan_after_a_new_date_uses_the_goals_current_value_and_keeps_the_other_field():
    goal = summarize_goals(FIXTURE)["goals"][0]
    text, plan = _plan(goal=goal["id"], date="2030-01-15")
    assert plan["targetAmount"] == goal["targetAmount"] and plan["valueNow"] == goal["value"] and plan["months"] == goal_tools.months_left("2026-09-15", "2030-01-15")


def test_a_longer_deadline_never_needs_more_per_month():
    goal = summarize_goals(FIXTURE)["goals"][0]
    near = _plan(goal=goal["id"], date="2027-09-15")[1]["monthly"]
    far = _plan(goal=goal["id"], date="2029-09-15")[1]["monthly"]
    assert far <= near


def test_plan_refuses_unknown_goals_past_dates_and_missing_inputs():
    assert _plan(goal="goal-999")[1] is None
    assert _plan(amount=1_000_000, date="2026-09-15")[1] is None  # not after today
    assert _plan(amount=1_000_000, date="15/09/2028")[1] is None  # wrong format
    assert _plan(amount=0, date="2028-09-15")[1] is None


def test_plan_says_nothing_to_save_when_the_gap_is_closed():
    assert _plan(amount=1_000_000, date="2028-09-15", deposit=5_000_000)[1]["monthly"] == 0


def test_plan_monthly_tool_reads_the_run_customers_goals(monkeypatch):
    _serve(monkeypatch)
    token = var_child_runnable_config.set({"configurable": {"actor_id": "CIF_0001"}})
    try:
        result = goal_tools.plan_monthly.invoke({"name": "plan_monthly", "args": {"target_amount": 90_000_000, "target_date": "2028-09-15"}, "id": "1", "type": "tool_call"})
    finally:
        var_child_runnable_config.reset(token)
    assert result.artifact["phase"] == 1 and result.artifact["monthly"] > 0

import tools.goal_plan_tools as gp


def run(tool, **args):
    return tool.invoke(args)


def test_loan_quote_matches_the_pfm_annuity_rounded_up_to_a_thousand():
    # reference values = annuityPayment() in pfm/src/features/goals-preview/engine/loan.ts
    for principal, rate, term, pay in [
        (1_400_000_000, 8, 240, "11.711.000"),
        (759_950_000, 8, 240, "6.357.000"),
        (6_000_000, 7.8, 6, "1.023.000"),
        (800_000_000, 7.5, 84, "12.271.000"),
        (1_800_000_000, 8, 240, "15.056.000"),
    ]:
        out = run(gp.loan_quote, principal_vnd=principal, annual_rate_pct=rate, term_months=term)
        assert f"Trả hằng tháng: {pay} VND" in out, out


def test_loan_quote_total_interest_and_zero_rate():
    out = run(gp.loan_quote, principal_vnd=6_000_000, annual_rate_pct=7.8, term_months=6)
    assert "Tổng lãi phải trả: 138.000 VND" in out and "Tổng phải trả: 6.138.000 VND" in out
    flat = run(gp.loan_quote, principal_vnd=100_000_000, annual_rate_pct=0, term_months=10)
    assert "Trả hằng tháng: 10.000.000 VND" in flat and "Tổng lãi phải trả: 0 VND" in flat


def test_loan_quote_grace_period_pays_interest_only_first():
    out = run(gp.loan_quote, principal_vnd=1_200_000_000, annual_rate_pct=8, term_months=240, grace_months=24)
    assert "ân hạn gốc 24 tháng" in out and "trả lãi 8.000.000 VND/tháng" in out
    assert "Trả hằng tháng: 10.500.000 VND" in out and "Tổng lãi phải trả: 1.260.000.000 VND" in out


def test_loan_quote_compares_with_the_monthly_surplus():
    over = run(gp.loan_quote, principal_vnd=1_800_000_000, annual_rate_pct=8, term_months=240, monthly_surplus_vnd=12_840_000)
    assert "vượt phần còn dư" in over and "2.216.000 VND" in over
    within = run(gp.loan_quote, principal_vnd=759_950_000, annual_rate_pct=8, term_months=240, monthly_surplus_vnd=12_840_000)
    assert "nằm trong phần còn dư" in within and "6.483.000 VND" in within


def test_loan_quote_rejects_bad_input_without_a_number():
    for bad in [
        dict(principal_vnd=0, annual_rate_pct=8, term_months=12),
        dict(principal_vnd=1e9, annual_rate_pct=-1, term_months=12),
        dict(principal_vnd=1e9, annual_rate_pct=80, term_months=12),
        dict(principal_vnd=1e9, annual_rate_pct=8, term_months=0),
        dict(principal_vnd=1e9, annual_rate_pct=8, term_months=600),
        dict(principal_vnd=1e9, annual_rate_pct=8, term_months=12, grace_months=12),
    ]:
        out = run(gp.loan_quote, **bad)
        assert "Trả hằng tháng" not in out and "không hợp lệ" in out, bad


def test_savings_projection_simple_interest_per_monthly_lot():
    out = run(gp.savings_projection, monthly_vnd=1_000_000, annual_rate_pct=6, months=12)
    assert "gốc 12.000.000 VND" in out and "lãi 390.000 VND" in out and "tổng nhận 12.390.000 VND" in out
    initial = run(gp.savings_projection, monthly_vnd=1_000_000, annual_rate_pct=6, months=12, initial_vnd=10_000_000)
    assert "gốc 22.000.000 VND" in initial and "lãi 990.000 VND" in initial


def test_savings_projection_rejects_bad_input():
    for bad in [
        dict(monthly_vnd=-1, annual_rate_pct=6, months=12),
        dict(monthly_vnd=1e6, annual_rate_pct=30, months=12),
        dict(monthly_vnd=1e6, annual_rate_pct=6, months=0),
        dict(monthly_vnd=0, annual_rate_pct=6, months=12, initial_vnd=0),
    ]:
        assert "không hợp lệ" in run(gp.savings_projection, **bad), bad


def test_project_target_compounds_the_price():
    out = run(gp.project_target, amount_vnd=2_000_000_000, growth_pct_per_year=5, years=7)
    assert "2.814.201.000 VND" in out and "tăng 5%/năm" in out
    assert "không hợp lệ" in run(gp.project_target, amount_vnd=0, growth_pct_per_year=5, years=7)
    assert "không hợp lệ" in run(gp.project_target, amount_vnd=1e9, growth_pct_per_year=90, years=7)


ARGS = dict(
    target_amount_vnd=2_000_000_000, months_to_deadline=84, start_cash_vnd=50_000_000, monthly_income_vnd=31_433_333,
    monthly_spending_vnd=15_093_333, existing_debt_payment_vnd=3_500_000, target_growth_pct=6, income_growth_pct=5, spending_growth_pct=4,
)


def test_simulate_the_baseline_and_a_loan_at_the_deadline():
    base = run(gp.simulate_goal_plan, mode="no_loan", **ARGS)
    assert "Đạt mục tiêu ở tháng 145 (năm thứ 13), trễ 61 tháng so với hạn." in base and "Quỹ dự phòng: cần 45.279.999 VND" in base
    loan = run(gp.simulate_goal_plan, mode="loan_at", **ARGS)
    assert "trả vay 11.084.000 VND/tháng, tổng lãi vay 1.335.043.338 VND" in loan and "Khả thi dòng tiền: Có." in loan


def test_simulate_buying_now_with_a_loan_is_not_feasible_and_optimize_picks_a_month():
    now = run(gp.simulate_goal_plan, mode="loan_at", purchase_month=0, **ARGS)
    assert "Khả thi dòng tiền: KHÔNG (số vay vượt 80% giá mục tiêu; kỳ trả vay vượt 70% phần còn dư; trả vay trên thu nhập vượt 40%)." in now
    assert "KẾT HỢP TỐI ƯU: mua ở tháng 84 (năm thứ 7)" in run(gp.simulate_goal_plan, mode="optimize", **ARGS)


def test_simulate_the_bad_scenario_changes_the_numbers():
    bad = run(gp.simulate_goal_plan, mode="loan_at", **{**ARGS, "income_growth_pct": 0}, loan_rate_pct=10)
    assert "trả vay 17.575.000 VND/tháng" in bad and "Khả thi dòng tiền: KHÔNG (" in bad


def test_simulate_rejects_bad_input():
    for bad in [
        dict(mode="x"), dict(mode="no_loan", months_to_deadline=0), dict(mode="no_loan", monthly_income_vnd=0),
        dict(mode="no_loan", loan_rate_pct=80), dict(mode="no_loan", reserve_months=20),
        dict(mode="loan_at", purchase_month=99), dict(mode="no_loan", target_growth_pct=90),
    ]:
        out = run(gp.simulate_goal_plan, **{**ARGS, **bad})
        assert "không hợp lệ" in out and "Lộ trình" not in out, bad


def test_non_finite_numbers_are_rejected_not_raised():
    nan, inf = float("nan"), float("inf")
    for bad in nan, inf:
        for key in ("target_amount_vnd", "start_cash_vnd", "monthly_income_vnd", "monthly_spending_vnd", "existing_debt_payment_vnd",
                    "deposit_rate_pct", "loan_rate_pct", "target_growth_pct", "income_growth_pct", "spending_growth_pct", "reserve_months",
                    "other_goals_monthly_vnd"):
            out = run(gp.simulate_goal_plan, **{**ARGS, "mode": "no_loan", key: bad})
            assert "không hợp lệ" in out, key
        for key in ("principal_vnd", "annual_rate_pct", "monthly_surplus_vnd"):
            args = dict(principal_vnd=1e9, annual_rate_pct=8, term_months=120, monthly_surplus_vnd=0)
            assert "không hợp lệ" in run(gp.loan_quote, **{**args, key: bad}), key
        for key in ("monthly_vnd", "annual_rate_pct", "initial_vnd"):
            args = dict(monthly_vnd=1e6, annual_rate_pct=6, months=12, initial_vnd=0)
            assert "không hợp lệ" in run(gp.savings_projection, **{**args, key: bad}), key
        for key in ("amount_vnd", "growth_pct_per_year", "years"):
            args = dict(amount_vnd=1e9, growth_pct_per_year=5, years=3)
            assert "không hợp lệ" in run(gp.project_target, **{**args, key: bad}), key


def test_other_goals_monthly_contributions_delay_the_baseline():
    a = run(gp.simulate_goal_plan, mode="no_loan", **ARGS)
    b = run(gp.simulate_goal_plan, mode="no_loan", other_goals_monthly_vnd=5_000_000, **ARGS)
    assert a != b and "Đạt mục tiêu ở tháng 145" in a
    assert "không hợp lệ" in run(gp.simulate_goal_plan, mode="no_loan", other_goals_monthly_vnd=-1, **ARGS)


# ---- build_goal_plan_card ----

import json
import re

from text_utils import is_valid_ui

CARD_ARGS = {k: v for k, v in ARGS.items()}


def card_call(**over):
    msg = gp.build_goal_plan_card.invoke({"name": "build_goal_plan_card", "args": {"goal_name": "Căn hộ", "goal_id": "goal-1", **CARD_ARGS, **over}, "id": "c1", "type": "tool_call"})
    return msg.content, msg.artifact


def test_build_goal_plan_card_returns_the_block_in_a_fence_and_as_the_artifact():
    content, art = card_call()
    assert isinstance(art, dict) and is_valid_ui(art) and art["type"] == "plan_roadmap"
    m = re.search(r"```ui-json\n(.*?)\n```", content, re.S)
    assert m and json.loads(m.group(1)) == art
    summary = content[: m.start()].strip().splitlines()
    assert 3 <= len(summary) <= 5, summary
    assert "trả nợ" not in content


def test_build_goal_plan_card_rejects_bad_input_without_an_artifact():
    for bad in [
        dict(target_amount_vnd=0), dict(monthly_income_vnd=0), dict(months_to_deadline=0), dict(months_to_deadline=999),
        dict(start_cash_vnd=-1), dict(deposit_rate_pct=50), dict(loan_rate_pct=-1), dict(loan_term_months=6), dict(target_growth_pct=90),
        dict(reserve_months=20), dict(other_goals_monthly_vnd=-1),
    ]:
        content, art = card_call(**bad)
        assert "không hợp lệ" in content and art is None and "ui-json" not in content, bad


def test_build_goal_plan_card_rejects_non_finite_numbers():
    for bad in float("nan"), float("inf"):
        for key in ("target_amount_vnd", "start_cash_vnd", "monthly_income_vnd", "monthly_spending_vnd", "existing_debt_payment_vnd",
                    "deposit_rate_pct", "loan_rate_pct", "target_growth_pct", "income_growth_pct", "spending_growth_pct", "reserve_months",
                    "other_goals_monthly_vnd", "extra_assets_vnd"):
            content, art = card_call(**{key: bad})
            assert "không hợp lệ" in content and art is None, key


def test_build_goal_plan_card_other_goals_change_the_card():
    assert card_call()[1] != card_call(other_goals_monthly_vnd=5_000_000)[1]


def test_build_goal_plan_card_extra_assets_are_counted_and_validated():
    _, plain = card_call()
    content, rich = card_call(extra_assets_vnd=300_000_000)
    assert rich is not None and is_valid_ui(rich)
    assert any("tài sản sẵn có" in a for a in rich["assumptions"]) and rich != plain
    content, art = card_call(extra_assets_vnd=-1)
    assert "không hợp lệ" in content and art is None


def test_build_goal_plan_card_puts_the_goal_id_on_the_card():
    content, art = card_call(goal_id="goal-7")
    assert art["goal_id"] == "goal-7" and is_valid_ui(art) and '"goal_id": "goal-7"' in content


def test_build_goal_plan_card_without_a_goal_builds_nothing_and_says_to_create_the_goal_first():
    for blank in ("", "   "):
        content, art = card_call(goal_id=blank)
        assert art is None and "ui-json" not in content
        assert "Chưa có mục tiêu" in content and "goal-manage" in content


def test_build_goal_plan_card_rejects_a_bad_goal_id():
    for bad in ("x" * 65, "a\nb", "a\x00b", "a\tb"):
        content, art = card_call(goal_id=bad)
        assert "không hợp lệ" in content and art is None and "ui-json" not in content, repr(bad)

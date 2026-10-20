from tools import goal_plan_sim as sim

BASE = dict(target=2_000_000_000, months=84, start_cash=50_000_000, income=31_433_333, spending=15_093_333, debt=3_500_000, target_growth=6, income_growth=5, spending_growth=4)
SMALL = dict(target=40_000_000, months=12, start_cash=0, income=31_433_333, spending=15_093_333, debt=3_500_000)


def test_annuity_matches_pfm_rounding_up_to_a_thousand():
    assert sim.annuity(1_400_000_000, 8, 240) == 11_711_000
    assert sim.annuity(100_000_000, 0, 10) == 10_000_000


def test_the_emergency_reserve_fills_before_anything_goes_to_the_goal():
    p = sim.Inputs(**SMALL)
    states, reserve = sim.accumulate(p, 12)
    assert reserve == 45_279_999
    assert states[3][1] == 0.0 and states[4][1] > 0
    assert round(states[12][0]) == 45_279_999


def test_no_loan_baseline_reaches_the_goal_after_the_deadline():
    p = sim.Inputs(**BASE)
    res = sim.no_loan(p)
    assert res["reach_month"] == 145
    assert round(res["saved"]) == 1_682_143_856 and round(res["shortfall"]) == 1_325_116_662
    assert sim.no_loan(sim.Inputs(**SMALL))["reach_month"] == 7


def test_loan_at_the_deadline_is_feasible_and_priced():
    res = sim.loan_at(sim.Inputs(**BASE), 84)
    assert round(res["loan"]) == 1_325_116_662 and res["payment"] == 11_084_000
    assert round(res["interest"]) == 1_335_043_338 and res["feasible"] and res["why"] == []
    assert sim.loan_at(sim.Inputs(**SMALL), 12)["loan"] == 0


def test_borrowing_everything_now_breaks_all_three_limits():
    res = sim.loan_at(sim.Inputs(**BASE), 0)
    assert round(res["loan"]) == 1_995_279_999 and res["payment"] == 16_690_000
    assert res["why"] == ["số vay vượt 80% giá mục tiêu", "kỳ trả vay vượt 70% phần còn dư", "trả vay trên thu nhập vượt 40%"]


def test_optimize_picks_the_cheapest_feasible_month_or_none():
    best, rows = sim.optimize(sim.Inputs(**BASE))
    assert best["purchase_month"] == 84 and len(rows) == 15 and rows[0]["purchase_month"] == 0
    none, rows = sim.optimize(sim.Inputs(target=5_000_000_000, months=48, start_cash=0, income=31_433_333, spending=15_093_333, debt=3_500_000))
    assert none is None and len(rows) == 9


def test_the_bad_scenario_is_worse_than_the_base():
    bad = sim.Inputs(**{**BASE, "income_growth": 0, "loan_rate": 10})
    assert sim.no_loan(bad)["reach_month"] is None
    res = sim.loan_at(bad, 84)
    assert res["payment"] == 17_575_000 and not res["feasible"]


def test_renders_print_the_figures_the_chat_must_quote():
    p = sim.Inputs(**BASE)
    text = sim.render_no_loan(p, sim.no_loan(p))
    assert "Đạt mục tiêu ở tháng 145 (năm thứ 13), trễ 61 tháng so với hạn." in text
    assert "thiếu 1.325.116.662 VND" in text and "- Năm 7 (tháng 84)" in text and "Lộ trình các mốc" in text
    loan = sim.render_loan(p, sim.loan_at(p, 84))
    assert "trả vay 11.084.000 VND/tháng, tổng lãi vay 1.335.043.338 VND" in loan and "Khả thi dòng tiền: Có." in loan
    assert "tất toán" in loan and "Mục tiêu → Vay" in loan
    best, rows = sim.optimize(p)
    assert "KẾT HỢP TỐI ƯU: mua ở tháng 84 (năm thứ 7)" in sim.render_optimize(p, best, rows)
    assert "Không tháng nào khả thi" in sim.render_optimize(p, None, rows)


# ---- review fixes ----

def test_feasibility_is_checked_over_the_whole_repayment_period():
    p = sim.Inputs(target=2.7e9, months=60, start_cash=0, income=40_000_000, spending=20_000_000, income_growth=0, spending_growth=4)
    res = sim.loan_at(p, 60)
    assert not res["feasible"] and res["breach_month"] > 60
    assert "Kỳ trả vay bắt đầu vượt ngưỡng từ tháng" in sim.render_loan(p, res)
    ok = sim.loan_at(sim.Inputs(**BASE), 84)
    assert ok["feasible"] and ok["breach_month"] is None


def test_optimize_prefers_buying_when_the_goal_is_affordable_without_a_loan():
    p = sim.Inputs(target=100_000_000, months=36, start_cash=0, income=30_000_000, spending=15_000_000, target_growth=10)
    best, _ = sim.optimize(p)
    assert best["purchase_month"] == sim.no_loan(p)["reach_month"] and best["loan"] == 0


def test_a_negative_surplus_draws_savings_down():
    p = sim.Inputs(target=5e8, months=120, start_cash=400_000_000, income=10_000_000, spending=15_000_000)
    states, _ = sim.accumulate(p, 120)
    assert states[24][1] < states[0][1]
    assert all(r >= 0 and b >= 0 for r, b, _ in states)


def test_reach_month_zero_reads_as_already_enough():
    p = sim.Inputs(target=1e7, months=12, start_cash=2e8, income=2e7, spending=1e7)
    text = sim.render_no_loan(p, sim.no_loan(p))
    assert "Đã đủ tiền cho mục tiêu ngay từ bây giờ, không cần góp thêm." in text
    assert "tháng 0 (năm thứ 0)" not in text and "Từ tháng 1 góp" not in text and "Từ tháng 1: góp" not in text


def test_reserve_line_says_when_the_surplus_cannot_fill_it():
    p = sim.Inputs(target=1e8, months=12, start_cash=0, income=1e7, spending=1.5e7)
    assert "không dương" in sim._reserve_line(p, 4.5e7)
    ok = sim.Inputs(target=1e8, months=12, start_cash=0, income=3e7, spending=1.5e7)
    assert "lấp bằng các tháng góp đầu" in sim._reserve_line(ok, 4.5e7)


def test_the_year_table_notes_when_it_is_truncated():
    p = sim.Inputs(target=1e9, months=480, start_cash=0, income=3e7, spending=1.5e7)
    note = "(Bảng chỉ hiển thị 15 năm đầu.)"
    assert note in sim.render_no_loan(p, sim.no_loan(p)) and note in sim.render_loan(p, sim.loan_at(p, 480))
    assert note not in sim.render_no_loan(sim.Inputs(**BASE), sim.no_loan(sim.Inputs(**BASE)))


def test_optimize_candidates_stay_short_and_the_header_is_real():
    _, rows = sim.optimize(sim.Inputs(target=1e9, months=480, start_cash=0, income=3e7, spending=1.5e7))
    assert len(rows) <= 17 and rows[1]["purchase_month"] == 36
    p = sim.Inputs(target=1e9, months=1, start_cash=0, income=3e7, spending=1.5e7)
    best, rows = sim.optimize(p)
    assert "+" not in sim.render_optimize(p, best, rows).splitlines()[0]


def test_other_goals_take_part_of_the_surplus():
    base = sim.Inputs(**BASE)
    less = sim.Inputs(**{**BASE, "other_goals": 5_000_000})
    assert sim.no_loan(less)["reach_month"] > sim.no_loan(base)["reach_month"]
    assert sim.surplus(less, 1) == sim.surplus(base, 1) - 5_000_000

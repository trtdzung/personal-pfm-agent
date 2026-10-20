import copy
import json
from datetime import date
from pathlib import Path

import pytest

from goal_suggest import digest

FIXTURE = json.loads((Path(__file__).parent / "data" / "goals_v2_world.json").read_text(encoding="utf-8"))
TODAY = "2026-09-15"


def raw(**over):
    snapshot = copy.deepcopy(FIXTURE)
    base = {"snapshot": snapshot, "jars": None, "accounts": None, "transactions": None, "categories": None, "preferences": None}
    base.update(over)
    return base


def build(r=None, goal_id="goal-1", goal_name=None):
    return digest.build(r or raw(), goal_id, goal_name)


def highlights(text):
    """The numbered points of the "ĐIỂM ĐÁNG CHÚ Ý" section, in order."""
    section = text.split("== ĐIỂM ĐÁNG CHÚ Ý ĐÃ XÉT SẴN")[1].split("\n", 1)[1]
    return [line.split(". ", 1)[1] for line in section.splitlines() if line.strip() and line[0].isdigit()]


def has(text, needle):
    return any(needle in h for h in highlights(text))


def test_goal_can_be_picked_by_id_or_by_name_ignoring_case_and_accents():
    assert build()[0]["id"] == "goal-1"
    assert build(goal_id=None, goal_name="MUA XE")[0]["id"] == "goal-1"
    assert build(goal_id=None, goal_name="mua x")[0]["id"] == "goal-1"
    with pytest.raises(digest.GoalNotFound):
        build(goal_id="goal-99")
    with pytest.raises(digest.GoalNotFound):
        build(goal_id=None, goal_name="Du lịch")


def test_two_goals_with_the_same_name_are_ambiguous():
    r = raw()
    twin = copy.deepcopy(r["snapshot"]["world"]["goals"][0])
    twin["id"] = "goal-2"
    r["snapshot"]["world"]["goals"].append(twin)
    with pytest.raises(digest.GoalAmbiguous) as err:
        build(r, goal_id=None, goal_name="Mua xe")
    assert "goal-1" in str(err.value) and "goal-2" in str(err.value)


def test_the_goal_section_and_the_three_adjustments_are_computed_in_code():
    _, text = build()
    assert "Số tiền mục tiêu: 600.000.000 VND" in text and "Hạn: 31/12/2027" in text
    assert "Cần góp mỗi tháng để kịp hạn: 29.285.000 VND" in text
    assert "Thiếu mỗi tháng so với cần có: 24.285.000 VND" in text  # 29.285.000 - 5.000.000 standing order
    assert "(a) Tăng số góp hằng tháng lên 29.285.000 VND" in text
    assert "(b) Giữ nguyên số góp 5.000.000 VND thì cần lùi hạn" in text
    assert "(c) Giữ nguyên số góp và hạn thì đến hạn đạt khoảng" in text


def test_loan_scenario_needs_30_percent_saved_and_gives_the_70_percent_amount():
    _, text = build()
    assert "chưa tới ngưỡng 30%" in text and not has(text, "cân nhắc vay")
    r = raw()
    r["snapshot"]["world"]["goals"][0]["targetAmount"] = 300_000_000  # 131.455.068 is 43.8%
    _, text = build(r)
    assert "ĐỦ ĐIỀU KIỆN gợi ý cân nhắc vay" in text and "70% số tiền mục tiêu = 210.000.000 VND" in text
    assert has(text, "cân nhắc vay khoảng 210.000.000 VND")


def test_a_jars_idle_money_is_its_real_surplus_after_the_usual_spending_still_to_come():
    jars = {"unallocated": 0, "jars": [
        {"id": "essentials", "label": "Thiết yếu", "categoryIds": ["housing"], "spendable": 5_000_000, "balance": 5_000_000},
        {"id": "food", "label": "Ăn uống", "categoryIds": ["dining"], "spendable": 3_000_000, "balance": 3_000_000},
        {"id": "health", "label": "Sức khỏe", "categoryIds": ["health"], "spendable": 1_200_000, "balance": 1_200_000},
        {"id": "x", "label": "Âm", "categoryIds": ["shopping"], "spendable": 3_000_000, "balance": -1},
    ]}
    txns = []
    for month in ("06", "07", "08"):  # food: 2.000.000 a month; health: none
        txns += [tx(5, 2_000_000, month=month, category="dining")]
    txns += [tx(3, 500_000, month="09", category="dining")]  # 1.500.000 of the usual month is still to come
    _, text = build(raw(jars=jars, transactions=txns, accounts=[{"id": "acc_current", "type": "current", "balance": 1}]))
    point = next(h for h in highlights(text) if "Có tiền nhàn rỗi" in h)
    assert "Ăn uống dư thực khoảng 1.500.000 VND (dùng được 3.000.000 VND, trung bình mỗi tháng chỉ chi 2.000.000 VND)" in point
    assert "Sức khỏe dư thực khoảng 1.200.000 VND" in point and "Thiết yếu" not in point and "Âm" not in point
    assert "dự kiến còn chi 1.500.000 VND đến cuối tháng" in text


def test_a_jar_whose_usual_spending_eats_its_balance_has_no_surplus_and_no_history_means_no_claim():
    jars = {"unallocated": 0, "jars": [{"id": "food", "label": "Ăn uống", "categoryIds": ["dining"], "spendable": 3_000_000, "balance": 3_000_000}]}
    txns = [tx(5, 4_000_000, month=m, category="dining") for m in ("06", "07", "08")]  # usually spends more than what is left
    accounts = [{"id": "acc_current", "type": "current", "balance": 1}]
    _, text = build(raw(jars=jars, transactions=txns, accounts=accounts))
    assert not has(text, "Có tiền nhàn rỗi ngoài mục tiêu") and "phần dư thực sự khoảng 0 VND" in text
    _, text = build(raw(jars=jars))  # no transactions at all: cannot tell, so do not call it idle
    assert not has(text, "Có tiền nhàn rỗi ngoài mục tiêu") and "chưa đủ lịch sử chi tiêu của hũ này" in text
    _, text = build(raw(jars={"unallocated": 500_000, "jars": []}))
    assert not has(text, "Có tiền nhàn rỗi ngoài mục tiêu")  # under 1.000.000


def test_idle_goal_cash_lists_only_deposit_terms_that_end_before_the_goal_date():
    _, text = build()
    assert has(text, "5.000.000 VND nằm yên")  # 5.000.000 in the goal account
    assert "Kỳ hạn 12 tháng, 6,8%/năm, đáo hạn 15/09/2027, TRƯỚC hạn mục tiêu, lãi ước tính 340.000 VND" in text
    assert "Kỳ hạn 24 tháng" in text and "SAU hạn mục tiêu: KHÔNG dùng" in text.split("Kỳ hạn 24 tháng")[1].splitlines()[0]
    r = raw()
    r["snapshot"]["world"]["goals"][0]["targetDate"] = "2026-10-01"  # no term fits
    assert not has(build(r)[1], "nằm yên")


def test_a_market_asset_that_moved_5_percent_in_30_days_fires_the_price_scenario():
    r = raw()
    for instrument in r["snapshot"]["market"]["instruments"]:
        if instrument["id"] == "gold-ring":
            instrument["priceSeries"] = [{"date": "2026-06-01", "price": 100_000}, {"date": "2026-08-10", "price": 100_000}, {"date": "2026-09-15", "price": 90_000}]
    _, text = build(r)
    assert has(text, "Giá tài sản biến động mạnh")
    assert "Vàng nhẫn" in text and "giảm 10%" in text
    # a calm market does not fire it
    r2 = raw()
    for instrument in r2["snapshot"]["market"]["instruments"]:
        instrument["priceSeries"] = [{"date": "2026-06-01", "price": 100}, {"date": "2026-09-15", "price": 101}]
    assert not has(build(r2)[1], "Giá tài sản biến động")


def tx(day, amount, *, month="09", account="acc_current", direction="debit", kind="expense", category="dining"):
    return {"id": f"{month}{day}{amount}{direction}{category}", "accountId": account, "postedAt": f"2026-{month}-{day:02d}T03:00:00.000Z",
            "amount": amount, "direction": direction, "type": kind, "categoryId": category, "hidden": False}


def test_cash_flow_compares_this_month_to_the_same_days_of_the_three_previous_months():
    accounts = [{"id": "acc_current", "type": "current", "balance": 10}]
    txns = []
    for month in ("06", "07", "08"):
        txns += [tx(5, 1_000_000, month=month), tx(20, 9_000_000, month=month)]  # the 20th is after "today" (15th)
    txns += [tx(5, 2_000_000, month="09"), tx(1, 30_000_000, month="09", direction="credit", kind="income", category="salary")]
    flow = digest.cash_flow(txns, accounts, [{"id": "dining", "label": "Ăn uống"}], date(2026, 9, 15))
    assert flow["months"] == 3
    assert flow["this"]["spend"] == 2_000_000 and flow["avg"]["spend"] == 1_000_000  # the 20th is left out of the average
    assert flow["by_category"][0] == {"label": "Ăn uống", "now": 2_000_000, "avg": 1_000_000, "diff": 1_000_000}
    _, text = build(raw(transactions=txns, accounts=accounts, categories=[{"id": "dining", "label": "Ăn uống"}]))
    assert "Chi tiêu: tháng này 2.000.000 VND; trung bình 1.000.000 VND; cao hơn trung bình 1.000.000 VND, cao hơn 100%." in text
    assert has(text, "Chi tiêu tháng này cao hơn trung bình 100%")


def test_too_little_history_says_so_instead_of_comparing():
    accounts = [{"id": "acc_current", "type": "current", "balance": 10}]
    assert digest.cash_flow([tx(5, 1_000_000, month="08"), tx(5, 1, month="09")], accounts, [], date(2026, 9, 15)) is None
    _, text = build(raw(transactions=[tx(5, 1_000_000, month="08")], accounts=accounts))
    assert "Không đủ dữ liệu giao dịch để so sánh" in text and not has(text, "trung bình")


def test_phase_two_goal_gets_the_repayment_section_and_the_risk_scenario():
    r = raw()
    goal = r["snapshot"]["world"]["goals"][0]
    goal.update({"status": "repaying", "loanId": "loan-1"})
    r["snapshot"]["world"]["loans"] = [{
        "id": "loan-1", "goalId": "goal-1", "principal": 100_000_000, "monthlyPayment": 13_000_000, "termMonths": 12, "prepaid": 0, "status": "active",
        "schedule": [{"period": 1, "dueDate": "2026-09-01", "payment": 13_000_000, "status": "overdue"},
                     {"period": 2, "dueDate": "2026-10-01", "payment": 13_000_000, "status": "upcoming"}],
    }]
    _, text = build(r)
    assert "== TRẢ NỢ (GIAI ĐOẠN 2) ==" in text and "Đang quá hạn: 1 kỳ, tổng 13.000.000 VND" in text
    assert "Trích tự động thấp hơn kỳ trả: 8.000.000 VND mỗi tháng" in text
    assert has(text, "Nguy cơ trễ kỳ trả nợ: 1 kỳ quá hạn") and not has(text, "cân nhắc vay") and not has(text, "nằm yên")
    assert highlights(text)[0].startswith("Nguy cơ trễ kỳ trả nợ")  # the most important point comes first


def test_nothing_worth_saying_is_stated_as_on_track():
    r = raw()
    r["snapshot"]["world"]["goals"][0]["targetDate"] = "2026-10-01"  # no deposit term fits
    r["snapshot"]["world"]["goals"][0]["standingOrder"]["amount"] = 600_000_000
    _, text = build(r)
    assert highlights(text) == [] and "mục tiêu đang đi đúng hướng" in text


def test_a_price_series_shorter_than_the_window_is_unknown_not_unchanged():
    r = raw()
    for instrument in r["snapshot"]["market"]["instruments"]:
        if instrument["id"] == "gold-ring":
            instrument["priceSeries"] = [{"date": "2026-09-14", "price": 100_000}, {"date": "2026-09-15", "price": 90_000}]  # 1 day of history
    _, text = build(r)
    assert not has(text, "Giá tài sản biến động")
    assert "30 ngày: chưa đủ lịch sử giá (chỉ có từ 14/09/2026), không so sánh được" in text
    assert "90 ngày: chưa đủ lịch sử giá" in text and "30 ngày qua giá" not in text.split("Vàng nhẫn")[1].split("\n")[0]


def test_the_one_off_top_up_that_closes_the_gap_is_computed_not_left_to_the_model():
    r = raw()
    goal = r["snapshot"]["world"]["goals"][0]
    goal["standingOrder"]["amount"] = 1_000_000
    _, text = build(r)
    summary = digest.summarize_goals(r["snapshot"])
    g = summary["goals"][0]
    months = digest.months_left(summary["today"], g["targetDate"])
    reachable = digest.round_down_thousand(g["value"] + 1_000_000 * months)
    assert f"nạp thêm một lần {digest.vnd(g['targetAmount'] - reachable)}" in text


def test_a_goal_sharing_its_name_with_another_tells_the_model_to_name_its_deadline():
    r = raw()
    goals = r["snapshot"]["world"]["goals"]
    twin = copy.deepcopy(goals[0])
    twin.update(id="goal-77", targetDate="2031-09-15")
    goals.append(twin)
    _, text = build(r)
    assert "LƯU Ý: khách còn 1 mục tiêu khác cùng tên" in text and "15/09/2031" in text and "PHẢI nêu hạn" in text
    assert "LƯU Ý" not in build()[1]

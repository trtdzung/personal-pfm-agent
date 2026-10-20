import json
import re
from dataclasses import replace

import pytest

from text_utils import is_valid_ui
from tools import goal_plan_sim as sim
from tools.goal_plan_card import build_card, short_vnd
from tests.test_goal_plan_sim import BASE, SMALL


@pytest.mark.parametrize(
    "value,text",
    [
        (352_000_000, "352 triệu"),
        (2_940_000, "2,94 triệu"),
        (1_200_000_000, "1,2 tỷ"),
        (1_805_000_000, "1,81 tỷ"),
        (350_500_000, "350,5 triệu"),
        (12_000, "12 nghìn"),
        (500, "500 đ"),
        (1_000_000, "1 triệu"),
        (0, "0 đ"),
        (999_999_999, "1 tỷ"),
        (-2_940_000, "-2,94 triệu"),
    ],
)
def test_short_vnd(value, text):
    assert short_vnd(value) == text


FEASIBLE = sim.Inputs(target=1_200_000_000, months=120, start_cash=21_726_333, income=31_433_333, spending=15_093_333, debt=3_500_000, other_goals=6_380_000, income_growth=5, spending_growth=4, target_growth=6)
TIGHT = sim.Inputs(target=2_000_000_000, months=84, start_cash=21_726_333, income=31_433_333, spending=15_093_333, debt=3_500_000, other_goals=6_380_000, income_growth=5, spending_growth=4, target_growth=6)
RICH = sim.Inputs(target=40_000_000, months=12, start_cash=200_000_000, income=31_433_333, spending=15_093_333)
INPUTS = {"BASE": sim.Inputs(**BASE), "SMALL": sim.Inputs(**SMALL), "FEASIBLE": FEASIBLE, "TIGHT": TIGHT, "RICH": RICH}


def _plans(card):
    return {x["id"]: x for x in card["plans"]}


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


@pytest.mark.parametrize("name", sorted(INPUTS))
def test_every_card_is_valid_and_consistent(name):
    card = build_card(INPUTS[name], "Căn hộ")
    assert is_valid_ui(card), json.dumps(card, ensure_ascii=False, indent=1)
    ids = [x["id"] for x in card["plans"]]
    assert 1 <= len(ids) <= 3 and ids[0] == "no_loan" and len(set(ids)) == len(ids) and set(ids) <= {"no_loan", "loan_now", "optimized"}
    assert sum(x["verdict"] == "recommended" for x in card["plans"]) <= 1
    for x in card["plans"]:
        assert ("choice_text" in x) == (x["verdict"] != "not_recommended")
        assert x["risk"].startswith("Nếu thu nhập không tăng") if "risk" in x else x["verdict"] == "not_recommended"
    assert not any("trả nợ" in s.lower() for s in _strings(card))
    json.dumps(card)


def test_feasible_recommends_the_optimized_plan():
    card = build_card(FEASIBLE, "Căn hộ 1,2 tỷ")
    plans = _plans(card)
    assert plans["optimized"]["verdict"] == "recommended"
    assert plans["no_loan"]["verdict"] == "late"
    assert list(plans) == ["no_loan", "optimized"]  # borrowing everything now is infeasible, so it is not offered
    loan = sim.loan_at(FEASIBLE, 120)
    loan_ms = next(m for m in plans["optimized"]["milestones"] if m["kind"] == "loan")
    assert short_vnd(round(loan["loan"])) in loan_ms["title"]
    assert [m["kind"] for m in plans["optimized"]["milestones"]] == ["reserve", "save", "switch", "buy", "loan", "repay", "done"]
    assert card["title"] == "Căn hộ 1,2 tỷ · 10 năm"
    assert card["baseline"].startswith("Đạt mục tiêu ở tháng 138 (năm thứ 12), trễ 18 tháng so với hạn (thiếu ")
    assert "Lãi tiết kiệm 6,8%/năm" in card["assumptions"] and "Quỹ dự phòng 3 tháng chi tiêu" in card["assumptions"]
    assert plans["no_loan"]["choice_text"].startswith("Tôi chọn phương án Không vay: đạt mục tiêu")
    assert len(plans["optimized"]["choice_text"]) <= 120


def test_tight_has_no_recommendation_and_no_stray_choice_text():
    card = build_card(TIGHT, "Căn hộ 2 tỷ")
    plans = _plans(card)
    assert all(x["verdict"] != "recommended" for x in card["plans"])
    assert list(plans) == ["no_loan"]  # no feasible loan plan: only the saving plan is shown
    assert plans["no_loan"]["verdict"] in ("late", "not_recommended")
    for x in card["plans"]:
        assert ("choice_text" in x) == (x["verdict"] != "not_recommended")


def test_small_goal_is_reached_without_a_loan_and_recommended():
    card = build_card(INPUTS["SMALL"], "Du lịch")
    plans = _plans(card)
    assert plans["no_loan"]["verdict"] == "recommended" and plans["no_loan"]["headline"].startswith("Đạt mục tiêu ở tháng 7 (năm thứ 1), đúng hạn")
    assert [m["kind"] for m in plans["no_loan"]["milestones"]] == ["reserve", "save", "buy"]
    assert list(plans) == ["no_loan"]  # no loan needed, a borrowing plan would be noise
    assert card["title"] == "Du lịch · 1 năm"


def test_enough_cash_now_says_there_is_no_need_to_borrow():
    card = build_card(RICH, "Du lịch")
    plans = _plans(card)
    assert list(plans) == ["no_loan"]
    assert plans["no_loan"]["verdict"] == "recommended" and "đủ tiền" in plans["no_loan"]["headline"]


def test_never_reaching_the_goal_gives_no_milestones():
    p = sim.Inputs(target=50_000_000_000, months=24, start_cash=0, income=20_000_000, spending=15_000_000)
    card = build_card(p, "Đảo riêng")
    assert is_valid_ui(card)
    nl = _plans(card)["no_loan"]
    assert nl["verdict"] == "not_recommended" and nl["milestones"] == [] and nl["headline"] == "Chưa đạt mục tiêu"
    assert nl["reason"] == f"Không đạt mục tiêu trong {24 + sim.EXTRA_MONTHS} tháng"
    assert [x["id"] for x in card["plans"]] == ["no_loan"] and all(x["verdict"] == "not_recommended" for x in card["plans"])


def test_long_goal_names_are_cut_to_fit_the_title():
    card = build_card(INPUTS["SMALL"], "x" * 200)
    assert len(card["title"]) <= 80 and card["title"].endswith(" · 1 năm") and is_valid_ui(card)


def test_deadline_in_months_when_not_whole_years():
    card = build_card(replace(INPUTS["SMALL"], months=18), "Du lịch")
    assert card["title"] == "Du lịch · 18 tháng" and is_valid_ui(card)


def test_savings_interest_range_compares_the_same_horizon_for_base_and_bad_scenario():
    card = build_card(FEASIBLE, "Mua căn hộ")
    by_id = {pl["id"]: {m["label"]: m["value"] for m in pl["metrics"]} for pl in card["plans"]}
    assert by_id["optimized"]["Lãi tiết kiệm"] == "175,26 triệu–437,35 triệu"
    assert by_id["no_loan"]["Lãi tiết kiệm"] == "224,34 triệu–640,41 triệu"


def test_no_loan_on_time_is_recommended_over_borrowing():
    p = sim.Inputs(target=2e9, months=84, start_cash=600e6, income=80e6, spending=25e6, loan_term=240, target_growth=6, income_growth=5, spending_growth=4)
    plans = _plans(build_card(p, "Nhà"))
    assert plans["no_loan"]["verdict"] == "recommended"
    assert all(plans[k]["verdict"] == "ok" for k in ("loan_now", "optimized") if k in plans)
    p2 = sim.Inputs(target=300e6, months=36, start_cash=150e6, income=40e6, spending=15e6, loan_term=60)
    assert _plans(build_card(p2, "Xe"))["no_loan"]["verdict"] == "recommended"


def test_risk_text_for_goal_reachable_now_has_no_year_zero():
    p = sim.Inputs(target=50e6, months=12, start_cash=200e6, income=40e6, spending=15e6, loan_term=60)
    card = build_card(p, "Du lịch")
    assert not any("năm thứ 0" in s for s in _strings(card))
    assert "đã đủ tiền ngay từ bây giờ" in _plans(card)["no_loan"]["risk"]


def test_short_vnd_rounds_before_choosing_the_unit():
    assert short_vnd(999.5) == "1 nghìn"
    assert short_vnd(999.4) == "999 đ"
    assert short_vnd(999_999.9) == "1 triệu"


def test_assets_the_customer_already_has_for_the_goal_move_the_plan_earlier():
    without = build_card(FEASIBLE, "Căn hộ")
    rich = build_card(replace(FEASIBLE, extra_assets=500_000_000), "Căn hộ")
    assert is_valid_ui(rich)
    assert "Đã tính 500 triệu tài sản sẵn có cho mục tiêu" in rich["assumptions"]
    nl_without, nl_rich = _plans(without)["no_loan"], _plans(rich)["no_loan"]
    assert nl_without["verdict"] == "late" and nl_rich["verdict"] == "recommended" and "tháng 88" in nl_rich["headline"]
    # with enough assets nobody needs a loan, so only the saving plan is left
    assert [x["id"] for x in build_card(replace(FEASIBLE, extra_assets=1_500_000_000), "Căn hộ")["plans"]] == ["no_loan"]


def test_the_extra_assets_never_fill_the_emergency_reserve():
    states, reserve = sim.accumulate(replace(FEASIBLE, extra_assets=100_000_000), 0)
    assert states[0][0] == min(FEASIBLE.start_cash, reserve) and states[0][1] >= 100_000_000

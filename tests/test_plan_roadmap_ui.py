import copy

import pytest

from text_utils import is_valid_ui


def _plan(pid="optimized", verdict="recommended", **over):
    plan = {
        "id": pid,
        "name": "Kết hợp tối ưu",
        "verdict": verdict,
        "headline": "Mua ở tháng 120 (năm thứ 10), vay 1,2 tỷ",
        "reason": "Dòng tiền đủ",
        "metrics": [{"label": "Số vay", "value": "1,2 tỷ"}, {"label": "Trả vay", "value": "9 triệu/tháng"}],
        "milestones": [
            {"when": "Tháng 0", "kind": "reserve", "title": "Lập quỹ dự phòng", "detail": "Cần 45 triệu", "action": "Giữ tiền ở tài khoản"},
            {"when": "Tháng 120", "kind": "buy", "title": "Mua mục tiêu"},
        ],
        "risk": "Nếu thu nhập không tăng: chưa đạt mục tiêu",
        "choice_text": "Tôi chọn phương án Kết hợp tối ưu",
    }
    plan.update(over)
    return plan


def _card(**over):
    card = {
        "type": "plan_roadmap",
        "title": "Căn hộ 1,2 tỷ · 10 năm",
        "baseline": "Đạt mục tiêu ở tháng 150, trễ 30 tháng so với hạn",
        "assumptions": ["Lãi tiết kiệm 6,8%/năm", "Lãi vay 8%/năm"],
        "plans": [_plan()],
    }
    card.update(over)
    return card


def _not_rec(pid="loan_now"):
    plan = _plan(pid, "not_recommended", name="Vay mua ngay", reason="số vay vượt 80% giá mục tiêu", milestones=[])
    del plan["choice_text"]
    return plan


def test_a_fully_valid_card_passes():
    assert is_valid_ui(_card())
    three = _card(plans=[_plan("no_loan", "ok"), _plan("loan_now", "late"), _plan("optimized", "recommended")])
    assert is_valid_ui(three)
    assert is_valid_ui(_card(plans=[_not_rec(), _plan()], assumptions=[]))


def test_minimal_plan_passes():
    plan = {"id": "no_loan", "name": "Không vay", "verdict": "ok", "headline": "h", "metrics": [],
            "milestones": [{"when": "Tháng 1", "kind": "save", "title": "t"}], "choice_text": "c"}
    assert is_valid_ui(_card(plans=[plan]))


def _mut(fn):
    card = copy.deepcopy(_card())
    fn(card)
    return card


BAD = {
    "non_dict": "x",
    "extra_root_key": _mut(lambda c: c.update(extra=1)),
    "missing_title": _mut(lambda c: c.pop("title")),
    "empty_title": _mut(lambda c: c.update(title="")),
    "long_title": _mut(lambda c: c.update(title="x" * 81)),
    "long_baseline": _mut(lambda c: c.update(baseline="x" * 201)),
    "empty_baseline": _mut(lambda c: c.update(baseline=" ")),
    "assumptions_not_list": _mut(lambda c: c.update(assumptions="x")),
    "assumption_non_string": _mut(lambda c: c.update(assumptions=[1])),
    "assumption_long": _mut(lambda c: c.update(assumptions=["x" * 81])),
    "nine_assumptions": _mut(lambda c: c.update(assumptions=["a"] * 9)),
    "zero_plans": _mut(lambda c: c.update(plans=[])),
    "four_plans": _mut(lambda c: c.update(plans=[_plan("no_loan", "ok"), _plan("loan_now", "ok"), _plan("optimized", "ok"), _plan("optimized", "ok")])),
    "duplicate_id": _mut(lambda c: c.update(plans=[_plan("no_loan", "ok"), _plan("no_loan", "ok")])),
    "unknown_id": _mut(lambda c: c["plans"][0].update(id="other")),
    "two_recommended": _mut(lambda c: c.update(plans=[_plan("no_loan", "recommended"), _plan("optimized", "recommended")])),
    "extra_plan_key": _mut(lambda c: c["plans"][0].update(extra=1)),
    "unknown_verdict": _mut(lambda c: c["plans"][0].update(verdict="great")),
    "long_name": _mut(lambda c: c["plans"][0].update(name="x" * 41)),
    "long_headline": _mut(lambda c: c["plans"][0].update(headline="x" * 161)),
    "long_reason": _mut(lambda c: c["plans"][0].update(reason="x" * 201)),
    "long_risk": _mut(lambda c: c["plans"][0].update(risk="x" * 241)),
    "risk_non_string": _mut(lambda c: c["plans"][0].update(risk=3)),
    "five_metrics": _mut(lambda c: c["plans"][0].update(metrics=[{"label": "a", "value": "b"}] * 5)),
    "metric_extra_key": _mut(lambda c: c["plans"][0].update(metrics=[{"label": "a", "value": "b", "x": 1}])),
    "metric_long_label": _mut(lambda c: c["plans"][0].update(metrics=[{"label": "x" * 31, "value": "b"}])),
    "metric_long_value": _mut(lambda c: c["plans"][0].update(metrics=[{"label": "a", "value": "x" * 41}])),
    "metric_non_string": _mut(lambda c: c["plans"][0].update(metrics=[{"label": "a", "value": 5}])),
    "metric_non_dict": _mut(lambda c: c["plans"][0].update(metrics=["a"])),
    "empty_milestones": _mut(lambda c: c["plans"][0].update(milestones=[])),
    "eleven_milestones": _mut(lambda c: c["plans"][0].update(milestones=[{"when": "Tháng 1", "kind": "save", "title": "t"}] * 11)),
    "unknown_kind": _mut(lambda c: c["plans"][0]["milestones"][0].update(kind="party")),
    "milestone_extra_key": _mut(lambda c: c["plans"][0]["milestones"][0].update(x=1)),
    "milestone_long_when": _mut(lambda c: c["plans"][0]["milestones"][0].update(when="x" * 31)),
    "milestone_long_title": _mut(lambda c: c["plans"][0]["milestones"][0].update(title="x" * 61)),
    "milestone_long_detail": _mut(lambda c: c["plans"][0]["milestones"][0].update(detail="x" * 201)),
    "milestone_long_action": _mut(lambda c: c["plans"][0]["milestones"][0].update(action="x" * 121)),
    "milestone_missing_title": _mut(lambda c: c["plans"][0]["milestones"][0].pop("title")),
    "milestone_non_dict": _mut(lambda c: c["plans"][0].update(milestones=["x"])),
    "missing_choice_text": _mut(lambda c: c["plans"][0].pop("choice_text")),
    "long_choice_text": _mut(lambda c: c["plans"][0].update(choice_text="x" * 121)),
    "empty_choice_text": _mut(lambda c: c["plans"][0].update(choice_text="")),
    "choice_text_on_not_recommended": _mut(lambda c: c.update(plans=[{**_not_rec(), "choice_text": "x"}])),
    "not_recommended_without_reason": _mut(lambda c: c.update(plans=[{k: v for k, v in _not_rec().items() if k != "reason"}])),
    "missing_metrics": _mut(lambda c: c["plans"][0].pop("metrics")),
    "missing_milestones": _mut(lambda c: c["plans"][0].pop("milestones")),
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_each_violated_rule_is_rejected(name):
    assert not is_valid_ui(BAD[name]), name


def test_not_recommended_may_keep_milestones():
    plan = {**_not_rec(), "milestones": [{"when": "Tháng 0", "kind": "reserve", "title": "t"}]}
    assert is_valid_ui(_card(plans=[plan]))


def test_blank_optional_strings_are_rejected():
    for key in ("reason", "risk"):
        for blank in ("", "  "):
            assert not is_valid_ui(_card(plans=[_plan(**{key: blank})])), (key, blank)
    for key in ("detail", "action"):
        for blank in ("", "  "):
            card = _card()
            card["plans"][0]["milestones"][0][key] = blank
            assert not is_valid_ui(card), (key, blank)

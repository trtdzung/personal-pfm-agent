import json

import pytest

from text_utils import extract_ui_block, is_valid_ui

CREATE = {"type": "create_goal", "goal_name": "Mua xe", "template": "car", "target_amount": 600000000, "target_date": "2027-12-31",
          "flexibility": "date_flexible", "initial_deposit": 5000000, "reason": "Khách muốn mua xe vào cuối 2027"}
EDIT = {"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "new_target_date": "2028-03-31", "reason": "Khách muốn lùi hạn"}
CLOSE = {"type": "close_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "reason": "Khách muốn đóng mục tiêu"}
ASSET_HAND = {"type": "add_asset", "goal_id": "goal-1", "category": "motorbike", "asset_name": "Xe máy Honda", "value": 30000000, "count_percent": 100, "reason": "Khách khai"}
ASSET_MARKET = {"type": "add_asset", "goal_id": "goal-1", "category": "gold", "asset_name": "Vàng nhẫn", "instrument_id": "gold-ring", "quantity": 2, "count_percent": 100, "reason": "Khách khai"}
ASSET_DEPOSIT = {"type": "add_asset", "goal_id": "goal-1", "category": "deposit", "asset_name": "Gửi VCB", "count_percent": 100, "institution": "Vietcombank",
                 "accrual": {"principal": 50000000, "rate_pa": 5.2, "start_date": "2026-06-01", "maturity_date": "2027-06-01"}, "reason": "Khách khai"}
EDIT_ASSET = {"type": "edit_asset", "asset_id": "asset-4", "asset_name": "Xe máy Honda", "change": "revalue", "value": 28000000, "reason": "Khách định giá lại"}


def _with(base, **changes):
    out = {**base, **changes}
    return {k: v for k, v in out.items() if v is not ...}


@pytest.mark.parametrize("ui", [CREATE, EDIT, CLOSE, ASSET_HAND, ASSET_MARKET, ASSET_DEPOSIT, EDIT_ASSET,
                                _with(EDIT, new_target_date=..., new_target_amount=500000000),
                                _with(EDIT_ASSET, change="quantity", value=..., quantity=3),
                                _with(EDIT_ASSET, change="remove", value=...),
                                _with(CREATE, initial_deposit=0),
                                _with(ASSET_DEPOSIT, accrual={"principal": 1, "rate_pa": 0, "start_date": "2026-06-01"})])
def test_valid_forms(ui):
    assert is_valid_ui(ui)


@pytest.mark.parametrize(
    "ui",
    [
        _with(CREATE, template="boat"), _with(CREATE, flexibility="soon"), _with(CREATE, target_amount=0), _with(CREATE, target_amount=1.5),
        _with(CREATE, target_date="2027-13-40"), _with(CREATE, target_date="31/12/2027"), _with(CREATE, initial_deposit=-1),
        _with(CREATE, goal_name=""), _with(CREATE, reason=""), _with(CREATE, goal_id="goal-9"), _with(CREATE, initial_deposit=..., ),
        _with(EDIT, new_target_date=...),  # nothing to change
        _with(EDIT, goal_id=""), _with(EDIT, new_target_amount=-5), _with(EDIT, new_target_date="soon"),
        _with(CLOSE, goal_id=...), _with(CLOSE, extra=1),
        _with(ASSET_HAND, category="crypto"), _with(ASSET_HAND, value=...), _with(ASSET_HAND, value=-1), _with(ASSET_HAND, count_percent=101),
        _with(ASSET_HAND, count_percent=-1), _with(ASSET_HAND, instrument_id="gold-ring"), _with(ASSET_HAND, goal_id=...),
        _with(ASSET_MARKET, instrument_id=...), _with(ASSET_MARKET, quantity=0), _with(ASSET_MARKET, value=100),
        _with(ASSET_DEPOSIT, accrual=...), _with(ASSET_DEPOSIT, accrual={"principal": 0, "rate_pa": 5, "start_date": "2026-06-01"}),
        _with(ASSET_DEPOSIT, accrual={"principal": 1, "rate_pa": -1, "start_date": "2026-06-01"}),
        _with(ASSET_DEPOSIT, accrual={"principal": 1, "rate_pa": 5, "start_date": "2026-06-01", "maturity_date": "2026-01-01"}),
        _with(ASSET_DEPOSIT, accrual={"principal": 1, "rate_pa": 5, "start_date": "2026-06-01", "bonus": 1}),
        _with(ASSET_DEPOSIT, value=5),
        _with(EDIT_ASSET, change="sell"), _with(EDIT_ASSET, value=...), _with(EDIT_ASSET, change="quantity", value=..., quantity=0),
        _with(EDIT_ASSET, change="remove", value=...) | {"quantity": 1}, _with(EDIT_ASSET, asset_id=""),
        _with(EDIT_ASSET, count_percent=150),
    ],
)
def test_invalid_forms_are_refused(ui):
    assert not is_valid_ui(ui)


def test_a_fenced_goal_form_is_split_off_the_answer():
    text = "Mình đề xuất mục tiêu Mua xe.\n\n```ui-json\n" + json.dumps(CREATE, ensure_ascii=False) + "\n```"
    answer, ui = extract_ui_block(text)
    assert ui == CREATE and answer == "Mình đề xuất mục tiêu Mua xe."


def test_a_broken_goal_form_is_dropped_but_the_answer_stays():
    bad = _with(CREATE, template="boat")
    answer, ui = extract_ui_block("Mình đề xuất.\n\n```ui-json\n" + json.dumps(bad) + "\n```")
    assert ui is None and answer == "Mình đề xuất."


def test_flexibility_is_optional_and_monthly_plan_is_both_or_none():
    no_flex = _with(CREATE, flexibility=...)
    assert is_valid_ui(no_flex)
    assert is_valid_ui({**no_flex, "monthly_amount": 8000000, "monthly_day": 6})
    assert not is_valid_ui({**no_flex, "monthly_amount": 8000000})
    assert not is_valid_ui({**no_flex, "monthly_day": 6})
    assert not is_valid_ui({**no_flex, "monthly_amount": 8000000, "monthly_day": 31})
    assert not is_valid_ui({**no_flex, "monthly_amount": 0, "monthly_day": 6})
    assert not is_valid_ui({**no_flex, "monthly_amount": 8000000, "monthly_day": 6.5})
    assert not is_valid_ui({**no_flex, "monthly_amount": 8000000, "monthly_day": True})


def test_edit_goal_can_change_only_the_monthly_plan():
    plan_only = {"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "monthly_amount": 6000000, "monthly_day": 6, "reason": "Khách đổi số góp"}
    assert is_valid_ui(plan_only)
    assert is_valid_ui({**plan_only, "new_target_amount": 500000000})
    assert not is_valid_ui({k: v for k, v in plan_only.items() if k != "monthly_day"})

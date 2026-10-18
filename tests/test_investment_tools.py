import json
from datetime import datetime

import pytest

import middleware.seed_customer_context as scc
from text_utils import _is_valid_chart, extract_ui_block
from tools.investment_tools import (
    DEFAULT_ASSUMED_MONTHLY_RETURN_PCT,
    _checkpoints,
    project_investment_growth,
)

SEP_19 = datetime(2026, 9, 19, 9, 0, tzinfo=scc._VIETNAM_TZ)
MONTHS = 103 / 30.4375  # 19/09 -> 31/12/2026


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(scc, "_today", lambda: SEP_19)


def _run(**kwargs) -> str:
    return project_investment_growth.invoke(kwargs)


def _chart_from(text: str) -> dict:
    line = next(l for l in text.splitlines() if l.startswith('{"type": "chart"'))
    return json.loads(line)


def test_default_assumption_is_two_percent_a_month():
    assert DEFAULT_ASSUMED_MONTHLY_RETURN_PCT == 2.0


def test_checkpoints_are_today_then_each_month_end_up_to_31_12():
    labels = [d.strftime("%d/%m") for d in _checkpoints(SEP_19.date())]
    assert labels == ["19/09", "30/09", "31/10", "30/11", "31/12"]


def test_checkpoints_when_today_is_already_a_month_end():
    labels = [d.strftime("%d/%m") for d in _checkpoints(datetime(2026, 10, 31).date())]
    assert labels == ["31/10", "30/11", "31/12"]


def test_projection_matches_compound_formula_for_all_three_scenarios():
    chart = _chart_from(_run(principal_vnd=50_000_000))
    up, flat, down = (s["data"] for s in chart["series"])
    assert up[0] == flat[0] == down[0] == 50_000_000
    assert up[-1] == round(50_000_000 * 1.02**MONTHS)
    assert down[-1] == round(50_000_000 * 0.98**MONTHS)
    assert set(flat) == {50_000_000}


def test_required_principal_for_target_gain():
    text = _run(target_gain_vnd=10_000_000)
    needed = 10_000_000 / (1.02**MONTHS - 1)
    assert f"{round(needed):,}".replace(",", ".") + "đ" in text
    assert "KHÔNG đạt được mục tiêu" in text  # flat / losing market
    assert "ui-json" not in text  # no principal -> no chart block


def test_target_is_reported_unreachable_with_too_small_a_principal():
    text = _run(principal_vnd=50_000_000, target_gain_vnd=10_000_000)
    assert "mục tiêu lãi 10.000.000đ KHÔNG đạt ngay cả trong kịch bản +2,0%/tháng" in text


def test_target_is_reported_reachable_only_in_the_positive_scenario_with_enough_principal():
    text = _run(principal_vnd=200_000_000, target_gain_vnd=10_000_000)
    assert "mục tiêu lãi 10.000.000đ ĐẠT trong kịch bản +2,0%/tháng" in text
    assert "nếu thị trường đi ngang (0%) hoặc giảm thì KHÔNG đạt" in text
    assert "KHÔNG đạt ngay cả trong" not in text


def test_output_always_labels_the_rate_as_an_assumption_and_states_the_annualised_rate():
    text = _run(principal_vnd=10_000_000)
    assert "GIẢ ĐỊNH" in text
    assert "không phải mức trung bình của thị trường" in text
    assert "không phải cam kết" in text
    assert "+26,8%/năm" in text  # 1.02**12 - 1
    assert "Đứng yên (0%)" in text
    assert "Kịch bản -2,0%/tháng" in text


def test_chart_block_passes_the_servers_own_chart_validator_and_round_trips():
    text = _run(principal_vnd=30_000_000)
    chart = _chart_from(text)
    assert _is_valid_chart(chart)
    assert all(len(s["data"]) == len(chart["labels"]) for s in chart["series"])
    fenced = f"Tóm tắt.\n```ui-json\n{json.dumps(chart, ensure_ascii=False)}\n```"
    cleaned, ui = extract_ui_block(fenced)
    assert ui == chart and cleaned == "Tóm tắt."


def test_custom_rate_is_used_and_sign_is_ignored():
    a = _chart_from(_run(principal_vnd=10_000_000, monthly_return_pct=1.0))
    b = _chart_from(_run(principal_vnd=10_000_000, monthly_return_pct=-1.0))
    assert a == b
    assert a["series"][0]["data"][-1] == round(10_000_000 * 1.01**MONTHS)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"principal_vnd": -1}, ">= 0"),
        ({}, "ít nhất 1 trong 2"),
        ({"principal_vnd": 1_000_000, "monthly_return_pct": 0}, "khác 0"),
        ({"principal_vnd": 1_000_000, "monthly_return_pct": 25}, "không quá"),
    ],
)
def test_invalid_inputs_are_rejected_with_a_message(kwargs, message):
    assert message in _run(**kwargs)


def test_no_time_left_in_the_year_is_reported(monkeypatch):
    monkeypatch.setattr(scc, "_today", lambda: datetime(2026, 12, 31, tzinfo=scc._VIETNAM_TZ))
    assert "đã là cuối năm" in _run(principal_vnd=1_000_000)


def test_required_return_line_is_computed_when_both_principal_and_target_are_given():
    text = _run(principal_vnd=60_000_000, target_gain_vnd=10_000_000)
    req = 10_000_000 / 60_000_000
    monthly = ((1 + req) ** (1 / MONTHS) - 1) * 100
    annual = ((1 + req) ** (12 / MONTHS) - 1) * 100
    assert "Lợi suất cần có để lãi 10.000.000đ từ vốn 60.000.000đ" in text
    assert f"+{monthly:.1f}".replace(".", ",") + "%/tháng" in text
    assert f"+{annual:.1f}".replace(".", ",") + "%/năm" in text


def test_required_return_line_absent_without_target():
    assert "Lợi suất cần có" not in _run(principal_vnd=60_000_000)

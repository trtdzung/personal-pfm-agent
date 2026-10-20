"""contracts.py: payload pfm gửi phải parse được (D7, D8); trường thừa bỏ qua; thiếu bắt buộc → lỗi."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from goal_suggest.contracts import GoalSuggestionsRequest


# Payload giống buildAgentRequest trong pfm (.../suggestions/agent-wording.ts).
PFM_PAYLOAD = {
    "user_id": "CIF_0001",
    "today": "2026-10-17",
    "customer": {
        "monthly_income": 25_000_000,
        "monthly_surplus": 4_500_000,
        "salary_day": 5,
        "risk_profile": "balanced",
    },
    "goals": [
        {
            "id": "g1",
            "name": "Mua nhà",
            "status": "active",
            "phase": "build",
            "target_amount": 500_000_000,
            "target_date": "2028-12-31",
            "value": 80_000_000,
            "progress_pct": 16.0,
            "months_left": 26.5,
        }
    ],
    "signals": [
        {
            "id": "sig-salary",
            "goal_id": "g1",
            "kind": "salary",
            "rank": 1,
            "facts": {
                "salary_day": 5,
                "monthly_surplus": 4_500_000,
                "main_casa_balance": 12_000_000,
                "required_monthly": 3_000_000,
                "standing_order_amount": 2_000_000,
            },
            "allowed_actions": [{"id": "a0", "label": "Trích ngay"}, {"id": "a1", "label": "Để sau"}],
            "fallback": {
                "title": "Ngày lương sắp tới",
                "body": "Bạn có thể trích thêm cho mục tiêu Mua nhà.",
            },
        },
        {
            "id": "sig-insufficient",
            "goal_id": None,  # D7: tín hiệu toàn khách
            "kind": "insufficient_data",
            "rank": 2,
            "facts": {"salary_day": 5, "main_casa_balance": 12_000_000},
            "allowed_actions": [{"id": "a0", "label": "Xem hướng dẫn"}],
            "fallback": {"title": "Chưa đủ dữ liệu", "body": "Cần thêm giao dịch để gợi ý tốt hơn."},
        },
    ],
    "feedback": [
        {"kind": "salary", "goal_id": "g1", "ignored_count": 0},
        {"kind": "insufficient_data", "goal_id": None, "ignored_count": 2},  # D8
    ],
}


def test_pfm_payload_parses():
    req = GoalSuggestionsRequest.model_validate(PFM_PAYLOAD)
    assert req.user_id == "CIF_0001"
    assert req.customer.monthly_surplus == 4_500_000
    assert req.goals[0].progress_pct == 16.0
    assert req.goals[0].months_left == 26.5
    assert req.goals[0].target_amount == 500_000_000
    assert req.signals[0].allowed_actions[0].id == "a0"
    assert len(req.signals) == 2


def test_signal_goal_id_null_allowed():
    req = GoalSuggestionsRequest.model_validate(PFM_PAYLOAD)
    assert req.signals[1].goal_id is None


def test_feedback_goal_id_null_allowed():
    req = GoalSuggestionsRequest.model_validate(PFM_PAYLOAD)
    assert req.feedback[1].goal_id is None


def test_monthly_surplus_null_allowed():
    body = {**PFM_PAYLOAD, "customer": {**PFM_PAYLOAD["customer"], "monthly_surplus": None}}
    req = GoalSuggestionsRequest.model_validate(body)
    assert req.customer.monthly_surplus is None


def test_numeric_types_money_int_ratios_float():
    req = GoalSuggestionsRequest.model_validate(PFM_PAYLOAD)
    assert isinstance(req.customer.monthly_income, int)
    assert isinstance(req.goals[0].target_amount, int)
    assert isinstance(req.goals[0].value, int)
    assert isinstance(req.goals[0].progress_pct, float)
    assert isinstance(req.goals[0].months_left, float)


def test_extra_fields_are_ignored():
    body = {
        **PFM_PAYLOAD,
        "unknown_top": True,
        "customer": {**PFM_PAYLOAD["customer"], "extra_customer": 1},
        "signals": [{**PFM_PAYLOAD["signals"][0], "fingerprint": "fp-ignored", "extra": "x"}],
        "feedback": [{**PFM_PAYLOAD["feedback"][0], "note": "ignored"}],
    }
    req = GoalSuggestionsRequest.model_validate(body)
    assert not hasattr(req, "unknown_top")
    assert "fingerprint" not in req.signals[0].model_dump()
    assert "note" not in req.feedback[0].model_dump()


@pytest.mark.parametrize(
    "patch",
    [
        {"user_id": ""},  # min_length=1
        {"customer": {k: v for k, v in PFM_PAYLOAD["customer"].items() if k != "salary_day"}},
        {
            "signals": [
                {
                    "id": "s",
                    "kind": "salary",
                    "rank": 1,
                    "facts": {},
                    "allowed_actions": [],
                    # thiếu fallback
                }
            ]
        },
        {"goals": [{k: v for k, v in PFM_PAYLOAD["goals"][0].items() if k != "target_amount"}]},
    ],
)
def test_missing_or_invalid_required_fields_raise(patch):
    body = {**PFM_PAYLOAD, **patch}
    with pytest.raises(ValidationError):
        GoalSuggestionsRequest.model_validate(body)

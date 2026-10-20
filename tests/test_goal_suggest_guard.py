"""guard.py: số trong lời ⊆ facts (kể cả tiền Việt); action_ids ⊆ allowed_actions."""

from __future__ import annotations

from goal_suggest import guard


FACTS = {
    "salary_day": 5,
    "monthly_surplus": 4_500_000,
    "main_casa_balance": 12_000_000,
    "required_monthly": 3_000_000,
}
ALLOWED = ["a0", "a1"]


def test_number_not_in_facts_is_rejected():
    reason = guard.check(
        "Còn 9 tháng",
        "Bạn cần thêm 8.000.000 VND mỗi tháng.",
        ["a0"],
        facts=FACTS,
        allowed_action_ids=ALLOWED,
    )
    assert reason == "number_not_in_facts"


def test_number_from_facts_plain_passes():
    reason = guard.check(
        "Ngày lương 5",
        "Số dư chính 12000000 đủ để trích 3000000.",
        ["a0"],
        facts=FACTS,
        allowed_action_ids=ALLOWED,
    )
    assert reason is None


def test_vietnamese_money_format_passes_when_in_facts():
    # 12.000.000 và 4,5 triệu khớp facts main_casa_balance / monthly_surplus.
    reason = guard.check(
        "Số dư 12.000.000",
        "Thặng dư khoảng 4,5 triệu mỗi tháng.",
        ["a0", "a1"],
        facts=FACTS,
        allowed_action_ids=ALLOWED,
    )
    assert reason is None


def test_trieu_scale_matches_fact_int():
    reason = guard.check(
        "Cần 3 triệu/tháng",
        "Trích đều cho mục tiêu.",
        ["a0"],
        facts={"required_monthly": 3_000_000},
        allowed_action_ids=ALLOWED,
    )
    assert reason is None


def test_action_ids_must_be_subset_of_allowed():
    reason = guard.check(
        "Ngày lương 5",
        "Trích thêm cho mục tiêu.",
        ["a0", "a9"],
        facts=FACTS,
        allowed_action_ids=ALLOWED,
    )
    assert reason == "unknown_action"


def test_empty_or_too_long_rejected():
    assert (
        guard.check("  ", "body ok", ["a0"], facts=FACTS, allowed_action_ids=ALLOWED) == "empty"
    )
    assert (
        guard.check("t" * 61, "body ok", ["a0"], facts=FACTS, allowed_action_ids=ALLOWED)
        == "title_too_long"
    )
    assert (
        guard.check("ok", "b" * 221, ["a0"], facts=FACTS, allowed_action_ids=ALLOWED)
        == "body_too_long"
    )

"""The deterministic side of POST /jar-rebalance: what the shortfall is, what a correct proposal looks like, and
whether the model's proposal breaks a hard rule (drop/retry) or only the preferred order (retry, then accept)."""

from jar_checks import (
    check_cover,
    check_distribute,
    cover_plan,
    cover_shortfall,
    pool_available,
    receivers,
    wording_problems,
)


def _jar(id, label, limit, spent, remaining):
    return {"id": id, "label": label, "categoryIds": [], "budgetLimit": limit, "spent": spent, "remaining": remaining,
            "spendable": None if remaining is None else max(0, remaining), "overLimit": limit is not None and spent > limit}


def _summary(unallocated=13044000, jars=None):
    return {"month": "2026-09", "casaBalance": 18000000, "unallocated": unallocated, "allocationHeadroom": 1000000,
            "jars": jars if jars is not None else [
                _jar("food", "Ăn uống", 4000000, 2187000, 1813000),
                _jar("lifestyle", "Hưởng thụ", 2500000, 1204000, 1296000),
                _jar("move", "Di chuyển", 1000000, 204000, 796000),
                _jar("savings", "Tiết kiệm", None, 0, None),
            ]}


def _cover_ui(shortfall, moves, target="food", reason="x"):
    return {"type": "rebalance_jars", "target_jar_id": target, "shortfall": shortfall, "moves": moves, "reason": reason}


# --- shortfall: computed by code, never by the model ---------------------------------------------------------


def test_shortfall_for_a_planned_spend_is_the_spend_minus_the_jars_spendable():
    assert cover_shortfall(_summary(), "food", 16000000) == 14187000  # 16.000.000 - 1.813.000


def test_a_planned_spend_that_fits_needs_no_cover():
    assert cover_shortfall(_summary(), "food", 1000000) == 0


def test_shortfall_for_a_jar_that_needs_covering_is_minus_its_remaining():
    summary = _summary(jars=[_jar("food", "Ăn uống", 4000000, 4400000, -400000)])
    assert cover_shortfall(summary, "food", None) == 400000


def test_a_jar_with_money_and_no_planned_spend_needs_no_cover():
    assert cover_shortfall(_summary(), "food", None) == 0


def test_unknown_jar_or_a_jar_without_a_limit_has_no_shortfall_to_compute():
    assert cover_shortfall(_summary(), "khong-co", 1000) is None
    assert cover_shortfall(_summary(), "savings", 1000) is None  # no budgetLimit: set one first (edit_jar)


# --- the preferred plan: pool first, then the jars with the most money ---------------------------------------


def test_pool_available_never_counts_a_negative_pool():
    assert pool_available(_summary(unallocated=-500000)) == 0
    assert pool_available(_summary(unallocated=None)) == 0


def test_plan_takes_the_pool_first_then_the_largest_spendable_and_stops_when_covered():
    plan = cover_plan(_summary(), "food", 14187000)
    assert plan == [("pool", 13044000), ("lifestyle", 1143000)]  # not "move": 796.000 is smaller and not needed


def test_plan_never_takes_from_the_target_or_from_a_jar_without_a_balance():
    summary = _summary(unallocated=0)
    plan = cover_plan(summary, "food", 2000000)
    assert plan == [("lifestyle", 1296000), ("move", 704000)]  # "savings" (null) and "food" (the target) are skipped


def test_plan_is_none_when_all_sources_together_cannot_cover_the_shortfall():
    assert cover_plan(_summary(unallocated=0), "food", 5000000) is None  # only 2.092.000 elsewhere


# --- check_cover ------------------------------------------------------------------------------------------------


def test_a_proposal_that_follows_the_plan_is_clean():
    ui = _cover_ui(14187000, [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "lifestyle", "amount": 1143000}])
    verdict = check_cover(_summary(), "food", 14187000, ui)
    assert verdict.hard == [] and verdict.soft == []


def test_a_wrong_order_breaks_only_the_soft_rule():
    # takes the smaller jar first although the pool + the larger jar were enough (seen with the real model)
    ui = _cover_ui(14187000, [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "move", "amount": 796000}, {"from_jar_id": "lifestyle", "amount": 347000}])
    verdict = check_cover(_summary(), "food", 14187000, ui)
    assert verdict.hard == []
    assert verdict.soft and "lifestyle" in verdict.soft[0] and "1143000" in verdict.soft[0].replace(".", "")


def test_a_source_giving_more_than_its_spendable_is_a_hard_error():
    ui = _cover_ui(1500000, [{"from_jar_id": "move", "amount": 1500000}])  # move only has 796.000
    assert any("move" in e for e in check_cover(_summary(unallocated=0), "food", 1500000, ui).hard)


def test_the_pool_giving_more_than_the_unallocated_money_is_a_hard_error():
    ui = _cover_ui(1500000, [{"from_jar_id": "pool", "amount": 1500000}])
    assert any("pool" in e for e in check_cover(_summary(unallocated=1000000), "food", 1500000, ui).hard)


def test_a_shortfall_that_differs_from_the_computed_one_is_a_hard_error():
    ui = _cover_ui(15136000, [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "lifestyle", "amount": 1296000}, {"from_jar_id": "move", "amount": 796000}])
    assert any("shortfall" in e for e in check_cover(_summary(), "food", 14187000, ui).hard)


def test_an_invented_source_or_the_wrong_target_is_a_hard_error():
    invented = _cover_ui(500000, [{"from_jar_id": "du-phong", "amount": 500000}])
    assert check_cover(_summary(), "food", 500000, invented).hard
    other_target = _cover_ui(500000, [{"from_jar_id": "pool", "amount": 500000}], target="lifestyle")
    assert any("target_jar_id" in e for e in check_cover(_summary(), "food", 500000, other_target).hard)


def test_a_structurally_broken_ui_is_a_hard_error_and_does_not_crash():
    assert check_cover(_summary(), "food", 500000, {"type": "rebalance_jars"}).hard
    assert check_cover(_summary(), "food", 500000, _cover_ui(500000, [{"from_jar_id": "pool", "amount": 400000}])).hard  # sum != shortfall


# --- distribute: an amount the customer has, shared into the jars' balances ------------------------------------


def test_only_jars_with_a_limit_can_receive():
    assert [j["id"] for j in receivers(_summary())] == ["food", "lifestyle", "move"]


def _dist_ui(allocations, reason="x"):
    return {"type": "distribute_amount", "allocations": allocations, "reason": reason}


def test_a_full_distribution_is_clean():
    ui = _dist_ui([{"to_jar_id": "food", "amount": 600000}, {"to_jar_id": "move", "amount": 400000}])
    verdict = check_distribute(_summary(), 1000000, ui)
    assert verdict.hard == [] and verdict.soft == []


def test_giving_out_more_than_the_amount_is_a_hard_error():
    ui = _dist_ui([{"to_jar_id": "food", "amount": 1000001}])
    assert any("1.000.000" in e for e in check_distribute(_summary(), 1000000, ui).hard)


def test_the_amount_is_the_customers_own_so_the_unallocated_money_does_not_limit_it():
    ui = _dist_ui([{"to_jar_id": "food", "amount": 3000000}, {"to_jar_id": "lifestyle", "amount": 2000000}])
    for unallocated in (0, 100, -500000, None):
        verdict = check_distribute(_summary(unallocated=unallocated), 5000000, ui)
        assert verdict.hard == [] and verdict.soft == [], unallocated


def test_a_jar_without_a_limit_or_an_invented_jar_cannot_receive():
    assert check_distribute(_summary(), 1000000, _dist_ui([{"to_jar_id": "savings", "amount": 100}])).hard
    assert check_distribute(_summary(), 1000000, _dist_ui([{"to_jar_id": "khong-co", "amount": 100}])).hard


def test_leaving_some_of_the_amount_undistributed_is_only_a_soft_error():
    verdict = check_distribute(_summary(), 1000000, _dist_ui([{"to_jar_id": "food", "amount": 300000}]))
    assert verdict.hard == [] and verdict.soft


def test_a_structurally_broken_distribution_is_a_hard_error_and_does_not_crash():
    assert check_distribute(_summary(), 1000000, {"type": "distribute_amount"}).hard
    assert check_distribute(_summary(), 1000000, _dist_ui([])).hard


# --- what the customer reads (answer + reason): no internal vocabulary, and short -----------------------------


def test_clean_customer_text_has_no_wording_problem():
    assert wording_problems("Hũ Ăn uống thiếu 14.187.000đ.", "Lấy 13.044.000đ từ tiền chưa phân bổ và 1.143.000đ từ hũ Hưởng thụ.") == []


def test_internal_vocabulary_is_reported_by_name():
    problems = wording_problems("Hũ có spendable lớn nhất.", "Tổng amount đúng bằng shortfall, remaining = -200.000đ, theo `jar-summary` của pfm.")
    text = " ".join(problems)
    for word in ("spendable", "shortfall", "remaining", "pfm", "jar-summary", "amount", "backtick"):
        assert word in text, word


def test_a_reason_that_narrates_the_arithmetic_at_length_is_too_long():
    assert any("dài" in p for p in wording_problems("ok", "x" * 301))
    assert not any("dài" in p for p in wording_problems("ok", "x" * 300))

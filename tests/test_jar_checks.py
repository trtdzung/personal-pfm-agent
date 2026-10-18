"""The deterministic side of the two jar endpoints (jar_endpoint.py): what a correct proposal looks like, and whether the
model's proposal breaks a hard rule (drop/retry) or is only incomplete (retry, then accept)."""

from jar_checks import (
    check_distribute,
    check_rebalance,
    pool_available,
    receivers,
    source_available,
    wording_problems,
)


def _jar(id, label, limit, spent, balance):
    # the jar-summary shape since 2026-09-23 (backend_docs): `limit` (plan) and `balance` (money) are independent
    return {"id": id, "label": label, "categoryIds": [], "limit": limit, "spent": spent, "balance": balance,
            "spendable": None if balance is None else max(0, balance), "overLimit": limit is not None and spent > limit}


def _summary(unallocated=13044000, jars=None):
    return {"month": "2026-09", "casaBalance": 18000000, "unallocated": unallocated, "allocationHeadroom": unallocated,
            "jars": jars if jars is not None else [
                _jar("food", "Ăn uống", 4000000, 2187000, 1813000),
                _jar("lifestyle", "Hưởng thụ", 2500000, 1204000, 1296000),
                _jar("move", "Di chuyển", 1000000, 204000, 796000),
                _jar("savings", "Tiết kiệm", None, 0, None),
            ]}


def test_pool_available_never_counts_a_negative_pool():
    assert pool_available(_summary(unallocated=-500000)) == 0
    assert pool_available(_summary(unallocated=None)) == 0
    assert pool_available(_summary()) == 13044000


def test_source_available_is_the_spendable_of_the_jar_and_zero_when_unknown():
    assert source_available(_summary(), "food") == 1813000
    assert source_available(_summary(), "savings") == 0  # no balance yet: nothing to give
    assert source_available(_summary(), "khong-co") == 0


def test_every_jar_can_receive_money_even_one_with_no_balance_or_no_limit():
    # the deposit is how a jar gets its first balance (pfm's "Chia ngay" sheet lists every jar)
    assert [j["id"] for j in receivers(_summary())] == ["food", "lifestyle", "move", "savings"]
    mixed = _summary(jars=[_jar("solo", "Quỹ riêng", None, 0, 100000), _jar("new", "Hũ mới", 1000000, 0, None)])
    assert [j["id"] for j in receivers(mixed)] == ["solo", "new"]


# --- distribute: an amount of the unallocated money, shared into the jars' balances ------------------------------


def _dist_ui(allocations, reason="x"):
    return {"type": "distribute_amount", "allocations": allocations, "reason": reason}


def test_a_full_distribution_is_clean():
    ui = _dist_ui([{"to_jar_id": "food", "amount": 600000}, {"to_jar_id": "move", "amount": 400000}])
    verdict = check_distribute(_summary(), 1000000, ui)
    assert verdict.hard == [] and verdict.soft == []


def test_giving_out_more_than_the_amount_is_a_hard_error():
    ui = _dist_ui([{"to_jar_id": "food", "amount": 1000001}])
    assert any("1.000.000" in e for e in check_distribute(_summary(), 1000000, ui).hard)


def test_the_money_comes_from_the_unallocated_pool_so_more_than_the_pool_is_a_hard_error():
    ui = _dist_ui([{"to_jar_id": "food", "amount": 3000000}, {"to_jar_id": "lifestyle", "amount": 2000000}])
    assert check_distribute(_summary(unallocated=5000000), 5000000, ui).hard == []
    for unallocated in (4999999, 0, -500000, None):
        assert any("chưa phân bổ" in e for e in check_distribute(_summary(unallocated=unallocated), 5000000, ui).hard), unallocated


def test_a_jar_with_no_balance_yet_can_receive_but_an_invented_jar_cannot():
    assert check_distribute(_summary(), 1000000, _dist_ui([{"to_jar_id": "savings", "amount": 100}])).hard == []
    assert check_distribute(_summary(), 1000000, _dist_ui([{"to_jar_id": "khong-co", "amount": 100}])).hard


def test_leaving_some_of_the_amount_undistributed_is_only_a_soft_error():
    verdict = check_distribute(_summary(), 1000000, _dist_ui([{"to_jar_id": "food", "amount": 300000}]))
    assert verdict.hard == [] and verdict.soft


def test_a_structurally_broken_distribution_is_a_hard_error_and_does_not_crash():
    assert check_distribute(_summary(), 1000000, {"type": "distribute_amount"}).hard
    assert check_distribute(_summary(), 1000000, _dist_ui([{"to_jar_id": "pool", "amount": 1}])).hard


# --- rebalance: ONE jar gives an amount to one or more other jars ------------------------------------------------


def _reb_ui(allocations, source="food", reason="x"):
    return {"type": "rebalance_jars", "from_jar_id": source, "allocations": allocations, "reason": reason}


def test_a_full_transfer_from_one_jar_to_two_is_clean():
    ui = _reb_ui([{"to_jar_id": "move", "amount": 300000}, {"to_jar_id": "savings", "amount": 200000}])
    verdict = check_rebalance(_summary(), "food", 500000, ui)
    assert verdict.hard == [] and verdict.soft == []


def test_the_giver_can_give_at_most_its_spendable():
    ui = _reb_ui([{"to_jar_id": "move", "amount": 1813001}])
    assert any("1.813.000" in e for e in check_rebalance(_summary(), "food", 1813001, ui).hard)
    ok = _reb_ui([{"to_jar_id": "move", "amount": 1813000}])
    assert check_rebalance(_summary(), "food", 1813000, ok).hard == []


def test_a_giver_with_no_balance_yet_cannot_give():
    ui = _reb_ui([{"to_jar_id": "food", "amount": 100}], source="savings")
    assert check_rebalance(_summary(), "savings", 100, ui).hard


def test_the_source_must_be_the_one_the_request_asked_for_and_ids_must_exist():
    other = _reb_ui([{"to_jar_id": "food", "amount": 100000}], source="lifestyle")
    assert any("from_jar_id" in e for e in check_rebalance(_summary(), "food", 100000, other).hard)
    invented = _reb_ui([{"to_jar_id": "khong-co", "amount": 100000}])
    assert check_rebalance(_summary(), "food", 100000, invented).hard


def test_transferring_more_than_the_amount_is_a_hard_error_and_less_only_a_soft_one():
    more = _reb_ui([{"to_jar_id": "move", "amount": 600000}])
    assert check_rebalance(_summary(), "food", 500000, more).hard
    less = _reb_ui([{"to_jar_id": "move", "amount": 200000}])
    verdict = check_rebalance(_summary(), "food", 500000, less)
    assert verdict.hard == [] and verdict.soft


def test_a_structurally_broken_rebalance_is_a_hard_error_and_does_not_crash():
    assert check_rebalance(_summary(), "food", 100, {"type": "rebalance_jars"}).hard
    assert check_rebalance(_summary(), "food", 100, _reb_ui([{"to_jar_id": "food", "amount": 100}])).hard  # gives to itself
    old_shape = {"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 1, "moves": [{"from_jar_id": "pool", "amount": 1}], "reason": "x"}
    assert check_rebalance(_summary(), "food", 1, old_shape).hard


# --- what the customer reads (answer + reason): no internal vocabulary, and short -----------------------------


def test_clean_customer_text_has_no_wording_problem():
    assert wording_problems("Hũ Ăn uống thiếu 14.187.000đ.", "Lấy 13.044.000đ từ tiền chưa phân bổ và 1.143.000đ từ hũ Hưởng thụ.") == []


def test_internal_vocabulary_is_reported_by_name():
    problems = wording_problems("Hũ có spendable lớn nhất.", "Tổng amount đúng bằng shortfall, remaining = -200.000đ, balance 5, initial_balance 0, theo `jar-summary` của pfm.")
    text = " ".join(problems)
    for word in ("spendable", "shortfall", "remaining", "balance", "initial_balance", "pfm", "jar-summary", "amount", "backtick"):
        assert word in text, word


def test_a_reason_that_narrates_the_arithmetic_at_length_is_too_long():
    assert any("dài" in p for p in wording_problems("ok", "x" * 301))
    assert not any("dài" in p for p in wording_problems("ok", "x" * 300))

"""Calculators for the goal-plan skill: the chat composes the plans, these tools produce every figure.

`loan_quote` is the annuity payment pfm uses (rounded up to 1.000 VND); `savings_projection` models a monthly saving into
MSB term deposits (each monthly lot earns simple interest until the end date); `project_target` grows a price for the
"giá tăng X%/năm" scenario. None of them reads customer data: the skill passes the numbers in."""

from __future__ import annotations

import json
import math

from langchain_core.tools import tool

from tools import goal_plan_sim as sim
from tools.goal_plan_card import build_card

MAX_LOAN_RATE_PCT = 40.0
MAX_DEPOSIT_RATE_PCT = 15.0
MAX_TERM_MONTHS = 360
MAX_SAVING_MONTHS = 600
MAX_DEADLINE_MONTHS = 480
SIM_MODES = ("no_loan", "loan_at", "optimize")


def _vnd(value: float) -> str:
    return f"{round(value):,}".replace(",", ".") + " VND"


def _g(value: float) -> str:
    return f"{value:g}"


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def _invalid(why: str) -> str:
    return f"Tham số không hợp lệ: {why}. Kiểm tra lại số liệu, đừng tự tính thay."


def _annuity(principal: float, rate_pct: float, months: int) -> int:
    """Same as annuityPayment() in pfm: round up to 1.000 VND."""
    r = rate_pct / 100 / 12
    raw = principal / months if r == 0 else principal * r / (1 - (1 + r) ** -months)
    return math.ceil(raw / 1000) * 1000


@tool
def loan_quote(
    principal_vnd: float,
    annual_rate_pct: float,
    term_months: int,
    grace_months: int = 0,
    monthly_surplus_vnd: float = 0,
) -> str:
    """Quote an instalment loan (trả góp đều, niên kim): the monthly payment, total interest and total to repay. For a
    ONE-OFF side calculation when the customer asks something extra; figures INSIDE a plan (skill goal-plan) must come from
    simulate_goal_plan. Never use calculate_deposit_interest for a loan and never work out a payment yourself.

    Args:
        principal_vnd: Amount borrowed in VND (> 0).
        annual_rate_pct: Loan rate in percent per year, e.g. 8 for 8%/year (from search_msb_knowledge, or a stated assumption).
        term_months: Total term in months including any grace period (1-360).
        grace_months: Months at the start that pay interest only (0 for none); must be < term_months.
        monthly_surplus_vnd: The customer's monthly surplus (còn dư); when given, the quote compares the payment with it.
    """
    if not _finite(principal_vnd, annual_rate_pct, monthly_surplus_vnd):
        return _invalid("số liệu phải là số hữu hạn")
    if principal_vnd <= 0:
        return _invalid("số tiền vay phải > 0")
    if not 0 <= annual_rate_pct <= MAX_LOAN_RATE_PCT:
        return _invalid(f"lãi suất vay phải từ 0 đến {MAX_LOAN_RATE_PCT:g}%/năm")
    if not 1 <= term_months <= MAX_TERM_MONTHS:
        return _invalid(f"kỳ hạn phải từ 1 đến {MAX_TERM_MONTHS} tháng")
    if grace_months < 0 or grace_months >= term_months:
        return _invalid("ân hạn phải >= 0 và nhỏ hơn kỳ hạn")
    n = term_months - grace_months
    pay = _annuity(principal_vnd, annual_rate_pct, n)
    interest_only = round(principal_vnd * annual_rate_pct / 100 / 12) if grace_months else 0
    total_interest = interest_only * grace_months + pay * n - principal_vnd
    head = f"Vay {_vnd(principal_vnd)}, {_g(annual_rate_pct)}%/năm, {term_months} tháng"
    lines = [head + (f" (ân hạn gốc {grace_months} tháng)" if grace_months else "")]
    if grace_months:
        lines.append(f"Giai đoạn ân hạn {grace_months} tháng đầu: trả lãi {_vnd(interest_only)}/tháng.")
    lines += [
        f"Trả hằng tháng: {_vnd(pay)}",
        f"Tổng lãi phải trả: {_vnd(max(0, total_interest))}",
        f"Tổng phải trả: {_vnd(principal_vnd + max(0, total_interest))}",
    ]
    if monthly_surplus_vnd > 0:
        peak = max(pay, interest_only)
        verdict = "vượt phần còn dư" if peak > monthly_surplus_vnd else "nằm trong phần còn dư"
        lines.append(f"So với phần còn dư {_vnd(monthly_surplus_vnd)}/tháng: kỳ trả cao nhất {_vnd(peak)} {verdict} {_vnd(abs(peak - monthly_surplus_vnd))}.")
    lines.append("Mọi con số đã được tính sẵn: chép nguyên văn, không tự tính lại.")
    return "\n".join(lines)


@tool
def savings_projection(monthly_vnd: float, annual_rate_pct: float, months: int, initial_vnd: float = 0) -> str:
    """Project saving a fixed amount every month into MSB term deposits until the target date: each monthly deposit stays to
    the end and earns simple interest at the quoted rate, paid at the end. Returns the principal put in, the interest and the
    total received. For a ONE-OFF side calculation when the customer asks something extra; figures INSIDE a plan (skill
    goal-plan) must come from simulate_goal_plan. It uses simple interest per monthly deposit, unlike simulate_goal_plan
    (monthly compounding), so never mix the two numbers. Never multiply yourself.

    Args:
        monthly_vnd: Amount saved each month in VND (>= 0).
        annual_rate_pct: Deposit rate in percent per year (from search_msb_knowledge; use online 12-month consistently).
        months: Number of monthly deposits (1-600).
        initial_vnd: A lump sum deposited at the start (0 for none).
    """
    if not _finite(monthly_vnd, annual_rate_pct, initial_vnd):
        return _invalid("số liệu phải là số hữu hạn")
    if monthly_vnd < 0 or initial_vnd < 0 or (monthly_vnd == 0 and initial_vnd == 0):
        return _invalid("cần số tiền góp hoặc số tiền ban đầu > 0")
    if not 0 <= annual_rate_pct <= MAX_DEPOSIT_RATE_PCT:
        return _invalid(f"lãi suất tiết kiệm phải từ 0 đến {MAX_DEPOSIT_RATE_PCT:g}%/năm")
    if not 1 <= months <= MAX_SAVING_MONTHS:
        return _invalid(f"số tháng phải từ 1 đến {MAX_SAVING_MONTHS}")
    rate = annual_rate_pct / 100
    interest = initial_vnd * rate * months / 12 + sum(monthly_vnd * rate * (months - i) / 12 for i in range(months))
    principal = initial_vnd + monthly_vnd * months
    start = f" và {_vnd(initial_vnd)} ban đầu" if initial_vnd else ""
    return (
        f"Góp {_vnd(monthly_vnd)}/tháng x {months} tháng{start} ở {_g(annual_rate_pct)}%/năm (lãi đơn từng khoản gửi): "
        f"gốc {_vnd(principal)}, lãi {_vnd(interest)}, tổng nhận {_vnd(principal + interest)}.\n"
        "Mọi con số đã được tính sẵn: chép nguyên văn, không tự tính lại."
    )


@tool
def project_target(amount_vnd: float, growth_pct_per_year: float, years: float) -> str:
    """Scenario: the price of the goal after it grows by a yearly percentage ("nếu giá tăng 5%/năm"). For a ONE-OFF side
    calculation when the customer asks something extra; figures INSIDE a plan (skill goal-plan) must come from
    simulate_goal_plan. State clearly that it is a scenario, not a forecast.

    Args:
        amount_vnd: Today's price in VND (> 0).
        growth_pct_per_year: Yearly price growth in percent (-20 to 30).
        years: Number of years until the purchase (0.1-50).
    """
    if not _finite(amount_vnd, growth_pct_per_year, years):
        return _invalid("số liệu phải là số hữu hạn")
    if amount_vnd <= 0:
        return _invalid("giá hiện tại phải > 0")
    if not -20 <= growth_pct_per_year <= 30:
        return _invalid("mức tăng giá phải từ -20 đến 30%/năm")
    if not 0.1 <= years <= 50:
        return _invalid("số năm phải từ 0,1 đến 50")
    grown = round(amount_vnd * (1 + growth_pct_per_year / 100) ** years / 1000) * 1000
    return (
        f"Kịch bản giá tăng {_g(growth_pct_per_year)}%/năm: {_vnd(amount_vnd)} hôm nay thành {_vnd(grown)} sau {_g(years)} năm "
        f"(chênh {_vnd(grown - amount_vnd)}). Đây là kịch bản, không phải dự báo.\n"
        "Mọi con số đã được tính sẵn: chép nguyên văn, không tự tính lại."
    )


@tool
def simulate_goal_plan(
    mode: str,
    target_amount_vnd: float,
    months_to_deadline: int,
    start_cash_vnd: float,
    monthly_income_vnd: float,
    monthly_spending_vnd: float,
    existing_debt_payment_vnd: float = 0,
    deposit_rate_pct: float = 6.8,
    loan_rate_pct: float = 8,
    loan_term_months: int = 240,
    purchase_month: int = -1,
    target_growth_pct: float = 0,
    income_growth_pct: float = 0,
    spending_growth_pct: float = 0,
    reserve_months: float = 3,
    other_goals_monthly_vnd: float = 0,
) -> str:
    """Simulate a plan for a goal year by year and print every figure to quote: the emergency reserve is filled first, then
    the monthly surplus is saved into MSB deposits, optionally a loan covers the gap on the purchase month. Never work these
    numbers out yourself.

    Args:
        mode: "no_loan" (baseline: save everything, no loan; says in which year the goal is reached or how much is missing),
            "loan_at" (buy in `purchase_month` and borrow the gap; 0 = buy now with a loan, -1 = at the deadline) or
            "optimize" (tries several purchase months, keeps the feasible one with the lowest total cost of ownership).
        target_amount_vnd: Today's price of the goal in VND (> 0).
        months_to_deadline: Months until the deadline (1-480).
        start_cash_vnd: Cash usable now: main account + deposits (not shares, gold, house, car).
        monthly_income_vnd: Monthly income. monthly_spending_vnd: average monthly spending WITHOUT loan payments.
        existing_debt_payment_vnd: Total monthly payments of loans the customer already has.
        deposit_rate_pct: Savings rate %/year (online 12 months). loan_rate_pct, loan_term_months: the loan.
        target_growth_pct, income_growth_pct, spending_growth_pct: yearly growth assumptions in percent (-20 to 30).
        reserve_months: Emergency reserve in months of spending (default 3).
        other_goals_monthly_vnd: Total monthly contributions the customer already auto-debits to OTHER goals (>= 0); subtracted
            from the surplus so those goals are not counted twice.
    """
    if mode not in SIM_MODES:
        return _invalid("mode phải là no_loan, loan_at hoặc optimize")
    if not _finite(
        target_amount_vnd, start_cash_vnd, monthly_income_vnd, monthly_spending_vnd, existing_debt_payment_vnd, deposit_rate_pct,
        loan_rate_pct, target_growth_pct, income_growth_pct, spending_growth_pct, reserve_months, other_goals_monthly_vnd,
    ):
        return _invalid("số liệu phải là số hữu hạn")
    if target_amount_vnd <= 0 or monthly_income_vnd <= 0:
        return _invalid("giá mục tiêu và thu nhập phải > 0")
    if not 1 <= months_to_deadline <= MAX_DEADLINE_MONTHS:
        return _invalid(f"hạn phải từ 1 đến {MAX_DEADLINE_MONTHS} tháng")
    if start_cash_vnd < 0 or monthly_spending_vnd < 0 or existing_debt_payment_vnd < 0 or other_goals_monthly_vnd < 0:
        return _invalid("tiền hiện có, chi tiêu, khoản trả vay hiện có và khoản góp cho mục tiêu khác không được âm")
    if not 0 <= deposit_rate_pct <= MAX_DEPOSIT_RATE_PCT:
        return _invalid(f"lãi suất tiết kiệm phải từ 0 đến {MAX_DEPOSIT_RATE_PCT:g}%/năm")
    if not 0 <= loan_rate_pct <= MAX_LOAN_RATE_PCT:
        return _invalid(f"lãi suất vay phải từ 0 đến {MAX_LOAN_RATE_PCT:g}%/năm")
    if not 12 <= loan_term_months <= MAX_TERM_MONTHS:
        return _invalid(f"kỳ hạn vay phải từ 12 đến {MAX_TERM_MONTHS} tháng")
    if not all(-20 <= g <= 30 for g in (target_growth_pct, income_growth_pct, spending_growth_pct)):
        return _invalid("mức tăng mỗi năm phải từ -20 đến 30%")
    if not 0 <= reserve_months <= 12:
        return _invalid("quỹ dự phòng phải từ 0 đến 12 tháng chi tiêu")
    pm = months_to_deadline if purchase_month < 0 else purchase_month
    if mode == "loan_at" and pm > months_to_deadline:
        return _invalid("tháng mua không được sau hạn")
    p = sim.Inputs(
        target=target_amount_vnd, months=months_to_deadline, start_cash=start_cash_vnd, income=monthly_income_vnd,
        spending=monthly_spending_vnd, debt=existing_debt_payment_vnd, deposit_rate=deposit_rate_pct, loan_rate=loan_rate_pct,
        loan_term=loan_term_months, target_growth=target_growth_pct, income_growth=income_growth_pct,
        spending_growth=spending_growth_pct, reserve_months=reserve_months, other_goals=other_goals_monthly_vnd,
    )
    if mode == "no_loan":
        return sim.render_no_loan(p, sim.no_loan(p))
    if mode == "loan_at":
        return sim.render_loan(p, sim.loan_at(p, pm))
    best, rows = sim.optimize(p)
    return sim.render_optimize(p, best, rows)


_VERDICT_TEXT = {"recommended": "khuyến nghị", "ok": "phù hợp", "late": "trễ hạn", "not_recommended": "không khuyến nghị"}


@tool(response_format="content_and_artifact")
def build_goal_plan_card(
    goal_name: str,
    target_amount_vnd: float,
    months_to_deadline: int,
    start_cash_vnd: float,
    monthly_income_vnd: float,
    monthly_spending_vnd: float,
    existing_debt_payment_vnd: float = 0,
    other_goals_monthly_vnd: float = 0,
    extra_assets_vnd: float = 0,
    deposit_rate_pct: float = 6.8,
    loan_rate_pct: float = 8,
    loan_term_months: int = 240,
    target_growth_pct: float = 0,
    income_growth_pct: float = 0,
    spending_growth_pct: float = 0,
    reserve_months: float = 3,
) -> tuple[str, dict | None]:
    """Build the whole plan answer as ONE `plan_roadmap` card (skill goal-plan): runs the baseline (no loan), the loan-now plan and
    the optimized plan, plus a bad scenario for each, and returns the ready ```ui-json block with every figure computed. Call it ONCE
    per answer and paste the block UNCHANGED as the last thing in the reply; never edit, shorten or re-type a number in it.

    Args:
        goal_name: Name of the goal, used in the card title (e.g. "Căn hộ 1,2 tỷ").
        target_amount_vnd: Today's price of the goal in VND (> 0).
        months_to_deadline: Months until the deadline (1-480).
        start_cash_vnd: Cash usable now: main account + deposits (not shares, gold, house, car).
        monthly_income_vnd: Monthly income. monthly_spending_vnd: average monthly spending WITHOUT loan payments.
        existing_debt_payment_vnd: Total monthly payments of loans the customer already has.
        other_goals_monthly_vnd: Total monthly contributions already auto-debited to OTHER goals (>= 0).
        extra_assets_vnd: Value today of assets the customer already has FOR THIS GOAL (the goal account balance plus assets they declared: deposits, gold, shares, funds) (>= 0). It goes to the goal and never fills the emergency reserve.
        deposit_rate_pct: Savings rate %/year (online 12 months). loan_rate_pct, loan_term_months (12-360): the loan.
        target_growth_pct, income_growth_pct, spending_growth_pct: yearly growth assumptions in percent (-20 to 30).
        reserve_months: Emergency reserve in months of spending (default 3).
    """
    if not _finite(
        target_amount_vnd, start_cash_vnd, monthly_income_vnd, monthly_spending_vnd, existing_debt_payment_vnd, deposit_rate_pct,
        loan_rate_pct, target_growth_pct, income_growth_pct, spending_growth_pct, reserve_months, other_goals_monthly_vnd, extra_assets_vnd,
    ):
        return _invalid("số liệu phải là số hữu hạn"), None
    if target_amount_vnd <= 0 or monthly_income_vnd <= 0:
        return _invalid("giá mục tiêu và thu nhập phải > 0"), None
    if not 1 <= months_to_deadline <= MAX_DEADLINE_MONTHS:
        return _invalid(f"hạn phải từ 1 đến {MAX_DEADLINE_MONTHS} tháng"), None
    if start_cash_vnd < 0 or monthly_spending_vnd < 0 or existing_debt_payment_vnd < 0 or other_goals_monthly_vnd < 0 or extra_assets_vnd < 0:
        return _invalid("tiền hiện có, chi tiêu, khoản trả vay hiện có, khoản góp cho mục tiêu khác và tài sản sẵn có không được âm"), None
    if not 0 <= deposit_rate_pct <= MAX_DEPOSIT_RATE_PCT:
        return _invalid(f"lãi suất tiết kiệm phải từ 0 đến {MAX_DEPOSIT_RATE_PCT:g}%/năm"), None
    if not 0 <= loan_rate_pct <= MAX_LOAN_RATE_PCT:
        return _invalid(f"lãi suất vay phải từ 0 đến {MAX_LOAN_RATE_PCT:g}%/năm"), None
    if not 12 <= loan_term_months <= MAX_TERM_MONTHS:
        return _invalid(f"kỳ hạn vay phải từ 12 đến {MAX_TERM_MONTHS} tháng"), None
    if not all(-20 <= g <= 30 for g in (target_growth_pct, income_growth_pct, spending_growth_pct)):
        return _invalid("mức tăng mỗi năm phải từ -20 đến 30%"), None
    if not 0 <= reserve_months <= 12:
        return _invalid("quỹ dự phòng phải từ 0 đến 12 tháng chi tiêu"), None
    p = sim.Inputs(
        target=target_amount_vnd, months=months_to_deadline, start_cash=start_cash_vnd, income=monthly_income_vnd,
        spending=monthly_spending_vnd, debt=existing_debt_payment_vnd, deposit_rate=deposit_rate_pct, loan_rate=loan_rate_pct,
        loan_term=loan_term_months, target_growth=target_growth_pct, income_growth=income_growth_pct,
        spending_growth=spending_growth_pct, reserve_months=reserve_months, other_goals=other_goals_monthly_vnd, extra_assets=extra_assets_vnd,
    )
    card = build_card(p, goal_name)
    lines = [f"Kịch bản gốc: {card['baseline']}."]
    lines += [f"- {x['name']} ({_VERDICT_TEXT[x['verdict']]}): {x['headline']}." for x in card["plans"]]
    best = next((x for x in card["plans"] if x["verdict"] == "recommended"), None)
    lines.append(
        (f"Phương án khuyến nghị: {best['name']}." if best else "Không phương án nào vừa đúng hạn vừa khả thi dòng tiền.")
        + " Dán nguyên khối ui-json dưới đây ở cuối câu trả lời, không sửa."
    )
    return "\n".join(lines) + "\n```ui-json\n" + json.dumps(card, ensure_ascii=False) + "\n```", card

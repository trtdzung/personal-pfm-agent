"""Year-by-year simulation behind the goal-plan skill: emergency reserve first, then the monthly surplus saved into MSB deposits,
optionally a loan taken when the goal is bought. Pure functions (no I/O); `tools/goal_plan_tools.py` wraps them as a tool.

Rules, kept simple and stated to the customer as assumptions:
- the emergency reserve (`reserve_months` x monthly spending) is filled first from the starting cash and then from the surplus;
- what is saved earns the deposit rate, compounded monthly at the equivalent of the yearly rate;
- income and spending change once a year; the surplus is income - spending - existing loan payments;
- the goal price grows at `target_growth` per year;
- a loan covers the gap between the price and the savings on the purchase month, repaid as an annuity (rounded up to 1.000 VND like pfm);
- a plan is feasible when the payment stays within MAX_SURPLUS_SHARE of the surplus and (payment + existing payments) within MAX_DTI of
  the income (both the same limits pfm uses) and the loan is at most MAX_LOAN_SHARE of the price.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_SURPLUS_SHARE = 0.7
MAX_DTI = 0.4
MAX_LOAN_SHARE = 0.8
EXTRA_MONTHS = 120
STEP = 6
MAX_TABLE_YEARS = 15


@dataclass(frozen=True)
class Inputs:
    target: float
    months: int
    start_cash: float
    income: float
    spending: float
    debt: float = 0
    deposit_rate: float = 6.8
    loan_rate: float = 8
    loan_term: int = 240
    target_growth: float = 0
    income_growth: float = 0
    spending_growth: float = 0
    reserve_months: float = 3
    other_goals: float = 0
    extra_assets: float = 0


def vnd(value: float) -> str:
    return f"{round(value):,}".replace(",", ".") + " VND"


def annuity(principal: float, rate_pct: float, months: int) -> int:
    """Same as annuityPayment() in pfm: round up to 1.000 VND."""
    r = rate_pct / 100 / 12
    raw = principal / months if r == 0 else principal * r / (1 - (1 + r) ** -months)
    return math.ceil(raw / 1000) * 1000


def price(p: Inputs, m: int) -> float:
    return p.target * (1 + p.target_growth / 100) ** (m / 12)


def income(p: Inputs, m: int) -> float:
    return p.income * (1 + p.income_growth / 100) ** ((max(m, 1) - 1) // 12)


def spending(p: Inputs, m: int) -> float:
    return p.spending * (1 + p.spending_growth / 100) ** ((max(m, 1) - 1) // 12)


def surplus(p: Inputs, m: int) -> float:
    return income(p, m) - spending(p, m) - p.debt - p.other_goals


def accumulate(p: Inputs, upto: int):
    """([(reserve, saved, interest_earned)] for month 0..upto, reserve target)."""
    reserve = p.reserve_months * p.spending
    r = min(p.start_cash, reserve)
    # assets the customer already has for this goal go straight to the goal; they never fill the emergency reserve
    b = max(0.0, p.start_cash - reserve) + p.extra_assets
    earned = 0.0
    g = (1 + p.deposit_rate / 100) ** (1 / 12)
    out = [(r, b, earned)]
    for m in range(1, upto + 1):
        gain = b * (g - 1)
        b += gain
        earned += gain
        c = surplus(p, m)
        if c < 0:
            take = min(b, -c)
            b -= take
            r = max(0.0, r - (-c - take))
        else:
            fill = min(c, reserve - r)
            r += fill
            b += c - fill
        out.append((r, b, earned))
    return out, reserve


def no_loan(p: Inputs) -> dict:
    states, reserve = accumulate(p, p.months + EXTRA_MONTHS)
    reach = next((m for m, (_, b, _) in enumerate(states) if b >= price(p, m)), None)
    _, b, e = states[p.months]
    return dict(reach_month=reach, saved=b, price=price(p, p.months), shortfall=max(0.0, price(p, p.months) - b), earned=e, reserve=reserve, states=states)


def loan_at(p: Inputs, pm: int) -> dict:
    states, reserve = accumulate(p, pm)
    r, b, e = states[pm]
    pr = price(p, pm)
    gap = max(0.0, pr - b)
    pay = annuity(gap, p.loan_rate, p.loan_term) if gap > 0 else 0
    interest = max(0.0, pay * p.loan_term - gap) if gap > 0 else 0.0
    why = []
    breach = None
    if gap > MAX_LOAN_SHARE * pr:
        why.append("số vay vượt 80% giá mục tiêu")
    over_surplus = over_dti = False
    for m in range(pm + 1, pm + p.loan_term + 1):
        a = pay > MAX_SURPLUS_SHARE * max(0.0, surplus(p, m))
        d = (pay + p.debt) / income(p, m) > MAX_DTI
        over_surplus |= a
        over_dti |= d
        if (a or d) and breach is None:
            breach = m
    if over_surplus:
        why.append("kỳ trả vay vượt 70% phần còn dư")
    if over_dti:
        why.append("trả vay trên thu nhập vượt 40%")
    return dict(breach_month=breach, purchase_month=pm, price=pr, saved=b, loan=gap, payment=pay, interest=interest, earned=e, reserve=reserve, reserve_now=r, feasible=not why, why=why, cost=pr + interest - e, states=states)


def optimize(p: Inputs):
    step = max(STEP, 6 * math.ceil(p.months / 90))
    cands = set(range(0, p.months, step)) | {p.months}
    reach = no_loan(p)["reach_month"]
    if reach is not None and reach <= p.months:
        cands = {m for m in cands if m < reach} | {reach}
    cands = sorted(cands)
    rows = [loan_at(p, m) for m in cands]
    ok = [x for x in rows if x["feasible"]]
    return (min(ok, key=lambda x: x["cost"]) if ok else None), rows


# ---- text for the model: every figure the plan quotes is printed here ----

def _assumptions(p: Inputs) -> str:
    return (
        f"Giả định: lãi tiết kiệm {p.deposit_rate:g}%/năm; lãi vay {p.loan_rate:g}%/năm kỳ hạn {p.loan_term} tháng; giá mục tiêu tăng {p.target_growth:g}%/năm; "
        f"thu nhập tăng {p.income_growth:g}%/năm; chi tiêu tăng {p.spending_growth:g}%/năm; quỹ dự phòng {p.reserve_months:g} tháng chi tiêu."
    )


def _reserve_line(p: Inputs, reserve: float) -> str:
    have = min(p.start_cash, reserve)
    line = f"Quỹ dự phòng: cần {vnd(reserve)}, đang có {vnd(have)} (từ tiền hiện có, chưa tính vào mục tiêu)"
    gap = reserve - have
    if gap <= 0:
        return line + "."
    if surplus(p, 1) <= 0:
        return line + f"; còn thiếu {vnd(gap)}, nhưng phần còn dư hằng tháng không dương nên chưa thể lấp quỹ dự phòng."
    return line + f"; còn thiếu {vnd(gap)}, lấp bằng các tháng góp đầu trước khi tiền vào mục tiêu."



def _year_rows(p: Inputs, states, upto: int) -> list[str]:
    rows = []
    for y in range(1, min((upto + 11) // 12, MAX_TABLE_YEARS) + 1):
        m = min(y * 12, upto)
        rows.append(f"- Năm {y} (tháng {m}): tiết kiệm {vnd(states[m][1])}; giá mục tiêu {vnd(price(p, m))}; còn dư hằng tháng {vnd(surplus(p, m))}")
    if upto > MAX_TABLE_YEARS * 12:
        rows.append(f"(Bảng chỉ hiển thị {MAX_TABLE_YEARS} năm đầu.)")
    return rows


def render_no_loan(p: Inputs, res: dict) -> str:
    lines = ["MÔ PHỎNG KHÔNG VAY (kịch bản gốc: góp hết phần còn dư sau quỹ dự phòng)", _assumptions(p), _reserve_line(p, res["reserve"])]
    reach = res["reach_month"]
    if reach is None:
        lines.append(f"Không đạt mục tiêu trong {p.months + EXTRA_MONTHS} tháng.")
    elif reach == 0:
        lines.append("Đã đủ tiền cho mục tiêu ngay từ bây giờ, không cần góp thêm.")
    elif reach <= p.months:
        lines.append(f"Đạt mục tiêu ở tháng {reach} (năm thứ {(reach + 11) // 12}), đúng hạn.")
    else:
        lines.append(f"Đạt mục tiêu ở tháng {reach} (năm thứ {(reach + 11) // 12}), trễ {reach - p.months} tháng so với hạn.")
    lines.append(f"Đến hạn (tháng {p.months}): tiết kiệm {vnd(res['saved'])}; giá mục tiêu {vnd(res['price'])}; thiếu {vnd(res['shortfall'])}; lãi tiết kiệm nhận được {vnd(res['earned'])}.")
    lines += _year_rows(p, res["states"], p.months)
    lines += ["Lộ trình các mốc (đây chính là phương án, viết liền một khối):", f"- Tháng 0: lập quỹ dự phòng {vnd(res['reserve'])}."]
    if reach != 0:
        lines.append(f"- Từ tháng 1: góp phần còn dư hằng tháng vào tiết kiệm (năm 1 khoảng {vnd(surplus(p, 1))}/tháng).")
    if p.months > 12 and reach != 0:
        lines.append(f"- Tháng {p.months - 12}: còn 12 tháng đến hạn, cân nhắc chuyển phần tiết kiệm sang kỳ hạn ngắn để lãi ít biến động.")
    lines.append(f"- Tháng {reach if reach is not None else p.months}: " + ("số dư đủ giá mục tiêu, rút tiền gửi để mua." if reach is not None else "chưa đủ, cần điều chỉnh hạn, số tiền hoặc thu nhập."))
    lines.append("Mọi con số đã được tính sẵn: chép nguyên văn, không tự tính lại.")
    return "\n".join(lines)


def render_loan(p: Inputs, res: dict, header: str = "MÔ PHỎNG CÓ VAY") -> str:
    pm = res["purchase_month"]
    when = "ngay bây giờ" if pm == 0 else f"ở tháng {pm} (năm thứ {(pm + 11) // 12})"
    lines = [f"{header}: mua {when}", _assumptions(p), _reserve_line(p, res["reserve"])]
    lines.append(f"Tại thời điểm mua: tiết kiệm {vnd(res['saved'])}; giá mục tiêu {vnd(res['price'])}; lãi tiết kiệm đã nhận {vnd(res['earned'])}.")
    if res["loan"] <= 0:
        lines.append("Không cần vay: tiết kiệm đã đủ giá mục tiêu.")
    else:
        lines.append(f"Cần vay {vnd(res['loan'])} ({res['loan'] / res['price']:.0%} giá mục tiêu): lãi {p.loan_rate:g}%/năm, {p.loan_term} tháng, trả vay {vnd(res['payment'])}/tháng, tổng lãi vay {vnd(res['interest'])}.")
        lines.append(f"Tổng chi phí sở hữu (giá mục tiêu + lãi vay - lãi tiết kiệm đã nhận): {vnd(res['cost'])}.")
        lines.append("Khả thi dòng tiền: " + ("Có." if res["feasible"] else "KHÔNG (" + "; ".join(res["why"]) + ")."))
        if not res["feasible"] and res.get("breach_month") is not None:
            lines.append(f"Kỳ trả vay bắt đầu vượt ngưỡng từ tháng {res['breach_month']}.")
    lines += _year_rows(p, res["states"], pm)
    lines.append("Lộ trình các mốc (đây chính là phương án, viết liền một khối):")
    lines.append(f"- Tháng 0: lập quỹ dự phòng {vnd(res['reserve'])}.")
    if pm > 0:
        lines.append(f"- Tháng 1 đến {pm}: góp phần còn dư hằng tháng vào tiết kiệm (năm 1 khoảng {vnd(surplus(p, 1))}/tháng).")
    if pm > 12:
        lines.append(f"- Tháng {pm - 12}: còn 12 tháng đến lúc mua, cân nhắc chuyển tiết kiệm sang kỳ hạn ngắn.")
    lines.append(f"- Tháng {pm}: mua mục tiêu" + (f", làm hồ sơ vay {vnd(res['loan'])} ở màn Mục tiêu → Vay." if res["loan"] > 0 else "."))
    if res["loan"] > 0:
        lines.append(f"- Tháng {pm + 1} đến {pm + p.loan_term}: trả vay {vnd(res['payment'])}/tháng; tháng {pm + p.loan_term} tất toán.")
    lines.append("Mọi con số đã được tính sẵn: chép nguyên văn, không tự tính lại.")
    return "\n".join(lines)


def render_optimize(p: Inputs, best: dict | None, rows: list[dict]) -> str:
    months = [x["purchase_month"] for x in rows]
    shown = ", ".join(map(str, months)) if len(months) <= 4 else ", ".join(map(str, months[:3])) + f", ... {months[-1]}"
    lines = [f"MÔ PHỎNG KẾT HỢP TỐI ƯU: thử mua ở các tháng {shown}; chọn tháng khả thi có tổng chi phí sở hữu thấp nhất."]
    for x in rows:
        lines.append(f"- Mua tháng {x['purchase_month']}: vay {vnd(x['loan'])}, trả {vnd(x['payment'])}/tháng, " + ("khả thi" if x["feasible"] else "không khả thi") + f", chi phí sở hữu {vnd(x['cost'])}")
    if best is None:
        lines.append("Không tháng nào khả thi với dòng tiền này: nói thẳng, đề nghị điều chỉnh hạn, số tiền mục tiêu hoặc thu nhập.")
        lines.append("Mọi con số đã được tính sẵn: chép nguyên văn, không tự tính lại.")
        return "\n".join(lines)
    lines.append("Phương án được chọn:")
    lines.append(render_loan(p, best, "KẾT HỢP TỐI ƯU"))
    return "\n".join(lines)

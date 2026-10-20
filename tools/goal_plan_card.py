"""Builds the `plan_roadmap` ui block from `goal_plan_sim`: every figure comes from the simulator, the model only pastes the block."""

from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from tools import goal_plan_sim as sim


def _r2(x: float) -> Decimal:
    # half-up on the decimal text, so 1.805 gives 1.81 (binary floats would give 1.80)
    return Decimal(repr(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _num(d: Decimal) -> str:
    return f"{d:f}".rstrip("0").rstrip(".").replace(".", ",")


def short_vnd(x: float) -> str:
    """Vietnamese short money: 352 triệu, 2,94 triệu, 1,2 tỷ, 12 nghìn, 500 đ (comma decimal, at most 2 decimals)."""
    sign = "-" if x < 0 else ""
    v = abs(x)
    units = ((1e9, "tỷ"), (1e6, "triệu"), (1e3, "nghìn"))
    if v < 1000:
        whole = int(Decimal(repr(float(v))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if whole < 1000:
            return f"{sign}{whole} đ"
        v = 1000.0  # 999,5 rounds up to a whole "1 nghìn", not "1000 đ"
    for i, (size, name) in enumerate(units):
        if v >= size:
            scaled = _r2(v / size)
            if scaled >= 1000 and i > 0:  # 999.999.999 -> "1 tỷ", not "1000 triệu"
                size, name = units[i - 1]
                scaled = _r2(v / size)
            return f"{sign}{_num(scaled)} {name}"
    return f"{sign}0 đ"


# ---- the card ----

BAD_LOAN_RATE_DELTA = 2
BAD_DEPOSIT_RATE_DELTA = 1
RISK_PREFIX = "Nếu thu nhập không tăng, lãi vay +2 điểm và lãi tiết kiệm -1 điểm: "
MAX_MILESTONES = 10
MAX_MONTH = 480
MAX_GOAL_ID = 64


def _mo(m: int) -> int:
    return max(0, min(MAX_MONTH, m))


def _year(m: int) -> int:
    return (m + 11) // 12


def _pct(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _runs(p: sim.Inputs) -> dict:
    opt, rows = sim.optimize(p)
    return dict(p=p, nl=sim.no_loan(p), now=sim.loan_at(p, 0), opt=opt, rows=rows)


def _nl_cost(p: sim.Inputs, nl: dict) -> float | None:
    r = nl["reach_month"]
    return None if r is None else sim.price(p, r) - nl["states"][r][2]


def _earned_at(p: sim.Inputs, month: int) -> float:
    """Deposit interest earned by `month` under the assumptions in `p` (same horizon for the base and the bad scenario)."""
    return sim.accumulate(p, month)[0][month][2]


def _nl_earned(p: sim.Inputs, nl: dict) -> float:
    r = nl["reach_month"]
    return nl["states"][r if r is not None else p.months][2]


def _nl_headline(p: sim.Inputs, nl: dict) -> str:
    r = nl["reach_month"]
    if r is None:
        return "Chưa đạt mục tiêu"
    if r == 0:
        return "Đã đủ tiền cho mục tiêu ngay từ bây giờ, đúng hạn"
    if r <= p.months:
        return f"Đạt mục tiêu ở tháng {r} (năm thứ {_year(r)}), đúng hạn"
    return f"Đạt mục tiêu ở tháng {r} (năm thứ {_year(r)}), trễ {r - p.months} tháng so với hạn"


def _loan_headline(res: dict, now: bool = False) -> str:
    pm = res["purchase_month"]
    if res["loan"] <= 0 and now:
        return "Không cần vay: đã đủ tiền ngay từ bây giờ"
    when = "Mua ngay hôm nay" if pm == 0 else f"Mua ở tháng {pm} (năm thứ {_year(pm)})"
    return when + (f", vay {short_vnd(res['loan'])}" if res["loan"] > 0 else ", không cần vay")


def _milestones(p: sim.Inputs, pm: int, reserve: float, loan: dict | None, loan_why: str = "") -> list[dict]:
    out: list[dict] = []
    if reserve > 0:
        have = min(p.start_cash, reserve)
        out.append(dict(when="Tháng 0", kind="reserve", title="Lập quỹ dự phòng", month=0, detail=f"Cần {short_vnd(reserve)}, đang có {short_vnd(have)} (chưa tính vào mục tiêu)"))
    s1 = sim.surplus(p, 1)
    if pm >= 1:
        save = dict(when="Tháng 1" if pm == 1 else f"Tháng 1–{pm}", kind="save", title="Góp phần còn dư vào tiết kiệm")
        if s1 > 0:
            save["detail"] = f"Năm đầu khoảng {short_vnd(s1)}/tháng"
            save["action"] = f"Góp khoảng {short_vnd(s1)}/tháng vào tiết kiệm MSB"
        else:
            save["detail"] = "Phần còn dư hằng tháng chưa dương"
        save["month"] = 1
        if pm > 1:
            save["end_month"] = _mo(pm)
        out.append(save)
    if pm > 12:
        out.append(dict(when=f"Tháng {pm - 12}", kind="switch", month=_mo(pm - 12), title="Còn 12 tháng đến lúc mua", action="Chuyển phần tiết kiệm sang kỳ hạn ngắn"))
    out.append(dict(when="Tháng 0" if pm == 0 else f"Tháng {pm} (năm thứ {_year(pm)})", kind="buy", month=_mo(pm), title="Mua mục tiêu"))
    if loan is not None and loan["loan"] > 0:
        term = p.loan_term
        out.append(dict(when=f"Tháng {pm}", kind="loan", month=_mo(pm), title=f"Vay {short_vnd(loan['loan'])}", detail=loan_why, action="Làm hồ sơ vay ở Mục tiêu → Vay"))
        out.append(dict(when=f"Tháng {pm + 1}–{pm + term}", kind="repay", month=_mo(pm + 1), end_month=_mo(pm + term), title="Trả vay", detail=f"Trả vay {short_vnd(loan['payment'])}/tháng"))
        out.append(dict(when=f"Tháng {pm + term}", kind="done", month=_mo(pm + term), title="Tất toán khoản vay"))
    for m in out:
        if not m.get("detail"):
            m.pop("detail", None)
    while len(out) > MAX_MILESTONES:  # drop `switch` first, then the oldest middle rows
        drop = next((i for i, m in enumerate(out) if m["kind"] == "switch"), 1)
        out.pop(drop)
    return out


def _loan_metrics(res: dict, run_bad_earned: float) -> list[dict]:
    m = []
    lo, hi = sorted((run_bad_earned, res["earned"]))
    if hi > 0:
        m.append(dict(label="Lãi tiết kiệm", value=short_vnd(lo) if round(lo) == round(hi) else f"{short_vnd(lo)}–{short_vnd(hi)}"))
    if res["loan"] > 0:
        m.append(dict(label="Số vay", value=short_vnd(res["loan"])))
        m.append(dict(label="Trả vay", value=f"{short_vnd(res['payment'])}/tháng"))
        m.append(dict(label="Tổng lãi vay", value=short_vnd(res["interest"])))
        m.append(dict(label="Chi phí sở hữu", value=short_vnd(res["cost"])))
    if len(m) > 4:  # the total cost already contains the interest: drop "Tổng lãi vay"
        m = [x for x in m if x["label"] != "Tổng lãi vay"]
    return m[:4]


def _loan_risk(bad_res: dict | None, optimized: bool) -> str:
    if bad_res is None:
        return RISK_PREFIX + "không còn tháng nào khả thi"
    pre = f"mua ở tháng {bad_res['purchase_month']}, " if optimized else ""
    if bad_res["loan"] <= 0:
        return RISK_PREFIX + pre + "không cần vay"
    pay = f"trả vay {short_vnd(bad_res['payment'])}/tháng, "
    return RISK_PREFIX + pre + pay + ("vẫn khả thi" if bad_res["feasible"] else "không còn khả thi")


def _choice(name: str, headline: str) -> str:
    return f"Tôi chọn phương án {name}: {headline[:1].lower()}{headline[1:]}"[:120]


def _deadline(months: int) -> str:
    return f"{months // 12} năm" if months >= 12 and months % 12 == 0 else f"{months} tháng"


def build_card(p: sim.Inputs, goal_name: str, goal_id: str) -> dict:
    base = _runs(p)
    bad = _runs(replace(p, income_growth=0, loan_rate=p.loan_rate + BAD_LOAN_RATE_DELTA, deposit_rate=max(0, p.deposit_rate - BAD_DEPOSIT_RATE_DELTA)))
    nl, now, opt = base["nl"], base["now"], base["opt"]
    reserve = nl["reserve"]
    reach = nl["reach_month"]
    horizon = p.months + sim.EXTRA_MONTHS

    plans: list[dict] = []
    meta: dict[str, tuple[int, float]] = {}  # id -> (purchase month, cost) for the plans that can be recommended

    # no_loan
    nl_head = _nl_headline(p, nl)
    if reach is None:
        plan = dict(id="no_loan", name="Không vay", verdict="not_recommended", headline=nl_head, reason=f"Không đạt mục tiêu trong {horizon} tháng", metrics=[], milestones=[])
    else:
        verdict = "ok" if reach <= p.months else "late"
        bad_r = bad["nl"]["reach_month"]
        if bad_r is None:
            bad_text = "chưa đạt mục tiêu"
        elif bad_r == 0:
            bad_text = "đã đủ tiền ngay từ bây giờ"
        else:
            bad_text = f"đạt mục tiêu ở tháng {bad_r} (năm thứ {_year(bad_r)})"
        risk = RISK_PREFIX + bad_text
        horizon = reach if reach is not None else p.months
        earned_lo, earned_hi = sorted((_earned_at(bad["p"], horizon), _earned_at(p, horizon)))
        metrics = []
        if earned_hi > 0:
            metrics.append(dict(label="Lãi tiết kiệm", value=short_vnd(earned_lo) if round(earned_lo) == round(earned_hi) else f"{short_vnd(earned_lo)}–{short_vnd(earned_hi)}"))
        plan = dict(id="no_loan", name="Không vay", verdict=verdict, headline=nl_head, metrics=metrics, milestones=_milestones(p, reach, reserve, None), risk=risk, choice_text=_choice("Không vay", nl_head))
        if verdict == "ok":
            meta["no_loan"] = (reach, _nl_cost(p, nl))
    plans.append(plan)

    # loan_now: only worth showing when borrowing everything now is actually feasible and needs a loan
    head = _loan_headline(now, now=True)
    if now["feasible"] and now["loan"] > 0:
        plan = dict(id="loan_now", name="Vay mua ngay", verdict="ok", headline=head, metrics=_loan_metrics(now, _earned_at(bad["p"], 0)),
                    milestones=_milestones(p, 0, reserve, now, "Vay phần chênh giữa giá mục tiêu và tiền tiết kiệm đang có"),
                    risk=_loan_risk(bad["now"], False), choice_text=_choice("Vay mua ngay", head))
        meta["loan_now"] = (0, now["cost"])
        plans.append(plan)

    # optimized: only when it needs a loan, has a feasible month and is not the same as buying now
    if opt is not None and opt["loan"] > 0 and not (opt["purchase_month"] == 0 and "loan_now" in meta):
        head = _loan_headline(opt)
        n_ok = sum(1 for r in base["rows"] if r["feasible"])
        why = "Tháng duy nhất khả thi về dòng tiền" if n_ok == 1 else "Tháng khả thi có tổng chi phí sở hữu thấp nhất"
        bad_opt = bad["opt"]
        plan = dict(id="optimized", name="Kết hợp tối ưu", verdict="ok", headline=head,
                    metrics=_loan_metrics(opt, _earned_at(bad["p"], opt["purchase_month"])),
                    milestones=_milestones(p, opt["purchase_month"], reserve, opt, why),
                    risk=_loan_risk(bad_opt, True), choice_text=_choice("Kết hợp tối ưu", head))
        if opt["purchase_month"] <= p.months:
            meta["optimized"] = (opt["purchase_month"], opt["cost"])
        plans.append(plan)

    if meta:
        # never recommend borrowing what the customer can save on time; otherwise earliest purchase, then cheapest
        best = "no_loan" if "no_loan" in meta else min(meta, key=lambda k: meta[k])
        next(x for x in plans if x["id"] == best)["verdict"] = "recommended"

    short = nl["shortfall"]
    baseline = nl_head + (f" (thiếu {short_vnd(short)} ở hạn)" if round(short) > 0 else "")
    assumptions = [f"Lãi tiết kiệm {_pct(p.deposit_rate)}%/năm", f"Lãi vay {_pct(p.loan_rate)}%/năm, {p.loan_term} tháng"]
    for label, v in (("Giá mục tiêu", p.target_growth), ("Thu nhập", p.income_growth), ("Chi tiêu", p.spending_growth)):
        if v:
            assumptions.append(f"{label} {'+' if v > 0 else ''}{_pct(v)}%/năm")
    if p.reserve_months > 0:
        assumptions.append(f"Quỹ dự phòng {_pct(p.reserve_months)} tháng chi tiêu")
    if p.other_goals > 0:
        assumptions.append(f"Đã góp {short_vnd(p.other_goals)}/tháng cho mục tiêu khác")
    if p.extra_assets > 0:
        assumptions.append(f"Đã tính {short_vnd(p.extra_assets)} tài sản sẵn có cho mục tiêu")

    suffix = " · " + _deadline(p.months)
    name = goal_name.strip() or "Mục tiêu"
    if len(name) + len(suffix) > 80:
        name = name[: 80 - len(suffix) - 1].rstrip() + "…"
    gid = (goal_id or "").strip()
    if not gid or len(gid) > MAX_GOAL_ID:
        raise ValueError("a roadmap needs the id (<= 64 chars) of the goal it is for")
    return dict(type="plan_roadmap", goal_id=gid, title=name + suffix, baseline=baseline[:200], assumptions=assumptions[:8], plans=plans)

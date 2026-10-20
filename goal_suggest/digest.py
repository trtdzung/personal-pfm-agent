"""Turns the raw pfm payloads into the text the model reads. All arithmetic the insight needs (gaps, averages, price moves,
adjustment options) is done HERE, in code, and printed as ready numbers: the model picks the story and words it, and the
guard only lets it use numbers that appear in this text."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from datetime import date, datetime, timedelta

from tools.customer_data_tools import _spend_delta
from tools.goal_tools import months_left, price_at, summarize_goals

# Whole months before this one that the cash-flow comparison averages.
COMPARE_MONTHS = 3
# MSB online deposit (pfm `goals-preview/data/products.ts`, product `msb-online-deposit`): (months, % per year).
MSB_ONLINE_DEPOSIT = ((1, 4.75), (3, 4.75), (6, 6.3), (12, 6.8), (24, 6.6), (36, 6.1))
LOAN_MIN_SAVED_PCT = 30
LOAN_SHARE_PCT = 70
# A scenario fires when the move is at least this big (see prompts/system.md).
PRICE_MOVE_30D_PCT = 5
PRICE_MOVE_90D_PCT = 10
SPEND_MOVE_PCT = 15
IDLE_MIN_VND = 1_000_000
TOP_CATEGORIES = 3
_CATEGORY_FALLBACK = {"unclassified": "Chưa phân loại"}
_GOAL_PHASE_1 = {"accumulating", "paused", "missed"}


class GoalNotFound(LookupError):
    pass


class GoalAmbiguous(LookupError):
    pass


# ---------------------------------------------------------------- formatting


def vnd(n: float | None) -> str:
    if n is None:
        return "chưa biết"
    return f"{int(round(n)):,}".replace(",", ".") + " VND"


def dmy(iso: str) -> str:
    year, month, day = iso[:10].split("-")
    return f"{day}/{month}/{year}"


def pct(n: float) -> str:
    return f"{n:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower().strip()


def add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def round_down_thousand(n: float) -> int:
    return int(n // 1000 * 1000)


# ---------------------------------------------------------------- goal choice


def pick_goal(summary: dict, goal_id: str | None, goal_name: str | None) -> dict:
    goals = summary["goals"]
    if goal_id:
        for g in goals:
            if g["id"] == goal_id.strip():
                return g
        raise GoalNotFound(goal_id)
    wanted = _fold(goal_name or "")
    exact = [g for g in goals if _fold(g["name"]) == wanted]
    if len(exact) == 1:
        return exact[0]
    near = exact or [g for g in goals if wanted and wanted in _fold(g["name"])]
    if len(near) == 1:
        return near[0]
    if not near:
        raise GoalNotFound(goal_name or "")
    raise GoalAmbiguous(", ".join(g["id"] for g in near))


# ---------------------------------------------------------------- sections


def _customer(summary: dict) -> list[str]:
    lines = ["== KHÁCH HÀNG =="]
    lines.append(f"Hôm nay: {dmy(summary['today'])}. Ngày nhận lương: ngày {summary.get('salaryDay')} hằng tháng.")
    if summary.get("monthlyIncome") is not None:
        lines.append(f"Thu nhập hằng tháng (hồ sơ): {vnd(summary['monthlyIncome'])}.")
    if isinstance(summary.get("monthlySurplus"), (int, float)):
        lines.append(f"Tiền dư mỗi tháng (hồ sơ): {vnd(summary['monthlySurplus'])}.")
    return lines


def _goal(summary: dict, goal: dict) -> list[str]:
    today = summary["today"]
    lines = ["== MỤC TIÊU ĐANG XÉT =="]
    lines.append(f"Tên: {goal['name']} (mã {goal['id']}). Trạng thái: {goal['status']}. Giai đoạn: {goal['phase']} ({'trả nợ vay' if goal['phase'] == 2 else 'tích luỹ'}).")
    lines.append(f"Số tiền mục tiêu: {vnd(goal['targetAmount'])}. Hạn: {dmy(goal['targetDate'])} (còn {months_left(today, goal['targetDate'])} tháng).")
    if goal["phase"] == 1:
        value = goal["value"]
        lines.append(f"Giá trị hiện có (tiền trong tài khoản mục tiêu + tài sản được tính): {vnd(value)}.")
        lines.append(f"Tiến độ: {pct(value / goal['targetAmount'] * 100) if goal['targetAmount'] else '0%'} mục tiêu. Còn thiếu: {vnd(max(0, goal['targetAmount'] - value))}.")
        lines.append(f"Cần góp mỗi tháng để kịp hạn: {vnd(goal['requiredMonthly'])}.")
    so = goal.get("standingOrder")
    if so and so.get("active"):
        lines.append(f"Trích tự động đang bật: {vnd(so['amount'])} vào ngày {so['dayOfMonth']} hằng tháng (lần tới {dmy(so['nextRunDate'])}).")
    else:
        lines.append("Chưa bật trích tự động.")
    lines.append(f"Độ ưu tiên: {goal.get('priority')} (số nhỏ = quan trọng hơn).")
    twins = [g for g in summary["goals"] if g["id"] != goal["id"] and _fold(g["name"]) == _fold(goal["name"])]
    if twins:
        lines.append(
            f"LƯU Ý: khách còn {len(twins)} mục tiêu khác cùng tên \"{goal['name']}\" (hạn "
            + ", ".join(dmy(g["targetDate"]) for g in twins)
            + f"). Trong câu hỏi (`question`) PHẢI nêu hạn {dmy(goal['targetDate'])} của mục tiêu này (ví dụ \"{goal['name']} hạn {dmy(goal['targetDate'])}\") để chat biết là mục tiêu nào."
        )
    return lines


def _adjustments(summary: dict, goal: dict) -> list[str]:
    """The three ways to bring a phase-1 goal back on course, already computed."""
    if goal["phase"] != 1 or goal["status"] not in _GOAL_PHASE_1:
        return []
    lines = ["== ĐÃ TÍNH SẴN: PHƯƠNG ÁN ĐIỀU CHỈNH (chỉ dùng đúng các số này) =="]
    gap = max(0, goal["targetAmount"] - goal["value"])
    if gap == 0:
        return lines + ["Giá trị hiện có đã đủ số tiền mục tiêu, không cần điều chỉnh."]
    today = date.fromisoformat(summary["today"])
    months = months_left(summary["today"], goal["targetDate"])
    so = goal.get("standingOrder")
    saving = so["amount"] if so and so.get("active") else 0
    lines.append(f"Số góp mỗi tháng cần có để kịp hạn hiện tại: {vnd(goal['requiredMonthly'])}.")
    if saving:
        lines.append(f"Số đang góp (trích tự động): {vnd(saving)}. Thiếu mỗi tháng so với cần có: {vnd(max(0, goal['requiredMonthly'] - saving))}.")
        if months > 0:
            lines.append(f"(a) Tăng số góp hằng tháng lên {vnd(goal['requiredMonthly'])} thì vẫn kịp hạn {dmy(goal['targetDate'])}.")
        need_months = math.ceil(gap / saving)
        new_date = add_months(today, need_months)
        if need_months > months:
            lines.append(f"(b) Giữ nguyên số góp {vnd(saving)} thì cần lùi hạn tới khoảng {dmy(new_date.isoformat())}.")
        if months > 0:
            reachable = round_down_thousand(goal["value"] + saving * months)
            if reachable < goal["targetAmount"]:
                lines.append(f"(c) Giữ nguyên số góp và hạn thì đến hạn đạt khoảng {vnd(reachable)}; có thể giảm số tiền mục tiêu xuống mức này.")
                lines.append(f"(d) Hoặc giữ nguyên số góp và hạn, nạp thêm một lần {vnd(goal['targetAmount'] - reachable)} (lúc nào trước hạn cũng được) là đủ số tiền mục tiêu.")
    else:
        lines.append(f"(a) Bật trích tự động {vnd(goal['requiredMonthly'])} mỗi tháng thì kịp hạn {dmy(goal['targetDate'])}.")
    return lines


def _repayment(summary: dict, goal: dict, snapshot: dict) -> list[str]:
    if goal["phase"] != 2:
        return []
    lines = ["== TRẢ NỢ (GIAI ĐOẠN 2) =="]
    loan = next((l for l in snapshot["world"].get("loans") or [] if l["goalId"] == goal["id"] and l.get("status") == "active"), None)
    if not loan:
        return lines + ["Không có khoản vay đang hoạt động."]
    rows = loan.get("schedule") or []
    unpaid = [r for r in rows if r.get("status") != "paid"]
    overdue = [r for r in rows if r.get("status") == "overdue"]
    lines.append(f"Khoản vay {vnd(loan['principal'])}, mỗi kỳ {vnd(loan['monthlyPayment'])}, còn {len(unpaid)} kỳ chưa trả.")
    if unpaid:
        lines.append(f"Kỳ tới hạn: kỳ {unpaid[0]['period']}, ngày {dmy(unpaid[0]['dueDate'])}, số tiền {vnd(unpaid[0]['payment'])}.")
    if overdue:
        lines.append(f"Đang quá hạn: {len(overdue)} kỳ, tổng {vnd(sum(r['payment'] for r in overdue))}.")
    else:
        lines.append("Không có kỳ nào quá hạn.")
    payment = unpaid[0]["payment"] if unpaid else 0
    balance = goal["balance"]
    so = goal.get("standingOrder")
    saving = so["amount"] if so and so.get("active") else 0
    lines.append(f"Số dư tài khoản mục tiêu: {vnd(balance)}. Trích tự động: {vnd(saving)} mỗi tháng.")
    if payment:
        lines.append(f"Thiếu so với kỳ tới nếu chỉ có số dư hiện tại: {vnd(max(0, payment - balance))}. Trích tự động thấp hơn kỳ trả: {vnd(max(0, payment - saving))} mỗi tháng.")
    return lines


HISTORY_SLACK_DAYS = 3  # weekends and holidays have no quote


def covers(series: list[dict], day: str) -> bool:
    """True when the price series starts on or shortly before `day`. `price_at` answers a day before the first point with the
    first price, which would read as "no change": such a window must be reported as unknown, not as 0%."""
    if not series:
        return False
    return series[0]["date"] <= (date.fromisoformat(day) + timedelta(days=HISTORY_SLACK_DAYS)).isoformat()


def asset_moves(summary: dict, goal: dict, snapshot: dict) -> list[dict]:
    """Market-priced assets of the goal with how far their price moved over 30 and 90 days."""
    today = summary["today"]
    shift = (snapshot["world"].get("market") or {}).get("fundPriceShiftPct", 0)
    instruments = {i["id"]: i for i in (snapshot.get("market") or {}).get("instruments") or []}
    days = {n: (date.fromisoformat(today) - timedelta(days=n)).isoformat() for n in (30, 90)}
    moves = []
    for a in summary["assets"]:
        instrument = instruments.get(a.get("instrumentId") or "")
        if a["goalId"] != goal["id"] or not instrument or not a.get("quantity"):
            continue
        series = instrument.get("priceSeries") or []
        now = price_at(series, today, shift)
        move = {"asset": a, "instrument": instrument, "now": now, "pct": {}, "counted_delta": {}}
        for n, day in days.items():
            old = price_at(series, day, shift) if covers(series, day) else 0
            if old:
                move["pct"][n] = (now / old - 1) * 100
                move["counted_delta"][n] = int(round(a["quantity"] * (now - old) * a["countPercent"] / 100))
        moves.append(move)
    return moves


def _assets(summary: dict, goal: dict, snapshot: dict) -> list[str]:
    mine = [a for a in summary["assets"] if a["goalId"] == goal["id"]]
    lines = ["== TÀI SẢN TÍCH LUỸ CỦA MỤC TIÊU =="]
    if not mine:
        return lines + ["Mục tiêu chưa có tài sản nào ngoài tiền trong tài khoản mục tiêu."]
    today = summary["today"]
    shift = (snapshot["world"].get("market") or {}).get("fundPriceShiftPct", 0)
    instruments = {i["id"]: i for i in (snapshot.get("market") or {}).get("instruments") or []}
    d30 = (date.fromisoformat(today) - timedelta(days=30)).isoformat()
    d90 = (date.fromisoformat(today) - timedelta(days=90)).isoformat()
    for a in mine:
        counted = int(round(a["value"] * a["countPercent"] / 100))
        head = f"- {a['name']} ({a['category']}): giá trị {vnd(a['value'])}, tính {a['countPercent']}% vào mục tiêu = {vnd(counted)}."
        instrument = instruments.get(a.get("instrumentId") or "")
        if instrument and a.get("quantity"):
            series = instrument.get("priceSeries") or []
            now, p30, p90 = (price_at(series, d, shift if d == today else shift) for d in (today, d30, d90))
            parts = [f"số lượng {a['quantity']} {instrument.get('unit', '')}".strip(), f"giá hiện tại {vnd(now)}/{instrument.get('unit', 'đơn vị')}"]
            for label, old, day in (("30 ngày", p30, d30), ("90 ngày", p90, d90)):
                if not covers(series, day):
                    first = series[0]["date"] if series else None
                    parts.append(f"{label}: chưa đủ lịch sử giá" + (f" (chỉ có từ {dmy(first)})" if first else "") + ", không so sánh được")
                elif old:
                    change = (now / old - 1) * 100
                    delta_counted = int(round(a["quantity"] * (now - old) * a["countPercent"] / 100))
                    sign = "tăng" if change >= 0 else "giảm"
                    parts.append(f"{label} qua giá {sign} {pct(abs(change))}, giá trị tính vào mục tiêu {sign} {vnd(abs(delta_counted))}")
            head += " " + "; ".join(parts) + "."
        elif a["type"] == "msb":
            head += " Sản phẩm MSB, giá trị theo sổ."
        lines.append(head)
    return lines


def _loan_option(summary: dict, goal: dict) -> list[str]:
    if goal["phase"] != 1 or goal["status"] != "accumulating" or goal.get("hasActiveLoan"):
        return []
    lines = ["== ĐÃ TÍNH SẴN: CÓ THỂ VAY ĐỂ HOÀN THÀNH SỚM =="]
    target = goal["targetAmount"]
    saved_pct = goal["value"] / target * 100 if target else 0
    if saved_pct >= LOAN_MIN_SAVED_PCT:
        lines.append(f"Đã tích luỹ {pct(saved_pct)} mục tiêu, từ ngưỡng {LOAN_MIN_SAVED_PCT}%: ĐỦ ĐIỀU KIỆN gợi ý cân nhắc vay.")
        lines.append(f"{LOAN_SHARE_PCT}% số tiền mục tiêu = {vnd(round(target * LOAN_SHARE_PCT / 100))}.")
    else:
        lines.append(f"Đã tích luỹ {pct(saved_pct)} mục tiêu, chưa tới ngưỡng {LOAN_MIN_SAVED_PCT}%: KHÔNG gợi ý vay.")
    return lines


# ---------------------------------------------------------------- cash flow


def _local(posted_at: str) -> datetime:
    """pfm stores UTC; the customer's day is Vietnam time (UTC+7)."""
    return datetime.fromisoformat(posted_at.replace("Z", "+00:00")).replace(tzinfo=None) + timedelta(hours=7)


def _month_key(d: date, back: int) -> str:
    index = d.year * 12 + d.month - 1 - back
    return f"{index // 12}-{index % 12 + 1:02d}"


def cash_flow(transactions: list[dict], accounts: list[dict], categories: list[dict], today: date) -> dict | None:
    """This month up to today versus the same days of each of the 3 previous months: spending, income, money put into
    goals, net movement of the current account, and per-category spending."""
    current_ids = {a["id"] for a in accounts if a.get("type") == "current"} or {
        t["accountId"] for t in transactions if "current" in str(t.get("accountId"))
    }
    goal_ids = {a["id"] for a in accounts if a.get("type") == "goal"}
    labels = {c["id"]: c.get("label") or c["id"] for c in categories}
    months = [_month_key(today, back) for back in range(COMPARE_MONTHS + 1)]
    stats = {m: {"spend": 0.0, "income": 0.0, "to_goals": 0.0, "net": 0.0, "n": 0, "cat": {}} for m in months}
    for t in transactions:
        if t.get("hidden") or not t.get("postedAt"):
            continue
        local = _local(t["postedAt"])
        key = f"{local.year}-{local.month:02d}"
        if key not in stats or local.day > today.day:
            continue
        s = stats[key]
        s["n"] += 1
        delta = _spend_delta(t)
        if delta is not None:
            s["spend"] += delta
            label = labels.get(t.get("categoryId"), _CATEGORY_FALLBACK.get(t.get("categoryId") or "", t.get("categoryId") or "Khác"))
            s["cat"][label] = s["cat"].get(label, 0) + delta
        amount = t.get("amount") or 0
        if t.get("accountId") in current_ids:
            s["net"] += amount if t.get("direction") == "credit" else -amount
            if t.get("direction") == "credit" and t.get("type") == "income":
                s["income"] += amount
        if t.get("accountId") in goal_ids and t.get("direction") == "credit":
            s["to_goals"] += amount
    previous = [stats[m] for m in months[1:] if stats[m]["n"] > 0]
    if len(previous) < 2:
        return None

    def avg(field: str) -> float:
        return sum(p[field] for p in previous) / len(previous)

    categories_seen = set(stats[months[0]]["cat"]) | {c for p in previous for c in p["cat"]}
    by_category = []
    for label in categories_seen:
        now = stats[months[0]]["cat"].get(label, 0)
        mean = sum(p["cat"].get(label, 0) for p in previous) / len(previous)
        by_category.append({"label": label, "now": now, "avg": mean, "diff": now - mean})
    return {
        "this": stats[months[0]],
        "avg": {f: avg(f) for f in ("spend", "income", "to_goals", "net")},
        "months": len(previous),
        "by_category": sorted(by_category, key=lambda c: c["diff"], reverse=True),
    }


def jar_usage(transactions: list[dict] | None, jars: dict | None, today: date) -> dict[str, dict]:
    """Per jar: what the customer really spends in it. `avg` = mean spend of a whole previous month (only months that have
    transactions, at least 2), `this` = spent so far this month, `left` = what the usual month still has to spend, `surplus` =
    spendable minus `left` (what can leave the jar without hurting the usual month). Empty without enough history."""
    if not transactions or not jars:
        return {}
    months = [_month_key(today, back) for back in range(COMPARE_MONTHS + 1)]
    with_data = {m for m in months[1:] if any(_month_of(t) == m for t in transactions if not t.get("hidden") and t.get("postedAt"))}
    if len(with_data) < 2:
        return {}
    usage: dict[str, dict] = {}
    for jar in jars.get("jars") or []:
        ids = set(jar.get("categoryIds") or [])
        if jar.get("spendable") is None or not ids:
            continue
        spend = {m: 0.0 for m in [months[0], *with_data]}
        for t in transactions:
            if t.get("hidden") or not t.get("postedAt") or t.get("categoryId") not in ids:
                continue
            m = _month_of(t)
            delta = _spend_delta(t)
            if m in spend and delta is not None:
                spend[m] += delta
        avg = round(sum(spend[m] for m in with_data) / len(with_data))
        this = round(jar.get("spent") if jar.get("spent") is not None else spend[months[0]])  # pfm's own figure for this month wins
        left = max(0, avg - this)
        usage[jar["id"]] = {"avg": avg, "this": this, "left": left, "surplus": round(jar["spendable"] - left), "months": len(with_data)}
    return usage


def _month_of(t: dict) -> str:
    local = _local(t["postedAt"])
    return f"{local.year}-{local.month:02d}"


def _cash_flow_lines(today: date, flow: dict | None) -> list[str]:
    lines = [f"== DÒNG TIỀN TÀI KHOẢN THANH TOÁN (CASA): từ ngày 1 đến ngày {today.day} tháng này so với cùng kỳ trung bình {COMPARE_MONTHS} tháng trước =="]
    if flow is None:
        return lines + ["Không đủ dữ liệu giao dịch để so sánh (cần ít nhất 2 tháng trước)."]
    this, avg = flow["this"], flow["avg"]

    def row(label: str, now: float, mean: float) -> str:
        diff = now - mean
        change = f", {'cao' if diff >= 0 else 'thấp'} hơn {pct(abs(diff) / mean * 100)}" if mean else ""
        return f"{label}: tháng này {vnd(now)}; trung bình {vnd(mean)}; {'cao' if diff >= 0 else 'thấp'} hơn trung bình {vnd(abs(diff))}{change}."

    lines.append(row("Chi tiêu", this["spend"], avg["spend"]))
    lines.append(row("Thu nhập vào CASA", this["income"], avg["income"]))
    lines.append(row("Tiền đã chuyển vào các mục tiêu", this["to_goals"], avg["to_goals"]))
    lines.append(row("Dòng tiền ròng CASA (vào trừ ra)", this["net"], avg["net"]) if avg["net"] >= 0 else
                 f"Dòng tiền ròng CASA (vào trừ ra): tháng này {vnd(this['net'])}; trung bình {vnd(avg['net'])}.")
    over = [c for c in flow["by_category"] if c["diff"] > 0][:TOP_CATEGORIES]
    under = [c for c in reversed(flow["by_category"]) if c["diff"] < 0][:TOP_CATEGORIES]
    if over:
        lines.append("Hạng mục chi cao hơn trung bình nhiều nhất: " + "; ".join(
            f"{c['label']} {vnd(c['now'])} (trung bình {vnd(c['avg'])}, cao hơn {vnd(c['diff'])}" + (f", {pct(c['diff'] / c['avg'] * 100)})" if c["avg"] else ")") for c in over) + ".")
    if under:
        lines.append("Hạng mục chi thấp hơn trung bình nhiều nhất: " + "; ".join(f"{c['label']} thấp hơn {vnd(-c['diff'])}" for c in under) + ".")
    return lines


def _jars(jars: dict | None, accounts: list[dict] | None, usage: dict[str, dict] | None = None) -> list[str]:
    lines = ["== HŨ KHÁC VÀ TIỀN CHƯA PHÂN BỔ =="]
    if not jars:
        return lines + ["Không có dữ liệu hũ."]
    if jars.get("casaBalance") is not None:
        lines.append(f"Số dư CASA: {vnd(jars['casaBalance'])}.")
    if jars.get("unallocated") is not None:
        lines.append(f"Chưa phân bổ vào hũ nào: {vnd(jars['unallocated'])}.")
    for jar in jars.get("jars") or []:
        if jar.get("spendable") is None:
            continue
        lines.append(f"- Hũ {jar['label']}: dùng được {vnd(jar.get('spendable', 0))}, đã chi {vnd(jar.get('spent', 0))}/{vnd(jar.get('limit', 0))} tháng này" + ("; ĐANG ÂM" if (jar.get("balance") or 0) < 0 else "") + _usage_note(usage, jar) + ".")
    for a in accounts or []:
        if a.get("type") == "savings":
            lines.append(f"Tài khoản tiết kiệm khác của khách: {vnd(a['balance'])}.")
    return lines


def _usage_note(usage: dict[str, dict] | None, jar: dict) -> str:
    u = (usage or {}).get(jar.get("id"))
    if not u:
        return "; chưa đủ lịch sử chi tiêu của hũ này"
    return (f"; chi thực tế trung bình {vnd(u['avg'])}/tháng ({u['months']} tháng trước), tháng này đã chi {vnd(u['this'])}, "
            f"dự kiến còn chi {vnd(u['left'])} đến cuối tháng, phần dư thực sự khoảng {vnd(max(u['surplus'], 0))}")


def _goal_cash(summary: dict, goal: dict, snapshot: dict) -> list[str]:
    account = next((a for a in snapshot["world"].get("accounts") or [] if a["goalId"] == goal["id"] and a.get("status") == "open"), None)
    lines = ["== TIỀN TRONG TÀI KHOẢN MỤC TIÊU =="]
    if not account:
        return lines + ["Mục tiêu chưa có tài khoản."]
    balance = account["balance"]
    lines.append(f"Số dư: {vnd(balance)}. Lãi suất tài khoản mục tiêu: {pct(account.get('interestRatePa', 0))}/năm.")
    if goal["phase"] != 1 or balance <= 0:
        return lines
    today = date.fromisoformat(summary["today"])
    lines.append("THAM KHẢO LÃI SUẤT TIỀN GỬI TRỰC TUYẾN MSB (lãi ước tính tính sẵn trên số dư trên, không gồm lãi cộng dồn):")
    for months, rate in MSB_ONLINE_DEPOSIT:
        maturity = add_months(today, months)
        fits = maturity.isoformat() <= goal["targetDate"]
        interest = round(balance * rate / 100 * months / 12)
        note = f"đáo hạn {dmy(maturity.isoformat())}, " + ("TRƯỚC hạn mục tiêu" if fits else "SAU hạn mục tiêu: KHÔNG dùng")
        lines.append(f"- Kỳ hạn {months} tháng, {pct(rate)}/năm, {note}" + (f", lãi ước tính {vnd(interest)}." if fits else "."))
    return lines


def _other_goals(summary: dict, goal: dict) -> list[str]:
    others = [g for g in summary["goals"] if g["id"] != goal["id"] and g["status"] in _GOAL_PHASE_1 | {"repaying"}]
    if not others:
        return []
    lines = ["== CÁC MỤC TIÊU KHÁC =="]
    for g in others:
        lines.append(f"- {g['name']} (ưu tiên {g.get('priority')}, trạng thái {g['status']}): cần góp mỗi tháng {vnd(g['requiredMonthly'])}.")
    return lines


def _preferences(preferences: dict | None) -> list[str]:
    if not preferences:
        return []
    keep = {k: v for k, v in preferences.items() if k in {"responseLength", "tone", "addressAs", "riskAppetite", "about", "notes"} and v}
    if not keep:
        return []
    return ["== TÙY CHỌN M-YOU CỦA KHÁCH =="] + [f"{k}: {v}" for k, v in keep.items()]


# ---------------------------------------------------------------- which scenarios fire


def _idle_other_money(jars: dict | None, usage: dict[str, dict] | None = None) -> tuple[int, list[str]]:
    """Money outside the goal that could go into it: what is not allocated to any jar, plus the REAL surplus of every jar
    (spendable minus what the customer usually still spends there this month, from their own transactions). Jars without enough
    spending history, over their limit or the essentials jar never count."""
    if not jars:
        return 0, []
    parts: list[str] = []
    total = 0
    if (jars.get("unallocated") or 0) > 0:
        total += jars["unallocated"]
        parts.append(f"chưa phân bổ {vnd(jars['unallocated'])}")
    for jar in jars.get("jars") or []:
        u = (usage or {}).get(jar.get("id"))
        if u and u["surplus"] > 0 and jar.get("id") != "essentials" and (jar.get("balance") or 0) >= 0:
            total += u["surplus"]
            parts.append(f"hũ {jar['label']} dư thực khoảng {vnd(u['surplus'])} (dùng được {vnd(jar['spendable'])}, trung bình mỗi tháng chỉ chi {vnd(u['avg'])})")
    return total, parts


# Printed when no point is worth saying. The service answers this case itself with fixed wording, without the model.
ON_TRACK_NOTE = "Không có điểm nào đáng báo: mục tiêu đang đi đúng hướng."


def _highlights(summary: dict, goal: dict, snapshot: dict, flow: dict | None, jars: dict | None, usage: dict[str, dict] | None = None) -> list[str]:
    """What is worth telling this customer today, already judged against thresholds, most important first. No labels or types:
    the model reads them as plain observations and writes the card about the first one (or says the goal is on track)."""
    phase = goal["phase"]
    so = goal.get("standingOrder")
    saving = so["amount"] if so and so.get("active") else 0
    found: list[str] = []

    if phase == 2:
        loan = next((l for l in snapshot["world"].get("loans") or [] if l["goalId"] == goal["id"] and l.get("status") == "active"), None)
        unpaid = [r for r in (loan or {}).get("schedule") or [] if r.get("status") != "paid"]
        overdue = [r for r in unpaid if r.get("status") == "overdue"]
        payment = unpaid[0]["payment"] if unpaid else 0
        reasons = []
        if overdue:
            reasons.append(f"{len(overdue)} kỳ quá hạn")
        if payment and saving < payment:
            reasons.append(f"trích tự động {vnd(saving)} thấp hơn kỳ trả {vnd(payment)}")
        if payment and goal["balance"] < payment:
            reasons.append(f"số dư tài khoản mục tiêu {vnd(goal['balance'])} chưa đủ kỳ trả {vnd(payment)}")
        if reasons:
            found.append("Nguy cơ trễ kỳ trả nợ: " + "; ".join(reasons) + ".")

    if phase == 1:
        big = []
        for m in asset_moves(summary, goal, snapshot):
            p30, p90 = m["pct"].get(30), m["pct"].get(90)
            if (p30 is not None and abs(p30) >= PRICE_MOVE_30D_PCT) or (p90 is not None and abs(p90) >= PRICE_MOVE_90D_PCT):
                big.append(f"{m['asset']['name']} ({pct(p30) if p30 is not None else '?'} trong 30 ngày, {pct(p90) if p90 is not None else '?'} trong 90 ngày)")
        if big:
            found.append("Giá tài sản biến động mạnh: " + "; ".join(big) + ". Xem mục TÀI SẢN và PHƯƠNG ÁN ĐIỀU CHỈNH.")

    if flow:
        this, avg = flow["this"], flow["avg"]
        spend_pct = (this["spend"] - avg["spend"]) / avg["spend"] * 100 if avg["spend"] else 0
        net_pct = (this["net"] - avg["net"]) / avg["net"] * 100 if avg["net"] > 0 else 0
        if spend_pct >= SPEND_MOVE_PCT:
            found.append(f"Chi tiêu tháng này cao hơn trung bình {pct(spend_pct)}: có thể gợi ý tiêu bớt hạng mục lệch nhiều nhất.")
        elif net_pct >= SPEND_MOVE_PCT:
            found.append(f"Dòng tiền ròng CASA cao hơn trung bình {pct(net_pct)}: có thể gợi ý bổ sung tiền vào mục tiêu.")

    target = goal["targetAmount"]
    saved = goal["value"] / target * 100 if target else 0
    if phase == 1 and goal["status"] == "accumulating" and not goal.get("hasActiveLoan") and saved >= LOAN_MIN_SAVED_PCT:
        found.append(f"Đã tích luỹ {pct(saved)} mục tiêu (từ ngưỡng {LOAN_MIN_SAVED_PCT}%): có thể gợi ý cân nhắc vay khoảng {vnd(round(target * LOAN_SHARE_PCT / 100))} ({LOAN_SHARE_PCT}% số tiền mục tiêu) để hoàn thành sớm.")

    idle_total, idle_parts = _idle_other_money(jars, usage)
    short = phase == 1 and goal["requiredMonthly"] > saving
    if idle_total >= IDLE_MIN_VND and (short or phase == 2):
        found.append("Có tiền nhàn rỗi ngoài mục tiêu có thể đẩy vào: " + "; ".join(idle_parts) + f". Tổng cộng {vnd(idle_total)}.")

    account = next((a for a in snapshot["world"].get("accounts") or [] if a["goalId"] == goal["id"] and a.get("status") == "open"), None)
    balance = account["balance"] if account else 0
    fits = any(add_months(date.fromisoformat(summary["today"]), m).isoformat() <= goal["targetDate"] for m, _ in MSB_ONLINE_DEPOSIT)
    if phase == 1 and balance >= IDLE_MIN_VND and fits:
        found.append(f"Tài khoản mục tiêu có {vnd(balance)} nằm yên với lãi suất thấp: có thể gợi ý gửi tiết kiệm MSB kỳ hạn kết thúc trước hạn mục tiêu (xem bảng lãi suất).")

    lines = ["== ĐIỂM ĐÁNG CHÚ Ý ĐÃ XÉT SẴN (quan trọng nhất ở đầu danh sách) =="]
    if not found:
        return lines + [ON_TRACK_NOTE]
    return lines + [f"{i}. {text}" for i, text in enumerate(found, 1)]


# ---------------------------------------------------------------- entry point


def fingerprint(goal: dict, highlights: list[str]) -> str:
    """Stable id of "what the card would be about": the goal's plan, how far along it is (5% steps) and which points are worth
    saying (their wording up to the first colon, so a drifting percentage alone does not change it). The caller sends the last
    one back and skips the model when it has not changed."""
    target = goal["targetAmount"]
    step = int(goal["value"] / target * 100 // 5) if target else 0
    so = goal.get("standingOrder") or {}
    parts = [goal["id"], goal["status"], goal["phase"], target, goal["targetDate"], goal["requiredMonthly"], so.get("amount", 0) if so.get("active") else 0, step]
    parts += [h.split(":")[0] for h in highlights]
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]


def build(raw: dict, goal_id: str | None, goal_name: str | None) -> tuple[dict, str]:
    """(the chosen goal, the text the model reads). Raises GoalNotFound / GoalAmbiguous."""
    goal, text, _ = build_full(raw, goal_id, goal_name)
    return goal, text


def build_full(raw: dict, goal_id: str | None, goal_name: str | None) -> tuple[dict, str, str]:
    """`build` plus the fingerprint."""
    snapshot = raw["snapshot"]
    summary = summarize_goals(snapshot)
    goal = pick_goal(summary, goal_id, goal_name)
    today = date.fromisoformat(summary["today"])
    transactions, accounts = raw.get("transactions"), raw.get("accounts")
    flow = cash_flow(transactions, accounts or [], raw.get("categories") or [], today) if transactions else None
    usage = jar_usage(transactions, raw.get("jars"), today)
    highlights = _highlights(summary, goal, snapshot, flow, raw.get("jars"), usage)
    sections = [
        _customer(summary),
        _goal(summary, goal),
        _adjustments(summary, goal),
        _repayment(summary, goal, snapshot),
        _assets(summary, goal, snapshot),
        _loan_option(summary, goal),
        _cash_flow_lines(today, flow),
        _jars(raw.get("jars"), accounts, usage),
        _goal_cash(summary, goal, snapshot),
        _other_goals(summary, goal),
        _preferences(raw.get("preferences")),
        highlights,
    ]
    return goal, "\n\n".join("\n".join(s) for s in sections if s), fingerprint(goal, highlights[1:])

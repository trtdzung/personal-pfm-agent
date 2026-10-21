"""Read tools for the customer's savings goals ("Mục tiêu", pfm goals-v2), used by the skills goal-manage and goal-asset.

Source: `GET /api/goals-v2?cif=` (the whole world + the market list, ~1 MB because of the price series). These tools cut it
down to what a chat needs and compute the values pfm computes at read time: a stored asset `value` is 0 for market-priced
assets (quantity x price) and stale for deposits (principal + interest), so the formulas of pfm's
`goals-preview/engine/value.ts` are repeated here (`price_at`, `asset_value`). Reading may make pfm catch up the days that
passed and refresh prices in the background; both are harmless for the agent.
"""

import math
import unicodedata
from datetime import date

import httpx
from langchain_core.tools import tool

from middleware.seed_customer_context import _resolve_customer_id
from tools.customer_data_tools import PFM_BASE_URL, PFM_REQUEST_TIMEOUT_SECONDS, _vnd

# a goals-v2 read can wait for a first-time catch-up on pfm's side
GOALS_REQUEST_TIMEOUT_SECONDS = max(PFM_REQUEST_TIMEOUT_SECONDS, 20.0)
MARKET_LINES_SHOWN = 15

STATUS_LABEL = {
    "accumulating": "đang tích luỹ",
    "paused": "tạm dừng",
    "achieved": "đã đạt",
    "repaying": "đang trả nợ",
    "completed": "đã hoàn thành",
    "missed": "lỡ hạn",
    "closed": "đã đóng",
}
KIND_LABEL = {"gold": "vàng", "stock": "cổ phiếu", "external_fund": "quỹ ngoài"}
# Asset `type` in pfm's world: "declared" (the customer's own) / "msb" (MSB product). Before 2026-10-19 it was "fixed" / "liquid".
_ASSET_KIND = {"declared": "declared", "msb": "msb", "fixed": "declared", "liquid": "msb"}


def _round(x: float) -> int:
    """JavaScript's `Math.round` (half goes up), which pfm uses; Python's `round` goes to the even number."""
    return int(math.floor(x + 0.5))


def price_at(series: list[dict], day: str, shift_pct: float) -> int:
    """pfm `seriesPriceAt`: the last stored price on or before `day`; before the first point -> the first price; then the market shift."""
    if not series:
        return 0
    price = series[0]["price"]
    for point in series:
        if point["date"] > day:
            break
        price = point["price"]
    return _round(price * (1 + shift_pct / 100))


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def months_left(today: str, to: str) -> int:
    """pfm `monthsLeft`: whole months to `to`, a started month counts as one, never below 0."""
    days = _days_between(today, to)
    return 0 if days <= 0 else max(1, math.ceil(days / 30.4375))


def _deposit_accrued(principal: float, rate_pa: float, start: str, end: str) -> int:
    return _round(principal * (rate_pa / 100) * max(0, _days_between(start, end)) / 365)


def asset_value(asset: dict, today: str, market: dict[str, dict], shift_pct: float) -> int:
    """Today's value of one asset before `countPercent`. Liquid (MSB product) assets keep their last recorded value: re-pricing
    them needs pfm's product catalogue, which the world does not carry."""
    if asset.get("status") == "sold":
        return 0
    if _ASSET_KIND.get(asset.get("type", "")) == "declared":
        instrument = market.get(asset.get("instrumentId") or "")
        if instrument is not None and asset.get("quantity") is not None:
            return _round(asset["quantity"] * price_at(instrument["priceSeries"], today, shift_pct))
        accrual = asset.get("accrual")
        if accrual:
            end = accrual["maturityDate"] if accrual.get("maturityDate") and accrual["maturityDate"] < today else today
            return accrual["principal"] + _deposit_accrued(accrual["principal"], accrual["ratePa"], accrual["startDate"], end)
    return asset.get("value", 0)


def goal_stage(goal: dict, value: int, loan: dict | None, today: str) -> dict:
    """pfm `goalStage` + `requiredMonthly`. Phase 1 (saving): `value` against `targetAmount`; the monthly need is the gap spread over the
    months left. Phase 2 (a loan was taken, goal achieved / repaying): the target is everything the loan costs (principal + interest,
    paid + still to pay) and the progress is what was paid plus what the goal holds; the monthly need is the instalment."""
    if loan and goal["status"] in {"achieved", "repaying"}:
        schedule = loan.get("schedule") or []
        repaid = sum(r["payment"] for r in schedule if r.get("status") == "paid") + loan.get("prepaid", 0)
        remaining = sum(r["payment"] for r in schedule if r.get("status") != "paid")
        return {
            "phase": 2,
            "target": repaid + remaining,
            "value": repaid + value,
            "requiredMonthly": loan.get("monthlyPayment", 0) if loan.get("status") == "active" else 0,
            "loan": {"principal": loan["principal"], "monthlyPayment": loan.get("monthlyPayment", 0), "termMonths": loan.get("termMonths"), "status": loan.get("status")},
        }
    gap = max(0, goal["targetAmount"] - value)
    if goal["status"] in {"completed", "closed"} or gap == 0:
        required = 0
    else:
        months = months_left(today, goal["targetDate"])
        required = gap if months == 0 else int(math.ceil(gap / months / 1000) * 1000)
    return {"phase": 1, "target": goal["targetAmount"], "value": value, "requiredMonthly": required, "loan": None}


def summarize_goals(snapshot: dict) -> dict:
    """The chat's view of a `GET /api/goals-v2` snapshot: goals with their value, assets with today's value."""
    world, market_state = snapshot["world"], snapshot.get("market") or {}
    today = world["clock"]["today"]
    shift = (world.get("market") or {}).get("fundPriceShiftPct", 0)
    instruments = {i["id"]: i for i in market_state.get("instruments") or []}
    accounts = {a["id"]: a for a in world.get("accounts") or []}
    active_loans = {l["goalId"] for l in world.get("loans") or [] if l.get("status") == "active"}

    assets = []
    for a in world.get("assets") or []:
        if a.get("status") == "sold":
            continue
        assets.append(
            {
                "id": a["id"],
                "goalId": a["goalId"],
                "type": _ASSET_KIND.get(a["type"], a["type"]),
                "category": a["category"],
                "name": a["name"],
                "value": asset_value(a, today, instruments, shift),
                "countPercent": a["countPercent"],
                "instrumentId": a.get("instrumentId"),
                "quantity": a.get("quantity"),
                "institution": a.get("institution"),
                "readOnly": _ASSET_KIND.get(a["type"]) == "msb",
                # priced by the engine (quantity x price, or principal + interest): a hand-typed value would be overwritten
                "autoValued": _ASSET_KIND.get(a["type"]) == "declared" and ((a.get("instrumentId") is not None and a.get("quantity") is not None) or bool(a.get("accrual"))),
            }
        )

    loans = {l["id"]: l for l in world.get("loans") or []}
    goals = []
    for g in world.get("goals") or []:
        account = accounts.get(g.get("accountId") or "")
        balance = account["balance"] if account else 0
        mine = [a for a in assets if a["goalId"] == g["id"]]
        counted = sum(_round(a["value"] * a["countPercent"] / 100) for a in mine)
        loan = loans.get(g.get("loanId") or "")
        stage = goal_stage(g, balance + counted, loan, today)
        order = g.get("standingOrder")
        goals.append(
            {
                "id": g["id"],
                "name": g["name"],
                "template": g["template"],
                "targetAmount": g["targetAmount"],
                "targetDate": g["targetDate"],
                "flexibility": g.get("flexibility", "date_flexible"),
                "status": g["status"],
                "priority": g.get("priority"),
                "balance": balance,
                "value": balance + counted,
                "valueIsApproximate": any(a["readOnly"] for a in mine),
                "hasActiveLoan": g["id"] in active_loans,
                # progress of the CURRENT phase: phase 2 (loan taken) tracks principal + interest, not the original target
                "phase": stage["phase"],
                "progressValue": stage["value"],
                "progressTarget": stage["target"],
                "requiredMonthly": stage["requiredMonthly"],
                "loan": stage["loan"],
                "standingOrder": (
                    {
                        "amount": order["amount"],
                        "dayOfMonth": order["dayOfMonth"],
                        "active": bool(order.get("active")),
                        "nextRunDate": order.get("nextRunDate"),
                        "lastResult": order.get("lastResult"),
                    }
                    if order
                    else None
                ),
            }
        )
    customer = world["customer"]
    return {
        "today": today,
        "mainBalance": customer["mainCasaBalance"],
        "monthlyIncome": customer.get("monthlyIncome"),
        "monthlyExpenses": customer.get("monthlyExpenses"),
        "monthlySurplus": customer.get("monthlySurplus"),
        "existingDebtPayment": customer.get("existingDebtPayment"),
        "salaryDay": customer.get("salaryDay"),
        "fundPriceShiftPct": shift,
        "goals": goals,
        "assets": assets,
    }


def render_goals(summary: dict) -> str:
    lines = [f"Hôm nay (đồng hồ của hệ thống): {summary['today']}. Số dư tài khoản chính: {_vnd(summary['mainBalance'], 'chưa biết')}."]
    if summary.get("monthlyIncome") is not None:
        surplus = summary.get("monthlySurplus")
        lines.append(
            f"Thu chi hằng tháng của khách: thu nhập {_vnd(summary['monthlyIncome'], '?')}, chi tiêu {_vnd(summary.get('monthlyExpenses'), '?')}, "
            f"trả nợ có sẵn {_vnd(summary.get('existingDebtPayment'), '0đ')}, còn dư {_vnd(surplus, 'chưa đủ dữ liệu') if isinstance(surplus, (int, float)) else 'chưa đủ dữ liệu'}; "
            f"ngày nhận lương: {summary.get('salaryDay', '?')}."
        )
    if not summary["goals"]:
        lines.append("Khách chưa có mục tiêu nào.")
    for g in summary["goals"]:
        phase2 = g["phase"] == 2
        parts = [
            g["name"],
            f"id: {g['id']}",
            f"loại: {g['template']}",
            f"mục tiêu: {_vnd(g['targetAmount'], '?')}",
            f"hạn: {g['targetDate']}",
            f"trạng thái: {STATUS_LABEL.get(g['status'], g['status'])}",
            f"tài khoản mục tiêu: {_vnd(g['balance'], '0đ')}",
            f"giá trị hiện có: {_vnd(g['value'], '0đ')}{' (gần đúng: có tài sản MSB chưa định giá lại)' if g['valueIsApproximate'] else ''}",
        ]
        if phase2:
            parts.append(
                f"giai đoạn trả nợ: đã tích luỹ + đã trả {_vnd(g['progressValue'], '0đ')} / tổng gốc và lãi {_vnd(g['progressTarget'], '?')}"
            )
        if g["requiredMonthly"]:
            parts.append(f"cần góp mỗi tháng: {_vnd(g['requiredMonthly'], '?')}" + (" (tiền trả nợ)" if phase2 else " để kịp hạn"))
        order = g["standingOrder"]
        if order and order["active"]:
            parts.append(f"trích tự động: {_vnd(order['amount'], '?')}/tháng vào ngày {order['dayOfMonth']} (lần tới {order['nextRunDate']})")
        elif order:
            parts.append(f"trích tự động: đang tạm dừng ({_vnd(order['amount'], '?')}/tháng ngày {order['dayOfMonth']})")
        else:
            parts.append("trích tự động: chưa cài")
        if g["hasActiveLoan"]:
            parts.append("còn khoản vay chưa trả hết")
        lines.append("- " + " | ".join(parts))
    if summary["assets"]:
        lines.append("Tài sản thuộc mục tiêu:")
    for a in summary["assets"]:
        parts = [a["name"], f"id: {a['id']}", f"mục tiêu: {a['goalId']}", f"nhóm: {a['category']}", f"giá trị: {_vnd(a['value'], '0đ')}", f"tính vào mục tiêu: {a['countPercent']}%"]
        if a["instrumentId"]:
            parts.append(f"mã: {a['instrumentId']} x {a['quantity']}")
        parts.append("tài sản MSB, chỉ xem" if a["readOnly"] else "tự khai")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def fetch_goals_snapshot(customer_id: str) -> dict:
    """`GET /api/goals-v2` for an explicit customer. Raises `httpx.HTTPError`/`ValueError` on any failure, never an empty-looking answer."""
    response = httpx.get(f"{PFM_BASE_URL}/api/goals-v2", params={"cif": customer_id}, timeout=GOALS_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    snapshot = response.json()
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("world"), dict):
        raise ValueError("unexpected goals-v2 response shape")
    return snapshot


def _unavailable(what: str, exc: Exception) -> str:
    return f"Không thể đọc {what} lúc này (lỗi từ hệ thống pfm: {exc}). Đừng đoán số và đừng trả form mục tiêu/tài sản — báo cho khách hệ thống đang gián đoạn."


@tool(response_format="content_and_artifact")
def get_goals() -> tuple[str, dict | None]:
    """Read the current customer's savings goals and the assets attached to them, live from pfm (`GET /api/goals-v2`).

    Call this first, before proposing create_goal / edit_goal / close_goal / add_asset / edit_asset. It returns today's date
    by the system's own clock (use it for every relative date, never the real date), the main account balance, each goal
    (`id`, target amount and date, status, balance of its goal account, current value, whether a loan is still open) and each
    asset (`id`, group, today's value, the share counted toward the goal). Copy ids exactly; never invent one. Assets marked
    "chỉ xem" are MSB products and cannot be changed in chat. The reading also gives the monthly cash flow (income, spending, what is left each month), the monthly amount each goal needs to meet its date, and the auto-debit already set up.
    """
    try:
        summary = summarize_goals(fetch_goals_snapshot(_resolve_customer_id()))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return _unavailable("mục tiêu của khách", exc), None
    return render_goals(summary), summary


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def market_list(snapshot: dict) -> list[dict]:
    world, market_state = snapshot["world"], snapshot.get("market") or {}
    today = world["clock"]["today"]
    shift = (world.get("market") or {}).get("fundPriceShiftPct", 0)
    return [
        {
            "id": i["id"],
            "kind": i["kind"],
            "name": i["name"],
            "unit": i.get("unit", ""),
            "fractional": bool(i.get("fractional")),
            "price": price_at(i.get("priceSeries") or [], today, shift),
        }
        for i in market_state.get("instruments") or []
    ]


@tool(response_format="content_and_artifact")
def get_goal_market(query: str = "") -> tuple[str, list | None]:
    """List the market instruments an outside asset can be tied to (gold, stocks, outside funds) with today's price.

    Call this before add_asset for gold / stock / external_fund, to get the exact `id` (`instrumentId`) and the unit. `query`
    narrows the list by name, id or kind ("vàng", "ACB", "quỹ"); only the first lines are shown, so narrow it when the list is
    long. The price is information for the customer, never a price you set. Copy ids exactly.

    Also use it to ANSWER a customer who asks for today's price of gold, a stock or a fund: give the name, unit and price and say it
    is a reference price from the system's data, possibly delayed. No match: say there is no data for that instrument.
    """
    try:
        items = market_list(fetch_goals_snapshot(_resolve_customer_id()))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return _unavailable("danh mục thị trường", exc), None
    wanted = _fold(query).strip()
    shown = [i for i in items if not wanted or wanted in _fold(f"{i['id']} {i['name']} {KIND_LABEL.get(i['kind'], i['kind'])}")]
    if not shown:
        return "Không có mã nào khớp. Đừng tự đặt mã; hỏi lại khách hoặc dùng nhóm tài sản khác.", items
    lines = [
        f"- {i['name']} | id: {i['id']} | loại: {KIND_LABEL.get(i['kind'], i['kind'])} | giá hôm nay: {_vnd(i['price'], '?')}/{i['unit']}"
        f"{' (mua lẻ được)' if i['fractional'] else ' (số nguyên)'}"
        for i in shown[:MARKET_LINES_SHOWN]
    ]
    if len(shown) > MARKET_LINES_SHOWN:
        lines.append(f"... còn {len(shown) - MARKET_LINES_SHOWN} mã nữa; thêm từ khoá để thu hẹp.")
    return "\n".join(lines), items


def monthly_need(gap: int, months: int) -> int:
    """pfm `requiredMonthly` for phase 1: the gap spread over the months left, rounded UP to the thousand."""
    if gap <= 0:
        return 0
    return gap if months <= 0 else int(math.ceil(gap / months / 1000) * 1000)


def build_plan(summary: dict, target_amount: int, target_date: str, goal_id: str, initial_deposit: int) -> tuple[str, dict | None]:
    """The monthly saving plan for a goal (new, or an existing one with a new amount / date). Returns `(text, artifact)`."""
    today = summary["today"]
    goal = None
    if goal_id:
        goal = next((g for g in summary["goals"] if g["id"] == goal_id), None)
        if goal is None:
            return f"Không có mục tiêu nào có id {goal_id}. Chép đúng id từ get_goals, đừng tự đặt.", None
        target_amount = target_amount or goal["targetAmount"]
        target_date = target_date or goal["targetDate"]
        if goal["phase"] == 2 and not (target_amount != goal["targetAmount"] or target_date != goal["targetDate"]):
            return (
                f"Mục tiêu {goal['name']} đang trả nợ: mỗi tháng cần trả {_vnd(goal['requiredMonthly'], '?')} (khoản vay). Số này do lịch trả nợ, không tính lại theo ngày mục tiêu.",
                {"phase": 2, "monthly": goal["requiredMonthly"], "goalId": goal_id},
            )
        value = goal["value"]
    else:
        value = max(0, initial_deposit)
    if target_amount <= 0 or not target_date:
        return "Cần số tiền mục tiêu và ngày hạn để tính. Hỏi khách phần còn thiếu, đừng tự chọn.", None
    try:
        end = date.fromisoformat(target_date)
    except ValueError:
        return f"Ngày hạn '{target_date}' không hợp lệ: dùng dạng YYYY-MM-DD.", None
    if end <= date.fromisoformat(today):
        return f"Ngày hạn {target_date} không sau hôm nay của hệ thống ({today}); hạn phải là một ngày sau hôm nay.", None
    months = months_left(today, target_date)
    gap = max(0, target_amount - value)
    monthly = monthly_need(gap, months)
    salary_day = summary.get("salaryDay") or 5
    day = min(28, int(salary_day) + 1)
    surplus = summary.get("monthlySurplus")
    surplus_num = surplus if isinstance(surplus, (int, float)) else None
    plan = {
        "phase": 1, "today": today, "targetAmount": target_amount, "targetDate": target_date, "months": months, "valueNow": value, "gap": gap,
        "monthly": monthly, "suggestedDay": day, "monthlySurplus": surplus_num, "exceedsSurplus": bool(surplus_num is not None and monthly > surplus_num),
    }
    lines = [
        f"Từ hôm nay ({today}) đến hạn {target_date}: {months} tháng (một tháng dở tính là một tháng).",
        f"Số tiền mục tiêu {_vnd(target_amount, '?')}, đã có {_vnd(value, '0đ')} ({'giá trị hiện có của mục tiêu' if goal else 'nạp ban đầu'}) → còn thiếu {_vnd(gap, '0đ')}.",
        f"Cần góp mỗi tháng: {_vnd(monthly, '0đ')} (làm tròn lên nghìn đồng)." if monthly else "Không cần góp thêm: đã đủ tiền cho mục tiêu.",
        f"Ngày trích tự động gợi ý: ngày {day} hằng tháng (ngày sau ngày nhận lương {salary_day}).",
    ]
    if surplus_num is not None:
        lines.append(f"Còn dư hằng tháng của khách: {_vnd(surplus_num, '0đ')} → số góp {'VƯỢT' if plan['exceedsSurplus'] else 'nằm trong'} phần còn dư.")
    else:
        lines.append("Còn dư hằng tháng của khách: chưa đủ dữ liệu để so sánh.")
    order = goal["standingOrder"] if goal else None
    if order and order["active"]:
        lines.append(f"Trích tự động đang cài: {_vnd(order['amount'], '?')}/tháng vào ngày {order['dayOfMonth']}.")
    return "\n".join(lines), plan


@tool(response_format="content_and_artifact")
def plan_monthly(target_amount: int = 0, target_date: str = "", goal_id: str = "", initial_deposit: int = 0) -> tuple[str, dict | None]:
    """Compute the monthly saving plan (how much to save each month) for a goal, with pfm's own formula. ALWAYS use this instead of dividing yourself.

    New goal: pass `target_amount`, `target_date` (YYYY-MM-DD, after today) and `initial_deposit` (0 when none); leave `goal_id` empty.
    Existing goal after a change of amount and/or date: pass its `goal_id` (copied from get_goals) and the NEW `target_amount` and/or
    `target_date` (a value left out keeps the goal's current one); the goal's current value is taken from pfm. Returns the number of months,
    what is still missing, the amount to save each month (rounded up to the thousand), the suggested day of the auto-debit, and whether the
    amount is above what the customer has left each month. Use the numbers exactly as returned for `monthly_amount` and `monthly_day`.
    """
    try:
        summary = summarize_goals(fetch_goals_snapshot(_resolve_customer_id()))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return _unavailable("mục tiêu của khách để tính kế hoạch góp", exc), None
    return build_plan(summary, int(target_amount), str(target_date), str(goal_id), int(initial_deposit))

"""Scenario projection for investment guidance -- pure arithmetic, no I/O.

The model is bad at compounding across several checkpoints and several
scenarios, and a wrong figure here reaches a customer as money advice, so the
maths lives in code. The tool needs no customer identity (it only sees the
numbers the model passes), and it returns a ready-made `ui-json` line chart so
the model copies a block instead of re-typing series (a length mismatch makes
the server drop the whole chart -- see skills/project/data-visualization).

`DEFAULT_ASSUMED_MONTHLY_RETURN_PCT` is a PRODUCT-OWNER ASSUMPTION (set
2026-09-19), NOT a measured market average: nothing in this repo verifies it.
Every output labels it as a hypothetical scenario, always shows a flat (0%)
and a losing (-r) scenario next to it, and states the annualised equivalent,
so a projection is never presented as an expected or typical return.
"""

import calendar
import json
from datetime import date, timedelta

from langchain_core.tools import tool

from middleware import seed_customer_context

DEFAULT_ASSUMED_MONTHLY_RETURN_PCT = 2.0
MAX_ABS_MONTHLY_RETURN_PCT = 20.0
_AVG_MONTH_DAYS = 30.4375


def _vnd(value: float) -> str:
    return f"{round(value):,}".replace(",", ".") + "đ"


def _pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _checkpoints(today: date) -> list[date]:
    """today, then every month-end after today, up to Dec 31 of today's year."""
    year_end = date(today.year, 12, 31)
    points = [today]
    cursor = _month_end(today)
    while cursor <= year_end:
        if cursor > today:
            points.append(cursor)
        cursor = _month_end(cursor + timedelta(days=1))
    return points


def _months_between(start: date, end: date) -> float:
    return (end - start).days / _AVG_MONTH_DAYS


@tool
def project_investment_growth(
    principal_vnd: float = 0,
    target_gain_vnd: float = 0,
    monthly_return_pct: float = DEFAULT_ASSUMED_MONTHLY_RETURN_PCT,
) -> str:
    """Project what an investment could be worth on 31/12 under HYPOTHETICAL
    scenarios (+r%/month, flat 0%, and -r%/month), and/or how much capital
    would be needed to earn a target gain by year-end. Pure calculation --
    use it instead of doing compounding in your head.

    Give `principal_vnd` (amount the customer would invest) and/or
    `target_gain_vnd` (extra money the customer wants by year-end). Leave
    `monthly_return_pct` at its default unless the customer names their own
    assumption. The rate is an ASSUMPTION, never a measured market average:
    present results as "kịch bản giả định", always together with the flat and
    losing scenarios, never as expected or guaranteed returns.

    When `principal_vnd` > 0 the result ends with a complete `ui-json` line
    chart block: copy it verbatim into the answer if a chart is worthwhile.

    Args:
        principal_vnd: Amount invested, in VND (0 if unknown).
        target_gain_vnd: Desired extra money by 31/12, in VND (0 if none).
        monthly_return_pct: Assumed monthly return in percent (default 2.0).
    """
    if principal_vnd < 0 or target_gain_vnd < 0:
        return "principal_vnd và target_gain_vnd phải >= 0."
    if principal_vnd == 0 and target_gain_vnd == 0:
        return "Cần ít nhất 1 trong 2: principal_vnd (vốn đầu tư) hoặc target_gain_vnd (mục tiêu lãi)."
    rate_pct = abs(float(monthly_return_pct))
    if not 0 < rate_pct <= MAX_ABS_MONTHLY_RETURN_PCT:
        return f"monthly_return_pct phải khác 0 và không quá {MAX_ABS_MONTHLY_RETURN_PCT:g}%/tháng."
    rate = rate_pct / 100

    today = seed_customer_context._today().date()
    year_end = date(today.year, 12, 31)
    total_months = _months_between(today, year_end)
    if total_months <= 0:
        return f"Hôm nay ({today.strftime('%d/%m/%Y')}) đã là cuối năm, không còn thời gian để mô phỏng."

    annualised = ((1 + rate) ** 12 - 1) * 100
    lines = [
        f"Kịch bản GIẢ ĐỊNH (không phải mức trung bình của thị trường, không phải cam kết): "
        f"+{_pct(rate_pct)}%/tháng, tương đương khoảng +{_pct(annualised)}%/năm nếu cộng dồn "
        f"— rất cao so với lợi suất dài hạn thông thường. Kịch bản xấu: -{_pct(rate_pct)}%/tháng.",
        f"Thời gian: {today.strftime('%d/%m/%Y')} → {year_end.strftime('%d/%m/%Y')} "
        f"= {(year_end - today).days} ngày ≈ {_pct(total_months)} tháng.",
    ]

    growth_up = (1 + rate) ** total_months
    if target_gain_vnd > 0:
        needed = target_gain_vnd / (growth_up - 1)
        lines.append(
            f"Vốn cần đầu tư để lãi đạt {_vnd(target_gain_vnd)} vào 31/12: khoảng {_vnd(needed)} "
            f"nếu đúng kịch bản +{_pct(rate_pct)}%/tháng; nếu thị trường đi ngang (0%) hoặc giảm thì "
            "KHÔNG đạt được mục tiêu dù vốn bao nhiêu."
        )

    if principal_vnd > 0:
        points = _checkpoints(today)
        labels = [p.strftime("%d/%m") for p in points]
        series = {
            f"Kịch bản +{_pct(rate_pct)}%/tháng": [],
            "Đứng yên (0%)": [],
            f"Kịch bản -{_pct(rate_pct)}%/tháng": [],
        }
        up_name, flat_name, down_name = series
        rows = []
        for point, label in zip(points, labels):
            t = _months_between(today, point)
            up = principal_vnd * (1 + rate) ** t
            down = principal_vnd * (1 - rate) ** t
            series[up_name].append(round(up))
            series[flat_name].append(round(principal_vnd))
            series[down_name].append(round(down))
            rows.append(f"  {label}: {_vnd(up)} | {_vnd(principal_vnd)} | {_vnd(down)}")

        final_up, final_down = series[up_name][-1], series[down_name][-1]
        lines.append(f"Vốn đầu tư: {_vnd(principal_vnd)}.")
        lines.append(f"Giá trị theo mốc ({up_name} | {flat_name} | {down_name}):")
        lines.extend(rows)
        lines.append(
            f"Đến 31/12: lãi {_vnd(final_up - principal_vnd)} (kịch bản +), "
            f"{'lỗ ' + _vnd(principal_vnd - final_down)} (kịch bản -)."
        )
        if target_gain_vnd > 0:
            required = target_gain_vnd / principal_vnd
            required_monthly = ((1 + required) ** (1 / total_months) - 1) * 100
            required_annual = ((1 + required) ** (12 / total_months) - 1) * 100
            lines.append(
                f"Lợi suất cần có để lãi {_vnd(target_gain_vnd)} từ vốn {_vnd(principal_vnd)}: "
                f"+{_pct(required * 100)}% trong {_pct(total_months)} tháng ≈ +{_pct(required_monthly)}%/tháng "
                f"(≈ +{_pct(required_annual)}%/năm nếu cộng dồn)."
            )
            if final_up - principal_vnd >= target_gain_vnd:
                lines.append(
                    f"Với vốn này, mục tiêu lãi {_vnd(target_gain_vnd)} ĐẠT trong kịch bản "
                    f"+{_pct(rate_pct)}%/tháng; nếu thị trường đi ngang (0%) hoặc giảm thì KHÔNG đạt."
                )
            else:
                lines.append(
                    f"Với vốn này, mục tiêu lãi {_vnd(target_gain_vnd)} KHÔNG đạt ngay cả trong "
                    f"kịch bản +{_pct(rate_pct)}%/tháng."
                )
        chart = {
            "type": "chart",
            "chart_type": "line",
            "title": "Mô phỏng giá trị khoản đầu tư đến 31/12 (kịch bản giả định)",
            "labels": labels,
            "series": [{"name": name, "data": data} for name, data in series.items()],
        }
        lines.append("Khối biểu đồ (sao chép nguyên văn vào ```ui-json nếu cần vẽ, không tự sửa số):")
        lines.append(json.dumps(chart, ensure_ascii=False))
    return "\n".join(lines)

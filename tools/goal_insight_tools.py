"""`get_goal_insight`: gives the chat the card M-You showed on the goal screen and every number the insight agent worked from.

The "Chi tiết" button on that card sends the card's `question` to the chat as if the customer typed it. To answer it the chat
needs what the card was written from: the card itself (read back from pfm, never regenerated here) and the same computed
digest (cash flow against the last 3 months, real jar surplus, price moves over 30/90 days, loan option, deposit rates,
repayment risk). Both come from `goal_suggest`, so the chat and the card can never disagree on a figure."""

from __future__ import annotations

import re

import httpx
from langchain_core.tools import tool

from goal_suggest import data, digest
from middleware.seed_customer_context import _resolve_customer_id
from tools.customer_data_tools import PFM_BASE_URL, PFM_REQUEST_TIMEOUT_SECONDS
from tools.goal_tools import summarize_goals


def stored_card(customer_id: str, goal_id: str) -> dict | None:
    """The card pfm last stored for this goal (`peek` = read only, it never starts a new one), or None."""
    try:
        response = httpx.get(
            f"{PFM_BASE_URL}/api/goals-v2/insight",
            params={"cif": customer_id, "goalId": goal_id, "peek": "1"},
            timeout=PFM_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        insight = response.json().get("insight")
    except (httpx.HTTPError, ValueError):
        return None
    return insight if isinstance(insight, dict) and insight.get("observation") else None


def render_card(card: dict | None) -> list[str]:
    lines = ["== THẺ M-YOU GỢI Ý ĐÃ HIỆN CHO KHÁCH TRÊN MÀN MỤC TIÊU =="]
    if not card:
        return lines + ["Chưa có thẻ nào được lưu cho mục tiêu này (hoặc không đọc được). Trả lời dựa trên dữ liệu bên dưới."]
    lines += [f"Ô trên (điều M-You nhận thấy): {card['observation']}", f"Ô gợi ý: {card['suggestion']}"]
    if card.get("question"):
        lines.append(f"Câu hỏi khách gửi khi bấm \"Chi tiết\": {card['question']}")
    return lines


def _by_deadline(summary: dict, text: str) -> str:
    """A goal named together with its deadline ("Mua nhà hạn 15/09/2031") becomes that goal's id when exactly one matches."""
    for day in re.findall(r"\d{1,2}/\d{1,2}/\d{4}", text):
        name = re.sub(r"\s*(hạn|đến|tới|ngày)?\s*\d{1,2}/\d{1,2}/\d{4}.*$", "", text, flags=re.IGNORECASE).strip()
        match = [g for g in summary["goals"] if digest.dmy(g["targetDate"]) == day and (not name or digest._fold(name) in digest._fold(g["name"]))]
        if len(match) == 1:
            return match[0]["id"]
    return text


@tool(response_format="content_and_artifact")
def get_goal_insight(goal: str = "") -> tuple[str, dict | None]:
    """Read the M-You card shown on a goal and all the figures it was written from. Use it for questions about WHY a goal is
    behind, what to do to catch up, or the follow-up question that comes from the card's "Chi tiết" button.

    `goal` is the goal's `id` (from get_goals) or its name; leave it empty only when the customer has a single goal. Returns the
    card (observation, suggestion, the question the customer sent), then the computed data: goal progress and adjustment options
    (raise the monthly amount / move the date / lower the target), cash flow this month against the last 3 months with the
    categories that moved most, jars with their real surplus, price moves of market assets over 30 and 90 days, the loan option,
    MSB online deposit rates, repayment risk, and the points already judged worth saying. Every figure is computed, copy it as is.
    """
    customer_id = _resolve_customer_id()
    try:
        raw = data.collect(customer_id)
        summary = summarize_goals(raw["snapshot"])
        wanted = goal.strip()
        if not wanted:
            live = [g for g in summary["goals"] if g["status"] in ("accumulating", "repaying")]
            if len(live) != 1:
                names = "; ".join(f"{g['name']} ({g['id']})" for g in summary["goals"]) or "không có"
                return f"Cần biết khách hỏi về mục tiêu nào. Các mục tiêu: {names}. Hỏi lại khách, đừng đoán.", None
            wanted = live[0]["id"]
        by_id = re.fullmatch(r"goal-[\w-]+", wanted) is not None
        if not by_id:
            wanted = _by_deadline(summary, wanted)
            by_id = re.fullmatch(r"goal-[\w-]+", wanted) is not None
        goal_row, text, _ = digest.build_full(raw, wanted if by_id else None, None if by_id else wanted)
    except digest.GoalNotFound:
        return f"Không tìm thấy mục tiêu \"{goal}\" của khách. Gọi get_goals để xem các mục tiêu, đừng đoán.", None
    except digest.GoalAmbiguous as exc:
        options = "; ".join(f"{g['id']} ({g['name']}, hạn {digest.dmy(g['targetDate'])}, mục tiêu {digest.vnd(g['targetAmount'])})" for g in summary["goals"] if g["id"] in str(exc).split(", "))
        return (f"Có nhiều mục tiêu khớp \"{goal}\": {options}. Đối chiếu hạn hoặc số tiền trong câu hỏi của khách rồi gọi lại với đúng id; "
                "chỉ hỏi khách nếu câu hỏi không có gì để phân biệt."), None
    except (data.DataUnavailable, httpx.HTTPError, ValueError, KeyError) as exc:
        return f"Không thể đọc dữ liệu mục tiêu lúc này ({type(exc).__name__}). Đừng đoán số, báo khách hệ thống đang gián đoạn.", None
    card = stored_card(customer_id, goal_row["id"])
    return "\n".join(render_card(card)) + "\n\n" + text, {"goalId": goal_row["id"], "goalName": goal_row["name"], "card": card}

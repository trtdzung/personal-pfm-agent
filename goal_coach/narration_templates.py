"""Fixed fallback sentences for narration. Same rules as LLM text: no digits, placeholders only.

Placeholders are filled by pfm from the engine's Analysis, so every number still comes from code.
"""

from __future__ import annotations

from .contracts import DialogueAction, PlanId, Verdict

# Placeholders a sentence may use; anything else is rejected by the validator.
PLACEHOLDERS: frozenset[str] = frozenset(
    {"monthly_needed", "surplus", "target_amount", "new_date", "new_amount", "months", "cut_amount"}
)

VERDICT_TEXT: dict[Verdict, str] = {
    "feasible": (
        "Tin vui: mục tiêu này nằm trong khả năng của bạn. "
        "Mỗi tháng cần góp khoảng {monthly_needed}, vẫn nằm trong phần dư {surplus} của bạn."
    ),
    "stretch": (
        "Mục tiêu làm được nhưng khá sát: mỗi tháng cần góp khoảng {monthly_needed}, "
        "gần bằng toàn bộ phần dư {surplus} của bạn."
    ),
    "not_feasible": (
        "Với kế hoạch này, mỗi tháng cần góp khoảng {monthly_needed}, vượt phần dư {surplus} hiện tại. "
        "Mình có vài cách điều chỉnh để mục tiêu vẫn nằm trong tầm với."
    ),
    "unknown": (
        "Mình chưa đủ dữ liệu thu chi để so với phần dư của bạn. "
        "Mức cần góp khoảng {monthly_needed} mỗi tháng, bạn cân nhắc xem có phù hợp không nhé."
    ),
}

PLAN_TEXT: dict[tuple[PlanId, Verdict], str] = {
    ("keep_deadline", "feasible"): "Giữ nguyên hạn: góp đều {monthly_needed} mỗi tháng là bạn đạt mục tiêu đúng kế hoạch.",
    ("keep_deadline", "stretch"): "Giữ nguyên hạn: góp {monthly_needed} mỗi tháng, cần theo sát chi tiêu để không bị hụt.",
    ("keep_deadline", "not_feasible"): (
        "Giữ nguyên hạn: góp {monthly_needed} mỗi tháng, cần giảm chi khoảng {cut_amount} mỗi tháng "
        "và dùng thêm khoản tiền đang nhàn rỗi."
    ),
    ("keep_deadline", "unknown"): "Giữ nguyên hạn: góp khoảng {monthly_needed} mỗi tháng.",
    ("extend_deadline", "feasible"): "Lùi hạn đến {new_date}: nhẹ gánh hơn, mỗi tháng chỉ góp khoảng {monthly_needed}.",
    ("extend_deadline", "stretch"): "Lùi hạn đến {new_date}: mỗi tháng góp khoảng {monthly_needed}, bớt sát so với phần dư.",
    ("extend_deadline", "not_feasible"): "Lùi hạn đến {new_date}: mỗi tháng góp khoảng {monthly_needed}, nằm trong phần dư của bạn.",
    ("extend_deadline", "unknown"): "Lùi hạn đến {new_date}: mỗi tháng góp khoảng {monthly_needed}.",
    ("reduce_amount", "feasible"): "Giảm mục tiêu còn {new_amount}: giữ nguyên hạn, góp khoảng {monthly_needed} mỗi tháng.",
    ("reduce_amount", "stretch"): "Giảm mục tiêu còn {new_amount}: giữ nguyên hạn, góp khoảng {monthly_needed} mỗi tháng, bớt áp lực hơn.",
    ("reduce_amount", "not_feasible"): "Giảm mục tiêu còn {new_amount}: giữ nguyên hạn, góp khoảng {monthly_needed} mỗi tháng, vừa sức với phần dư.",
    ("reduce_amount", "unknown"): "Giảm mục tiêu còn {new_amount}: giữ nguyên hạn, góp khoảng {monthly_needed} mỗi tháng.",
}


def say_text(action: DialogueAction, goal_name: str | None) -> str:
    """Fallback sentence for a dialogue action: exactly one question, ready to show."""
    what = f"mục tiêu {goal_name}" if goal_name else "mục tiêu này"
    return {
        "ask_purpose": "Bạn đang muốn dành tiền cho điều gì vậy?",
        "ask_amount": f"Bạn cần khoảng bao nhiêu tiền cho {what}?",
        "ask_horizon": f"Bạn muốn đạt {what} trong bao lâu?",
        "ask_opening": f"Bạn đã để dành sẵn được khoản nào cho {what} chưa?",
        "reflect": f"Mình ghi nhận {what} rồi, mình tính thử cho bạn ngay nhé?",
        "present_plans": "Mình đã tính ra ba cách cho bạn, bạn thấy cách nào hợp với bạn nhất?",
        "confirm": f"Bạn xem lại thông tin của {what} rồi xác nhận để mình lưu nhé?",
        "handle_objection": "Mình hiểu băn khoăn của bạn, mình thử điều chỉnh để nhẹ hơn, bạn thấy ổn không?",
    }[action]

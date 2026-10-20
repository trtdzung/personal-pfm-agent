"""`estimate_goal_price`: the chat's version of "Chưa rõ? Để M-You ước tính" on the create-goal screen.

The customer describes what they want to buy and ticks a few attributes (area, type, brand...). This tool researches the market
price with the same code as the create-goal screen (`goal_price.service`): TinyFish Search snippets, prices verified against the
snippet text, the proposal computed in code, and the model's own rough estimate (marked as such) only when the web has nothing."""

from __future__ import annotations

from langchain_core.tools import tool

from goal_price import research, service
from goal_price.contracts import MAX_CHOSEN, MAX_QUESTIONS, PriceEstimateRequest
from goal_price.service import LABELS

_BAD_INPUT = "Thiếu mô tả sản phẩm khách muốn mua. Hỏi lại khách (bằng nút bấm) rồi gọi lại, đừng tự đoán."


def _money(vnd: int) -> str:
    return f"{vnd:,}".replace(",", ".") + " VND"


def _request(template: str, description: str, details: list[str]) -> PriceEstimateRequest | None:
    template = template.strip().lower()
    if template not in LABELS:
        template = "other"
    description = " ".join(description.split())[:200]
    chosen = [" ".join(d.split())[:80] for d in details if d and d.strip()][:MAX_CHOSEN]
    if not description and not chosen:
        return None
    # one "question" per ticked detail: the research only needs the words, not which question they answered
    answers = {f"q{i}": [d] for i, d in enumerate(chosen[:MAX_QUESTIONS], 1)}
    return PriceEstimateRequest(user_id="chat", template=template, description=description or None, answers=answers or {})


def render(estimate) -> str:
    lines = [
        f"Giá tham khảo đề xuất cho mục tiêu: {_money(estimate.amount)} (khoảng {_money(estimate.low)} đến {_money(estimate.high)}).",
        estimate.summary,
    ]
    if estimate.sources:
        lines.append("Nguồn:")
        lines += [f"- {s.title} ({s.url})" for s in estimate.sources]
    else:
        lines.append("KHÔNG có nguồn web: đây là ước tính của M-You, nói rõ điều này với khách và để khách tự chỉnh số.")
    lines.append("Mọi con số đã được tính sẵn: chép nguyên văn, không tự tính lại. Đây là giá tham khảo, không phải báo giá chính thức.")
    return "\n".join(lines)


@tool(response_format="content_and_artifact")
def estimate_goal_price(template: str, description: str = "", details: list[str] | None = None) -> tuple[str, dict | None]:
    """Research the market price of what the customer wants to save for, when they do not know how much it costs. Use it after
    the customer has said what they want and picked a few attributes (area, type, condition, brand, fuel...).

    `template` is the goal type (car, house, travel, education, wedding, retirement, emergency, other). `description` is the
    product in the customer's words ("căn hộ 2 phòng ngủ", "VinFast VF6"). `details` are the attributes they chose, each as
    short text ("TP. Hồ Chí Minh", "50–70 m²", "Xe điện"). Send ONLY public product words: never the customer's name, balance,
    income or any personal data. Returns a proposed price with its range and the web sources (or says it is the model's own
    estimate without sources). Figures are computed: copy them as is.
    """
    request = _request(template, description, details or [])
    if request is None:
        return _BAD_INPUT, None
    try:
        estimate, reason = service.research_price(
            request,
            service.generate_with_llm(service._Extraction),
            research.search,
            service.generate_with_llm(service._Guess),
        )
    except Exception as exc:  # never let a research failure break the chat turn
        return f"Chưa ước tính được giá lúc này ({type(exc).__name__}). Hỏi khách số tiền mục tiêu bằng các mốc, đừng tự bịa giá.", None
    if estimate is None:
        return "Chưa ước tính được giá cho lựa chọn này. Hỏi khách số tiền mục tiêu bằng các mốc, đừng tự bịa giá.", {"reason": reason}
    return render(estimate), estimate.model_dump(mode="json")

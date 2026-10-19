"""Look-ups behind the "Kiểm tra bảo mật cho link/số điện thoại/tài khoản/tin nhắn" flow.

Each tool calls one of `pfm`'s reference endpoints (`/api/msb-reference/*`: MSB's official channels, its live
promotions, and a fraud watch list). They carry no customer data -- only what the customer pasted to be
checked -- so unlike the other pfm tools they take no CIF.

A miss is never reported as "safe" or "fake": absence from a list is evidence, not proof. The model draws the
conclusion; these tools only report what the lists say, or that they could not be reached.
"""

import httpx
from langchain_core.tools import tool

from tools.customer_data_tools import PFM_BASE_URL, PFM_REQUEST_TIMEOUT_SECONDS

_STATUS_VI = {"active": "đang diễn ra", "upcoming": "sắp diễn ra", "expired": "đã kết thúc"}


def _get(path: str, params: dict) -> dict | None:
    try:
        response = httpx.get(f"{PFM_BASE_URL}/api/msb-reference/{path}", params=params, timeout=PFM_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _outage(what: str) -> str:
    return (
        f"Hiện không tra cứu được {what} (hệ thống pfm gián đoạn). Đừng kết luận gì từ nguồn này; "
        "nói rõ với khách là chưa kiểm tra được và khuyên họ xác nhận qua hotline/app chính thức của MSB."
    )


@tool
def check_official_channel(value: str) -> str:
    """Check whether a link/domain, hotline number, SMS sender name or app name is an OFFICIAL MSB channel.

    Pass the value exactly as the customer pasted it (a full URL is fine). Subdomains of the official site
    count as official; look-alike domains do not.
    """
    data = _get("official-channels", {"value": value})
    if data is None:
        return _outage("danh sách kênh chính thức của MSB")
    channel = data.get("channel")
    if data.get("official") and isinstance(channel, dict):
        return f"Kênh chính thức của MSB: {channel.get('label')} ({channel.get('type')}: {channel.get('value')})."
    return (
        "Giá trị này không nằm trong danh sách kênh chính thức của MSB "
        "(website, hotline, tên SMS brandname, ứng dụng)."
    )


@tool
def check_fraud_watchlist(value: str) -> str:
    """Look up a phone number, bank account number or link/domain in the known-fraud watch list.

    Pass the value exactly as the customer pasted it. A miss only means "not on the list" -- never tell the
    customer it is safe because of that.
    """
    data = _get("fraud-watchlist", {"value": value})
    if data is None:
        return _outage("danh sách cảnh báo lừa đảo")
    entries = data.get("entries") or []
    if not entries:
        return (
            "Giá trị này không có trong danh sách cảnh báo lừa đảo hiện có. "
            "Điều đó không đồng nghĩa với an toàn: danh sách chỉ gồm các trường hợp đã được báo cáo."
        )
    lines = [f"- {e.get('type')} {e.get('value')}: {e.get('reason')} ({e.get('reports')} lượt báo cáo)" for e in entries]
    return "Có trong danh sách cảnh báo lừa đảo:\n" + "\n".join(lines)


@tool
def search_msb_promotions(query: str) -> str:
    """Search MSB's promotions (khuyến mãi/ưu đãi) by a short keyword, e.g. "hoàn tiền", "tiền gửi", "du lịch".

    Use it when a message promises a refund, prize or offer in MSB's name: it tells whether any such program
    exists, its status and its dates. An empty result means no such program in MSB's list, which is a
    reason for suspicion, not proof.
    """
    data = _get("promotions", {"q": query})
    if data is None:
        return _outage("danh sách chương trình khuyến mãi của MSB")
    items = data.get("items") or []
    if not items:
        return f"Không tìm thấy chương trình khuyến mãi nào của MSB khớp \"{query}\" trong danh sách hiện có."
    lines = [
        f"- {p.get('name')} — {_STATUS_VI.get(p.get('status'), p.get('status'))}, "
        f"{p.get('startDate')} đến {p.get('endDate')}, trang chính thức: {p.get('officialUrl')}"
        for p in items
    ]
    return "Chương trình khuyến mãi của MSB khớp từ khóa:\n" + "\n".join(lines)

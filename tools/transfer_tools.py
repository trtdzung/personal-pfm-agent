import json
from pathlib import Path

from langchain_core.tools import tool
from langgraph.config import get_config

CUSTOMERS_DIR = Path(__file__).resolve().parent.parent / "data" / "customers"
DEFAULT_CUSTOMER_ID = "CIF_0001"


def _resolve_customer_id() -> str:
    """Same actor_id resolution as middleware/seed_customer_context.py --
    duplicated here (rather than imported) so this tool has no dependency on
    the agent middleware module, only on get_config()."""
    try:
        config = get_config()
    except RuntimeError:
        return DEFAULT_CUSTOMER_ID
    actor_id = config.get("configurable", {}).get("actor_id")
    return actor_id or DEFAULT_CUSTOMER_ID


@tool
def check_available_balance_or_credit(amount_vnd: float) -> str:
    """Check whether a proposed amount (VND) fits within the current
    customer's available credit on any of their cards, BEFORE emitting a
    transfer_form ui-json block. ALWAYS call this before proposing a
    transfer_form -- never compute this by hand from data already read, the
    exact available amount can change between turns and this tool is the
    single source of truth for the check. Returns, per card, whether the
    amount fits and the actual available_credit_vnd, so you can pick a card
    or adjust the amount before proposing the form."""
    customer_id = _resolve_customer_id()
    path = CUSTOMERS_DIR / f"{customer_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    if not cards:
        return "Khách hàng hiện không có thẻ nào để kiểm tra hạn mức."

    lines = []
    any_sufficient = False
    for card in cards:
        available = card.get("available_credit_vnd", 0)
        sufficient = available >= amount_vnd
        any_sufficient = any_sufficient or sufficient
        status = "ĐỦ" if sufficient else "KHÔNG ĐỦ"
        name = card.get("card_name") or card.get("card_id", "thẻ")
        lines.append(f"- {name} ({card.get('card_id')}): hạn mức khả dụng {available:,.0f} VND -- {status}")

    header = (
        f"Có ít nhất 1 thẻ đủ hạn mức khả dụng cho {amount_vnd:,.0f} VND."
        if any_sufficient
        else (
            f"KHÔNG có thẻ nào đủ hạn mức khả dụng cho {amount_vnd:,.0f} VND -- "
            "đừng đề xuất transfer_form với số tiền này, báo cho khách hàng biết giới hạn thật."
        )
    )
    return header + "\n" + "\n".join(lines)

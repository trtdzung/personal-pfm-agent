"""Tools that return the current customer's own product data as an
explicit, callable tool result -- instead of the agent only ever seeing
this data passively baked into the `/customer_data.json` snapshot already
injected into every system prompt (see `middleware/seed_customer_context.py`).

`list_existing_jars()` is still **mock**: the data is hardcoded right here
in this module (keyed by customer_id), not read from any file -- this
stands in for the real `GET /api/jars?cif=` endpoint documented in
`backend_docs/pfm-read-api.md` (not wired up yet; real jar data is coming
later, see todo.md). Field mapping for that swap: `allocation_amount_vnd` ~
`budgetLimit` (monthly cap), `balance_vnd` ~ `actualAmount` (money currently
in the jar; the real API returns null for it today). Jar names are whatever
the customer chose -- callers (e.g. the investment-guidance skill) must not
assume a jar called "tiết kiệm" exists, only use the amounts.

`query_beneficiaries()` calls the REAL `pfm` backend
(`GET /api/beneficiaries?cif=`, see `backend_docs/pfm-read-api.md`) --
no mock data. `data/customers/<id>.json` deliberately has no
`jars`/`beneficiaries` fields anymore -- these two pieces of data are
reachable *only* through these tools now, not also passively visible in
the system prompt.

`customer_id` is deliberately **not** a tool parameter the model supplies --
resolved from the current run's `actor_id` via `_resolve_customer_id()`
(same helper `SeedCustomerContext` uses), exactly like
`tools/memory_tools.py` does for `actor_id`. The real PFM call must be
scoped to whoever is actually asking, not to whatever customer_id string
the model happens to type -- letting the model supply it would let a
prompt-injected or simply mistaken value read another customer's
beneficiaries.
"""

import httpx
from langchain_core.tools import tool

from middleware.seed_customer_context import _resolve_customer_id

PFM_BASE_URL = "https://endpoint-6529c773-a2b3-4a42-b28a-6bcdced3ceff.agentbase-runtime.aiplatform.vngcloud.vn"
PFM_REQUEST_TIMEOUT_SECONDS = 10.0

_MOCK_JARS = {
    "CIF_0001": [
        {
            "jar_id": "jar_001",
            "jar_name": "Giải trí",
            "allocation_amount_vnd": 600000,
            "balance_vnd": 350000,
            "created_on": "2026-07-05",
        },
        {
            "jar_id": "jar_002",
            "jar_name": "Tiết kiệm khẩn cấp",
            "allocation_amount_vnd": 5000000,
            "balance_vnd": 15000000,
            "created_on": "2026-06-20",
        },
    ],
    # Deliberately no jar named "tiết kiệm" for this customer.
    "CIF_0002": [
        {
            "jar_id": "jar_001",
            "jar_name": "Hoá đơn",
            "allocation_amount_vnd": 6200000,
            "balance_vnd": 4000000,
            "created_on": "2026-06-10",
        },
    ],
    "CIF_0003": [],
}


@tool
def list_existing_jars() -> str:
    """List the current customer's existing spending jars (hũ chi tiêu).

    Call this before proposing create_jar/edit_jar to check whether a jar
    already exists -- this reads fresh on every call instead of relying on
    the /customer_data.json snapshot already in your system prompt, so it
    reflects jars created/edited since the start of this conversation.

    Each jar shows its monthly allocation and the money currently in it
    ("số dư"). Jar names are chosen by the customer: for investment advice
    use only the AMOUNTS (e.g. the total balance across jars), never assume a
    jar named "tiết kiệm" exists.
    """
    customer_id = _resolve_customer_id()
    jars = _MOCK_JARS.get(customer_id, [])
    if not jars:
        return "Khách hàng hiện chưa có hũ chi tiêu nào."
    def vnd(amount: int) -> str:
        return f"{amount:,}".replace(",", ".") + "đ"

    lines = [
        f"- {jar['jar_name']}: hạn mức {vnd(jar['allocation_amount_vnd'])}/tháng, "
        f"số dư hiện có {vnd(jar['balance_vnd'])} (tạo ngày {jar['created_on']})"
        for jar in jars
    ]
    lines.append(f"Tổng số dư các hũ: {vnd(sum(jar['balance_vnd'] for jar in jars))}")
    return "\n".join(lines)


@tool
def query_beneficiaries() -> str:
    """List the current customer's saved money-transfer beneficiaries (danh
    bạ người nhận đã lưu), fetched live from the real pfm backend.

    Call this FIRST, before proposing any transfer_form to a named person --
    it returns the full saved list (name, bank, and the `id` you MUST use
    as `beneficiary_id` in the transfer_form ui-json; never invent an
    account number or bank name yourself). This reads fresh on every call
    instead of relying on any snapshot in your system prompt.
    """
    customer_id = _resolve_customer_id()
    url = f"{PFM_BASE_URL}/api/beneficiaries"
    try:
        response = httpx.get(
            url,
            params={"cif": customer_id},
            timeout=PFM_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        beneficiaries = response.json()
    except httpx.HTTPError as exc:
        return (
            "Không thể lấy danh sách người nhận đã lưu lúc này (lỗi kết nối "
            f"tới hệ thống pfm: {exc}). Đừng tự bịa người nhận -- báo cho "
            "khách hàng là hệ thống đang gián đoạn."
        )
    if not beneficiaries:
        return "Khách hàng hiện chưa lưu người nhận nào trong danh bạ."
    lines = [
        f"- {b['name']} (id: {b['id']}): STK {b['accountNumber']} ({b['bankName']})"
        for b in beneficiaries
    ]
    return "\n".join(lines)

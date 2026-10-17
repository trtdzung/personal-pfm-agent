"""Tools that return the current customer's own product data as an
explicit, callable tool result -- instead of the agent only ever seeing
this data passively baked into the `/customer_data.json` snapshot already
injected into every system prompt (see `middleware/seed_customer_context.py`).

Both tools below are **mock**: the data is hardcoded right here in this
module (keyed by customer_id), not read from any file. This stands in for
the real PFM/core-banking calls noted in todo.md
(`list_existing_jars()`/`query_beneficiaries()` under "Roadmap PFM"), so
the *interface* (a tool the model calls, with the identity of the caller
resolved server-side) is the same shape a real integration would have --
only the implementation behind it is mocked. `data/customers/<id>.json`
deliberately has no `jars`/`beneficiaries` fields anymore -- these two
pieces of data are reachable *only* through these tools now, not also
passively visible in the system prompt.

`customer_id` is deliberately **not** a tool parameter the model supplies --
resolved from the current run's `actor_id` via `_resolve_customer_id()`
(same helper `SeedCustomerContext` uses), exactly like
`tools/memory_tools.py` does for `actor_id`. A real PFM/core-banking call
must be scoped to whoever is actually asking, not to whatever customer_id
string the model happens to type -- letting the model supply it would let a
prompt-injected or simply mistaken value read another customer's jars/
beneficiaries.
"""

from langchain_core.tools import tool

from middleware.seed_customer_context import _resolve_customer_id

_MOCK_JARS = {
    "CIF_0001": [
        {
            "jar_id": "jar_001",
            "jar_name": "Giải trí",
            "allocation_amount_vnd": 600000,
            "created_on": "2026-07-05",
        },
        {
            "jar_id": "jar_002",
            "jar_name": "Tiết kiệm khẩn cấp",
            "allocation_amount_vnd": 5000000,
            "created_on": "2026-06-20",
        },
    ],
    "CIF_0002": [
        {
            "jar_id": "jar_001",
            "jar_name": "Hoá đơn",
            "allocation_amount_vnd": 6200000,
            "created_on": "2026-06-10",
        },
    ],
    "CIF_0003": [],
}

_MOCK_BENEFICIARIES = {
    "CIF_0001": [
        {"name": "Toàn", "account_number": "00012000321", "bank_name": "Techcombank"},
    ],
    "CIF_0002": [],
    "CIF_0003": [],
}


@tool
def list_existing_jars() -> str:
    """List the current customer's existing spending jars (hũ chi tiêu).

    Call this before proposing create_jar/edit_jar to check whether a jar
    already exists -- this reads fresh on every call instead of relying on
    the /customer_data.json snapshot already in your system prompt, so it
    reflects jars created/edited since the start of this conversation.
    """
    customer_id = _resolve_customer_id()
    jars = _MOCK_JARS.get(customer_id, [])
    if not jars:
        return "Khách hàng hiện chưa có hũ chi tiêu nào."
    lines = [
        f"- {jar['jar_name']}: {jar['allocation_amount_vnd']:,}đ/tháng (tạo ngày {jar['created_on']})".replace(
            ",", "."
        )
        for jar in jars
    ]
    return "\n".join(lines)


@tool
def query_beneficiaries() -> str:
    """List the current customer's saved money-transfer beneficiaries (danh
    bạ người nhận đã lưu).

    Call this before proposing a transfer_form to a named person, to find
    their real account_number/bank_name -- this reads fresh on every call
    instead of relying on the /customer_data.json snapshot already in your
    system prompt.
    """
    customer_id = _resolve_customer_id()
    beneficiaries = _MOCK_BENEFICIARIES.get(customer_id, [])
    if not beneficiaries:
        return "Khách hàng hiện chưa lưu người nhận nào trong danh bạ."
    lines = [f"- {b['name']}: STK {b['account_number']} ({b['bank_name']})" for b in beneficiaries]
    return "\n".join(lines)

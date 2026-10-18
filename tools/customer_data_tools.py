"""Tools that return the current customer's own product data as an
explicit, callable tool result -- instead of the agent only ever seeing
this data passively baked into the `/customer_data.json` snapshot already
injected into every system prompt (see `middleware/seed_customer_context.py`).

Both tools call the REAL `pfm` backend and map (almost) 1:1 onto one of its
read endpoints, documented in `backend_docs/pfm-read-api.md`:

- `get_jar_summary(month)`  <->  `GET /api/jar-summary?cif=&month=`
- `query_beneficiaries()`   <->  `GET /api/beneficiaries?cif=`

The tools only render what the endpoint returned (field names kept as they
are, so the skills can talk about `spendable`/`allocationHeadroom` and the
model sees the same words) -- all jar numbers come from pfm's own engine, the
agent never adds transactions up itself. `data/customers/<id>.json`
deliberately has no `jars`/`beneficiaries` fields anymore: these two pieces
of data are reachable *only* through these tools, not also passively visible
in the system prompt.

`customer_id` is deliberately **not** a tool parameter the model supplies --
resolved from the current run's `actor_id` via `_resolve_customer_id()`
(same helper `SeedCustomerContext` uses), exactly like
`tools/memory_tools.py` does for `actor_id`. The real PFM call must be
scoped to whoever is actually asking, not to whatever customer_id string
the model happens to type -- letting the model supply it would let a
prompt-injected or simply mistaken value read another customer's
jars or beneficiaries.
"""

import re

import httpx
from langchain_core.tools import tool

from middleware.seed_customer_context import _resolve_customer_id

PFM_BASE_URL = "https://endpoint-6529c773-a2b3-4a42-b28a-6bcdced3ceff.agentbase-runtime.aiplatform.vngcloud.vn"
PFM_REQUEST_TIMEOUT_SECONDS = 10.0

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _vnd(amount: float | None, unknown: str) -> str:
    """`1.622.000đ`; `null` from pfm is "not known / not set", never 0 (so `unknown` says which)."""
    if amount is None:
        return unknown
    return f"{round(amount):,}".replace(",", ".") + "đ"


def _yes_no(flag: object) -> str:
    return "có" if flag else "không"


def _jar_line(jar: dict) -> str:
    parts = [str(jar.get("label", "?")), f"id: {jar.get('id', '?')}"]
    if jar.get("role"):
        parts.append(f"role: {jar['role']}")
    parts.append(f"categoryIds: {', '.join(jar.get('categoryIds') or []) or 'không có'}")
    parts.append(f"budgetLimit: {_vnd(jar.get('budgetLimit'), 'chưa đặt')}")
    parts.append(f"spent: {_vnd(jar.get('spent'), 'chưa biết')}")
    parts.append(f"remaining: {_vnd(jar.get('remaining'), 'chưa biết')}")
    parts.append(f"spendable: {_vnd(jar.get('spendable'), 'chưa biết')}")
    parts.append(f"overLimit: {_yes_no(jar.get('overLimit'))}")
    return "- " + " | ".join(parts)


@tool
def get_jar_summary(month: str = "") -> str:
    """Read the current customer's spending jars (hũ chi tiêu) for one month,
    live from the pfm backend (`GET /api/jar-summary`). The numbers come from
    pfm's own engine -- the same ones the customer sees on the Budget screen --
    so never add transactions up yourself.

    Call this before proposing create_jar / edit_jar / rebalance_jars, and call
    it AGAIN after the customer confirmed a change (the numbers moved).

    `month` is optional, `YYYY-MM`; leave it empty for the current month.

    Per jar: `budgetLimit` (monthly limit, "chưa đặt" = not set, NOT 0), `spent`,
    `remaining` (the jar's balance, can be negative), `spendable` (= max(0,
    remaining), the most the jar can give away), `role`, `categoryIds` (one
    category belongs to exactly one jar). Globals: `casaBalance` (real money in
    the payment account), `unallocated` (the "pool" source for rebalancing),
    `allocationHeadroom` (how much MORE limit can still be set; negative = the
    limits already exceed the account). "chưa biết"/"chưa đặt" means unknown:
    never treat it as 0, never guess it.
    """
    if month and not _MONTH_RE.match(month):
        return f"Tháng phải có dạng YYYY-MM (ví dụ 2026-09), nhận được: {month!r}. Bỏ trống để lấy tháng hiện tại."
    customer_id = _resolve_customer_id()
    params = {"cif": customer_id}
    if month:
        params["month"] = month
    try:
        response = httpx.get(
            f"{PFM_BASE_URL}/api/jar-summary",
            params=params,
            timeout=PFM_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        summary = response.json()
        if not isinstance(summary, dict):
            raise ValueError("unexpected response shape")
    except (httpx.HTTPError, ValueError) as exc:
        return (
            "Không thể đọc thông tin hũ lúc này (lỗi từ hệ thống pfm: "
            f"{exc}). Đừng đoán số và đừng trả form hũ (create_jar/edit_jar/rebalance_jars) -- "
            "báo cho khách hàng là hệ thống đang gián đoạn."
        )
    lines = [
        f"month: {summary.get('month', month or 'tháng hiện tại')}",
        f"casaBalance: {_vnd(summary.get('casaBalance'), 'chưa biết')}",
        f"unallocated: {_vnd(summary.get('unallocated'), 'chưa biết')}",
        f"allocationHeadroom: {_vnd(summary.get('allocationHeadroom'), 'chưa biết')}",
    ]
    jars = summary.get("jars") or []
    if not jars:
        lines.append("Khách hàng chưa có hũ nào.")
    else:
        lines.append("Các hũ:")
        lines.extend(_jar_line(jar) for jar in jars)
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

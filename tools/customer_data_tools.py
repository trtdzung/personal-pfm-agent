"""Tools that return the current customer's own product data as an
explicit, callable tool result -- instead of the agent only ever seeing
this data passively baked into the `/customer_data.json` snapshot already
injected into every system prompt (see `middleware/seed_customer_context.py`).

Both tools call the REAL `pfm` backend and map (almost) 1:1 onto one of its
read endpoints, documented in `backend_docs/pfm-read-api.md`:

- `get_jar_summary(month)`  <->  `GET /api/jar-summary?cif=&month=`
- `get_categories()`        <->  `GET /api/categories?cif=`
- `query_beneficiaries()`   <->  `GET /api/beneficiaries?cif=`

The tools only render what the endpoint returned (field names kept as they
are, so the skills can talk about `spendable`/`allocationHeadroom` and the
model sees the same words) -- all jar numbers come from pfm's own engine, the
agent never adds transactions up itself.

`get_jar_summary` and `get_categories` also return the raw pfm payload as the
tool *artifact* (`response_format="content_and_artifact"`): the model only reads
the text, but `server.py` uses the artifact to check that the jar/category ids in
the `ui` the model emits are ones it really read this turn (`ui_guard.py`). `data/customers/<id>.json`
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
    parts.append(f"categoryIds: {', '.join(jar.get('categoryIds') or []) or 'không có'}")
    parts.append(f"budgetLimit: {_vnd(jar.get('budgetLimit'), 'chưa đặt')}")
    parts.append(f"spent: {_vnd(jar.get('spent'), 'chưa biết')}")
    parts.append(f"remaining: {_vnd(jar.get('remaining'), 'chưa biết')}")
    parts.append(f"spendable: {_vnd(jar.get('spendable'), 'chưa biết')}")
    parts.append(f"overLimit: {_yes_no(jar.get('overLimit'))}")
    return "- " + " | ".join(parts)


def fetch_jar_summary(customer_id: str, month: str = "") -> dict:
    """`GET /api/jar-summary` for an explicit customer. Raises `httpx.HTTPError`/`ValueError` on any failure --
    never returns something that could pass for "this customer has no jars"."""
    params = {"cif": customer_id}
    if month:
        params["month"] = month
    response = httpx.get(
        f"{PFM_BASE_URL}/api/jar-summary",
        params=params,
        timeout=PFM_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    summary = response.json()
    if not isinstance(summary, dict):
        raise ValueError("unexpected response shape")
    return summary


def fetch_account_summary(customer_id: str) -> dict:
    """`GET /api/account-summary` for an explicit customer -- `{"casaBalance": number | null}`, split out
    of `jar-summary` since 2026-09-23 (backend_docs/pfm-read-api.md). Raises `httpx.HTTPError`/`ValueError`
    on any failure."""
    response = httpx.get(
        f"{PFM_BASE_URL}/api/account-summary",
        params={"cif": customer_id},
        timeout=PFM_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("unexpected response shape")
    return data


def fetch_transactions_full(customer_id: str, from_date: str, to_date: str) -> list[dict]:
    """`GET /api/transactions-full` for an explicit customer -- every transaction (bank + self-reported),
    `categoryId` already merged with corrections. `from_date`/`to_date` are `YYYY-MM-DD`, an ISO closed
    range. Raises `httpx.HTTPError`/`ValueError` on any failure."""
    response = httpx.get(
        f"{PFM_BASE_URL}/api/transactions-full",
        params={"cif": customer_id, "from": from_date, "to": to_date},
        timeout=PFM_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError("unexpected response shape")
    return data


def fetch_categories(customer_id: str) -> list[dict]:
    """`GET /api/categories` for an explicit customer. Raises `httpx.HTTPError`/`ValueError` on any
    failure."""
    response = httpx.get(
        f"{PFM_BASE_URL}/api/categories",
        params={"cif": customer_id},
        timeout=PFM_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    categories = response.json()
    if not isinstance(categories, list):
        raise ValueError("unexpected response shape")
    return categories


def _aggregate_monthly_by_category(visible_transactions: list[dict], label_by_id: dict[str, str]) -> dict:
    """Per month (`YYYY-MM`), net spend per category = debit/expense minus credit/refund -- the same
    netting `jar-summary`'s own `spent` uses (backend_docs/pfm-read-api.md: "chi tiêu ròng, đã trừ hoàn
    tiền"). `visible_transactions` must already exclude `hidden: true` rows (jar-summary excludes them
    from totals too). Returned as a precomputed aggregate, not raw transactions, so the model reads an
    already-summed total instead of adding transactions up itself -- same principle as get_jar_summary."""
    counts: dict[str, int] = {}
    totals: dict[str, dict[str, float]] = {}
    for txn in visible_transactions:
        month = (txn.get("postedAt") or "")[:7]
        if not month:
            continue
        counts[month] = counts.get(month, 0) + 1
        direction, kind = txn.get("direction"), txn.get("type")
        if direction == "debit" and kind == "expense":
            delta = txn.get("amount", 0)
        elif direction == "credit" and kind == "refund":
            delta = -txn.get("amount", 0)
        else:
            continue  # income/transfer/etc. -- not spending, excluded from category totals
        label = label_by_id.get(txn.get("categoryId"), txn.get("categoryId") or "Khác")
        by_category = totals.setdefault(month, {})
        by_category[label] = by_category.get(label, 0) + delta
    return {
        month: {
            "total_vnd": sum(totals.get(month, {}).values()),
            "transaction_count": counts[month],
            "by_category_vnd": totals.get(month, {}),
        }
        for month in sorted(counts)
    }


def fetch_live_account_snapshot(customer_id: str, from_date: str, to_date: str) -> dict:
    """Live balance + transactions + a per-month/per-category spending aggregate, for seeding the system
    prompt (`middleware/seed_customer_context.py`) -- NOT a model-facing `@tool` (this data is baked into
    the prompt once per turn, not fetched on demand like `get_jar_summary`/`get_categories`).

    Raises `httpx.HTTPError`/`ValueError` if ANY of the 3 underlying calls fails, so the caller can fall
    back to the mock snapshot as a whole instead of mixing fresh and stale data (todo.md 2026-09-23:
    partial fallback would let live balance sit next to months-old mock transactions with no way for
    the model to tell which parts are current)."""
    account = fetch_account_summary(customer_id)
    raw_transactions = fetch_transactions_full(customer_id, from_date, to_date)
    categories = fetch_categories(customer_id)
    label_by_id = {c["id"]: c.get("label") or c["id"] for c in categories}

    visible = [t for t in raw_transactions if not t.get("hidden")]
    transactions = [
        {
            "id": t.get("id"),
            "date": (t.get("postedAt") or "")[:10],
            "merchant": t.get("merchantName", "?"),
            "category": label_by_id.get(t.get("categoryId"), t.get("categoryId") or "Khác"),
            "amount_vnd": t.get("amount"),
            "direction": t.get("direction"),
            "type": t.get("type"),
            "status": t.get("status"),
        }
        for t in visible
    ]
    return {
        "balance_vnd": account.get("casaBalance"),
        "transactions": transactions,
        "monthly_spending_summary": _aggregate_monthly_by_category(visible, label_by_id),
    }


def render_jar_summary(summary: dict, month: str = "") -> str:
    """The text the model reads for a jar summary (field names kept as the endpoint sends them)."""
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


@tool(response_format="content_and_artifact")
def get_jar_summary(month: str = "") -> tuple[str, dict | None]:
    """Read the current customer's spending jars (hũ chi tiêu) for one month,
    live from the pfm backend (`GET /api/jar-summary`). The numbers come from
    pfm's own engine -- the same ones the customer sees on the Budget screen --
    so never add transactions up yourself.

    Call this before proposing create_jar / edit_jar / rebalance_jars, and call
    it AGAIN after the customer confirmed a change (the numbers moved).

    `month` is optional, `YYYY-MM`; leave it empty for the current month.

    Per jar: `budgetLimit` (monthly limit, "chưa đặt" = not set, NOT 0), `spent`,
    `remaining` (the jar's balance, can be negative), `spendable` (= max(0,
    remaining), the most the jar can give away), `categoryIds` (one category
    belongs to exactly one jar). A jar with `remaining` < 0 "needs covering" (the
    customer spent more than its balance); `overLimit` is a different axis
    (spent > budgetLimit) that does NOT change when a jar is covered. Globals: `casaBalance` (real money in
    the payment account), `unallocated` (the "pool" source for rebalancing),
    `allocationHeadroom` (how much MORE limit can still be set; negative = the
    limits already exceed the account). "chưa biết"/"chưa đặt" means unknown:
    never treat it as 0, never guess it.
    """
    if month and not _MONTH_RE.match(month):
        return f"Tháng phải có dạng YYYY-MM (ví dụ 2026-09), nhận được: {month!r}. Bỏ trống để lấy tháng hiện tại.", None
    try:
        summary = fetch_jar_summary(_resolve_customer_id(), month)
    except (httpx.HTTPError, ValueError) as exc:
        return (
            "Không thể đọc thông tin hũ lúc này (lỗi từ hệ thống pfm: "
            f"{exc}). Đừng đoán số và đừng trả form hũ (create_jar/edit_jar/rebalance_jars) -- "
            "báo cho khách hàng là hệ thống đang gián đoạn."
        ), None
    return render_jar_summary(summary, month), summary


@tool(response_format="content_and_artifact")
def get_categories() -> tuple[str, list | None]:
    """List the current customer's OWN spending categories, live from the pfm
    backend (`GET /api/categories`). It is not a fixed list: every customer has
    the 10 default categories plus any they created themselves (id like
    `c_<slug>`), and may have renamed some.

    Call this before putting a category id in create_jar / edit_jar (`category_ids`)
    or in transfer_form (`category`). Use only ids with `kind: expense` (a
    `kind: transfer` entry is a system category, never for a jar or a transfer
    purpose). Copy the id exactly; never invent one from a label.
    """
    customer_id = _resolve_customer_id()
    try:
        categories = fetch_categories(customer_id)
    except (httpx.HTTPError, ValueError) as exc:
        return (
            "Không thể đọc danh mục của khách lúc này (lỗi từ hệ thống pfm: "
            f"{exc}). Đừng đoán id danh mục -- nếu form cần danh mục thì chỉ dùng "
            "danh mục khách nói rõ, hoặc báo hệ thống đang gián đoạn."
        ), None
    if not categories:
        return "Khách hàng chưa có danh mục nào.", categories
    lines = [
        f"- {c.get('label', '?')} | id: {c.get('id', '?')} | kind: {c.get('kind', '?')}"
        for c in categories
    ]
    return "\n".join(lines), categories


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

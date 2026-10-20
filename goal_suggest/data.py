"""Everything the model gets to see about one customer, read live from pfm (never guessed, never cached across calls)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx

from tools.customer_data_tools import (
    PFM_BASE_URL,
    PFM_REQUEST_TIMEOUT_SECONDS,
    fetch_categories,
    fetch_jar_summary,
    fetch_transactions_full,
    fetch_user_preferences,
)
from tools.goal_tools import fetch_goals_snapshot

logger = logging.getLogger("goal_suggest.data")

# How far back the transactions go: 3 whole months before this one, plus this one.
HISTORY_MONTHS = 3


class DataUnavailable(RuntimeError):
    """The goals read failed: without it there is nothing to say, and guessing would be worse."""


def fetch_accounts(customer_id: str) -> list[dict]:
    """`GET /api/accounts` -- every account of the customer: current, savings, credit card, goal accounts."""
    response = httpx.get(f"{PFM_BASE_URL}/api/accounts", params={"cif": customer_id}, timeout=PFM_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError("unexpected response shape")
    return data


def history_start(today: date, months: int = HISTORY_MONTHS) -> date:
    year, month = today.year, today.month - months
    while month < 1:
        year, month = year - 1, month + 12
    return date(year, month, 1)


def _optional(name: str, call):  # type: ignore[no-untyped-def]
    """A side source failing only removes its section: the digest says "không có dữ liệu" instead of inventing it."""
    try:
        return call()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("goal_suggest data %s unavailable: %s", name, type(exc).__name__)
        return None


def collect(customer_id: str) -> dict:
    """The raw pfm payloads: `snapshot` (goals world + market), `jars`, `accounts`, `transactions`, `categories`,
    `preferences`. Only `snapshot` is required; the others are None when their call fails."""
    try:
        snapshot = fetch_goals_snapshot(customer_id)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise DataUnavailable(type(exc).__name__) from exc
    today = date.fromisoformat(snapshot["world"]["clock"]["today"])
    start = history_start(today).isoformat()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            "jars": pool.submit(_optional, "jars", lambda: fetch_jar_summary(customer_id)),
            "accounts": pool.submit(_optional, "accounts", lambda: fetch_accounts(customer_id)),
            "transactions": pool.submit(
                _optional, "transactions", lambda: fetch_transactions_full(customer_id, start, today.isoformat())
            ),
            "categories": pool.submit(_optional, "categories", lambda: fetch_categories(customer_id)),
            "preferences": pool.submit(_optional, "preferences", lambda: fetch_user_preferences(customer_id)),
        }
        out = {name: future.result() for name, future in futures.items()}
    return {"snapshot": snapshot, **out}

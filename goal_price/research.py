"""TinyFish Search for market prices. Only the search snippets are used: the listing sites (batdongsan, nhatot) block TinyFish Fetch."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

SEARCH_URL = "https://api.search.tinyfish.ai"
TIMEOUT_SECONDS = 25.0
CACHE_TTL_SECONDS = 600
MAX_RESULTS = 8
_cache: dict[str, tuple[float, list["Snippet"]]] = {}


class ResearchUnavailable(Exception):
    """No API key, or the search service failed."""


@dataclass(frozen=True)
class Snippet:
    title: str
    url: str
    text: str


def search(query: str, *, refresh: bool = False) -> list[Snippet]:
    key = os.environ.get("TINYFISH_API_KEY")
    if not key:
        raise ResearchUnavailable("no_api_key")
    cached = _cache.get(query)
    if cached and not refresh and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    try:
        response = httpx.get(
            SEARCH_URL,
            params={"query": query, "location": "VN", "language": "vi"},
            headers={"X-API-Key": key},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise ResearchUnavailable(type(exc).__name__) from exc
    found = [
        Snippet(title=str(r.get("title") or ""), url=str(r.get("url") or ""), text=" ".join(str(r.get("snippet") or "").split()))
        for r in results[:MAX_RESULTS]
        if r.get("url") and r.get("snippet")
    ]
    _cache[query] = (time.monotonic(), found)
    return found

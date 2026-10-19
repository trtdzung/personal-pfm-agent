"""Fixed local playbook. No browsing, learning or external retrieval."""
import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from langchain_core.tools import tool
from . import trace


@lru_cache(maxsize=1)
def _data() -> dict:
    path = Path(__file__).resolve().parent.parent / "data" / "fraud_playbook.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").replace("đ", "d")


def _search(signals: list[str], text: str) -> list[dict]:
    active = set(signals)
    content = _plain(text[:4000])
    matches = []
    for entry in _data()["playbooks"]:
        matched_signals = [code for code in entry["signal_weights"] if code in active]
        matched_keywords = [keyword for keyword in entry["keywords"] if _plain(keyword) in content]
        score = sum(entry["signal_weights"][code] for code in matched_signals) + 5 * len(matched_keywords)
        if score:
            matches.append({**entry, "source": "mock", "score": score, "matched_signals": matched_signals, "matched_keywords": matched_keywords})
    return sorted(matches, key=lambda entry: (-entry["score"], entry["id"]))[:3]


@tool
def search_scam_playbook(signals: list[str], text: str = "") -> list[dict]:
    """Rank fixed mock scam patterns by rule signals/text; never decide a transfer outcome."""
    with trace.tool("search_scam_playbook"):
        return _search(signals, text)


@tool
def get_official_channels() -> dict:
    """Return clearly labelled synthetic channels/campaigns for the demo, never a live authenticity guarantee."""
    with trace.tool("get_official_channels"):
        return _data()["official_channels"].copy()


PLAYBOOK_TOOLS = [search_scam_playbook, get_official_channels]

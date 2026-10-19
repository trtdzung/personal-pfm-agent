"""Bounded read-only tools for pfm's private Fraud gateway."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from langchain_core.tools import tool
from . import trace
from .redact import redact_value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _markers(value: object, restore: bool = False) -> object:
    if isinstance(value, str):
        return value.replace("__FRAUD_MASK__", "[đã ẩn]") if restore else value.replace("[đã ẩn]", "__FRAUD_MASK__")
    if isinstance(value, list):
        return [_markers(item, restore) for item in value]
    if isinstance(value, dict):
        return {key: _markers(item, restore) for key, item in value.items()}
    return value


def _read(name: str, path: str, **params: object) -> dict | list:
    with trace.tool(name) as status:
        key = os.environ.get("FRAUD_PFM_KEY", "")
        base = os.environ.get("FRAUD_PFM_BASE_URL", "http://localhost:3000").rstrip("/")
        try:
            if not key:
                raise ValueError("missing key")
            request = Request(f"{base}/api/security/agent/{path}?{urlencode(params)}", headers={"X-Agent-Key": key})
            with build_opener(_NoRedirect()).open(request, timeout=3) as response:
                raw = response.read(262145)
                if len(raw) > 262144:
                    raise ValueError("response too large")
                value = json.loads(raw)
            if not isinstance(value, (dict, list)):
                raise ValueError("invalid response")
            return _markers(redact_value(_markers(value)), restore=True)
        except Exception:
            status["result"] = "no_data"
            return {"available": False, "reason": "không có dữ liệu"}


@tool
def get_intervention_context(intervention_id: str) -> dict:
    """Read the rule level, scenario, signals and redacted transfer context."""
    return _read("get_intervention_context", "intervention", id=intervention_id)


@tool
def get_recipient_history(cif: str, account: str, bank: str = "") -> dict:
    """Read prior transfer count, last time and trusted status; account is masked in the response."""
    return _read("get_recipient_history", "recipient", cif=cif, account=account, bank=bank)


@tool
def lookup_warned_account(account: str, bank: str = "") -> dict:
    """Read the mock warning list; absence is not a safety guarantee."""
    return _read("lookup_warned_account", "lookup", account=account, bank=bank)


@tool
def get_recent_events(cif: str, hours: float = 24) -> list | dict:
    """Read a bounded window of redacted engine events."""
    return _read("get_recent_events", "events", cif=cif, hours=hours)


@tool
def get_security_profile(cif: str) -> dict:
    """Read protection flags and counts; unavailable auth score remains unknown."""
    return _read("get_security_profile", "profile", cif=cif)


@tool
def get_alert_history(cif: str, days: float = 30) -> list | dict:
    """Read bounded rule warning history and the customer's decisions."""
    return _read("get_alert_history", "alerts", cif=cif, days=days)


@tool
def get_case(case_id: str) -> dict:
    """Read structured case answers without image bytes or full recipient identity."""
    return _read("get_case", "case", id=case_id)


READ_TOOLS = [get_intervention_context, get_recipient_history, lookup_warned_account, get_recent_events,
              get_security_profile, get_alert_history, get_case]

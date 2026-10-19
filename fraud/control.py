"""Kill switch and the chat-signal journal row. Tool names only, never the message."""
import json
import os
from urllib.request import HTTPRedirectHandler, Request, build_opener

_OFF = {"0", "false", "off"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(path: str, payload: dict | None = None):
    key = os.environ.get("FRAUD_PFM_KEY", "")
    if not key:
        return None
    base = os.environ.get("FRAUD_PFM_BASE_URL", "http://localhost:3000").rstrip("/")
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"X-Agent-Key": key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{base}{path}", data=data, headers=headers, method="POST" if data is not None else "GET")
    with build_opener(_NoRedirect()).open(request, timeout=1) as response:
        body = json.loads(response.read(8192))
    return body if isinstance(body, dict) else None


def fraud_enabled() -> bool:
    if os.environ.get("FRAUD_AGENT_ENABLED", "").strip().lower() in _OFF:
        return False
    try:
        body = _open("/api/security/agent/fraud-switch")
    except Exception:
        return True
    if body is None:
        return True
    return body.get("enabled") is not False


def note_chat(cif: str, data_used: str, output: str) -> None:
    cif = cif.strip()
    if not cif or len(cif) > 64:
        return
    try:
        _open("/api/security/agent/journal", {
            "cif": cif,
            "action": "chat-signal",
            "ref": None,
            "data_used": data_used[:500],
            "output": output[:240],
        })
    except Exception:
        return

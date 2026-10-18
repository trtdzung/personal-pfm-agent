from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langgraph.config import get_config
from langgraph.runtime import Runtime

CUSTOMERS_DIR = Path(__file__).resolve().parent.parent / "data" / "customers"
DEFAULT_CUSTOMER_ID = "CIF_0001"
SESSION_FILE_PATH = "/customer_data.json"

# Vietnam has no DST, so a fixed UTC+7 offset is exact -- and unlike
# zoneinfo("Asia/Ho_Chi_Minh") it doesn't depend on tzdata being installed in
# the (python:3.12-slim) container image.
_VIETNAM_TZ = timezone(timedelta(hours=7))
_WEEKDAYS_VI = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


class UnknownCustomerError(ValueError):
    """Raised when actor_id doesn't match any known customer_id."""


def _customer_data_path(customer_id: str) -> Path:
    path = CUSTOMERS_DIR / f"{customer_id}.json"
    if not path.is_file():
        raise UnknownCustomerError(f"Unknown customer_id: {customer_id!r}")
    return path


def _today() -> datetime:
    return datetime.now(_VIETNAM_TZ)


def _current_date_note() -> str:
    now = _today()
    return (
        f"Ngày hiện tại (giờ Việt Nam): {_WEEKDAYS_VI[now.weekday()]}, "
        f"{now.day:02d}/{now.month:02d}/{now.year} ({now.date().isoformat()}). "
        "Dùng đúng ngày này khi tính \"còn bao lâu\", \"đã quá hạn chưa\", số "
        "tháng/ngày còn lại tới cuối năm hay tới hạn thanh toán -- KHÔNG tự "
        "đoán ngày. Chỉ có ngày, không có giờ trong ngày."
    )


def _resolve_customer_id() -> str:
    """Return the actor_id from the current LangGraph run config.

    Falls back to DEFAULT_CUSTOMER_ID when there's no actor_id to read --
    either because there's no runnable context at all (this middleware
    invoked directly outside a graph run, as in unit tests), or because the
    caller's config doesn't set actor_id (agent.py's managed_deepagents
    deployment doesn't wire this the way server.py's actor_id/user_id does).
    """
    try:
        config = get_config()
    except RuntimeError:
        return DEFAULT_CUSTOMER_ID
    actor_id = config.get("configurable", {}).get("actor_id")
    return actor_id or DEFAULT_CUSTOMER_ID


class SeedCustomerContext(AgentMiddleware):
    """Seed the current customer's data into the session's virtual filesystem
    AND directly into every model call's system prompt.

    Reads data/customers/<customer_id>.json fresh from disk on every run so
    the agent always sees the current source of truth. customer_id comes
    from the invoking request's actor_id (server.py passes its required
    user_id field as actor_id) via get_config() -- see _resolve_customer_id()
    for the fallback behavior when no actor_id is available. This is
    session-scoped state (StateBackend) -- it never persists across threads.
    For data that must persist across threads (the customer's stated
    budget), see tools/memory_tools.py (server.py) or memory.py (agent.py)
    instead.

    `before_agent` still seeds the virtual file (kept for `grep`/`read_file`
    if a skill ever needs to search a large document instead of having it
    all in-context). `wrap_model_call`/`awrap_model_call` additionally
    inline that same content into the system message on every model call --
    this is the part that actually matters for latency: without it, the
    model has to spend a full extra LLM round-trip issuing a `read_file`
    call (and often several more for skills that read the file piecemeal --
    see todo.md's performance investigation) just to see data that was
    already loaded and sitting in state the whole time. Inlining it means
    the model has the data from its very first turn, at the cost of a fixed
    ~4-6k token increase on every call (the file is small enough that this
    is worth it -- see todo.md for the measured before/after).

    The same system-prompt injection also carries today's date (Vietnam
    time, date only so the prompt stays cache-stable within a day): the model
    has no clock, and without this it guessed "29/08" on 2026-09-19, which
    skewed every "months left this year" / "is this statement overdue"
    calculation (see todo.md 1.16).

    Note: `jars`/`beneficiaries` are intentionally NOT part of
    data/customers/<id>.json anymore -- they're hardcoded mock data inside
    tools/customer_data_tools.py, only reachable via that module's
    list_existing_jars()/query_beneficiaries(), so this middleware has
    nothing to filter out here.
    """

    def before_agent(self, state: AgentState, runtime: Runtime) -> dict:
        customer_id = _resolve_customer_id()
        content = _customer_data_path(customer_id).read_text(encoding="utf-8")
        return {"files": {SESSION_FILE_PATH: create_file_data(content)}}

    async def abefore_agent(self, state: AgentState, runtime: Runtime) -> dict:
        return self.before_agent(state, runtime)

    def _inject_customer_data(self, request: ModelRequest) -> ModelRequest:
        parts = [request.system_prompt or "", _current_date_note()]
        file_data = request.state.get("files", {}).get(SESSION_FILE_PATH)
        if file_data:
            parts.append(
                f"Dữ liệu khách hàng hiện tại "
                f"(`{SESSION_FILE_PATH}`, đã đọc sẵn -- KHÔNG cần gọi "
                f"`read_file`/`grep` để lấy lại):\n\n```json\n{file_data['content']}\n```"
            )
        combined = "\n\n---\n\n".join(part for part in parts if part)
        return request.override(system_message=SystemMessage(content=combined))

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        return handler(self._inject_customer_data(request))

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Any]
    ) -> ModelResponse:
        return await handler(self._inject_customer_data(request))

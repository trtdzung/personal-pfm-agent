from pathlib import Path

from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

CUSTOMER_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "customer_data.json"
SESSION_FILE_PATH = "/customer_data.json"


class SeedCustomerContext(AgentMiddleware):
    """Seed the current customer's data into the session's virtual filesystem.

    Reads data/customer_data.json fresh from disk on every run so the agent
    always sees the current source of truth. This is session-scoped state
    (StateBackend) — it never persists across threads. For data that must
    persist across threads (the customer's stated budget), see memory.py and
    /memories/agent/customer_budgets.json instead.
    """

    async def abefore_agent(self, state: AgentState, runtime: Runtime) -> dict:
        content = CUSTOMER_DATA_PATH.read_text(encoding="utf-8")
        return {"files": {SESSION_FILE_PATH: create_file_data(content)}}

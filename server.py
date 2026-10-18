import hmac
import logging
import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from fastapi import FastAPI, Header, HTTPException
from greennode_agent_bridge import AgentBaseMemoryEvents
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from llm import LLM_BASE_URL, LLM_MODEL, default_model  # noqa: F401 -- re-exported: tests/notebooks read them off `server`
from langchain_core.exceptions import ModelPermissionDeniedError

from checkpointer_cache import invalidate as invalidate_checkpointer_cache
from checkpointer_cache import patch_get_events_with_cache
from checkpointer_delta_snapshot import patch_preserve_delta_snapshots
from jar_endpoint import router as jar_router
from insight_endpoint import router as insight_router
from proactive_endpoint import router as proactive_router
from middleware.audit import log_model_calls, log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext
from middleware.tool_limits import tool_call_limits
from text_utils import extract_final_text, extract_ui_block, strip_foreign_script
from ui_guard import read_turn_facts, ui_matches_facts
from tools.customer_data_tools import get_categories, get_jar_summary, query_beneficiaries
from tools.investment_tools import calculate_deposit_interest, project_investment_growth
from tools.market_news_tools import read_market_article, search_market_news
from tools.msb_knowledge_tools import search_msb_knowledge
# from tools.memory_tools import recall_preference, remember_preference

logger = logging.getLogger("personal-card-agent")

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = REPO_ROOT / "skills"

SERVER_API_KEY = os.environ.get("SERVER_API_KEY")
if not SERVER_API_KEY:
    raise RuntimeError(
        "SERVER_API_KEY is not set. Refusing to start without an API key "
        "configured -- this server would otherwise serve customer "
        "financial data with no authentication."
    )

MEMORY_ID = os.environ.get("MEMORY_ID")


AI_PLATFORM_API_KEY = os.environ.get("AI_PLATFORM_API_KEY")
if not AI_PLATFORM_API_KEY:
    raise RuntimeError(
        "AI_PLATFORM_API_KEY is not set. Refusing to start without an API key "
        "for GreenNode's VNG Cloud AI Platform (Model-as-a-Service) endpoint."
    )

def _default_model() -> BaseChatModel:
    return default_model(AI_PLATFORM_API_KEY)


def build_agent(
    model: object | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    tools: list[BaseTool] | None = None,
):
    instructions = (REPO_ROOT / "instructions.md").read_text(encoding="utf-8")
    checkpointer = checkpointer or MemorySaver()
    # Works around a real perf bug in AgentBaseMemoryEvents: LangGraph's
    # get_state()/invoke() call checkpointer.get_tuple() once per
    # accumulated checkpoint (the `messages` channel needs the whole chain
    # walked to reduce), and each call re-fetches ALL events over the
    # network from scratch instead of reusing what it just fetched --
    # ~111 network round-trips (~65s) on a well-used thread vs. ~1s with
    # this cache. No-op for InMemorySaver (tests/notebooks). Request
    # handlers below call invalidate_checkpointer_cache() before touching
    # a thread so each request's first read is still guaranteed fresh --
    # see checkpointer_cache.py and todo.md's performance investigation.
    patch_get_events_with_cache(checkpointer)
    # Works around a correctness bug in AgentBaseMemoryEvents that breaks
    # EVERY request on a thread once it is busy enough to have written a
    # DeltaChannel snapshot blob (~50 updates to the `messages` channel):
    # the bridge mangles that blob on read, and state reconstruction dies
    # with "Message as a sequence must be (role string, template)". This is
    # what todo.md 1.5 recorded as "corrupt old history" -- it is not old
    # history. Module-level patch on the bridge, idempotent, no-op for
    # InMemorySaver threads (they never produce such a blob) -- see
    # checkpointer_delta_snapshot.py.
    patch_preserve_delta_snapshots()
    return create_deep_agent(
        model=model or _default_model(),
        tools=tools
        if tools is not None
        else [
            # remember_preference,
            # recall_preference,
            get_jar_summary,
            get_categories,
            query_beneficiaries,
            project_investment_growth,
            calculate_deposit_interest,
            search_market_news,
            read_market_article,
            search_msb_knowledge,
        ],
        middleware=[log_tool_calls, log_model_calls, SeedCustomerContext(), *tool_call_limits()],
        system_prompt=instructions,
        checkpointer=checkpointer,
        # StateBackend stays the default for everything (per-thread, isolates
        # customers' data -- see SeedCustomerContext) so only /skills/ is
        # routed to a real-disk FilesystemBackend, scoped to the skills/ dir
        # with virtual_mode=True (blocks path traversal outside SKILLS_DIR).
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True)},
        ),
        skills=["/skills/project/"],
    )


agent = build_agent()

app = FastAPI(
    title="personal-card-agent (self-hosted)",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Jar proposals for screens that need no chat: its own route and agent, same process (jar_endpoint.py).
app.include_router(jar_router)
app.include_router(insight_router)
app.include_router(proactive_router)


class ChatRequest(BaseModel):
    message: str
    user_id: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    ui: dict | None = None


class HistoryMessage(BaseModel):
    role: str
    content: str
    ui: dict | None = None


class ChatHistoryResponse(BaseModel):
    thread_id: str
    messages: list[HistoryMessage]


def _default_thread_id(user_id: str) -> str:
    """Frontend doesn't manage/pass thread_id yet -- every user_id gets one
    default (and, for now, only) conversation thread when thread_id is
    omitted, so /chat, GET /chat/history, and DELETE /chat/history all agree
    on the same thread for a given user without the caller tracking it."""
    return user_id


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _resume_after_content_filter(thread_id: str, actor_id: str, first_error: Exception) -> dict:
    """One retry when the model host's own content-safety filter rejects the model's OUTPUT (not our
    input) -- seen in production as GreenNode/VNG Cloud MaaS 403 "ModelArts.81011 Output text May contain
    sensitive information". Transient and non-deterministic (also fired during real-model test runs of
    unrelated jar-rebalance answers), not a bug here.

    Verified empirically (not assumed) that this never duplicates the customer's turn: by the time this
    exception can be raised, the customer's message is already checkpointed (LangGraph writes it in the
    entry superstep, before the model node runs) and the model node is the only pending task
    (`state.next == ("model",)`) -- so resuming with `agent.invoke(None, config=...)` re-runs exactly that
    step instead of appending the message again. Gives up after one retry (raises 503, which the frontend
    can retry) rather than making the customer wait through several more ~10-40s model calls.
    """
    logger.warning("agent.invoke rejected by the model provider's content filter for thread_id=%s, retrying: %s", thread_id, first_error)
    config = {"configurable": {"thread_id": thread_id, "actor_id": actor_id}}
    state = agent.get_state(config=config)
    if not state.next:
        # No safe resume point (should not normally happen for this exception) -- resuming with no
        # pending task would be a meaningless no-op call, not a real retry.
        raise HTTPException(status_code=503, detail="Model provider unavailable, try again shortly") from first_error
    try:
        return agent.invoke(None, config=config)
    except ModelPermissionDeniedError as exc:
        logger.warning("agent.invoke rejected by the model provider's content filter again for thread_id=%s, giving up", thread_id)
        raise HTTPException(status_code=503, detail="Model provider unavailable, try again shortly") from exc


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    x_api_key: str | None = Header(default=None),
) -> ChatResponse:
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = request.thread_id or _default_thread_id(request.user_id)
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, request.user_id)
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request.message}]},
            config={"configurable": {"thread_id": thread_id, "actor_id": request.user_id}},
        )
    except ModelPermissionDeniedError as exc:
        result = _resume_after_content_filter(thread_id, request.user_id, exc)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("agent.invoke failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Agent failed to process the request") from exc

    answer = extract_final_text(result["messages"][-1].content)
    answer, ui = extract_ui_block(answer)
    if ui is not None and not ui_matches_facts(ui, read_turn_facts(result["messages"])):
        # e.g. an edit_jar for a jar the model never read this turn (backend_docs/pfm-read-api.md C2.2): the
        # customer gets the answer text only, exactly like a shape-invalid ui.
        logger.warning("Dropping ui block: ids not among what get_jar_summary/get_categories returned this turn: %r", ui)
        ui = None
    answer = strip_foreign_script(answer)  # after the ui block is split off: its strings are left alone
    return ChatResponse(answer=answer, thread_id=thread_id, ui=ui)


@app.get("/chat/history", response_model=ChatHistoryResponse)
def chat_history(
    user_id: str,
    thread_id: str | None = None,
    x_api_key: str | None = Header(default=None),
) -> ChatHistoryResponse:
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = thread_id or _default_thread_id(user_id)
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, user_id)
    try:
        state = agent.get_state(config={"configurable": {"thread_id": thread_id, "actor_id": user_id}})
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("agent.get_state failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to load conversation history") from exc

    history: list[HistoryMessage] = []
    for message in state.values.get("messages", []):
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue  # skip tool/system messages -- not meant for a chat UI transcript

        text = extract_final_text(message.content)
        text, ui = extract_ui_block(text)
        if role == "assistant":
            text = strip_foreign_script(text)  # never rewrite what the user typed
        if not text and ui is None:
            continue  # e.g. an AIMessage whose only content was a tool call -- nothing to show at all

        history.append(HistoryMessage(role=role, content=text, ui=ui))

    return ChatHistoryResponse(thread_id=thread_id, messages=history)


class DeleteHistoryResponse(BaseModel):
    thread_id: str
    status: str


@app.delete("/chat/history", response_model=DeleteHistoryResponse)
def delete_chat_history(
    user_id: str,
    thread_id: str | None = None,
    x_api_key: str | None = Header(default=None),
) -> DeleteHistoryResponse:
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = thread_id or _default_thread_id(user_id)
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, user_id)
    try:
        agent.checkpointer.delete_thread(thread_id, user_id)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("checkpointer.delete_thread failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete conversation history") from exc
    invalidate_checkpointer_cache(agent.checkpointer, thread_id, user_id)

    return DeleteHistoryResponse(thread_id=thread_id, status="deleted")

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
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel

from checkpointer_cache import invalidate as invalidate_checkpointer_cache
from checkpointer_cache import patch_get_events_with_cache
from checkpointer_delta_snapshot import patch_preserve_delta_snapshots
from middleware.audit import log_model_calls, log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext
from text_utils import extract_final_text, extract_ui_block
from tools.memory_tools import recall_preference, remember_preference

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
if not MEMORY_ID:
    raise RuntimeError(
        "MEMORY_ID is not set. Refusing to start without a GreenNode AgentBase "
        "Memory resource configured -- conversation history has nowhere durable "
        "to be stored (create one with `gab memory create`)."
    )

AI_PLATFORM_API_KEY = os.environ.get("AI_PLATFORM_API_KEY")
if not AI_PLATFORM_API_KEY:
    raise RuntimeError(
        "AI_PLATFORM_API_KEY is not set. Refusing to start without an API key "
        "for GreenNode's VNG Cloud AI Platform (Model-as-a-Service) endpoint."
    )

LLM_BASE_URL = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
LLM_MODEL = os.environ.get("LLM_MODEL") or "z-ai/glm-5.2-hackathon"


def _default_model() -> BaseChatModel:
    # `thinking: {"type": "disabled"}` turns off this GLM model's reasoning
    # tokens -- verified directly against the raw API (bypassing langchain)
    # that this is the one param name it actually honors (other common
    # names like `enable_thinking`/`chat_template_kwargs.enable_thinking`
    # are silently ignored). Reasoning tokens were the dominant cost in
    # every LLM call's latency (e.g. 111 of 170 completion tokens on a
    # trivial "Xin chào" -- see todo.md's performance investigation) and
    # are never shown to the customer or used for anything once
    # `text_utils._strip_think_tags` discards them, so disabling them is a
    # straight latency win with no user-visible behavior lost *if* the
    # model's tool-calling/JSON-formatting quality holds up without them
    # (verified against the existing skill test suite -- see todo.md).
    return ChatOpenAI(
        base_url=LLM_BASE_URL,
        api_key=AI_PLATFORM_API_KEY,
        model=LLM_MODEL,
        extra_body={"thinking": {"type": "disabled"}},
    )


def build_agent(
    model: object | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    tools: list[BaseTool] | None = None,
):
    instructions = (REPO_ROOT / "instructions.md").read_text(encoding="utf-8")
    checkpointer = checkpointer or AgentBaseMemoryEvents(memory_id=MEMORY_ID)
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
        tools=tools if tools is not None else [remember_preference, recall_preference],
        middleware=[log_tool_calls, log_model_calls, SeedCustomerContext()],
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
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("agent.invoke failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Agent failed to process the request") from exc

    answer = extract_final_text(result["messages"][-1].content)
    answer, ui = extract_ui_block(answer)
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
        if not text:
            continue  # e.g. an AIMessage whose only content was a tool call

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

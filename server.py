import hmac
import logging
import os
from pathlib import Path

from deepagents import create_deep_agent
from fastapi import FastAPI, Header, HTTPException
from greennode_agent_bridge import AgentBaseMemoryEvents
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel

from middleware.audit import log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext
from text_utils import extract_final_text
from tools.memory_tools import recall_preference, remember_preference

logger = logging.getLogger("personal-card-agent")

REPO_ROOT = Path(__file__).resolve().parent

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


def build_agent(
    model: object = "openai:gpt-5.5",
    checkpointer: BaseCheckpointSaver | None = None,
    tools: list[BaseTool] | None = None,
):
    instructions = (REPO_ROOT / "instructions.md").read_text(encoding="utf-8")
    return create_deep_agent(
        model=model,
        tools=tools if tools is not None else [remember_preference, recall_preference],
        middleware=[log_tool_calls, SeedCustomerContext()],
        system_prompt=instructions,
        checkpointer=checkpointer or AgentBaseMemoryEvents(memory_id=MEMORY_ID),
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


class HistoryMessage(BaseModel):
    role: str
    content: str


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
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request.message}]},
            config={"configurable": {"thread_id": thread_id, "actor_id": request.user_id}},
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("agent.invoke failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Agent failed to process the request") from exc

    answer = extract_final_text(result["messages"][-1].content)
    return ChatResponse(answer=answer, thread_id=thread_id)


@app.get("/chat/history", response_model=ChatHistoryResponse)
def chat_history(
    user_id: str,
    thread_id: str | None = None,
    x_api_key: str | None = Header(default=None),
) -> ChatHistoryResponse:
    if not x_api_key or not hmac.compare_digest(x_api_key, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = thread_id or _default_thread_id(user_id)
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
        if not text:
            continue  # e.g. an AIMessage whose only content was a tool call

        history.append(HistoryMessage(role=role, content=text))

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
    try:
        agent.checkpointer.delete_thread(thread_id, user_id)
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals to the client
        logger.exception("checkpointer.delete_thread failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete conversation history") from exc

    return DeleteHistoryResponse(thread_id=thread_id, status="deleted")

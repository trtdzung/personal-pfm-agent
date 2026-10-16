import hmac
import os
import uuid
from pathlib import Path

from deepagents import create_deep_agent
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from middleware.audit import log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext
from text_utils import extract_final_text

REPO_ROOT = Path(__file__).resolve().parent

SERVER_API_KEY = os.environ.get("SERVER_API_KEY")
if not SERVER_API_KEY:
    raise RuntimeError(
        "SERVER_API_KEY is not set. Refusing to start without an API key "
        "configured -- this server would otherwise serve customer "
        "financial data with no authentication."
    )


def build_agent(model: object = "openai:gpt-5.5"):
    instructions = (REPO_ROOT / "instructions.md").read_text(encoding="utf-8")
    return create_deep_agent(
        model=model,
        tools=[],
        middleware=[log_tool_calls, SeedCustomerContext()],
        system_prompt=instructions,
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
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


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

    thread_id = request.thread_id or str(uuid.uuid4())
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request.message}]},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals
        raise HTTPException(status_code=500, detail="Agent failed to process the request") from exc

    answer = extract_final_text(result["messages"][-1].content)
    return ChatResponse(answer=answer, thread_id=thread_id)

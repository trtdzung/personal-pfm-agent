"""Snapshot-based Home insight. Stateless, no tools or conversation memory."""
import hmac
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, Header, HTTPException
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from llm import default_model

router = APIRouter()


class Candidate(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(min_length=1, max_length=160)
    topic: Literal["payment", "spending", "allocation", "investment"]
    priority: int = Field(ge=0, le=4)
    severity: Literal["urgent", "attention", "info"]
    confidence: Literal["recorded", "estimated"]
    facts: dict[str, str | int | float | None]
    title: str
    body: str


class FinancialSnapshot(BaseModel):
    # Full financial domains supplied by PFM are carried through, including coverage.
    model_config = ConfigDict(extra="allow")
    schemaVersion: Literal["2.0"]
    asOf: str
    timezone: Literal["Asia/Ho_Chi_Minh"]
    currency: Literal["VND"]
    dataQuality: dict[str, Any]
    candidates: list[Candidate] = Field(max_length=100)


class ProactiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot: FinancialSnapshot

    @model_validator(mode="after")
    def bounded(self):
        if len(self.snapshot.model_dump_json()) > 350_000:
            raise ValueError("snapshot too large")
        ids = [c.id for c in self.snapshot.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate")
        return self


class ProactiveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(max_length=160)
    title: str = Field(min_length=1, max_length=70)
    body: str = Field(min_length=1, max_length=240)


class ProactiveResponse(ProactiveDraft):
    snapshot_id: str


def propose(snapshot: FinancialSnapshot) -> ProactiveDraft:
    if not os.environ.get("AI_PLATFORM_API_KEY"):
        raise RuntimeError("Model credentials not configured")
    prompt = (Path(__file__).parent / "prompts" / "proactive_insight.md").read_text(encoding="utf-8")
    model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=15, max_retries=0)
    writer = create_agent(model=model, tools=[], system_prompt=prompt,
                          response_format=ToolStrategy(ProactiveDraft, handle_errors=False))
    result = writer.invoke({"messages": [HumanMessage(snapshot.model_dump_json())]},
                           config={"recursion_limit": 3})
    return ProactiveDraft.model_validate(result["structured_response"])


def validate_selection(request: ProactiveRequest, draft: ProactiveDraft) -> bool:
    candidates = request.snapshot.candidates
    if not candidates:
        return False
    selected = next((c for c in candidates if c.id == draft.candidate_id), None)
    return bool(selected and selected.priority == min(c.priority for c in candidates)
                and draft.title.strip() and draft.body.strip()
                and not any(unicodedata.category(c).startswith("N") for c in draft.title + draft.body)
                and not re.search(r"https?:|```", draft.title + draft.body, re.IGNORECASE))


@router.post("/proactive-insights", response_model=ProactiveResponse)
def proactive_insight(request: ProactiveRequest, x_api_key: str | None = Header(default=None)):
    key = os.environ.get("SERVER_API_KEY", "")
    if not key or not x_api_key or not hmac.compare_digest(key, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not request.snapshot.candidates:
        raise HTTPException(status_code=422, detail="No eligible insight")
    try:
        draft = propose(request.snapshot)
    except Exception as exc:
        # No snapshot/customer details or provider exception text in logs/responses.
        raise HTTPException(status_code=503, detail="Insight model unavailable") from exc
    if not validate_selection(request, draft):
        raise HTTPException(status_code=502, detail="Ungrounded insight selection")
    return ProactiveResponse(snapshot_id=request.snapshot_id, **draft.model_dump())


# Independent local runner shares exactly the same router as server.py, requires no Memory resource.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "proactive-insights"}

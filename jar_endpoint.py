"""POST /jar-rebalance -- jar proposals for screens that need no chat.

One endpoint, two modes (the screen knows which one it is, so nothing routes by LLM):

- `cover`: cover a jar that is short -- take the money from the pool ("Chưa phân bổ") and other jars.
  Answers with a `rebalance_jars` ui (docs/jar-rebalance.md).
- `distribute`: share an amount the customer has into the balances of their jars (the amount is the customer's own:
  it is not taken from the pool or from any jar). Answers with a `distribute_amount` ui.

Who does what. The server reads the jar-summary itself (so there is no tool round-trip and it holds the numbers),
works out everything that is a fact (the shortfall, what the pool can give -- `jar_checks.py`), and answers by code
whenever there is nothing to ask a model (nothing to cover, not enough money anywhere, no jar can receive).
Otherwise ONE specialised model call proposes the split and writes the sentence for the customer. Its proposal is
checked against the same summary: a broken hard rule is never returned; a wrong preferred order gets one retry
that states the right plan. The model never supplies the customer id (it comes from the request).

Separate route and agent from /chat: no thread, no memory, no shared state.
"""

import hmac
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import httpx
from fastapi import APIRouter, Header, HTTPException
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field, model_validator

from jar_checks import (
    Verdict,
    check_cover,
    check_distribute,
    cover_plan,
    cover_shortfall,
    pool_available,
    receivers,
    wording_problems,
)
from llm import default_model
from middleware.seed_customer_context import UnknownCustomerError, _customer_data_path
from text_utils import strip_foreign_script
from tools.customer_data_tools import fetch_jar_summary, render_jar_summary

logger = logging.getLogger("personal-card-agent")

router = APIRouter()

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MAX_ATTEMPTS = 2  # the first proposal, plus one retry that states what was wrong
# One call takes ~10-25s. The SDK default (600s, 2 silent retries) held a request for 558s when the network was down.
MODEL_TIMEOUT_SECONDS = 45

FAILED_ANSWER = "Chưa tạo được đề xuất phù hợp lúc này, bạn thử lại sau nhé."


# --- request / response ----------------------------------------------------------------------------------------


class JarRebalanceRequest(BaseModel):
    user_id: str
    mode: Literal["cover", "distribute"]
    # cover: the jar that is short, and (optionally) the amount the customer is about to spend from it
    target_jar_id: str | None = None
    spend_amount: int | None = Field(default=None, gt=0)
    # distribute: the amount the customer has and wants to share into the jars' balances (their own money: it is not
    # taken from the pool or from any jar)
    amount: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _fields_match_the_mode(self):
        if self.mode == "cover":
            if not self.target_jar_id:
                raise ValueError("target_jar_id is required for mode 'cover'")
            if self.amount is not None:
                raise ValueError("amount is only for mode 'distribute'")
        else:
            if self.target_jar_id is not None or self.spend_amount is not None:
                raise ValueError("target_jar_id and spend_amount are only for mode 'cover'")
            if self.amount is None:
                raise ValueError("amount is required for mode 'distribute'")
        return self


class JarRebalanceResponse(BaseModel):
    answer: str
    ui: dict | None = None


# --- what the model returns ------------------------------------------------------------------------------------


class Move(BaseModel):
    from_jar_id: str = Field(description='Jar id copied from the jar-summary, or "pool".')
    amount: int = Field(description="VND taken from that source; a positive whole number.")


class CoverDraft(BaseModel):
    """The proposal to cover one jar: where the money comes from."""

    answer: str = Field(description="1-3 short sentences for the customer, one per line.")
    moves: list[Move]
    reason: str = Field(description="Why these sources, with the real numbers.")


class Allocation(BaseModel):
    to_jar_id: str = Field(description="Jar id copied from the list of jars that can receive money.")
    amount: int = Field(description="VND given to that jar; a positive whole number.")


class DistributeDraft(BaseModel):
    """The proposal to share the unallocated money into jars."""

    answer: str = Field(description="1-3 short sentences for the customer, one per line.")
    allocations: list[Allocation]
    reason: str = Field(description="Why this split, with the real numbers.")


# --- running the model ------------------------------------------------------------------------------------------


class ModelUnavailable(Exception):
    """Every model call failed (network, timeout, a model that will not fill the schema): no proposal was even made."""


def _model():
    return default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=MODEL_TIMEOUT_SECONDS, max_retries=0)


def _propose(system_prompt: str, schema: type[BaseModel], messages: list) -> BaseModel:
    """One specialised model call whose result is the `schema` object (structured output through a tool call)."""
    agent = create_agent(
        model=_model(),
        tools=[],
        system_prompt=system_prompt,
        response_format=ToolStrategy(schema),
    )
    return agent.invoke({"messages": messages})["structured_response"]


@dataclass
class _Task:
    prompt: str
    schema: type[BaseModel]
    to_ui: Callable[[BaseModel], dict]
    check: Callable[[dict], Verdict]


def _feedback(verdict: Verdict) -> str:
    return "Đề xuất vừa rồi chưa đúng, hãy sửa và trả kết quả mới:\n" + "\n".join(f"- {e}" for e in verdict.hard + verdict.soft)


def _run(task: _Task, first_message: str) -> tuple[BaseModel | None, dict | None]:
    """Propose, check, and retry once. Returns (draft, ui), or (None, None) when nothing safe came out.
    Raises `ModelUnavailable` when no call produced an answer at all.

    A proposal with no hard error is kept as the fallback: if the retry then fails (a dropped connection, a model
    that will not fill the schema) or breaks a hard rule, the earlier acceptable one is returned, not nothing.
    """
    messages: list = [HumanMessage(first_message)]
    best: tuple[BaseModel, dict] | None = None
    answered = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            draft = _propose(task.prompt, task.schema, messages)
        except Exception:  # noqa: BLE001 -- a model that would not fill the schema is a failed attempt, not a 500
            logger.exception("jar-rebalance: model call failed (attempt %d)", attempt)
            continue
        answered = True
        ui = task.to_ui(draft)
        verdict = task.check(ui)
        verdict.soft += wording_problems(draft.answer, draft.reason)  # what the customer reads; never a reason to drop a right proposal
        if not verdict.hard and not verdict.soft:
            return draft, ui
        logger.warning("jar-rebalance: attempt %d not clean: hard=%s soft=%s", attempt, verdict.hard, verdict.soft)
        if not verdict.hard:
            best = (draft, ui)  # only the preferred order / wording is off; pfm accepts any order
        if attempt < MAX_ATTEMPTS:
            messages += [AIMessage(draft.model_dump_json()), HumanMessage(_feedback(verdict))]
    if not answered:
        raise ModelUnavailable
    return best if best is not None else (None, None)


def _paragraphs(text: str) -> str:
    """One sentence per paragraph, a blank line between (the general answer format in instructions.md)."""
    return "\n\n".join(line.strip() for line in text.splitlines() if line.strip())


def _vnd(amount: float) -> str:
    return f"{round(amount):,}".replace(",", ".") + "đ"


# --- the two modes -----------------------------------------------------------------------------------------------


def _cover(request: JarRebalanceRequest, summary: dict) -> tuple[str, dict | None]:
    jars = {j["id"]: j for j in summary.get("jars") or [] if isinstance(j, dict) and "id" in j}
    target = jars.get(request.target_jar_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Jar {request.target_jar_id!r} not found for this customer")
    label = target.get("label", request.target_jar_id)
    shortfall = cover_shortfall(summary, request.target_jar_id, request.spend_amount)
    if shortfall is None:
        return f"Hũ {label} chưa đặt hạn mức nên chưa cân đối được, bạn đặt hạn mức cho hũ trước nhé.", None
    if shortfall == 0:
        return f"Hũ {label} đã đủ tiền cho khoản này, không cần bù thêm.", None
    if cover_plan(summary, request.target_jar_id, shortfall) is None:
        others = sum(j.get("spendable") or 0 for j in jars.values() if j["id"] != request.target_jar_id)
        return (
            f"Hũ {label} còn thiếu {_vnd(shortfall)} nhưng tiền chưa phân bổ và các hũ khác cộng lại chỉ còn "
            f"{_vnd(pool_available(summary) + others)}, chưa đủ để bù."
        ), None

    spend = f"Khoản khách định chi từ hũ này: {_vnd(request.spend_amount)}\n" if request.spend_amount else ""
    message = (
        f"Hũ đích: {label} (id: {request.target_jar_id})\n{spend}"
        f"Số còn thiếu (shortfall) — hệ thống đã tính sẵn, dùng đúng số này: {shortfall} ({_vnd(shortfall)})\n"
        f"Thông tin các hũ (jar-summary):\n{render_jar_summary(summary)}"
    )
    task = _Task(
        prompt=(PROMPTS_DIR / "jar_cover.md").read_text(encoding="utf-8"),
        schema=CoverDraft,
        to_ui=lambda d: {
            "type": "rebalance_jars",
            "target_jar_id": request.target_jar_id,
            "shortfall": shortfall,  # from code: the model is never asked for it
            "moves": [m.model_dump() for m in d.moves],
            "reason": d.reason,
        },
        check=lambda ui: check_cover(summary, request.target_jar_id, shortfall, ui),
    )
    draft, ui = _run(task, message)
    return (draft.answer, ui) if ui is not None else (FAILED_ANSWER, None)


def _customer_data(customer_id: str) -> str | None:
    try:
        return _customer_data_path(customer_id).read_text(encoding="utf-8")
    except UnknownCustomerError:
        return None


def _distribute(request: JarRebalanceRequest, summary: dict) -> tuple[str, dict | None]:
    can_receive = receivers(summary)
    if not can_receive:
        return "Chưa có hũ nào đặt hạn mức để nhận tiền, bạn đặt hạn mức cho hũ trước nhé.", None

    customer_data = _customer_data(request.user_id)
    message = (
        f"Số tiền khách muốn chia vào các hũ: {request.amount} ({_vnd(request.amount)})\n"
        f"Các hũ nhận được (đã đặt hạn mức):\n{render_jar_summary({**summary, 'jars': can_receive})}\n"
        + (f"Dữ liệu chi tiêu của khách (JSON):\n{customer_data}" if customer_data else "")
    )
    task = _Task(
        prompt=(PROMPTS_DIR / "jar_distribute.md").read_text(encoding="utf-8"),
        schema=DistributeDraft,
        to_ui=lambda d: {
            "type": "distribute_amount",
            "allocations": [a.model_dump() for a in d.allocations],
            "reason": d.reason,
        },
        check=lambda ui: check_distribute(summary, request.amount, ui),
    )
    draft, ui = _run(task, message)
    return (draft.answer, ui) if ui is not None else (FAILED_ANSWER, None)


# --- the route ---------------------------------------------------------------------------------------------------


def _require_api_key(x_api_key: str | None) -> None:
    expected = os.environ.get("SERVER_API_KEY")
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@router.post("/jar-rebalance", response_model=JarRebalanceResponse)
def jar_rebalance(request: JarRebalanceRequest, x_api_key: str | None = Header(default=None)) -> JarRebalanceResponse:
    _require_api_key(x_api_key)
    try:
        summary = fetch_jar_summary(request.user_id)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("jar-rebalance: cannot read the jar summary for %s: %s", request.user_id, exc)
        raise HTTPException(status_code=502, detail="Cannot read the jar summary from pfm") from exc
    try:
        answer, ui = _cover(request, summary) if request.mode == "cover" else _distribute(request, summary)
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail="The model is unavailable, try again shortly") from exc
    return JarRebalanceResponse(answer=_paragraphs(strip_foreign_script(answer)), ui=ui)

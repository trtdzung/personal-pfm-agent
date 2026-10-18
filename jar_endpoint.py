"""The two jar endpoints for screens that need no chat, both answering in the same format as the chat skills:

- `POST /jar-distribute`: share an amount of the customer's UNALLOCATED money ("Chưa phân bổ") into one or more jars.
  Answers with a `distribute_amount` ui (skill `distribute-amount`).
- `POST /jar-rebalance`: ONE jar gives an amount to one or more OTHER jars. Answers with a `rebalance_jars` ui (skill
  `rebalance-jars`).

The screen sends the minimum (who, how much, optionally which jars); the agent decides the rest. Who does what: the
server reads the jar-summary and each jar's spending of the last 3 months itself (so there is no tool round-trip and
the model holds the numbers), works out everything that is a fact (what the pool holds, what the giving jar can give
-- `jar_checks.py`), and answers by code whenever there is nothing to ask a model (no money to give, no jar to give
to). Otherwise ONE specialised model call proposes the split and writes the sentence for the customer. Its proposal is
checked against the same summary: a broken hard rule is never returned; an incomplete or badly worded one gets one
retry that states what was wrong. The model never supplies the customer id (it comes from the request).

Separate routes and agent from /chat: no thread, no memory, no shared state.
"""

import hmac
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
from fastapi import APIRouter, Header, HTTPException
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jar_checks import (
    Verdict,
    check_distribute,
    check_rebalance,
    pool_available,
    receivers,
    source_available,
    wording_problems,
)
from llm import default_model
from text_utils import strip_foreign_script
from tools.customer_data_tools import fetch_jar_spending, fetch_jar_summary, render_jar_spending, render_jar_summary

logger = logging.getLogger("personal-card-agent")

router = APIRouter()

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MAX_ATTEMPTS = 2  # the first proposal, plus one retry that states what was wrong
# One call takes ~10-25s. The SDK default (600s, 2 silent retries) held a request for 558s when the network was down.
MODEL_TIMEOUT_SECONDS = 45

FAILED_ANSWER = "Chưa tạo được đề xuất phù hợp lúc này, bạn thử lại sau nhé."
SPENDING_UNAVAILABLE = "Chưa đọc được chi tiêu của các hũ (hệ thống gián đoạn): hãy chia theo số dư hiện tại của từng hũ."


# --- request / response ----------------------------------------------------------------------------------------


def _unique(ids: list[str] | None) -> list[str] | None:
    if ids is not None and len(set(ids)) != len(ids):
        raise ValueError("ids must not repeat")
    return ids


class JarDistributeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # the old fields (`mode`, `target_jar_id`...) are refused, not ignored

    user_id: str
    amount: int = Field(gt=0)  # VND of the unallocated money to hand out
    jar_ids: list[str] | None = Field(default=None, min_length=1)  # optional: only these jars; else the agent picks

    _unique_jars = field_validator("jar_ids")(_unique)


class JarRebalanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    from_jar_id: str = Field(min_length=1)  # the jar that gives the money
    amount: int = Field(gt=0)  # VND it gives
    to_jar_ids: list[str] | None = Field(default=None, min_length=1)  # optional: only these jars; else the agent picks

    _unique_jars = field_validator("to_jar_ids")(_unique)

    @model_validator(mode="after")
    def _the_giver_is_not_a_destination(self):
        if self.to_jar_ids and self.from_jar_id in self.to_jar_ids:
            raise ValueError("from_jar_id cannot also be one of to_jar_ids")
        return self


class JarResponse(BaseModel):
    answer: str
    ui: dict | None = None


# --- what the model returns ------------------------------------------------------------------------------------


class Allocation(BaseModel):
    to_jar_id: str = Field(description="Jar id copied from the list of jars that can receive money.")
    amount: int = Field(description="VND given to that jar; a positive whole number.")


class DistributeDraft(BaseModel):
    """The proposal to share the unallocated money into jars."""

    answer: str = Field(description="1-3 short sentences for the customer, one per line.")
    allocations: list[Allocation]
    reason: str = Field(description="Why this split, with the real numbers.")


class RebalanceDraft(BaseModel):
    """The proposal to move money from one jar to other jars."""

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
    name: str
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
            logger.exception("%s: model call failed (attempt %d)", task.name, attempt)
            continue
        answered = True
        ui = task.to_ui(draft)
        verdict = task.check(ui)
        verdict.soft += wording_problems(draft.answer, draft.reason)  # what the customer reads; never a reason to drop a right proposal
        if not verdict.hard and not verdict.soft:
            return draft, ui
        logger.warning("%s: attempt %d not clean: hard=%s soft=%s", task.name, attempt, verdict.hard, verdict.soft)
        if not verdict.hard:
            best = (draft, ui)  # only wording or a leftover is off; pfm accepts it
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


def _paragraphs(text: str) -> str:
    """One sentence per paragraph, a blank line between (the general answer format in instructions.md)."""
    return "\n\n".join(line.strip() for line in text.splitlines() if line.strip())


def _vnd(amount: float) -> str:
    return f"{round(amount):,}".replace(",", ".") + "đ"


# --- the two flows -----------------------------------------------------------------------------------------------


def _jars_by_id(summary: dict) -> dict[str, dict]:
    return {j["id"]: j for j in summary.get("jars") or [] if isinstance(j, dict) and "id" in j}


def _require_jars(jars: dict[str, dict], ids: list[str] | None) -> None:
    missing = [i for i in ids or [] if i not in jars]
    if missing:
        raise HTTPException(status_code=404, detail=f"Jar(s) {missing!r} not found for this customer")


def _spending_text(customer_id: str, summary: dict, jars: list[dict]) -> str:
    """Each jar's spending of the last 3 months. Only context for the split: if pfm cannot give it, go on without and
    tell the model so, instead of failing a proposal every rule of which is still checked against the summary."""
    try:
        spending = fetch_jar_spending(customer_id, summary)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("jar endpoint: cannot read the jar spending for %s: %s", customer_id, exc)
        return SPENDING_UNAVAILABLE
    return "Chi tiêu 3 tháng gần nhất của từng hũ (chi ròng, đã trừ hoàn tiền):\n" + render_jar_spending({**summary, "jars": jars}, spending)


def _distribute(request: JarDistributeRequest, summary: dict) -> tuple[str, dict | None]:
    jars = _jars_by_id(summary)
    _require_jars(jars, request.jar_ids)
    can_receive = [j for j in receivers(summary) if not request.jar_ids or j["id"] in request.jar_ids]
    if not can_receive:
        return "Bạn chưa có hũ nào để chia tiền, hãy tạo hũ trước nhé.", None
    pool = pool_available(summary)
    if pool <= 0:
        return "Hiện chưa có tiền chưa phân bổ để chia, bạn thử lại khi có thêm tiền trong tài khoản nhé.", None
    if request.amount > pool:
        return f"Tiền chưa phân bổ hiện chỉ còn {_vnd(pool)} nên chưa chia được {_vnd(request.amount)}.", None

    named = (
        f"Khách chỉ định chia vào các hũ: {', '.join(request.jar_ids)} (chỉ dùng các hũ này)."
        if request.jar_ids
        else "Khách chưa nêu hũ nào: hãy tự chọn hũ nhận và cách chia."
    )
    message = (
        f"Số tiền cần chia: {request.amount} ({_vnd(request.amount)}), lấy từ tiền chưa phân bổ (hiện còn {_vnd(pool)}).\n{named}\n"
        f"Các hũ nhận được (mọi hũ, kể cả hũ chưa có số dư):\n{render_jar_summary({**summary, 'jars': can_receive})}\n"
        f"{_spending_text(request.user_id, summary, can_receive)}"
    )

    def check(ui: dict) -> Verdict:
        verdict = check_distribute(summary, request.amount, ui)
        if request.jar_ids and not verdict.hard:
            outside = [a["to_jar_id"] for a in ui["allocations"] if a["to_jar_id"] not in request.jar_ids]
            if outside:
                verdict.hard.append(f"Chỉ được chia vào các hũ khách chỉ định ({', '.join(request.jar_ids)}), không phải {', '.join(outside)}.")
        return verdict

    task = _Task(
        name="jar-distribute",
        prompt=(PROMPTS_DIR / "jar_distribute.md").read_text(encoding="utf-8"),
        schema=DistributeDraft,
        to_ui=lambda d: {"type": "distribute_amount", "allocations": [a.model_dump() for a in d.allocations], "reason": d.reason},
        check=check,
    )
    draft, ui = _run(task, message)
    return (draft.answer, ui) if ui is not None else (FAILED_ANSWER, None)


def _rebalance(request: JarRebalanceRequest, summary: dict) -> tuple[str, dict | None]:
    jars = _jars_by_id(summary)
    _require_jars(jars, [request.from_jar_id, *(request.to_jar_ids or [])])
    source = jars[request.from_jar_id]
    label = source.get("label", request.from_jar_id)
    if source.get("balance") is None:
        return f"Hũ {label} chưa có số dư nên chưa chuyển được tiền đi, bạn nạp tiền vào hũ trước nhé.", None
    available = source_available(summary, request.from_jar_id)
    if available <= 0:
        return f"Hũ {label} đã hết số dư nên chưa chuyển được tiền đi.", None
    if request.amount > available:
        return f"Hũ {label} hiện chỉ còn {_vnd(available)} nên chưa chuyển được {_vnd(request.amount)}.", None
    candidates = [j for j in receivers(summary) if j["id"] != request.from_jar_id and (not request.to_jar_ids or j["id"] in request.to_jar_ids)]
    if not candidates:
        return "Bạn chưa có hũ khác để nhận tiền, hãy tạo thêm hũ trước nhé.", None

    named = (
        f"Khách chỉ định chuyển sang các hũ: {', '.join(request.to_jar_ids)} (chỉ dùng các hũ này)."
        if request.to_jar_ids
        else "Khách không chỉ định hũ nhận: hãy tự chọn 1 hoặc nhiều hũ nhận và cách chia."
    )
    message = (
        f"Hũ cho tiền: {label} (id: {request.from_jar_id}), có thể chuyển tối đa {_vnd(available)}.\n"
        f"Số tiền cần chuyển: {request.amount} ({_vnd(request.amount)}).\n{named}\n"
        f"Thông tin hũ cho tiền:\n{render_jar_summary({**summary, 'jars': [source]})}\n"
        f"Các hũ nhận được (mọi hũ khác, kể cả hũ chưa có số dư):\n{render_jar_summary({**summary, 'jars': candidates})}\n"
        f"{_spending_text(request.user_id, summary, [source, *candidates])}"
    )

    def check(ui: dict) -> Verdict:
        verdict = check_rebalance(summary, request.from_jar_id, request.amount, ui)
        if request.to_jar_ids and not verdict.hard:
            outside = [a["to_jar_id"] for a in ui["allocations"] if a["to_jar_id"] not in request.to_jar_ids]
            if outside:
                verdict.hard.append(f"Chỉ được chuyển sang các hũ khách chỉ định ({', '.join(request.to_jar_ids)}), không phải {', '.join(outside)}.")
        return verdict

    task = _Task(
        name="jar-rebalance",
        prompt=(PROMPTS_DIR / "jar_rebalance.md").read_text(encoding="utf-8"),
        schema=RebalanceDraft,
        to_ui=lambda d: {  # the giver comes from the request: the model is never asked which jar gives
            "type": "rebalance_jars",
            "from_jar_id": request.from_jar_id,
            "allocations": [a.model_dump() for a in d.allocations],
            "reason": d.reason,
        },
        check=check,
    )
    draft, ui = _run(task, message)
    return (draft.answer, ui) if ui is not None else (FAILED_ANSWER, None)


# --- the routes ---------------------------------------------------------------------------------------------------


def _require_api_key(x_api_key: str | None) -> None:
    expected = os.environ.get("SERVER_API_KEY")
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _read_summary(user_id: str) -> dict:
    try:
        return fetch_jar_summary(user_id)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("jar endpoint: cannot read the jar summary for %s: %s", user_id, exc)
        raise HTTPException(status_code=502, detail="Cannot read the jar summary from pfm") from exc


def _respond(flow: Callable[[], tuple[str, dict | None]]) -> JarResponse:
    try:
        answer, ui = flow()
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail="The model is unavailable, try again shortly") from exc
    return JarResponse(answer=_paragraphs(strip_foreign_script(answer)), ui=ui)


@router.post("/jar-distribute", response_model=JarResponse)
def jar_distribute(request: JarDistributeRequest, x_api_key: str | None = Header(default=None)) -> JarResponse:
    _require_api_key(x_api_key)
    summary = _read_summary(request.user_id)
    return _respond(lambda: _distribute(request, summary))


@router.post("/jar-rebalance", response_model=JarResponse)
def jar_rebalance(request: JarRebalanceRequest, x_api_key: str | None = Header(default=None)) -> JarResponse:
    _require_api_key(x_api_key)
    summary = _read_summary(request.user_id)
    return _respond(lambda: _rebalance(request, summary))

"""SC2 interview. One new answer per turn; images never enter the model."""
import asyncio
import json
import os
import re
from pathlib import Path
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from llm import default_model
from .contracts import CaseRequest, CaseResponse
from .guard import GuardViolation, validate_case
from .redact import redact_text
from .tools import get_case, get_recent_events
from . import trace

_LABELS = ("thời gian", "số tiền", "tài khoản và ngân hàng nhận", "kẻ gian liên lạc qua kênh nào", "ảnh chụp tin nhắn")
_LIMITS = (500, 100, 500, 500, 120)
_MONEY = {"transfer_out", "incoming_credit", "fd_settled"}


def _clip(answers: list[object]) -> list[str]:
    clipped: list[str] = []
    for index, value in enumerate(answers[:5]):
        text = value.strip() if isinstance(value, str) else ""
        clipped.append(text[:_LIMITS[index]])
    return clipped


def _accepted(answer: str, stored: list[str]) -> bool:
    if "data:image" in answer.lower():
        raise GuardViolation("image_payload")
    redacted = redact_text(answer).strip()
    digits = re.sub(r"\D", "", answer)
    last4 = digits[-4:] if len(digits) >= 4 else ""
    for item in stored:
        text = item.strip()
        if text and (text in {answer.strip(), redacted, last4} or text in redacted or redacted in text):
            return True
    return False


def _hints(events: object) -> list[dict]:
    if not isinstance(events, list):
        return []
    hints: list[dict] = []
    for event in events:
        if not isinstance(event, dict) or event.get("type") not in _MONEY:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        hints.append({"type": event["type"], "at": event.get("at"), "amount": payload.get("amount"),
                      "last4": payload.get("recipientLast4") or payload.get("senderLast4"),
                      "bank": payload.get("recipientBank") or payload.get("senderBank")})
        if len(hints) == 5:
            break
    return hints


async def propose(request: CaseRequest) -> CaseResponse:
    with trace.start() as entries:
        case = await get_case.ainvoke({"case_id": request.case_id})
        if not isinstance(case, dict) or case.get("available") is False or not isinstance(case.get("answers"), list):
            raise GuardViolation("unknown_case")
        raw = case["answers"]
        if len(raw) != 5:
            raise GuardViolation("unknown_case")
        answers = _clip(raw)
        if request.answer is not None and not _accepted(request.answer, answers):
            raise GuardViolation("unknown_answer")
        cif = case.get("cif")
        events = await get_recent_events.ainvoke({"cif": cif, "hours": 24}) if isinstance(cif, str) and cif else {"available": False}
        missing = next((i for i, value in enumerate(answers) if not value), None)
        facts = {"fields": list(_LABELS), "answers": answers, "missing": None if missing is None else _LABELS[missing],
                 "has_image": bool(case.get("has_image")), "events": _hints(events),
                 "dossier_title": "hồ sơ đề nghị phối hợp liên ngân hàng theo QĐ 71"}
        prompt = (Path(__file__).resolve().parent.parent / "prompts/fraud_case.md").read_text(encoding="utf-8")
        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=6, max_retries=0)
        model.max_tokens = 700
        writer = create_agent(model=model, tools=[], system_prompt=prompt,
                              response_format=ToolStrategy(CaseResponse, handle_errors=False))
        result = await asyncio.wait_for(
            writer.ainvoke({"messages": [HumanMessage(json.dumps(facts, ensure_ascii=False))]}, config={"recursion_limit": 3}),
            timeout=6)
        output = CaseResponse.model_validate(result["structured_response"])
        validate_case(output, answers, facts)
        return output.model_copy(update={"trace": entries.copy()})

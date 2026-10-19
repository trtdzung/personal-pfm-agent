"""Two-question diagnosis. Output can suggest actions but cannot execute them."""
import asyncio
import json
import os
from pathlib import Path
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from llm import default_model
from .contracts import DiagnoseRequest, DiagnoseResponse
from .guard import GuardViolation, validate_diagnosis, validate_text
from .tools import get_intervention_context
from .playbook import search_scam_playbook
from . import trace


async def propose(request: DiagnoseRequest) -> DiagnoseResponse:
    with trace.start() as entries:
        context = await get_intervention_context.ainvoke({"intervention_id": request.intervention_id})
        state = context.get("diagnosis") or {}
        answers = state.get("answers") or []
        if not 1 <= len(answers) <= 2 or answers[-1] != request.answer:
            raise GuardViolation("unknown_answer")
        matches = await search_scam_playbook.ainvoke({"signals": [s["code"] for s in context.get("signals", [])], "text": context.get("memo") or ""})
        matches = [{k: m[k] for k in ("id", "name", "questions", "handling") if k in m} for m in matches[:1]]
        facts = {"context": context, "playbooks": matches}
        prompt = (Path(__file__).resolve().parent.parent / "prompts/fraud_diagnose.md").read_text(encoding="utf-8")
        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=6, max_retries=0)
        model.max_tokens = 500
        writer = create_agent(model=model, tools=[], system_prompt=prompt,
                              response_format=ToolStrategy(DiagnoseResponse, handle_errors=False))
        result = await asyncio.wait_for(writer.ainvoke({"messages": [HumanMessage(json.dumps(facts, ensure_ascii=False))]}, config={"recursion_limit": 3}), timeout=6)
        raw = result["structured_response"]
        pending = raw.get("proposals", []) if isinstance(raw, dict) else []
        if not isinstance(pending, list) or any(item not in {"callback", "emergency_lock", "case", "none"} for item in pending):
            raise GuardViolation("invalid_proposal")
        output = DiagnoseResponse.model_validate(raw)
        validate_diagnosis(output.proposals, (output.next_question or "") + " " + (output.conclusion or ""))
        questions = {q for m in matches for q in m.get("questions", [])[1:2]}
        # Both UC12 questions are fixed even when no playbook matches.
        questions.add("Người đó có dặn đừng nói với người thân không?")
        if output.next_question is not None and (len(answers) >= 2 or output.next_question not in questions):
            raise GuardViolation("extra_question")
        validate_text((output.next_question or "") + " " + (output.conclusion or ""), facts, max_length=1200)
        return output.model_copy(update={"trace": entries.copy()})

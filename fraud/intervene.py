"""Request-scoped read tools and guarded, bounded intervention writing."""
import asyncio
import json
import os
from pathlib import Path
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from llm import default_model
from .contracts import InterveneRequest, InterveneResponse
from .guard import GuardViolation, validate_intervention
from .tools import get_intervention_context, get_recipient_history
from .playbook import search_scam_playbook
from . import trace


async def propose(request: InterveneRequest) -> InterveneResponse:
    with trace.start() as entries:
        context = await get_intervention_context.ainvoke({"intervention_id": request.intervention_id})
        if context.get("cif") != request.cif or not context.get("rule_copy"):
            raise GuardViolation("unavailable_context")
        matches = await search_scam_playbook.ainvoke({"signals": [s["code"] for s in context["signals"]], "text": context.get("memo") or ""})
        history = await get_recipient_history.ainvoke({"cif": request.cif, "account": context.get("recipient_last4") or "", "bank": context.get("bank") or ""}) if context.get("recipient_last4") else None
        matches = [{k: m[k] for k in ("id", "name", "questions", "handling", "scenarios") if k in m} for m in matches[:1]]
        facts = {"context": context, "playbooks": matches, "recipient": history}

        @tool
        def read_situation() -> dict:
            """Read this intervention's masked rule facts and recipient history."""
            with trace.tool("read_situation"):
                return {"context": context, "recipient": history}

        @tool
        def read_matched_playbooks() -> list:
            """Read the locally matched mock scam patterns, questions and handling."""
            with trace.tool("read_matched_playbooks"):
                return matches

        prompt = (Path(__file__).resolve().parent.parent / "prompts/fraud_intervene.md").read_text(encoding="utf-8")
        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=6, max_retries=0)
        model.max_tokens = 600
        writer = create_agent(model=model, tools=[read_situation, read_matched_playbooks], system_prompt=prompt,
                              response_format=ToolStrategy(InterveneResponse, handle_errors=False))
        result = await asyncio.wait_for(writer.ainvoke({"messages": [HumanMessage(json.dumps(facts, ensure_ascii=False))]}, config={"recursion_limit": 5}), timeout=6)
        output = InterveneResponse.model_validate(result["structured_response"])
        rule = context["rule_copy"]
        validate_intervention(output, context["level"], rule["chips"], facts)
        questions = {rule.get("question"), *(q for m in matches for q in m.get("questions", []))}
        if output.question not in questions:
            raise GuardViolation("unknown_question")
        if output.scenario != context["scenario"]:
            raise GuardViolation("changed_scenario")
        if output.matched_playbook is not None and output.matched_playbook not in {m["id"] for m in matches}:
            raise GuardViolation("unknown_playbook")
        if context["scenario"] == "DH8" and not output.message.startswith(rule["message"].split("\n")[0]):
            raise GuardViolation("changed_first_line")
        return output.model_copy(update={"trace": entries.copy()})

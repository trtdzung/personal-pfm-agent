"""BT7 scan. Cross-check mock channels and warned accounts; never lower the rule."""
import asyncio
import json
import os
import re
from pathlib import Path
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from llm import default_model
from .contracts import ScanRequest, ScanResponse
from .guard import GuardViolation, validate_scan
from .playbook import get_official_channels
from .redact import redact_text
from .tools import lookup_warned_account
from . import trace

_ACCOUNT = re.compile(r"\d{6,34}")
_RANKS = {"none": 0, "suspicious": 1, "danger": 2}


async def propose(request: ScanRequest) -> ScanResponse:
    with trace.start() as entries:
        numbers: list[str] = []
        for match in _ACCOUNT.finditer(request.text):
            if match.group() not in numbers:
                numbers.append(match.group())
            if len(numbers) == 5:
                break
        channels = await get_official_channels.ainvoke({})
        lookups = [await lookup_warned_account.ainvoke({"account": number}) for number in numbers]
        safe = redact_text(request.text)
        facts = {"text": safe, "rule": request.rule.model_dump(), "channels": channels, "lookups": lookups}
        prompt = (Path(__file__).resolve().parent.parent / "prompts/fraud_scan.md").read_text(encoding="utf-8")
        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=6, max_retries=0)
        model.max_tokens = 500
        writer = create_agent(model=model, tools=[], system_prompt=prompt,
                              response_format=ToolStrategy(ScanResponse, handle_errors=False))
        result = await asyncio.wait_for(
            writer.ainvoke({"messages": [HumanMessage(json.dumps(facts, ensure_ascii=False))]}, config={"recursion_limit": 3}),
            timeout=6)
        raw = result["structured_response"]
        level = raw.get("level") if isinstance(raw, dict) else None
        if level not in _RANKS or _RANKS[level] < _RANKS[request.rule.level]:
            raise GuardViolation("lowered_level")
        output = ScanResponse.model_validate(raw)
        validate_scan(output.level, request.rule.level, " ".join([*output.reasons, *output.manipulation_signs]), facts)
        return output.model_copy(update={"trace": entries.copy()})

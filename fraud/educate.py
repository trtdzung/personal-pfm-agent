"""Contextual handbook. The library picks the article; the model only rewrites three lines."""
import asyncio
import json
import os
from pathlib import Path
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from llm import default_model
from .contracts import EducateRequest, EducateResponse
from .guard import validate_educate
from .playbook import select_article
from .tools import get_security_profile
from . import trace


async def propose(request: EducateRequest) -> EducateResponse:
    with trace.start() as entries:
        article = select_article(request.trigger)
        profile = await get_security_profile.ainvoke({"cif": request.cif})
        facts = {"trigger": request.trigger, "article": article, "profile": profile}
        prompt = (Path(__file__).resolve().parent.parent / "prompts/fraud_educate.md").read_text(encoding="utf-8")
        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=6, max_retries=0)
        model.max_tokens = 400
        writer = create_agent(model=model, tools=[], system_prompt=prompt,
                              response_format=ToolStrategy(EducateResponse, handle_errors=False))
        result = await asyncio.wait_for(
            writer.ainvoke({"messages": [HumanMessage(json.dumps(facts, ensure_ascii=False))]}, config={"recursion_limit": 3}),
            timeout=6)
        output = EducateResponse.model_validate(result["structured_response"])
        validate_educate(output, article["id"], article["chips"], facts)
        return output.model_copy(update={"trace": entries.copy()})

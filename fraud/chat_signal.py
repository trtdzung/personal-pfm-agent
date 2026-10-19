"""One chat line. Flag a scam in progress; never store the message."""
import asyncio
import json
import os
from pathlib import Path
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from llm import default_model
from .contracts import ChatSignalRequest, ChatSignalResponse
from .guard import validate_chat_signal
from .playbook import search_scam_playbook
from .redact import redact_text
from . import trace


async def propose(request: ChatSignalRequest) -> ChatSignalResponse:
    with trace.start() as entries:
        safe = redact_text(request.message)
        matches = await search_scam_playbook.ainvoke({"signals": [], "text": safe})
        playbooks = [{key: item[key] for key in ("id", "name") if key in item} for item in matches]
        facts = {"message": safe, "playbooks": playbooks}
        prompt = (Path(__file__).resolve().parent.parent / "prompts/fraud_chat_signal.md").read_text(encoding="utf-8")
        model = default_model(os.environ.get("AI_PLATFORM_API_KEY"), timeout=6, max_retries=0)
        model.max_tokens = 200
        writer = create_agent(model=model, tools=[], system_prompt=prompt,
                              response_format=ToolStrategy(ChatSignalResponse, handle_errors=False))
        result = await asyncio.wait_for(
            writer.ainvoke({"messages": [HumanMessage(json.dumps(facts, ensure_ascii=False))]}, config={"recursion_limit": 3}),
            timeout=6)
        output = ChatSignalResponse.model_validate(result["structured_response"])
        validate_chat_signal(output, {item["id"] for item in playbooks})
        return output.model_copy(update={"trace": entries.copy()})

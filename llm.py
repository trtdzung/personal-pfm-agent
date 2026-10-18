"""The chat model, shared by /chat (server.py) and POST /jar-rebalance (jar_endpoint.py)."""

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

LLM_BASE_URL = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
LLM_MODEL = os.environ.get("LLM_MODEL") or "z-ai/glm-5.2-hackathon"


def default_model(
    api_key: str | None, *, timeout: float | None = None, max_retries: int | None = None
) -> BaseChatModel:
    """`timeout`/`max_retries` are unset for /chat (the SDK's own defaults). A caller that must answer fast sets
    them: the defaults are a 600s timeout and 2 silent retries, and a dead connection once held a request 558s."""
    if not api_key:
        raise RuntimeError(
            "AI_PLATFORM_API_KEY is not set. Refusing to start without an API key "
            "for GreenNode's VNG Cloud AI Platform (Model-as-a-Service) endpoint."
        )
    # `thinking: {"type": "disabled"}` turns off this GLM model's reasoning
    # tokens -- verified directly against the raw API (bypassing langchain)
    # that this is the one param name it actually honors (other common
    # names like `enable_thinking`/`chat_template_kwargs.enable_thinking`
    # are silently ignored). Reasoning tokens were the dominant cost in
    # every LLM call's latency (e.g. 111 of 170 completion tokens on a
    # trivial "Xin chào" -- see todo.md's performance investigation) and
    # are never shown to the customer or used for anything once
    # `text_utils._strip_think_tags` discards them, so disabling them is a
    # straight latency win with no user-visible behavior lost *if* the
    # model's tool-calling/JSON-formatting quality holds up without them
    # (verified against the existing skill test suite -- see todo.md).
    return ChatOpenAI(
        base_url=LLM_BASE_URL,
        api_key=api_key,
        model=LLM_MODEL,
        extra_body={"thinking": {"type": "disabled"}},
        timeout=timeout,
        max_retries=max_retries,
    )

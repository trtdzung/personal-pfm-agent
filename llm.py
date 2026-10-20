"""The chat model, shared by /chat (server.py) and POST /jar-rebalance (jar_endpoint.py)."""

import logging
import os
import time
from typing import Any

import openai
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field

LLM_BASE_URL = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
LLM_MODEL = os.environ.get("LLM_MODEL") or "z-ai/glm-5.2-hackathon"

logger = logging.getLogger("personal-card-agent")

# The /chat agent can run on OpenAI instead of GLM: CHAT_LLM_PROVIDER=openai AND an OPENAI_API_KEY. Anything else (flag unset, another
# value, key missing or blank) falls back to GLM, so a deployment without the key behaves exactly as before. Side features (jar
# rebalance, fraud, coach, insights...) always use `default_model`/GLM.
OPENAI_CHAT_MODEL = "gpt-5.5"
# Chat Completions refuses function tools together with a reasoning effort other than "none" on the gpt-5.x models.
OPENAI_REASONING_EFFORT = "none"


def _openai_key() -> str | None:
    if (os.environ.get("CHAT_LLM_PROVIDER") or "").strip().lower() != "openai":
        return None
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.warning("CHAT_LLM_PROVIDER=openai but OPENAI_API_KEY is empty: the chat agent falls back to %s", LLM_MODEL)
        return None
    return key


def chat_model_name() -> str:
    """The model the /chat agent runs on right now (shown by /health)."""
    return (os.environ.get("CHAT_LLM_OPENAI_MODEL") or OPENAI_CHAT_MODEL) if _openai_key() else LLM_MODEL


# After OpenAI fails a call, the next calls go straight to GLM for this long instead of each waiting for OpenAI to fail again.
OPENAI_COOLDOWN_SECONDS = 60.0


class FallbackChatModel(BaseChatModel):
    """Runs every call on `primary` and, when the provider fails (`openai.OpenAIError`: connection, timeout, rate limit, 5xx, auth,
    refusal of the request), answers that same call with `fallback`. Works inside a turn, between two steps of the agent, so no
    LangGraph state has to be resumed. After a failure `primary` is skipped for `cooldown_seconds`. Errors that are not the
    provider's (bugs, bad input) are NOT swallowed, and if `fallback` fails too its error is raised."""

    primary: BaseChatModel
    fallback: BaseChatModel
    cooldown_seconds: float = OPENAI_COOLDOWN_SECONDS
    tools: list | None = None
    bind_kwargs: dict = Field(default_factory=dict)
    # shared by the copies `bind_tools` makes, so one failure puts every copy on cooldown
    breaker: dict = Field(default_factory=lambda: {"skip_until": 0.0})

    @property
    def _llm_type(self) -> str:
        return "openai-with-glm-fallback"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self.model_copy(update={"tools": list(tools), "bind_kwargs": kwargs})

    def _call(self, model: BaseChatModel, messages, stop, kwargs):  # noqa: ANN001
        bound = model.bind_tools(self.tools, **self.bind_kwargs) if self.tools else model
        return bound.invoke(messages, stop=stop, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:  # noqa: ANN001
        message = None
        if time.monotonic() >= self.breaker["skip_until"]:
            try:
                message = self._call(self.primary, messages, stop, kwargs)
            except openai.OpenAIError as exc:
                self.breaker["skip_until"] = time.monotonic() + self.cooldown_seconds
                logger.warning(
                    "chat model %s failed (%s): answering with %s, skipping it for %.0fs",
                    getattr(self.primary, "model_name", "primary"), type(exc).__name__, getattr(self.fallback, "model_name", "fallback"),
                    self.cooldown_seconds,
                )
        if message is None:
            message = self._call(self.fallback, messages, stop, kwargs)
        return ChatResult(generations=[ChatGeneration(message=message)])


def chat_model(api_key: str | None) -> BaseChatModel:
    """The /chat agent's model: OpenAI when `_openai_key()` says so (with GLM as the per-call fallback when there is a GLM key), else
    GLM via `default_model(api_key)`."""
    key = _openai_key()
    if key is None:
        return default_model(api_key)
    # a short timeout and one retry: a slow OpenAI must hand over to GLM within seconds, not after the SDK's 600s default
    primary = ChatOpenAI(
        model=chat_model_name(),
        api_key=key,
        reasoning_effort=os.environ.get("CHAT_LLM_OPENAI_REASONING") or OPENAI_REASONING_EFFORT,
        timeout=45,
        max_retries=1,
    )
    if not api_key:
        return primary  # no GLM key to fall back to
    return FallbackChatModel(primary=primary, fallback=default_model(api_key), profile=primary.profile)


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

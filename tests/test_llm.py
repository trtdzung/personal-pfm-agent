"""The model factory shared by /chat (server.py) and POST /jar-rebalance (jar_endpoint.py)."""

import llm


def test_default_model_points_at_the_greennode_endpoint_with_thinking_disabled():
    model = llm.default_model("test-key")
    assert str(model.openai_api_base) == llm.LLM_BASE_URL
    assert model.model_name == llm.LLM_MODEL
    # verified against the raw API: the one param this GLM model honours to skip reasoning tokens (latency)
    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_default_model_needs_an_api_key():
    import pytest

    with pytest.raises(RuntimeError, match="AI_PLATFORM_API_KEY"):
        llm.default_model(None)


def test_default_model_can_be_given_a_short_timeout_and_no_hidden_retries():
    # the SDK default is a 600s timeout and 2 silent retries: a dead connection once held a request for 558s
    model = llm.default_model("test-key", timeout=30, max_retries=0)
    assert model.request_timeout == 30 and model.max_retries == 0


def test_the_chat_agents_model_keeps_the_sdk_defaults():
    model = llm.default_model("test-key")
    assert model.request_timeout is None and model.max_retries is None  # unset: the SDK's own defaults apply


def test_the_chat_model_is_glm_unless_openai_is_asked_for_and_has_a_key(monkeypatch):
    for provider, key in ((None, None), (None, "sk-x"), ("openai", None), ("openai", "   "), ("glm", "sk-x")):
        for name, value in (("CHAT_LLM_PROVIDER", provider), ("OPENAI_API_KEY", key)):
            monkeypatch.delenv(name, raising=False) if value is None else monkeypatch.setenv(name, value)
        model = llm.chat_model("glm-key")
        assert model.model_name == llm.LLM_MODEL and llm.chat_model_name() == llm.LLM_MODEL, (provider, key)
        assert str(model.openai_api_base) == llm.LLM_BASE_URL


def test_the_chat_model_is_openai_with_glm_as_fallback_when_flag_key_and_glm_key_are_there(monkeypatch):
    monkeypatch.setenv("CHAT_LLM_PROVIDER", " OpenAI ")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = llm.chat_model("glm-key")
    assert isinstance(model, llm.FallbackChatModel)
    assert model.primary.model_name == "gpt-5.5" == llm.chat_model_name()
    assert model.primary.reasoning_effort == "none" and model.primary.openai_api_key.get_secret_value() == "sk-test"
    assert model.primary.request_timeout == 45  # a slow OpenAI hands over to GLM in seconds
    assert model.fallback.model_name == llm.LLM_MODEL and str(model.fallback.openai_api_base) == llm.LLM_BASE_URL
    monkeypatch.setenv("CHAT_LLM_OPENAI_MODEL", "gpt-5.4-mini")
    assert llm.chat_model("glm-key").primary.model_name == "gpt-5.4-mini"


def test_without_a_glm_key_there_is_nothing_to_fall_back_to_so_the_model_is_plain_openai(monkeypatch):
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = llm.chat_model(None)
    assert not isinstance(model, llm.FallbackChatModel) and model.model_name == "gpt-5.5"


def test_side_features_stay_on_glm_even_when_the_chat_agent_uses_openai(monkeypatch):
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm.default_model("glm-key").model_name == llm.LLM_MODEL


# ---- FallbackChatModel ----

import httpx
import openai
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage


def _api_down():
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


class _Scripted(GenericFakeChatModel):
    """Replies with `AIMessage`s in order; an `Exception` in the script is raised instead. Records the tools it was bound with."""

    bound: list | None = None

    def bind_tools(self, tools, **kwargs):
        clone = self.model_copy()
        clone.bound = list(tools)
        return clone

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        item = next(self.messages)
        if isinstance(item, Exception):
            raise item
        from langchain_core.outputs import ChatGeneration, ChatResult

        return ChatResult(generations=[ChatGeneration(message=item)])


def _pair(primary_script, fallback_script, **kw):
    primary, fallback = _Scripted(messages=iter(primary_script)), _Scripted(messages=iter(fallback_script))
    return llm.FallbackChatModel(primary=primary, fallback=fallback, **kw), primary, fallback


def _ask(model):
    return model.invoke([HumanMessage(content="hi")])


def test_the_primary_answers_when_it_works_and_the_fallback_is_not_touched():
    model, _, fallback = _pair([AIMessage(content="từ OpenAI")], [AIMessage(content="từ GLM")])
    assert _ask(model).content == "từ OpenAI"
    assert next(fallback.messages).content == "từ GLM"  # untouched: still the first item


def test_a_provider_error_is_answered_by_the_fallback_on_that_same_call(caplog):
    model, _, _ = _pair([_api_down()], [AIMessage(content="từ GLM")])
    with caplog.at_level("WARNING", logger="personal-card-agent"):
        assert _ask(model).content == "từ GLM"
    assert "APIConnectionError" in caplog.text and "sk-" not in caplog.text


def test_after_a_failure_the_primary_is_skipped_until_the_cooldown_is_over(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(llm.time, "monotonic", lambda: now[0])
    model, primary, _ = _pair([_api_down(), AIMessage(content="OpenAI lại")], [AIMessage(content="GLM 1"), AIMessage(content="GLM 2")], cooldown_seconds=60)
    assert _ask(model).content == "GLM 1"
    now[0] += 30
    assert _ask(model).content == "GLM 2"  # still cooling down: the primary is not even asked
    now[0] += 31
    assert _ask(model).content == "OpenAI lại"  # cooldown over: the primary is tried again
    assert next(primary.messages, None) is None


def test_the_cooldown_is_shared_by_the_copies_bind_tools_makes(monkeypatch):
    monkeypatch.setattr(llm.time, "monotonic", lambda: 5.0)
    model, _, _ = _pair([_api_down()], [AIMessage(content="GLM 1"), AIMessage(content="GLM 2")])
    one, two = model.bind_tools([]), model.bind_tools([])
    assert _ask(one).content == "GLM 1" and _ask(two).content == "GLM 2"


def test_an_error_that_is_not_the_providers_is_not_swallowed():
    import pytest

    model, _, fallback = _pair([ValueError("bug")], [AIMessage(content="từ GLM")])
    with pytest.raises(ValueError):
        _ask(model)
    assert next(fallback.messages).content == "từ GLM"


def test_when_the_fallback_fails_too_its_error_is_raised():
    import pytest

    model, _, _ = _pair([_api_down()], [_api_down()])
    with pytest.raises(openai.APIConnectionError):
        _ask(model)


def test_tools_are_bound_to_whichever_model_answers():
    seen = {}

    class _Spy(_Scripted):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen[self.tag] = self.bound
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        tag: str = ""

    primary = _Spy(messages=iter([_api_down()]), tag="primary")
    fallback = _Spy(messages=iter([AIMessage(content="ok")]), tag="fallback")
    model = llm.FallbackChatModel(primary=primary, fallback=fallback).bind_tools(["tool_a"])
    assert _ask(model).content == "ok"
    assert seen == {"primary": ["tool_a"], "fallback": ["tool_a"]}

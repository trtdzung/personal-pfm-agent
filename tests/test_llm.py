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

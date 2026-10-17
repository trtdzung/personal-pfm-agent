import time
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command


class LogToolCalls(AgentMiddleware):
    """Print every tool call before and after execution, with duration.

    Implements both the sync and async hooks so this middleware works
    whether the agent is invoked via .invoke()/.stream() (sync — e.g. the
    local notebooks/try_agent.ipynb and scripts/verify_agent.py) or
    .ainvoke()/.astream() (async — e.g. the managed Agent Server). Only
    implementing one raises NotImplementedError in the other context.

    Pairs with `LogModelCalls` below for a full step-by-step timeline
    (tool-execution time vs model-thinking time) in plain server logs, no
    external dependency (e.g. LangSmith) needed -- see todo.md's
    performance investigation for why this matters: agent latency here is
    dominated by the NUMBER of sequential model+tool round-trips in a
    turn, not any single slow step, so seeing each step's duration is what
    actually explains where time goes.
    """

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        name = request.tool_call["name"]
        print(f"Calling tool: {name}")
        t0 = time.perf_counter()
        result = handler(request)
        dt = time.perf_counter() - t0
        print(f"Finished tool: {name} ({dt:.2f}s)")
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        name = request.tool_call["name"]
        print(f"Calling tool: {name}")
        t0 = time.perf_counter()
        result = await handler(request)
        dt = time.perf_counter() - t0
        print(f"Finished tool: {name} ({dt:.2f}s)")
        return result


class LogModelCalls(AgentMiddleware):
    """Print the duration of every LLM call the agent makes.

    One "model call" here is one full round-trip to the LLM API (one turn
    of the agent's tool-calling loop deciding what to do next, or
    composing the final answer) -- see `LogToolCalls` above for the
    complementary tool-execution-time half of the picture.
    """

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        t0 = time.perf_counter()
        response = handler(request)
        dt = time.perf_counter() - t0
        print(f"Model call: {dt:.2f}s")
        return response

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        t0 = time.perf_counter()
        response = await handler(request)
        dt = time.perf_counter() - t0
        print(f"Model call: {dt:.2f}s")
        return response


log_tool_calls = LogToolCalls()
log_model_calls = LogModelCalls()

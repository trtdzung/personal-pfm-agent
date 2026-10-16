from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command


class LogToolCalls(AgentMiddleware):
    """Print every tool call before and after execution.

    Implements both the sync and async hooks so this middleware works
    whether the agent is invoked via .invoke()/.stream() (sync — e.g. the
    local notebooks/try_agent.ipynb and scripts/verify_agent.py) or
    .ainvoke()/.astream() (async — e.g. the managed Agent Server). Only
    implementing one raises NotImplementedError in the other context.
    """

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        print(f"Calling tool: {request.tool_call['name']}")
        result = handler(request)
        print(f"Finished tool: {request.tool_call['name']}")
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        print(f"Calling tool: {request.tool_call['name']}")
        result = await handler(request)
        print(f"Finished tool: {request.tool_call['name']}")
        return result


log_tool_calls = LogToolCalls()

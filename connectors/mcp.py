from managed_deepagents import connectors

# Example remote MCP server declaration. Not wired into agent.py by default —
# add it to `agent.py`'s `tools=[...]` (or a subagent) once you want the
# agent to call it.
connector = connectors.mcp(
    mcp_servers={
        "langchainDocs": {
            "transport": "http",
            "url": "https://docs.langchain.com/mcp",
            "include_tools": ["search_docs_by_lang_chain"],
        },
    },
)

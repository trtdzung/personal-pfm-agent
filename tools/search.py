from langchain.tools import tool


@tool(parse_docstring=True)
def internet_search(query: str) -> str:
    """Search the internet for relevant sources.

    This is a mock implementation so the quickstart runs with no extra
    API keys beyond the model provider key. Swap it for a real search
    tool (e.g. Tavily) when you're ready to go further than the quickstart.

    Args:
        query: The search query.
    """
    return f"Mock results for: {query}"

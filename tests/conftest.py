import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

collect_ignore = []
try:
    import fastapi  # noqa: F401
except ImportError:
    collect_ignore.extend(["test_server.py", "test_jar_endpoint.py", "test_insight_endpoint.py", "test_proactive_endpoint.py"])

try:
    import greennode_agent_bridge  # noqa: F401
except ImportError:
    collect_ignore.extend([
        "test_checkpointer_delta_snapshot.py",
        "test_checkpointer_delete_pagination.py",
        "test_checkpointer_local_cache_race.py",
    ])

try:
    import langchain_openai  # noqa: F401
except ImportError:
    collect_ignore.append("test_llm.py")

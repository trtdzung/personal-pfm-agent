import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

collect_ignore = []
try:
    import fastapi  # noqa: F401
except ImportError:
    collect_ignore.append("test_server.py")

try:
    import greennode_agent_bridge  # noqa: F401
except ImportError:
    collect_ignore.append("test_checkpointer_delta_snapshot.py")

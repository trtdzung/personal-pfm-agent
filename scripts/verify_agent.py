"""Local-invoke verification script for personal-card-agent.

Exercises the checklist in
docs/superpowers/plans/2026-08-30-personal-card-agent-verification.md
(rows 1-9 and 11) against the real agent construction from agent.py,
using a local `deepagents.create_deep_agent` (no `mda dev` server needed)
with a `MemorySaver()` checkpointer so same-thread multi-turn rows (8->9)
work correctly.

Row 10 (cross-thread durable budget memory via /memories/agent/) CANNOT be
tested by this script -- that mount only exists on the real managed
deployment. Run `mda dev .` and test row 10 through LangSmith Studio
instead.

Usage:
    uv sync --extra notebook   # once, for python-dotenv
    uv run --extra notebook python scripts/verify_agent.py

Requires OPENAI_API_KEY in .env. This script makes real API calls and will
incur real cost -- it is not run automatically by any test suite.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from deepagents import create_deep_agent  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from middleware.audit import log_tool_calls  # noqa: E402
from middleware.seed_customer_context import SeedCustomerContext  # noqa: E402

CHECKLIST_QUESTIONS = [
    "Tháng này tôi đã chi tiêu bao nhiêu trên thẻ?",
    "Giao dịch lớn nhất tuần vừa rồi là gì?",
    "Liệt kê các giao dịch trên 2 triệu trong tháng 7",
    'Danh mục nào đang "ngốn" tiền của tôi nhất?',
    "Tôi có đang trả lãi thẻ tín dụng không, và vì sao?",
    "Tôi nên dùng thẻ tín dụng hay ghi nợ cho khoản chi 5 triệu này?",
    "Ngày sao kê và ngày đến hạn thanh toán của thẻ tôi là khi nào?",
    "Tôi có đang chi tiêu vượt ngân sách tháng này không?",
    "Ngân sách của tôi là 15 triệu/tháng.",
    "Vậy tôi có đang chi tiêu vượt ngân sách tháng này không?",
    "Khoá thẻ của tôi giúp tôi.",
]
THREAD_CONFIG = {"configurable": {"thread_id": "script-verify-1"}}


def build_agent():
    instructions = (REPO_ROOT / "instructions.md").read_text(encoding="utf-8")
    return create_deep_agent(
        model="openai:gpt-5.5",
        tools=[],
        middleware=[log_tool_calls, SeedCustomerContext()],
        system_prompt=instructions,
        checkpointer=MemorySaver(),
    )


def main() -> None:
    assert os.environ.get("OPENAI_API_KEY"), (
        f"Set OPENAI_API_KEY in {REPO_ROOT / '.env'} first"
    )
    agent = build_agent()
    for question in CHECKLIST_QUESTIONS:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config=THREAD_CONFIG,
        )
        print(f"Q: {question}\nA: {result['messages'][-1].content}\n{'-' * 60}")

    print(
        "Row 10 (cross-thread durable budget memory) cannot be tested by this "
        "script -- run `mda dev .` and re-ask the budget question in a NEW "
        "Studio thread instead."
    )


if __name__ == "__main__":
    main()

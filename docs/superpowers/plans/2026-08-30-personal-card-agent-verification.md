# Personal Card Agent — Manual Verification

Two ways to exercise these questions against the real agent:

- **Via `mda dev .` + LangSmith Studio** (the only way to test row 10,
  cross-thread durable budget memory — local tooling below cannot do this).
- **Via local tooling** (`notebooks/try_agent.ipynb`'s appended cells, or
  `uv run --extra notebook python scripts/verify_agent.py`) — exercises
  rows 1-9 and 11 against the real model using this repo's actual
  `agent.py` construction (name, tools, middleware, instructions), with a
  local checkpointer so same-thread multi-turn rows (8→9) work. Prints
  each question/answer pair to the terminal; row 10 is skipped with a
  reminder to test it via Studio instead.

Run against: (fill in date/commit when run)

Prerequisite: `.env` has `OPENAI_API_KEY` filled in (and `LANGSMITH_API_KEY`
too if using the `mda dev` route). For the local-tooling route:
`uv sync --extra notebook` first (needed for `python-dotenv` and the
notebook-invoke path).

For each question, record PASS/FAIL and a one-line note. A PASS requires:
the audit middleware log shows `read_file` was called on `/customer_data.json`
before the answer, the numbers in the answer match `data/customer_data.json`,
and the agent never claims to have performed a card action.

| # | Question (from docs/sample_questions_and_answers.md) | Result | Note |
|---|---|---|---|
| 1 | Tháng này tôi đã chi tiêu bao nhiêu trên thẻ? | | |
| 2 | Giao dịch lớn nhất tuần vừa rồi là gì? | | |
| 3 | Liệt kê các giao dịch trên 2 triệu trong tháng 7 | | |
| 4 | Danh mục nào đang "ngốn" tiền của tôi nhất? | | |
| 5 | Tôi có đang trả lãi thẻ tín dụng không, và vì sao? | | |
| 6 | Tôi nên dùng thẻ tín dụng hay ghi nợ cho khoản chi 5 triệu này? | | |
| 7 | Ngày sao kê và ngày đến hạn thanh toán của thẻ tôi là khi nào? | | |
| 8 | Tôi có đang chi tiêu vượt ngân sách tháng này không? (asked *before* ever telling the agent a budget — expect it to ask you for one, not guess) | | |
| 9 | Same thread: tell the agent "ngân sách của tôi là 15 triệu/tháng", then re-ask question 8 — expect it to use that number | | |
| 10 | **Studio-only** — start a **new** thread (new `thread_id`) and re-ask question 8 — expect it to still remember the budget from question 9 (durable memory). Local tooling cannot test this — see the limitation note above. | | |
| 11 | "Khoá thẻ của tôi giúp tôi" — expect the agent to decline/redirect, not claim to have locked the card | | |

## Follow-ups filed

(List anything that failed and needs a follow-up task; leave "None" if all
rows passed. If this file was created but never run, say that explicitly
here instead of leaving blank rows silently.)

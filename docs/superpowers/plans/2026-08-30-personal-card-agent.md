# Personal Card Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `research-assistant` Managed Deep Agents scaffold into `personal-card-agent`, an agent that answers the card-finance questions in `docs/sample_questions_and_answers.md` using `data/customer_data.json`, with zero hardcoded per-question answer logic.

**Architecture:** A `before_agent` middleware (`SeedCustomerContext`) re-reads `data/customer_data.json` from disk on every run and seeds it into the session's virtual filesystem as `/customer_data.json`; the agent answers by calling deepagents' built-in `read_file`/`grep` tools and reasoning over that JSON itself — no custom calculation tools. A durable, agent-scoped memory file `/memories/agent/customer_budgets.json` (via the existing `memory.py`) holds the one fact the system has no other source for (customer-stated budget), keyed by `customer_id` so it never gets overwritten wholesale. An explicit `MemorySaver()` checkpointer keeps in-thread conversation history durable across turns instead of relying on undocumented platform defaults.

**Tech Stack:** Python 3.11+, `managed-deepagents` / `deepagents` (LangGraph-based), `langchain`, `uv` for dependency management and packaging, `pytest` for tests, Harbor for evals.

**Spec:** `docs/superpowers/specs/2026-08-30-personal-card-agent-design.md`

## Global Constraints

- No tool computes answers (no "sum spending", "top category" style tools). All aggregation/reasoning happens in the LLM over data read via generic `read_file`/`grep`/`write_file`/`edit_file` tools already provided by deepagents.
- `data/customer_data.json` is re-read from disk every agent run (session-scoped state), never embedded statically into `instructions.md` or committed to durable memory.
- `/memories/agent/customer_budgets.json` is a dict keyed by `customer_id`; code and instructions must only ever read/write the current customer's entry, never overwrite the whole file.
- The agent provides information and advice only — it must never claim to perform card actions (open card, lock card, set alerts).
- Single demo customer for this iteration; multi-customer auth (`identity.py`) and per-user thread isolation are explicitly out of scope (see spec §9).
- `MemorySaver()` (in-memory) is the checkpointer for this iteration; a persistent production checkpointer is out of scope (see spec §9).

---

## Task 1: Relocate customer data + regression-test its arithmetic

**Files:**
- Create: `data/customer_data.json` (moved from `docs/sample_customer_data.json`)
- Delete: `docs/sample_customer_data.json`
- Modify: `pyproject.toml` (add a `dev` dependency group for `pytest`)
- Test: `tests/data/test_customer_data.py`

**Interfaces:**
- Produces: `data/customer_data.json` at the fixed repo-relative path every later task reads from. Top-level keys: `customer`, `chat_memory_example`, `cards`, `statements`, `monthly_spending_summary`, `transactions`.
- Produces: a `dev` dependency group (`pytest`) runnable via `uv sync --group dev` / `uv run --group dev pytest`, which every later test-bearing task relies on.

- [ ] **Step 1: Add the `pytest` dev dependency group**

Edit `pyproject.toml`, adding this section after `[project.optional-dependencies]`:

```toml
[dependency-groups]
dev = ["pytest"]
```

- [ ] **Step 2: Write the failing test**

Create `tests/data/test_customer_data.py`:

```python
import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "customer_data.json"


def _load():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def test_customer_data_file_exists_and_valid_json():
    assert DATA_PATH.exists(), "expected data/customer_data.json to exist"
    data = _load()
    assert isinstance(data, dict)


def test_customer_data_has_required_top_level_keys():
    data = _load()
    for key in (
        "customer",
        "chat_memory_example",
        "cards",
        "statements",
        "monthly_spending_summary",
        "transactions",
    ):
        assert key in data, f"missing top-level key: {key}"


def test_customer_has_customer_id():
    data = _load()
    assert "customer_id" in data["customer"]


def test_monthly_totals_match_summed_transactions():
    data = _load()
    totals_by_month: dict[str, int] = {}
    counts_by_month: dict[str, int] = {}
    for txn in data["transactions"]:
        month = txn["date"][:7]
        totals_by_month[month] = totals_by_month.get(month, 0) + txn["amount_vnd"]
        counts_by_month[month] = counts_by_month.get(month, 0) + 1

    for month, summary in data["monthly_spending_summary"].items():
        if month.startswith("_"):
            continue
        assert totals_by_month[month] == summary["total_vnd"], (
            f"{month}: summed transactions {totals_by_month[month]} != "
            f"declared total_vnd {summary['total_vnd']}"
        )
        assert counts_by_month[month] == summary["transaction_count"], (
            f"{month}: summed transaction count {counts_by_month[month]} != "
            f"declared transaction_count {summary['transaction_count']}"
        )


def test_category_breakdown_sums_to_month_total():
    data = _load()
    for month, summary in data["monthly_spending_summary"].items():
        if month.startswith("_"):
            continue
        category_sum = sum(summary["by_category_vnd"].values())
        assert category_sum == summary["total_vnd"], (
            f"{month}: category breakdown sums to {category_sum} != "
            f"total_vnd {summary['total_vnd']}"
        )
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run --group dev pytest tests/data/test_customer_data.py -v`
Expected: FAIL — `data/customer_data.json` does not exist yet (only `docs/sample_customer_data.json` does).

- [ ] **Step 4: Move the data file**

```bash
git mv docs/sample_customer_data.json data/customer_data.json
```

(The file's content is unchanged — it already contains the customer/cards/statements/monthly_spending_summary/transactions structure the test checks.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --group dev pytest tests/data/test_customer_data.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add data/customer_data.json pyproject.toml tests/data/test_customer_data.py
git status  # confirm docs/sample_customer_data.json shows as deleted (git mv already staged it)
git commit -m "move customer sample data to data/, add regression test for arithmetic"
```

---

## Task 2: `SeedCustomerContext` middleware

**Files:**
- Create: `middleware/seed_customer_context.py`
- Test: `tests/middleware/test_seed_customer_context.py`

**Interfaces:**
- Consumes: `data/customer_data.json` (Task 1) as the on-disk source of truth.
- Produces: `middleware.seed_customer_context.SeedCustomerContext` (an `AgentMiddleware` subclass) and `middleware.seed_customer_context.SESSION_FILE_PATH = "/customer_data.json"`, both imported by `agent.py` in Task 3.

- [ ] **Step 1: Verify the deepagents middleware/file-seeding API**

Run:

```bash
uv sync --group dev
uv run python -c "
from langchain.agents.middleware import AgentMiddleware, AgentState
from deepagents.backends.utils import create_file_data
import inspect
print(inspect.signature(AgentMiddleware.abefore_agent))
print(inspect.signature(create_file_data))
"
```

Expected: prints a signature for `abefore_agent` of the shape
`(self, state: AgentState, runtime: Runtime) -> ...` and a signature for
`create_file_data` that takes text/bytes content. If either import fails or
the signature differs meaningfully (e.g. `create_file_data` lives in a
different module, or the hook is named differently), adjust the imports and
class body in Step 3 to match what you actually observe — the test in Step 2
is the pass/fail authority, not this inspection.

- [ ] **Step 2: Write the failing test**

Create `tests/middleware/test_seed_customer_context.py`:

```python
import asyncio
import json

from middleware.seed_customer_context import SeedCustomerContext, SESSION_FILE_PATH


def test_abefore_agent_seeds_customer_data_file():
    middleware = SeedCustomerContext()
    result = asyncio.run(middleware.abefore_agent(state={}, runtime=None))

    assert "files" in result
    assert SESSION_FILE_PATH in result["files"]

    file_data = result["files"][SESSION_FILE_PATH]
    content = file_data["content"] if isinstance(file_data, dict) else file_data
    if isinstance(content, bytes):
        content = content.decode("utf-8")

    parsed = json.loads(content)
    assert "customer_id" in parsed["customer"]
    assert "transactions" in parsed


def test_session_file_path_is_absolute():
    assert SESSION_FILE_PATH.startswith("/")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run --group dev pytest tests/middleware/test_seed_customer_context.py -v`
Expected: FAIL — `middleware/seed_customer_context.py` does not exist yet.

- [ ] **Step 4: Implement the middleware**

Create `middleware/seed_customer_context.py`:

```python
from pathlib import Path

from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

CUSTOMER_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "customer_data.json"
SESSION_FILE_PATH = "/customer_data.json"


class SeedCustomerContext(AgentMiddleware):
    """Seed the current customer's data into the session's virtual filesystem.

    Reads data/customer_data.json fresh from disk on every run so the agent
    always sees the current source of truth. This is session-scoped state
    (StateBackend) — it never persists across threads. For data that must
    persist across threads (the customer's stated budget), see memory.py and
    /memories/agent/customer_budgets.json instead.
    """

    async def abefore_agent(self, state: AgentState, runtime: Runtime) -> dict:
        content = CUSTOMER_DATA_PATH.read_text(encoding="utf-8")
        return {"files": {SESSION_FILE_PATH: create_file_data(content)}}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --group dev pytest tests/middleware/test_seed_customer_context.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add middleware/seed_customer_context.py tests/middleware/test_seed_customer_context.py
git commit -m "add SeedCustomerContext middleware to seed customer data every session"
```

---

## Task 3: Wire `agent.py` (middleware, checkpointer, rename, drop search tool)

**Files:**
- Modify: `agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `middleware.seed_customer_context.SeedCustomerContext` (Task 2), `middleware.audit.log_tool_calls` (existing, unchanged).
- Produces: `agent.agent`, a `personal-card-agent` deep agent with no `internet_search` tool, `SeedCustomerContext` + `log_tool_calls` middleware, and an explicit `MemorySaver()` checkpointer. Later tasks (instructions rewrite, evals) assume this agent name and this middleware wiring.

- [ ] **Step 1: Verify `define_deep_agent` accepts a `checkpointer` argument**

Run:

```bash
uv run python -c "
from managed_deepagents import define_deep_agent
import inspect
print(inspect.signature(define_deep_agent))
"
```

Expected: `checkpointer` appears as a parameter. If it does not, keep
`checkpointer=MemorySaver()` out of the `define_deep_agent(...)` call, note
in a code comment above the call that the platform's default checkpointing is
being relied on instead (per spec §5's documented fallback), and skip the
`test_checkpointer_explicitly_configured` assertion in Step 2 (delete that
one test function) — do not block the rest of this task on it.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_agent.py`:

```python
from pathlib import Path

AGENT_PY = Path(__file__).resolve().parents[1] / "agent.py"


def _source() -> str:
    return AGENT_PY.read_text(encoding="utf-8")


def test_agent_module_imports_without_error():
    import agent  # noqa: F401 -- import failure is the test failure


def test_agent_renamed_to_personal_card_agent():
    assert 'name="personal-card-agent"' in _source()


def test_internet_search_tool_removed():
    assert "internet_search" not in _source()


def test_seed_customer_context_middleware_wired():
    assert "SeedCustomerContext()" in _source()


def test_checkpointer_explicitly_configured():
    assert "MemorySaver()" in _source()
    assert "checkpointer=MemorySaver()" in _source()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --group dev pytest tests/test_agent.py -v`
Expected: FAIL — `agent.py` still defines `research-assistant` with `internet_search`.

- [ ] **Step 4: Rewrite `agent.py`**

```python
from langgraph.checkpoint.memory import MemorySaver
from managed_deepagents import define_deep_agent

from middleware.audit import log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext

agent = define_deep_agent(
    name="personal-card-agent",
    model="openai:gpt-5.5",
    tools=[],
    middleware=[log_tool_calls, SeedCustomerContext()],
    checkpointer=MemorySaver(),
)
```

(If Step 1 found `define_deep_agent` does not accept `checkpointer`, drop
that line and the `from langgraph.checkpoint.memory import MemorySaver`
import, and add a one-line comment noting the platform default is used
instead.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --group dev pytest tests/test_agent.py -v`
Expected: PASS. `test_agent_module_imports_without_error` requires a valid
`.env` (`OPENAI_API_KEY`, `LANGSMITH_API_KEY` per README Setup) — if those
are not configured in this environment, that one test may fail at
model-string resolution; treat the other three (source-based) tests as the
authoritative signal for this task and note the skipped import check for
follow-up in an environment with real keys.

- [ ] **Step 6: Commit**

```bash
git add agent.py tests/test_agent.py
git commit -m "rewire agent.py as personal-card-agent: drop search tool, add context seeding and checkpointer"
```

---

## Task 4: Rewrite `instructions.md`

**Files:**
- Modify: `instructions.md`
- Test: `tests/test_instructions.py`

**Interfaces:**
- Consumes: `SESSION_FILE_PATH = "/customer_data.json"` (Task 2, referenced as a literal path — instructions.md is prose, not code, so no import) and the durable path `/memories/agent/customer_budgets.json` (design spec §4).
- Produces: the agent's behavioral contract; no other task depends on its exact wording, only on the file existing and containing the assertions tested below.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_instructions.py`:

```python
from pathlib import Path

INSTRUCTIONS = Path(__file__).resolve().parents[1] / "instructions.md"


def _text() -> str:
    return INSTRUCTIONS.read_text(encoding="utf-8")


def test_instructions_defines_info_only_role():
    assert "chỉ cung cấp thông tin và tư vấn" in _text()


def test_instructions_references_customer_data_file():
    assert "/customer_data.json" in _text()


def test_instructions_references_budget_memory_file():
    assert "/memories/agent/customer_budgets.json" in _text()


def test_instructions_warns_against_overwriting_whole_budget_file():
    assert "không ghi đè toàn bộ file" in _text()


def test_instructions_no_longer_describes_research_assistant():
    text = _text().lower()
    assert "careful research assistant" not in text
    assert "internet search" not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --group dev pytest tests/test_instructions.py -v`
Expected: FAIL — current `instructions.md` is still the research-assistant prompt.

- [ ] **Step 3: Rewrite `instructions.md`**

```markdown
# Personal Card Agent

Bạn là trợ lý tài chính về thẻ (personal card agent) cho một khách hàng cá
nhân. Bạn **chỉ cung cấp thông tin và tư vấn tài chính** — bạn không thực
hiện bất kỳ hành động nào làm thay đổi trạng thái thẻ (mở thẻ, khoá thẻ, đặt
lịch nhắc, thiết lập cảnh báo tự động...). Nếu khách hàng yêu cầu một hành
động như vậy, giải thích rằng việc đó ngoài phạm vi hỗ trợ hiện tại và gợi ý
họ liên hệ kênh phù hợp (tổng đài, app ngân hàng).

## Trước khi trả lời bất kỳ câu hỏi nào về số liệu

1. Đọc `/customer_data.json` bằng `read_file` (hoặc `grep` nếu chỉ cần lọc
   nhanh theo từ khoá/khoảng ngày trong file lớn). File này được nạp lại mới
   hoàn toàn vào đầu mỗi phiên — luôn là dữ liệu khách hàng hiện tại, không
   bao giờ dùng số liệu ví dụ hay nhớ lại từ các phiên trước.
2. Tự tính toán (tổng, %, so sánh, xu hướng...) trực tiếp từ dữ liệu đọc
   được. Không có công cụ tính sẵn nào khác — mọi phép cộng/so sánh là bạn tự
   làm. Khi cộng nhiều giao dịch, liệt kê lại các số hạng trước khi ra tổng để
   giảm sai sót.
3. Không bao giờ bịa số. Nếu dữ liệu không đủ để trả lời, nói rõ giới hạn đó
   thay vì suy diễn.

## Câu hỏi về ngân sách

Ngân sách/hạn mức tự đặt của khách hàng **không có trong `customer_data.json`
và không nằm trong bất kỳ hệ thống lõi nào** — bạn chỉ biết được nếu khách
hàng từng nói ra.

- Trước khi trả lời câu hỏi liên quan ngân sách, đọc file bền vững
  `/memories/agent/customer_budgets.json` bằng `read_file`. File này là một
  dict khoá theo `customer_id` (lấy `customer_id` từ trường `customer` trong
  `/customer_data.json`), ví dụ:
  `{"CUS-000482": {"monthly_budget_vnd": 15000000, "mentioned_on": "2026-08-10"}}`
- Nếu file chưa tồn tại, hoặc không có entry cho `customer_id` hiện tại: nói
  rõ bạn chưa biết ngân sách của khách hàng và hỏi lại — không giả định con
  số.
- Nếu khách hàng cho biết ngân sách (mới hoặc cập nhật) trong hội thoại, ghi
  lại bằng `write_file`/`edit_file` vào đúng entry của `customer_id` hiện tại
  — **tuyệt đối không ghi đè toàn bộ file**, chỉ cập nhật entry của khách
  hàng đang trò chuyện, để không ảnh hưởng dữ liệu của khách hàng khác trong
  cùng file dùng chung này.

## Các nhóm câu hỏi cần trả lời được

Tham khảo đầy đủ ví dụ và giọng văn tại
`docs/sample_questions_and_answers.md`. Không copy số liệu ví dụ trong tài
liệu đó — luôn tính lại từ `/customer_data.json` thật của khách hàng đang
trò chuyện.

1. **Thống kê & tra cứu giao dịch** — tổng chi tiêu theo khoảng thời gian,
   giao dịch lớn nhất, lọc theo mức tiền/danh mục, điểm thưởng/hoàn tiền.
2. **Quản lý chi tiêu** — so với ngân sách (xem mục trên), số dư khả dụng,
   mức trả tối thiểu để tránh lãi.
3. **Insight & phân tích hành vi chi tiêu** — bất thường, danh mục chiếm tỉ
   trọng lớn, so sánh giữa các tháng, có đang trả lãi không và vì sao, có
   đang tối ưu hoàn tiền/điểm thưởng không.
4. **Tư vấn tài chính & chi tiêu** — chọn thẻ tín dụng/ghi nợ cho một khoản
   chi, cắt giảm chi tiêu ở đâu, phân bổ chi tiêu hợp lý theo thu nhập, cải
   thiện điểm tín dụng, đánh giá phí thường niên, xử lý khi sắp trễ hạn.
5. **Thông tin thẻ & kỳ sao kê** — ngày sao kê/đến hạn, hạn mức, ưu đãi thẻ,
   trạng thái sao kê hiện tại.

## Nguyên tắc trả lời chung

- Luôn dẫn số liệu cụ thể lấy từ `/customer_data.json` (và
  `/memories/agent/customer_budgets.json` khi liên quan) — không bịa số.
- Nêu rõ khoảng thời gian/kỳ dữ liệu đang tham chiếu.
- Tư vấn = gợi ý có căn cứ dựa trên dữ liệu thật của khách hàng, không khẳng
  định chắc chắn thay khách hàng ra quyết định tài chính.
- Insight ưu tiên giải thích "vì sao" (nguyên nhân/đóng góp chính), không chỉ
  liệt kê số liệu.
- Khi thiếu dữ liệu, nói rõ giới hạn thay vì suy diễn.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --group dev pytest tests/test_instructions.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add instructions.md tests/test_instructions.py
git commit -m "rewrite instructions.md for the personal card agent"
```

---

## Task 5: Scaffold cleanup, `pyproject.toml` packaging, `README.md`

**Files:**
- Delete: `tools/search.py`, `tools/` (directory, once empty), `skills/research/SKILL.md`, `skills/research/` (directory), `skills/` (directory, once empty), `sandbox/__init__.py`, `sandbox/` (directory)
- Modify: `pyproject.toml`, `README.md`
- Test: `tests/test_packaging.py`, `tests/test_readme.py`

**Interfaces:**
- Consumes: nothing code-level from earlier tasks (this is repo hygiene), but should run after Task 3 confirms `tools/search.py` is truly unreferenced.
- Produces: a wheel build that includes `data/customer_data.json`; no other task depends on this one's outputs.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_readme.py`:

```python
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_describes_personal_card_agent():
    text = README.read_text(encoding="utf-8")
    assert "personal-card-agent" in text
    assert "research-assistant" not in text
```

Create `tests/test_packaging.py`:

```python
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed in this environment")
def test_wheel_includes_customer_data_json(tmp_path):
    dist_dir = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        cwd=REPO_ROOT,
        check=True,
    )
    wheels = sorted(dist_dir.glob("*.whl"))
    assert wheels, "expected `uv build --wheel` to produce a .whl file"
    with zipfile.ZipFile(wheels[-1]) as archive:
        names = archive.namelist()
        assert any(name.endswith("customer_data.json") for name in names), names
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --group dev pytest tests/test_readme.py tests/test_packaging.py -v`
Expected: `test_readme_describes_personal_card_agent` FAILs (README still says
research-assistant). `test_wheel_includes_customer_data_json` either FAILs
(current `pyproject.toml` has no `data/customer_data.json` inclusion rule) or
is SKIPPED if `uv` is unavailable in this environment — either is an
acceptable starting state.

- [ ] **Step 3: Delete unused scaffold pieces**

```bash
git rm tools/search.py
git rm -r skills/research
git rm sandbox/__init__.py
rmdir tools 2>/dev/null || true
rmdir sandbox 2>/dev/null || true
rmdir skills 2>/dev/null || true
```

(The trailing `rmdir` calls are best-effort — they only succeed if the
directory is now empty; ignore failures.)

- [ ] **Step 4: Update `pyproject.toml`**

Replace the `[project]` block's `name`/`description` and the
`[tool.hatch.build.targets.wheel]` section:

```toml
[project]
name = "personal-card-agent"
version = "0.1.0"
description = "Managed Deep Agents personal financial assistant for card customers: transaction stats, spending insights, and financial advice from a customer's card data."
requires-python = ">=3.11"
dependencies = [
    "managed-deepagents",
    "langchain",
]
```

```toml
[tool.hatch.build.targets.wheel]
packages = ["middleware"]

[tool.hatch.build.targets.wheel.force-include]
"data/customer_data.json" = "data/customer_data.json"
```

- [ ] **Step 5: Update `README.md`**

Replace the title and opening paragraph:

```markdown
# personal-card-agent — Managed Deep Agents personal card assistant

A [Managed Deep Agents](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)
(MDA) project: a card-finance assistant that answers a customer's spending,
budgeting, insight, and advisory questions from `data/customer_data.json`,
built by repurposing the MDA quickstart scaffold. See
`docs/sample_questions_and_answers.md` for the question catalogue and
`docs/superpowers/specs/2026-08-30-personal-card-agent-design.md` for the
design.
```

Replace the "Try asking" line under **Run locally**:

```markdown
This compiles the project, loads `.env`, starts a local Agent Server, and
opens LangSmith Studio so you can chat with the agent and inspect tool
calls. Try asking: *"Tháng này tôi đã chi tiêu bao nhiêu trên thẻ?"*
```

In the **Project layout** section, replace the tree and the notes below it
to match the current layout (drop `tools/search.py`, `skills/`, `sandbox/`;
add `data/customer_data.json` and `middleware/seed_customer_context.py`):

```
.
├── agent.py                 # define_deep_agent(): name, model, middleware, checkpointer
├── instructions.md          # system prompt -> synced to Context Hub on deploy
├── identity.py              # who may call the deployment (LangSmith API key by default)
├── memory.py                # durable memory (on) — customer_budgets.json lives here
├── pyproject.toml           # dependencies + packaging (includes data/customer_data.json)
├── .env                     # OPENAI_API_KEY / LANGSMITH_API_KEY (never committed)
│
├── data/
│   └── customer_data.json   # sample customer data, re-read into every session
├── middleware/
│   ├── audit.py              # wrap_tool_call middleware that logs every tool call
│   └── seed_customer_context.py  # before_agent hook that seeds /customer_data.json
├── connectors/
│   └── mcp.py                # example remote MCP server declaration (not wired in by default)
├── channels/
│   └── slack.py               # Slack channel stub (needs a real Slack app to work)
├── schedules/
│   └── example.py             # daily cron-triggered run
├── sandbox/                   # deleted — not used by this agent
│
├── evals/
│   └── tasks/                 # Harbor eval tasks, incl. card-agent question checks
└── notebooks/
    └── try_agent.ipynb        # run the agent interactively, locally or via `mda dev`
```

(Remove the old bullet list of notes that referenced `tools/search.py`,
`skills/research`, and the Slack/schedules/connectors caveats can stay as
they still apply unmodified.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --group dev pytest tests/test_readme.py tests/test_packaging.py -v`
Expected: `test_readme_describes_personal_card_agent` PASSes.
`test_wheel_includes_customer_data_json` PASSes if `uv` is installed, or
stays SKIPPED otherwise — in that case, run the equivalent check manually in
an environment with `uv` before considering this task done:

```bash
uv build --wheel --out-dir /tmp/dist
python -c "
import zipfile, pathlib
whl = sorted(pathlib.Path('/tmp/dist').glob('*.whl'))[-1]
names = zipfile.ZipFile(whl).namelist()
assert any(n.endswith('customer_data.json') for n in names), names
print('OK:', [n for n in names if n.endswith('customer_data.json')])
"
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml README.md tests/test_readme.py tests/test_packaging.py
git add -u tools skills sandbox  # stage the deletions
git commit -m "clean up unused research-assistant scaffold, package customer data for deploy"
```

---

## Task 6: Harbor eval tasks for two arithmetic-heavy questions

**Files:**
- Create: `evals/tasks/spending-total-question/Task.md`, `evals/tasks/spending-total-question/instruction.md`, `evals/tasks/spending-total-question/environment/.gitkeep`, `evals/tasks/spending-total-question/tests/test_answer.py`
- Create: `evals/tasks/large-transactions-question/Task.md`, `evals/tasks/large-transactions-question/instruction.md`, `evals/tasks/large-transactions-question/environment/.gitkeep`, `evals/tasks/large-transactions-question/tests/test_answer.py`

**Interfaces:**
- Consumes: the exact numbers in `data/customer_data.json` as of Task 1 (August 2026 total = 11,324,000 VND; July 2026 transactions over 2,000,000 VND = Vietnam Airlines, Điện Máy Xanh, Lotte Mart). If `data/customer_data.json` is ever edited later, these two eval tasks' expected values must be updated to match — they are not computed dynamically.
- Produces: nothing consumed by other tasks; this is a leaf task.

This task's tests are graded by Harbor against a real agent run (`mda evals`
per the README), not by our own pytest suite directly — same caveat as the
existing `evals/tasks/example-task/Task.md`: "the exact Task.md schema is
still evolving in beta, so treat this file as a starting point rather than a
guaranteed-correct reference." Each step below is still independently
verifiable without running Harbor, by hand-writing a fake `answer.md` and
running the test file directly with pytest.

- [ ] **Step 1: Create the spending-total-question eval task**

Create `evals/tasks/spending-total-question/Task.md`:

```markdown
# spending-total-question

A Harbor task checking that the personal-card-agent correctly sums a
month's transactions from `data/customer_data.json`.

- **instruction**: `instruction.md`
- **environment**: `environment/` (empty — the agent starts from a blank
  working directory; its customer data comes from the `SeedCustomerContext`
  middleware, not from this directory)
- **grading**: `tests/test_answer.py` checks that `answer.md` contains the
  correct August 2026 total (11.324.000 VNĐ), derived by hand from
  `data/customer_data.json`

Run it with `mda evals init -i` to get Harbor set up, then execute this task
through Harbor once your environment/tests match the schema in the
[Harbor docs](https://www.harborframework.com/docs/tasks) — the exact
Task.md schema is still evolving in beta, so treat this file as a starting
point rather than a guaranteed-correct reference.
```

Create `evals/tasks/spending-total-question/instruction.md`:

```markdown
Trả lời câu hỏi sau dựa trên dữ liệu khách hàng hiện tại của bạn, viết câu
trả lời vào file `answer.md` trong thư mục làm việc:

Tính đến ngày hiện tại, khách hàng đã chi tiêu bao nhiêu trên thẻ trong
tháng 8/2026? Nêu rõ tổng số tiền (VNĐ).
```

Create empty `evals/tasks/spending-total-question/environment/.gitkeep` (zero
bytes, same as `evals/tasks/example-task/environment/.gitkeep`).

Create `evals/tasks/spending-total-question/tests/test_answer.py`:

```python
from pathlib import Path

# Expected total from data/customer_data.json ->
# monthly_spending_summary["2026-08"].total_vnd. Update this constant if the
# sample data changes.
EXPECTED_AUGUST_TOTAL_VND = 11324000


def test_answer_contains_correct_august_total():
    answer = Path("answer.md")
    assert answer.exists(), "expected the agent to create answer.md"
    text = answer.read_text()
    assert text.strip(), "answer.md should not be empty"

    normalized = text.replace(".", "").replace(",", "")
    assert str(EXPECTED_AUGUST_TOTAL_VND) in normalized, (
        f"expected answer.md to contain the August total "
        f"({EXPECTED_AUGUST_TOTAL_VND} VND), got: {text}"
    )
```

- [ ] **Step 2: Verify the test logic by hand, without a real agent**

```bash
cd evals/tasks/spending-total-question
echo "Khách hàng đã chi tổng cộng 11.324.000 VNĐ trong tháng 8/2026." > answer.md
uv run --group dev pytest tests/test_answer.py -v
rm answer.md
cd ../../..
```

Expected: PASS. This confirms the grading logic works before any real agent
run is involved.

- [ ] **Step 3: Create the large-transactions-question eval task**

Create `evals/tasks/large-transactions-question/Task.md`:

```markdown
# large-transactions-question

A Harbor task checking that the personal-card-agent correctly filters and
lists transactions above a threshold from `data/customer_data.json`.

- **instruction**: `instruction.md`
- **environment**: `environment/` (empty — the agent starts from a blank
  working directory; its customer data comes from the `SeedCustomerContext`
  middleware, not from this directory)
- **grading**: `tests/test_answer.py` checks that `answer.md` mentions all
  three July 2026 transactions over 2,000,000 VNĐ (Vietnam Airlines, Điện
  Máy Xanh, Lotte Mart) and does not mistakenly include a smaller one

Run it with `mda evals init -i` to get Harbor set up, then execute this task
through Harbor once your environment/tests match the schema in the
[Harbor docs](https://www.harborframework.com/docs/tasks) — the exact
Task.md schema is still evolving in beta, so treat this file as a starting
point rather than a guaranteed-correct reference.
```

Create `evals/tasks/large-transactions-question/instruction.md`:

```markdown
Trả lời câu hỏi sau dựa trên dữ liệu khách hàng hiện tại của bạn, viết câu
trả lời vào file `answer.md` trong thư mục làm việc:

Liệt kê tất cả giao dịch trên 2.000.000 VNĐ trong tháng 7/2026 — với mỗi
giao dịch nêu rõ merchant và số tiền.
```

Create empty `evals/tasks/large-transactions-question/environment/.gitkeep`.

Create `evals/tasks/large-transactions-question/tests/test_answer.py`:

```python
from pathlib import Path

# Expected transactions from data/customer_data.json, July 2026,
# amount_vnd > 2,000,000. Update this list if the sample data changes.
EXPECTED_MERCHANTS = ["Vietnam Airlines", "Điện Máy Xanh", "Lotte Mart"]


def test_answer_lists_all_large_july_transactions():
    answer = Path("answer.md")
    assert answer.exists(), "expected the agent to create answer.md"
    text = answer.read_text()
    assert text.strip(), "answer.md should not be empty"

    for merchant in EXPECTED_MERCHANTS:
        assert merchant in text, f"expected answer.md to mention {merchant}"

    # A smaller July transaction that must NOT be listed as if it were > 2tr.
    assert "Pizza Hut" not in text
```

- [ ] **Step 4: Verify the test logic by hand, without a real agent**

```bash
cd evals/tasks/large-transactions-question
cat > answer.md <<'EOF'
Các giao dịch trên 2.000.000 VNĐ trong tháng 7/2026:
- Vietnam Airlines: 2.850.000 VNĐ
- Điện Máy Xanh: 4.100.000 VNĐ
- Lotte Mart: 2.200.000 VNĐ
EOF
uv run --group dev pytest tests/test_answer.py -v
rm answer.md
cd ../../..
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/tasks/spending-total-question evals/tasks/large-transactions-question
git commit -m "add Harbor eval tasks for spending-total and large-transaction questions"
```

---

## Task 7: Manual end-to-end verification

**Files:**
- Create: `docs/superpowers/plans/2026-08-30-personal-card-agent-verification.md`

**Interfaces:**
- Consumes: the fully wired agent from Tasks 1-6.
- Produces: a filled-in verification record. This is the final task — nothing depends on it.

This task cannot be automated: it exercises real chat turns against a real
model. Do not mark the plan complete without doing it.

- [ ] **Step 1: Create the verification checklist**

Create `docs/superpowers/plans/2026-08-30-personal-card-agent-verification.md`:

```markdown
# Personal Card Agent — Manual Verification

Run against: `mda dev .` (fill in date/commit when run)

Prerequisite: `.env` has `OPENAI_API_KEY` and `LANGSMITH_API_KEY` filled in
(see README Setup).

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
| 10 | Start a **new** thread (new `thread_id`) and re-ask question 8 — expect it to still remember the budget from question 9 (durable memory), while a fresh question about turn-to-turn context from the *old* thread should NOT be recalled in this new thread | | |
| 11 | "Khoá thẻ của tôi giúp tôi" — expect the agent to decline/redirect, not claim to have locked the card | | |

## Follow-ups filed

(List anything that failed and needs a follow-up task; leave "None" if all
rows passed.)
```

- [ ] **Step 2: Run `mda dev .` and work through the table**

Fill in every row of the table in the file created in Step 1 while chatting
with the agent through LangSmith Studio (opened automatically by `mda dev .`).

- [ ] **Step 3: Commit the filled-in results**

```bash
git add docs/superpowers/plans/2026-08-30-personal-card-agent-verification.md
git commit -m "record manual verification results for personal-card-agent"
```

If any row failed, do not consider the plan complete — file a follow-up
task for each failure before treating this implementation as done.

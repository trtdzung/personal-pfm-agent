# personal-pfm-agent — Managed Deep Agents personal finance assistant

A [Managed Deep Agents](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)
(MDA) project: a card-finance assistant that answers a customer's spending,
budgeting, insight, and advisory questions from `data/customer_data.json`,
built by repurposing the MDA quickstart scaffold. See
`docs/sample_questions_and_answers.md` for the question catalogue and
`docs/superpowers/specs/2026-08-30-personal-card-agent-design.md` for the
design.

Managed Deep Agents is LangChain's hosted runtime for [deepagents](https://docs.langchain.com/oss/python/deepagents/overview)
projects — in this layout, **the directory a file lives in determines its
role** (tools, middleware, identity, memory, schedules, ...). This repo is
hand-authored to match the same shape `mda init` would scaffold, so you can
use it as a reference or delete pieces you don't need.
lệch

## Khai báo xuất xứ code và nguồn dữ liệu

### 1. Xuất xứ code

| Thành phần | Nguồn |
| ---------- | ----- |
| Khung dự án | Cấu trúc thư mục theo mẫu quickstart của [Managed Deep Agents](https://docs.langchain.com/langsmith/python/managed-deep-agents-quickstart) (LangChain, mẫu `research-assistant`), dựng lại thủ công theo cùng hình dạng rồi sửa thành trợ lý tài chính MSB. Tài liệu tham khảo nằm ở mục `Sources` cuối README. |
| Thư viện bên thứ ba | `deepagents`, `langchain`, `langchain-core`, `langchain-openai`, `fastapi`, `uvicorn`, `greennode-agent-bridge` (phiên bản ghim trong `requirements.txt`). |
| Do đội viết trong repo này | Máy chủ `server.py`; các tool trong `tools/` (đọc dữ liệu pfm, mô phỏng lộ trình tiết kiệm và vay `tools/goal_plan_*`, tra cứu kiến thức MSB); các skill nghiệp vụ `skills/` và `instructions.md`; phát hiện lừa đảo `fraud/`; kiểm tra đầu ra `ui_guard.py`, `guardrails.py`; các bản vá chạy lúc khởi động cho `greennode-agent-bridge` (`checkpointer_*.py`); bộ kiểm thử `tests/`. |
| Công cụ AI hỗ trợ lập trình | Một phần mã được viết với sự hỗ trợ của Claude (Anthropic) và Cursor; các dòng `Co-Authored-By` trong lịch sử git ghi lại những commit có sự tham gia đó. Đội chịu trách nhiệm về toàn bộ mã nộp, phần logic tài chính quan trọng có kiểm thử trong `tests/`. |

### 2. Mô hình LLM sử dụng

| Mục đích | Mô hình | Nơi chạy |
| -------- | ------- | -------- |
| Trợ lý chat chính (`POST /chat`) | `z-ai/glm-5.2-hackathon` (mặc định, đổi bằng `LLM_MODEL`) | GreenNode / VNG Cloud AI Platform (Model-as-a-Service) |
| Gợi ý mục tiêu, ước tính giá, hiểu ý định của coach mục tiêu | `google/gemma-4-31b-it` (đổi bằng `GOAL_COACH_MODEL`, `GOAL_PRICE_MODEL`, `GOAL_SUGGEST_MODEL`) | GreenNode / VNG Cloud MaaS |
| Các tính năng phụ còn lại (cân đối hũ, chống lừa đảo, insight, proactive) | Mô hình mặc định của agent (GLM-5.2) | GreenNode / VNG Cloud MaaS |

Mô hình chỉ diễn giải và soạn lời. Mọi con số tài chính (số dư, lộ trình, khoản trả vay, lãi) do code tính trong `tools/`, và thẻ lộ trình do tool dựng rồi máy chủ gắn vào câu trả lời, không do mô hình tự viết.

### 3. Nguồn dữ liệu

| Dữ liệu | Loại | Chi tiết |
| ------- | ---- | -------- |
| Hồ sơ khách hàng `data/customers/CIF_0001` đến `CIF_0004` | Giả lập (synthetic) | Bốn persona mẫu. Tài khoản, giao dịch và tổng hợp chi tiêu được đồng bộ từ cơ sở dữ liệu prototype của repo `pfm` (bản ghi gắn nhãn `source: mock`); thẻ, sao kê và thông tin cá nhân là dữ liệu minh họa. Không dùng dữ liệu khách hàng thật của MSB. |
| Kiến thức sản phẩm MSB `data/msb_knowledge/pages/` | Crawl từ nguồn công khai | 77 trang của `www.msb.com.vn/khach-hang-ca-nhan/` cùng các PDF biểu phí có lớp chữ, lấy ngày 19/09/2026 bằng TinyFish Fetch (`scripts/sync_msb_knowledge.py`). Mỗi đoạn trích dẫn kèm URL nguồn và ngày lấy. |
| Lãi suất tiền gửi `data/msb_knowledge/curated/*.md` | Chép tay từ văn bản công khai | Các quyết định lãi suất của MSB phát hành dưới dạng ảnh scan (ví dụ QĐ 4144, QĐ 2896) được đội chép tay; mỗi bản chép ghi mã sha256 của PDF gốc để phát hiện văn bản đổi. |
| Tin tức thị trường (tool `search_market_news`) | Crawl lúc chạy, tùy chọn | `cafef.vn`, `vietstock.vn`, `tuoitre.vn` qua TinyFish; không có khóa thì tool trả "chưa cấu hình". |
| Kịch bản lừa đảo `data/fraud_playbook.json` | Tự soạn (nhãn `source: mock`) | Do đội soạn, phiên bản 2026-10-15. |
| Dữ liệu khách theo thời gian thực | API của repo `pfm` | Agent đọc qua `PFM_BASE_URL`; nguồn gốc dữ liệu pfm xem README của repo `pfm`. |

## Ghi chú bảo mật: thông tin xác thực đã lộ trong lịch sử git đã bị thu hồi

Notebook thử nghiệm `notebooks/greennode_agentbase_test.ipynb` từng chứa trực tiếp Client Secret của ứng dụng xác thực máy-với-máy dùng để gọi agent, cùng một token truy cập (đã hết hạn từ trước). Hai commit liên quan là `0a25fc0` và `8b162b3` (17/10/2026), nên giá trị này vẫn đọc được trong lịch sử git.

Cách xử lý, hoàn tất ngày 21/10/2026:

- **Đã thu hồi (xoay) Client Secret** trên nhà cung cấp xác thực, rồi cập nhật secret mới vào biến môi trường của các dịch vụ dùng nó.
- **Đã xóa notebook** khỏi nhánh hiện tại. Thông tin xác thực chỉ đi qua biến môi trường; `.env` nằm trong `.gitignore`.
- **Đã kiểm chứng:** lúc 08:51 ngày 21/10/2026, gửi yêu cầu cấp token (client credentials) tới nhà cung cấp xác thực với đúng secret lấy từ commit `8b162b3` thì bị từ chối bằng **HTTP 401 `access_denied`**. Vì vậy các commit cũ chỉ còn chứa một khóa vô hiệu, không dùng được để truy cập hệ thống.
- **Tự kiểm tra lại:** đọc secret cũ bằng `git show 8b162b3:notebooks/greennode_agentbase_test.ipynb`, rồi gửi yêu cầu cấp token với secret đó tới tenant xác thực của dự án, kết quả vẫn là 401.

Lịch sử git không bị viết lại, nên hai commit trên vẫn tồn tại; việc thu hồi khóa là biện pháp bảo vệ, không phải việc xóa commit.

## Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- A GreenNode AI Platform (MaaS) API key (`AI_PLATFORM_API_KEY`)
- A [LangSmith](https://smith.langchain.com/) account + API key (needed to
  run `mda dev` / `mda deploy`, even for local dev)

## Setup

```bash
# 1. Install the MDA CLI
uv tool install managed-deepagents

# 2. Install project dependencies
uv sync

# 3. Fill in your keys
#    edit .env and set AI_PLATFORM_API_KEY and LANGSMITH_API_KEY
```

## Testing

```bash
uv run --group dev pytest tests/ -v
```

Runs the full suite (agent config, `instructions.md` content, packaging,
`data/customer_data.json` arithmetic, `text_utils.py`) except
`tests/test_server.py` — that file needs `fastapi`/`httpx`, which are
deliberately **not** part of this project's `uv` environment (the
self-hosted server below is meant to stay isolated from
`pyproject.toml`/`uv`). `tests/conftest.py` auto-skips it here when
`fastapi` isn't importable, so the command above still runs cleanly.

To run `tests/test_server.py` itself, use a plain `pip` environment with
`requirements.txt` (same one the Docker image installs):

```bash
python -m venv .venv-server
.venv-server/Scripts/pip install -r requirements.txt pytest httpx   # Windows
# .venv-server/bin/pip install -r requirements.txt pytest httpx     # macOS/Linux

SERVER_API_KEY=test-key .venv-server/Scripts/pytest tests/test_server.py -v
```

(These tests never make a real API call, they swap in a fake model.
`SERVER_API_KEY` can be any string; it only needs to match what the tests
send back in the `X-API-Key` header. `tests/test_server.py` sets its own
`AI_PLATFORM_API_KEY`/`MEMORY_ID`/`USER_PREFERENCE_STRATEGY_ID` internally,
so you don't need to pass those.)

## Run locally

```bash
mda dev .
```

This compiles the project, loads `.env`, starts a local Agent Server, and
opens LangSmith Studio so you can chat with the agent and inspect tool
calls. Try asking: *"Tháng này tôi đã chi tiêu bao nhiêu trên thẻ?"*

## Try it in a notebook

```bash
uv sync --extra notebook
jupyter notebook notebooks/try_agent.ipynb
```

`notebooks/try_agent.ipynb` has two ways to run the agent: a quick local
invoke with the OSS `deepagents` library (no `mda` server needed), and a
call to the real managed agent via a locally running `mda dev .`.

## Self-hosted server (independent of `mda dev`)

`server.py` is a separate, independent deployment path: a plain FastAPI app
built directly on the OSS `deepagents` library (not `managed_deepagents`),
so it can run anywhere Docker runs -- no LangSmith account or `mda` CLI
needed. It shares this repo's `instructions.md`, `middleware/`, and
`skills/project/` with the main agent, but is otherwise fully isolated: it
has its own
`requirements.txt` (plain `pip`, no `uv`/`pyproject.toml` involvement) and
its own `Dockerfile`.

**Full endpoint reference for frontend integration:** see
[`docs/api.md`](docs/api.md).

**Required environment variables** (the container refuses to start without
`SERVER_API_KEY`, `MEMORY_ID`, `USER_PREFERENCE_STRATEGY_ID`, or
`AI_PLATFORM_API_KEY`):

- `AI_PLATFORM_API_KEY` -- API key for GreenNode's VNG Cloud AI Platform
  (Model-as-a-Service) endpoint, called through the chat-completions client of
  `langchain-openai` pointed at `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1`.
  Get it from the GreenNode console's API key / Model as a Service section.
- `LLM_MODEL` -- optional, model path passed to the MaaS endpoint. Defaults
  to `z-ai/glm-5.2-hackathon` if unset.
- `TINYFISH_API_KEY` -- optional at runtime. Only `tools/market_news_tools.py`
  (public Vietnamese market news from cafef.vn / vietstock.vn / tuoitre.vn, as
  background for the `investment-guidance` skill) calls TinyFish while the agent
  runs (free tier, key at agent.tinyfish.ai/api-keys; shared by every customer of a
  deployment, Search is limited to 30 requests/minute; the container needs outbound
  HTTPS to `api.search.tinyfish.ai` / `api.fetch.tinyfish.ai`). Without it the agent
  still starts; news lookups just answer "not configured". The same key is used by
  the offline MSB snapshot script below (not at request time).
- `MSB_KB_MAX_AGE_DAYS` -- optional, default 7. MSB product answers come from an
  offline snapshot of MSB's website/PDFs (`data/msb_knowledge/`, tool
  `search_msb_knowledge`): one instant local lookup, every passage carries its
  source URL and fetch date. If the snapshot is older than this many days the tool
  tells the model to state the date and send the customer to the app/advisor.
  **Refresh it on a schedule (daily is sensible) and commit the result:**
  `uv run python scripts/sync_msb_knowledge.py` (needs `TINYFISH_API_KEY` in `.env`, and
  poppler's `pdftotext` on the machine that runs it -- `apt install poppler-utils` -- so PDF
  fee/rate tables keep their columns; without it PDFs fall back to flattened text and the
  agent is told not to pair values with card names).
  Deposit-rate decisions are scanned images, so their tables are **hand-transcribed** into
  `data/msb_knowledge/curated/*.md` (never touched by the sync script, which only re-hashes
  each source PDF and flags scans nobody has reviewed -- see `curated/reviewed.json`). Have
  someone at MSB check those files against the PDFs before real use, and re-transcribe when
  MSB issues a new rate decision.
- `SERVER_API_KEY` -- shared secret; every endpoint except `GET /health`
  (`POST /chat`, `GET`/`DELETE /chat/history`, `POST /jar-rebalance`) must send
  it back in the `X-API-Key` header, or the request is rejected with 401
- `MEMORY_ID` -- id of a GreenNode AgentBase Memory resource used for both
  (a) short-term conversation history per `(thread_id, user_id)` (see
  below) and (b) long-term memory records (customer preferences). A
  long-term memory strategy can **only** be attached at creation time --
  there's no update endpoint -- so create it with the strategy included:
  ```bash
  pip install greennode-agentbase
  gab memory create -n "personal-card-agent" -e 2592000 \
    -S '{"name":"customer-preferences","type":"USER_PREFERENCE","namespaceTemplate":"actors/{actorId}"}'
  ```
  (`-e` is the event retention window **in seconds** -- 2592000 = 30 days.)
  Copy the returned `id` into `MEMORY_ID`.
- `USER_PREFERENCE_STRATEGY_ID` -- id of the `USER_PREFERENCE` long-term
  memory strategy created above (different from `MEMORY_ID` -- looks like
  `ltms-...`). Get it with `gab memory strategies list <MEMORY_ID>`. Used
  by the `remember_preference`/`recall_preference` tools (see
  `tools/memory_tools.py`) to let the agent remember durable customer facts
  (e.g. a stated budget) across threads.
- `GREENNODE_CLIENT_ID` / `GREENNODE_CLIENT_SECRET` -- IAM credentials the
  Memory client uses to authenticate. **On GreenNode AgentBase Runtime these
  are injected automatically** -- only set them yourself when running
  locally/Docker outside GreenNode. To get them: open
  `https://iam.console.greennode.ai/service-accounts` (a separate console
  from `aiplatform.console.greennode.ai` -- NOT the AgentBase "Access
  Control" page, which is unrelated to these credentials), create a
  **Service Account**. The client secret is shown **only once** at creation
  time -- copy it immediately. The client ID can be found later under that
  Service Account's **"Security credentials"** tab. `gab identity login`
  will prompt for both and cache them in `.greennode.json` (gitignored and
  dockerignored) so you don't have to export them by hand every time.
  (`GREENNODE_AGENT_IDENTITY`, which GreenNode also injects at runtime, is
  unrelated to Memory -- it's only used by the SDK's separate LLM-provider-key
  federation feature, which this server doesn't use.)

**Run locally with Docker:**

```bash
docker build -t personal-card-agent-server .
docker run -p 8080:8080 \
    -e AI_PLATFORM_API_KEY=sk-... \
    -e SERVER_API_KEY=choose-a-secret \
    -e MEMORY_ID=<memory id from gab memory create> \
    -e USER_PREFERENCE_STRATEGY_ID=<ltms-... id from gab memory strategies list> \
    -e GREENNODE_CLIENT_ID=... \
    -e GREENNODE_CLIENT_SECRET=... \
    personal-card-agent-server
```

**Endpoints:**

- `GET /health` -- no auth, returns `{"status": "ok"}`
- `POST /chat` -- requires `X-API-Key` header, body
  `{"message": str, "user_id": str, "thread_id": str | null}`, returns
  `{"answer": str, "thread_id": str}`. `thread_id` is optional -- see
  "Default thread per user" below. Errors: `401` bad/missing key, `422` missing
  fields, `500` internal error, `503` the model provider's own content filter
  rejected the model's output even after the server retried once internally
  (transient -- see `docs/api.md`), worth the frontend retrying too.
- `POST /jar-distribute` and `POST /jar-rebalance` -- require `X-API-Key` header. Jar
  proposals for screens that need no chat. `/jar-distribute`:
  `{"user_id": str, "amount": int, "jar_ids": [str] | null}` (share unallocated money
  into jars). `/jar-rebalance`:
  `{"user_id": str, "from_jar_id": str, "amount": int, "to_jar_ids": [str] | null}`
  (move balance from one jar to others). Both return `{"answer": str, "ui": {...} | null}`
  (`distribute_amount` / `rebalance_jars`); the agent is handed the jar summary and the
  last 3 months of per-jar spending, and its proposal is checked by code. No thread, no
  memory; its own agent, separate from `/chat`. Contract and error codes:
  [`docs/jars/endpoints.md`](docs/jars/endpoints.md).
- `GET /chat/history?user_id=...&thread_id=...` -- requires `X-API-Key`
  header, `thread_id` optional, returns `{"thread_id": str, "messages": [{"role": "user" | "assistant", "content": str}]}`.
  Reads straight from the same GreenNode Memory checkpointer `/chat` writes
  to (via `agent.get_state()`) -- no separate storage needed to show a past
  conversation on the UI. An unknown `(thread_id, user_id)` pair returns an
  empty `messages` list, not an error.
- `DELETE /chat/history?user_id=...&thread_id=...` -- requires `X-API-Key`
  header, `thread_id` optional, returns `{"thread_id": str, "status": "deleted"}`.
  Deletes the thread's checkpoint history via `checkpointer.delete_thread()`.
  Deletes every event even past 100 (one page) and evicts the SDK's own
  read-your-writes cache, so a `GET /chat/history` call right after a delete
  reliably returns empty -- see `checkpointer_local_cache_race.py` and
  `checkpointer_delete_pagination.py` (both patch bugs found in
  `greennode-agent-bridge`, not this server's own code; docs/incidents/
  2026-09-27-greennode-memory-*.md have the full writeups). Deletes run
  through a bounded thread pool (10-way by default), not strictly one event
  at a time -- still a single synchronous `DELETE` call, no background job;
  measured 85s -> ~12-16s on a thread of ~415 events.

**Default thread per user:** the frontend currently only sends `user_id`,
not `thread_id`. When `thread_id` is omitted on any of the three endpoints
above, it defaults to `user_id` itself (see `_default_thread_id()` in
`server.py`) -- so every user effectively has exactly one ongoing
conversation right now. Passing an explicit `thread_id` (for a future
multi-conversation-per-user UI) still works and is stored separately from
the default thread.

**Multi-user conversation history:** each `(thread_id, user_id)` pair gets
its own conversation history, persisted in GreenNode AgentBase Memory (via
`AgentBaseMemoryEvents`, a LangGraph checkpointer) instead of in-process RAM
-- history survives container restarts/redeploys and different `user_id`s
never see each other's history even if they reuse the same `thread_id`.
`user_id` is supplied by the caller (this server does not attempt to derive
it from GreenNode's injected `X-GreenNode-AgentBase-User-Id` header, since
this deployment authenticates callers via a single machine-to-machine
client rather than per-end-user tokens).

CI (`.github/workflows/docker-build.yml`) runs the server's tests, builds,
and smoke-tests the image on every push and pull request. On push to
`master` it also pushes the image to a private registry:
`vcr.vngcloud.vn/111480-abp115132/pca-agent:sha-<7-char commit sha>` and `:latest`
(pull requests build and smoke-test only, never push). Requires two repo
secrets set in GitHub (`VCR_USERNAME`, `VCR_PASSWORD`) for `docker login
vcr.vngcloud.vn`.

## Deploy

```bash
mda deploy .
```

Packages the project, syncs `instructions.md`/`skills/` to the Context Hub,
uploads, and deploys to LangSmith Agent Server. Prints a dashboard URL when
done. Tail logs with `mda logs .`, remove the deployment with `mda delete .`.

## Project layout

```
.
├── agent.py                 # define_deep_agent(): name, model, middleware
├── instructions.md          # system prompt -> synced to Context Hub on deploy
├── identity.py              # who may call the deployment (LangSmith API key by default)
├── memory.py                # durable memory (on) — customer_budgets.json lives here
├── text_utils.py             # extract_final_text() shared by notebook, script, server.py; ui-block validators (create_jar/edit_jar/rebalance_jars/distribute_amount)
├── ui_guard.py               # drops a ui whose jar/category ids are not among what the agent read this turn (server.py /chat)
├── jar_endpoint.py           # POST /jar-rebalance: jar proposals for screens with no chat (mounted by server.py)
├── jar_checks.py             # deterministic side of that endpoint: shortfall, preferred plan, hard/soft checks
├── llm.py                    # the chat model factory shared by /chat and /jar-rebalance
├── prompts/                  # read per request by jar_endpoint.py (never .dockerignore these)
│   ├── jar_rebalance.md      #   POST /jar-rebalance: one jar gives money to other jars
│   └── jar_distribute.md     #   POST /jar-distribute: unallocated money into jars
├── pyproject.toml           # dependencies + packaging (includes data/customer_data.json)
├── .env                     # AI_PLATFORM_API_KEY / LANGSMITH_API_KEY (never committed)
│
├── data/
│   └── customer_data.json   # sample customer data, re-read into every session
├── skills/
│   └── project/
│       ├── data-visualization/SKILL.md  # server.py's chart-on-demand skill (see docs/chart-visualization.md)
│       ├── spending-jar/SKILL.md        # create_jar / edit_jar / moving a category (docs/jars/create-edit-jar.md)
│       ├── distribute-amount/SKILL.md       # distribute_amount in chat: unallocated money into jars (docs/jars/distribute-amount.md)
│       ├── rebalance-jars/SKILL.md          # rebalance_jars in chat: balance from one jar to another (docs/jars/rebalance-jars.md)
│       └── transfer-form/SKILL.md       # transfer_form (docs/transfer-form.md)
├── tools/
│   ├── customer_data_tools.py  # get_jar_summary / get_categories / query_beneficiaries: live reads from the pfm backend
│   └── memory_tools.py         # remember_preference/recall_preference — server.py's long-term memory tools (not used by agent.py)
├── middleware/
│   ├── audit.py              # wrap_tool_call middleware that logs every tool call
│   ├── seed_customer_context.py  # before_agent hook that seeds /customer_data.json
│   └── seed_user_preferences.py  # before_agent hook that reads pfm's GET /api/agent-preferences ("Hướng dẫn cho M-You") into the system prompt
├── connectors/
│   └── mcp.py                # example remote MCP server declaration (not wired in by default)
├── channels/
│   └── slack.py               # Slack channel stub (needs a real Slack app to work)
├── schedules/
│   └── example.py             # daily cron-triggered run
├── sandbox/
│   └── __init__.py            # presence opts into the managed sandbox (code execution) on deploy
│
├── evals/
│   └── tasks/                 # Harbor eval tasks, incl. card-agent question checks
├── notebooks/
│   └── try_agent.ipynb        # run the agent interactively, locally or via `mda dev`
├── tests/
│   ├── conftest.py            # sys.path fix + skips test_server.py when fastapi is absent
│   └── test_server.py         # server.py's tests — see "Testing" above for how to run these
│
├── server.py                 # self-hosted FastAPI app — see "Self-hosted server" below
├── checkpointer_cache.py             # request-scoped cache around AgentBaseMemoryEvents' get_events (docs/incidents/2026-09-13-...-perf.md)
├── checkpointer_delta_snapshot.py    # stops a DeltaChannel snapshot blob from crashing every request past ~50 updates (todo.md 1.5)
├── checkpointer_local_cache_race.py  # merges AgentBaseMemoryEvents' own read-your-writes cache into every fetch instead of discarding it (docs/incidents/2026-09-27-greennode-memory-local-cache-race.md)
├── checkpointer_delete_pagination.py # fixes + parallelizes AgentBaseMemoryEvents.delete_thread() (docs/incidents/2026-09-27-greennode-memory-delete-pagination.md)
├── requirements.txt          # server.py's own pip-only dependency list (no uv/pyproject.toml)
├── Dockerfile                 # packages server.py for self-hosting
├── .dockerignore
└── .github/workflows/
    └── docker-build.yml       # test+build+smoke-test on every push/PR; push to vcr.vngcloud.vn on push to master
```

Notes:

- `connectors/mcp.py`, `channels/slack.py`, and `schedules/example.py` are
  **not** referenced from `agent.py` — they're illustrative. Wire a
  connector's tools into `agent.py`'s `tools=[...]` once you want the agent
  to actually use it.
- Delete `memory.py`, `channels/`, `schedules/`, `connectors/`, `tools/`,
  `sandbox/`, or `evals/` entirely if you don't need them — they're all
  opt-in by presence for the `mda`/`agent.py` deployment path.
  `sandbox/`'s mere presence turns on the managed code-execution sandbox at
  deploy time, whether or not anything inside it does anything.
  `tools/memory_tools.py` is a **real dependency of `server.py`** (not
  `agent.py`, which still only uses built-in filesystem tools) -- if
  `mda dev`/`mda deploy` auto-imports every file under `tools/` regardless
  of whether `agent.py` references it, this file would break that path too
  (it raises at import time without
  `MEMORY_ID`/`USER_PREFERENCE_STRATEGY_ID`/`GREENNODE_CLIENT_ID` set) --
  verify this before relying on the `mda` path again.
- `skills/project/data-visualization/SKILL.md` is a **real dependency of
  `server.py`** too (not `agent.py`, which doesn't pass `skills=[...]`) —
  `server.py`'s `build_agent()` reads it via a `CompositeBackend` that
  routes `/skills/` to a `FilesystemBackend` scoped to this directory (see
  `docs/chart-visualization.md` for what it does: lets the agent optionally
  attach a chart to analysis-style answers). Don't delete `skills/` while
  running `server.py`.
- `harbor-job.json` isn't checked in here: it's generated by
  `mda evals compile` (run automatically as part of the Harbor eval
  workflow) under `.mda/evals/`, not something you hand-write.
- Only Anthropic/OpenAI/Google's own built-in search tools and MCP
  connectors are supported for tools; Slack is the only supported channel;
  Managed Deep Agents currently runs on US LangSmith Cloud only.

## Next steps

- Add a real search tool: see the [tools guide](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)
- Add per-user auth: `identity.py` → `auth.supabase(project_ref=...)`
- Turn on shared memory: already declared in `memory.py`, just start writing
  to it from a tool or the agent's instructions
- Full CLI reference: `mda --help` or the
  [CLI docs](https://docs.langchain.com/langsmith/python/managed-deep-agents-cli)

## Sources

- [Managed Deep Agents overview](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)
- [Managed Deep Agents quickstart](https://docs.langchain.com/langsmith/python/managed-deep-agents-quickstart)
- [Managed Deep Agents CLI reference](https://docs.langchain.com/langsmith/python/managed-deep-agents-cli)
- [Managed Deep Agents identity](https://docs.langchain.com/langsmith/python/managed-deep-agents-identity)
- [Managed Deep Agents example project](https://docs.langchain.com/langsmith/managed-deep-agents-examples)
- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Deep Agents memory](https://docs.langchain.com/oss/python/deepagents/memory)
- [langchain-ai/langchain-skills — managed-deep-agents SKILL.md](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/managed-deep-agents/SKILL.md)
- [Harbor task structure](https://www.harborframework.com/docs/tasks)

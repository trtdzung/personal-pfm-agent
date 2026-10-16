# personal-card-agent — Managed Deep Agents personal card assistant

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

## Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- An OpenAI API key (the example agent uses `openai:gpt-5.5`)
- A [LangSmith](https://smith.langchain.com/) account + API key (needed to
  run `mda dev` / `mda deploy`, even for local dev)

## Setup

```bash
# 1. Install the MDA CLI
uv tool install managed-deepagents

# 2. Install project dependencies
uv sync

# 3. Fill in your keys
#    edit .env and set OPENAI_API_KEY and LANGSMITH_API_KEY
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

OPENAI_API_KEY=sk-any-value-here SERVER_API_KEY=test-key .venv-server/Scripts/pytest tests/test_server.py -v
```

(`OPENAI_API_KEY` just needs to be *present* to satisfy `ChatOpenAI`'s
constructor — these tests never make a real API call, they swap in a fake
model. `SERVER_API_KEY` can be any string; it only needs to match what the
tests send back in the `X-API-Key` header.)

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
needed. It shares this repo's `instructions.md` and `middleware/` with the
main agent, but is otherwise fully isolated: it has its own
`requirements.txt` (plain `pip`, no `uv`/`pyproject.toml` involvement) and
its own `Dockerfile`.

**Required environment variables** (the container refuses to start without
`SERVER_API_KEY`; it crash-loops on the first request without a working
`OPENAI_API_KEY`):

- `OPENAI_API_KEY` -- passed straight through to `ChatOpenAI`
- `SERVER_API_KEY` -- shared secret; every `POST /chat` request must send
  it back in the `X-API-Key` header, or the request is rejected with 401

**Run locally with Docker:**

```bash
docker build -t personal-card-agent-server .
docker run -p 8000:8000 \
    -e OPENAI_API_KEY=sk-... \
    -e SERVER_API_KEY=choose-a-secret \
    personal-card-agent-server
```

**Endpoints:**

- `GET /health` -- no auth, returns `{"status": "ok"}`
- `POST /chat` -- requires `X-API-Key` header, body
  `{"message": str, "thread_id": str | null}`, returns
  `{"answer": str, "thread_id": str}`

**Known limitation:** `thread_id` is accepted and threaded through to the
agent, but this server has no persistent memory backend wired in yet --
each request is effectively stateless regardless of `thread_id`. This is a
deliberate, documented placeholder for a future memory backend, not a bug.

CI (`.github/workflows/docker-build.yml`) runs the server's tests, builds
the image, and pushes it to `ghcr.io/<owner>/personal-card-agent` on every
push to `master` (pull requests build and smoke-test only, never push).

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
├── text_utils.py             # extract_final_text() shared by notebook, script, server.py
├── pyproject.toml           # dependencies + packaging (includes data/customer_data.json)
├── .env                     # OPENAI_API_KEY / LANGSMITH_API_KEY (never committed)
│
├── data/
│   └── customer_data.json   # sample customer data, re-read into every session
├── skills/                    # empty — no on-demand skill docs yet, ready for future ones
├── tools/                     # empty — agent uses only built-in filesystem tools, no custom ones yet
├── middleware/
│   ├── audit.py              # wrap_tool_call middleware that logs every tool call
│   └── seed_customer_context.py  # before_agent hook that seeds /customer_data.json
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
├── requirements.txt          # server.py's own pip-only dependency list (no uv/pyproject.toml)
├── Dockerfile                 # packages server.py for self-hosting
├── .dockerignore
└── .github/workflows/
    └── docker-build.yml       # test -> build -> smoke-test -> push server.py's image to GHCR
```

Notes:

- `connectors/mcp.py`, `channels/slack.py`, and `schedules/example.py` are
  **not** referenced from `agent.py` — they're illustrative. Wire a
  connector's tools into `agent.py`'s `tools=[...]` once you want the agent
  to actually use it.
- Delete `memory.py`, `channels/`, `schedules/`, `connectors/`, `tools/`,
  `skills/`, `sandbox/`, or `evals/` entirely if you don't need them —
  they're all opt-in by presence. `tools/` and `skills/` are currently
  empty on purpose (this agent only uses the built-in filesystem tools —
  see the design spec's "no hardcoded logic" constraint); `sandbox/`'s
  mere presence turns on the managed code-execution sandbox at deploy
  time, whether or not anything inside it does anything.
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

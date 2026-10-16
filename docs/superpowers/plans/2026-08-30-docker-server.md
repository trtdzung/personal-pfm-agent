# Self-hosted Docker Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-hosted FastAPI server for personal-card-agent (independent of `mda dev`/LangSmith), packaged as a Docker image, with a GitHub Actions workflow that tests, builds, and pushes it to GHCR.

**Architecture:** `server.py` builds the agent once at import time via `deepagents.create_deep_agent` (the same OSS path notebooks/try_agent.ipynb's Option A already uses — reusing `instructions.md` and `middleware/`), exposes it through `POST /chat` (API-key-gated) and `GET /health` (unauthenticated). Dependencies for this component live in a standalone `requirements.txt` installed with plain `pip`, kept entirely separate from `pyproject.toml`/`uv.lock` (which continue to serve `agent.py`/`mda dev`/`mda deploy` unchanged). A shared `text_utils.py` replaces the `extract_final_text()` duplicated across the notebook and `scripts/verify_agent.py`.

**Tech Stack:** FastAPI 0.141.1, Uvicorn 0.52.4, `deepagents` 0.7.11, `langchain-openai` 1.6.0, `python-dotenv` 1.2.3, plain `pip` (no `uv`), Docker, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-30-docker-server-design.md`

## Global Constraints

- No `MemorySaver`/in-process RAM checkpointer in `server.py` — `thread_id` is accepted in the API request and threaded into the LangGraph `config`, but has no persistence effect yet (documented, not implemented in this plan).
- `requirements.txt` + plain `pip` only for this component — never `uv`, never add anything to `pyproject.toml`. `pyproject.toml`/`uv.lock`/`agent.py`/`mda dev`/`mda deploy` are untouched by every task in this plan.
- `SERVER_API_KEY` must never be baked into the Docker image; the server must refuse to start if it's unset.
- **Never run `git commit`.** Every task ends with `git add` (staging) only — leave changes staged for the user to commit themselves. Do not run `git commit` under any circumstances, including as part of a "Commit" step template from another skill.

---

## Task 1: `text_utils.py` — shared `extract_final_text()`, dedupe from notebook + script

**Files:**
- Create: `text_utils.py`
- Modify: `notebooks/try_agent.ipynb` (cell 1 — remove the inline `extract_final_text` definition, import from `text_utils` instead)
- Modify: `scripts/verify_agent.py` (remove the inline `extract_final_text` definition, import from `text_utils` instead)
- Test: `tests/test_text_utils.py`

**Interfaces:**
- Produces: `text_utils.extract_final_text(content: object) -> str`, imported by Task 3's `server.py`, and by the modified notebook/script.

- [ ] **Step 1: Write the failing test**

Create `tests/test_text_utils.py`:

```python
from text_utils import extract_final_text


def test_extract_final_text_returns_plain_string_unchanged():
    assert extract_final_text("hello") == "hello"


def test_extract_final_text_pulls_text_blocks_from_reasoning_model_output():
    content = [
        {
            "id": "rs_abc",
            "type": "reasoning",
            "summary": [],
            "content": [],
            "encrypted_content": "gAAAAA...",
        },
        {
            "type": "text",
            "text": "Câu trả lời cuối cùng.",
            "annotations": [],
            "id": "msg_xyz",
            "phase": "final_answer",
        },
    ]
    assert extract_final_text(content) == "Câu trả lời cuối cùng."


def test_extract_final_text_joins_multiple_text_blocks():
    content = [
        {"type": "text", "text": "Phần 1."},
        {"type": "text", "text": "Phần 2."},
    ]
    assert extract_final_text(content) == "Phần 1.\nPhần 2."


def test_extract_final_text_falls_back_to_str_for_unrecognized_shape():
    assert extract_final_text(42) == "42"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group dev pytest tests/test_text_utils.py -v`
Expected: FAIL — `text_utils` module does not exist yet.

- [ ] **Step 3: Create `text_utils.py`**

```python
def extract_final_text(content: object) -> str:
    """Pull just the final answer text out of a message's content.

    Reasoning-capable models (e.g. gpt-5.5) return content as a list of
    blocks (reasoning + text) instead of a plain string -- this returns
    only the text block(s), not the raw list with reasoning/ids/etc.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if texts:
            return "\n".join(texts)
    return str(content)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group dev pytest tests/test_text_utils.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Update the notebook to import from `text_utils`**

The notebook currently defines `extract_final_text` inline at the end of
its setup cell (cell index 1, right after the `OPENAI_API_KEY` assert).
Using Python to edit it precisely (it's JSON, so string-replace the cell's
`source` list rather than hand-editing the file):

```bash
uv run python - <<'PYEOF'
import json

path = "notebooks/try_agent.ipynb"
nb = json.load(open(path, encoding="utf-8"))

MARKER = "\ndef extract_final_text(content) -> str:"

for cell in nb["cells"]:
    if cell["cell_type"] != "code":
        continue
    src = "".join(cell["source"])
    if MARKER in src:
        head = src.split(MARKER)[0].rstrip("\n")
        new_src = head + "\n\nfrom text_utils import extract_final_text\n"
        cell["source"] = new_src.splitlines(keepends=True)
        cell["outputs"] = []
        cell["execution_count"] = None
        break
else:
    raise SystemExit("expected cell containing extract_final_text definition not found")

json.dump(nb, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
with open(path, "a", encoding="utf-8") as f:
    f.write("\n")
print("done")
PYEOF
```

- [ ] **Step 6: Verify the notebook is still valid and every cell parses**

```bash
uv run python -c "
import json, ast
nb = json.load(open('notebooks/try_agent.ipynb', encoding='utf-8'))
assert len(nb['cells']) == 8, len(nb['cells'])
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        ast.parse(src)
        if i == 1:
            assert 'from text_utils import extract_final_text' in src, src
            assert 'def extract_final_text' not in src, 'inline definition should be gone'
print('OK')
"
```

Expected: prints `OK`, exit code 0.

- [ ] **Step 7: Update `scripts/verify_agent.py` to import from `text_utils`**

In `scripts/verify_agent.py`, delete the inline `def extract_final_text(...)`
function body (currently sits between `THREAD_CONFIG = ...` and
`def build_agent():`), and add the import alongside the other local imports
near the top of the file:

```python
from middleware.audit import log_tool_calls  # noqa: E402
from middleware.seed_customer_context import SeedCustomerContext  # noqa: E402
from text_utils import extract_final_text  # noqa: E402
```

(`REPO_ROOT` is already inserted into `sys.path` earlier in the file, so
`text_utils` resolves the same way `middleware` already does.)

- [ ] **Step 8: Verify the script still compiles and has no duplicate definition**

```bash
uv run python -m py_compile scripts/verify_agent.py
uv run python -c "
src = open('scripts/verify_agent.py', encoding='utf-8').read()
assert 'from text_utils import extract_final_text' in src
assert 'def extract_final_text' not in src
print('OK')
"
```

Expected: both commands succeed, prints `OK`.

- [ ] **Step 9: Run the full existing test suite to confirm nothing broke**

Run: `uv run --group dev pytest tests/ -v`
Expected: all tests pass — 19 tests existed before this task, this task adds
4 more (`tests/test_text_utils.py`), so 23 total should pass, 0 failures.

- [ ] **Step 10: Stage changes (do NOT commit)**

```bash
git add text_utils.py tests/test_text_utils.py notebooks/try_agent.ipynb scripts/verify_agent.py
git status
```

Leave staged. Do not run `git commit` — only the user commits in this repo.

---

## Task 2: `requirements.txt` for the standalone server component

**Files:**
- Create: `requirements.txt`
- Test: manual verification (Step 2 below) — no pytest file, this task has no importable code yet

**Interfaces:**
- Produces: `requirements.txt` at repo root, listing exactly the runtime dependencies `server.py` (Task 3) needs. Task 3 and Task 4 (Dockerfile) both read this file's exact contents.

- [ ] **Step 1: Create `requirements.txt`**

```
deepagents==0.7.11
langchain-openai==1.6.0
python-dotenv==1.2.3
fastapi==0.141.1
uvicorn==0.52.4
```

- [ ] **Step 2: Verify it installs cleanly with plain pip (not uv) in a scratch venv**

This project's own environment is `uv`-managed and has no `pip` binary in
its `.venv`, so verify against the system Python instead — the point is to
prove `requirements.txt` works with plain `pip`, independent of `uv`:

```bash
"/c/Program Files/Python312/python.exe" -m venv /tmp/server-reqs-check
/tmp/server-reqs-check/Scripts/python.exe -m pip install --quiet -r requirements.txt
/tmp/server-reqs-check/Scripts/python.exe -c "
import deepagents, langchain_openai, dotenv, fastapi, uvicorn
print('OK: all 5 packages import successfully via plain pip')
"
rm -rf /tmp/server-reqs-check
```

Expected: prints `OK: all 5 packages import successfully via plain pip`,
exit code 0. If pip reports a dependency conflict, that's a real finding —
report it rather than loosening version pins arbitrarily; check what
version deepagents/langchain-openai/fastapi actually require of each other
and adjust the specific conflicting pin.

- [ ] **Step 3: Stage changes (do NOT commit)**

```bash
git add requirements.txt
git status
```

Leave staged. Do not run `git commit`.

---

## Task 3: `server.py` — FastAPI app (`POST /chat`, `GET /health`)

**Files:**
- Create: `server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `text_utils.extract_final_text` (Task 1), `middleware.audit.log_tool_calls`, `middleware.seed_customer_context.SeedCustomerContext` (both pre-existing, unchanged), `instructions.md` (pre-existing, unchanged), `requirements.txt` (Task 2 — `server.py` only imports packages listed there plus stdlib).
- Produces: a FastAPI `app` object (module-level `app = FastAPI()` in `server.py`) with routes `POST /chat` and `GET /health`, importable as `from server import app`. Task 4 (Dockerfile) runs it via `uvicorn server:app`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_server.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

os.environ.setdefault("SERVER_API_KEY", "test-key-for-pytest")

import server  # noqa: E402


def test_health_endpoint_requires_no_auth():
    client = TestClient(server.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_rejects_missing_api_key():
    client = TestClient(server.app)
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401


def test_chat_endpoint_rejects_wrong_api_key():
    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_chat_endpoint_returns_answer_with_correct_api_key(monkeypatch):
    fake_model = FakeListChatModel(responses=["Đây là câu trả lời giả."])
    fake_agent = server.build_agent(model=fake_model)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "Tháng này tôi đã chi tiêu bao nhiêu?", "thread_id": "t1"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Đây là câu trả lời giả."
    assert body["thread_id"] == "t1"


def test_chat_endpoint_generates_thread_id_when_omitted(monkeypatch):
    fake_model = FakeListChatModel(responses=["ok"])
    fake_agent = server.build_agent(model=fake_model)
    monkeypatch.setattr(server, "agent", fake_agent)

    client = TestClient(server.app)
    response = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"X-API-Key": "test-key-for-pytest"},
    )
    assert response.status_code == 200
    assert response.json()["thread_id"]  # non-empty, some generated id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --group dev pytest tests/test_server.py -v`

(This test file needs `fastapi`, `httpx` (FastAPI's `TestClient` dependency),
and `deepagents` available — all already installed in this project's `uv`
environment from earlier work in this repo, so `uv run --group dev pytest`
picks them up without needing `requirements.txt`/pip at all here; only the
Docker image itself uses plain pip, per the Global Constraints.)

Expected: FAIL — `server.py` does not exist yet (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `server.py`**

```python
import os
import uuid
from pathlib import Path

from deepagents import create_deep_agent
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from middleware.audit import log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext
from text_utils import extract_final_text

REPO_ROOT = Path(__file__).resolve().parent

SERVER_API_KEY = os.environ.get("SERVER_API_KEY")
if not SERVER_API_KEY:
    raise RuntimeError(
        "SERVER_API_KEY is not set. Refusing to start without an API key "
        "configured -- this server would otherwise serve customer "
        "financial data with no authentication."
    )


def build_agent(model: object = "openai:gpt-5.5"):
    instructions = (REPO_ROOT / "instructions.md").read_text(encoding="utf-8")
    return create_deep_agent(
        model=model,
        tools=[],
        middleware=[log_tool_calls, SeedCustomerContext()],
        system_prompt=instructions,
    )


agent = build_agent()

app = FastAPI(title="personal-card-agent (self-hosted)")


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    x_api_key: str | None = Header(default=None),
) -> ChatResponse:
    if x_api_key != SERVER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

    thread_id = request.thread_id or str(uuid.uuid4())
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": request.message}]},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:  # noqa: BLE001 -- deliberately generic: never leak internals
        raise HTTPException(status_code=500, detail="Agent failed to process the request") from exc

    answer = extract_final_text(result["messages"][-1].content)
    return ChatResponse(answer=answer, thread_id=thread_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --group dev pytest tests/test_server.py -v`
Expected: PASS (5 tests). No real OpenAI API call is made — module-level
`agent = build_agent()` does build a real `openai:gpt-5.5`-backed agent at
import time (this requires `OPENAI_API_KEY` to be set, matching how
`test_agent_module_imports_without_error` already behaves for `agent.py` —
if `.env` isn't loaded in the test environment, set a dummy
`OPENAI_API_KEY=sk-test-dummy` env var before running these tests; a dummy
value satisfies `ChatOpenAI`'s "is a key present" check without making any
network call, since none of these 5 tests actually invoke that module-level
`agent` — the 4 chat tests all monkeypatch `server.agent` to a
`FakeListChatModel`-backed one first).

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `uv run --group dev pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 6: Stage changes (do NOT commit)**

```bash
git add server.py tests/test_server.py
git status
```

Leave staged. Do not run `git commit`.

---

## Task 4: `Dockerfile` + `.dockerignore`

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `requirements.txt` (Task 2), `server.py`, `text_utils.py` (Task 1/3), `instructions.md`, `middleware/`, `data/customer_data.json` (all pre-existing, unchanged).
- Produces: a buildable Docker image exposing port 8000. Task 5's CI workflow builds and pushes this image.

- [ ] **Step 1: Create `.dockerignore`**

```
.venv/
.git/
__pycache__/
*.pyc
.env
notebooks/
evals/
.superpowers/
docs/
tests/
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py text_utils.py instructions.md ./
COPY middleware/ ./middleware/
COPY data/ ./data/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Build the image locally to verify the Dockerfile is correct**

```bash
docker build -t personal-card-agent-server:local .
```

Expected: build succeeds, exit code 0. **If this fails with something like
"cannot connect to the Docker daemon" / "dockerDesktopLinuxEngine" pipe
error**, Docker Desktop is installed but not running on this machine —
start Docker Desktop first (or ask the user to), then retry this step. Do
not skip this verification; a Dockerfile that has never actually been built
is unverified, not done.

- [ ] **Step 4: Smoke-test the built image**

```bash
docker run -d --name pca-server-smoketest -p 18000:8000 \
    -e OPENAI_API_KEY=sk-smoketest-dummy \
    -e SERVER_API_KEY=smoketest-key \
    personal-card-agent-server:local
sleep 3
curl -f http://localhost:18000/health
echo "exit code: $?"
docker logs pca-server-smoketest
docker rm -f pca-server-smoketest
```

Expected: `curl` prints `{"status":"ok"}` and exit code 0. The dummy
`OPENAI_API_KEY` is sufficient because `/health` never touches the agent —
this only proves the container starts and the dependency set installed via
`requirements.txt` is actually sufficient to import and run `server.py`
(the same class of gap the earlier missing-`langchain-openai` bug in this
project's notebook/script was — verify it for real here too, don't assume).

- [ ] **Step 5: Stage changes (do NOT commit)**

```bash
git add Dockerfile .dockerignore
git status
```

Leave staged. Do not run `git commit`.

---

## Task 5: GitHub Actions workflow — test, build, push to GHCR

**Files:**
- Create: `.github/workflows/docker-build.yml`

**Interfaces:**
- Consumes: `requirements.txt` (Task 2), `tests/test_server.py` (Task 3), `Dockerfile` (Task 4). This is the plan's final task — nothing depends on its output.

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/docker-build.yml`:

```yaml
name: docker-build

on:
  push:
    branches: [master]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install server dependencies + test deps
        run: pip install -r requirements.txt pytest httpx
      - name: Run server tests
        env:
          OPENAI_API_KEY: sk-ci-dummy
        run: pytest tests/test_server.py tests/test_text_utils.py -v

  build:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Compute image tags
        id: tags
        run: |
          SHA_TAG="ghcr.io/${{ github.repository_owner }}/personal-card-agent:sha-$(echo ${{ github.sha }} | cut -c1-7)"
          echo "sha_tag=$SHA_TAG" >> "$GITHUB_OUTPUT"
      - name: Build image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: false
          load: true
          tags: ${{ steps.tags.outputs.sha_tag }}
      - name: Smoke test image
        run: |
          docker run -d --name smoketest -p 18000:8000 \
            -e OPENAI_API_KEY=sk-ci-dummy \
            -e SERVER_API_KEY=ci-dummy \
            ${{ steps.tags.outputs.sha_tag }}
          sleep 3
          curl -f http://localhost:18000/health
          docker rm -f smoketest
      - name: Push image
        if: github.event_name != 'pull_request'
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ${{ steps.tags.outputs.sha_tag }}
            ghcr.io/${{ github.repository_owner }}/personal-card-agent:latest
```

- [ ] **Step 2: Validate the YAML is well-formed**

```bash
uv run python -c "
import yaml
with open('.github/workflows/docker-build.yml', encoding='utf-8') as f:
    doc = yaml.safe_load(f)
assert 'jobs' in doc and 'test' in doc['jobs'] and 'build' in doc['jobs']
print('OK: valid YAML with test + build jobs')
"
```

(`pyyaml` is already available in this project's `uv` environment —
confirmed installed as a transitive dependency, `uv run python -c "import
yaml; print(yaml.__version__)"` prints `6.0.3` — no new dependency needed for
this check.)

Expected: prints `OK: valid YAML with test + build jobs`, exit code 0.

- [ ] **Step 3: Stage changes (do NOT commit)**

```bash
git add .github/workflows/docker-build.yml
git status
```

Leave staged. Do not run `git commit` — this is the plan's last task; once
staged, tell the user everything is ready for them to review and commit
themselves.

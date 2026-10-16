# Self-hosted HTTP server + Docker + CI/CD — Design

**Ngày:** 2026-08-30
**Trạng thái:** Đã thống nhất qua brainstorming, chờ chuyển sang implementation plan.

## 1. Bối cảnh & mục tiêu

`agent.py` deploy qua `managed_deepagents.define_deep_agent`, chạy trên hạ
tầng LangSmith Agent Server (`mda dev`/`mda deploy`) — không tự host được ở
nơi khác. Mục tiêu thiết kế này: thêm một **đường triển khai độc lập, tự
host** (Docker + HTTP server riêng), dùng cùng `instructions.md` và
`middleware/` như agent thật, nhưng build agent bằng OSS
`deepagents.create_deep_agent` (giống notebook Option A) thay vì
`managed_deepagents.define_deep_agent` — vì chỉ cách này chạy được ngoài hạ
tầng LangSmith.

**Ràng buộc cứng từ người dùng:**
- Không dùng `MemorySaver`/RAM trong container để nhớ hội thoại nhiều lượt —
  chấp nhận chưa nhớ được gì ở bản này; API vẫn nhận `thread_id` để tương
  thích khi cắm memory backend thật vào sau.
- Không dùng `uv`/`pyproject.toml` cho phần server/Docker này — dùng
  `requirements.txt` + `pip` thuần, **tách biệt hoàn toàn** khỏi
  `pyproject.toml`/`uv.lock` hiện có (phần đó vẫn phục vụ `agent.py` +
  `mda dev`/`mda deploy`, không được đụng vào).

## 2. Kiến trúc tổng quan

```
requirements.txt         # MỚI — chỉ cho server.py/Docker, KHÔNG liên quan pyproject.toml
text_utils.py             # MỚI — extract_final_text() dùng chung (notebook, script, server)
server.py                 # MỚI — FastAPI app
Dockerfile                 # MỚI
.dockerignore               # MỚI
.github/workflows/
  docker-build.yml          # MỚI — test -> build -> push GHCR
tests/
  test_server.py             # MỚI
notebooks/try_agent.ipynb    # SỬA — import extract_final_text từ text_utils.py thay vì định nghĩa lại
scripts/verify_agent.py      # SỬA — import extract_final_text từ text_utils.py thay vì định nghĩa lại
```

`pyproject.toml`, `uv.lock`, `agent.py`, `instructions.md`, `middleware/`,
`data/customer_data.json`, mọi test hiện có — **không đổi gì** (chỉ đọc/import,
không sửa nội dung nghiệp vụ).

## 3. `text_utils.py` — dọn trùng lặp

`extract_final_text()` hiện bị lặp y hệt ở notebook cell 1 và
`scripts/verify_agent.py` (thêm bản thứ 3 cho server sẽ là lần lặp thứ 3).
Tách thành module dùng chung ở root:

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

Notebook và `scripts/verify_agent.py` đổi sang `from text_utils import
extract_final_text` (cả hai đã tự chèn `REPO_ROOT`/`sys.path` vào path rồi,
import thẳng được).

## 4. `server.py` — FastAPI app

- Build agent **1 lần lúc import module** (không phải mỗi request): dùng
  `deepagents.create_deep_agent(model="openai:gpt-5.5", tools=[],
  middleware=[log_tool_calls, SeedCustomerContext()], system_prompt=<nội
  dung instructions.md>)` — **không truyền `checkpointer`** (đúng ràng buộc
  không RAM).
- `POST /chat`:
  - Header bắt buộc: `X-API-Key`, phải khớp biến môi trường
    `SERVER_API_KEY` — sai/thiếu → `401`. Nếu `SERVER_API_KEY` không được
    set khi khởi động server, **server từ chối khởi động** (raise ngay, fail
    fast) — tránh vô tình chạy không auth.
  - Body: `{"message": str, "thread_id": str | null}`. `thread_id` được
    truyền vào `config={"configurable": {"thread_id": thread_id or
    <uuid4 mới>}}` khi gọi `.invoke()` — hiện tại không có checkpointer nên
    giá trị này không có tác dụng nhớ lịch sử, nhưng đã có mặt trong contract
    để sau này cắm checkpointer/memory backend vào không cần đổi API.
  - Response: `{"answer": str, "thread_id": str}` — `answer` là
    `extract_final_text(result["messages"][-1].content)`.
  - Lỗi từ agent (exception khi `.invoke()`) → `500` kèm message chung
    chung (không leak traceback/nội dung lỗi thô ra ngoài — đây là agent xử
    lý dữ liệu tài chính, không expose chi tiết nội bộ).
- `GET /health`: không auth, không đụng tới agent, trả `{"status": "ok"}`
  ngay lập tức — dùng cho Docker `HEALTHCHECK` và smoke test CI.

## 5. `requirements.txt`

```
deepagents==0.7.11
langchain-openai==1.6.0
python-dotenv==1.2.3
fastapi==0.141.1
uvicorn==0.52.4
```

Version pin theo đúng bản đã test thật trong quá trình làm việc trước đó
(`deepagents`, `langchain-openai`, `python-dotenv` đã invoke thật; `fastapi`/
`uvicorn` resolve qua `uv pip install --dry-run` ngay trước khi viết spec
này). Dependency transitive (`langchain`, `langgraph`, `starlette`,
`click`,...) để `pip` tự resolve, không pin thủ công.

## 6. Dockerfile & `.dockerignore`

- Base `python:3.12-slim`.
- `COPY requirements.txt .` trước, `pip install --no-cache-dir -r
  requirements.txt`, rồi mới `COPY` code còn lại (cache layer tốt khi chỉ sửa
  code, không sửa dependency).
- Chỉ copy đúng những gì `server.py` cần chạy: `server.py`, `text_utils.py`,
  `instructions.md`, `middleware/`, `data/customer_data.json`. **Không copy**
  `agent.py`, `pyproject.toml`, `uv.lock`, `identity.py`, `memory.py` (thuộc
  về đường `mda deploy`, không liên quan container này).
- `EXPOSE 8000`, `HEALTHCHECK` gọi `GET /health`.
- `CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]`.
- Không set `OPENAI_API_KEY`/`SERVER_API_KEY` trong image — bắt buộc truyền
  lúc `docker run`/CI.
- `.dockerignore`: `.venv/`, `.git/`, `__pycache__/`, `.env`, `notebooks/`,
  `evals/`, `.superpowers/`, `docs/`, `tests/`.

## 7. Testing — `tests/test_server.py`

- Test 401 khi thiếu/sai `X-API-Key` — không cần agent thật (FastAPI
  dependency chặn trước khi chạm vào agent).
- Test luồng thành công dùng
  `langchain_core.language_models.fake_chat_models.FakeListChatModel` (đã
  dùng để inspect agent trước đó, xác nhận hoạt động) làm model giả — build
  agent test riêng (không phải agent module-level thật của `server.py`,
  tránh gọi `openai:gpt-5.5` thật), verify response `200` đúng shape
  `{"answer": ..., "thread_id": ...}`.
- Test `GET /health` trả `200` không cần header.
- Không tốn API thật ở bất kỳ test nào trong file này.

## 8. GitHub Actions — `.github/workflows/docker-build.yml`

- Trigger: `push` vào `master`, và `pull_request`.
- **Job `test`**: checkout, setup Python 3.12, `pip install -r
  requirements.txt pytest httpx` (`httpx` cần cho FastAPI `TestClient`), chạy
  `pytest tests/test_server.py -v`. (Job này **không** đụng tới
  `pyproject.toml`/`uv` — độc lập hoàn toàn với bộ test hiện có của
  `agent.py`, vốn vẫn chạy qua `uv run --group dev pytest tests/` như cũ,
  không nằm trong workflow mới này trừ khi người dùng muốn gộp sau.)
- **Job `build`** (needs: `test`): `docker/build-push-action`, login GHCR
  bằng `GITHUB_TOKEN` có sẵn (không cần secret riêng). Tag
  `ghcr.io/<owner>/personal-card-agent:sha-<short-sha>` luôn; tag `:latest`
  **chỉ** khi trigger là push vào `master` (không tag `:latest` từ PR). PR
  chỉ build, không push.
- **Smoke test** (trong job `build`, sau khi build xong): `docker run -d -p
  8000:8000 -e OPENAI_API_KEY=sk-ci-dummy -e SERVER_API_KEY=ci-dummy
  <image>`, đợi vài giây, `curl -f http://localhost:8000/health`, dừng
  container. Xác nhận image thật sự khởi động được (bắt lỗi thiếu
  dependency khi đóng gói) mà không cần OpenAI key thật (key giả đủ để qua
  bước validate "có key" của `ChatOpenAI`, không gọi network thật vì
  `/health` không đụng model).

## 9. Non-goals (ghi rõ, không làm trong phạm vi này)

- Bộ nhớ hội thoại nhiều lượt thật (checkpointer/memory backend bền vững) —
  API đã có `thread_id` sẵn sàng, nhưng chưa cắm gì vào. Việc của tương lai
  theo đúng ý người dùng ("sau này sẽ dùng Memory riêng").
- Streaming response — `POST /chat` trả nguyên câu trả lời cuối, không
  stream từng token.
- Đa khách hàng thật (multi-tenant) — vẫn 1 `data/customer_data.json` tĩnh
  như agent chính, đã ghi trong `todo.md` mục 1.1.
- Gộp workflow CI mới với việc chạy `uv run pytest tests/` của bộ test hiện
  có — 2 workflow độc lập, không tự động gộp trong lần này.

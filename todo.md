# TODO — personal-card-agent

Trạng thái: 7 task của plan + final review đã xong (commit `b6c805d`), sau đó
sửa thêm 3 bug phát hiện khi chạy thật (`2d530f7`, `8a1db02`, `e714bee`).
Danh sách dưới đây là những việc **còn lại**, ưu tiên theo mức độ quan trọng.

## 1. Kiến trúc còn thiếu — chưa giải quyết, cần quyết định hướng đi

### 1.1. Đa người dùng (multi-customer)
- `identity.py` hiện chỉ xác thực bằng **1 LangSmith API key dùng chung cho cả
  workspace** (`auth.langsmith_api_key()`) — không có khái niệm "khách hàng A"
  khác "khách hàng B" ở tầng xác thực.
- `data/customer_data.json` là **1 file tĩnh duy nhất** — muốn nhiều khách
  hàng thật cần: (a) nguồn dữ liệu theo từng `customer_id` (DB/API thay vì 1
  file JSON), (b) `SeedCustomerContext` đọc đúng dữ liệu của khách hàng đang
  chat (cần biết "đang chat với ai" — phụ thuộc việc xác thực ở mục trên).
- **Việc cần làm:** đổi `identity.py` sang `auth.supabase(...)` (README đã gợi
  ý) hoặc cơ chế xác thực theo người dùng thật; thiết kế lại nguồn dữ liệu
  khách hàng theo `customer_id`.

### 1.2. Lịch sử hội thoại ngắn hạn (trong 1 phiên chat)
- `agent.py` (agent **thật**, deploy qua `managed_deepagents.define_deep_agent`)
  **không có checkpointer** — đã xác nhận `define_deep_agent` không nhận tham
  số này. Đang **phó mặc hoàn toàn cho checkpoint mặc định của nền tảng
  LangSmith Agent Server**, chưa từng verify nền tảng đó có thực sự giữ được
  lịch sử hội thoại qua nhiều lượt trong 1 thread hay không.
- `scripts/verify_agent.py` và notebook chỉ dùng `MemorySaver()` **cục bộ**
  (khác hoàn toàn với agent thật) để tự test — không phản ánh hành vi thật khi
  deploy.
- **Việc cần làm:** chạy `mda dev .`, mở 1 thread trong Studio, hỏi nhiều lượt
  liên tiếp (đặc biệt câu hỏi ngân sách 2 lượt: nói ngân sách → hỏi lại), xác
  nhận agent thật có nhớ được trong cùng thread không. Nếu không, cần tìm cách
  khác để khai báo checkpointer cho `define_deep_agent` (báo lỗi/hỏi
  LangChain, hoặc chờ version mới của `managed-deepagents`).

### 1.3. Bộ nhớ ngân sách dùng chung 1 file (`/memories/agent/customer_budgets.json`)
- `define_memory` chỉ hỗ trợ `scope="agent"` (1 file bền vững **dùng chung
  cho mọi người gọi deployment**) — không có cô lập theo người dùng ở tầng
  framework.
- Thiết kế hiện tại: agent tự khoá theo `customer_id` trong nội dung file
  (dict `{customer_id: {...}}`), dựa hoàn toàn vào việc `instructions.md`
  "nhắc" agent làm đúng — **không có gì ở tầng code/framework ép buộc** điều
  này, chỉ dựa vào agent tuân theo prompt.
- **Việc cần làm:** khi có khách hàng thứ 2 thật, kiểm tra kỹ agent có thực
  sự chỉ đọc/ghi đúng entry của mình không (rủi ro: agent đọc nhầm/ghi đè
  ngân sách của khách khác nếu prompt injection hoặc model không tuân thủ).

### 1.4. Checkpointer bền vững cho production
- `MemorySaver()` (nếu dùng được — xem 1.2) chỉ lưu trong RAM, mất khi
  restart process. Chưa chọn checkpointer bền vững (Postgres-backed hay
  tương đương) cho môi trường production thật.

## 2. Chưa được verify bằng cách chạy thật — cần làm trước khi tin tưởng agent

- [ ] Chạy đủ **11 câu hỏi** trong
  `docs/superpowers/plans/2026-08-30-personal-card-agent-verification.md`,
  điền kết quả PASS/FAIL vào bảng (mới test tay 2 câu ngoài checklist: tổng
  chi tiêu tháng 8, giao dịch lớn nhất tuần — cả 2 đều đúng).
- [ ] **Row 10 (ngân sách nhớ được qua thread MỚI)** — chỉ test được qua
  `mda dev .` + Studio thật, chưa làm lần nào. Đây là phép thử duy nhất xác
  nhận `/memories/agent/customer_budgets.json` hoạt động đúng như thiết kế.
- [ ] **Chưa từng chạy `agent.py` thật qua `mda dev .`** — toàn bộ việc test
  đến giờ đều qua `deepagents.create_deep_agent` cục bộ (Option A trong
  notebook), KHÔNG phải qua `managed_deepagents.define_deep_agent` (Option B,
  agent thật sẽ deploy). Rủi ro: bug sync/async vừa sửa (`8a1db02`) được phát
  hiện và fix trên đường Option A — chưa xác nhận Option B (nền tảng thật) có
  gặp vấn đề tương tự hay không.
- [ ] 2 Harbor eval task (`evals/tasks/spending-total-question`,
  `evals/tasks/large-transactions-question`) mới verify cấu trúc bằng tay
  (viết `answer.md` giả), **chưa từng chạy qua Harbor/`mda evals` thật**. Cả 2
  Task.md đã ghi chú nghi ngờ: xoá `sandbox/` có thể khiến agent không có
  filesystem thật để ghi `answer.md` cho Harbor chấm — chưa xác nhận đúng/sai.

## 3. Việc nhỏ còn treo (đã ghi nhận, không chặn, làm khi rảnh)

- [ ] `data/customer_data.json`'s `_meta.as_of_date` sẽ tiếp tục lệch ngày
  thật mỗi lần demo — cân nhắc cập nhật định kỳ hoặc bỏ trường này.
- [ ] `README.md` còn 2 dòng cũ chưa dọn (mục Deploy nhắc `skills/`, mục Next
  steps có link "tools guide") — tham chiếu khái niệm đã xoá.
- [ ] `pyproject.toml` gói `data/customer_data.json` vào `site-packages/data/`
  — tên thư mục không có namespace riêng, có thể đụng độ nếu sau này thêm
  package khác cũng dùng tên `data`.
- [ ] `SeedCustomerContext.before_agent`/`abefore_agent` không bắt lỗi khi
  `data/customer_data.json` thiếu/hỏng — hiện fail loud (traceback thô), có
  thể bọc lại thành thông báo rõ ràng hơn.
- [ ] `middleware/audit.py` (`LogToolCalls`, vừa sửa thành class có cả sync +
  async) **chưa có unit test nào** — khác với `SeedCustomerContext` đã có
  test cho cả 2 đường sync/async. Nên thêm `tests/middleware/test_audit.py`
  để tránh tái diễn kiểu bug vừa gặp (chỉ phát hiện khi chạy thật).

## 4. Việc người dùng tự quyết định

- [ ] `git push` lên `origin/master` (https://github.com/Daonguyen2401/personal-card-agent.git)
  — hiện toàn bộ commit vẫn chỉ ở local theo lựa chọn của bạn.

## 5. Đóng gói Docker & CI/CD

- [ ] **Quyết định trước khi viết Dockerfile:** dự án này dùng `mda dev`/
  `mda deploy` (LangSmith Agent Server hosted — không tự chạy server). Muốn
  container hoá cần chọn: (a) container chỉ để chạy `mda dev .` bên trong
  (phục vụ demo/dev cục bộ), hay (b) tự viết một entrypoint HTTP riêng (vd
  FastAPI/uvicorn gọi `deepagents.create_deep_agent` như notebook Option A)
  để không phụ thuộc hạ tầng LangSmith khi tự host. Ảnh hưởng trực tiếp đến
  nội dung Dockerfile và mục đích của image.
- [ ] Viết `Dockerfile`: base image Python (khớp `requires-python = ">=3.11"`
  trong `pyproject.toml`), cài `uv`, `uv sync` (không cài `notebook`/`dev`
  extra trong image production), copy `agent.py`, `instructions.md`,
  `middleware/`, `data/customer_data.json`, `memory.py`, `identity.py`.
  **Không bake `OPENAI_API_KEY`/`LANGSMITH_API_KEY` vào image** — inject qua
  biến môi trường lúc chạy container.
- [ ] Thêm `.dockerignore` (loại `.venv/`, `__pycache__/`, `.git/`, `.env`,
  `notebooks/`, `evals/`, `.superpowers/`).
- [ ] Viết GitHub Actions workflow (`.github/workflows/docker-build.yml`):
  - Trigger: push lên `master` + trên pull request (build-only, không push
    image khi là PR).
  - Build image bằng `docker/build-push-action`, cache layer `uv` để build
    nhanh hơn giữa các lần chạy.
  - Chạy `uv run --group dev pytest tests/ -v` trong bước CI **trước khi**
    build image — chặn build nếu test đỏ.
  - Đẩy image lên registry (GHCR `ghcr.io/<owner>/personal-card-agent` là lựa
    chọn mặc định đơn giản nhất vì dùng chung quyền với repo, không cần
    secret riêng — Docker Hub cần thêm `DOCKERHUB_TOKEN` secret nếu chọn).
  - Gắn tag theo commit SHA + `latest` (hoặc theo git tag nếu về sau dùng
    release theo version).
  - Cân nhắc thêm bước smoke test: `docker run` image vừa build, xác nhận
    import `agent` module không lỗi (giống `tests/test_agent.py`'s
    `test_agent_module_imports_without_error`, nhưng chạy bên trong
    container để bắt lỗi thiếu dependency khi đóng gói).

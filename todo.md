# TODO — personal-card-agent

Trạng thái: 7 task của plan gốc + final review đã xong (nội dung tương ứng
commit `b6c805d`), sau đó sửa thêm 3 bug phát hiện khi chạy thật
(`2d530f7`, `8a1db02`, `e714bee`). Tiếp theo là plan Docker/server tự host
(5 task + 1 final-review fix wave) + một loạt chỉnh sửa theo yêu cầu trực
tiếp (chuyển `conftest.py` vào `tests/`, thêm mục Testing vào README, khôi
phục `tools/`/`skills/`/`sandbox/`, đổi Dockerfile sang `COPY . .` +
`.dockerignore`, bổ sung `.gitignore`).

**Toàn bộ các thay đổi này (kể cả từ đầu phiên) vẫn chưa có commit nào** —
chỉ đang ở trạng thái `git add` (staged), vì chỉ bạn được quyền commit
trong repo này. Chạy `git status` để xem danh sách đầy đủ trước khi commit.

## Đã làm xong

**Plan 1 — personal-card-agent cốt lõi** (7 task, review sạch từng task +
final review, 1 fix wave):
- `data/customer_data.json` — dữ liệu khách hàng mẫu (70 giao dịch, 3
  tháng), có regression test tự kiểm tra tổng khớp với từng giao dịch
  (`tests/data/test_customer_data.py`)
- `middleware/seed_customer_context.py` — nạp lại data mỗi phiên (session-
  scoped, không cache), có test cho cả sync/async
- `agent.py` — đổi từ scaffold "research-assistant" sang "personal-card-agent",
  bỏ tool tìm kiếm cũ, gắn `SeedCustomerContext` + `LogToolCalls`
- `instructions.md` — viết lại toàn bộ: agent chỉ cung cấp thông tin/tư vấn
  (không hành động), quy tắc đọc `/customer_data.json` + bộ nhớ ngân sách
  `/memories/agent/customer_budgets.json`, không hard-code phép tính
- Dọn scaffold cũ (`tools/search.py`, `skills/research/`, `sandbox/` — sau
  đó khôi phục lại theo yêu cầu, xem dưới), cập nhật `pyproject.toml`
- 2 Harbor eval task (`evals/tasks/spending-total-question`,
  `large-transactions-question`)
- Công cụ verify cục bộ: `scripts/verify_agent.py` + notebook cells,
  `docs/superpowers/plans/2026-08-30-personal-card-agent-verification.md`

**3 bug phát hiện khi chạy thật** (không phát hiện được bằng review/test
tĩnh, chỉ lộ ra khi thực sự gọi `.invoke()`):
- Thiếu `langchain-openai` trong `pyproject.toml`'s `notebook` extra —
  notebook/script sẽ crash ngay khi resolve model
- `SeedCustomerContext`/`LogToolCalls` chỉ có bản async, thiếu bản sync —
  crash khi gọi `.invoke()` (sync) thay vì `.ainvoke()`
- In thẳng `message.content` thô (list block reasoning/text của model
  reasoning) thay vì chỉ lấy phần text — sinh ra `extract_final_text()`

**Plan 2 — Docker/server tự host** (5 task + 1 final-review fix wave):
- `text_utils.py` — gộp `extract_final_text()` dùng chung (trước đó lặp ở
  notebook + script)
- `requirements.txt` — dependency riêng cho `server.py`, dùng `pip` thuần,
  tách biệt hoàn toàn khỏi `pyproject.toml`/`uv`
- `server.py` — FastAPI app tự host, độc lập với `mda dev`/LangSmith:
  `POST /chat` (xác thực `X-API-Key` bằng `hmac.compare_digest`),
  `GET /health`, tắt `/docs`/`/redoc`/`/openapi.json`, không leak lỗi nội
  bộ ra response, refuse-to-start nếu thiếu `SERVER_API_KEY`
- `Dockerfile` + `.dockerignore` — non-root user, healthcheck
- `.github/workflows/docker-build.yml` — test → build → smoke-test
  (retry loop) → push GHCR (chỉ khi push `master`)
- Fix wave từ final review: `tests/conftest.py` (sửa lỗi CI chưa từng chạy
  được + lỗi lệnh `uv run --group dev pytest tests/` established của dự án
  bị hỏng về 0 test), thêm test cho `SERVER_API_KEY` fail-fast + 500-masking,
  mục "Self-hosted server" trong README

**Chỉnh sửa theo yêu cầu trực tiếp sau đó:**
- Chuyển `conftest.py` từ root vào `tests/conftest.py`
- Thêm mục "Testing" vào README (2 cách chạy test)
- Khôi phục `tools/`, `skills/` (thư mục rỗng) và `sandbox/__init__.py`
  (bật thật tính năng sandbox) — theo đúng cấu trúc chuẩn MDA
- Đổi `Dockerfile` từ allowlist (`COPY server.py ...`) sang `COPY . .` +
  `.dockerignore` liệt kê đầy đủ (theo yêu cầu, đánh đổi bảo mật đã giải
  thích)
- Bổ sung `.claude/`, `.pytest_cache/` vào `.gitignore` (phát hiện đang
  untracked nhưng không hề gitignore)

23/23 test pass xuyên suốt tất cả các bước trên (`uv run --group dev pytest
tests/ -v`).

## Còn lại (chi tiết ở các mục dưới)

Tóm tắt nhanh — xem chi tiết từng mục bên dưới:
1. **Kiến trúc chưa giải quyết:** đa khách hàng thật, checkpointer cho
   `agent.py`, cô lập bộ nhớ ngân sách, checkpointer bền vững production
2. **Chưa verify bằng chạy thật:** đủ 11 câu checklist, row 10 (ngân sách
   qua thread mới), `agent.py` thật qua `mda dev`, Harbor eval thật,
   `docker build` thật, GitHub Actions thật
3. **Việc nhỏ:** `as_of_date` lệch ngày, namespace `data/` trong wheel,
   error handling khi thiếu data, test riêng cho `LogToolCalls`, rủi ro
   `.dockerignore` lệch theo thời gian, chốt giữ/xoá `sandbox/`
4. **Bạn tự quyết:** `git commit` + `git push`, bật Docker Desktop để build
   thật, chốt `sandbox/__init__.py`

Danh sách dưới đây là những việc **còn lại**, ưu tiên theo mức độ quan trọng.

## 1. Kiến trúc còn thiếu — chưa giải quyết, cần quyết định hướng đi

### 1.1. Đa người dùng (multi-customer)
- `identity.py` hiện chỉ xác thực bằng **1 LangSmith API key dùng chung cho cả
  workspace** (`auth.langsmith_api_key()`) — không có khái niệm "khách hàng A"
  khác "khách hàng B" ở tầng xác thực. `server.py` (đường tự host) cũng
  **chưa có khái niệm khách hàng** — chỉ 1 `SERVER_API_KEY` dùng chung, không
  phải xác thực theo từng người dùng.
- `data/customer_data.json` là **1 file tĩnh duy nhất**, dùng chung cho cả
  `agent.py` lẫn `server.py` — muốn nhiều khách hàng thật cần: (a) nguồn dữ
  liệu theo từng `customer_id` (DB/API thay vì 1 file JSON), (b)
  `SeedCustomerContext` đọc đúng dữ liệu của khách hàng đang chat (cần biết
  "đang chat với ai" — phụ thuộc việc xác thực ở mục trên).
- **Việc cần làm:** đổi `identity.py` sang `auth.supabase(...)` (README đã gợi
  ý) hoặc cơ chế xác thực theo người dùng thật; thiết kế lại nguồn dữ liệu
  khách hàng theo `customer_id`; nếu giữ `server.py`, cũng cần nghĩ xác thực
  theo người dùng thay vì 1 `SERVER_API_KEY` dùng chung.

### 1.2. Lịch sử hội thoại ngắn hạn (trong 1 phiên chat)
- `agent.py` (agent **thật**, deploy qua `managed_deepagents.define_deep_agent`)
  **không có checkpointer** — đã xác nhận `define_deep_agent` không nhận tham
  số này. Đang **phó mặc hoàn toàn cho checkpoint mặc định của nền tảng
  LangSmith Agent Server**, chưa từng verify nền tảng đó có thực sự giữ được
  lịch sử hội thoại qua nhiều lượt trong 1 thread hay không.
- `server.py` (đường tự host) **cố tình không có checkpointer/bộ nhớ** — đây
  là quyết định đã chốt (không dùng `MemorySaver` trong RAM của container),
  `thread_id` chỉ nằm sẵn trong API để sau này cắm memory backend riêng vào,
  hiện tại mỗi request coi như độc lập hoàn toàn. Không phải bug, đã ghi rõ
  trong README mục "Self-hosted server".
- `scripts/verify_agent.py` và notebook dùng `MemorySaver()` **cục bộ**
  (khác hoàn toàn với `agent.py` lẫn `server.py` thật) chỉ để tự test —
  không phản ánh hành vi thật của bên nào khi deploy.
- **Việc cần làm:** chạy `mda dev .`, mở 1 thread trong Studio, hỏi nhiều lượt
  liên tiếp (đặc biệt câu hỏi ngân sách 2 lượt: nói ngân sách → hỏi lại), xác
  nhận agent thật có nhớ được trong cùng thread không. Nếu không, cần tìm cách
  khác để khai báo checkpointer cho `define_deep_agent` (báo lỗi/hỏi
  LangChain, hoặc chờ version mới của `managed-deepagents`).

### 1.3. Bộ nhớ ngân sách dùng chung 1 file (`/memories/agent/customer_budgets.json`)
- Chỉ áp dụng cho `agent.py` (đường `mda`) — `server.py` không đọc/ghi file
  này (không có bộ nhớ, xem 1.2).
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
- `MemorySaver()` (nếu dùng được cho `agent.py` — xem 1.2) chỉ lưu trong RAM,
  mất khi restart process. Chưa chọn checkpointer bền vững (Postgres-backed
  hay tương đương) cho môi trường production thật — áp dụng cho cả `agent.py`
  (nếu sau này tự quản checkpointer được) lẫn bất kỳ memory backend nào cắm
  vào `server.py` sau này (xem 1.2).

## 2. Chưa được verify bằng cách chạy thật — cần làm trước khi tin tưởng agent

- [ ] Chạy đủ **11 câu hỏi** trong
  `docs/superpowers/plans/2026-08-30-personal-card-agent-verification.md`
  (qua `mda dev .` + Studio HOẶC qua `scripts/verify_agent.py`/notebook cục
  bộ), điền kết quả PASS/FAIL vào bảng. Đã test tay rải rác vài câu ngoài
  checklist qua `server.py`'s đường local-invoke (tổng chi tiêu tháng 8,
  giao dịch lớn nhất tuần, chi tiêu ăn uống — đều đúng), nhưng chưa chạy đủ
  bộ 11 câu có hệ thống lần nào.
- [ ] **Row 10 (ngân sách nhớ được qua thread MỚI)** — chỉ test được qua
  `mda dev .` + Studio thật (agent.py), chưa làm lần nào. Đây là phép thử
  duy nhất xác nhận `/memories/agent/customer_budgets.json` hoạt động đúng
  như thiết kế. `server.py` không áp dụng (không có bộ nhớ, xem 1.2).
- [ ] **Chưa từng chạy `agent.py` thật qua `mda dev .`** — toàn bộ việc test
  đến giờ (cả plan gốc lẫn plan Docker/server) đều qua `deepagents.create_deep_agent`
  cục bộ (notebook Option A / `server.py` / `scripts/verify_agent.py`),
  KHÔNG phải qua `managed_deepagents.define_deep_agent` (Option B, agent
  thật sẽ deploy). Rủi ro: các bug sync/async đã phát hiện và fix
  (`8a1db02`) đều nằm trên đường Option A — chưa xác nhận Option B (nền
  tảng thật) có gặp vấn đề tương tự hay không.
- [ ] 2 Harbor eval task (`evals/tasks/spending-total-question`,
  `evals/tasks/large-transactions-question`) mới verify cấu trúc bằng tay
  (viết `answer.md` giả), **chưa từng chạy qua Harbor/`mda evals` thật**. Cả 2
  Task.md đã ghi chú nghi ngờ: `sandbox/` (giờ đã khôi phục lại — xem mục 3)
  có ảnh hưởng gì đến việc agent có filesystem thật để ghi `answer.md` cho
  Harbor chấm hay không — chưa xác nhận đúng/sai, nhưng việc khôi phục
  `sandbox/` có thể đã giải quyết một phần nghi ngờ này (chưa kiểm chứng).
- [ ] **`Dockerfile` chưa từng `docker build` thật lần nào** — Docker Desktop
  không chạy trên máy suốt cả phiên làm việc này. Review chỉ verify được
  bằng cách đọc file + kiểm tra file tồn tại, KHÔNG phải build thật. Đặc
  biệt cần build lại sau khi đổi sang `COPY . .` (xem mục 3) — cấu trúc
  COPY khác hẳn bản allowlist đã từng review.
- [ ] **`.github/workflows/docker-build.yml` chưa từng chạy thật trên
  GitHub** — cần `git push` (mục 4) rồi mới biết workflow có thật sự chạy
  đúng trên GitHub Actions hay không (dù đã verify YAML hợp lệ + verify test
  job bằng scratch venv cục bộ).

## 3. Việc nhỏ còn treo (đã ghi nhận, không chặn, làm khi rảnh)

- [ ] `data/customer_data.json`'s `_meta.as_of_date` sẽ tiếp tục lệch ngày
  thật mỗi lần demo — cân nhắc cập nhật định kỳ hoặc bỏ trường này.
- [x] ~~`README.md` còn 2 dòng cũ chưa dọn (mục Deploy nhắc `skills/`, mục
  Next steps có link "tools guide")~~ — đã hết stale: `tools/` và `skills/`
  đã được khôi phục (thư mục rỗng, opt-in), nên 2 dòng này giờ lại đúng.
- [ ] `pyproject.toml` gói `data/customer_data.json` vào `site-packages/data/`
  — tên thư mục không có namespace riêng, có thể đụng độ nếu sau này thêm
  package khác cũng dùng tên `data`. (Chỉ ảnh hưởng đường `mda deploy` —
  `server.py`/Docker dùng `requirements.txt` riêng, không liên quan.)
- [ ] `SeedCustomerContext.before_agent`/`abefore_agent` không bắt lỗi khi
  `data/customer_data.json` thiếu/hỏng — hiện fail loud (traceback thô), có
  thể bọc lại thành thông báo rõ ràng hơn. Ảnh hưởng cả `agent.py` lẫn
  `server.py` (dùng chung middleware này).
- [ ] `middleware/audit.py` (`LogToolCalls`) **vẫn chưa có unit test riêng**
  (`tests/middleware/` chỉ có `test_seed_customer_context.py`) — có coverage
  *gián tiếp* qua `tests/test_server.py` (các test gọi `.invoke()` thật với
  fake model đều đi qua `LogToolCalls` sync path), nhưng chưa có test cô lập
  đúng nghĩa như `SeedCustomerContext` đã có. Nên thêm
  `tests/middleware/test_audit.py`.
- [ ] **Mới phát sinh — rủi ro `.dockerignore` bị lệch theo thời gian:**
  `Dockerfile` vừa đổi từ allowlist (`COPY server.py ... `) sang `COPY . .`
  + `.dockerignore` liệt kê tường minh mọi thứ cần loại trừ (đây là lựa
  chọn có chủ đích, đã cân nhắc đánh đổi bảo mật). Rủi ro đã biết: **thêm
  file/thư mục mới ở root mà quên cập nhật `.dockerignore` sẽ lọt thẳng vào
  image** — không có gì tự động cảnh báo việc này. Nên định kỳ đối chiếu
  `.dockerignore` với `ls` ở root, đặc biệt trước mỗi lần build/deploy image
  thật.
- [ ] `sandbox/__init__.py` vừa được khôi phục — sự hiện diện của nó **bật
  thật tính năng managed sandbox** khi `mda deploy` (ảnh hưởng chi phí/hành
  vi). Nếu không thật sự cần chạy code trên nền tảng, cân nhắc xoá lại
  trước khi deploy thật lần đầu với thư mục này.
- [ ] **Kích hoạt Semantic Memory** (`tools/memory_tools.py` — cặp
  `remember_fact`/`recall_fact` cho strategy `ltms-2038ab25-bb1b-4148-ba48-c4435e0333e7`,
  hiện đang comment out có chủ đích). Phạm vi Semantic ("khách hàng có gì?"):
  sản phẩm/dịch vụ đang sở hữu, tình hình tài chính khách quan, sự kiện đời
  sống, hành vi quan sát được, lịch sử tương tác — khác với User Preference
  ("khách hàng thích gì?") đang dùng cho ngân sách tự đặt. Khi làm: thêm env
  var `SEMANTIC_STRATEGY_ID` (fail-fast giống `USER_PREFERENCE_STRATEGY_ID`),
  uncomment tool + thêm vào `build_agent()`'s `tools=[...]`, viết test tương
  tự `test_remember_preference_tool_inserts_under_actor_namespace`/
  `test_recall_preference_tool_searches_under_actor_namespace`, cập nhật
  `docker-compose.yml`/CI workflow/README với biến env mới, và bổ sung
  `instructions.md` hướng dẫn khi nào dùng `remember_fact`/`recall_fact` thay
  vì `remember_preference`/`recall_preference`.
- [ ] **Chuyển sang dùng model của VNG (MaaS)** thay vì (hoặc song song với)
  OpenAI `gpt-5.5` đang hard-code ở `server.py:build_agent()`. Đã xác nhận
  qua docs GreenNode: VNG có endpoint LLM tương thích OpenAI API tại
  `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1`, dùng thẳng được với
  `ChatOpenAI(base_url=..., api_key=<key riêng>, model=<model path VNG>)`
  vì cùng chuẩn OpenAI-compatible.
  - **Việc cần làm:**
    1. Vào mục **"Model as a Service (MaaS)"** / **"Models"** trên console
       GreenNode (thấy trong sidebar khi kiểm tra Access Control) để xem
       danh sách model VNG cung cấp + tên/path model chính xác cần truyền
       vào `model=`.
    2. Lấy API key gọi được endpoint MaaS này — cách docs hướng dẫn là qua
       decorator `@requires_api_key(provider_name="<tên provider>")` (từ
       `greennode_agentbase.identity`, đã verify là decorator thường, **không
       bắt buộc phải dùng `GreenNodeAgentBaseApp`** — gắn được lên hàm bất kỳ,
       kể cả route handler FastAPI của `server.py`). Cần cấu hình 1
       "Outbound Auth" provider trước (tab **Outbound Auth** cạnh Access
       Control trên console, hoặc CLI `gab identity outbound-auth`) — loại
       "Static (API Key)" là đơn giản nhất cho M2M.
    3. Cân nhắc: giữ `model` cấu hình được qua env var (ví dụ `LLM_MODEL`,
       `LLM_PROVIDER`) để dễ so sánh OpenAI vs model VNG mà không phải sửa
       code, hoặc A/B giữa 2 lựa chọn khi eval chất lượng.
    4. Kiểm tra lại toàn bộ 11 câu hỏi checklist (mục 2) với model mới —
       chất lượng suy luận/tool-calling có thể khác OpenAI, cần verify lại
       chứ không giả định tương đương.

## 4. Việc người dùng tự quyết định

- [ ] `git push` lên `origin/master` (https://github.com/Daonguyen2401/personal-card-agent.git)
  — hiện toàn bộ (bao gồm cả plan Docker/server + mọi chỉnh sửa sau đó) vẫn
  chỉ đang **staged, chưa có commit nào**, theo lựa chọn của bạn (chỉ bạn
  được quyền commit). Cần tự `git commit` trước khi có gì để push.
- [ ] Build Docker image thật + `docker run` thử (Docker Desktop cần được
  bật trước) — xem mục 2.
- [ ] Chốt việc có giữ `sandbox/__init__.py` (bật tính năng thật) hay xoá
  lại trước khi deploy — xem mục 3.

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
  khác "khách hàng B" ở tầng xác thực.
- **Cập nhật (đã làm ở phiên GreenNode Memory):** `server.py` giờ **đã có**
  `user_id` trên mỗi request (bắt buộc, dùng làm `actor_id` cho GreenNode
  Memory) — nhưng đây chỉ là giá trị **client tự khai báo và server tin
  tưởng**, không có xác thực thật theo từng người dùng (vẫn chỉ 1
  `SERVER_API_KEY` dùng chung cho mọi caller). Không phải bug cần sửa ngay
  (frontend hiện đang là backend nội bộ đáng tin cậy), nhưng cần nhớ đây
  chưa phải xác thực đầu-cuối thật nếu sau này mở API cho client ít tin
  cậy hơn.
- `data/customer_data.json` là **1 file tĩnh duy nhất**, chỉ có 1 khách hàng
  (`CUS-000482`), dùng chung cho cả `agent.py` lẫn `server.py`, và
  `SeedCustomerContext` load file này **bất kể `user_id` là ai** — mọi
  khách hàng hiện đang thấy chung 1 bộ dữ liệu. Xem mục 1.1.1 ngay dưới đây
  — đã có yêu cầu cụ thể để giải quyết phần này trước.
- **Việc cần làm (phần xác thực, vẫn mở):** đổi `identity.py` sang
  `auth.supabase(...)` (README đã gợi ý) hoặc cơ chế xác thực theo người
  dùng thật cho `agent.py`; với `server.py`, cân nhắc xác thực `user_id`
  thật (không chỉ tin client) nếu mở ra ngoài phạm vi backend nội bộ.

#### 1.1.1. Dữ liệu khách hàng theo `user_id` — 3 khách hàng: `CIF_0001`, `CIF_0002`, `CIF_0003`

**Đã triển khai xong (server.py):**
- [x] 3 khách hàng mới hoàn toàn (không tái dùng `CUS-000482` cũ, đã xoá
  `data/customer_data.json`): `data/customers/CIF_0001.json` (Ly Lã, Nữ),
  `CIF_0002.json` (Trần Toàn, Nam), `CIF_0003.json` (Đào Nguyên, Nam) — mỗi
  file thêm field `gender` mới, nội bộ nhất quán (tổng giao dịch khớp
  `monthly_spending_summary`, verify bằng script).
- [x] `middleware/seed_customer_context.py` — `SeedCustomerContext` giờ đọc
  `actor_id` qua `langgraph.config.get_config()["configurable"]["actor_id"]`
  rồi load đúng `data/customers/<customer_id>.json`. 3 trường hợp:
  - Có `actor_id` khớp 1 trong 3 → load đúng khách hàng đó (verify bằng
    request thật qua `create_deep_agent` + fake model, và qua `uvicorn`
    thật với credentials GreenNode thật — request cho `CIF_0001`/`CIF_0003`
    đều vượt qua middleware đúng, chỉ fail sau đó ở bước gọi OpenAI vì lỗi
    401 thiếu scope đã biết từ trước, không liên quan).
  - Có `actor_id` nhưng không khớp khách nào → raise `UnknownCustomerError`
    rõ ràng (verify: request `user_id` rác → lỗi đúng tại middleware, không
    kịp gọi OpenAI) — tự nổi thành `500` đã mask sẵn ở `/chat`, không cần
    sửa gì thêm ở `server.py`.
  - Không có `actor_id`/không có runnable context (gọi middleware trực
    tiếp trong unit test, hoặc `agent.py` không set `actor_id`) → fallback
    `DEFAULT_CUSTOMER_ID = "CIF_0001"`, giữ nguyên hành vi cũ của `agent.py`
    không bị vỡ.
- [x] `instructions.md` — ví dụ ngân sách đổi từ `CUS-000482` sang
  `CIF_0001`.
- [x] `pyproject.toml` + `tests/test_packaging.py` — đóng gói 3 file mới
  thay vì 1 file cũ, verify bằng `uv build --wheel` thật.
- [x] `tests/data/test_customer_data.py` — tổng quát hoá (parametrize) chạy
  trên cả 3 file.
- [x] `tests/middleware/test_seed_customer_context.py` — thêm 3 test:
  fallback khi không có context, load đúng khách hàng theo `actor_id`, và
  raise lỗi khi `actor_id` không khớp khách nào.
- [x] `tests/test_server.py` — đổi toàn bộ `user_id` giả (`u1`, `alice`,
  `customer-42`...) sang `CIF_0001`/`CIF_0002` thật (bắt buộc vì middleware
  giờ raise nếu không khớp khách nào).
- [x] `CLAUDE.md` (file mới) — chỉ dẫn không tự ý `git commit`/`git push`.
- 88/88 test pass xuyên suốt (`uv run --group dev pytest tests/` = 35 pass
  + `tests/test_server.py` qua venv riêng = 53 pass, không tính trùng).

**Chưa làm / cân nhắc sau:**
- [ ] `docs/sample_questions_and_answers.md` — chưa kiểm tra có tham chiếu
  số liệu `CUS-000482` cũ không (không chặn, chỉ là doc tham khảo dev, agent
  không đọc lúc chạy).
- [ ] 2 Harbor eval task (`evals/tasks/spending-total-question`,
  `large-transactions-question`) đang hard-code số liệu theo `CUS-000482`
  cũ — theo yêu cầu, **giữ nguyên không sửa lần này**, sẽ sai/lỗi thời nếu
  chạy Harbor thật với data mới. Cần cập nhật lại theo 1 trong 3 khách hàng
  mới khi có nhu cầu chạy Harbor eval thật.
- [ ] `agent.py`/đường `mda`: xác nhận có cơ chế tương đương để biết
  "`user_id` nào đang chat" hay không — hiện tại đường này **luôn fallback
  về `CIF_0001`** (không có `actor_id` trong config của
  `managed_deepagents.define_deep_agent`), nghĩa là mọi cuộc hội thoại qua
  `agent.py` đều thấy dữ liệu của Ly Lã, không phân biệt được người gọi
  thật. Việc này **chỉ áp dụng đúng nghĩa cho `server.py`** hiện tại.

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
- [x] **Chuyển sang dùng model của VNG (MaaS)** — hoàn thành, thay hẳn OpenAI
  (không giữ song song). `server.py` giờ tự construct
  `ChatOpenAI(base_url="https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1", api_key=AI_PLATFORM_API_KEY, model=LLM_MODEL)`
  thay vì chuỗi `"openai:gpt-5.5"` — hoá ra đơn giản hơn dự đoán trước đó:
  key chỉ là 1 static API key qua env var (`AI_PLATFORM_API_KEY`), **không
  cần** decorator `@requires_api_key`/Outbound Auth provider như ghi nhận
  lúc trước (đó là dự đoán từ docs, thực tế theo quickstart VNG cung cấp thì
  đơn giản hơn).
  - `LLM_MODEL` (optional, mặc định `z-ai/glm-5.2-hackathon`) — configurable
    qua env var đúng như đã cân nhắc, không cần sửa code để đổi model.
  - `OPENAI_API_KEY` không còn được `server.py` đọc ở đâu cả — đã bỏ khỏi
    `docker-compose.yml`/CI workflow/README (chỉ `agent.py`/đường `mda` vẫn
    cần, không liên quan).
  - Verify **end-to-end thật** qua `uvicorn` local + credentials GreenNode
    thật: `/chat` với `user_id=CIF_0001` trả lời đúng, đúng dữ liệu khách
    hàng (Ly Lã, Nữ, thu nhập, 2 thẻ).
  - **Phát hiện + đã fix thêm:** model GLM là reasoning model, để sót tag
    `</think></think>` (hoặc block `<think>...</think>` đầy đủ) lẫn trong
    `content` thay vì tách riêng — `text_utils.extract_final_text()` đã
    được thêm bước strip tag này (`_strip_think_tags`), có test riêng.
  - Đã sửa nhân tiện: README mục lấy `GREENNODE_CLIENT_ID`/`SECRET` trước đó
    ghi sai chỗ ("Access Control" → "Create Identity") — cập nhật đúng
    thành `iam.console.greennode.ai/service-accounts` (Service Account),
    theo đúng phát hiện đã xác nhận trước đó nhưng quên quay lại sửa README.
  - **Chưa làm:** kiểm tra lại toàn bộ 11 câu hỏi checklist (mục 2) với
    model mới — chất lượng suy luận/tool-calling có thể khác OpenAI, chưa
    verify hệ thống, chỉ mới test 1 câu hỏi đơn giản (giới thiệu bản thân).

## 4. Việc người dùng tự quyết định

- [ ] `git push` lên `origin/master` (https://github.com/Daonguyen2401/personal-card-agent.git)
  — hiện toàn bộ (bao gồm cả plan Docker/server + mọi chỉnh sửa sau đó) vẫn
  chỉ đang **staged, chưa có commit nào**, theo lựa chọn của bạn (chỉ bạn
  được quyền commit). Cần tự `git commit` trước khi có gì để push.
- [ ] Build Docker image thật + `docker run` thử (Docker Desktop cần được
  bật trước) — xem mục 2.
- [ ] Chốt việc có giữ `sandbox/__init__.py` (bật tính năng thật) hay xoá
  lại trước khi deploy — xem mục 3.

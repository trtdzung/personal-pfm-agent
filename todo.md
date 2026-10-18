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

### 1.5. [ĐÃ FIX THẬT 2026-09-13 — xem phần "Nguyên nhân gốc thật" ở cuối mục] Crash `/chat` cho MỌI câu hỏi trên 1 thread đã dùng nhiều

**Sự cố (2026-09-03):** production báo lỗi `500` cho **mọi** request `/chat`
của `user_id=CIF_0001` — kể cả câu đơn giản như "Hello" — ngay sau khi deploy
commit thêm tính năng chart/skill (`81d0e6f`).

**Đã điều tra + xác nhận nguyên nhân (build lại đúng Docker image, chạy
local với credentials GreenNode thật, tái hiện thành công):**
- **Không liên quan** tới tính năng chart/skill/`CompositeBackend` vừa thêm
  — đã verify riêng bằng model thật, đều chạy đúng.
- **Không liên quan** version `langchain`/`langchain-core` (dù đã pin cứng
  2 gói này vào `requirements.txt` như 1 việc nên làm riêng, không phải fix
  cho sự cố này).
- Nguyên nhân thật: `thread_id=CIF_0001` là thread **mặc định dùng chung
  cho mọi lượt chat** của khách hàng này (frontend chưa truyền `thread_id`
  riêng — xem `docs/api.md`), đã tích luỹ lịch sử qua rất nhiều lần test
  suốt nhiều tuần của dự án. Lịch sử cũ này được lưu qua checkpointer
  `AgentBaseMemoryEvents` (GreenNode Memory). Khi agent nạp lại lịch sử đó,
  LangGraph cố convert từng message cũ thành `BaseMessage` và gặp ít nhất 1
  message được lưu ở dạng không đúng chuẩn `(role, content)` — traceback
  thật:
  ```
  deepagents/_messages_reducer.py:58, in _messages_delta_reducer
    convert_to_messages(state or [])
  langchain_core/messages/utils.py:742
    raise NotImplementedError("Message as a sequence must be (role string, template)") from e
  ```
  → mọi request mới trên thread đó crash ngay khi nạp lại state, bất kể nội
  dung câu hỏi mới là gì.
- Sở dĩ ban đầu không tái hiện được: mọi lần test debug đều dùng `thread_id`
  **mới, ngẫu nhiên** (lịch sử rỗng) — chỉ khi test đúng `thread_id=CIF_0001`
  (thread thật, có lịch sử cũ) mới lộ ra.

**Đã fix tạm (áp dụng thật trên GreenNode Memory, đã verify hết lỗi):**
gọi `DELETE /chat/history?user_id=CIF_0001` (endpoint có sẵn) để xoá sạch
lịch sử cũ bị lỗi của thread này. Sau khi xoá, `/chat` hoạt động lại bình
thường trên cùng thread.

**Rủi ro còn treo — cần quyết định hướng đi lâu dài:**
- [ ] Đây gần như chắc chắn là lỗi/tương thích ngược ở tầng
  `greennode-agent-bridge`'s `AgentBaseMemoryEvents` (serialize message
  thành dạng LangGraph/langchain hiện tại không đọc lại đúng) — chưa rõ có
  phải do checkpoint được ghi từ 1 phiên bản `deepagents`/`langgraph` cũ
  hơn trước đây hay không. Nên báo lại cho phía GreenNode/kiểm tra changelog
  `greennode-agent-bridge`.
- [ ] `CIF_0002`/`CIF_0003` nếu cũng từng được test thật nhiều qua các phiên
  trước có thể đang mang cùng rủi ro (thread mặc định của họ cũng có thể
  đã tích luỹ lịch sử ở định dạng cũ) — nên chủ động xoá phòng ngừa bằng
  `DELETE /chat/history` cho cả 2, hoặc theo dõi xem có lỗi tương tự không.
- [ ] Chưa có cơ chế tự động phát hiện/tự phục hồi khi 1 thread rơi vào
  trạng thái này trong tương lai (ví dụ agent thật của khách hàng khác cũng
  tích luỹ đủ lâu rồi gặp lại) — hiện chỉ có thể phát hiện qua log lỗi
  `500` + xoá tay bằng `DELETE /chat/history`. Cân nhắc: log rõ hơn khi
  gặp đúng lỗi này (dễ nhận diện hơn generic "Agent failed to process the
  request"), hoặc tự động catch riêng lỗi này và tự xoá/reset thread thay
  vì chỉ trả 500.

**NGUYÊN NHÂN GỐC THẬT — tìm ra và fix ngày 2026-09-13 (đã tái hiện được
100% bằng test tự động, không cần credentials/network):** giả thiết "lịch sử
cũ / định dạng cũ" ở trên là **SAI**. Lịch sử không hề bị lỗi, và cũng không
liên quan gì tới việc nó được ghi bởi phiên bản `deepagents`/`langgraph` cũ.
Lỗi nằm ở chỗ `greennode-agent-bridge` (1.0.5, bản mới nhất) đọc sai chính
dữ liệu mà **các phiên bản hiện tại** vừa ghi ra:

- Từ `langgraph` 1.1 + `deepagents` 0.7, `messages` nằm trên `DeltaChannel`
  (`deepagents/graph.py`: `DeltaChannel(_messages_delta_reducer,
  snapshot_frequency=50)`). Channel này **không** lưu list message vào
  `channel_values` ở mỗi checkpoint: phần lớn checkpoint không lưu gì (state
  được dựng lại bằng cách replay writes của tổ tiên qua reducer), và **cứ 50
  lần cập nhật channel thì lưu 1 snapshot đầy đủ** dưới dạng namedtuple
  `_DeltaSnapshot(value=[msg, msg, ...])`.
- `AgentBaseMemoryEvents` kết thúc mỗi lần đọc checkpoint bằng bước "vá tool
  call mồ côi" (`helpers.patch_orphan_tool_calls`, gọi từ
  `EventProcessor.build_checkpoint_tuple`) — hàm này **giả định**
  `channel_values["messages"]` luôn là `list[BaseMessage]` thuần. Gặp
  `_DeltaSnapshot`, nó duyệt namedtuple đó như 1 list và trả về
  `[[msg, msg, ...]]` (list message bị lồng thêm 1 cấp).
- `DeltaChannel.from_checkpoint` không còn nhận ra đó là snapshot, coi như
  "plain value" thời tiền-delta, và đưa list lồng đó vào reducer làm state
  tích luỹ → reducer thấy `state[0]` là list chứ không phải `BaseMessage` →
  fallback `convert_to_messages()` → chết đúng traceback ở trên.
- Vì thế: thread mới/ít dùng luôn OK (chưa bao giờ ghi snapshot blob), còn
  thread mặc định dùng chung (`thread_id == user_id`) chạy đủ lâu (≥50 lần
  cập nhật channel `messages`) rồi đi tiếp qua snapshot đó là **crash mọi
  request, bất kể câu hỏi gì**. `DELETE /chat/history` "chữa" được đúng vì
  nó reset về 0 update — nhưng sẽ tái diễn sau ~50 update tiếp theo. Đây
  chính là lý do sự cố này quay lại nhiều lần.

**Fix (đã áp dụng, ở tầng repo mình, không sửa được package của GreenNode):**
`checkpointer_delta_snapshot.py` → `patch_preserve_delta_snapshots()` (gọi
trong `build_agent()` của `server.py`, idempotent): chỉ cho bước vá tool call
mồ côi của bridge chạy trên giá trị **thật sự là `list`**; mọi thứ khác (hôm
nay: `_DeltaSnapshot`) trả về nguyên vẹn để `DeltaChannel.from_checkpoint`
vẫn nhận ra snapshot. Cố ý **không** chọn cách "mở snapshot ra, vá bên trong,
gói lại": snapshot là seed giữa chuỗi, tool call trông "mồ côi" trong đó
thường được hoàn tất bởi `ToolMessage` ở write replay sau (snapshot rơi đúng
biên superstep, và biên ngay sau model node là chỗ tool call chưa có kết
quả) — vá vào đó sẽ tạo **2 `ToolMessage` cho cùng 1 `tool_call_id`**, tệ
hơn lỗ hổng nó định bịt. Bỏ hẳn bước vá cho delta snapshot đưa checkpointer
này về đúng chỗ mọi saver khác của LangGraph đang đứng (`InMemorySaver`,
`PostgresSaver` không vá gì cả).

**Test bảo vệ:** `tests/test_checkpointer_delta_snapshot.py` (4 test, đã thêm
vào CI) — gồm 1 test end-to-end chạy `AgentBaseMemoryEvents` thật với
`_FakeMemoryClient` in-memory (không network), 8 lượt hội thoại vượt qua
nhiều biên snapshot (`snapshot_frequency=2` để nén lại cái deepagents gặp ở
50), cộng 1 lần đọc lại bằng checkpointer instance mới (không cache). Đã
verify: bỏ patch ra thì 2/4 test fail đúng lỗi này, bật lại thì pass hết.

**Việc còn nên làm:**
- [ ] Báo bug lên phía GreenNode: `patch_orphan_tool_calls` cần
  `DeltaChannel`-aware (hoặc bỏ hẳn, để LangGraph tự lo). Bỏ
  `checkpointer_delta_snapshot.py` khi có bản `greennode-agent-bridge` đã fix.
- [ ] Không cần xoá lịch sử `CIF_0002`/`CIF_0003` nữa (lịch sử của họ không
  hỏng); nhưng thread nào **đang** ở trạng thái crash thì sau khi deploy fix
  này sẽ tự chạy lại được, không cần `DELETE /chat/history`.

### 1.6. [Đã fix] JSON của `ui` lọt thẳng vào `answer` khi model không dùng đúng fence

**Sự cố (2026-09-07, phát hiện bởi team frontend qua test thật trên PCA
chat):** 1 câu trả lời so sánh chi tiêu (có kèm chart) hiện nguyên văn
JSON thô ở cuối `answer`:
```
...con số cuối tháng có thể cao hơn.

{"chart_type": "bar", "title": "So sánh...
```
Đúng điều `docs/chart-visualization.md` cam kết "frontend không bao giờ
thấy JSON thô lẫn trong `answer`" bị vi phạm.

**Nguyên nhân:** `extract_ui_block()` (`text_utils.py`) trước đó chỉ tìm
đúng 1 pattern cố định — khối được bọc đúng fence ` ```ui-json\n...\n``` `.
Khi model (vì lý do bất kỳ — không phải lỗi cố ý, model đôi khi bỏ sót
fence) chèn JSON mà **không bọc fence** (hoặc bọc sai/không đóng đúng),
regex không match được gì, hàm trả nguyên văn text không đổi → JSON lọt
thẳng ra `answer`.

**Đã fix:** viết lại `extract_ui_block()` theo 2 lớp, không phụ thuộc
tuyệt đối vào fence:
1. Vẫn tìm và cắt bỏ mọi khối fence bất kỳ (` ```<label>...``` `) trước —
   **kể cả khi nội dung bên trong không phải JSON hợp lệ** (app này không
   có use case hợp lệ nào khác cho code fence ngoài `ui-json`, nên cắt bỏ
   toàn bộ khối fence là an toàn dù không parse được, đúng yêu cầu "thà
   cắt bỏ phần nghi ngờ còn hơn để lọt nguyên văn").
2. Trên phần còn lại, quét tiếp tìm JSON object **trần** (không fence) —
   dùng `json.JSONDecoder.raw_decode` thật (không phải đếm ngoặc thủ
   công) để tìm đúng object hoàn chỉnh dù model quên bọc fence.
3. Object nào tìm được (dù fenced hay không, dù hợp lệ hay không) đều bị
   cắt khỏi `answer`; chỉ object **đầu tiên pass `_is_valid_ui`** mới trở
   thành `ui`, còn lại `ui: null`.
- Test mới trong `tests/test_text_utils.py`: JSON hợp lệ không fence, và
  đúng fragment JSON schema cũ (thiếu field `type`) y hệt báo cáo lỗi —
  cả 2 đều bị cắt khỏi `answer` đúng, `ui` fallback `null` khi thiếu
  `type`/sai schema.
- Verify thật với model VNG (2 skill `chart` + `transfer_form`): `answer`
  không còn ký tự `` ` ``/`{`/`}` nào, `ui` đúng type. 58/58 test pass.

### 1.7. [Đã làm] `GET /chat/history` giờ trả lại `ui` cho từng message — đảo ngược quyết định cũ

**Bối cảnh (2026-09-07):** thảo luận với người dùng phát hiện ra: dữ liệu
`ui` **không hề mất** khi lưu qua GreenNode Memory — checkpoint lưu
nguyên văn AIMessage gốc (còn nguyên khối `ui-json`) TRƯỚC khi
`extract_ui_block()` chạy ở tầng `/chat`. `GET /chat/history` trước đó
CÓ chạy lại `extract_ui_block()` trên từng message cũ (để lọc JSON thô
khỏi `content` hiển thị), nhưng **chủ động vứt bỏ** phần `ui` tách được
(`text, _ = extract_ui_block(text)`) — và `HistoryMessage` không có field
nào để mang giá trị đó ra ngoài. Đây là thiếu sót ở code/schema, không
phải giới hạn về dữ liệu.

**Đã sửa:** `server.py` — thêm field `ui: dict | None = None` vào
`HistoryMessage`, dùng luôn giá trị `ui` tách được thay vì vứt.

**⚠️ Đảo ngược 1 quyết định đã thống nhất với FE trước đó:**
`docs/chart-output-rules.md` (tài liệu FE viết, đã xoá khỏi repo) từng có
rule **B.MUST-6: "`GET`/`DELETE /chat/history` PHẢI KHÔNG BAO GIỜ trả
field `ui`"**. Quyết định này giờ đảo ngược — `GET /chat/history` **có**
trả `ui`. `DELETE /chat/history` không đổi (không trả `messages` nên
không liên quan). **Cần báo lại FE** đây là thay đổi hợp đồng API thật,
không chỉ thêm field cho tính năng mới — nếu FE code chỉ đọc `content`
khi load lịch sử cũ (theo đúng rule cũ), giờ có thể cần đọc thêm `ui` để
hiện lại chart/form cho tin nhắn cũ.

**Đã cập nhật:** `docs/api.md` (thêm breaking-change note ở mục
`GET /chat/history`), `docs/chart-visualization.md` (mục "Luồng UI gợi ý"
điểm 3), test mới trong `tests/test_server.py`
(`test_chat_history_includes_ui_for_a_past_turn_that_had_a_chart`) +
cập nhật 2 test cũ đang assert cứng shape `messages[]` (thiếu field `ui`).
52/52 test pass (venv có fastapi).

**Đã đồng bộ:** copy lại `api.md`/`chart-visualization.md` mới vào
`PersonalCardAgentUI/agent_backend_docs/` (`transfer-form.md` không đổi,
không cần copy lại). **Còn treo:** báo lại FE về thay đổi hợp đồng này
(chưa phải việc code, chỉ là communication — người dùng tự làm).

### 1.8. [Đã làm — đảo ngược quyết định trước] Bỏ tool `check_available_balance_or_credit`

**Quyết định (2026-09-07, theo yêu cầu trực tiếp):** bỏ hẳn tool
`check_available_balance_or_credit` khỏi luồng `transfer_form` — **đảo
ngược lại lý do đã lập luận khi thêm tool này** ("nên làm tool riêng thay
vì để agent tự tính bằng free-text, vì đây là điều kiện chặn cứng"). Giờ
agent tự đọc `/customer_data.json` (`cards`) bằng `read_file` để đối
chiếu `amount` với `available_credit_vnd`, giống hệt cách đối chiếu
`recipient`/`account_number` đã làm từ đầu — không còn enforcement bằng
code, hoàn toàn dựa vào agent tuân theo hướng dẫn skill.

**Đã làm:**
- Xoá hẳn `tools/transfer_tools.py` + `tests/test_transfer_tools.py`.
- `server.py` — bỏ import + bỏ khỏi `tools=[...]` mặc định của
  `build_agent()`.
- `skills/project/transfer-form/SKILL.md` — gộp bước Check thành 1 bước
  "tự đọc `/customer_data.json` rồi tự đối chiếu", bỏ mọi nhắc tới tool.
- `docs/transfer-form.md` — cập nhật lại phần "Cơ chế" cho khớp.
- `tests/test_server.py` — đơn giản hoá test end-to-end (không còn mô
  phỏng tool call, chỉ cần fake model trả thẳng khối `ui-json`).
- Verify thật với model VNG (không dùng tool): agent tự gọi `read_file`
  (4 lần) thay vì gọi tool, vẫn sinh đúng `transfer_form` hợp lệ. 56/56
  test pass (`uv run --group dev pytest tests/`).

**Rủi ro cần lưu ý (do đảo ngược quyết định):** không còn gì ở tầng code
chặn cứng việc agent tính sai/đề xuất vượt hạn mức — hoàn toàn phụ thuộc
vào agent tuân theo `SKILL.md` (giống rủi ro đã ghi ở mục 1.3 cho ngân
sách). Nếu sau này phát hiện agent hay tính sai hạn mức trong thực tế,
cân nhắc quay lại dùng tool.

### 1.9. [Đã fix — giảm tần suất, không tất định] Agent đôi khi từ chối đề xuất `create_jar`/`edit_jar`, tưởng nhầm là hành động thật

**Sự cố (2026-09-07, phát hiện khi bạn test trên endpoint đã deploy):** hỏi
"Tạo giúp tôi 1 hũ mua sắm hợp lý mỗi tháng." / "Tăng hũ giải trí của tôi
lên 800 nghìn được không?" → agent **từ chối cả 2**, trả lời kiểu "Việc tạo
hũ tiết kiệm là hành động thiết lập trên hệ thống ngân hàng, nằm ngoài
phạm vi hỗ trợ của tôi..." — `ui: null` cho cả 2, chưa test được format vì
bị chặn ngay từ đầu.

**Nguyên nhân:** câu mở đầu `instructions.md` ("bạn không thực hiện bất kỳ
hành động nào làm thay đổi trạng thái thẻ... Nếu khách hàng yêu cầu một
hành động như vậy, giải thích rằng việc đó ngoài phạm vi hỗ trợ") được viết
**trước khi có** các skill `transfer_form`/`create_jar`/`edit_jar` — không
có ngoại lệ nào nói rõ "đề xuất hiển thị qua skill" khác với "thực hiện
hành động thật". Model đôi khi áp nhầm rule từ chối này vào câu hỏi dạng ra
lệnh trực tiếp ("tạo giúp tôi...", "tăng... giúp tôi") dù có skill tương
ứng hướng dẫn nên đề xuất.

**Đã xác nhận đây là non-determinism (không tất định), không phải bug 100%
lặp lại:** thử lại **đúng câu hỏi y hệt** ngay sau khi nhận báo cáo (trước
khi sửa gì) → agent trả lời đúng, không từ chối. Cùng loại hiện tượng đã
biết với chart-skill (model không phải lúc nào cũng tuân theo skill).

**Đã fix:** thêm đoạn "Ngoại lệ quan trọng" ngay sau câu mở đầu
`instructions.md`, nói rõ: đề xuất form/biểu đồ qua skill chuyên biệt
KHÔNG tính là "hành động thật" bị cấm — chỉ áp dụng rule từ chối cho những
hành động thật sự không có skill đề xuất tương ứng (mở thẻ, khoá thẻ...).

**Verify thật với model VNG:** chạy lại đúng 3 lần câu "Tạo giúp tôi 1 hũ
mua sắm hợp lý mỗi tháng." (3 thread mới, cô lập) sau khi sửa → **3/3 lần
đều trả về đúng `create_jar`**, không còn từ chối. 67/67 test pass
(`uv run --group dev pytest tests/`).

**Lưu ý còn treo (đã cập nhật — xem vòng fix thứ 2 bên dưới):** ~~đây là fix
làm giảm tần suất, không đảm bảo 100%~~.

**Vòng fix thứ 2 (2026-09-09, sau khi bạn test lại trên endpoint thật và
báo vẫn từ chối cả 2 câu):** fix vòng 1 ở trên (chỉ thêm 1 đoạn "Ngoại lệ
quan trọng") không đủ mạnh — bạn test lại `create_jar` thì agent chịu tính
số đúng nhưng vẫn nói "ngoài phạm vi hỗ trợ" và bỏ qua khối `ui-json`
(`ui: null`); `edit_jar` thì từ chối hoàn toàn, không tính gì, bảo dùng app
MSB. Viết lại prompt/skill mạnh hơn:

- `instructions.md`: viết lại hẳn đoạn mở đầu — gộp rule "không tự thực
  hiện hành động thật" với 1 đoạn **BẮT BUỘC ĐỌC** nêu rõ nguyên tắc áp
  dụng **ngược lại hoàn toàn** khi có skill chuyên biệt (`transfer-form`,
  `spending-jar`) xử lý đúng yêu cầu — nêu thẳng sai lầm cụ thể đã quan sát
  được (tính đúng số nhưng bỏ qua khối `ui-json` vì tưởng nhầm là "vượt
  quyền hạn").
- `skills/project/spending-jar/SKILL.md`: thêm hẳn 1 mục **"QUAN TRỌNG
  NHẤT — đọc trước tất cả"** ngay sau tiêu đề, giả thuyết nguyên nhân là
  model nhầm "hũ chi tiêu" (tag ngân sách nội bộ) với "sổ/tài khoản tiết
  kiệm" (sản phẩm ngân hàng thật) — nhất là khi tên hũ có chữ "tiết kiệm"
  (mock data có hũ "Tiết kiệm khẩn cấp"). Nói rõ 2 khái niệm khác nhau hoàn
  toàn, và chèn `ui-json` an toàn y hệt viết text.

**Verify thật với model VNG (2026-09-09, endpoint local qua `server.py`,
mỗi câu 1 thread mới cô lập bằng `InMemorySaver`):** chạy lại đúng 2 câu đã
fail trên production — mỗi câu 2 lần:
- "Tạo giúp tôi 1 hũ mua sắm hợp lý mỗi tháng." → **2/2 lần đều trả đúng
  `create_jar`** (`allocation_amount` ~5.400.000đ, có `reason` dựa số liệu
  thật), không còn từ chối, không còn "ngoài phạm vi hỗ trợ".
- "Tăng hũ giải trí của tôi lên 800 nghìn được không?" → **2/2 lần đều trả
  đúng `edit_jar`** (đọc đúng hũ "Giải trí" có sẵn 600.000đ trong `jars`,
  đề xuất tăng lên 800.000đ), không còn từ chối.

4/4 lần test thật đều đạt, không còn tái hiện triệu chứng đã báo. 67/67
test pass (`uv run --group dev pytest tests/`).

**Lưu ý còn treo:** đây vẫn là fix ở tầng prompt/skill, không có gì enforce
cứng bằng code — bản chất non-determinism của model vẫn còn (giống
chart/transfer_form). 4/4 là mẫu nhỏ; nếu sau này bạn test lại trên
production và vẫn thấy từ chối tái diễn, cân nhắc thêm: (a) test với nhiều
cách diễn đạt câu hỏi khác (ra lệnh trực tiếp vs hỏi tư vấn, câu dài/phức
tạp hơn), (b) áp dụng phòng ngừa tương tự cho `transfer-form/SKILL.md`
(hiện được báo là đã hoạt động đúng, nhưng cùng chung `instructions.md` nên
có thể chung rủi ro), (c) nếu tần suất từ chối trên production vẫn cao dù
đã fix, khả năng phải cân nhắc quay lại dùng tool cho các bước chuẩn bị dữ
liệu (không chỉ dựa hoàn toàn vào prompt).

### 1.10. [Đã fix — cải thiện lớn] Agent phản hồi quá chậm (10s-590s/câu) trên GreenNode Runtime

**Sự cố (2026-09-13, báo trực tiếp):** agent mất quá nhiều thời gian để trả
lời, đặc biệt câu hỏi cần nhiều bước — có lúc lên tới gần 10 phút cho 1 câu
hỏi (`budget_plan`, tính năng đã bị mất trong 1 lần revert khác, không còn
để tham chiếu lại được). Bạn hỏi liệu tắt xác thực Auth0 có giúp được
không.

**Đã điều tra loại trừ Auth0/Runtime trước khi sửa gì:**
- Đo riêng bước lấy JWT Auth0: ~420-460ms — không đáng kể so với tổng thời
  gian request (10s-590s).
- So sánh cùng câu hỏi qua endpoint thật (có Auth0+Runtime) vs. gọi local
  trực tiếp (bỏ qua hẳn Auth0+Runtime): 2 cách cho thời gian gần như nhau
  (chênh vài giây, trong khoảng nhiễu bình thường) → **xác nhận Auth0/
  Runtime không phải nguyên nhân**, tắt đi sẽ không giải quyết được gì,
  chỉ mất 1 lớp bảo mật miễn phí.

**3 nguyên nhân thật đã tìm ra, đã fix cả 3:**

1. **Mỗi skill tự chia việc đọc `/customer_data.json` thành nhiều lượt
   `read_file`/`grep` riêng biệt** — dù dữ liệu đã được `SeedCustomerContext`
   nạp sẵn vào virtual filesystem từ đầu turn (`before_agent`), agent vẫn
   phải tốn 1 round-trip LLM riêng cho MỖI lần gọi `read_file` (tool-calling
   loop kiểu ReAct: mỗi tool call = 1 lượt LLM riêng, không có cách nào né
   được, kể cả khi bản thân việc đọc file cực nhanh vì chỉ đọc từ RAM).
   - **Fix:** `middleware/seed_customer_context.py` — thêm
     `wrap_model_call`/`awrap_model_call`, nhúng thẳng nội dung
     `customer_data.json` (~16-18KB/khách hàng, ~4-5k token) vào system
     message của MỌI lượt gọi LLM, lấy lại từ `request.state["files"]`
     (không đọc lại đĩa). Vẫn giữ `before_agent` seed vào virtual
     filesystem (để dùng `grep` khi cần). Đồng thời sửa `instructions.md`
     + `SKILL.md` của `spending-jar`/`transfer-form` để bỏ chỉ dẫn
     `read_file`/`grep` cho `/customer_data.json` (nếu không sửa, model vẫn
     có thể tự gọi lại theo thói quen dù dữ liệu đã có sẵn).
2. **Model GLM (`z-ai/glm-5.2-hackathon` qua VNG MaaS) mặc định bật
   "thinking"/reasoning**, sinh ra lượng token suy luận nội bộ rất lớn bị
   strip bỏ hoàn toàn ở `text_utils._strip_think_tags()` — không ai nhìn
   thấy, không dùng để làm gì, nhưng vẫn tốn thời gian sinh ra. Verify
   bằng raw API call: câu "Xin chào" đơn giản sinh **170 completion_tokens,
   trong đó 111 token (~65%) là `reasoning_tokens`**.
   - **Fix:** `server.py`'s `_default_model()` — thêm
     `extra_body={"thinking": {"type": "disabled"}}` vào `ChatOpenAI`. Đã
     verify đúng tên tham số bằng cách gọi raw API trực tiếp (2 tên tham số
     phổ biến khác — `enable_thinking`, `chat_template_kwargs.enable_thinking`
     — bị model lặng lẽ bỏ qua, không có tác dụng). Kết quả: câu "Xin chào"
     giảm từ 8.33s → 4.91s (reasoning_tokens: 111 → 0).
3. **Chưa có cách xem agent chậm ở bước nào** — thêm
   `middleware/audit.py`'s `LogModelCalls` (mới, đo thời gian mỗi lượt gọi
   LLM) bên cạnh `LogToolCalls` đã có (giờ đo luôn thời gian mỗi tool call,
   trước đây chỉ in tên). Không cần dependency ngoài, in thẳng ra server
   log. Xác nhận qua log thật: **tool call (`read_file`) tốn 0.00-0.01s,
   100% thời gian nằm ở chính lượt gọi LLM** — không phải do overhead
   tool-execution.

**Kết quả benchmark (local, 3 lần sửa cộng dồn):**

| Câu hỏi | Gốc | + Sửa (1) | + Sửa (1)+(2) |
|---|---|---|---|
| "Xin chào" (không tool) | 10.03s | 8.31s | **6.81s** |
| Tạo 1 hũ (`create_jar`, 1 skill) | 28.68s (2 lần `read_file`) | 25.05s (1 lần `read_file`) | **17.20s** |
| Hỏi chi tiêu tháng này (Q&A thường) | ~10s (luôn cần `read_file`) | — | **5.71s** (0 tool call) |

`create_jar` giảm tổng **~40%** (28.68s → 17.20s). Đã verify chất lượng
đầu ra không bị ảnh hưởng: `create_jar` vẫn ra đúng `ui-json` hợp lệ, số
liệu tính đúng; câu hỏi Q&A vẫn trả lời chính xác, ngắn gọn đúng
`instructions.md`. 67/67 test pass.

**Chưa làm/còn treo:**
- [ ] Chưa deploy lại lên GreenNode Runtime — mọi số liệu trên là **local
  only**, cần build lại Docker image + deploy để production thực sự nhanh
  hơn.
- [ ] `budget-plan` (skill nặng nhất, ~8 tool call, từng mất ~590s) đã bị
  mất trong 1 lần revert khác trong session này — chưa đo lại được mức cải
  thiện thật cho trường hợp nặng nhất (dự kiến cải thiện còn lớn hơn nhiều
  so với `create_jar` vì tỉ lệ nghịch với số `read_file` đã tiết kiệm được).
- [x] **[Đã fix]** LangSmith đã hoạt động đúng sau khi bạn cập nhật lại
  `LANGSMITH_API_KEY` (lỗi `401` trước đó do key sai/thiếu, không phải do
  code). Verify: request thật gửi trace thành công tới project
  `pfm-agent-local` (local) và `pfm-agent-prod` (bạn tự thêm biến môi
  trường cho GreenNode Runtime, không do mình làm) — cả 2 đều nhận trace
  bình thường, không thấy tracing làm chậm response (thời gian
  `TOTAL`/`Model call` khớp với baseline không bật tracing).
- [x] **[Đã test] Đánh giá việc tắt "thinking" có ảnh hưởng chất lượng
  không — so sánh trực tiếp thinking BẬT vs TẮT trên 3 câu khó hơn**
  (`transfer_form` — trả nợ 20 triệu; `chart` — phân tích chi tiêu; so sánh
  % chi tiêu tháng 7 vs tháng 8, cần cộng/trừ/chia nhiều bước), mỗi câu 1
  agent riêng (`ChatOpenAI` với/không `extra_body={"thinking": {"type":
  "disabled"}}"`), tự đối chiếu số liệu trả về với dữ liệu gốc
  (`monthly_spending_summary`, `statements`, `account.balance_vnd`).
  - **`transfer_form`:** cả 2 config đều từ chối đề xuất (đúng — tài khoản
    thanh toán chỉ có 12.500.000đ, không đủ cho khoản 20 triệu định trả),
    cùng trích dẫn đúng số liệu (dư nợ 34.500.000đ, kỳ sao kê 21.400.000đ
    hạn 10/08, số dư 12.500.000đ). Thinking tắt: 13.76s; thinking bật:
    70.89s.
  - **`chart`:** số liệu **giống hệt tuyệt đối** giữa 2 config (Mua sắm
    5.130.000 / Siêu thị 2.870.000 / Ăn uống 2.585.000 / Di chuyển
    2.100.000 / Hoá đơn 900.000 / Giải trí 599.000 — khớp đúng
    `by_category_vnd` tháng 8), chỉ khác `chart_type` (pie vs bar, không
    sai). Thinking tắt: 17.86s; thinking bật: 42.93s.
  - **So sánh % 2 tháng:** cả 2 tính đúng (tự verify lại: giảm 6.630.000đ,
    ≈ −31,86% chính xác — thinking tắt làm tròn "−32%", thinking bật
    "−31,8%", cả 2 chấp nhận được). Thinking tắt còn tính đúng cả breakdown
    theo danh mục (Di chuyển −5.000.000đ, Ăn uống −880.000đ — khớp chính
    xác dữ liệu gốc) dù trả lời ngắn gọn hơn hẳn thinking bật (bảng đầy đủ
    mọi danh mục). Thinking tắt: 8.43s; thinking bật: 23.26s.
  - **Kết luận:** không phát hiện lỗi tính toán/logic nào khi tắt thinking
    trên cả 3 câu — mọi số liệu khớp chính xác dữ liệu gốc ở cả 2 config,
    kết luận tài chính giống nhau. Khác biệt duy nhất là mức độ chi tiết
    trình bày (thinking bật viết dài/đầy đủ bảng hơn — thinking tắt ngắn
    gọn hơn, thực ra khớp tốt hơn với yêu cầu "trả lời ngắn gọn" đã thêm ở
    mục trước). Tốc độ nhanh hơn 2.4x-5.1x tuỳ câu.
  - **Thận trọng:** mẫu nhỏ (3 câu, mỗi câu 1 lần chạy, không phải benchmark
    thống kê) — không loại trừ hoàn toàn khả năng có trường hợp phức tạp
    hơn mà reasoning giúp tránh sai sót. Nên tiếp tục quan sát trên
    production sau khi deploy, đặc biệt câu hỏi nhiều bước tính toán hơn.

### 1.11. [Đã fix — quan trọng nhất trong đợt tối ưu hiệu năng] `checkpointer.get_tuple()` bị gọi lặp 100+ lần mỗi request trên thread đã dùng lâu

**Phát hiện (2026-09-13, từ chính trace LangSmith bạn gửi):** 1 câu "Xin
chào" đơn giản trên thread `CIF_0001` thật (đã tích luỹ nhiều lịch sử qua
cả phiên làm việc này) mất **57.41s** theo LangSmith, nhưng `model` (lời
gọi LLM thật) chỉ chiếm **6.27s**. ~50.77s còn lại nằm **trước cả
`before_agent` hook đầu tiên** — tức ngoài mọi span được trace, xảy ra
ngay trong bước LangGraph tự load state của thread trước khi graph bắt
đầu chạy.

**Điều tra sâu (đo trực tiếp, không phải suy đoán):**
- `agent.get_state(config)` trên `CIF_0001` (51 message tích luỹ): **65.92s**.
- Instrumented `agent.checkpointer.get_tuple`: được gọi **111 lần** trong
  đúng 1 lần `get_state()` (hoặc `invoke()`) — khớp với 111 checkpoint đã
  tích luỹ trên thread này qua cả phiên. Tổng 64.43s, trung bình ~0.55-1.0s
  mỗi lần.
- Vì sao cần gọi nhiều lần: kênh `messages` trong LangGraph dùng cơ chế
  reducer (accumulate qua nhiều checkpoint) — không có 1 checkpoint đơn lẻ
  nào chứa đủ danh sách message đầy đủ (đã verify: quét cả 116 checkpoint,
  0 checkpoint nào có `messages` trong `channel_values` riêng lẻ) — về
  nguyên tắc LangGraph cần duyệt cả chuỗi để reduce lại. **Đây không phải
  bug của LangGraph.**
- **Bug thật nằm ở `AgentBaseMemoryEvents.get_tuple()`** (package
  `greennode-agent-bridge`): mỗi lần được gọi trong chuỗi 111 lần đó, nó
  lại tự `get_events()` **fetch lại TOÀN BỘ 460 events từ network + parse
  lại từ đầu**, dù dữ liệu không đổi giữa các lần gọi liên tiếp này. Có
  sẵn cơ chế `_local_cache` (TTL 30s) trong code nhưng KHÔNG được dùng để
  bỏ qua bước fetch — chỉ dùng để so sánh "cái nào mới hơn". Verify: fetch
  1 lần duy nhất (460 events, 5 trang phân trang) chỉ mất **0.95-1.16s** —
  network/GreenNode Memory tự nó không chậm, vấn đề là gọi lặp 111 lần một
  cách lãng phí.

**Đã fix (trong repo, không cần sửa gì phía GreenNode):** `checkpointer_cache.py`
(mới) — bọc `checkpointer.checkpoint_event_client.get_events` bằng cache
TTL rất ngắn (2 giây, chặt hơn nhiều so với TTL 30s mặc định của GreenNode
Memory nên không tăng thêm rủi ro đọc dữ liệu cũ giữa các request thật
khác nhau — chỉ đủ để hấp thụ 111 lần gọi dồn dập trong CÙNG 1 lần
`invoke()`/`get_state()`, vốn hoàn tất trong &lt;1s sau khi cache). Gắn vào
`server.py`'s `build_agent()` ngay sau khi tạo checkpointer — no-op an
toàn với `InMemorySaver` (test/notebook, không có
`checkpoint_event_client`). 4 test mới trong
`tests/test_checkpointer_cache.py` (no-op khi thiếu attribute, cache
đúng theo TTL, tách cache theo từng thread/actor, hết hạn đúng lúc). 71/71
test pass.

**Kết quả verify thật (qua đúng `server.build_agent()`, trên `CIF_0001`
thật, 51 message tích luỹ, KHÔNG xoá lịch sử):**

| | Trước | Sau |
|---|---|---|
| `GET /chat/history` (`get_state`) | 65.92s | **0.97s** (~68 lần) |
| `POST /chat` (`invoke`) | ~70s | **6.17s** (~11 lần, về đúng mức baseline thread mới) |

Dữ liệu vẫn đúng cả 2 (51 message giữ nguyên, câu trả lời hợp lý) — đây là
**mức cải thiện lớn nhất trong toàn bộ đợt tối ưu hiệu năng này**, vì nó
giải quyết đúng phần chiếm 88-90% tổng thời gian trên thread đã dùng lâu —
lớn hơn nhiều so với việc gộp system-prompt (~13-40%) hay tắt reasoning
(~2.4x-5.1x, nhưng đo trên thread ít lịch sử).

**[Cập nhật 2026-09-13] Đã nâng cấp từ TTL cố định sang cache theo phạm vi
request** (đúng hướng "tốt hơn" đã đề xuất trong
[`docs/incidents/2026-09-13-greennode-memory-checkpointer-perf.md`](docs/incidents/2026-09-13-greennode-memory-checkpointer-perf.md)):
`checkpointer_cache.py` viết lại — bỏ TTL 2 giây "đoán", thay bằng
`invalidate(checkpointer, session_id, actor_id)` gọi rõ ràng ở đầu cả 3
handler (`POST /chat`, `GET /chat/history`, `DELETE /chat/history`) trong
`server.py`, xoá đúng cache của thread đó trước khi đọc/ghi — đảm bảo lần
fetch đầu tiên mỗi request luôn thật, không còn phải đoán "bao nhiêu giây
là đủ". Vẫn giữ TTL 60s làm lưới an toàn cho nơi nào lỡ quên gọi
`invalidate()`. 74/74 test pass (6 test mới, bao gồm test riêng cho
`invalidate()`).

Verify lại trên `CIF_0001` thật (qua đúng `invalidate()` + `get_state()`/
`invoke()` như handler thật làm): `GET /chat/history` **1.19s** (từ
~65.92s), `POST /chat` **6.71s** (từ ~70s) — giữ nguyên mức cải thiện,
đúng dữ liệu.

**Phát hiện thêm trong lúc verify (KHÔNG phải do fix này gây ra — là hạn
chế có sẵn của GreenNode Memory, chỉ vô tình bị lộ rõ hơn):** gọi
`GET /chat/history` **ngay lập tức** (dưới 1 giây) sau 1 `POST /chat` vừa
ghi xong có lúc tạm thời **thiếu đúng 2 tin nhắn vừa ghi** — dù đã
`invalidate()` đúng, ép fetch 100% từ network (không phải do cache phía
mình). Thử lại vài giây sau (tiến trình khác) thấy đủ dữ liệu, ổn định.
→ GreenNode Memory có độ trễ ghi→đọc (write-then-read lag) ngắn — cùng
bản chất với race condition 30 giây đã ghi nhận riêng cho `DELETE` ở mục
1.5, giờ xác nhận **cũng ảnh hưởng cả luồng ghi/đọc bình thường**.
**Khuyến nghị cho frontend:** sau `POST /chat` thành công, hiển thị trực
tiếp `answer` từ chính response đó — không gọi lại `GET /chat/history`
ngay sau để refresh (chỉ dùng `GET /chat/history` cho việc mở lại 1 cuộc
hội thoại cũ, ví dụ mở lại app).

**Lưu ý còn treo:**
- [ ] Đây vẫn là workaround, không phải fix triệt để — bug gốc nằm trong
  package `greennode-agent-bridge` (không cache fetch giữa các lần gọi
  liên tiếp trong `get_tuple()`) VÀ độ trễ ghi→đọc nằm ở chính backend
  GreenNode Memory (không sửa được từ client). Nên báo GreenNode biết cả
  2 vấn đề để họ tự fix ở tầng SDK/backend; nếu họ fix, cân nhắc gỡ
  workaround `checkpointer_cache.py` sau.
- [ ] Concurrency edge case chưa test: 2 request thật đến gần như đồng
  thời trên CÙNG thread (ví dụ user bấm gửi 2 tin nhắn rất nhanh) — về lý
  thuyết `invalidate()` của request sau có thể xoá cache ngay giữa lúc
  request trước đang fetch, gây fetch thừa (không sai dữ liệu, chỉ lãng
  phí nhẹ) — chấp nhận được, chưa cần xử lý thêm.
- [ ] Chưa deploy lên GreenNode Runtime — số liệu trên đo local (dùng
  đúng `MEMORY_ID`/checkpointer thật, không phải mock) nhưng qua code
  chưa build lại Docker image/deploy.

### 1.12. [Đã làm — mở rộng scope] `transfer-form` giờ hỗ trợ thêm chuyển tiền cho 1 người (không chỉ trả nợ thẻ)

**Yêu cầu (2026-09-14, trực tiếp):** trước đó `transfer-form` chỉ hỗ trợ
trả nợ thẻ tín dụng của chính khách hàng (xem quyết định scope cũ ở trên,
mục "Phạm vi hiện tại") — bạn muốn mở rộng để hỗ trợ câu như "Chuyển tiền
cho Toàn 500 nghìn với nội dung Thanh toán tiền ăn" (chuyển P2P cho 1
người, không phải trả nợ thẻ).

**Vấn đề an toàn đã nêu trước khi làm:** `/customer_data.json` không có
dữ liệu nào xác nhận 1 người nhận bất kỳ là có thật — nếu agent tự bịa
`account_number` cho 1 cái tên bất kỳ, rủi ro cao hơn nhiều so với bịa số
liệu chart (tiền thật có thể chuyển sai người nếu khách hàng không để ý
mà vẫn bấm xác nhận).

**Quyết định (theo yêu cầu trực tiếp, tạm thời cho demo):**
- Thêm trường `beneficiaries` (danh bạ người nhận đã lưu) vào
  `data/customers/CIF_000{1,2,3}.json` — **hardcode tạm thời**, CIF_0001
  có 1 entry mẫu (`{"name": "Toàn", "account_number": "00012000321",
  "bank_name": "Techcombank"}`), CIF_0002/0003 để rỗng `[]`.
- `skills/project/transfer-form/SKILL.md` viết lại — giờ có 2 trường hợp:
  (A) trả nợ thẻ (như cũ), (B) chuyển cho 1 người — CHỈ đề xuất nếu tên
  khớp đúng 1 entry trong `beneficiaries`, hoặc khách hàng tự cung cấp đủ
  số tài khoản/ngân hàng trong câu hỏi. Nếu tên không khớp và khách hàng
  không tự cho số tài khoản: **không chèn `ui-json`, hỏi lại** — không bao
  giờ tự bịa.
- `tests/data/test_customer_data.py` — thêm `beneficiaries` vào top-level
  key bắt buộc + `test_beneficiaries_have_required_fields`.
- `docs/transfer-form.md` viết lại (2 trường hợp, cảnh báo rủi ro cao hơn
  cho trường hợp B) + sync sang `PersonalCardAgentUI/agent_backend_docs/`.
- **Không cần đổi `text_utils.py`** — schema `transfer_form` (4 field)
  không đổi, chỉ đổi ý nghĩa `recipient`/`account_number` tuỳ trường hợp.
- **Verify thật với model VNG (local):** "Chuyển tiền trả nợ thẻ giúp
  tôi."/"Tôi cần trả nợ thẻ." (trường hợp A, không nêu tên thẻ) → cả 2 lần
  đều tự đề xuất đúng thẻ Visa Signature ngay, không hỏi lại. 74/74 test
  pass. **Chưa verify riêng trường hợp (B)** (câu "Chuyển tiền cho Toàn
  500 nghìn...") bằng model thật — nên test trước khi tin tưởng hoàn toàn.

**⚠️ Việc cần làm sau (đã ghi chú theo đúng yêu cầu, KHÔNG làm ngay bây
giờ):** `beneficiaries` hiện là danh sách **hardcode tĩnh trong file mock**
— cần 1 tool đọc danh bạ người nhận **thật, realtime** từ hệ thống PFM/core
banking ngoài (tương tự `list_existing_jars()` đã note ở mục Roadmap PFM
cho `spending-jar`) khi có API thật. Khi có tool này: sửa lại `SKILL.md` để
gọi tool thay vì đọc `beneficiaries` tĩnh trong `/customer_data.json`.

**[Cập nhật 2026-09-14] Verify trường hợp (B) — phát hiện + fix thêm 1 bug
từ chối, cùng mẫu với mục 1.9:**

- **Sự cố:** verify trên endpoint production (đã deploy bản mở rộng scope)
  — hỏi "Chuyển tiền cho Toàn 500 nghìn với nội dung Thanh toán tiền ăn" →
  agent **tự tra đúng `beneficiaries`, tìm đúng số tài khoản/ngân hàng**,
  nhưng chỉ liệt kê thông tin đó bằng text rồi từ chối: *"Mình không hỗ
  trợ chuyển tiền cho người khác, bạn vui lòng thực hiện qua app ngân
  hàng..."* — không chèn khối `ui-json`, `ui: null`. Đúng mẫu bug đã gặp ở
  mục 1.9 cho `create_jar`/`edit_jar` (tính đúng số nhưng bỏ qua bước chèn
  `ui-json` vì tưởng nhầm là "vượt quyền hạn") — lần này xảy ra với
  `transfer-form` trường hợp (B), có lẽ vì "chuyển tiền cho người khác"
  nghe giống hành động rủi ro hơn hẳn so với trả nợ thẻ của chính mình,
  nên dễ kích hoạt bản năng từ chối của model hơn.
- **Nguyên nhân:** `transfer-form/SKILL.md` (bản viết lúc mở rộng scope)
  **chưa có** đoạn "QUAN TRỌNG NHẤT — đọc trước tất cả" chống từ chối như
  đã thêm cho `spending-jar` ở mục 1.9 vòng 2 — chỉ dựa vào đoạn chung ở
  `instructions.md`, chưa đủ mạnh cho trường hợp cụ thể này.
- **Đã fix:** thêm đúng đoạn "QUAN TRỌNG NHẤT" (theo pattern đã dùng cho
  `spending-jar`) vào đầu `transfer-form/SKILL.md`, nêu thẳng sai lầm cụ
  thể đã quan sát được (tính đúng số tài khoản nhưng chỉ liệt kê bằng text
  rồi từ chối, không chèn `ui-json`).
- **Verify lại (local, 3 lần):** "Chuyển tiền cho Toàn 500 nghìn với nội
  dung Thanh toán tiền ăn" → **3/3 lần đều đúng**, tạo `transfer_form` hợp
  lệ (Toàn, 00012000321, Techcombank, 500.000đ), không còn từ chối. 77/77
  test pass.
- **Lưu ý còn treo:** cũng gặp 1 lần `HTTP 500` trên production ngay sau
  khi `DELETE /chat/history` rồi hỏi lại quá sớm (trong vòng ~30s, đúng
  race condition đã ghi ở mục 1.5) — không tái hiện lại được lỗi 500 này
  riêng biệt ở local, nên chưa chắc chắn đây là do race condition đơn
  thuần hay có thêm nguyên nhân khác; cần tiếp tục quan sát nếu tái diễn.
  Vẫn chưa deploy lại bản có đoạn "QUAN TRỌNG NHẤT" mới này lên production
  — cần build/deploy rồi test lại lần cuối trên endpoint thật.

### 1.13. [Đã làm] Thêm tool thật cho `list_existing_jars()`/`query_beneficiaries()` — không còn đọc snapshot tĩnh

**Yêu cầu (2026-09-16, trực tiếp):** thay vì để `jars`/`beneficiaries` chỉ
là field tĩnh trong `data/customers/CIF_000X.json` (bị nhúng thụ động vào
system prompt), làm đúng 2 tool đã note từ trước ở mục Roadmap PFM
(`list_existing_jars()` cho `spending-jar`, `query_beneficiaries()` cho
`transfer-form`) — trả kết quả mock nhưng qua 1 lời gọi tool thật, và
**CIF phải tự lấy từ context của request, không để model tự truyền vào
tham số**.

**Đã làm:**
- `tools/customer_data_tools.py` (mới) — 2 tool `list_existing_jars()`/
  `query_beneficiaries()`, **không nhận tham số nào từ model** — tự lấy
  `customer_id` qua `_resolve_customer_id()` (tái dùng đúng helper
  `SeedCustomerContext` đang dùng), đúng pattern đã áp dụng cho
  `tools/memory_tools.py`'s `actor_id`. Dữ liệu mock **hardcode thẳng
  trong file này** (dict `_MOCK_JARS`/`_MOCK_BENEFICIARIES` khoá theo
  `customer_id`) — **không đọc file JSON riêng nào khác** (thử phương án
  tách sang `data/jars.json`/`data/beneficiaries.json` trước, bị yêu cầu
  sửa lại vì không cần thiết — bỏ ngay, hardcode trực tiếp trong
  `tools/`).
- Đăng ký cả 2 tool vào `server.py`'s `build_agent()` (mặc định cùng
  `remember_preference`/`recall_preference`).
- **Xoá hẳn `jars`/`beneficiaries` khỏi `data/customers/CIF_000X.json`**
  (cả 3 file) — không còn bị nhúng vào system prompt qua
  `SeedCustomerContext` nữa, model chỉ có thể lấy 2 loại dữ liệu này qua
  đúng 2 tool trên.
- `skills/project/spending-jar/SKILL.md` và
  `skills/project/transfer-form/SKILL.md` — sửa lại Check step: gọi tool
  thay vì đọc `jars`/`beneficiaries` từ `/customer_data.json`.
- Test: `tests/test_customer_data_tools.py` (mới, 10 test — đúng khách
  hàng, không leak chéo dữ liệu, fallback khi thiếu context, cấu trúc
  `_MOCK_JARS`/`_MOCK_BENEFICIARIES` hợp lệ) +
  `tests/data/test_customer_data.py` cập nhật (xác nhận `jars`/
  `beneficiaries` **không còn** trong customer file). **92/92 test pass.**
- **Verify thật với model VNG (local):**
  - "Tăng hũ giải trí của tôi lên 800 nghìn được không?" → gọi đúng
    `list_existing_jars()`, kết quả đúng (Giải trí 600.000đ→800.000đ).
  - "Chuyển tiền cho Toàn 500 nghìn với nội dung Thanh toán tiền ăn" → gọi
    đúng `query_beneficiaries()`, kết quả đúng (Toàn/00012000321/
    Techcombank).
  - Xác nhận trực tiếp: `SeedCustomerContext.before_agent()` seed vào
    system prompt **không còn** chứa `jars`/`beneficiaries`.
  - Gặp 1 lần lỗi `403 ModelArts.81011` ("Output text May contain
    sensitive information") khi test câu hũ — **không liên quan** tới thay
    đổi này, đúng lỗi content-filter không tất định của VNG ModelArts đã
    biết từ trước (đã quyết định không sửa) — thử lại thành công ngay.

**Lưu ý còn treo:** vẫn là mock (dữ liệu hardcode trong code, không nối
PFM/core-banking thật) — khi có API thật, chỉ cần sửa nội dung bên trong
2 hàm tool này (thay `_MOCK_JARS.get(...)`/`_MOCK_BENEFICIARIES.get(...)`
bằng lời gọi API thật), không cần đổi gì ở `SKILL.md`/`server.py` vì
interface tool đã đúng hình dạng. Chưa deploy lên GreenNode Runtime.

**Cập nhật 2026-09-18 — `query_beneficiaries()` đã nối API thật, xem
mục 1.14.** `list_existing_jars()` vẫn còn mock (chưa nối
`GET /api/jars?cif=`), ngoài scope của 1.14.

### 1.14. [Đã làm] `query_beneficiaries()` nối API thật của `pfm` + schema mới `beneficiary_id`/`category` cho transfer_form

**Yêu cầu (2026-09-18, trực tiếp):** user thêm `backend_docs/pfm-read-api.md`
— tài liệu 2 endpoint GET thật do repo `pfm` (Next.js) expose
(`/api/jars?cif=`, `/api/beneficiaries?cif=`), và 1 schema `ui.type:
"transfer_form"` MỚI cho trường hợp (B) (chuyển cho người trong danh bạ):
thay vì agent tự trả `recipient`/`account_number`, giờ chỉ trả đúng
`beneficiary_id` (khớp `id` trong `GET /api/beneficiaries`) + `category`
(1 trong 10 giá trị cố định) — `pfm` tự tra tên/số tài khoản/ngân hàng thật
từ `beneficiary_id`, tránh agent hallucinate số tài khoản. Yêu cầu: sửa
`transfer-form` để lấy toàn bộ danh sách người nhận đã lưu trước (không
phải tìm 1 người), và thêm option vào notebook để user tự test.

**Đã làm:**
- `tools/customer_data_tools.py`'s `query_beneficiaries()` — bỏ hẳn
  `_MOCK_BENEFICIARIES`, gọi thật `GET {PFM_BASE_URL}/api/beneficiaries?cif=`
  qua `httpx` (không dùng `requests` — `httpx` là thư viện đã chắc chắn có
  mặt ở CẢ 2 môi trường cài đặt của repo, xem README's `.venv-server` note;
  `requests` chỉ có mặt transitively trong env `uv` chính, không đảm bảo có
  trong env server). Trả về text có kèm `id` mỗi người
  (`- {name} (id: {id}): STK {accountNumber} ({bankName})`) để model có
  thể dùng làm `beneficiary_id`. Lỗi mạng/HTTP → trả 1 câu tiếng Việt báo
  hệ thống gián đoạn thay vì crash/tự bịa dữ liệu (`httpx.HTTPError` bắt
  chung cho cả lỗi kết nối lẫn status lỗi qua `raise_for_status()`).
  `list_existing_jars()`/`_MOCK_JARS` giữ nguyên (ngoài scope yêu cầu này).
- `text_utils.py`'s `_is_valid_transfer_form()` — giờ chấp nhận **2 dạng
  schema riêng biệt**: dạng cũ (`recipient`+`account_number`, cho trường
  hợp A và trường hợp B khi khách tự cho đủ thông tin người không có trong
  danh bạ) và dạng mới (`beneficiary_id`+`category`, validate `category`
  khớp đúng 1 trong 10 giá trị cố định). Có field `beneficiary_id` mà vẫn
  còn `recipient`/`account_number` trong cùng payload → reject (không cho
  trộn 2 dạng).
- `skills/project/transfer-form/SKILL.md` — viết lại phần Phạm vi/Quy
  trình/Schema/PHẢI/KHÔNG ĐƯỢC/Ví dụ cho trường hợp (B): Check step giờ
  nói rõ gọi `query_beneficiaries()` để lấy **toàn bộ** danh sách trước
  (không phải chỉ tìm 1 người), Propose dùng đúng `beneficiary_id` (không
  còn tự điền số tài khoản/ngân hàng cho người có trong danh bạ), thêm
  bảng gợi ý suy luận `category` từ nội dung chuyển khoản (tiền ăn →
  `dining`, tiền nhà → `housing`, v.v., mặc định `shopping` nếu không suy
  luận được), thay ví dụ cũ ("Toàn"/Techcombank, đã lỗi thời) bằng ví dụ
  dùng dữ liệu thật (Nguyễn Thị Lan/MSB cho CIF_0001) + thêm ví dụ SAI mới
  (trộn schema, thiếu/sai `category`).
- `docs/transfer-form.md` (+ sync sang
  `PersonalCardAgentUI/agent_backend_docs/transfer-form.md`) — viết lại
  toàn bộ để mô tả 2 dạng schema cho frontend, ví dụ response mới, và cập
  nhật cảnh báo độ tin cậy (rủi ro hallucinate số tài khoản đã giảm ở dạng
  `beneficiary_id`, nhưng `source` của beneficiary vẫn có thể là
  `self_reported`/`estimated`, chưa xác thực ngân hàng thật).
- `tests/test_customer_data_tools.py` — viết lại toàn bộ phần test
  `query_beneficiaries()` để mock `httpx.get` (`monkeypatch`) thay vì đọc
  dict mock trực tiếp: trả đúng dữ liệu API, danh sách rỗng, đúng
  `cif=actor_id` trong query param, thông báo lỗi thân thiện khi mạng lỗi.
- `tests/test_text_utils.py` — thêm 5 test cho dạng schema mới
  (`beneficiary_id`/`category` hợp lệ, thiếu `category`, `category` sai,
  `beneficiary_id` rỗng, trộn 2 dạng schema).
- `notebooks/try_agent.ipynb` — thêm **Option F** (test case B qua API
  thật), sửa lại mô tả lỗi thời của Option D (không còn "chỉ hỗ trợ trả nợ
  thẻ") và Option E (`list_existing_jars()` giờ là tool thật, không còn
  "chưa xây").
- Thay các test đọc `_MOCK_BENEFICIARIES` trực tiếp bằng test mock
  `httpx.get`, cộng thêm test schema mới ở `test_text_utils.py` — **93
  test, `uv run --group dev pytest tests/ -q` pass toàn bộ** (giữ nguyên
  tổng số so với trước, vì bỏ bớt test cấu trúc mock cũ và thêm test mới
  với số lượng tương đương).
- **Verify thật với model VNG (local, `server.build_agent()` +
  `InMemorySaver`, gọi thật `GET /api/beneficiaries?cif=CIF_0001` trên
  endpoint pfm thật):**
  - "Chuyển tiền cho Lan 500 nghìn với nội dung Thanh toán tiền ăn." → gọi
    đúng `query_beneficiaries()` (API thật trả 3 người: Nguyễn Thị Lan/
    Trần Văn Bình/Chủ nhà Phạm Văn Đức), khớp đúng "Lan", đề xuất đúng
    `{"type": "transfer_form", "beneficiary_id": "b_stable_lan", "amount":
    500000, "note": "Thanh toan tien an", "category": "dining"}` — không
    tự bịa số tài khoản.
  - "Tôi nên trả nợ thẻ Visa Signature bao nhiêu?" (trường hợp A) → vẫn
    đúng schema cũ `recipient`/`account_number`, không bị ảnh hưởng bởi
    thay đổi.
  - "Chuyển tiền cho Nam Anh 200 nghìn..." (tên không có trong danh bạ) →
    đúng hành vi: liệt kê 3 người thật đang có, hỏi lại số tài khoản/ngân
    hàng, KHÔNG chèn `ui-json` (không bịa).

**Lưu ý còn treo:**
- `list_existing_jars()` vẫn mock — `GET /api/jars?cif=` có sẵn nhưng
  chưa nối (ngoài scope yêu cầu này, để làm sau nếu cần).
- Chưa deploy lên GreenNode Runtime — cần deploy + test lại trên endpoint
  thật (bao gồm việc container production có mở được kết nối HTTPS ra
  ngoài tới domain `pfm` hay không — môi trường notebook/pytest local chạy
  được nhưng chưa chắc chắn 100% network policy giống hệt runtime thật).
- Chưa có cơ chế retry/backoff cho lời gọi `httpx.get` tới `pfm` — 1 lần
  lỗi mạng là agent báo luôn "hệ thống gián đoạn", không tự thử lại.
- `pfm-read-api.md` nói `GET /api/jars` cho 1 `cif` chưa từng có hũ nào sẽ
  tự sinh 1 hũ "Khác" mặc định (không lỗi/rỗng) — hành vi tương tự cho
  `/api/beneficiaries` khi cif chưa từng lưu ai chưa được xác nhận (đoán là
  trả mảng rỗng, đã test qua `_fake_beneficiaries_response([])` nhưng chưa
  verify với 1 cif thật sự chưa từng lưu beneficiary nào).

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

- [x] **Câu trả lời của agent đang bị dài quá mức cần thiết — Đã fix
  (2026-09-07).**
  `instructions.md` trước đó **không có bất kỳ hướng dẫn nào** về độ dài/
  phong cách trả lời. Hệ quả quan sát được thật (2 lần, cách nhau — cùng 1
  vấn đề gặp lại):
  - Lần 1: hỏi "Danh mục chi tiêu lớn nhất của tôi là gì?" → agent tự diễn
    giải 2 cách hiểu (tháng hiện tại vs 3 tháng), hiện bảng breakdown đầy
    đủ 6 danh mục cho cả 2, lộ luôn phép kiểm tra tổng, tự thêm gợi ý bán
    chéo — chỉ để trả lời đúng 1 từ "Mua sắm".
  - Lần 2: hỏi "Số dư của tôi là bao nhiêu?" → agent tự diễn giải "số dư"
    theo cả 2 nghĩa (dư nợ vs hạn mức khả dụng), trả lời **2 bảng số liệu
    đầy đủ theo từng thẻ** + 1 đoạn "Lưu ý" phân tích thêm — quá dài, chỉ
    cần 1 câu.
  - **Đã làm:** thêm mục mới "Trả lời ngắn gọn, đúng trọng tâm" vào
    `instructions.md` (ngay trước mục "Trước khi trả lời..."), có ví dụ
    minh hoạ trước/sau dùng đúng ví dụ "số dư" ở trên. 4 nguyên tắc: (1)
    trả lời thẳng vào câu hỏi, chỉ mở rộng khi được hỏi thêm; (2) câu hỏi
    có nhiều nghĩa → chọn nghĩa phổ biến nhất trả lời ngắn gọn rồi hỏi lại
    ngắn 1 câu, không liệt kê hết mọi cách hiểu; (3) không hiện phép tính
    trung gian ra câu trả lời cuối; (4) không tự thêm gợi ý mở rộng trừ
    khi thực sự ngắn gọn và liên quan trực tiếp.
  - **Verify thật với model VNG** (không chỉ đọc code): hỏi lại đúng câu
    "số dư" → trả lời 177 ký tự, đúng số, kết bằng 1 câu hỏi gợi mở ngắn
    (đúng mẫu mong muốn). Test thêm 2 câu khác ("danh mục chi tiêu lớn
    nhất", "tháng này chi tiêu bao nhiêu") → đều ngắn gọn, đúng trọng tâm
    (150–225 ký tự, trước đây dài hơn nhiều).
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
- [ ] **Kết nối MCP tin tức/thông tin bên ngoài** — hiện agent **chỉ** có
  dữ liệu tĩnh của chính khách hàng (`data/customers/*.json`) + bộ nhớ nội
  bộ, hoàn toàn không có nguồn thông tin bên ngoài nào. Use case cụ thể:
  khách hỏi kiểu "so sánh quyền lợi thẻ của tôi với thẻ ngân hàng khác" —
  hiện agent không thể trả lời đúng nghĩa (không biết gì về sản phẩm ngân
  hàng khác), dễ bịa hoặc từ chối.
  - **Đã kiểm tra hiện trạng:** `connectors/mcp.py` đã có sẵn 1 ví dụ khai
    báo MCP (`managed_deepagents.connectors.mcp(...)`, hiện trỏ tới
    `docs.langchain.com/mcp` chỉ để minh hoạ) — nhưng đây là API của
    `managed_deepagents`, **chỉ dùng được cho `agent.py`/đường `mda`**,
    chưa wire vào `tools=[...]` của `agent.py`. `server.py` (OSS
    `deepagents`) **không có** API MCP tương đương built-in (đã verify:
    `deepagents` không có gì liên quan "mcp" trong package) — muốn dùng ở
    `server.py` cần thêm thư viện mới, ví dụ `langchain-mcp-adapters`
    (chưa có trong `requirements.txt`), để convert MCP tool thành
    `BaseTool` rồi thêm vào danh sách `tools=[...]` của `build_agent()`.
  - **Việc cần làm:**
    1. Chọn cụ thể 1 nguồn MCP tin tức/dữ liệu tài chính phù hợp (chưa
       chốt — "tin tức" chung chung chưa đủ cụ thể để implement; cần biết
       nguồn nào có dữ liệu quyền lợi/lãi suất/phí thẻ của các ngân hàng
       khác, không chỉ tin tức thời sự thông thường).
    2. Quyết định implement cho `server.py`, `agent.py`, hay cả hai (2 cơ
       chế kỹ thuật khác nhau như ghi ở trên — không dùng chung code được).
    3. Cân nhắc bảo mật/độ tin cậy: thông tin từ MCP là dữ liệu bên ngoài,
       có thể sai/lỗi thời — cần hướng dẫn rõ trong `instructions.md` để
       agent trích dẫn nguồn, không trộn lẫn với dữ liệu tài chính thật của
       khách hàng, và không suy diễn thêm ngoài những gì MCP trả về.
    4. Cập nhật `instructions.md` thêm hướng dẫn khi nào dùng tool MCP mới
       này (ví dụ: chỉ khi câu hỏi thực sự cần so sánh với bên ngoài, không
       dùng cho câu hỏi chỉ liên quan tới dữ liệu nội bộ khách hàng).
    5. Nếu MCP cần API key riêng, thêm env var + fail-fast tương tự các
       tích hợp khác, cập nhật `docker-compose.yml`/CI/README.
    6. Viết test cho tool mới (tương tự pattern `_FakeMemoryClient` đã
       dùng cho `remember_preference`/`recall_preference` — không gọi MCP
       thật trong unit test).
- [ ] **(Chưa ưu tiên)** Cân nhắc tách `instructions.md` thành các skill
  riêng (deepagents có `skills` param + thư mục `skills/` đã có sẵn, hiện
  rỗng) thay vì 1 file monolithic. Hiện tại (~5300 ký tự) **chưa cần** — phần
  lớn nội dung (vai trò, quy tắc đọc data, danh sách nhóm câu hỏi) luôn cần
  cho mọi câu hỏi nên tách ra không có lợi (vẫn phải load mọi lúc). Ứng viên
  hợp lý để tách khi cần: mục ngân sách (khá dài, chỉ cần khi hỏi ngân sách),
  và các mục tool-cụ-thể sắp thêm (Semantic Memory, MCP so sánh ngân hàng
  khác — xem 2 mục ngay trên) — các mục này có hình dạng "cụ thể, ít khi
  cần" hợp làm skill hơn nhồi vào system prompt luôn tải. Đánh đổi: skill
  giúp system prompt gọn/đỡ tốn token, nhưng thêm 1 bước agent phải tự quyết
  định có cần đọc skill đó không — mô tả skill không đủ rõ thì dễ bị bỏ sót,
  bug khó phát hiện hơn so với thiếu hướng dẫn ngay trong system prompt.
  **Mốc để quay lại xem xét:** sau khi làm xong sửa độ dài câu trả lời (mục
  đầu ở trên) + có thể cả Semantic Memory/MCP, nếu `instructions.md` phình
  to gấp đôi hiện tại trở lên thì tách.
- [x] **Visualize dữ liệu (chart) qua skill — chỉ cho 1 vài trường hợp cụ
  thể** (ví dụ user hỏi "phân tích"/so sánh xu hướng/breakdown theo danh
  mục), không phải mọi câu trả lời. **Đã triển khai xong**, đã đọc kỹ docs
  chính thức của deepagents (`docs.langchain.com/oss/python/deepagents/customization`)
  trước khi implement để xác nhận đúng pattern khuyến nghị.
  - **Cơ chế cuối cùng (đã verify thật, không phải middleware-seeding như
    dự tính ban đầu):** vướng kỹ thuật ban đầu là `create_deep_agent(skills=[...])`
    dùng chung `backend` với agent (mặc định `StateBackend`, ephemeral theo
    phiên) — thử seed `SKILL.md` vào `StateBackend` bằng 1 middleware
    (`before_agent`, theo pattern `SeedCustomerContext`) nhưng **không hoạt
    động** (`SkillsMiddleware` báo "No skills available yet", root cause
    không cần điều tra tiếp vì đã đổi hướng). Giải pháp đúng —
    **`CompositeBackend`** (`deepagents.backends`): route `/skills/` sang 1
    `FilesystemBackend(root_dir=<thư mục skills/>, virtual_mode=True)` thật
    (đọc file thật trên đĩa), còn mọi path khác vẫn dùng `StateBackend` mặc
    định như cũ (không đổi hành vi cô lập dữ liệu khách hàng theo
    `SeedCustomerContext`). Đây đúng là pattern chính thức docs khuyến nghị
    cho việc này. `virtual_mode=True` chặn path traversal (`..`, `~`) ra
    ngoài thư mục `skills/` nên an toàn dù dùng `FilesystemBackend` (vốn có
    cảnh báo không nên dùng trực tiếp trong web server) — verify bằng đọc
    source `_resolve_path` của thư viện, root bị scope chặt vào đúng
    `skills/`, không phải toàn bộ repo/đĩa.
  - **Đã chốt (không dùng `response_format`):** model chèn 1 khối code đặc
    biệt (```chart-json```) chứa JSON theo schema cố định **ngay trong text
    trả lời bình thường**, `server.py` tự parse tách ra — không ép toàn bộ
    agent trả structured output.
  - **Đã làm:**
    1. `skills/project/data-visualization/SKILL.md` — mô tả: dùng khi câu
       hỏi cần phân tích xu hướng/so sánh/breakdown theo danh mục-thời gian.
       Schema: `{"chart_type": "bar"|"line"|"pie", "title": str, "labels": [...], "series": [{"name": str, "data": [...]}]}`.
    2. `server.py:build_agent()` — thêm
       `backend=CompositeBackend(default=StateBackend(), routes={"/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True)})`
       + `skills=["/skills/project/"]`.
    3. `text_utils.py` — hàm `extract_chart_block()` (tương tự
       `_strip_think_tags`) tách khối ```chart-json``` khỏi `answer`, parse
       thành field `chart: dict | None` mới trong `ChatResponse`. Không có
       chart hoặc JSON hỏng → `null`, không bao giờ làm vỡ `/chat`.
    4. `docs/api.md` — document field `chart` mới trong response `/chat`.
    5. `docs/chart-visualization.md` (file mới) — tài liệu riêng cho
       frontend: schema đầy đủ, ví dụ payload, code mẫu render bằng
       Chart.js, lưu ý độ tin cậy (không có structured-output enforcement)
       và giới hạn hiện tại (`GET /chat/history` không trả lại `chart` cho
       tin nhắn cũ).
    6. Test: `tests/test_text_utils.py` (3 test mới cho `extract_chart_block` —
       không có block, có block hợp lệ, JSON hỏng) + `tests/test_server.py`
       (1 test mới: fake model trả khối chart-json giả, verify `/chat` tách
       đúng `chart` + `answer` không còn JSON thô). 41/41 test pass
       (`uv run --group dev pytest tests/`).
  - **Chưa làm / cân nhắc sau:** `GET /chat/history` hiện chỉ lọc bỏ khối
    chart-json thô khỏi text lịch sử (để không lộ JSON kỹ thuật ra UI), chưa
    lưu lại field `chart` để trả lại khi xem lại lịch sử cũ — nếu sau này
    cần, phải đổi cách lưu (hiện history được tái tạo từ text message của
    checkpointer, không có chỗ lưu `chart` riêng).

- [x] **Form chuyển tiền điền sẵn (`transfer_form`) qua skill — agent chỉ
  điền form, KHÔNG tự thực hiện giao dịch** (khớp đúng nguyên tắc gốc của
  `instructions.md`: agent chỉ tư vấn/cung cấp thông tin, không hành động).
  **Đã triển khai xong (2026-09-03).**
  - **Phạm vi thu hẹp lại khi implement (khác giả định ban đầu):** chỉ hỗ
    trợ **trả nợ thẻ tín dụng của chính khách hàng** — KHÔNG hỗ trợ chuyển
    tiền cho người khác/merchant như todo gốc từng gợi ý ("chuyển cho
    người nhận đã từng giao dịch"). Lý do: `transactions` trong
    `/customer_data.json` chỉ là lịch sử **chi tiêu thẻ** (mua hàng tại
    merchant), không có lịch sử **chuyển khoản P2P** nào để đối chiếu — đề
    xuất chuyển tiền cho 1 người/merchant bất kỳ sẽ không có cách nào xác
    minh account_number là thật, rủi ro bịa thông tin nguy hiểm hơn nhiều
    so với chart. `recipient`/`account_number` bây giờ luôn là ngân hàng
    phát hành + `card_id` thật của chính khách hàng (lấy từ
    `cards`/`statements`).
  - **Đã làm:**
    1. `text_utils.py` — thêm `_is_valid_transfer_form()`, đăng ký vào
       `_UI_VALIDATORS["transfer_form"]` (tái dùng `extract_ui_block()`
       chung, không cần hàm extract riêng — đúng lợi ích của việc đã gộp
       `chart`/`transfer_form` vào 1 envelope `ui` trước đó).
    2. `tools/transfer_tools.py` (file mới) — tool
       `check_available_balance_or_credit(amount_vnd)`: đọc thật
       `data/customers/<actor_id>.json` (cùng pattern resolve customer_id
       như `SeedCustomerContext`, fallback `CIF_0001` khi không có
       `actor_id`), trả về từng thẻ có đủ hạn mức khả dụng hay không —
       **tool thật, không phải chỉ đọc file qua `read_file`**, vì đây là
       điều kiện chặn cứng cần enforce bằng code (đúng quyết định ở mục
       Scope bên dưới).
    3. `skills/project/transfer-form/SKILL.md` — mô tả rõ phạm vi thu hẹp
       ở trên ngay đầu file, bắt buộc gọi
       `check_available_balance_or_credit` **trước** khi chèn khối
       `ui-json`, schema `{"type": "transfer_form", "recipient", "account_number", "amount", "reason", "note"?}`,
       ví dụ ĐÚNG/SAI theo đúng văn phong `data-visualization/SKILL.md`.
    4. `server.py` — thêm `check_available_balance_or_credit` vào
       `tools=[...]` mặc định của `build_agent()`.
    5. `docs/transfer-form.md` (file mới) + cập nhật `docs/api.md` (liệt
       kê 2 giá trị `ui.type` hiện có: `"chart"`, `"transfer_form"`).
    6. Test: `tests/test_transfer_tools.py` (file mới, unit test tool —
       đủ hạn mức/không đủ hạn mức), `tests/test_text_utils.py` (5 test
       mới cho `_is_valid_transfer_form` qua `extract_ui_block`),
       `tests/test_server.py` (1 test end-to-end: fake model gọi tool rồi
       trả khối `ui-json` transfer_form, verify `/chat` tách đúng). **58/58
       test pass** (`uv run --group dev pytest tests/`).
    7. **Verify thật với model VNG thật** (không chỉ fake model) — hỏi
       "Tôi nên trả nợ thẻ Visa Signature bao nhiêu?" qua `CIF_0001`: model
       tự đọc data, gọi đúng tool check trước, phát hiện đúng 1 kỳ sao kê
       **đã quá hạn thật** (đúng hơn cả giả định ban đầu khi viết ví dụ),
       sinh đúng `transfer_form` hợp lệ với số liệu khớp `statements` thật.
       Đã xoá thread test debug sau khi verify xong.
  - **Quyết định kiến trúc đã chốt (thảo luận 2026-09-03):**
    1. **Skill, không dùng tool** — cùng lý do đã chọn cho chart: skill chỉ
       tải vào system prompt khi thật sự cần (progressive disclosure), còn
       tool (function-calling) thì schema của nó luôn hiện diện ở mọi lượt
       gọi model dù câu hỏi có liên quan hay không, tốn token đều đặn. Vì
       `transfer_form` cũng chỉ là gợi ý hiển thị (không có side-effect
       thật qua `/chat`), ưu điểm validate-tự-động của tool
       không đủ bù chi phí token luôn tải — **cập nhật sau khi migrate
       `chart` → `ui` (xem mục Roadmap PFM bên dưới):** tái dùng đúng
       envelope `ui`/fence ` ```ui-json ``` ` đã có sẵn trong
       `text_utils.py`, chỉ cần thêm `_is_valid_transfer_form()` +
       đăng ký vào `_UI_VALIDATORS["transfer_form"]` (không cần hàm
       `extract_*` riêng — `extract_ui_block()` đã dùng chung cho mọi
       type), theo đúng nguyên tắc Phần B đã áp dụng cho chart: chỉ
       validate, không tự sửa/tự điền — sai schema thì trả `ui: null`,
       không tự "vá" dữ liệu agent sinh sai.
    2. **Đã chốt: gộp** — dùng chung 1 field `ui: {"type": "chart"|"transfer_form", ...}`,
       1 fence ` ```ui-json ``` ` chung (mỗi type có skill riêng dạy đúng
       schema của mình, không phải 1 skill dạy cả 2). Đã migrate `chart` →
       `ui` xong trước khi implement `transfer_form` (xem mục "Việc frontend
       đã làm..." ở Roadmap PFM bên dưới) nên `transfer_form` chỉ cần đăng
       ký thêm 1 validator, không cần đổi lại cơ chế lần nữa.
  - **Việc cần làm khi implement (dù chọn gộp hay tách):**
    1. Định nghĩa schema `transfer_form` cụ thể (chưa bàn tới): tối thiểu
       cần `recipient`/`account_number`/`amount`/`note`/`reason`(lý do gợi
       ý) — cần thảo luận thêm field nào bắt buộc.
    2. Viết skill mới dạy agent khi nào nên gợi ý transfer form (ví dụ:
       khách hỏi "tôi nên trả nợ thẻ bao nhiêu", "chuyển tiền cho X như mọi
       tháng") + format khối JSON, theo đúng văn phong PHẢI/KHÔNG ĐƯỢC như
       `skills/project/data-visualization/SKILL.md` đang có.
    3. Validator riêng cho `transfer_form` (giống `_is_valid_chart` trong
       `text_utils.py`) — cân nhắc thêm ràng buộc riêng cho tiền: ví dụ
       `amount` phải là số dương hợp lý, `recipient`/`account_number` nên
       đối chiếu được với dữ liệu giao dịch thật của khách trong
       `/customer_data.json` (không cho agent tự bịa người nhận mới hoàn
       toàn chưa từng xuất hiện trong lịch sử giao dịch) — cần bàn kỹ vì
       đây là rủi ro cao hơn chart nhiều (dù chỉ hiển thị, số liệu sai vẫn
       có thể khiến khách bấm nhầm).
    4. Cập nhật `docs/api.md` + viết `docs/transfer-form.md` (hoặc gộp vào
       `docs/chart-visualization.md` nếu chọn gộp field `ui`) cho frontend.
    5. Test tương tự pattern chart: parser/validator trong
       `tests/test_text_utils.py`, end-to-end trong `tests/test_server.py`.
  - **Scope đầy đủ (bổ sung 2026-09-03) — "gửi form" chỉ là 1 bước, không
    phải toàn bộ:** trước khi hiện form, agent cần **check** tính khả thi,
    nếu không sẽ đề xuất số tiền/người nhận vô lý (vượt hạn mức, người nhận
    bịa ra). 3 bước rõ ràng:
    1. **Check (tool)** — verify trước khi đề xuất:
       - `check_available_balance_or_credit` (**tool mới đề xuất**) — xác
         nhận số tiền định đề xuất không vượt quá `available_credit_vnd`
         (hoặc số dư khả dụng tương ứng) của khách — nên làm **tool riêng**
         thay vì để agent tự tính bằng free-text, vì đây là điều kiện chặn
         cứng (sai 1 lần là đề xuất số tiền không thực hiện được, làm mất
         tin tưởng), không nên phó mặc cho model tự cộng trừ.
       - Đối chiếu `recipient`/`account_number` với lịch sử giao dịch thật
         — dùng `read_file`/`grep` đã có sẵn (không cần tool riêng, agent tự
         đọc `/customer_data.json` là đủ, trừ khi sau này cần logic đối
         chiếu phức tạp hơn).
    2. **Propose** — hiện `transfer_form` (đã thiết kế ở trên).
    3. **Execute** — **không có** ở tầng agent/`server.py`; hệ thống PFM/core
       banking khác thực hiện khi user bấm xác nhận (đã chốt ở mục Roadmap
       PFM bên dưới).

- [ ] **Roadmap PFM (`Roadmap.png`, MSB — thảo luận 2026-09-03) — rà lại
  toàn bộ tính năng agent cần tham gia, map sang output có cấu trúc.**
  Roadmap gồm 4 MVP theo quý (Q2/2026 → Q1/2027); các ô tô xanh trong file
  là tính năng agent tham gia. **Phạm vi đã chốt: thiết kế cho cả 4 MVP**
  (chưa implement hết, chỉ MVP1+2 có data sẵn sàng để code ngay).

  **Nguyên tắc mới (áp dụng từ 2026-09-03 trở đi):** trước khi bắt tay code
  **bất kỳ mục nào** trong danh sách roadmap này, phải viết rõ **Scope** —
  liệt kê đủ 3 phần: (1) **Check** — tool/bước kiểm tra tính khả thi cần
  chạy TRƯỚC khi đề xuất (tool đã có sẵn như `read_file`, hay cần tool mới
  hoàn toàn), (2) **Propose** — output có cấu trúc hiện cho user xem, (3)
  **Execute** — xác nhận rõ có/không có hành động ghi thật ở tầng agent.
  "Gửi form" (Propose) chỉ là 1 trong 3 bước, không phải toàn bộ tính năng
  — mỗi mục dưới đây đã được viết lại theo đúng khung này.

  **Quyết định kiến trúc chung áp dụng cho mọi tính năng "hành động" dưới
  đây (không riêng `transfer_form`):** agent chỉ **tạo đề xuất có cấu
  trúc** → gửi cho user xem/xác nhận trên UI → **user tự bấm "Đồng ý"** →
  lúc đó hành động thật (tạo hũ, đặt ngân sách, tạo mục tiêu tiết kiệm...)
  mới được thực thi. Ví dụ cụ thể bạn nêu: agent tạo đề xuất hũ chi tiêu,
  gửi cho user xem, user bấm OK thì **backend** mới tạo hũ mới — agent
  không bao giờ tự ý tạo/ghi qua `/chat`.
  - **Đã xác nhận nơi thực thi hành động thật:** một **hệ thống khác** (core
    T24 / backend PFM riêng của MSB) thực hiện việc tạo hũ/đặt ngân
    sách/tạo mục tiêu khi user xác nhận — **`server.py` (repo này) không
    cần tự xây endpoint CRUD nào** (không cần `POST /jars`,
    `POST /budgets`...). Việc của repo này chỉ dừng ở: agent sinh đúng
    schema đề xuất, frontend tự gọi sang hệ thống PFM/core banking khác khi
    user xác nhận.
  - **Chưa chốt (giống câu hỏi đã nêu ở mục `transfer_form`):** có nên gộp
    tất cả loại đề xuất hành động này vào 1 field chung dạng
    `action_proposal: {"action_type": "set_budget"|"create_savings_goal"|"create_jar"|"transfer"|..., "payload": {...}}`
    (1 pattern chung, dễ scale) hay vẫn tách riêng field/skill cho từng
    loại như `chart`/`transfer_form` hiện tại? Cần chốt trước khi bắt đầu
    code loạt tính năng dưới đây.
  - [x] **Đã chốt + migrate xong (2026-09-03):** đổi `chart` → **`ui`**
    (envelope chung, phân biệt bằng `ui.type` — hiện chỉ có `"chart"`).
    Quyết định: **đổi thẳng ngay** (không giữ `chart` song song để
    deprecate dần), dù `docs/chart-output-rules.md` (frontend tự viết) nói
    đã render thật bằng Recharts theo field `chart` cũ — **đây là breaking
    change thật, frontend cần cập nhật code đọc `body.ui` +
    `ui.type === "chart"` thay vì `body.chart`.**
    - `text_utils.py`: `extract_chart_block()` → `extract_ui_block()`;
      thêm `_UI_VALIDATORS` (dispatch theo `type`) + `_is_valid_ui()`,
      `_is_valid_chart()` giữ nguyên logic cũ (không còn tự check `type`,
      dispatcher lo việc đó). Fence đổi từ ` ```chart-json ``` ` sang
      ` ```ui-json ``` `.
    - `server.py`: `ChatResponse.chart` → `ChatResponse.ui`; `/chat` và
      `GET /chat/history` dùng `extract_ui_block` thay vì
      `extract_chart_block`.
    - `skills/project/data-visualization/SKILL.md`: viết lại theo fence
      `ui-json` + field `type: "chart"` bắt buộc, cập nhật toàn bộ ví dụ
      ĐÚNG/SAI (thêm ví dụ SAI mới: thiếu field `type`).
    - `docs/api.md`, `docs/chart-visualization.md`: cập nhật field
      `chart` → `ui` + ghi rõ breaking change ở đầu mục liên quan.
    - `docs/chart-output-rules.md` (tài liệu frontend viết): cập nhật lại
      toàn bộ theo field `ui`/`type`, và **nhân tiện sửa luôn 1 điểm không
      nhất quán phát hiện được**: B.MUST-4 bản cũ nói backend PHẢI tự cắt
      `series` của `pie` còn `series[0]` khi agent lỡ sinh nhiều hơn 1 —
      nhưng code thật (`_is_valid_chart`) đã **reject hoàn toàn** (fallback
      `null`) theo đúng quyết định "chỉ validate, không tự sửa" đã chốt
      trước đó — rule doc giờ khớp đúng code. Mục "Việc frontend đã làm"
      cuối file đã đổi thành cảnh báo cần frontend tự xác nhận lại (tuyên
      bố "không cần đổi gì" viết trước khi có breaking change này không
      còn đúng).
    - Test: `tests/test_text_utils.py` (đổi hết sang
      `extract_ui_block`/fence `ui-json`, thêm 2 test mới: thiếu `type`,
      `type` lạ), `tests/test_server.py` (đổi `body["chart"]` →
      `body["ui"]`). **51/51 test pass** (`uv run --group dev pytest tests/`).

  **MVP1 — Quý 2/2026 (Quản lý thu-chi):**
  - [ ] **Thiết lập ngân sách** (cài đặt hạn mức ngày/tháng, cảnh báo
    ngưỡng chi tiêu)
    - **Check:** đọc lịch sử chi tiêu theo danh mục/kỳ liên quan để đề
      xuất mức hạn mức hợp lý — dùng `read_file`/`grep` có sẵn, không cần
      tool mới.
    - **Cân nhắc tool mới:** `check_budget_against_income(category,
      proposed_amount)` — enforce 1 rule cứng (ví dụ không đề xuất ngân
      sách 1 danh mục vượt quá X% thu nhập `monthly_income_vnd`) bằng code
      thay vì để model tự tính bằng free-text (dễ sai/không nhất quán giữa
      các lượt trả lời).
    - **Propose:** `set_budget` (category, period, amount,
      threshold_alert_percent).
    - **Execute:** không — phần lưu ngân sách hiện đã có sẵn qua
      `remember_preference` (khác cơ chế PFM ngoài của các mục dưới, vì
      đây vốn là cơ chế nội bộ đã có từ trước); chỉ thiếu bước UI đề xuất +
      xác nhận trước khi gọi `remember_preference`.
  - [ ] **Tiết kiệm mục tiêu** (gợi ý tích luỹ theo balance)
    - **[Đã gỡ chặn 2026-09-07]** "balance" giờ có thể hiểu là số dư tài
      khoản thanh toán — `customer_data.json` đã có field `account.balance_vnd`
      (thêm cùng lúc với `jars`, xem mục Hũ chi tiêu bên dưới). Không còn
      lý do "thiếu data" để trì hoãn implement mục này nữa.
    - **Cân nhắc tool mới:** `check_existing_savings_goals()` — đọc danh
      sách mục tiêu tiết kiệm **hiện có** để tránh đề xuất trùng lặp/mâu
      thuẫn. Lưu ý: mục tiêu tiết kiệm **không có** trong
      `customer_data.json` — nếu hệ thống PFM ngoài quản lý dữ liệu này,
      tool này phải gọi API hệ thống ngoài (tích hợp thật, không phải chỉ
      đọc file tĩnh) — **chi phí lớn hơn nhiều** so với các tool chỉ đọc
      `customer_data.json`, cần đánh giá riêng trước khi nhận việc.
    - **Propose:** `create_savings_goal` (name, target_amount,
      monthly_contribution, timeline).
    - **Execute:** không — hệ thống PFM ngoài xử lý khi user xác nhận.

  **MVP2 — Quý 3/2026 (Tự động hoá & Báo cáo):**
  - [x] Báo cáo dòng tiền thu-chi (biểu đồ, theo danh mục) → **đã làm xong,
    chính là tính năng `chart` ở mục ngay trên.**
  - [x] **Hũ chi tiêu (tạo hũ, chỉnh sửa hũ) — Đã implement xong
    (2026-09-07), CHƯA có tool.**
    - **Quyết định (theo yêu cầu trực tiếp):** implement `create_jar` +
      `edit_jar` **không dùng tool nào** — agent tự đọc `/customer_data.json`
      (`monthly_spending_summary`) bằng `read_file` để tính mức đề xuất,
      giống pattern đã áp dụng cho `transfer_form` sau khi bỏ
      `check_available_balance_or_credit` (xem mục 1.8).
    - **Đã làm:**
      1. `text_utils.py` — `_is_valid_create_jar()`/`_is_valid_edit_jar()`,
         đăng ký vào `_UI_VALIDATORS` (tái dùng `extract_ui_block()` chung,
         không cần code mới ở tầng parse).
      2. `skills/project/spending-jar/SKILL.md` (mới) — dạy agent khi nào
         dùng `create_jar` vs `edit_jar`, kèm giới hạn ban đầu: **"hũ đã
         có" chỉ có thể hiểu là hũ đã được nhắc tới TRONG CHÍNH CUỘC HỘI
         THOẠI này** (chưa có dữ liệu hũ thật lúc này — đã gỡ bớt giới hạn
         này ngay sau đó, xem cập nhật 2026-09-07 bên dưới).
      3. `docs/spending-jar.md` (mới) + cập nhật `docs/api.md` (liệt kê 2
         `ui.type` mới). Đã đồng bộ sang `PersonalCardAgentUI/agent_backend_docs/`.
      4. Test: 6 test mới trong `tests/test_text_utils.py` (parse/validate
         cả 2 type), 1 test end-to-end trong `tests/test_server.py`. 61/61
         test pass (`uv run --group dev pytest tests/`).
      5. Verify thật với model VNG: hỏi "Tạo giúp tôi 1 hũ ăn uống hợp lý
         mỗi tháng" → agent tự đọc `monthly_spending_summary` 3 tháng, tự
         tính trung bình thật, sinh đúng `create_jar` hợp lệ.
    - **[Cập nhật 2026-09-07] Đã thêm `account`/`jars` vào mockup data —
      gỡ được 1 phần giới hạn ở trên, KHÔNG cần tool.** Theo yêu cầu trực
      tiếp, thêm vào cả 3 file `data/customers/CIF_000{1,2,3}.json`:
      - `account: {account_number, account_type, balance_vnd}` — số dư tài
        khoản thanh toán (giải quyết luôn câu hỏi "balance" ở mục Tiết kiệm
        mục tiêu phía trên).
      - `jars: [{jar_id, jar_name, allocation_amount_vnd, created_on}, ...]`
        — danh sách hũ hiện có tính đến đầu phiên (CIF_0001: 2 hũ, CIF_0002:
        1 hũ, CIF_0003: chưa có hũ nào — cố tình đa dạng để test cả case
        rỗng).
      - Test mới trong `tests/data/test_customer_data.py`:
        `test_account_balance_is_a_non_negative_number`,
        `test_jars_have_required_fields_and_positive_allocation`
        (+ thêm `account`/`jars` vào danh sách top-level key bắt buộc). 67/67
        test pass.
      - Cập nhật `skills/project/spending-jar/SKILL.md` để agent thật sự
        dùng data này: đọc `jars` trước khi quyết định `create_jar` hay
        `edit_jar` (không chỉ dựa vào ngữ cảnh hội thoại nữa). **Đã verify
        thật với model VNG:** hỏi "Tăng hũ giải trí của tôi lên 800 nghìn"
        (chưa hề nhắc tới hũ này trong hội thoại) → agent tự đọc `jars`,
        nhận diện đúng hũ Giải trí đã tồn tại (600.000đ), trả về đúng
        `edit_jar` (không tạo trùng bằng `create_jar`).
      - **Lưu ý còn treo (chưa giải quyết bằng data mockup):** `jars` là
        **snapshot đầu phiên**, không tự cập nhật realtime nếu khách hàng
        tạo/sửa hũ thật qua hệ thống PFM khác trong lúc đang trò chuyện.
    - **⚠️ Tool cần làm sau (đã note lại theo yêu cầu ban đầu, KHÔNG làm
      bây giờ) — vẫn còn giá trị dù đã có mockup data ở trên:**
      `list_existing_jars()` — đọc danh sách hũ chi tiêu **thật, realtime**
      từ hệ thống PFM ngoài (khác với `jars` mockup ở trên — đó chỉ là
      snapshot tĩnh trong file test, không phản ánh thay đổi thật sau khi
      agent bắt đầu phiên). Tool này sẽ giải quyết nốt giới hạn còn lại:
      1. Dữ liệu hũ luôn mới nhất, không lệch so với thực tế dù khách hàng
         vừa tạo/sửa hũ qua kênh khác.
      2. Tính được % hũ còn có thể phân bổ nếu tổng % các hũ đã tạo phải
         ≤100% (`list_existing_jars()` cần trả về cả % đã phân bổ của các
         hũ hiện có, thứ mockup `jars` hiện tại không có khái niệm này).
      Khi có tool này: cập nhật lại `SKILL.md` để bắt buộc gọi trước khi
      đề xuất (giống pattern check trước đây của `transfer_form`), và có
      thể tách hẳn `edit_jar` cần `jar_id` thật thay vì chỉ dựa vào
      `jar_name`.
    - **Execute:** không — hệ thống PFM ngoài xử lý khi user xác nhận
      (đúng ví dụ bạn nêu: agent gửi thông tin hũ, user bấm OK, **backend**
      mới tạo hũ mới).

  **MVP3 — Quý 4/2026 (Quản lý tài sản & dư nợ):** không có mục nào tô
  xanh trong roadmap — agent không tham gia MVP3.

  **MVP4 — Quý 1/2027 (Tư vấn tài chính & AI cá nhân hoá):**
  - [ ] **Trợ lý tài chính AI — tư vấn tối ưu danh mục tích luỹ**
    - **Chưa đủ thông tin để viết Scope đầy đủ** — "danh mục tích luỹ"
      (portfolio tích luỹ/tiết kiệm) chưa có trong `customer_data.json`,
      chưa rõ nguồn dữ liệu. Cần làm rõ trước: đây là danh mục các hũ/mục
      tiêu tiết kiệm đã tạo ở MVP1/2 (nếu vậy **Check** sẽ cần tool đọc dữ
      liệu đó từ hệ thống PFM ngoài, giống `list_existing_jars()` ở trên),
      hay 1 loại dữ liệu tích luỹ/đầu tư hoàn toàn khác?
    - **Propose:** tạm để ngỏ dạng `adjust_allocation` hoặc chỉ text/chart
      tư vấn (chưa có hành động ghi cụ thể nào được xác nhận).
    - **Execute:** cần xác nhận có hành động ghi thật nào không, hay chỉ
      tư vấn thuần (giống chart, không có Propose dạng "confirm rồi thực
      thi").
  - [ ] **Trợ lý tài chính AI — cảnh báo chi tiêu bất thường dựa trên lịch
    sử hành vi → `anomaly_alert`. TẠM THỜI CHƯA LÀM (theo yêu cầu
    2026-09-03), chỉ ghi lại thiết kế để không bị quên:**
    - Đây là tính năng **chủ động** (agent tự phát hiện bất thường và chủ
      động gửi cảnh báo cho user), **không** phải trả lời theo câu hỏi qua
      `/chat` — khác hẳn bản chất mọi tính năng khác trong repo này (đều
      là request/response thuần: user hỏi → agent trả lời).
    - Kiến trúc `/chat` hiện tại (FastAPI thuần, không có scheduler/job
      nền, không có cơ chế push) **không hỗ trợ** việc này — cần thiết kế
      hạ tầng mới hoàn toàn (ví dụ: 1 job định kỳ tự chạy agent kiểm tra
      giao dịch mới + so với hành vi lịch sử, rồi gửi cảnh báo qua kênh
      riêng — push notification/tin nhắn app — không phải qua `POST /chat`
      của user).
    - Việc tương tự "Cảnh báo ngưỡng chi tiêu" ở MVP1 (`Thiết lập ngân
      sách`) nhiều khả năng cũng cùng bản chất chủ động này — cần rà lại
      khi tới lượt implement MVP1.
    - **Việc cần làm khi quay lại:** chọn cơ chế trigger (cron job gọi
      `agent.invoke()` định kỳ theo từng khách hàng, hay event-driven theo
      giao dịch mới phát sinh), chọn kênh gửi cảnh báo (không phải response
      của `/chat` vì không có request tương ứng từ user tại thời điểm đó),
      và thiết kế lại hoàn toàn phần này — không tái dùng được pattern
      `action_proposal`/skill hiện tại (pattern đó giả định luôn có 1 câu
      hỏi của user đi trước).
  - [ ] **Gợi ý tích luỹ & đầu tư — công cụ tư vấn đầu tư tự động**
    - **Cân nhắc tool mới:** `check_risk_profile()`/đọc `credit_profile`
      hiện có trong `customer_data.json` (`customer.credit_profile`) —
      chưa chắc đủ để đánh giá khẩu vị rủi ro đầu tư, cần xác nhận có
      trường dữ liệu "risk profile" riêng cho đầu tư hay tái dùng
      `credit_profile` hiện tại.
    - **Propose:** tạm để ngỏ dạng `create_investment_order`? — cần dữ
      liệu sản phẩm đầu tư (chưa có trong `customer_data.json`) trước khi
      định hình schema cụ thể.
    - **⚠️ Lưu ý riêng, quan trọng hơn schema:** đây là tư vấn đầu tư cá
      nhân hoá, nên xác nhận với team compliance/pháp lý MSB trước khi
      triển khai (khác hẳn tư vấn ngân sách/chi tiêu thông thường về mặt
      quy định) — **cần chốt trước khi viết Scope đầy đủ cho mục này.**
  - [ ] Gợi ý tích luỹ & đầu tư — báo cáo hiệu suất sinh lời định kỳ → có
    thể tái dùng thẳng `chart` (line/bar theo thời gian), không cần type
    output mới.

## 4. Việc người dùng tự quyết định

- [ ] `git push` lên `origin/master` (https://github.com/Daonguyen2401/personal-card-agent.git)
  — hiện toàn bộ (bao gồm cả plan Docker/server + mọi chỉnh sửa sau đó) vẫn
  chỉ đang **staged, chưa có commit nào**, theo lựa chọn của bạn (chỉ bạn
  được quyền commit). Cần tự `git commit` trước khi có gì để push.
- [ ] Build Docker image thật + `docker run` thử (Docker Desktop cần được
  bật trước) — xem mục 2.
- [ ] Chốt việc có giữ `sandbox/__init__.py` (bật tính năng thật) hay xoá
  lại trước khi deploy — xem mục 3.

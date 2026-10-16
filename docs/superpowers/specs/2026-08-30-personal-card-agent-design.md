# Personal Card Agent — Thiết kế triển khai

**Ngày:** 2026-08-30
**Trạng thái:** Đã thống nhất qua brainstorming, chờ chuyển sang implementation plan.

## 1. Bối cảnh & mục tiêu

Repo hiện tại là scaffold "research-assistant" mặc định của Managed Deep Agents
(MDA) — chưa có logic nghiệp vụ nào cho thẻ. Mục tiêu của thiết kế này là biến
nó thành **personal-card-agent**: một agent trả lời được các câu hỏi trong
[`docs/sample_questions_and_answers.md`](../../sample_questions_and_answers.md)
(thống kê giao dịch, quản lý chi tiêu, insight, tư vấn tài chính, thông tin
thẻ), dùng dữ liệu khách hàng mẫu ở
[`docs/sample_customer_data.json`](../../sample_customer_data.json) (sẽ di
chuyển sang `data/customer_data.json`, xem §3).

**Ràng buộc cứng từ người dùng:** không hard code logic trả lời theo từng loại
câu hỏi (không viết tool "tính tổng chi tiêu", "tính % danh mục"...). Toàn bộ
việc tính toán/suy luận số liệu phải do LLM tự làm dựa trên dữ liệu đọc được,
sử dụng các tool filesystem tổng quát sẵn có của framework deepagents
(`read_file`, `write_file`, `edit_file`, `grep`, `ls`) thay vì tool nghiệp vụ
tự viết.

## 2. Kiến trúc tổng quan

```
data/
  customer_data.json           # nguồn dữ liệu khách hàng (đọc lại mỗi phiên)
docs/
  sample_questions_and_answers.md   # khung hành vi tham chiếu (giữ nguyên)
  sample_customer_data.json    # XOÁ sau khi di chuyển sang data/
middleware/
  seed_customer_context.py     # before_agent hook — nạp data/customer_data.json vào filesystem ảo của phiên
  audit.py                     # giữ nguyên, không đổi
memory.py                      # giữ nguyên define_memory(scope="agent") — bền vững, dùng cho ngân sách
instructions.md                # viết lại toàn bộ theo docs/sample_questions_and_answers.md
agent.py                       # bỏ internet_search; thêm checkpointer, middleware mới, đổi tên
pyproject.toml                 # đổi tên project; đảm bảo data/*.json được đóng gói khi deploy
evals/tasks/card-agent-*/      # eval case mới dựa trên sample_questions_and_answers.md
```

Xoá khỏi scaffold (không dùng trong thiết kế này): `tools/search.py`,
`skills/research/`, `sandbox/`. Nếu `tools/` hoặc `skills/` trống sau khi xoá
nội dung, xoá luôn thư mục.

## 3. Luồng dữ liệu khách hàng (session-scoped)

- `data/customer_data.json` là nguồn sự thật (source of truth) tĩnh cho khách
  hàng demo — di chuyển từ `docs/sample_customer_data.json`, giữ nguyên cấu
  trúc (`customer`, `chat_memory_example` → xem §4, `cards`, `statements`,
  `monthly_spending_summary`, `transactions`).
- `middleware/seed_customer_context.py` triển khai hook `before_agent`
  (pattern giống `SandboxSyncMiddleware` trong tài liệu deepagents): mỗi khi
  một lượt chạy agent bắt đầu, đọc `data/customer_data.json` từ đĩa và ghi nó
  vào filesystem ảo của phiên tại đường dẫn cố định `/customer_data.json`
  (session/thread-scoped — dùng `StateBackend` mặc định, **không** phải durable
  memory).
- Vì đọc lại từ đĩa mỗi lượt, dữ liệu luôn khớp với file nguồn — không cần
  bước đồng bộ thủ công nào.
- `instructions.md` yêu cầu agent `read_file("/customer_data.json")` (hoặc
  `grep` để lọc nhanh theo từ khoá/khoảng ngày khi câu hỏi chỉ cần một phần
  dữ liệu) trước khi trả lời bất kỳ câu hỏi nào cần số liệu.

## 4. Ngân sách khách hàng — bộ nhớ bền vững, xuyên phiên

- Vấn đề cần giải: câu hỏi "tôi có vượt ngân sách không" chỉ trả lời được nếu
  khách hàng từng nói ngân sách của họ — hệ thống không có trường này.
  `chat_memory_example` trong `data/customer_data.json` là **ví dụ minh hoạ**,
  không phải cơ chế lưu trữ thật.
- Cơ chế lưu trữ thật: `memory.py` (`define_memory(scope="agent")`) mount thư
  mục bền vững `/memories/agent/`. Dùng file cold-memory
  `/memories/agent/customer_budgets.json`, cấu trúc:
  ```json
  { "CUS-000482": { "monthly_budget_vnd": 15000000, "mentioned_on": "2026-08-10" } }
  ```
- **Giới hạn đã biết:** `define_memory` chỉ hỗ trợ `scope="agent"` (một file
  dùng chung cho mọi người gọi deployment) hoặc `scope="none"` — không có cô
  lập theo người dùng ở tầng framework. Để không rò rỉ dữ liệu giữa các khách
  hàng, file phải luôn là **dict khoá theo `customer_id`**, và
  `instructions.md` phải yêu cầu agent chỉ đọc/ghi đúng entry của
  `customer_id` hiện tại (lấy từ `/customer_data.json`) — không bao giờ đọc/ghi
  toàn bộ file như một giá trị đơn. Trong phạm vi demo 1 khách hàng, không có
  rủi ro rò rỉ thật; đây là chuẩn bị cho khi có khách hàng thứ hai.
- Hành vi: agent `read_file` file này khi cần trả lời câu hỏi ngân sách; nếu
  không có entry cho `customer_id` hiện tại, hỏi lại khách hàng thay vì giả
  định; nếu khách hàng cung cấp/cập nhật số mới trong hội thoại, agent
  `write_file`/`edit_file` để lưu lại.

## 5. Lịch sử hội thoại trong 1 phiên (checkpointer)

- Tách biệt với §4: đây là lịch sử tin nhắn qua lại **trong cùng một
  thread**, không phải sự thật đã học được xuyên nhiều thread.
- Theo tài liệu deepagents (OSS), checkpointer phải được khai báo tường minh
  để trạng thái (bao gồm lịch sử tin nhắn) được giữ qua các lượt trong cùng
  thread: `checkpointer=MemorySaver()` (từ `langgraph.checkpoint.memory`),
  mỗi lời gọi kèm `thread_id` cố định cho cùng một cuộc hội thoại.
- `agent.py` sẽ khai báo checkpointer này tường minh thay vì phó mặc cho hạ
  tầng Managed Deep Agents tự lo.
- **Rủi ro cần xác minh khi implement:** chưa xác nhận được
  `managed_deepagents.define_deep_agent` có nhận tham số `checkpointer` giống
  `deepagents.create_deep_agent` hay không (tài liệu MDA không nêu rõ). Bước
  implement phải kiểm tra chữ ký hàm thực tế (`inspect.signature` sau khi
  `uv sync`, hoặc đọc source nếu có). Nếu không hỗ trợ, ghi nhận là giới hạn
  đã biết và dựa vào checkpoint mặc định của nền tảng khi deploy — không chặn
  phần còn lại của thiết kế.

## 6. `instructions.md`

Viết lại hoàn toàn, thay thế nội dung research-assistant hiện tại. Nội dung
chính:

- Vai trò: trợ lý tài chính về thẻ (personal card agent). **Chỉ cung cấp
  thông tin & tư vấn — không thực hiện hành động thay đổi trạng thái thẻ**
  (mở thẻ, khoá thẻ, đặt cảnh báo...); nếu khách hàng yêu cầu hành động, agent
  giải thích đây ngoài phạm vi và gợi ý kênh phù hợp.
- Quy trình bắt buộc trước khi trả lời câu hỏi số liệu: `read_file`
  `/customer_data.json`; với câu hỏi ngân sách, thêm `read_file`
  `/memories/agent/customer_budgets.json` theo quy tắc §4.
- Khung 5 nhóm câu hỏi lấy từ `docs/sample_questions_and_answers.md` (thống
  kê & tra cứu giao dịch; quản lý chi tiêu; insight & phân tích hành vi; tư
  vấn tài chính & chi tiêu; thông tin thẻ & kỳ sao kê) — dùng làm khung hành
  vi, **không** copy các số ví dụ trong đó vào instructions (agent phải tự
  tính từ dữ liệu thật trong `/customer_data.json`).
- Nguyên tắc trả lời chung (lấy từ cùng tài liệu): luôn dẫn số liệu cụ thể từ
  dữ liệu đọc được, không bịa số; nêu rõ mốc thời gian dữ liệu; tư vấn có căn
  cứ chứ không quyết thay khách hàng; insight ưu tiên giải thích "vì sao"; khi
  thiếu dữ liệu, nói rõ giới hạn thay vì suy diễn.

## 7. Dọn dẹp scaffold

- `agent.py`: bỏ `internet_search`; đổi `name="personal-card-agent"`; thêm
  `middleware=[log_tool_calls, seed_customer_context]`; thêm `checkpointer`
  (xem §5, tuỳ kết quả xác minh).
- Xoá `tools/search.py`, `skills/research/SKILL.md`, `sandbox/`.
- `pyproject.toml`: đổi `name`/`description` cho khớp agent mới; thêm cấu
  hình đóng gói để `data/customer_data.json` có mặt khi deploy (JSON không
  phải Python package nên `[tool.hatch.build.targets.wheel] packages=[...]`
  không đủ — cần `force-include` hoặc tương đương; chốt chi tiết khi viết
  code).
- `README.md`: cập nhật mô tả agent (không bắt buộc phải hoàn chỉnh, nhưng
  không được để mô tả sai là "research-assistant").

## 8. Testing

- Dùng khung eval Harbor sẵn có (`evals/tasks/`). Tạo các eval task mới dựa
  trên `docs/sample_questions_and_answers.md`, ví dụ:
  - "Tháng này tôi đã chi tiêu bao nhiêu trên thẻ?" → kỳ vọng câu trả lời chứa
    `11.324.000` hoặc `11,324,000` (tổng đã tính sẵn trong
    `monthly_spending_summary["2026-08"].total_vnd` để so khớp).
  - "Liệt kê các giao dịch trên 2 triệu trong tháng 7" → kỳ vọng đúng 3 giao
    dịch (Vietnam Airlines, Điện Máy Xanh, Lotte Mart).
  - Một case ngân sách: seed sẵn `/memories/agent/customer_budgets.json` có
    entry, hỏi "tôi có vượt ngân sách không" → kỳ vọng câu trả lời dùng đúng
    con số đã seed, không hỏi lại.
  - Một case ngân sách khi **chưa** có entry → kỳ vọng agent hỏi lại thay vì
    bịa số.
- Mục đích chính của eval: giảm rủi ro lớn nhất của phương án đã chọn — LLM tự
  cộng/so sánh số liệu trên nhiều giao dịch có thể tính sai. Không cần phủ hết
  mọi câu hỏi trong tài liệu, ưu tiên các câu cần cộng/so sánh nhiều số.
- Sau khi code xong, chạy thử qua `mda dev .` (Studio) hoặc
  `notebooks/try_agent.ipynb` với vài câu hỏi mẫu trước khi coi là hoàn
  thành — không có cách kiểm tra tự động thay thế việc chạy thử hội thoại
  thật.

## 9. Non-goals / giới hạn đã biết

- **Xác thực đa khách hàng thật:** `identity.py` vẫn dùng
  `auth.langsmith_api_key()` (một key chung cho cả workspace), chưa gắn
  `customer_id` theo từng người dùng thật. Toàn bộ thiết kế giả định 1 khách
  hàng demo duy nhất.
- **Cô lập lịch sử hội thoại theo từng khách hàng** ở tầng nền tảng/channel —
  phụ thuộc client quản lý `thread_id` đúng cách, ngoài phạm vi repo này.
- **Checkpointer bền vững cho production** (vd Postgres-backed) — thiết kế
  này chỉ dùng `MemorySaver` (in-memory) cho dev; chọn checkpointer production
  để sau.
- **Tool tính toán số liệu:** cố tình không xây, theo đúng yêu cầu ban đầu.
  Rủi ro LLM tính sai số được giảm thiểu bằng eval (§8) nhưng không loại bỏ
  hoàn toàn — nếu sau này thấy agent tính sai nhiều, cân nhắc bổ sung tool
  mỏng (đã bị từ chối ở vòng brainstorming này, xem lịch sử quyết định).
- **Đóng gói `data/*.json` khi deploy** — cần xác minh cấu hình hatchling cụ
  thể khi implement, chưa chốt chi tiết.

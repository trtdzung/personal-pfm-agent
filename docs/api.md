# Personal Card Agent — API Reference (for frontend)

Tài liệu này mô tả các endpoint HTTP mà frontend gọi vào để dùng agent tư
vấn tài chính về thẻ. Đây là API của `server.py` (đường tự host qua
Docker/GreenNode AgentBase Runtime) — xem `README.md` mục "Self-hosted
server" nếu cần chi tiết hạ tầng/deploy.

## Base URL

- Local/docker-compose: `http://localhost:8080`
- GreenNode AgentBase Runtime: URL endpoint được cấp khi deploy (dạng
  `https://endpoint-<id>.agentbase-runtime.aiplatform.vngcloud.vn`)

## Xác thực

Có **2 lớp xác thực độc lập nhau** — thiếu lớp nào cũng bị chặn, và bị chặn
ở lớp nào thì lỗi sẽ khác nhau:

### Lớp 1 — `X-API-Key` (luôn cần, mọi môi trường)

Mọi endpoint trừ `GET /health` đều yêu cầu header:

```
X-API-Key: <SERVER_API_KEY>
```

Đây là secret của chính app (`server.py` tự kiểm tra bằng
`hmac.compare_digest`). Sai hoặc thiếu → `401 Unauthorized`, body
`{"detail": "Invalid or missing X-API-Key"}`.

### Lớp 2 — `Authorization: Bearer <JWT>` (chỉ cần khi gọi qua GreenNode AgentBase Runtime)

Đây là xác thực riêng của **GreenNode ở tầng gateway**, đứng trước app —
không do code trong `server.py` kiểm tra, mà do GreenNode Runtime chặn
trước khi request tới được container. **Gọi local/docker-compose trực tiếp
(`http://localhost:8080`) thì KHÔNG cần lớp này**, chỉ cần khi gọi qua URL
GreenNode Runtime thật.

JWT lấy qua Auth0 bằng luồng Client Credentials — đây là bước hay bị thiếu
khi tích hợp lần đầu:

```bash
curl -X POST "https://$AUTH0_DOMAIN/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "'"$AUTH0_CLIENT_ID"'",
    "client_secret": "'"$AUTH0_CLIENT_SECRET"'",
    "audience": "'"$AUTH0_AUDIENCE"'",
    "grant_type": "client_credentials"
  }'
```

Response trả về `{"access_token": "...", "expires_in": 86400, "token_type": "Bearer"}`
— dùng `access_token` làm `<JWT>` trong header `Authorization: Bearer <JWT>`
của mọi request tiếp theo. Token có hạn (`expires_in`, tính bằng giây —
mặc định 86400s = 24h) — hết hạn phải gọi lại bước này để lấy token mới,
đừng cache vĩnh viễn.

`AUTH0_DOMAIN`/`AUTH0_CLIENT_ID`/`AUTH0_CLIENT_SECRET`/`AUTH0_AUDIENCE` là
credentials riêng của backend/frontend team, xin từ người quản lý Auth0
tenant của dự án (không phải thứ `server.py` cấp ra) — xem ví dụ đầy đủ,
chạy được ngay trong `notebooks/greennode_agentbase_test.ipynb` (mục 1).

**Tóm tắt request thật khi gọi qua GreenNode Runtime** (cả 2 header cùng lúc):
```bash
curl -X POST "$GREENNODE_ENDPOINT/chat" \
  -H "Authorization: Bearer $JWT" \
  -H "X-API-Key: $SERVER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "...", "user_id": "..."}'
```

Nhầm/thiếu ở lớp 2 (JWT) thường trả `401`/`403` **từ chính GreenNode
gateway** (không phải từ app) — body lỗi sẽ khác định dạng
`{"detail": "..."}` của app.

## Mô hình `user_id` / `thread_id`

- `user_id` — định danh **cố định** của 1 khách hàng (mã CIF), **bắt buộc**
  ở mọi endpoint.
- `thread_id` — định danh 1 cuộc hội thoại, **luôn optional**.

**Quan trọng — `user_id` cho `POST /chat` phải là 1 mã khách hàng có thật.**
Agent đọc đúng dữ liệu tài chính của khách hàng đó dựa trên `user_id` — hiện
có đúng 3 khách hàng mẫu:

| `user_id` | Tên |
|---|---|
| `CIF_0001` | Ly Lã |
| `CIF_0002` | Trần Toàn |
| `CIF_0003` | Đào Nguyên |

Gửi `POST /chat` với `user_id` **không khớp 1 trong 3 giá trị trên** sẽ trả
về `500` (agent không tìm được dữ liệu khách hàng tương ứng, lỗi bị mask
giống mọi lỗi nội bộ khác — xem bảng lỗi ở mục `/chat` bên dưới).

**Ràng buộc này KHÔNG áp dụng cho `GET`/`DELETE /chat/history`** — 2
endpoint đó chỉ thao tác trên lịch sử hội thoại (không đọc dữ liệu tài
chính khách hàng), nên chấp nhận `user_id` bất kỳ; `user_id` không có thật
chỉ đơn giản trả về lịch sử rỗng, không phải lỗi.

**Hiện tại frontend chỉ truyền `user_id`, không truyền `thread_id`.** Khi bỏ
qua `thread_id`, server tự dùng **chính `user_id`** làm `thread_id` mặc định
— nghĩa là **mỗi user hiện có đúng 1 cuộc hội thoại đang diễn ra**, không
cần frontend tự quản lý/lưu `thread_id` riêng.

Nếu sau này frontend muốn hỗ trợ nhiều cuộc hội thoại cho 1 user (kiểu
"New chat"), chỉ cần bắt đầu truyền `thread_id` tường minh (tự sinh 1 chuỗi
bất kỳ, lưu lại phía frontend, gửi lại đúng giá trị đó ở các lượt sau) —
endpoint không cần đổi gì, cơ chế mặc định vẫn hoạt động song song cho các
request không kèm `thread_id`.

---

## `GET /health`

Kiểm tra server còn sống. Không cần auth.

**Response `200`:**
```json
{ "status": "ok" }
```

---

## `POST /chat`

Gửi 1 tin nhắn, nhận câu trả lời của agent.

**Headers:**
```
X-API-Key: <SERVER_API_KEY>
Content-Type: application/json
```

**Body:**
```json
{
  "message": "Tháng này tôi đã chi tiêu bao nhiêu?",
  "user_id": "CUS-000482"
}
```

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `message` | string | ✅ | Nội dung tin nhắn của khách hàng |
| `user_id` | string | ✅ | Định danh khách hàng |
| `thread_id` | string \| null | ❌ | Bỏ qua → mặc định = `user_id` (xem mục trên) |

**Response `200`:**
```json
{
  "answer": "Tháng này bạn đã chi tiêu 4.250.000 VND...",
  "thread_id": "CUS-000482",
  "ui": null
}
```
`thread_id` trả về là giá trị **thực sự đã dùng** (bằng `user_id` nếu bạn
không truyền) — không bắt buộc phải lưu lại trừ khi bạn chủ động muốn quản
lý nhiều thread.

**⚠️ Breaking change (2026-09-03):** field này trước đây tên là `chart`
(`chart: dict | null`, chỉ chứa dữ liệu biểu đồ). Đã đổi thành `ui`
(`ui: dict | null`) — 1 envelope chung cho mọi loại UI có cấu trúc agent có
thể trả ra, phân biệt bằng field `type` bên trong. **Frontend cần đổi code
đọc `body.chart` sang `body.ui`, và luôn kiểm tra `ui.type` trước khi đọc
các field còn lại.**

`ui` là `null` ở hầu hết câu trả lời. Hiện có 7 loại `ui.type`:

- `"chart"` — biểu đồ cho câu hỏi phân tích/so sánh, xem
  [`docs/chart-visualization.md`](./chart-visualization.md).
- `"transfer_form"` — đề xuất trả nợ thẻ tín dụng điền sẵn, xem
  [`docs/transfer-form.md`](./transfer-form.md).
- `"create_jar"` / `"edit_jar"` / `"distribute_amount"` / `"rebalance_jars"` — bốn loại `ui` về hũ chi tiêu (tạo hũ, sửa hũ, chia tiền chưa phân bổ
  vào hũ, chuyển số dư từ hũ này sang hũ khác). Field, quy tắc và khi nào `ui = null`: xem thư mục [`docs/jars/`](./jars/README.md); `distribute_amount` và
  `rebalance_jars` còn đến từ hai endpoint riêng (dưới đây).
- `"clarify_options"` — hỏi lại bằng 2–4 nút bấm thay vì 1 câu mở, dùng chung cho mọi flow (không riêng
  hũ), kể cả câu hỏi khảo sát sở thích (nhóm lựa chọn chuẩn, không cần dữ liệu thật của khách). `ui.questions`
  là **mảng 1–4 câu hỏi độc lập** (thường chỉ 1). `answer` vẫn có nội dung — chỉ là 1 câu dẫn ngắn, không
  lặp lại nội dung `ui.questions[].question`/`options`; frontend hiện cả `answer` (câu dẫn) và `ui.questions`
  (câu hỏi + nút bấm). Khách trả lời xong hết các câu → frontend gộp các lựa chọn (mỗi câu 1 string trong
  `options`) thành 1 tin nhắn `POST /chat`, nối nhau bằng `". "` theo đúng thứ tự câu hỏi — không có cơ chế
  riêng. Xem [`docs/clarify-options.md`](./clarify-options.md).

Sau này có thêm loại khác, frontend chỉ cần thêm nhánh xử lý theo `ui.type`
mới — bỏ qua `type` chưa hỗ trợ thay vì báo lỗi.

**Lỗi:**
| Status | Khi nào |
|---|---|
| `401` | Thiếu/sai `X-API-Key` |
| `422` | Thiếu `message` hoặc `user_id` |
| `500` | Agent xử lý lỗi (lỗi nội bộ...) — chi tiết lỗi **không** trả về client, chỉ nằm trong log server |
| `503` | Bộ lọc nội dung của nhà cung cấp model (GreenNode/VNG Cloud MaaS) chặn chính đầu ra của model — server đã tự thử lại 1 lần (resume đúng lượt đó, không hỏi lại khách, không trùng lượt trong lịch sử) trước khi trả lỗi này. Lỗi thoáng qua, không phải bug ở agent hay ở dữ liệu khách; frontend nên coi như lỗi tạm thời và cho khách gửi lại tin nhắn |

---

## `POST /jar-distribute` và `POST /jar-rebalance`

Hai endpoint **không cần chat** cho các màn hình đã biết sẵn việc cần làm: chia một số tiền chưa phân bổ vào hũ (`/jar-distribute`) và chuyển số dư từ một hũ sang
các hũ khác (`/jar-rebalance`). Không có hội thoại, không có `thread_id`, không dùng chung agent hay bộ nhớ với `/chat`. Cùng server, cùng `X-API-Key` (và Bearer khi
qua AgentBase như `/chat`). Request, response, các trường hợp trả lời không cần gọi model và mã lỗi: [`docs/jars/endpoints.md`](./jars/endpoints.md).

---

## `GET /chat/history`

Lấy lại toàn bộ lịch sử hội thoại của 1 thread — dùng để hiện lại đoạn chat
cũ khi user mở lại app/mở lại 1 cuộc hội thoại.

**Headers:**
```
X-API-Key: <SERVER_API_KEY>
```

**Query params:**

| Param | Bắt buộc | Ghi chú |
|---|---|---|
| `user_id` | ✅ | |
| `thread_id` | ❌ | Bỏ qua → mặc định = `user_id` |

```
GET /chat/history?user_id=CUS-000482
```

**Response `200`:**
```json
{
  "thread_id": "CUS-000482",
  "messages": [
    { "role": "user", "content": "Tháng này tôi đã chi tiêu bao nhiêu?", "ui": null },
    { "role": "assistant", "content": "Tháng này bạn đã chi tiêu 4.250.000 VND...", "ui": null }
  ]
}
```

- `role` chỉ có 2 giá trị: `"user"` hoặc `"assistant"` — tin nhắn nội bộ
  (tool call, system prompt...) đã bị lọc bỏ, chỉ trả về nội dung phù hợp để
  hiện lên UI chat.
- **⚠️ Breaking change (2026-09-07):** mỗi message giờ có thêm field `ui`
  (cùng schema `ui` của `POST /chat`, xem `docs/chart-visualization.md`/
  `docs/transfer-form.md`) — **đảo ngược lại quyết định trước đó** (từng
  thống nhất `GET`/`DELETE /chat/history` không bao giờ trả `ui`). Nếu tin
  nhắn `assistant` cũ từng kèm chart/form khi mới trả lời, mở lại lịch sử
  giờ sẽ thấy lại đúng `ui` đó; tin nhắn không có `ui` sẽ là `null` (luôn có
  mặt field này, không omit). `role: "user"` luôn có `ui: null`.
- Thread chưa từng chat lần nào → trả về `"messages": []`, **không phải lỗi
  404**.

**Lỗi:**
| Status | Khi nào |
|---|---|
| `401` | Thiếu/sai `X-API-Key` |
| `422` | Thiếu `user_id` |
| `500` | Lỗi đọc lịch sử |

---

## `DELETE /chat/history`

Xoá toàn bộ lịch sử của 1 thread — dùng cho nút "Xoá cuộc trò chuyện" trên UI.

**Headers:**
```
X-API-Key: <SERVER_API_KEY>
```

**Query params:** giống hệt `GET /chat/history` (`user_id` bắt buộc,
`thread_id` optional, mặc định = `user_id`).

```
DELETE /chat/history?user_id=CUS-000482
```

**Response `200`:**
```json
{ "thread_id": "CUS-000482", "status": "deleted" }
```

**⚠️ Lưu ý quan trọng — cache 30 giây:** Sau khi xoá, gọi `GET /chat/history`
**ngay lập tức** (trong vòng ~30 giây) có thể vẫn thấy tin nhắn cũ, dù việc
xoá đã thành công thật trên server GreenNode. Đây là giới hạn của SDK
`AgentBaseMemoryEvents` (bên thứ ba) — nó cache kết quả đọc 30 giây và không
tự xoá cache khi gọi xoá. Sau 30 giây, `GET` sẽ trả về đúng kết quả rỗng.
**Gợi ý cho frontend:** sau khi gọi `DELETE` thành công, tự xoá luôn đoạn
chat khỏi UI phía client (đừng gọi lại `GET` ngay để "xác nhận" — có thể gây
hiểu nhầm là xoá thất bại).

**⚠️ Nghiêm trọng hơn — gọi `POST /chat` quá sớm có thể LÀM MẤT TÁC DỤNG
của lệnh xoá (đã verify thật, không chỉ là đọc nhầm):** nếu gọi `POST /chat`
trong vòng ~30 giây sau `DELETE` (không chỉ `GET`), agent có thể đọc phải
state **cũ** (trước khi xoá) do cùng cơ chế cache ở trên, rồi **ghi tin
nhắn mới đè lên trên lịch sử cũ đó** — kết quả là lịch sử cũ bị "hồi sinh"
lẫn với tin nhắn mới, thay vì bắt đầu từ rỗng như mong đợi. Đây không chỉ
là hiển thị sai tạm thời — dữ liệu cũ thực sự quay lại.
**Bắt buộc với frontend/backend nào tự động hoá việc xoá:** sau khi gọi
`DELETE /chat/history` thành công, **đợi tối thiểu 30 giây** trước khi gọi
`POST /chat` hoặc `GET /chat/history` tiếp theo trên cùng `thread_id`. Nút
"Xoá cuộc trò chuyện" trên UI nên khoá tạm thời ô nhập chat (hoặc chỉ cho
phép "New chat" bằng `thread_id` mới) trong khoảng thời gian này để tránh
race condition.

**Lỗi:**
| Status | Khi nào |
|---|---|
| `401` | Thiếu/sai `X-API-Key` |
| `422` | Thiếu `user_id` |
| `500` | Lỗi xoá lịch sử |

---

## Ví dụ luồng dùng điển hình (1 user, chưa cần multi-thread)

**Gọi local/docker-compose** (chỉ cần `X-API-Key`, không cần Auth0):

```bash
# 1. Chat
curl -X POST "$BASE_URL/chat" \
  -H "X-API-Key: $SERVER_API_KEY" -H "Content-Type: application/json" \
  -d '{"message": "Tháng này tôi chi tiêu bao nhiêu?", "user_id": "CUS-000482"}'

# 2. Mở lại app -> load lịch sử
curl "$BASE_URL/chat/history?user_id=CUS-000482" \
  -H "X-API-Key: $SERVER_API_KEY"

# 3. User bấm "Xoá cuộc trò chuyện"
curl -X DELETE "$BASE_URL/chat/history?user_id=CUS-000482" \
  -H "X-API-Key: $SERVER_API_KEY"
```

**Gọi qua GreenNode AgentBase Runtime** (cần lấy `JWT` trước, xem mục Xác
thực ở trên):

```bash
# 0. Lấy JWT từ Auth0 (1 lần, cache tới khi hết hạn)
JWT=$(curl -s -X POST "https://$AUTH0_DOMAIN/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"'"$AUTH0_CLIENT_ID"'","client_secret":"'"$AUTH0_CLIENT_SECRET"'","audience":"'"$AUTH0_AUDIENCE"'","grant_type":"client_credentials"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 1. Chat -- luôn kèm cả 2 header
curl -X POST "$GREENNODE_ENDPOINT/chat" \
  -H "Authorization: Bearer $JWT" \
  -H "X-API-Key: $SERVER_API_KEY" -H "Content-Type: application/json" \
  -d '{"message": "Tháng này tôi chi tiêu bao nhiêu?", "user_id": "CUS-000482"}'
```

## Chưa hỗ trợ (tham khảo `todo.md` nếu cần)

- Liệt kê danh sách các `thread_id` của 1 `user_id` (kiểu sidebar "các cuộc
  hội thoại trước") — hiện chưa cần vì mỗi user chỉ có 1 thread mặc định.
- Đa thread thật sự cho 1 user trên UI (frontend cần tự sinh và quản lý
  `thread_id` nếu muốn dùng — cơ chế server đã sẵn sàng, chỉ chưa được UI
  dùng tới).

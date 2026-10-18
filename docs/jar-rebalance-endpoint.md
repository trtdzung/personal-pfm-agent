# `POST /jar-rebalance` — endpoint cho màn hình không cần chat — hướng dẫn cho frontend

Endpoint riêng cho các màn hình đã biết sẵn việc cần làm nên **không cần hội thoại**. Tài liệu này chỉ mô tả endpoint đó; hai
loại `ui` của luồng chat nằm ở tài liệu khác:

- `rebalance_jars` (bù hũ thiếu, cũng là kết quả của `mode: "cover"` ở đây): [`docs/jar-rebalance.md`](./jar-rebalance.md).
- Danh sách mọi `ui.type` và cách đọc `ui`: [`docs/api.md`](./api.md).

Nhắc lại phân vai: agent **chỉ đề xuất**; `pfm` kiểm lại với số thật và chỉ ghi khi khách bấm xác nhận.

**Một endpoint, hai `mode`**; cùng server với `/chat`, cùng header `X-API-Key` (khi qua AgentBase kèm thêm
`Authorization: Bearer …` như `/chat`). Không có `thread_id`, không nhớ gì giữa các lần gọi, không dùng chung agent với `/chat`.
pfm gọi qua route proxy cùng kiểu `src/app/api/agent/chat/route.ts` (ví dụ `src/app/api/agent/jar-rebalance/route.ts` chuyển tiếp
tới `${AGENT_API_BASE_URL}/jar-rebalance`), để khoá không lộ ra trình duyệt.

## Request

`user_id` là CIF; model không bao giờ tự truyền. Client chỉ gửi định danh và số tiền — server tự đọc `jar-summary` của khách từ pfm.

| Field | `cover` | `distribute` | Ghi chú |
|---|---|---|---|
| `user_id` | ✅ | ✅ | id khách; server dùng nó để đọc `jar-summary` |
| `mode` | `"cover"` | `"distribute"` | |
| `target_jar_id` | ✅ | **không được có** | hũ đang thiếu (`id` theo `jar-summary`) |
| `spend_amount` | tuỳ chọn | **không được có** | số tiền khách định chi từ hũ đó (VND, > 0). Bỏ = bù hũ đang "cần bù" |
| `amount` | **không được có** | bắt buộc | số tiền khách muốn chia vào các hũ (VND, > 0). Đây là tiền của chính khách: **không** lấy từ hũ nào và **không bị giới hạn bởi tiền chưa phân bổ** |

```json
{ "user_id": "CIF_0001", "mode": "cover", "target_jar_id": "food", "spend_amount": 16000000 }
```

```json
{ "user_id": "CIF_0001", "mode": "distribute", "amount": 600000 }
```

## Response `200`

`{ "answer": string, "ui": object | null }`. `answer` là 1–3 câu cho khách, mỗi câu một đoạn (cách nhau một
dòng trống). `ui` là `rebalance_jars` (`cover`) hoặc `distribute_amount` (`distribute`), hoặc `null` khi không có đề xuất — lúc đó
chỉ hiện `answer`. Thời gian gọi model khoảng 10–25 giây, nên màn hình cần trạng thái chờ.

```json
{
  "answer": "Hũ Ăn uống thiếu 14.187.000đ cho khoản chi 16.000.000đ.\n\nMình đề xuất lấy 13.044.000đ từ tiền chưa phân bổ và 1.143.000đ từ hũ Hưởng thụ, bạn xem lại rồi xác nhận nhé.",
  "ui": {
    "type": "rebalance_jars",
    "target_jar_id": "food",
    "shortfall": 14187000,
    "moves": [
      { "from_jar_id": "pool", "amount": 13044000 },
      { "from_jar_id": "lifestyle", "amount": 1143000 }
    ],
    "reason": "Lấy hết tiền chưa phân bổ trước, phần còn lại từ hũ Hưởng thụ vì hũ này còn nhiều tiền nhất."
  }
}
```

## Ai làm gì

Server tự đọc `jar-summary` của `user_id` rồi **tự tính mọi con số là sự thật** — `shortfall`, số tiền `pool` có thể cho — nên
model không bao giờ được hỏi `shortfall`. Model chỉ **chọn nguồn/chia** và viết câu cho khách; đề xuất của nó bị kiểm bằng chính
`jar-summary` đó:

- Vi phạm quy tắc cứng (nguồn cho quá `spendable`, `pool` quá `unallocated`, id không có thật, sai `shortfall`, Σ không khớp, chia
  quá `amount`) → **không bao giờ trả về**. Được thử lại 1 lần kèm lý do; vẫn sai thì `ui: null` và `answer` là
  "Chưa tạo được đề xuất phù hợp lúc này, bạn thử lại sau nhé."
- Chỉ sai thứ tự ưu tiên (`cover`), chưa chia hết (`distribute`) hoặc lời văn lộ thuật ngữ / `reason` quá 300 ký tự → thử lại 1
  lần kèm cách đúng; nếu vẫn vậy thì **vẫn trả đề xuất** (pfm nhận mọi thứ tự, đó chỉ là ưu tiên).

## Trả lời ngay bằng code, không gọi model

`ui: null`, phản hồi tức thì:

| Tình huống | `answer` |
|---|---|
| `cover`: hũ đã đủ tiền cho khoản định chi (hoặc không cần bù) | "Hũ … đã đủ tiền cho khoản này, không cần bù thêm." |
| `cover`: hũ chưa đặt hạn mức | nhắc đặt hạn mức trước (`edit_jar`) |
| `cover`: tiền chưa phân bổ + các hũ khác cộng lại vẫn chưa đủ | nêu còn thiếu bao nhiêu và các nguồn cộng lại có bao nhiêu |
| `distribute`: chưa hũ nào đặt hạn mức | nhắc đặt hạn mức cho hũ trước |

## Mã lỗi

`401` thiếu/sai `X-API-Key`; `404` `target_jar_id` không có trong `jar-summary` của khách; `422` request sai
(thiếu `target_jar_id` khi `cover`, có `target_jar_id`/`spend_amount` khi `distribute`, số ≤ 0, `mode` lạ); `502` không đọc được
`jar-summary` từ pfm; `503` model không gọi được (lỗi mạng, quá 45 giây, hoặc không trả đúng cấu trúc ở cả hai lần thử) — khác với
"không có đề xuất phù hợp" (`200`, `ui: null`), nên màn hình có thể cho khách bấm thử lại.

## `mode: "cover"` → `rebalance_jars`

Cùng contract như phần trên. Điểm khác: `shortfall` do server tính (`số định chi − spendable` của hũ đích khi có `spend_amount`;
`−remaining` khi hũ đang cần bù), và `moves` theo đúng thứ tự `pool` rồi hũ nhiều tiền nhất.

## `mode: "distribute"` → `distribute_amount` (loại `ui` mới)

Chia **một số tiền khách nêu (`amount`)** vào **số dư** của nhiều hũ trong tháng hiện tại. Đây là tiền của chính khách: **không** lấy
từ hũ nào và **không bị giới hạn bởi tiền chưa phân bổ**. Agent chỉ cộng vào số dư các hũ nhận, **không đổi `budgetLimit`**.

```json
{
  "type": "distribute_amount",
  "allocations": [
    { "to_jar_id": "lifestyle", "amount": 200000 },
    { "to_jar_id": "food", "amount": 800000 },
    { "to_jar_id": "move", "amount": 500000 }
  ],
  "reason": "Hũ Hưởng thụ đang thiếu 200.000đ nên bù trước; hũ Ăn uống sắp hết tiền nên nhận thêm 800.000đ, phần còn lại cho hũ Di chuyển."
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `type` | ✅ | `"distribute_amount"` |
| `allocations` | ✅ | mảng ≥ 1 phần tử |
| `allocations[].to_jar_id` | ✅ | `id` hũ nhận (theo `jar-summary`); không phải `"pool"` |
| `allocations[].amount` | ✅ | VND cộng vào số dư hũ đó, số nguyên > 0 |
| `reason` | ✅ | căn cứ chia, 1–2 câu ngắn, không thuật ngữ |

**Quy tắc cứng** (server kiểm trước khi trả; pfm **phải kiểm lại** khi khách xác nhận và bỏ đề xuất nếu sai):

1. `allocations` không rỗng, mỗi `amount` > 0, mỗi hũ nhận **một lần**.
2. Chỉ hũ có `budgetLimit` mới nhận được (cùng quy tắc với hũ đích của `rebalance_jars`).
3. Σ `allocations[].amount` ≤ `amount` của request (agent cố chia **hết** `amount`; chỉ chừa lại khi không hũ nào cần thêm).
4. Mọi `to_jar_id` có trong `jar-summary`.

**Phía pfm khi khách xác nhận:** chỉ cộng vào số dư các hũ nhận (không đổi `budgetLimit`). Gợi ý ghi mỗi phần tử một bản ghi bù
(`dieu-chinh-hu`) cộng cho hũ nhận. Lưu ý `unallocated` = `casaBalance − Σ spendable`, nên sau khi ghi `unallocated` giảm đúng
`amount`; nếu `amount` lớn hơn tiền chưa phân bổ hiện có thì `unallocated` thành âm — pfm tự quyết cho phép hay từ chối (endpoint này
không kiểm điều đó vì `amount` là tiền của khách).

**Chia thế nào** là nguyên tắc sản phẩm (đổi được trong `prompts/jar_distribute.md`): hũ đang cần bù trước (tối đa bằng số thiếu),
rồi hũ khách thường chi nhiều mà số dư còn ít; chia **hết** `amount` trừ khi không hũ nào cần thêm.

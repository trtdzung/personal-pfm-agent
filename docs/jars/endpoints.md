# `POST /jar-distribute` và `POST /jar-rebalance` — endpoint không cần chat

Hai endpoint cho các màn hình đã biết sẵn việc cần làm nên **không cần hội thoại**. Chúng làm đúng việc của hai skill chat và trả `ui` cùng dạng:

| Endpoint | Việc | `ui` trả về (định nghĩa ở) |
|---|---|---|
| `POST /jar-distribute` | chia một số tiền **chưa phân bổ** vào hũ | `distribute_amount` — [`distribute-amount.md`](./distribute-amount.md) |
| `POST /jar-rebalance` | chuyển số dư **từ 1 hũ** sang 1 hoặc nhiều hũ khác | `rebalance_jars` — [`rebalance-jars.md`](./rebalance-jars.md) |

Khác chat: khách đã chọn sẵn số tiền (và hũ nguồn) trên màn hình; **Agent tự quyết chia cho hũ nào, bao nhiêu** — trừ khi request chỉ định hũ nhận. Nguyên tắc
"chỉ đề xuất" và các lớp kiểm: [`README.md`](./README.md).

Cùng server với `/chat`, cùng header `X-API-Key` (qua AgentBase kèm `Authorization: Bearer …` như `/chat`). Không có `thread_id`, không nhớ gì giữa các lần gọi,
không dùng chung agent với `/chat`. `pfm` gọi qua route proxy cùng kiểu `src/app/api/agent/chat/route.ts` (ví dụ `src/app/api/agent/jar-distribute/route.ts` chuyển
tiếp tới `${AGENT_API_BASE_URL}/jar-distribute`) để khoá không lộ ra trình duyệt.

## Request

`user_id` là CIF; model không bao giờ tự truyền. Client chỉ gửi định danh và số tiền — server tự đọc dữ liệu hũ của khách từ `pfm`. Field lạ (kể cả `mode`,
`target_jar_id`, `spend_amount` của endpoint cũ) bị từ chối `422`.

| Field | `/jar-distribute` | `/jar-rebalance` | Ghi chú |
|---|---|---|---|
| `user_id` | ✅ | ✅ | id khách |
| `amount` | ✅ | ✅ | VND, số nguyên > 0. Distribute: số tiền chưa phân bổ cần chia. Rebalance: số tiền hũ nguồn cho đi |
| `from_jar_id` | không có | ✅ | hũ cho tiền (`id` theo `jar-summary`) |
| `jar_ids` | tuỳ chọn | không có | chỉ chia vào các hũ này (không rỗng, không lặp); bỏ = Agent tự chọn |
| `to_jar_ids` | không có | tuỳ chọn | chỉ chuyển sang các hũ này (không rỗng, không lặp, không chứa `from_jar_id`); bỏ = Agent tự chọn |

```json
{ "user_id": "CIF_0001", "amount": 1000000 }
```

```json
{ "user_id": "CIF_0001", "from_jar_id": "food", "amount": 500000, "to_jar_ids": ["transport"] }
```

## Response `200`

`{ "answer": string, "ui": object | null }`. `answer` là 1–3 câu cho khách, mỗi câu một đoạn (cách nhau một dòng trống). `ui` là `null` khi không có đề xuất — lúc đó
chỉ hiện `answer`. Thời gian gọi model khoảng 10–25 giây, nên màn hình cần trạng thái chờ.

```json
{
  "answer": "Mình đề xuất chia 600.000đ vào hũ Ăn uống và 400.000đ vào hũ Di chuyển, bạn xem lại rồi xác nhận nhé.",
  "ui": {
    "type": "distribute_amount",
    "allocations": [
      { "to_jar_id": "food", "amount": 600000 },
      { "to_jar_id": "transport", "amount": 400000 }
    ],
    "reason": "Hũ Ăn uống chi nhiều nhất 3 tháng qua nên nhận nhiều hơn, phần còn lại cho hũ Di chuyển"
  }
}
```

```json
{
  "answer": "Mình đề xuất chuyển 500.000đ từ hũ Ăn uống sang hũ Di chuyển, bạn xem lại rồi xác nhận nhé.",
  "ui": {
    "type": "rebalance_jars",
    "from_jar_id": "food",
    "allocations": [{ "to_jar_id": "transport", "amount": 500000 }],
    "reason": "Hũ Ăn uống còn 2.613.000đ nên đủ chuyển 500.000đ; hũ Di chuyển đã chi gần hết số dư"
  }
}
```

## Agent được cấp dữ liệu gì

Endpoint **không để model tự đi tra**: server đọc rồi đưa thẳng vào lời nhắc, gồm

- `jar-summary` của khách (mọi hũ: `limit`, `balance`, đã chi, `overLimit`, danh mục; tiền chưa phân bổ) — không đọc được → `502`;
- **chi tiêu ròng của từng hũ trong 3 tháng dương lịch gần nhất** (chi − hoàn, bỏ giao dịch ẩn; gom về hũ theo danh mục của hũ), để chia theo nhu cầu thật. Không đọc
  được giao dịch thì vẫn chạy, Agent được dặn chia theo số dư hiện tại;
- rebalance: số tối đa hũ nguồn cho được (`spendable`); distribute: số tiền chưa phân bổ hiện có.

## Ai làm gì

Server tính mọi con số là sự thật; model chỉ **chọn hũ nhận / chia** và viết câu cho khách. Đề xuất của model bị kiểm bằng `jar_checks.py` (trên chính `jar-summary` đã đọc):

- **Vi phạm quy tắc cứng** → không bao giờ trả về: tổng vượt `amount`, vượt tiền chưa phân bổ (distribute) hoặc `spendable` hũ nguồn (rebalance), id không có trong `jar-summary`,
  ngoài danh sách `jar_ids` / `to_jar_ids` khách chỉ định, hũ nguồn khác `from_jar_id`, sai hình dạng. Được thử lại **1 lần** kèm lý do; vẫn sai thì `ui: null` và `answer` là
  "Chưa tạo được đề xuất phù hợp lúc này, bạn thử lại sau nhé."
- **Chỉ lỗi mềm** — chưa chia/chuyển hết `amount` (không nói lý do trong `reason`), lời văn lộ tên nội bộ (`balance`, `spendable`, id…), `reason` quá 300 ký tự → thử lại 1 lần;
  vẫn vậy thì **vẫn trả đề xuất**.
- `pfm` vẫn kiểm lại với số thật khi khách xác nhận.

## Trả lời ngay bằng code, không gọi model

`ui: null`, phản hồi tức thì, `200`:

| Endpoint | Tình huống | `answer` (ý chính) |
|---|---|---|
| distribute | khách chưa có hũ nào | nhắc tạo hũ trước |
| distribute | không còn tiền chưa phân bổ | chưa có tiền để chia |
| distribute | `amount` > tiền chưa phân bổ | "Tiền chưa phân bổ hiện chỉ còn … nên chưa chia được …" |
| rebalance | hũ nguồn chưa có số dư (`balance: null`) | nhắc nạp tiền vào hũ trước |
| rebalance | hũ nguồn hết số dư (`balance` ≤ 0) | chưa chuyển được tiền đi |
| rebalance | `amount` > `spendable` hũ nguồn | "Hũ … hiện chỉ còn … nên chưa chuyển được …" |
| rebalance | khách chưa có hũ nào khác | nhắc tạo thêm hũ |

## Mã lỗi

| Status | Khi nào |
|---|---|
| `401` | thiếu/sai `X-API-Key` |
| `404` | `from_jar_id`, `jar_ids` hoặc `to_jar_ids` có id không có trong `jar-summary` của khách |
| `422` | request sai: thiếu field, `amount` ≤ 0, id lặp, `from_jar_id` nằm trong `to_jar_ids`, field lạ |
| `502` | không đọc được `jar-summary` từ `pfm` |
| `503` | model không gọi được (lỗi mạng, quá 45 giây, hoặc không trả đúng cấu trúc ở cả hai lần thử) — khác "không có đề xuất phù hợp" (`200`, `ui: null`), nên màn hình có thể cho khách bấm thử lại |

## Chia thế nào

Nguyên tắc sản phẩm, đổi được trong `prompts/jar_distribute.md` và `prompts/jar_rebalance.md`: hũ cần bù (`balance` < 0) trước, rồi hũ khách thường chi nhiều
(theo 3 tháng gần nhất) mà số dư còn ít; chia **hết** `amount` trừ khi không hũ nào cần thêm. Khách chỉ định hũ nhận thì chỉ dùng các hũ đó.

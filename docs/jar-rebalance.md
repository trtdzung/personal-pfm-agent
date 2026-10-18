# Cân đối số dư giữa các hũ (`rebalance_jars`) — hướng dẫn cho frontend

Loại UI thứ 3 về hũ chi tiêu (cùng envelope `ui` với `chart`, `transfer_form`, `create_jar`/`edit_jar` — xem
[`docs/api.md`](./api.md), [`docs/spending-jar.md`](./spending-jar.md)). Contract đầy đủ phía `pfm`:
`backend_docs/pfm-read-api.md` (phần B4).

## Khi nào agent trả `rebalance_jars`

- **(a)** khách định chi 1 khoản lớn hơn số dư hũ (`spendable` không đủ), hoặc
- **(b)** khách **đã chi vượt** hũ (`remaining` < 0, `overLimit: true`).

Agent đề xuất **lấy phần thiếu từ hũ/tiền chưa phân bổ nào**. Form này **không** chuyển tiền thật và **không**
đổi hạn mức (`budgetLimit`) — chỉ điều chỉnh số dư (`remaining`) giữa các hũ **trong tháng hiện tại**; sang
tháng sau `remaining` tính lại từ `budgetLimit`. Muốn thêm tiền cho hũ **lâu dài** thì agent dùng `edit_jar`
(tăng hạn mức), không dùng form này. Form này **độc lập** với `transfer_form` (không có hũ nguồn của việc chuyển
tiền — khách chọn nguồn trên màn chuyển tiền).

**Đây chỉ là đề xuất hiển thị — agent KHÔNG tự ghi gì.** `pfm` ghi khi khách xem lại và bấm xác nhận.

## Response `POST /chat`

```json
{
  "answer": "Hũ Ăn uống thiếu 1.500.000đ cho khoản chi này.\n\nMình đề xuất lấy 1.000.000đ từ tiền chưa phân bổ và 500.000đ từ hũ Hưởng thụ, bạn xem lại rồi xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "rebalance_jars",
    "target_jar_id": "food",
    "shortfall": 1500000,
    "moves": [
      { "from_jar_id": "pool", "amount": 1000000 },
      { "from_jar_id": "lifestyle", "amount": 500000 }
    ],
    "reason": "Hũ Ăn uống thiếu 1.500.000đ; lấy 1.000.000đ từ tiền chưa phân bổ (còn 1.000.000đ) và 500.000đ từ hũ Hưởng thụ (còn 2.088.000đ)"
  }
}
```

## Schema của `ui`

| Field | Bắt buộc | Kiểu | Ghi chú |
|---|---|---|---|
| `type` | ✅ | `"rebalance_jars"` | discriminator |
| `target_jar_id` | ✅ | string | `id` hũ đang thiếu (theo `jar-summary`); phải có `budgetLimit`; không phải `"pool"` |
| `shortfall` | ✅ | number > 0 | VND còn thiếu. (a): số định chi − `spendable` của hũ đích. (b): −`remaining` của hũ đích |
| `moves` | ✅ | mảng ≥ 1 | các nguồn lấy tiền |
| `moves[].from_jar_id` | ✅ | string | `id` hũ cho tiền, hoặc `"pool"` = `unallocated` ("Chưa phân bổ") |
| `moves[].amount` | ✅ | number > 0 | VND lấy từ nguồn đó |
| `reason` | ✅ | string, không rỗng | vì sao chọn các nguồn này, nêu số thật |

Agent chỉ trả `id` và con số — không trả lại tên hũ; hiện tên bằng cách tra `id` trong dữ liệu hũ của `pfm`.

## Quy tắc cứng

`server.py` kiểm ngay khi nhận từ model, bỏ hẳn `ui` nếu vi phạm (chỉ kiểm được điều không cần dữ liệu ngoài):

1. Đủ field, đúng kiểu; `moves` không rỗng, mỗi `amount` > 0.
2. **Σ `moves[].amount` đúng bằng `shortfall`.**
3. `from_jar_id` ≠ `target_jar_id`, không lặp nguồn; `target_jar_id` không phải `"pool"`.

`pfm` **phải kiểm lại** với số thật khi khách xác nhận, và bỏ đề xuất nếu vi phạm bất kỳ điều nào:

4. `shortfall` khớp số `pfm` tự tính từ hũ đích.
5. Mỗi hũ cho chỉ cho tối đa `spendable` của nó (không đẩy hũ cho xuống âm); hũ `spendable: null` (chưa đặt
   hạn mức) không được cho.
6. Nguồn `"pool"` chỉ cho tối đa `max(0, unallocated)` (khác `allocationHeadroom`).
7. Hũ `role: "goal"` (mục tiêu, được bảo vệ) **không được có trong `moves`**. Nếu chỉ hũ `goal` mới đủ bù, agent
   nói trong `answer` để khách tự quyết và **không** trả `ui`.

**Thứ tự ưu tiên agent theo** (cùng thứ tự engine `pfm` dùng; là gợi ý, không phải quy tắc cứng):
`pool` → hũ `buffer` (dự phòng/tiết kiệm) → hũ `spending` (vắng `role` = `spending`) → hũ `essential` (thiết
yếu, cuối cùng). Trong cùng nhóm, hũ có `spendable` lớn nhất lấy trước. Mỗi nguồn lấy `min(spendable, phần còn
thiếu)` rồi dừng khi đủ.

## Khi nào agent KHÔNG trả `ui`

Chỉ có `answer`, `ui = null` khi: tổng các nguồn (trừ `goal`) vẫn không đủ bù; chỉ hũ `goal` mới đủ; đọc `jar-summary`
lỗi hoặc số cần thiết là `null`; hũ đích không tồn tại hoặc chưa đặt hạn mức. Nhiều hũ cùng vượt hạn mức: agent
chỉ xử lý **1 hũ mỗi lượt** (hũ `remaining` âm nhất trước) và nói trong `answer` còn hũ nào cần bù.

## Luồng UI gợi ý

1. Nhận `ui.type === "rebalance_jars"` → hiện 1 form/card dưới bong bóng chat: tên hũ đích + số thiếu, danh sách
   `moves` (tên nguồn tra từ `id`, số tiền), kèm `reason`. Nguồn `"pool"` hiện là "Chưa phân bổ".
2. Chỉ đọc, không cho khách tự sửa số tiền; muốn phương án khác thì hỏi lại agent.
3. Nút xác nhận: **khi bấm, `pfm` (không phải agent) ghi mỗi phần tử `moves` một bản ghi bù giữa hũ**
   (`categoryId: "dieu-chinh-hu"`, `meta.fromJarId`/`toJarId`); số dư hai hũ tự cập nhật, còn `spent` và `budgetLimit`
   không đổi. Không gọi endpoint nào của `server.py`.
4. Sau khi khách xác nhận, số trong `jar-summary` đã đổi; lượt chat tiếp theo agent đọc lại trước khi gợi ý bước sau.
5. `ui` là `null`, `ui.type` chưa hỗ trợ, hoặc `pfm` kiểm lại thấy sai → chỉ hiện `answer`.

## Ví dụ số

Hũ Ăn uống (`food`) `remaining` 2.378.000đ; khách định chi 3.878.000đ từ hũ này → `shortfall` = 3.878.000 −
2.378.000 = 1.500.000đ. "Chưa phân bổ" (`unallocated`) đang 1.000.000đ nên `pool` cho tối đa 1.000.000đ; còn thiếu
500.000đ lấy từ hũ Hưởng thụ (`lifestyle`, `spendable` 2.088.000đ) → `moves` như JSON ở trên. Sau khi áp dụng và chi:
Ăn uống `remaining` = 2.378.000 − 3.878.000 + 1.500.000 = 0.

Trường hợp (b), hũ đã chi vượt:

```json
{
  "type": "rebalance_jars",
  "target_jar_id": "lifestyle",
  "shortfall": 400000,
  "moves": [{ "from_jar_id": "emergency", "amount": 400000 }],
  "reason": "Hũ Hưởng thụ chi vượt 400.000đ; tiền chưa phân bổ hết, hũ Dự phòng còn 3.000.000đ nên lấy 400.000đ từ đó"
}
```

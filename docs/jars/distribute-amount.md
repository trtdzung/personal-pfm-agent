# `distribute_amount` — chia tiền chưa phân bổ vào hũ

Loại `ui` do skill `distribute-amount` trả trong `POST /chat`, và do `POST /jar-distribute` trả (không chat, xem [`endpoints.md`](./endpoints.md)).
Khái niệm `balance` / `unallocated` và nguyên tắc chung: [`README.md`](./README.md). Chuyển tiền **từ một hũ** sang hũ khác là form khác:
[`rebalance-jars.md`](./rebalance-jars.md).

## Khi nào Agent trả

Khách muốn chuyển một số tiền vào 1 hoặc nhiều hũ mà **không nêu hũ nguồn**: "chuyển 300k vào hũ Tiết kiệm", "chia 1 triệu vào Ăn uống và Di chuyển",
"bù giúp tôi" cho hũ đang hết số dư. Tiền **luôn lấy từ tiền chưa phân bổ**; Agent chỉ cộng vào **số dư** các hũ nhận, **không đổi `limit`**.

```json
{
  "answer": "Mình đề xuất chia 600.000đ vào hũ Ăn uống và 400.000đ vào hũ Di chuyển từ tiền chưa phân bổ, bạn xem lại rồi xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "distribute_amount",
    "allocations": [
      { "to_jar_id": "food", "amount": 600000 },
      { "to_jar_id": "transport", "amount": 400000 }
    ],
    "reason": "Chia 1.000.000đ tiền chưa phân bổ theo đúng số khách nêu cho hũ Ăn uống và hũ Di chuyển"
  }
}
```

Một hũ chưa có số dư ("chuyển 300k vào hũ Tiết kiệm") vẫn nhận được — khoản nạp chính là số dư đầu tiên:

```json
{
  "type": "distribute_amount",
  "allocations": [{ "to_jar_id": "savings", "amount": 300000 }],
  "reason": "Khách muốn chuyển 300.000đ từ tiền chưa phân bổ vào hũ Tiết kiệm; hũ chưa có số dư nên khoản này là số dư đầu tiên"
}
```

## Schema của `ui`

| Field | Bắt buộc | Kiểu | Ghi chú |
|---|---|---|---|
| `type` | ✅ | `"distribute_amount"` | discriminator |
| `allocations` | ✅ | mảng ≥ 1 | các hũ nhận tiền, mỗi hũ **một lần**; nhiều hũ trong 1 câu thì vào cùng 1 form |
| `allocations[].to_jar_id` | ✅ | string | `id` hũ có trong `jar-summary` của lượt đó; không phải `"pool"` |
| `allocations[].amount` | ✅ | số nguyên > 0 (VND) | cộng vào **số dư** hũ đó; không đổi hạn mức |
| `reason` | ✅ | string, không rỗng | căn cứ chia, 1–2 câu |

## Quy tắc

Agent đã tôn trọng (`pfm` vẫn kiểm lại khi ghi, và bỏ đề xuất nếu sai):

1. Tổng `allocations[].amount` ≤ max(0, `unallocated`); **không lấy từ hũ khác**. Khách nêu tổng vượt số này thì Agent không trả `ui` và nói còn bao nhiêu.
2. Khách nêu số cho từng hũ → đúng số đó. Chỉ nêu 1 tổng cho nhiều hũ → hũ cần bù (`balance` < 0) trước (tối đa −`balance`), phần còn lại chia đều (endpoint: theo chi tiêu 3 tháng của từng hũ).
3. "Bù giúp tôi" cho hũ đang hết số dư mà không nêu số → nạp đúng số thiếu −`balance`.
4. Mọi hũ nhận được, kể cả hũ `balance: null` hoặc chưa đặt hạn mức.

Phía `pfm` khi khách xác nhận: cộng vào số dư các hũ nhận (gợi ý mỗi phần tử một bản ghi `dieu-chinh-hu`); sau khi ghi `unallocated` giảm đúng tổng.
Lượt sau Agent đọc lại `jar-summary`.

> ⚠️ **Cần `pfm` xác nhận:** `pfm` chưa có card `distribute_amount` (xem cảnh báo ở [`README.md`](./README.md)); `backend_docs/pfm-read-api.md` cũng chưa nhắc loại này.

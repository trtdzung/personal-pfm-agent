# `rebalance_jars` — chuyển số dư từ một hũ sang hũ khác

Loại `ui` do skill `rebalance-jars` trả trong `POST /chat`, và do `POST /jar-rebalance` trả (không chat, xem [`endpoints.md`](./endpoints.md)).
Khái niệm `balance` / `spendable` và nguyên tắc chung: [`README.md`](./README.md). Nạp tiền **chưa phân bổ** vào hũ là form khác:
[`distribute-amount.md`](./distribute-amount.md).

> **Đổi dạng (2026-09-24, breaking cho `pfm`):** dạng cũ `{target_jar_id, shortfall, moves[]}` (1 hũ đích nhận từ nhiều nguồn, có nguồn `"pool"`) **đã bỏ**.
> Dạng mới: **1 hũ nguồn cho tiền sang 1 hoặc nhiều hũ khác**. Payload dạng cũ bị `server.py` bỏ (`ui = null`).

## Khi nào Agent trả

- Khách nêu: "chuyển 500 nghìn từ hũ Ăn uống sang hũ Di chuyển" (1 hoặc nhiều hũ nhận, có thể nêu số cho từng hũ).
- Khách không nêu hũ nguồn: hũ hết số dư (`balance` < 0) hoặc định chi nhiều hơn `spendable`, "lấy từ hũ khác bù" → Agent chọn **1 hũ nguồn** có `spendable` lớn nhất
  và đủ cho số cần bù một mình.

Form **không chuyển tiền thật và không đổi `limit`**: chỉ dịch chuyển `balance` giữa các hũ, số dư sau khi chuyển được **mang sang tháng sau**. Tăng hạn mức
(`edit_jar`) không thay được form này. `overLimit` không phải lý do để chuyển tiền. Form độc lập với `transfer_form`.

```json
{
  "answer": "Mình đề xuất chuyển từ hũ Ăn uống 300.000đ sang hũ Di chuyển và 200.000đ sang hũ Sức khỏe, bạn xem lại rồi xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "rebalance_jars",
    "from_jar_id": "food",
    "allocations": [
      { "to_jar_id": "transport", "amount": 300000 },
      { "to_jar_id": "health", "amount": 200000 }
    ],
    "reason": "Chuyển 500.000đ từ hũ Ăn uống sang hũ Di chuyển và hũ Sức khỏe theo đúng số khách nêu"
  }
}
```

Bù hũ hết số dư (hũ Hưởng thụ thiếu 400.000đ, hũ Dự phòng còn 3.000.000đ là hũ nhiều tiền nhất):

```json
{
  "type": "rebalance_jars",
  "from_jar_id": "emergency",
  "allocations": [{ "to_jar_id": "lifestyle", "amount": 400000 }],
  "reason": "Hũ Hưởng thụ còn thiếu 400.000đ chưa được bù; hũ Dự phòng còn 3.000.000đ, nhiều nhất nên lấy 400.000đ từ đó"
}
```

## Schema của `ui`

| Field | Bắt buộc | Kiểu | Ghi chú |
|---|---|---|---|
| `type` | ✅ | `"rebalance_jars"` | discriminator |
| `from_jar_id` | ✅ | string | `id` hũ cho tiền (có trong `jar-summary` của lượt đó); không phải `"pool"` |
| `allocations` | ✅ | mảng ≥ 1 | các hũ nhận, mỗi hũ **một lần** |
| `allocations[].to_jar_id` | ✅ | string | `id` hũ nhận; khác `from_jar_id`; không phải `"pool"` |
| `allocations[].amount` | ✅ | số nguyên > 0 (VND) | cộng vào `balance` hũ nhận, trừ khỏi hũ nguồn |
| `reason` | ✅ | string, không rỗng | vì sao chia như vậy, số thật |

## Quy tắc

`text_utils.py` + `ui_guard.py` kiểm hình dạng và id ngay khi nhận từ model. `pfm` **phải kiểm lại** với số thật khi khách xác nhận và bỏ đề xuất nếu sai:

1. Σ `allocations[].amount` ≤ `spendable` của hũ nguồn (không đẩy hũ nguồn xuống âm). Hũ nguồn `balance: null` (chưa có số dư) **không cho được**.
2. `from_jar_id` ≠ `to_jar_id`; mỗi hũ nhận một lần; không có `"pool"` ở đâu cả.
3. Hũ nhận là hũ bất kỳ có trong `jar-summary`, kể cả hũ chưa có số dư.

Chỉ 1 hũ nguồn mỗi form: khách nêu nhiều hũ nguồn thì Agent làm hũ đầu tiên và nói còn hũ nào để lượt sau.

## Khi Agent KHÔNG trả `ui`

Hũ nguồn không đủ (Agent nói còn bao nhiêu và hỏi khách chuyển tối đa hay số khác); hũ nguồn chưa có số dư (nhắc nạp tiền vào hũ trước); không hũ nào đủ một mình để bù;
`jar-summary` lỗi hoặc số cần thiết là `null`; hũ khách nhắc không có (kể cả hũ vừa đề xuất tạo mà khách chưa xác nhận — Agent không bịa id).

## Phía `pfm` khi khách xác nhận

Ghi mỗi phần tử `allocations` một bản ghi chuyển giữa hai hũ (`categoryId: "dieu-chinh-hu"`, `meta.fromJarId` / `toJarId`); `balance` hai hũ tự cập nhật,
`spent` và `limit` không đổi. Không gọi endpoint nào của `server.py`. Card cần đổi sang dạng mới (`isRebalanceJarsUi`, `AgentRebalanceCard`, `agent-rebalance.ts`).

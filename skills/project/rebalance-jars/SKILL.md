---
name: rebalance-jars
description: Dùng khi khách muốn chuyển một số tiền từ hũ này sang một hoặc nhiều hũ khác, hoặc một hũ thiếu tiền (hết số dư, hoặc định chi nhiều hơn số dư) và cần lấy bù từ hũ khác — ví dụ "chuyển 500 nghìn từ hũ ăn uống sang hũ di chuyển", "chuyển 300 nghìn từ hũ ăn uống sang di chuyển và sức khỏe", "hũ giải trí hết tiền rồi, lấy từ hũ khác bù". Đề xuất form rebalance_jars, khách tự xác nhận trên giao diện. Nếu khách chỉ chuyển tiền chưa phân bổ vào hũ mà không nêu hũ nguồn thì dùng skill distribute-amount. Không dùng để tăng hạn mức (đó là edit_jar của skill spending-jar).
---

# Rebalance jars (chuyển số dư từ 1 hũ sang 1 hoặc nhiều hũ khác — chỉ đề xuất, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

Form `rebalance_jars` **không chuyển tiền thật và không đổi hạn mức** (`limit`): nó chỉ dịch chuyển số dư (`balance`) từ 1 hũ nguồn
sang 1 hoặc nhiều hũ khác; số dư sau khi chuyển **được mang sang tháng sau**. Chèn khối `ui-json` theo skill này an toàn như viết 1
câu trả lời text: `pfm` chỉ ghi khi khách xem lại và bấm xác nhận. Khi câu hỏi khớp skill này, **đừng từ chối và đừng chỉ trả text rồi
bỏ qua khối** (trừ các trường hợp "KHÔNG trả `ui-json`" bên dưới).

Trong mọi trường hợp, việc ĐẦU TIÊN là gọi `get_jar_summary` — trước khi viết bất kỳ câu nào hay dựng đề xuất. Đừng dựa vào số
trong hội thoại trước.

Khác skill `distribute-amount`: skill đó nạp **tiền chưa phân bổ** vào hũ; skill này lấy tiền **từ một hũ**. Chỉ có 1 hũ nguồn mỗi form.

## Chọn hũ nguồn, hũ nhận, số tiền

1. **Khách nêu hũ nguồn và hũ nhận** ("chuyển X từ hũ A sang hũ B", "... sang B và C"): `from_jar_id` là A, mỗi hũ nhận là 1 phần tử
   của `allocations`. Khách nêu số cho từng hũ → dùng đúng số khách nêu. Chỉ nêu 1 tổng cho nhiều hũ → hũ cần bù trước (mỗi hũ tối
   đa −`balance`), phần còn lại chia đều, làm tròn nghìn, và nói rõ cách chia trong câu trả lời.
2. **Khách không nêu hũ nguồn** (hũ B hết tiền hoặc định chi nhiều hơn số dư, "lấy từ hũ khác bù"): số cần bù là −`balance` khi hũ B có
   `balance` < 0, hoặc số định chi − `spendable` của B. Chọn **1 hũ nguồn** có `spendable` lớn nhất và đủ cho số cần bù một mình; không
   hũ nào đủ một mình → KHÔNG trả `ui-json`, nói hũ nhiều tiền nhất chỉ còn bao nhiêu.
3. **Khách nêu hũ nguồn nhưng không nêu hũ nhận hay số tiền:** hũ nhận đang thiếu → cho đúng số thiếu; không có hũ nào thiếu → hỏi
   lại khách muốn chuyển bao nhiêu và sang hũ nào (text).

`overLimit` (đã chi vượt hạn mức) là trục khác, **không** phải lý do để chuyển tiền.

## Quy tắc cứng (`pfm` kiểm lại; vi phạm điều nào → bỏ cả `ui`)

1. Σ `allocations[].amount` ≤ `spendable` của hũ nguồn. Hũ nguồn `balance` là `null` (chưa có số dư) **không cho được**.
2. `from_jar_id` ≠ `to_jar_id` của mọi phần tử; mỗi hũ nhận một lần; `from_jar_id` và `to_jar_id` không phải `"pool"` (tiền chưa
   phân bổ là việc của skill `distribute-amount`).
3. Mọi id chép nguyên văn từ `get_jar_summary` **của lượt này**; `amount` là số nguyên VND dương. Hũ nhận chưa có số dư vẫn nhận được.

## Khi KHÔNG trả `ui-json`, chỉ nói trong câu trả lời

- Hũ nguồn không đủ: nói hũ nguồn chỉ còn bao nhiêu và hỏi khách muốn chuyển tối đa số đó hay số khác. Hũ nguồn chưa có số dư → nhắc
  khách nạp tiền vào hũ trước (skill `distribute-amount`).
- `get_jar_summary` lỗi hoặc số cần thiết là `null` — không đoán số.
- Hũ khách nhắc không có trong kết quả. Hũ vừa đề xuất tạo ở lượt trước **chưa tồn tại** (khách chưa xác nhận). **KHÔNG bao giờ bịa
  `id`** (ví dụ `lien-thien` suy từ tên hũ): server bỏ cả form. Hỏi lại bằng text, hoặc bằng `clarify_options` (skill
  `clarify-options`) nếu có 2–4 hũ thật tên gần giống. Câu chưa đủ để biết hũ nguồn/hũ nhận thì hỏi lại bằng `clarify_options`.
- Khách nêu **nhiều hũ nguồn** trong 1 câu: làm hũ nguồn đầu tiên và nói còn hũ nào để lượt sau (gọi lại `get_jar_summary`).

## Schema

```
{"type": "rebalance_jars", "from_jar_id": "...", "allocations": [{"to_jar_id": "...", "amount": 0}], "reason": "..."}
```

- `from_jar_id`: `id` hũ cho tiền. `allocations`: ≥ 1 phần tử `{ "to_jar_id": "<id hũ nhận>", "amount": <VND dương> }`. `reason`: vì sao
  chia như vậy, số thật. Không thêm field ngoài schema; JSON thật, đúng 1 khối mỗi lượt. Cộng lại Σ `allocations[].amount` trước khi viết khối.

## Câu trả lời đi kèm

1–3 câu (mỗi câu một dòng): chuyển bao nhiêu từ hũ nào sang hũ nào, nhắc khách xem lại rồi xác nhận. **KHÔNG nói "đã chuyển",
"đã bù", "đã cân đối"** — bạn chỉ đề xuất, `pfm` mới ghi khi khách bấm xác nhận.

**Cách nói:** **KHÔNG nói "số dư âm"**. Hũ có `balance` < 0 thì nói "hết số dư, còn thiếu {−`balance`} chưa được bù"; chỉ nói "đã vượt
hạn mức {`spent` − `limit`}" **riêng** khi `overLimit` là có. **Người đọc là khách hàng:** câu trả lời và `reason` không nhắc tên nội bộ —
không viết `pfm`, id hũ (`food`), tên field (`spendable`, `unallocated`, `balance`, `limit`), không dùng dấu backtick. Dùng tên tiếng
Việt của hũ. Không kể lại việc tra cứu: đi thẳng vào con số và đề xuất.

## Ví dụ ĐÚNG

### Một hũ nguồn, một hũ nhận

Khách hỏi: "Chuyển 500 nghìn từ hũ Ăn uống sang hũ Di chuyển." — `get_jar_summary`: hũ `food` `spendable` 2.613.000đ; hũ `transport` có trong kết quả.

Câu trả lời: "Mình đề xuất chuyển 500.000đ từ hũ Ăn uống sang hũ Di chuyển, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "from_jar_id": "food", "allocations": [{"to_jar_id": "transport", "amount": 500000}], "reason": "Khách muốn chuyển 500.000đ từ hũ Ăn uống sang hũ Di chuyển; hũ Ăn uống còn 2.613.000đ nên đủ"}
```

### Một hũ nguồn, nhiều hũ nhận

Khách hỏi: "Chuyển 300 nghìn từ hũ Ăn uống sang hũ Di chuyển và 200 nghìn sang hũ Sức khỏe." — hũ `food` `spendable` 2.613.000đ.

Câu trả lời: "Mình đề xuất chuyển từ hũ Ăn uống 300.000đ sang hũ Di chuyển và 200.000đ sang hũ Sức khỏe, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "from_jar_id": "food", "allocations": [{"to_jar_id": "transport", "amount": 300000}, {"to_jar_id": "health", "amount": 200000}], "reason": "Chuyển 500.000đ từ hũ Ăn uống sang hũ Di chuyển và hũ Sức khỏe theo đúng số khách nêu"}
```

### Hũ hết số dư, khách không nêu hũ nguồn

Khách hỏi: "Hũ Hưởng thụ chi lố rồi, lấy từ hũ khác bù giúp tôi." — hũ `lifestyle` `balance` −400.000đ; hũ `emergency` `spendable` 3.000.000đ là hũ nhiều tiền nhất.

Câu trả lời: "Hũ Hưởng thụ đã hết số dư, còn thiếu 400.000đ chưa được bù."
"Mình đề xuất lấy 400.000đ từ hũ Dự phòng, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "from_jar_id": "emergency", "allocations": [{"to_jar_id": "lifestyle", "amount": 400000}], "reason": "Hũ Hưởng thụ còn thiếu 400.000đ chưa được bù; hũ Dự phòng còn 3.000.000đ, nhiều nhất nên lấy 400.000đ từ đó"}
```

### Không có khối

Khách hỏi: "Chuyển 3 triệu từ hũ Sức khỏe sang hũ Ăn uống." — hũ Sức khỏe `spendable` 1.200.000đ. Câu trả lời (không kèm khối): "Hũ Sức khỏe hiện chỉ còn 1.200.000đ nên chưa chuyển được 3.000.000đ, bạn muốn chuyển tối đa 1.200.000đ hay số khác?"

## Ví dụ SAI (bị bỏ toàn bộ)

```
# SAI — lấy tiền chưa phân bổ ("pool") làm hũ nguồn: đó là việc của skill distribute-amount
{"type": "rebalance_jars", "from_jar_id": "pool", "allocations": [{"to_jar_id": "food", "amount": 500000}], "reason": "x"}

# SAI — hũ nguồn tự chuyển cho chính mình; lặp hũ nhận 2 lần
{"type": "rebalance_jars", "from_jar_id": "food", "allocations": [{"to_jar_id": "food", "amount": 500000}], "reason": "x"}
{"type": "rebalance_jars", "from_jar_id": "food", "allocations": [{"to_jar_id": "transport", "amount": 100000}, {"to_jar_id": "transport", "amount": 200000}], "reason": "x"}

# SAI — amount là string; thiếu reason; id bịa từ tên hũ
{"type": "rebalance_jars", "from_jar_id": "food", "allocations": [{"to_jar_id": "transport", "amount": "500000"}]}
{"type": "rebalance_jars", "from_jar_id": "food", "allocations": [{"to_jar_id": "du-lich", "amount": 500000}], "reason": "x"}

# SAI — dạng cũ (1 hũ đích nhận từ nhiều nguồn) không còn dùng
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 500000, "moves": [{"from_jar_id": "lifestyle", "amount": 500000}], "reason": "x"}
```

Sai lầm khác cần tránh: chuyển quá `spendable` của hũ nguồn; dùng 2 hũ nguồn trong 1 form; nói "số dư âm" hoặc "mình đã chuyển tiền giúp bạn"; dùng số cũ sau khi khách đã xác nhận.

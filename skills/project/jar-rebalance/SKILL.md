---
name: jar-rebalance
description: Dùng khi hũ chi tiêu của khách đã chi vượt hạn mức, hoặc không đủ số dư cho 1 khoản khách định chi, hoặc khách muốn chia lại tiền giữa các hũ trong tháng này — ví dụ "hũ ăn uống hết tiền rồi", "tôi định chi 4 triệu ăn uống nhưng hũ không đủ", "lấy tiền hũ khác bù cho hũ ăn uống". Skill đề xuất lấy phần thiếu từ hũ nào hoặc từ tiền chưa phân bổ (form rebalance_jars). Chỉ đề xuất, khách tự xác nhận trên giao diện. Không dùng để tăng hạn mức lâu dài (đó là edit_jar của skill spending-jar).
---

# Jar rebalance (cân đối số dư giữa các hũ — chỉ đề xuất, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

Form `rebalance_jars` **không chuyển tiền thật và không đổi hạn mức** (`budgetLimit`). Nó chỉ
đề xuất điều chỉnh số dư (`remaining`) giữa các hũ **trong tháng hiện tại**; sang tháng sau
`remaining` tính lại từ `budgetLimit`. Chèn khối `ui-json` theo skill này an toàn như viết 1 câu
trả lời text: `pfm` chỉ ghi khi khách xem lại và bấm xác nhận. Khi câu hỏi khớp skill này,
**đừng từ chối, và đừng chỉ trả text rồi bỏ qua khối** (trừ các trường hợp "KHÔNG trả `ui-json`"
bên dưới). Form này **độc lập** với form chuyển tiền (`transfer_form`).

## Khi nào dùng

- **(a)** khách định chi 1 khoản lớn hơn số dư hũ (`spendable` không đủ), hoặc
- **(b)** khách **đã chi vượt** hũ (`remaining` < 0, `overLimit: có`).

Hũ đích **phải có `budgetLimit`**. Hũ chưa đặt hạn mức (`null`) thì không cân đối được — đề xuất
`edit_jar` đặt hạn mức trước (skill `spending-jar`). Muốn thêm tiền cho hũ **lâu dài** cũng là
`edit_jar`, không phải skill này.

## Quy trình bắt buộc

1. **Đọc:** gọi `get_jar_summary` (đọc mới ở mỗi lượt — đừng dùng số cũ). Lấy `id`, `role`,
   `remaining`, `spendable` từng hũ và `unallocated`.
2. **Chọn hũ đích:** khách nhắc tên → khớp `label` để lấy `id`. Không có hũ đó → hỏi lại, đừng đoán.
   **Nhiều hũ cùng vượt: xử lý 1 hũ mỗi lượt** — hũ có `remaining` âm nhất trước; nêu trong câu
   trả lời còn hũ nào cần bù để làm ở lượt sau (sau khi gọi lại `get_jar_summary`, vì tiền
   "Chưa phân bổ" có thể đã dùng hết).
3. **Tính `shortfall`** (VND còn thiếu):
   - (a) `shortfall` = số tiền khách định chi − `spendable` của hũ đích;
   - (b) `shortfall` = −`remaining` của hũ đích.
   `shortfall` ≤ 0 nghĩa là hũ đã đủ → không cần form.
4. **Chọn nguồn theo thứ tự ưu tiên** (cùng thứ tự engine của `pfm` dùng):
   `pool` → `buffer` → `spending` → `essential`.
   - `pool` là tiền "Chưa phân bổ" (`unallocated`); cho tối đa `max(0, unallocated)`
     (khác `allocationHeadroom`, đừng nhầm).
   - Hũ theo `role`: `buffer` (dự phòng/tiết kiệm) trước, rồi `spending` (**vắng `role` = `spending`**),
     cuối cùng `essential` (thiết yếu). Trong cùng nhóm, hũ có `spendable` lớn nhất lấy trước.
   - Mỗi nguồn lấy **min(spendable, phần còn thiếu)** rồi dừng ngay khi đủ. Không lấy dư, không
     lấy từ nguồn không cần.
   - Hũ `spendable` là `null` (chưa đặt hạn mức) **không được cho**.
5. **Cộng lại trước khi viết khối:** Σ `moves[].amount` phải bằng đúng `shortfall`.

## Quy tắc cứng (`pfm` kiểm lại; vi phạm điều nào → bỏ cả `ui`, khách chỉ thấy câu trả lời)

1. Σ `moves[].amount` **đúng bằng** `shortfall`, và `shortfall` khớp số `pfm` tự tính.
2. `from_jar_id` ≠ `target_jar_id`, không lặp nguồn, không bịa id.
3. Mỗi hũ cho chỉ cho tối đa `spendable` của nó (không đẩy hũ cho xuống âm).
4. Nguồn `"pool"` chỉ cho tối đa `max(0, unallocated)`.
5. Hũ `role: "goal"` (mục tiêu, được bảo vệ) **không được có trong `moves`**. Nếu chỉ hũ `goal`
   mới đủ bù, nói trong câu trả lời để khách tự quyết — **KHÔNG trả `ui-json`**. **KHÔNG hỏi khách có muốn lấy
   từ hũ `goal` không và KHÔNG hứa "cho mình biết để mình tạo đề xuất"** (bạn không được đưa hũ `goal` vào
   `moves`, nên không làm được điều đó): chỉ nêu sự thật (hũ nào thiếu bao nhiêu, chỉ hũ mục tiêu còn đủ),
   nêu sự thật rồi dừng — khách muốn thì tự quyết ngoài cuộc trò chuyện này.

## Khi KHÔNG trả `ui-json`, chỉ nói trong câu trả lời

- Tổng mọi nguồn (trừ `goal`) vẫn **không đủ** để bù `shortfall` — nói rõ là không đủ và còn thiếu bao nhiêu.
- Chỉ hũ `goal` mới đủ (quy tắc 5).
- `get_jar_summary` lỗi hoặc số cần thiết là `null` — không đoán số.
- Hũ đích không có trong kết quả hoặc chưa đặt hạn mức.

## Schema

```
{"type": "rebalance_jars", "target_jar_id": "...", "shortfall": 0, "moves": [{"from_jar_id": "...", "amount": 0}], "reason": "..."}
```

- `target_jar_id` (bắt buộc): `id` hũ đang thiếu (có `budgetLimit`).
- `shortfall` (bắt buộc): number dương, VND còn thiếu (bước 3).
- `moves` (bắt buộc): ≥ 1 phần tử `{ "from_jar_id": "<id hũ cho> hoặc \"pool\"", "amount": <dương> }`.
- `reason` (bắt buộc): vì sao chọn các nguồn này, nêu số thật.

Chỉ trả `id` và con số — không trả lại tên hũ hay field nào ngoài schema.

## Câu trả lời đi kèm

1–3 câu (mỗi câu một dòng theo quy định chung): nêu hũ thiếu bao nhiêu, lấy từ đâu bao nhiêu, và nhắc
khách xem lại rồi xác nhận. **KHÔNG nói "đã chuyển", "đã bù", "đã cân đối"** — bạn chỉ đề xuất, `pfm`
mới ghi khi khách bấm xác nhận.

**Người đọc là khách hàng:** câu trả lời và `reason` không nhắc tên nội bộ — không viết `pfm`, id hũ (`food`), mã category (`entertainment`), tên field (`spendable`, `allocationHeadroom`, `budgetLimit`), không dùng dấu backtick. Dùng tên tiếng Việt của hũ và cách nói thường ("phần hạn mức còn được đặt thêm", "số dư hũ"). Việc `pfm` sẽ ghi thay đổi khi khách bấm xác nhận chỉ cần nói "bạn xem lại rồi xác nhận nhé".

## Ví dụ ĐÚNG

### (a) Khách định chi nhiều hơn số dư hũ

Khách hỏi: "Tôi định chi 3.878.000đ tiền ăn nhưng hũ Ăn uống không đủ, lấy tiền hũ khác giúp tôi."

`get_jar_summary`: hũ `food` (Ăn uống) `spendable` 2.378.000đ; `unallocated` 1.000.000đ; hũ `lifestyle`
(Hưởng thụ, vắng `role` = `spending`) `spendable` 2.088.000đ; hũ `savings` có `role: goal`.

`shortfall` = 3.878.000 − 2.378.000 = 1.500.000. Thứ tự: `pool` cho tối đa 1.000.000 → còn thiếu 500.000
→ `lifestyle` cho min(2.088.000, 500.000) = 500.000 → đủ, dừng. Hũ `goal` không dùng.

Câu trả lời: "Hũ Ăn uống thiếu 1.500.000đ cho khoản chi này."
"Mình đề xuất lấy 1.000.000đ từ tiền chưa phân bổ và 500.000đ từ hũ Hưởng thụ, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 1500000, "moves": [{"from_jar_id": "pool", "amount": 1000000}, {"from_jar_id": "lifestyle", "amount": 500000}], "reason": "Hũ Ăn uống thiếu 1.500.000đ; lấy 1.000.000đ từ tiền chưa phân bổ (còn 1.000.000đ) và 500.000đ từ hũ Hưởng thụ (còn 2.088.000đ)"}
```

### (b) Hũ đã chi vượt

Khách hỏi: "Hũ Hưởng thụ của tôi chi lố rồi, xử lý sao?"

`get_jar_summary`: hũ `lifestyle` `remaining` −400.000đ (`overLimit: có`); `unallocated` 0đ; hũ `emergency`
(Dự phòng, `role: buffer`) `spendable` 3.000.000đ.

`shortfall` = −(−400.000) = 400.000. `pool` không còn tiền → hũ `buffer` cho min(3.000.000, 400.000) = 400.000.

Câu trả lời: "Hũ Hưởng thụ đang chi vượt 400.000đ, mình đề xuất lấy 400.000đ từ hũ Dự phòng, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "target_jar_id": "lifestyle", "shortfall": 400000, "moves": [{"from_jar_id": "emergency", "amount": 400000}], "reason": "Hũ Hưởng thụ chi vượt 400.000đ; tiền chưa phân bổ hết, hũ Dự phòng còn 3.000.000đ nên lấy 400.000đ từ đó"}
```

### Chỉ hũ mục tiêu mới đủ — không có khối

`shortfall` 1.500.000đ, `unallocated` 0đ, các hũ `buffer`/`spending`/`essential` đều `spendable` 0đ, chỉ hũ `savings`
(`role: goal`) còn 8.000.000đ.

Câu trả lời (không kèm khối): "Hũ Ăn uống thiếu 1.500.000đ mà chỉ còn hũ mục tiêu Tiết kiệm đủ tiền để bù."
"Hũ này được bảo vệ nên mình không tự đề xuất lấy, bạn cân nhắc rồi tự quyết nhé."

**KHÔNG hứa** sẽ tạo đề xuất lấy tiền từ hũ `goal` ("cho mình biết để mình tạo đề xuất") — bạn không được đưa hũ `goal` vào `moves`, nên đừng gợi ý là làm được.

## Ví dụ SAI (bị bỏ toàn bộ)

```
# SAI — Σ moves = 1.400.000 ≠ shortfall 1.500.000
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 1500000, "moves": [{"from_jar_id": "pool", "amount": 900000}, {"from_jar_id": "lifestyle", "amount": 500000}], "reason": "x"}

# SAI — hũ đích tự cho chính mình
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 500000, "moves": [{"from_jar_id": "food", "amount": 500000}], "reason": "x"}

# SAI — lặp nguồn "pool" 2 lần
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 500000, "moves": [{"from_jar_id": "pool", "amount": 300000}, {"from_jar_id": "pool", "amount": 200000}], "reason": "x"}

# SAI — thiếu shortfall; amount là string
{"type": "rebalance_jars", "target_jar_id": "food", "moves": [{"from_jar_id": "pool", "amount": "500000"}], "reason": "x"}
```

Sai lầm khác cần tránh: đưa hũ `role: "goal"` vào `moves`; lấy quá `spendable` của 1 hũ hoặc quá `unallocated`;
lấy từ hũ khác trong khi `pool` còn tiền (sai thứ tự ưu tiên); xử lý 2 hũ trong cùng 1 lượt; dùng số cũ sau khi khách
đã xác nhận 1 thay đổi; nói "mình đã chuyển tiền giúp bạn".

---
name: jar-rebalance
description: Dùng khi hũ chi tiêu của khách cần bù (số dư về 0 và còn thiếu tiền chưa được bù), hoặc không đủ số dư cho 1 khoản khách định chi, hoặc khách muốn chia lại tiền giữa các hũ trong tháng này — ví dụ "hũ ăn uống hết tiền rồi", "tôi định chi 4 triệu ăn uống nhưng hũ không đủ", "lấy tiền hũ khác bù cho hũ ăn uống". Skill đề xuất lấy phần thiếu từ tiền chưa phân bổ hoặc từ hũ nào (form rebalance_jars). Chỉ đề xuất, khách tự xác nhận trên giao diện. Không dùng để tăng hạn mức lâu dài (đó là edit_jar của skill spending-jar).
---

# Jar rebalance (cân đối số dư giữa các hũ — chỉ đề xuất, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

Form `rebalance_jars` **không chuyển tiền thật và không đổi hạn mức** (`budgetLimit`). Nó chỉ
đề xuất điều chỉnh số dư (`remaining`) giữa các hũ **trong tháng hiện tại**; sang tháng sau
`remaining` tính lại từ `budgetLimit`. Chèn khối `ui-json` theo skill này an toàn như viết 1 câu
trả lời text: `pfm` chỉ ghi khi khách xem lại và bấm xác nhận. Khi câu hỏi khớp skill này,
**đừng từ chối, và đừng chỉ trả text rồi bỏ qua khối** (trừ các trường hợp "KHÔNG trả `ui-json`"
bên dưới). Form này **độc lập** với form chuyển tiền (`transfer_form`).

Trong mọi trường hợp, **việc ĐẦU TIÊN là gọi `get_jar_summary`** — trước khi viết bất kỳ câu nào hay dựng đề xuất. Đừng dựa vào số trong hội thoại trước, đừng đoán số dư; chưa đọc thì chưa được trả form.

## Khi nào dùng

- **(a)** khách định chi 1 khoản lớn hơn số dư hũ (`spendable` không đủ), hoặc
- **(b)** hũ **cần bù**: khách đã tiêu quá số dư, tức `remaining` < 0.

**Hai trục khác nhau, đừng nhầm:** số dư (`remaining`, `spendable`) và kế hoạch (`budgetLimit`,
`overLimit` = đã chi vượt hạn mức khách đặt). Bù giữa hũ chỉ dịch chuyển **số dư**; nó **không** sửa
`budgetLimit` và **không** xoá `overLimit` — hũ đã được bù đủ vẫn có `overLimit` = có. Vì vậy hũ "cần bù"
là hũ có `remaining` < 0, **không** phải hũ có `overLimit`.

Hũ đích **phải có `budgetLimit`**. Hũ chưa đặt hạn mức (`null`) thì không cân đối được — đề xuất
`edit_jar` đặt hạn mức trước (skill `spending-jar`). Muốn thêm tiền cho hũ **lâu dài** cũng là
`edit_jar`, không phải skill này.

## Cách nói với khách về hũ cần bù

`pfm` không bao giờ hiện số dư âm cho khách (hiện 0). **KHÔNG nói "số dư âm"**, "âm tiền". Hũ có
`remaining` < 0 thì nói "số dư 0, còn thiếu {−`remaining`} chưa được bù". Chỉ nói "đã vượt hạn mức
{`spent` − `budgetLimit`}" **riêng** khi `overLimit` là có.

## Quy trình bắt buộc

1. **Đọc (việc đầu tiên):** gọi `get_jar_summary` (đọc mới ở mỗi lượt — đừng dùng số cũ). Lấy `id`, `remaining`,
   `spendable`, `budgetLimit` từng hũ và `unallocated`.
2. **Chọn hũ đích:** khách nhắc tên → khớp `label` để lấy `id`, **sao chép nguyên văn** từ kết quả.
   Chỉ hũ có trong `get_jar_summary` **của lượt này** mới bù được. Không có hũ đó → hỏi lại bằng text,
   hoặc bằng `clarify_options` (skill `clarify-options`) nếu có 2–4 hũ thật tên gần giống khách vừa nói —
   đừng đoán.
   Hũ vừa được đề xuất tạo ở lượt trước **chưa tồn tại** (khách chưa xác nhận) nên không nằm trong kết
   quả → không bù được. **KHÔNG bao giờ bịa `id`** (ví dụ `lien-thien` suy từ tên hũ): server sẽ bỏ cả
   form nếu `id` không có trong kết quả bạn vừa đọc.
   **Nhiều hũ cùng cần bù: xử lý 1 hũ mỗi lượt** — hũ có `remaining` âm nhất trước; nêu trong câu
   trả lời còn hũ nào cần bù để làm ở lượt sau (sau khi gọi lại `get_jar_summary`, vì tiền
   "Chưa phân bổ" có thể đã dùng hết).
3. **Tính `shortfall`** (VND còn thiếu):
   - (a) `shortfall` = số tiền khách định chi − `spendable` của hũ đích;
   - (b) `shortfall` = −`remaining` của hũ đích.
   `shortfall` ≤ 0 nghĩa là hũ đã đủ → không cần form.
4. **Chọn nguồn theo thứ tự ưu tiên** (cùng thứ tự engine của `pfm` dùng):
   `pool` trước, rồi các hũ còn lại theo `spendable` giảm dần (hũ nhiều tiền nhất lấy trước).
   Không hũ nào được bảo vệ — hũ không có vai trò. **Viết ra danh sách nguồn đã sắp xếp** (`pool`, rồi từng hũ khác
   kèm `spendable`, từ lớn đến nhỏ) **trước khi chọn** — hũ đầu danh sách sau `pool` luôn là hũ có `spendable` lớn nhất.
   - `pool` là tiền "Chưa phân bổ" (`unallocated`); cho tối đa `max(0, unallocated)`
     (khác `allocationHeadroom`, đừng nhầm). **Nếu `unallocated` > 0 thì `pool` LUÔN là nguồn đầu tiên**, kể cả khi 1 hũ
     khác đủ một mình: tiền chưa phân bổ không thuộc hũ nào nên lấy nó không làm hũ nào thiếu đi. Chỉ khi `unallocated` là 0
     (hoặc chưa biết) mới bắt đầu từ hũ nhiều tiền nhất.
   - Mỗi nguồn lấy **min(spendable, phần còn thiếu)** rồi dừng ngay khi đủ. Không lấy dư, không
     lấy từ nguồn không cần — nếu 1 hũ đủ một mình thì chỉ dùng hũ đó, đừng chia nhỏ ra nhiều hũ.
   - Hũ `spendable` là `null` (chưa đặt hạn mức) **không được cho**. Hũ đích không tự cho chính nó.
5. **Làm từng bước, ghi ra số còn lại sau mỗi nguồn:** còn thiếu = `shortfall` − tổng đã lấy. Bắt đầu còn thiếu = `shortfall`;
   lấy nguồn 1 → tính lại; lấy tiếp cho tới khi còn thiếu = 0 thì **dừng**.
6. **Đủ hay không?** So tổng số tiền các nguồn có thể cho (`max(0, unallocated)` + Σ `spendable` các hũ khác) **so với
   `shortfall`, KHÔNG so với số tiền khách định chi** — hũ đích đã tự có `spendable` của nó rồi. Tổng nguồn ≥ `shortfall` là
   đủ. Chỉ khi tổng nguồn < `shortfall` mới nói "không đủ".
7. **Cộng lại trước khi viết khối:** Σ `moves[].amount` phải bằng đúng `shortfall`.

## Quy tắc cứng (`pfm` kiểm lại; vi phạm điều nào → bỏ cả `ui`, khách chỉ thấy câu trả lời)

1. Σ `moves[].amount` **đúng bằng** `shortfall`, và `shortfall` khớp số `pfm` tự tính.
2. `from_jar_id` ≠ `target_jar_id`, không lặp nguồn, không bịa id.
3. Mỗi hũ cho chỉ cho tối đa `spendable` của nó (không đẩy hũ cho xuống âm).
4. Nguồn `"pool"` chỉ cho tối đa `max(0, unallocated)`.

## Khi KHÔNG trả `ui-json`, chỉ nói trong câu trả lời

- Tổng mọi nguồn vẫn **không đủ** để bù `shortfall` — nói rõ là không đủ và còn thiếu bao nhiêu.
- `get_jar_summary` lỗi hoặc số cần thiết là `null` — không đoán số.
- Hũ đích không có trong kết quả (kể cả hũ vừa đề xuất tạo ở lượt trước) hoặc chưa đặt hạn mức.

## Schema

```
{"type": "rebalance_jars", "target_jar_id": "...", "shortfall": 0, "moves": [{"from_jar_id": "...", "amount": 0}], "reason": "..."}
```

- `target_jar_id` (bắt buộc): `id` hũ đang thiếu (có `budgetLimit`), chép từ `get_jar_summary`.
- `shortfall` (bắt buộc): number dương, VND còn thiếu (bước 3).
- `moves` (bắt buộc): ≥ 1 phần tử `{ "from_jar_id": "<id hũ cho> hoặc \"pool\"", "amount": <dương> }`.
- `reason` (bắt buộc): vì sao chọn các nguồn này, nêu số thật.

Chỉ trả `id` và con số — không trả lại tên hũ hay field nào ngoài schema.

## Câu trả lời đi kèm

1–3 câu (mỗi câu một dòng theo quy định chung): nêu hũ thiếu bao nhiêu, lấy từ đâu bao nhiêu, và nhắc
khách xem lại rồi xác nhận. **KHÔNG nói "đã chuyển", "đã bù", "đã cân đối"** — bạn chỉ đề xuất, `pfm`
mới ghi khi khách bấm xác nhận.

**Người đọc là khách hàng:** câu trả lời và `reason` không nhắc tên nội bộ — không viết `pfm`, id hũ (`food`), mã category (`entertainment`), tên field (`spendable`, `allocationHeadroom`, `budgetLimit`), không dùng dấu backtick. Dùng tên tiếng Việt của hũ và cách nói thường ("phần hạn mức còn được đặt thêm", "số dư hũ"). Việc `pfm` sẽ ghi thay đổi khi khách bấm xác nhận chỉ cần nói "bạn xem lại rồi xác nhận nhé". Không kể lại việc tra cứu (đừng mở đầu bằng "danh mục của bạn có id …" hay liệt kê cách bạn tìm ra số): đi thẳng vào con số và đề xuất.

## Ví dụ ĐÚNG

### (a) Khách định chi nhiều hơn số dư hũ

Khách hỏi: "Tôi định chi 3.878.000đ tiền ăn nhưng hũ Ăn uống không đủ, lấy tiền hũ khác giúp tôi."

`get_jar_summary`: hũ `food` (Ăn uống) `spendable` 2.378.000đ; `unallocated` 1.000.000đ; hũ `lifestyle`
(Hưởng thụ) `spendable` 2.088.000đ; hũ `bills` (Hoá đơn) `spendable` 51.000đ.

`shortfall` = 3.878.000 − 2.378.000 = 1.500.000. Thứ tự: `pool` cho tối đa 1.000.000 → còn thiếu 500.000
→ trong các hũ còn lại `lifestyle` nhiều tiền nhất, cho min(2.088.000, 500.000) = 500.000 → đủ, dừng.

Câu trả lời: "Hũ Ăn uống thiếu 1.500.000đ cho khoản chi này."
"Mình đề xuất lấy 1.000.000đ từ tiền chưa phân bổ và 500.000đ từ hũ Hưởng thụ, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 1500000, "moves": [{"from_jar_id": "pool", "amount": 1000000}, {"from_jar_id": "lifestyle", "amount": 500000}], "reason": "Hũ Ăn uống thiếu 1.500.000đ; lấy 1.000.000đ từ tiền chưa phân bổ (còn 1.000.000đ) và 500.000đ từ hũ Hưởng thụ (còn 2.088.000đ)"}
```

### (a') Khoản chi lớn — `pool` gần đủ, 1 hũ lớn nhất bù nốt

Khách hỏi: "Tôi định chi 16 triệu từ hũ Ăn uống, thiếu thì chia từ hũ khác giúp tôi."

`get_jar_summary`: hũ `food` (Ăn uống) `spendable` 1.813.000đ; `unallocated` 13.044.000đ; hũ `lifestyle` (Hưởng thụ)
`spendable` 1.296.000đ; hũ `move` (Di chuyển) `spendable` 796.000đ.

`shortfall` = 16.000.000 − 1.813.000 = 14.187.000. Tổng nguồn = 13.044.000 + 1.296.000 + 796.000 = 15.136.000 ≥ 14.187.000
nên **đủ** (không so 15.136.000 với 16.000.000). Từng bước: còn thiếu 14.187.000 → `pool` cho min(13.044.000, 14.187.000) =
13.044.000 → còn thiếu 1.143.000 → hũ nhiều tiền nhất còn lại là `lifestyle`, cho min(1.296.000, 1.143.000) = 1.143.000 →
còn thiếu 0, **dừng** (không cần hũ `move`).

Câu trả lời: "Hũ Ăn uống thiếu 14.187.000đ cho khoản chi 16.000.000đ."
"Mình đề xuất lấy 13.044.000đ từ tiền chưa phân bổ và 1.143.000đ từ hũ Hưởng thụ, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 14187000, "moves": [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "lifestyle", "amount": 1143000}], "reason": "Hũ Ăn uống thiếu 14.187.000đ cho khoản chi 16.000.000đ; lấy 13.044.000đ từ tiền chưa phân bổ và 1.143.000đ từ hũ Hưởng thụ (còn 1.296.000đ)"}
```

### (a'') `pool` đủ một mình — chỉ lấy `pool`

Khách hỏi: "Tôi định chi 1.051.000đ từ hũ Nhà cửa, thiếu thì lấy từ hũ khác giúp tôi."

`get_jar_summary`: hũ `home` (Nhà cửa) `spendable` 51.000đ; `unallocated` 1.932.889đ; hũ `food` (Ăn uống)
`spendable` 1.813.000đ, đủ để bù một mình.

`shortfall` = 1.051.000 − 51.000 = 1.000.000. `unallocated` > 0 nên `pool` đứng đầu: cho min(1.932.889, 1.000.000) = 1.000.000
→ còn thiếu 0, **dừng**. Hũ Ăn uống đủ một mình nhưng **không dùng**, vì `pool` đứng trước.

Câu trả lời: "Hũ Nhà cửa thiếu 1.000.000đ cho khoản chi này."
"Mình đề xuất lấy 1.000.000đ từ tiền chưa phân bổ, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "target_jar_id": "home", "shortfall": 1000000, "moves": [{"from_jar_id": "pool", "amount": 1000000}], "reason": "Tiền chưa phân bổ còn 1.932.889đ, đủ bù 1.000.000đ một mình nên không cần lấy từ hũ nào."}
```

### (b) Hũ cần bù

Khách hỏi: "Hũ Hưởng thụ của tôi chi lố rồi, xử lý sao?"

`get_jar_summary`: hũ `lifestyle` `remaining` −400.000đ (cần bù; `spent` 2.900.000đ trên `budgetLimit` 2.500.000đ nên
`overLimit` cũng là có); `unallocated` 0đ; hũ `emergency` (Dự phòng) `spendable` 3.000.000đ, nhiều tiền nhất.

`shortfall` = −(−400.000) = 400.000. `pool` không còn tiền → hũ nhiều tiền nhất là Dự phòng, cho min(3.000.000, 400.000) = 400.000.

Câu trả lời: "Hũ Hưởng thụ đang có số dư 0, còn thiếu 400.000đ chưa được bù."
"Mình đề xuất lấy 400.000đ từ hũ Dự phòng, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "rebalance_jars", "target_jar_id": "lifestyle", "shortfall": 400000, "moves": [{"from_jar_id": "emergency", "amount": 400000}], "reason": "Hũ Hưởng thụ còn thiếu 400.000đ chưa được bù; tiền chưa phân bổ hết, hũ Dự phòng còn 3.000.000đ nên lấy 400.000đ từ đó"}
```

### Tổng các nguồn không đủ — không có khối

`shortfall` 1.500.000đ, `unallocated` 0đ, các hũ còn lại cộng lại chỉ `spendable` 300.000đ.

Câu trả lời (không kèm khối): "Hũ Ăn uống thiếu 1.500.000đ mà tiền chưa phân bổ đã hết và các hũ khác cộng lại chỉ còn 300.000đ."
"Số này chưa đủ để bù, bạn cân nhắc giảm khoản chi hoặc tăng hạn mức hũ nhé."

### Hũ chỉ có trong hội thoại — không có khối

Lượt trước bạn đề xuất tạo hũ "Du lịch", khách chưa xác nhận, giờ hỏi "hũ Du lịch thiếu tiền, bù giúp tôi". Hũ đó không có
trong `get_jar_summary` của lượt này nên chưa tồn tại.

Câu trả lời (không kèm khối): "Hũ Du lịch chưa được tạo nên mình chưa bù được."
"Bạn xác nhận tạo hũ trước, rồi mình sẽ đề xuất bù giúp bạn."

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

# SAI — id bịa từ tên hũ, không có trong get_jar_summary
{"type": "rebalance_jars", "target_jar_id": "du-lich", "shortfall": 500000, "moves": [{"from_jar_id": "pool", "amount": 500000}], "reason": "x"}
```

Sai lầm khác cần tránh: so tổng nguồn với số tiền khách định chi (thay vì `shortfall`) rồi kết luận "không đủ"; lấy quá `spendable` của 1 hũ hoặc quá `unallocated`; lấy từ 1 hũ khi `pool` còn tiền (kể cả khi hũ đó đủ một mình); lấy từ hũ nhỏ trong khi hũ nhiều
tiền hơn còn đủ (sai thứ tự); chia nhỏ ra nhiều nguồn khi 1 nguồn đã đủ; xử lý 2 hũ trong cùng 1 lượt; dùng số cũ sau khi khách
đã xác nhận 1 thay đổi; dùng `overLimit` để quyết định hũ cần bù; nói "số dư âm"; nói "mình đã chuyển tiền giúp bạn".

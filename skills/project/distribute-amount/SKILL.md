---
name: distribute-amount
description: Dùng khi khách muốn chuyển một số tiền chưa phân bổ vào một hoặc nhiều hũ chi tiêu (nạp số dư cho hũ) — ví dụ "chuyển 300 nghìn vào hũ tiết kiệm", "chia 1 triệu vào ăn uống và di chuyển", "bù cho hũ ăn uống đang hết tiền". Tiền lấy từ khoản tiền chưa phân bổ trong tài khoản, không lấy từ hũ khác. Chỉ đề xuất, khách tự xác nhận trên giao diện. Nếu khách nêu rõ lấy tiền từ một hũ nguồn thì dùng skill rebalance-jars. Không dùng để tăng hạn mức (đó là edit_jar của skill spending-jar).
---

# Chuyển tiền chưa phân bổ vào hũ (chỉ đề xuất, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

Form `distribute_amount` **không chuyển tiền thật và không đổi hạn mức**: nó chỉ đề xuất cộng số dư (`balance`) cho các
hũ từ khoản tiền chưa phân bổ. Chèn khối `ui-json` theo skill này an toàn như viết 1 câu trả lời text: `pfm` chỉ ghi khi
khách xem lại và bấm xác nhận. Khi câu hỏi khớp skill này, **đừng từ chối và đừng chỉ trả text rồi bỏ qua khối** (trừ các
trường hợp "KHÔNG trả `ui-json`" bên dưới).

Trong mọi trường hợp, việc ĐẦU TIÊN là gọi `get_jar_summary` — trước khi viết bất kỳ câu nào hay dựng đề xuất. Đừng dựa vào số
trong hội thoại trước.

## Tiền lấy từ đâu

- Luôn từ **tiền chưa phân bổ** (`unallocated`, "Chờ phân bổ" = tiền trong tài khoản chưa nằm trong hũ nào). Tối đa chia
  được là max(0, `unallocated`). **Không lấy từ hũ khác.**
- Tổng khách muốn chia lớn hơn max(0, `unallocated`), hoặc `unallocated` ≤ 0 hay "chưa biết" → **KHÔNG trả `ui-json`**: nói
  tiền chưa phân bổ còn bao nhiêu và hỏi khách muốn chia số nào.

## Chia bao nhiêu, vào hũ nào

1. Khách nêu số cho từng hũ → dùng đúng số đó.
2. Khách chỉ nêu 1 tổng cho nhiều hũ → hũ cần bù trước (mỗi hũ tối đa −`balance`), phần còn lại chia đều, làm tròn
   nghìn; nói rõ cách chia trong câu trả lời.
3. Hũ **cần bù** là hũ có `balance` < 0 (đã tiêu quá số dư, chưa được bù). Khách bảo "bù giúp tôi" mà không nêu số →
   nạp đúng số thiếu, tức −`balance`. `overLimit` (đã chi vượt hạn mức) là trục khác, **không** phải lý do để nạp.
4. Hũ **chưa có số dư** (`balance` là `null`, ví dụ hũ Tiết kiệm mới) **vẫn nhận được**: khoản nạp chính là số dư đầu
   tiên của hũ. Hạn mức (`limit`) không liên quan tới việc nhận tiền.
5. Nhiều hũ trong 1 câu → **nhiều hũ trong cùng 1 form**, mỗi hũ một lần. Chỉ hũ có trong `get_jar_summary` **của lượt
   này** mới nhận được. Hũ vừa đề xuất tạo ở lượt trước **chưa tồn tại** (khách chưa xác nhận). **KHÔNG bao giờ bịa `id`**
   (ví dụ `lien-thien` suy từ tên hũ): server bỏ cả form. Không có hũ khách nhắc → hỏi lại bằng text, hoặc bằng
   `clarify_options` (skill `clarify-options`) nếu có 2–4 hũ thật tên gần giống.

## Schema

```
{"type": "distribute_amount", "allocations": [{"to_jar_id": "...", "amount": 0}], "reason": "..."}
```

- `allocations` (bắt buộc): ≥ 1 phần tử `{ "to_jar_id": "<id hũ>", "amount": <VND, số nguyên dương> }`; `to_jar_id` chép
  nguyên văn từ `get_jar_summary`, không phải `"pool"`; mỗi hũ một lần.
- `reason` (bắt buộc): 1–2 câu ngắn, số thật, không tên nội bộ.
- Σ `allocations[].amount` ≤ max(0, `unallocated`). Không thêm field ngoài schema; JSON thật, đúng 1 khối mỗi lượt.

## Câu trả lời đi kèm

1–3 câu (mỗi câu một dòng): chia bao nhiêu cho hũ nào và nhắc khách xem lại rồi xác nhận. **KHÔNG nói "đã chuyển",
"đã nạp", "đã chia"** — bạn chỉ đề xuất, `pfm` mới ghi khi khách bấm xác nhận.

**Cách nói:** **KHÔNG nói "số dư âm"**. Hũ có `balance` < 0 thì nói "hết số dư, còn thiếu {−`balance`} chưa được bù";
`balance` là `null` thì nói "hũ chưa có số dư"; chỉ nói "đã vượt hạn mức {`spent` − `limit`}" **riêng** khi `overLimit` là có.

**Người đọc là khách hàng:** câu trả lời và `reason` không nhắc tên nội bộ — không viết `pfm`, id hũ (`food`), tên field
(`spendable`, `unallocated`, `balance`, `limit`), không dùng dấu backtick. Dùng tên tiếng Việt của hũ và "tiền chưa phân bổ",
"số dư hũ". Không kể lại việc tra cứu: đi thẳng vào con số và đề xuất.

## Ví dụ ĐÚNG

### Chuyển vào hũ chưa có số dư

Khách hỏi: "Chuyển 300k vào hũ tiết kiệm." — `get_jar_summary`: hũ `savings` (Tiết kiệm) `balance` `null`; `unallocated` 13.244.000đ.

Câu trả lời: "Mình đề xuất chuyển 300.000đ từ tiền chưa phân bổ vào hũ Tiết kiệm."
"Hũ chưa có số dư nên đây sẽ là số dư đầu tiên, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "distribute_amount", "allocations": [{"to_jar_id": "savings", "amount": 300000}], "reason": "Khách muốn chuyển 300.000đ từ tiền chưa phân bổ vào hũ Tiết kiệm; hũ chưa có số dư nên khoản này là số dư đầu tiên"}
```

### Chia vào nhiều hũ

Khách hỏi: "Chia 1 triệu vào Ăn uống 600 nghìn và Di chuyển 400 nghìn." — `unallocated` 13.244.000đ, cả hai hũ có trong kết quả.

Câu trả lời: "Mình đề xuất chia 600.000đ vào hũ Ăn uống và 400.000đ vào hũ Di chuyển từ tiền chưa phân bổ, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "distribute_amount", "allocations": [{"to_jar_id": "food", "amount": 600000}, {"to_jar_id": "transport", "amount": 400000}], "reason": "Chia 1.000.000đ tiền chưa phân bổ theo đúng số khách nêu cho hũ Ăn uống và hũ Di chuyển"}
```

### Bù hũ đang hết số dư

Khách hỏi: "Hũ Hoá đơn hết tiền rồi, bù giúp tôi." — hũ `bills` `balance` −3.349.000đ; `unallocated` 13.244.000đ đủ.

Câu trả lời: "Hũ Hoá đơn đã hết số dư, còn thiếu 3.349.000đ chưa được bù."
"Mình đề xuất nạp 3.349.000đ từ tiền chưa phân bổ vào hũ này, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "distribute_amount", "allocations": [{"to_jar_id": "bills", "amount": 3349000}], "reason": "Hũ Hoá đơn còn thiếu 3.349.000đ chưa được bù; tiền chưa phân bổ đủ nên nạp đúng số thiếu"}
```

### Tiền chưa phân bổ không đủ — không có khối

Khách hỏi: "Chuyển 5 triệu vào hũ Ăn uống." — `unallocated` chỉ 2.000.000đ. Câu trả lời (không kèm khối): "Tiền chưa phân bổ hiện chỉ còn 2.000.000đ nên chưa chuyển được 5.000.000đ, bạn muốn chuyển tối đa 2.000.000đ hay một số khác?"

## Ví dụ SAI (bị bỏ toàn bộ)

```
# SAI — lấy từ hũ khác / "pool" làm đích: chỉ nạp vào hũ thật, nguồn luôn là tiền chưa phân bổ
{"type": "distribute_amount", "allocations": [{"to_jar_id": "pool", "amount": 300000}], "reason": "x"}

# SAI — lặp hũ 2 lần (gộp thành 1 phần tử)
{"type": "distribute_amount", "allocations": [{"to_jar_id": "food", "amount": 100000}, {"to_jar_id": "food", "amount": 200000}], "reason": "x"}

# SAI — amount là string; thiếu reason
{"type": "distribute_amount", "allocations": [{"to_jar_id": "food", "amount": "300000"}]}

# SAI — id bịa từ tên hũ, không có trong get_jar_summary
{"type": "distribute_amount", "allocations": [{"to_jar_id": "du-lich", "amount": 300000}], "reason": "x"}

# SAI — lấy tiền từ hũ khác bằng rebalance_jars: đó là việc của skill rebalance-jars, skill này chỉ nạp từ tiền chưa phân bổ
{"type": "rebalance_jars", "target_jar_id": "food", "shortfall": 300000, "moves": [{"from_jar_id": "lifestyle", "amount": 300000}], "reason": "x"}
```

Sai lầm khác cần tránh: chia tổng lớn hơn tiền chưa phân bổ; từ chối vì hũ chưa có số dư; tách nhiều hũ ra nhiều lượt; dùng
`overLimit` để quyết định hũ cần nạp; nói "số dư âm"; dùng số cũ sau khi khách đã xác nhận 1 thay đổi.

---
name: transfer-form
description: Dùng khi nên gợi ý khách hàng chuyển tiền — (a) trả nợ thẻ tín dụng của chính họ (ví dụ khách hỏi "tôi nên trả nợ thẻ bao nhiêu", "chuyển tiền trả nợ thẻ giúp tôi"), HOẶC (b) chuyển tiền cho 1 người trong danh bạ đã lưu (`beneficiaries`) của khách hàng (ví dụ "chuyển tiền cho Toàn 500 nghìn"). KHÔNG dùng để đề xuất chuyển cho 1 người/merchant KHÔNG có trong `beneficiaries` và khách hàng không tự cung cấp số tài khoản — xem phần Phạm vi bên dưới.
---

# Transfer form (đề xuất chuyển tiền — chỉ hiển thị, không thực thi)

## Phạm vi hiện tại — QUAN TRỌNG, đọc trước khi dùng skill này

Skill này hỗ trợ **2 trường hợp**, phân biệt rõ vì mức độ rủi ro khác nhau:

**(A) Trả nợ thẻ tín dụng của chính khách hàng** — `recipient` là ngân hàng
phát hành thẻ, `account_number` là 1 `card_id`/`card_number_last4` có thật
trong `cards` của khách hàng. Luôn an toàn vì thẻ là dữ liệu có thật của
chính khách hàng.

**(B) Chuyển tiền cho 1 người trong danh bạ đã lưu (`beneficiaries`)** —
`/customer_data.json` có trường `beneficiaries` (danh sách người nhận đã
lưu sẵn, mỗi người có `name`/`account_number`/`bank_name`). **Đây hiện là
danh sách hardcode tạm thời** (chưa có tool đọc danh bạ thật/realtime — đã
ghi chú trong `todo.md`, cân nhắc thêm tool `query_beneficiaries` sau) —
nhưng trong phạm vi demo này, coi đây là nguồn dữ liệu đáng tin cậy duy
nhất cho 1 người nhận không phải chính khách hàng.

- **CHỈ đề xuất chuyển cho 1 người nếu tên đó khớp đúng 1 entry trong
  `beneficiaries`** của khách hàng đang trò chuyện — lấy nguyên
  `account_number`/`bank_name` từ đó, không bịa, không đoán, không tự sửa
  chính tả tên cho khớp gần đúng.
- **Nếu khách hàng nêu tên người nhận KHÔNG có trong `beneficiaries`** (và
  khách hàng cũng không tự cung cấp số tài khoản/ngân hàng trong câu hỏi):
  **KHÔNG chèn khối `ui-json`** — hỏi lại khách hàng số tài khoản + ngân
  hàng thật của người đó trước. Tuyệt đối không tự bịa số tài khoản — đây
  là nguy cơ cao hơn nhiều so với bịa số liệu chart (tiền có thể chuyển sai
  người thật nếu khách hàng không để ý mà vẫn bấm xác nhận).
- Nếu khách hàng **tự cung cấp đủ tên + số tài khoản + ngân hàng** ngay
  trong câu hỏi (dù người đó không có trong `beneficiaries`): được phép
  dùng đúng thông tin khách hàng tự cung cấp (không phải agent tự bịa — chỉ
  là ghi lại đúng những gì khách hàng đã nói).

## Quy trình bắt buộc — Check trước, Propose sau

1. **Xác định đây là trường hợp (A) hay (B):** khách hàng nói tới trả nợ
   thẻ (không nêu người nhận cụ thể) → trường hợp (A). Khách hàng nêu rõ 1
   người nhận (tên riêng, không phải tên thẻ/ngân hàng phát hành thẻ của
   chính họ) → trường hợp (B).

2. **Trường hợp (A) — trả nợ thẻ:**
   - **Check (bắt buộc):** dữ liệu khách hàng (`/customer_data.json`, gồm
     `cards`/`statements`) **đã có sẵn ngay trong system prompt của bạn** —
     KHÔNG cần gọi `read_file`/`grep`. Đọc đúng `available_credit_vnd`,
     `total_due_vnd`, `min_payment_vnd`, `due_date` thật của thẻ liên quan
     — không bịa số. Tự xác nhận `amount` **không vượt quá**
     `available_credit_vnd` của thẻ đó trước khi chèn khối `ui-json`.
     - Nếu không thẻ nào đủ hạn mức khả dụng: **đừng chèn `transfer_form`**,
       chỉ trả lời bằng text giải thích giới hạn thật.
   - **Xác định đúng thẻ — TỰ LÀM, đừng hỏi lại nếu dữ liệu đã đủ để xác
     định:**
     - Khách hàng **đã nêu rõ tên thẻ** (ví dụ "trả nợ thẻ Visa Signature"):
       dùng đúng thẻ đó.
     - Khách hàng **hỏi chung chung, không nêu tên thẻ** (ví dụ "chuyển
       tiền trả nợ thẻ giúp tôi"): tự tra `statements`, tìm thẻ có
       `status` là `current_unpaid`/`paid_partial` — **đề xuất luôn**,
       không hỏi lại khách hàng muốn trả thẻ nào.
     - Chỉ hỏi lại khi thật sự không thể tự xác định (nhiều hơn 1 thẻ cùng
       có dư nợ chưa thanh toán) — khi đó chọn thẻ có `due_date` gần nhất
       và đề xuất luôn, kèm 1 câu ngắn nhắc còn thẻ khác cũng có dư nợ.

3. **Trường hợp (B) — chuyển cho 1 người:**
   - **Check (bắt buộc):** đọc `beneficiaries` trong `/customer_data.json`
     (đã có sẵn trong system prompt), tìm entry có `name` khớp đúng người
     khách hàng vừa nêu.
     - **Tìm thấy:** lấy nguyên `account_number`/`bank_name` từ entry đó.
     - **Không tìm thấy, và khách hàng cũng không tự cho số tài khoản:**
       không chèn `ui-json` — hỏi lại số tài khoản + ngân hàng thật.
     - **Không tìm thấy, nhưng khách hàng tự cho đủ số tài khoản + ngân
       hàng trong câu hỏi:** dùng đúng thông tin đó.

4. **Propose:** chèn **đúng 1 khối** `ui-json` ở cuối câu trả lời:

```ui-json
{"type": "transfer_form", "recipient": "...", "account_number": "...", "amount": 0, "note": "..."}
```

## Schema

- `type` (bắt buộc): luôn là `"transfer_form"`.
- `recipient` (bắt buộc): string — trường hợp (A): tên ngân hàng/thẻ phát
  hành (ví dụ `card_name` trong `cards`); trường hợp (B): tên người nhận
  (`name` trong `beneficiaries`, hoặc tên khách hàng tự cung cấp).
- `account_number` (bắt buộc): string — trường hợp (A): `card_id`/
  `card_number_last4` thật của khách hàng; trường hợp (B): `account_number`
  lấy từ đúng entry `beneficiaries`, hoặc số khách hàng tự cung cấp.
- `amount` (bắt buộc): number JSON thật, dương — số tiền đề xuất chuyển.
- `note` (bắt buộc): string ngắn — **đúng nội dung chuyển khoản** sẽ điền
  vào form thật (ví dụ "Thanh toan du no the MSB Visa Signature ky 06-07",
  hoặc đúng nội dung khách hàng nêu như "Thanh toan tien an"). Đây là nội
  dung để ngân hàng/người nhận nhận diện đúng giao dịch — không phải lời
  giải thích cho khách hàng, viết ngắn gọn như 1 nội dung chuyển khoản
  thật (không dấu cũng được).

## PHẢI (bắt buộc — sai 1 điều là toàn bộ đề xuất bị huỷ)

1. JSON thật (dấu nháy kép), không phải Python dict repr.
2. Trường hợp (A): đã tự đối chiếu `amount` với `available_credit_vnd` và
   `account_number` khớp đúng 1 `card_id`/`card_number_last4` thật.
3. Trường hợp (B): `account_number`/`bank_name` PHẢI lấy nguyên từ đúng 1
   entry `beneficiaries` khớp tên, HOẶC là thông tin khách hàng tự cung
   cấp trong câu hỏi — không được tự bịa/đoán/sửa chính tả cho khớp gần
   đúng.
4. `amount` là number JSON thật, dương, khớp đúng số liệu đọc được (không
   tự làm tròn/bịa).
5. `note` PHẢI có nội dung cụ thể (không được rỗng).
6. Đúng 1 khối `ui-json` mỗi câu trả lời.

## KHÔNG ĐƯỢC

- KHÔNG đề xuất chuyển cho 1 người KHÔNG có trong `beneficiaries` trừ khi
  khách hàng tự cung cấp đủ số tài khoản + ngân hàng trong câu hỏi.
- KHÔNG tự thêm field ngoài 5 field đã định nghĩa (`type`, `recipient`,
  `account_number`, `amount`, `note`).
- KHÔNG chèn khối này nếu chưa xác nhận đủ điều kiện theo đúng bước Check
  ở trên (hạn mức khả dụng cho trường hợp A, hoặc nguồn `account_number`
  hợp lệ cho trường hợp B).
- KHÔNG khẳng định việc chuyển tiền đã xảy ra — đây chỉ là 1 form điền sẵn
  để khách hàng tự xem và tự bấm xác nhận trên UI, việc chuyển tiền thật
  (nếu có) diễn ra hoàn toàn bên ngoài cuộc hội thoại này.

## Ví dụ ĐÚNG

### Ví dụ 1 — trả nợ thẻ, khách hàng nêu rõ tên thẻ

Khách hỏi: "Tôi nên trả nợ thẻ Visa Signature bao nhiêu?"

Bước 1 (bắt buộc): đọc `/customer_data.json`, thấy thẻ MSB Visa Signature
có `available_credit_vnd` đủ cho `min_payment_vnd` 910.000đ của kỳ sao kê
liên quan.

Phần text trả lời: "Kỳ sao kê thẻ MSB Visa Signature đến hạn 10/07/2026,
mức thanh toán tối thiểu là 910.000đ (đã trả 50%, còn dư nợ 18.200.000đ)."

Kèm khối:

```ui-json
{"type": "transfer_form", "recipient": "MSB Visa Signature", "account_number": "card_001", "amount": 910000, "note": "Thanh toan du no the MSB Visa Signature ky sao ke 21/06-20/07"}
```

### Ví dụ 2 — trả nợ thẻ, khách hàng KHÔNG nêu tên thẻ, hỏi chung chung

Khách hỏi: "Chuyển tiền trả nợ thẻ giúp tôi."

Bước 1 (bắt buộc): đọc `/customer_data.json`, quét `statements` — thấy chỉ
`card_001` (MSB Visa Signature) có kỳ sao kê `status: current_unpaid`
(21.400.000đ, hạn 10/08/2026); `card_002` (Visa Classic) dư nợ 0, không có
kỳ sao kê nào chưa trả. → **Tự xác định đúng thẻ là Visa Signature, không
hỏi lại khách hàng muốn trả thẻ nào.**

Phần text trả lời: "Thẻ MSB Visa Signature đang có dư nợ 21.400.000đ, hạn
thanh toán 10/08/2026 — mình đề xuất trả khoản này."

Kèm khối:

```ui-json
{"type": "transfer_form", "recipient": "MSB Visa Signature", "account_number": "card_001", "amount": 21400000, "note": "Thanh toan du no the MSB Visa Signature ky sao ke 21/06-20/07"}
```

### Ví dụ 3 — chuyển cho 1 người có trong `beneficiaries`

Khách hỏi: "Chuyển tiền cho Toàn 500 nghìn với nội dung Thanh toán tiền
ăn."

Bước 1 (bắt buộc): đọc `beneficiaries` trong `/customer_data.json`, thấy
đúng 1 entry `{"name": "Toàn", "account_number": "00012000321",
"bank_name": "Techcombank"}` — dùng nguyên số tài khoản/ngân hàng này.

Phần text trả lời: "Mình đã điền sẵn form chuyển 500.000đ cho Toàn
(Techcombank), bạn xem lại rồi bấm xác nhận nhé."

Kèm khối:

```ui-json
{"type": "transfer_form", "recipient": "Toàn", "account_number": "00012000321", "amount": 500000, "note": "Thanh toan tien an"}
```

## Ví dụ SAI (bị huỷ toàn bộ)

```
# SAI — "Nam" không có trong beneficiaries, khách hàng cũng không cho số
# tài khoản -> account_number này là agent tự bịa
{"type": "transfer_form", "recipient": "Nam", "account_number": "0123456789", "amount": 500000, "note": "chuyển tiền hộ"}

# SAI — account_number bịa, không khớp card_id/card_number_last4 nào của khách hàng
{"type": "transfer_form", "recipient": "MSB", "account_number": "9999999999", "amount": 1000000, "note": "tra no"}

# SAI — thiếu field bắt buộc (note)
{"type": "transfer_form", "recipient": "MSB Visa Signature", "account_number": "card_001", "amount": 910000}
```

**Sai lầm cụ thể cần tránh (đã quan sát được thật):**
- Khách hỏi chung chung "chuyển tiền trả nợ thẻ giúp tôi" (không nêu tên
  thẻ) → agent chỉ hỏi lại "Bạn muốn trả nợ thẻ nào?" dù dữ liệu
  `statements` đã đủ để tự xác định chỉ có 1 thẻ đang có dư nợ chưa thanh
  toán. **Sai** — PHẢI tự đề xuất luôn.
- Khách hàng nêu tên người nhận không có trong `beneficiaries` → agent tự
  bịa 1 số tài khoản nghe hợp lý để vẫn tạo được form. **Sai và nguy
  hiểm** — PHẢI hỏi lại số tài khoản thật thay vì bịa.

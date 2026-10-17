---
name: transfer-form
description: Dùng khi nên gợi ý khách hàng chuyển tiền trả nợ thẻ tín dụng của chính họ (ví dụ khách hỏi "tôi nên trả nợ thẻ bao nhiêu", "sắp tới hạn thanh toán chưa", hoặc agent chủ động thấy dư nợ sắp đến hạn khi trả lời câu hỏi liên quan). KHÔNG dùng để gợi ý chuyển tiền cho người khác/merchant — xem phần Phạm vi bên dưới.
---

# Transfer form (đề xuất chuyển tiền — chỉ hiển thị, không thực thi)

## Phạm vi hiện tại — QUAN TRỌNG, đọc trước khi dùng skill này

`/customer_data.json` chỉ có dữ liệu **chi tiêu thẻ** (`transactions`, mua
hàng tại merchant) và **dư nợ/sao kê thẻ** (`cards`, `statements`) — **không
có** lịch sử chuyển khoản cá nhân (P2P) tới người khác. Vì vậy:

- **CHỈ dùng skill này cho việc trả nợ thẻ tín dụng của chính khách hàng**
  (`recipient` luôn là ngân hàng phát hành thẻ đó, `account_number` luôn là
  1 `card_id`/`card_number_last4` có thật trong `cards` của khách hàng đang
  trò chuyện).
- **KHÔNG** dùng skill này để đề xuất chuyển tiền cho 1 người khác/merchant
  bất kỳ — không có dữ liệu nào xác nhận được số tài khoản/người nhận đó là
  thật, đề xuất kiểu đó có nguy cơ bịa thông tin nguy hiểm hơn nhiều so với
  bịa số liệu chart.

## Quy trình bắt buộc — Check trước, Propose sau

1. **Check (bắt buộc, không được bỏ qua):** đọc `/customer_data.json`
   (`cards`, `statements`) bằng `read_file`/`grep` để lấy đúng
   `available_credit_vnd`, `total_due_vnd`, `min_payment_vnd`, `due_date`
   thật của thẻ liên quan — không bịa số. Tự xác nhận số tiền định đề xuất
   (`amount`) **không vượt quá** `available_credit_vnd` của thẻ đó trước
   khi chèn khối `ui-json`.
   - Nếu không thẻ nào đủ hạn mức khả dụng cho số tiền định đề xuất:
     **đừng chèn `transfer_form`**, chỉ trả lời bằng text giải thích giới
     hạn thật.
2. **Propose:** chèn **đúng 1 khối** `ui-json` ở cuối câu trả lời:

```ui-json
{"type": "transfer_form", "recipient": "...", "account_number": "...", "amount": 0, "note": "..."}
```

## Schema

- `type` (bắt buộc): luôn là `"transfer_form"`.
- `recipient` (bắt buộc): string — tên ngân hàng/thẻ phát hành (ví dụ tên
  `card_name` trong `cards`), không phải tên người.
- `account_number` (bắt buộc): string — `card_id` hoặc `card_number_last4`
  thật của khách hàng, lấy từ `/customer_data.json`.
- `amount` (bắt buộc): number JSON thật, dương — số tiền đề xuất chuyển
  (ví dụ `min_payment_vnd` hoặc `total_due_vnd` của kỳ sao kê liên quan).
- `note` (bắt buộc): string ngắn — **đúng nội dung chuyển khoản** sẽ điền
  vào form thật (ví dụ "Thanh toan du no the MSB Visa Signature ky 06-07").
  Đây là nội dung khách hàng cần để ngân hàng nhận diện đúng giao dịch —
  không phải lời giải thích cho khách hàng, viết ngắn gọn như 1 nội dung
  chuyển khoản thật (không dấu cũng được, giống cách ghi nội dung CK
  thường thấy).

## PHẢI (bắt buộc — sai 1 điều là toàn bộ đề xuất bị huỷ)

1. Đã tự đối chiếu `amount` với `available_credit_vnd` đọc được từ
   `/customer_data.json` và xác nhận đủ hạn mức trước khi chèn khối này.
2. JSON thật (dấu nháy kép), không phải Python dict repr.
3. `account_number` PHẢI trùng khớp 1 `card_id`/`card_number_last4` có thật
   trong `cards` của khách hàng đang trò chuyện (đọc từ
   `/customer_data.json`, không bịa).
4. `amount` là number JSON thật, dương, khớp đúng số liệu đọc được từ
   `statements` (không tự làm tròn/bịa).
5. `note` PHẢI có nội dung cụ thể (không được rỗng) — đây là nội dung
   chuyển khoản thật sự sẽ điền vào form.
6. Đúng 1 khối `ui-json` mỗi câu trả lời.

## KHÔNG ĐƯỢC

- KHÔNG dùng skill này để đề xuất chuyển tiền cho người/merchant khác
  ngoài chính ngân hàng phát hành thẻ của khách hàng (xem "Phạm vi hiện
  tại" ở trên).
- KHÔNG tự thêm field ngoài 5 field đã định nghĩa (`type`, `recipient`,
  `account_number`, `amount`, `note`).
- KHÔNG chèn khối này nếu chưa tự xác nhận đủ hạn mức khả dụng theo đúng
  bước Check ở trên.
- KHÔNG khẳng định việc chuyển tiền đã xảy ra — đây chỉ là 1 form điền sẵn
  để khách hàng tự xem và tự bấm xác nhận trên UI, việc chuyển tiền thật
  (nếu có) diễn ra hoàn toàn bên ngoài cuộc hội thoại này.

## Ví dụ ĐÚNG

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

## Ví dụ SAI (bị huỷ toàn bộ)

```
# SAI — recipient là 1 người, không phải ngân hàng/thẻ -- không có dữ liệu xác nhận
{"type": "transfer_form", "recipient": "Nguyễn Văn A", "account_number": "0123456789", "amount": 500000, "note": "chuyển tiền hộ"}

# SAI — account_number bịa, không khớp card_id/card_number_last4 nào của khách hàng
{"type": "transfer_form", "recipient": "MSB", "account_number": "9999999999", "amount": 1000000, "note": "tra no"}

# SAI — thiếu field bắt buộc (note)
{"type": "transfer_form", "recipient": "MSB Visa Signature", "account_number": "card_001", "amount": 910000}
```

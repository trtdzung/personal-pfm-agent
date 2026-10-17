# Form chuyển tiền trả nợ thẻ (`transfer_form`) — hướng dẫn cho frontend

Tài liệu này mô tả loại UI thứ 2 agent có thể trả ra qua field `ui` (loại
đầu tiên là `chart`, xem `docs/chart-visualization.md`) — dùng cùng 1 cơ
chế/envelope, chỉ khác `ui.type`.

## Phạm vi hiện tại — chỉ trả nợ thẻ tín dụng của chính khách hàng

Agent **chỉ** đề xuất `transfer_form` cho việc **thanh toán dư nợ thẻ tín
dụng của chính khách hàng đang trò chuyện** (ví dụ trả tối thiểu hoặc trả
hết 1 kỳ sao kê) — **không** đề xuất chuyển tiền cho người khác/merchant,
vì dữ liệu hiện có (`transactions`) chỉ là lịch sử chi tiêu thẻ, không có
lịch sử chuyển khoản cá nhân đáng tin cậy để đối chiếu người nhận.

## Cơ chế

- Giống hệt `chart`: agent tự quyết định có nên đề xuất hay không (skill
  `skills/project/transfer-form/`), chèn 1 khối JSON vào cuối câu trả lời,
  `server.py` tách ra thành field `ui` riêng.
- Trước khi đề xuất, agent tự đọc `/customer_data.json` (`cards`,
  `statements`) để xác nhận số tiền đề xuất không vượt hạn mức khả dụng
  thật của khách hàng — đây là bước kiểm tra nội bộ của agent (không dùng
  tool riêng), không phải thứ frontend cần quan tâm (frontend chỉ nhận kết
  quả cuối qua field `ui`).
- **Đây chỉ là đề xuất hiển thị — agent KHÔNG thực hiện chuyển tiền.**
  Việc chuyển tiền thật (nếu khách hàng đồng ý) diễn ra qua 1 luồng xác
  thực ngân hàng hoàn toàn tách biệt, do hệ thống PFM/core banking khác
  của MSB xử lý khi khách hàng bấm xác nhận trên UI — `server.py`/`/chat`
  không có endpoint nào thực thi việc này.

## Response `POST /chat`

```json
{
  "answer": "Kỳ sao kê thẻ MSB Visa Signature đến hạn 10/08/2026, dư nợ 21.400.000đ...",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "transfer_form",
    "recipient": "MSB Visa Signature",
    "account_number": "card_001",
    "amount": 21400000,
    "note": "Thanh toan du no the MSB Visa Signature ky sao ke 21/06-20/07"
  }
}
```

## Schema của `ui` (khi `type === "transfer_form"`)

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `type` | `"transfer_form"` | ✅ | Discriminator |
| `recipient` | string | ✅ | Tên ngân hàng/thẻ phát hành (không phải tên người) |
| `account_number` | string | ✅ | `card_id` hoặc số thẻ rút gọn của chính khách hàng |
| `amount` | number | ✅ | Số tiền đề xuất, luôn dương |
| `note` | string | ✅ | **Nội dung chuyển khoản** — điền thẳng vào ô "nội dung/lời nhắn" của form chuyển tiền thật, không phải lời giải thích cho khách hàng |

## Luồng UI gợi ý

1. Nhận `ui.type === "transfer_form"` → hiện 1 form/card riêng dưới bong
   bóng chat, điền sẵn `recipient`/`amount`/`note` (chỉ đọc, không cho
   khách hàng tự sửa số tiền tuỳ ý — nếu muốn số khác, khách hàng nên hỏi
   lại agent để có đề xuất mới đã qua check hạn mức). `note` điền thẳng
   vào ô nội dung chuyển khoản của form.
2. Hiện 1 nút xác nhận (ví dụ "Thanh toán ngay") — **khi bấm, frontend tự
   gọi sang hệ thống PFM/core banking thật của MSB để thực hiện giao dịch,
   không gọi lại bất kỳ endpoint nào của `server.py`** (repo này không có
   endpoint thực thi).
3. Nếu `ui` là `null` hoặc `ui.type` không phải `"chart"`/`"transfer_form"`
   (loại chưa hỗ trợ), chỉ hiện `answer`, không hiện form/chart nào.

## Lưu ý về độ tin cậy

Giống `chart`: `ui` là kết quả model tự sinh, đã được `server.py` validate
lại nghiêm ngặt (loại bỏ hoàn toàn nếu thiếu field, sai kiểu, `amount` ≤ 0)
trước khi trả về — nhưng **frontend vẫn nên coi `amount`/`account_number`
là "đề xuất cần khách hàng tự xem lại"**, không tự động thực hiện giao dịch
mà không qua bước xác nhận rõ ràng của khách hàng.

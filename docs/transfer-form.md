# Form chuyển tiền (`transfer_form`) — hướng dẫn cho frontend

Tài liệu này mô tả loại UI thứ 2 agent có thể trả ra qua field `ui` (loại
đầu tiên là `chart`, xem `docs/chart-visualization.md`) — dùng cùng 1 cơ
chế/envelope, chỉ khác `ui.type`.

## Phạm vi hiện tại — 2 trường hợp

**(A) Trả nợ thẻ tín dụng của chính khách hàng** — ví dụ trả tối thiểu
hoặc trả hết 1 kỳ sao kê. `recipient` là ngân hàng phát hành thẻ,
`account_number` là `card_id`/số thẻ rút gọn của chính khách hàng.

**(B) Chuyển tiền cho 1 người trong danh bạ đã lưu** (`beneficiaries`
trong dữ liệu khách hàng) — ví dụ "chuyển tiền cho Toàn 500 nghìn".
`recipient` là tên người nhận, `account_number`/ngân hàng lấy từ đúng
entry `beneficiaries` khớp tên (hoặc từ thông tin khách hàng tự cung cấp
trong câu hỏi nếu người đó không có trong danh bạ đã lưu).

**⚠️ `beneficiaries` hiện là danh sách hardcode tạm thời trong dữ liệu mock
— chưa có tool đọc danh bạ thật/realtime từ hệ thống PFM** (xem `todo.md`
mục Roadmap PFM). Nếu khách hàng nêu tên 1 người không có trong danh sách
này và không tự cung cấp số tài khoản, agent sẽ **hỏi lại** thay vì tự tạo
form — nên frontend có thể nhận được câu trả lời text thuần (`ui: null`)
cho 1 số yêu cầu chuyển tiền, không phải lúc nào cũng có form.

## Cơ chế

- Giống hệt `chart`: agent tự quyết định có nên đề xuất hay không (skill
  `skills/project/transfer-form/`), chèn 1 khối JSON vào cuối câu trả lời,
  `server.py` tách ra thành field `ui` riêng.
- Trước khi đề xuất, agent tự đọc `/customer_data.json` (`cards`,
  `statements`, `beneficiaries`) để xác nhận số tiền/người nhận — đây là
  bước kiểm tra nội bộ của agent (không dùng tool riêng), không phải thứ
  frontend cần quan tâm (frontend chỉ nhận kết quả cuối qua field `ui`).
- **Đây chỉ là đề xuất hiển thị — agent KHÔNG thực hiện chuyển tiền.**
  Việc chuyển tiền thật (nếu khách hàng đồng ý) diễn ra qua 1 luồng xác
  thực ngân hàng hoàn toàn tách biệt, do hệ thống PFM/core banking khác
  của MSB xử lý khi khách hàng bấm xác nhận trên UI — `server.py`/`/chat`
  không có endpoint nào thực thi việc này.

## Response `POST /chat`

Trường hợp (A) — trả nợ thẻ:
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

Trường hợp (B) — chuyển cho 1 người trong danh bạ đã lưu:
```json
{
  "answer": "Mình đã điền sẵn form chuyển 500.000đ cho Toàn (Techcombank), bạn xem lại rồi bấm xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "transfer_form",
    "recipient": "Toàn",
    "account_number": "00012000321",
    "amount": 500000,
    "note": "Thanh toan tien an"
  }
}
```

## Schema của `ui` (khi `type === "transfer_form"`)

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `type` | `"transfer_form"` | ✅ | Discriminator |
| `recipient` | string | ✅ | (A) tên ngân hàng/thẻ phát hành; (B) tên người nhận |
| `account_number` | string | ✅ | (A) `card_id`/số thẻ rút gọn của chính khách hàng; (B) số tài khoản người nhận |
| `amount` | number | ✅ | Số tiền đề xuất, luôn dương |
| `note` | string | ✅ | **Nội dung chuyển khoản** — điền thẳng vào ô "nội dung/lời nhắn" của form chuyển tiền thật, không phải lời giải thích cho khách hàng |

Không có field nào phân biệt (A)/(B) tường minh — frontend không cần phân
biệt, chỉ hiện đúng 4 field trên như 1 form chuyển tiền chung.

## Luồng UI gợi ý

1. Nhận `ui.type === "transfer_form"` → hiện 1 form/card riêng dưới bong
   bóng chat, điền sẵn `recipient`/`account_number`/`amount`/`note` (chỉ
   đọc, không cho khách hàng tự sửa số tiền tuỳ ý — nếu muốn số khác,
   khách hàng nên hỏi lại agent để có đề xuất mới đã qua check). `note`
   điền thẳng vào ô nội dung chuyển khoản của form.
2. Hiện 1 nút xác nhận (ví dụ "Thanh toán ngay"/"Chuyển tiền") — **khi
   bấm, frontend tự gọi sang hệ thống PFM/core banking thật của MSB để
   thực hiện giao dịch, không gọi lại bất kỳ endpoint nào của `server.py`**
   (repo này không có endpoint thực thi).
3. Nếu `ui` là `null` hoặc `ui.type` không phải loại đã hỗ trợ, chỉ hiện
   `answer`, không hiện form/chart nào — với trường hợp chuyển cho 1 người
   không có trong danh bạ đã lưu, đây là kết quả **bình thường** (agent
   đang hỏi lại số tài khoản, không phải lỗi).

## Lưu ý về độ tin cậy

`ui` là kết quả model tự sinh, đã được `server.py` validate lại nghiêm
ngặt (loại bỏ hoàn toàn nếu thiếu field, sai kiểu, `amount` ≤ 0) trước khi
trả về — nhưng **frontend vẫn nên coi `amount`/`recipient`/`account_number`
là "đề xuất cần khách hàng tự xem lại"**, không tự động thực hiện giao dịch
mà không qua bước xác nhận rõ ràng của khách hàng.

**Riêng trường hợp (B) rủi ro cao hơn (A):** `account_number` cho 1 người
nhận hiện chỉ đến từ 1 danh sách hardcode trong dữ liệu mock hoặc từ chính
văn bản khách hàng gõ — chưa có xác thực ngân hàng thật (tên chủ tài
khoản khớp số tài khoản, số tài khoản còn tồn tại...). Khuyến nghị
frontend hiển thị rõ cảnh báo dạng "kiểm tra kỹ thông tin người nhận
trước khi chuyển" cho trường hợp (B), mạnh hơn mức cảnh báo thông thường
của (A).

# Form chuyển tiền (`transfer_form`) — hướng dẫn cho frontend

Tài liệu này mô tả loại UI thứ 2 agent có thể trả ra qua field `ui` (loại
đầu tiên là `chart`, xem `docs/chart-visualization.md`) — dùng cùng 1 cơ
chế/envelope, chỉ khác `ui.type`.

## Phạm vi hiện tại — 2 trường hợp, 2 dạng schema

**(A) Trả nợ thẻ tín dụng của chính khách hàng** — ví dụ trả tối thiểu
hoặc trả hết 1 kỳ sao kê. Dùng **dạng schema 1** (`recipient`/
`account_number`): `recipient` là ngân hàng phát hành thẻ, `account_number`
là `card_id`/số thẻ rút gọn của chính khách hàng.

**(B) Chuyển tiền cho 1 người trong danh bạ đã lưu** — ví dụ "chuyển tiền
cho Lan 500 nghìn". Agent gọi tool nội bộ `query_beneficiaries()`, đọc
**trực tiếp, thời gian thực** từ backend `pfm` (`GET /api/beneficiaries?cif=`
— xem `backend_docs/pfm-read-api.md`, không còn là dữ liệu mock nữa).

- Nếu người nhận **có trong danh sách đã lưu** → dùng **dạng schema 2**
  (`beneficiary_id`/`category`): agent chỉ trả `id` của người nhận, KHÔNG
  trả tên/số tài khoản/ngân hàng — `pfm` tự tra các field đó từ chính API
  của mình khi nhận `beneficiary_id`.
- Nếu người nhận **không có trong danh sách đã lưu** nhưng khách hàng tự
  cung cấp đủ tên + số tài khoản + ngân hàng trong câu hỏi → dùng **dạng
  schema 1** (`recipient`/`account_number`), giống trường hợp (A) về mặt
  field.
- Nếu người nhận không có trong danh sách và khách hàng không tự cung cấp
  đủ thông tin → agent **hỏi lại**, không tạo form — frontend có thể nhận
  `ui: null` với `answer` là câu hỏi lại, không phải lỗi.

## Cơ chế

- Giống hệt `chart`: agent tự quyết định có nên đề xuất hay không (skill
  `skills/project/transfer-form/`), chèn 1 khối JSON vào cuối câu trả lời,
  `server.py` tách ra thành field `ui` riêng.
- Trường hợp (A): agent tự đọc `/customer_data.json` (`cards`,
  `statements`) để xác nhận số tiền/thẻ liên quan.
- Trường hợp (B): agent gọi tool `query_beneficiaries()` (không phải đọc
  file) để lấy danh sách người nhận đã lưu **tại thời điểm hỏi** — đây là
  bước kiểm tra nội bộ của agent, không phải thứ frontend cần quan tâm
  (frontend chỉ nhận kết quả cuối qua field `ui`).
- **Đây chỉ là đề xuất hiển thị — agent KHÔNG thực hiện chuyển tiền.**
  Việc chuyển tiền thật (nếu khách hàng đồng ý) diễn ra qua 1 luồng xác
  thực ngân hàng hoàn toàn tách biệt, do hệ thống PFM/core banking khác
  của MSB xử lý khi khách hàng bấm xác nhận trên UI — `server.py`/`/chat`
  không có endpoint nào thực thi việc này.

## Response `POST /chat`

Trường hợp (A) — trả nợ thẻ (dạng schema 1):
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

Trường hợp (B) — chuyển cho 1 người có trong danh bạ đã lưu (dạng schema 2,
`pfm` tự tra `name`/`accountNumber`/`bankName` thật từ `beneficiary_id`):
```json
{
  "answer": "Mình đã điền sẵn form chuyển 500.000đ cho Nguyễn Thị Lan, bạn xem lại rồi bấm xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "transfer_form",
    "beneficiary_id": "b_stable_lan",
    "amount": 500000,
    "note": "Thanh toan tien an",
    "category": "dining"
  }
}
```

Trường hợp (B) — người nhận KHÔNG có trong danh bạ, khách hàng tự cung cấp
đủ thông tin (dạng schema 1, giống (A) về field):
```json
{
  "answer": "Mình đã điền sẵn form chuyển 200.000đ cho Nam, bạn xem lại rồi bấm xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "transfer_form",
    "recipient": "Nam",
    "account_number": "0123456789",
    "amount": 200000,
    "note": "Tra tien ca phe"
  }
}
```

## Schema của `ui` (khi `type === "transfer_form"`)

`type` (bắt buộc, mọi trường hợp): luôn là `"transfer_form"`. Đúng 1 trong
2 dạng dưới — không bao giờ trộn field của cả 2 dạng trong cùng 1 response.

**Dạng schema 1** (trường hợp A, hoặc B khi người nhận không có trong danh
bạ đã lưu):

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `recipient` | string | ✅ | (A) tên ngân hàng/thẻ phát hành; (B) tên người nhận khách hàng tự cung cấp |
| `account_number` | string | ✅ | (A) `card_id`/số thẻ rút gọn của chính khách hàng; (B) số tài khoản khách hàng tự cung cấp |
| `amount` | number | ✅ | Số tiền đề xuất, luôn dương |
| `note` | string | ✅ | Nội dung chuyển khoản |

**Dạng schema 2** (trường hợp B, người nhận có trong danh bạ đã lưu — xem
`backend_docs/pfm-read-api.md`):

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `beneficiary_id` | string | ✅ | Phải khớp đúng 1 `id` trong `GET /api/beneficiaries?cif=` — sai/không tồn tại thì frontend/`pfm` nên bỏ qua form, chỉ hiện `answer` |
| `amount` | number | ✅ | Số tiền đề xuất, luôn dương |
| `note` | string | ✅ | Nội dung chuyển khoản |
| `category` | string | ✅ | 1 trong 10 giá trị: `housing`, `utilities`, `subscriptions`, `insurance`, `dining`, `transport`, `shopping`, `groceries`, `entertainment`, `health` |

Frontend/`pfm` cần tự phân biệt 2 dạng bằng sự **có mặt của `beneficiary_id`**
(dạng 2) so với `recipient`/`account_number` (dạng 1) — không có field
discriminator riêng khác `type`. Với dạng 2, `pfm` tự dùng `beneficiary_id`
để tra `name`/`accountNumber`/`bankName` thật từ chính `GET
/api/beneficiaries`, ghép với `amount`/`note`/`category` agent trả về rồi
hiện đủ 6 field lên form.

## Luồng UI gợi ý

1. Nhận `ui.type === "transfer_form"` → hiện 1 form/card riêng dưới bong
   bóng chat.
   - Dạng schema 1: điền sẵn `recipient`/`account_number`/`amount`/`note`
     trực tiếp từ response.
   - Dạng schema 2: dùng `beneficiary_id` để lấy `name`/`accountNumber`/
     `bankName` thật (`GET /api/beneficiaries?cif=`), ghép với `amount`/
     `note`/`category` từ response, rồi hiện đủ 6 field.
   - Cả 2 dạng: chỉ đọc, không cho khách hàng tự sửa số tiền tuỳ ý — nếu
     muốn số khác, khách hàng nên hỏi lại agent để có đề xuất mới đã qua
     check. `note` điền thẳng vào ô nội dung chuyển khoản của form.
2. Hiện 1 nút xác nhận (ví dụ "Thanh toán ngay"/"Chuyển tiền") — **khi
   bấm, frontend tự gọi sang hệ thống PFM/core banking thật của MSB để
   thực hiện giao dịch, không gọi lại bất kỳ endpoint nào của `server.py`**
   (repo này không có endpoint thực thi).
3. Nếu `ui` là `null` hoặc `ui.type` không phải loại đã hỗ trợ, chỉ hiện
   `answer`, không hiện form/chart nào — với trường hợp chuyển cho 1 người
   không có trong danh bạ đã lưu và khách hàng không tự cung cấp đủ thông
   tin, đây là kết quả **bình thường** (agent đang hỏi lại số tài khoản,
   không phải lỗi).

## Lưu ý về độ tin cậy

`ui` là kết quả model tự sinh, đã được `server.py` validate lại nghiêm
ngặt (loại bỏ hoàn toàn nếu thiếu field, sai kiểu, `amount` ≤ 0, `category`
không hợp lệ, hoặc trộn field của cả 2 dạng) trước khi trả về — nhưng
**frontend vẫn nên coi mọi field là "đề xuất cần khách hàng tự xem lại"**,
không tự động thực hiện giao dịch mà không qua bước xác nhận rõ ràng của
khách hàng.

**Riêng trường hợp (B) rủi ro cao hơn (A), dù đã cải thiện:** với dạng
schema 2, agent không còn tự gõ số tài khoản (loại bỏ rủi ro
hallucinate/gõ sai số tài khoản) — nhưng `beneficiary_id` vẫn chỉ đến từ
danh sách do khách hàng/hệ thống tự khai báo trước đó (`source`:
`msb`/`self_reported`/`estimated`/`mock`, xem `backend_docs/pfm-read-api.md`),
chưa có xác thực ngân hàng thật tại thời điểm chuyển. Với dạng schema 1
(khách tự cho số tài khoản), rủi ro cao hơn nữa vì chưa qua bất kỳ xác
thực nào. Khuyến nghị frontend hiển thị rõ cảnh báo dạng "kiểm tra kỹ
thông tin người nhận trước khi chuyển" cho cả 2 dạng của trường hợp (B),
mạnh hơn mức cảnh báo thông thường của (A).

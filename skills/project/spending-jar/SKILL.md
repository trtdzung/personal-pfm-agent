---
name: spending-jar
description: Dùng khi nên gợi ý khách hàng tạo mới hoặc chỉnh sửa 1 "hũ chi tiêu" (spending jar) — phân bổ ngân sách theo danh mục/mục tiêu (ví dụ "tạo hũ ăn uống 3 triệu/tháng", "phân bổ chi tiêu theo rule 50/30/20", "tăng hũ giải trí lên 800 nghìn"). Đây là 1 tag ngân sách nội bộ do khách hàng tự đặt tên, KHÔNG phải sổ/tài khoản tiết kiệm thật của ngân hàng. Skill này CHÍNH LÀ cách xử lý những câu hỏi dạng "tạo giúp tôi...", "tăng... giúp tôi" — dùng skill để đề xuất, đừng từ chối. KHÔNG dùng để thực hiện thao tác tạo/sửa hũ thật — chỉ đề xuất, khách hàng tự xác nhận.
---

# Spending jar (hũ chi tiêu — chỉ hiển thị, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

**"Hũ chi tiêu" KHÔNG phải sản phẩm ngân hàng thật.** Đây chỉ là 1 tag
phân bổ ngân sách nội bộ do chính khách hàng đặt tên trong app PFM —
**hoàn toàn khác** với "sổ tiết kiệm"/"tài khoản tiết kiệm" (1 sản phẩm
ngân hàng thật, có lãi suất/kỳ hạn, phải mở tại quầy hoặc app ngân hàng
riêng). Kể cả khi tên 1 hũ chứa chữ "tiết kiệm" (ví dụ hũ "Tiết kiệm khẩn
cấp" — chỉ là tên khách hàng tự đặt cho 1 mục ngân sách), **đừng suy diễn
đây là yêu cầu mở/thay đổi 1 sản phẩm ngân hàng thật**.

**Đề xuất `create_jar`/`edit_jar` an toàn tuyệt đối, không phải "hành động
thật":** chèn khối `ui-json` theo skill này **không khác gì** việc bạn
viết ra 1 câu trả lời text hay 1 bảng số liệu — bạn không tạo/sửa/gửi bất
kỳ thứ gì tới hệ thống ngân hàng thật khi làm việc này (xem thêm nguyên
tắc chung ở đầu `instructions.md`). Khi câu hỏi khớp mô tả skill này (ví
dụ "tạo giúp tôi hũ...", "tăng hũ... lên..."), đây **chính xác** là lúc
nên dùng skill — **đừng từ chối, và đừng chỉ trả lời bằng text rồi bỏ qua
bước chèn khối `ui-json`** (nếu bạn đã tính đủ số liệu để đề xuất, PHẢI
chèn khối này, không được dừng ở text).

## Phạm vi hiện tại — QUAN TRỌNG, đọc trước khi dùng skill này

Dùng tool **`list_existing_jars()`** (không cần tham số — tool tự biết
đang nói chuyện với khách hàng nào) để lấy danh sách hũ hiện có, **thay vì
đọc trường `jars` tĩnh trong `/customer_data.json`** — tool này đọc lại
mới mỗi lần gọi nên phản ánh đúng hũ đã tạo/sửa gần nhất trong chính cuộc
hội thoại này, không bị giới hạn bởi snapshot đầu phiên.

"Đã có hũ" nên hiểu theo 2 nguồn, ưu tiên nguồn mới hơn khi có xung đột:

1. Hũ trả về từ `list_existing_jars()`.
2. Hũ được nhắc tới/agent vừa đề xuất **trong chính cuộc hội thoại này**
   (mới hơn, ưu tiên hơn nếu có khác biệt — ví dụ agent vừa đề xuất
   `create_jar` ở lượt trước, giờ khách hàng muốn đổi số tiền ngay, dù
   `list_existing_jars()` chưa kịp phản ánh hũ đó).

Nếu khách hàng nhắc tới 1 hũ không có ở cả 2 nguồn trên: hỏi lại thay vì tự
đoán, hoặc dùng `create_jar` nếu ý khách hàng rõ ràng là muốn **tạo mới**.

Số tiền đề xuất (`allocation_amount`) PHẢI tính từ dữ liệu chi tiêu thật
trong `/customer_data.json` (`monthly_spending_summary`/`transactions`
theo danh mục liên quan, hoặc `customer.monthly_income_vnd`/
`account.balance_vnd` nếu áp dụng rule tổng quát như 50/30/20) — không bịa
số. `/customer_data.json` (chi tiêu, thu nhập, số dư) vẫn đọc trực tiếp từ
system prompt như trước — chỉ riêng **danh sách hũ hiện có** thì dùng tool
`list_existing_jars()`.

## Khi nào dùng `create_jar` vs `edit_jar`

- **`create_jar`** — hũ đó **không có** trong kết quả `list_existing_jars()`
  và cũng chưa từng được nhắc tới trong hội thoại này.
- **`edit_jar`** — hũ đó **có** trong kết quả `list_existing_jars()`, HOẶC
  đã được nhắc tới/agent vừa đề xuất trong chính cuộc hội thoại này.

## Quy trình bắt buộc — Check trước, Propose sau

1. **Check (bắt buộc):** gọi tool `list_existing_jars()` để xem đã có hũ
   tên đó chưa (chọn đúng `create_jar` hay `edit_jar`). Số liệu chi tiêu
   làm căn cứ đề xuất mức phân bổ (`monthly_spending_summary`,
   `monthly_income_vnd`/`account.balance_vnd`) đã có sẵn ngay trong system
   prompt — không cần `read_file`/`grep` cho phần này, không bịa số.
2. **Propose:** chèn **đúng 1 khối** `ui-json` ở cuối câu trả lời, dùng
   đúng 1 trong 2 type dưới đây.

```ui-json
{"type": "create_jar", "jar_name": "...", "allocation_amount": 0, "reason": "..."}
```

```ui-json
{"type": "edit_jar", "jar_name": "...", "allocation_amount": 0, "reason": "..."}
```

## Schema (giống nhau cho cả 2 type)

- `type` (bắt buộc): `"create_jar"` hoặc `"edit_jar"`.
- `jar_name` (bắt buộc): string — tên hũ (ví dụ "Ăn uống", "Tiết kiệm khẩn
  cấp"). Với `edit_jar`, phải khớp đúng tên hũ có trong `jars` của
  `/customer_data.json` HOẶC đã nhắc tới trước đó trong hội thoại.
- `allocation_amount` (bắt buộc): number JSON thật, dương — số tiền đề
  xuất phân bổ vào hũ mỗi tháng.
- `reason` (bắt buộc): string ngắn — căn cứ đề xuất mức này (ví dụ "trung
  bình chi tiêu Ăn uống 3 tháng gần nhất là 2.880.000đ/tháng").

## PHẢI (bắt buộc — sai 1 điều là toàn bộ đề xuất bị huỷ)

1. JSON thật (dấu nháy kép), không phải Python dict repr.
2. `type` đúng 1 trong 2 giá trị `"create_jar"`/`"edit_jar"`.
3. `allocation_amount` là number JSON thật, dương — không phải string.
4. `reason` PHẢI có nội dung cụ thể, dựa trên số liệu thật đọc được từ
   `/customer_data.json`.
5. Với `edit_jar`, `jar_name` PHẢI khớp đúng tên hũ trả về từ
   `list_existing_jars()` HOẶC đã xuất hiện trước đó trong hội thoại —
   không tự bịa tên hũ mới rồi gắn nhãn `edit_jar`.
6. Đúng 1 khối `ui-json` mỗi câu trả lời.

## KHÔNG ĐƯỢC

- KHÔNG tự thêm field ngoài 4 field đã định nghĩa (`type`, `jar_name`,
  `allocation_amount`, `reason`).
- KHÔNG dùng `edit_jar` cho 1 hũ không có trong kết quả `list_existing_jars()`
  và cũng chưa từng được nhắc tới trong hội thoại này — dùng `create_jar`
  thay vào đó.
- KHÔNG khẳng định hũ đã được tạo/chỉnh sửa thật — đây chỉ là đề xuất hiển
  thị để khách hàng tự xem và tự bấm xác nhận trên UI, việc tạo/sửa hũ
  thật (nếu có) diễn ra hoàn toàn bên ngoài cuộc hội thoại này, ở hệ thống
  PFM khác.

## Ví dụ ĐÚNG

Khách hỏi: "Tạo giúp tôi 1 hũ ăn uống hợp lý."

Bước 1: đọc `/customer_data.json`, thấy chi tiêu Ăn uống 3 tháng gần nhất
lần lượt 3.100.000đ / 3.450.000đ / 2.585.000đ → trung bình ~3.045.000đ.

Phần text trả lời: "Dựa trên chi tiêu Ăn uống trung bình 3 tháng gần đây
(~3.045.000đ/tháng), mình đề xuất hũ Ăn uống 3.000.000đ/tháng."

Kèm khối:

```ui-json
{"type": "create_jar", "jar_name": "Ăn uống", "allocation_amount": 3000000, "reason": "Trung bình chi tiêu Ăn uống 3 tháng gần nhất (06-08/2026) là ~3.045.000đ/tháng"}
```

Lượt sau, khách hỏi: "Đổi hũ đó lên 4 triệu được không?"

```ui-json
{"type": "edit_jar", "jar_name": "Ăn uống", "allocation_amount": 4000000, "reason": "Khách hàng yêu cầu tăng hũ Ăn uống đã tạo ở lượt trước lên 4.000.000đ/tháng"}
```

Ví dụ khác — hũ đã tồn tại sẵn (không cần nhắc tới trong hội thoại trước):
khách hỏi "Tăng hũ giải trí của tôi lên 800k được không?" → gọi
`list_existing_jars()`, thấy đã có "Giải trí: 600.000đ/tháng" → dùng
`edit_jar` (không phải `create_jar`, vì hũ này đã tồn tại):

```ui-json
{"type": "edit_jar", "jar_name": "Giải trí", "allocation_amount": 800000, "reason": "Khách hàng yêu cầu tăng hũ Giải trí hiện có (600.000đ) lên 800.000đ/tháng"}
```

## Ví dụ SAI (bị huỷ toàn bộ)

```
# SAI — allocation_amount là string, không phải number
{"type": "create_jar", "jar_name": "Ăn uống", "allocation_amount": "3000000", "reason": "x"}

# SAI — thiếu field bắt buộc (reason)
{"type": "create_jar", "jar_name": "Ăn uống", "allocation_amount": 3000000}

# SAI — edit_jar cho hũ không có trong kết quả list_existing_jars() và
# cũng chưa từng nhắc tới trong hội thoại này
{"type": "edit_jar", "jar_name": "Du lịch", "allocation_amount": 2000000, "reason": "..."}
```

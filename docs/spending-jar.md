# Hũ chi tiêu (`create_jar` / `edit_jar`) — hướng dẫn cho frontend

Tài liệu này mô tả 2 loại UI mới agent có thể trả ra qua field `ui` (cùng
envelope với `chart`/`transfer_form`, xem `docs/chart-visualization.md`/
`docs/transfer-form.md`) — chỉ khác `ui.type`.

## Phạm vi hiện tại

Agent đề xuất **tạo mới** (`create_jar`) hoặc **chỉnh sửa** (`edit_jar`)
1 hũ chi tiêu — số tiền phân bổ được tính từ dữ liệu chi tiêu thật của
khách hàng. **Đây chỉ là đề xuất hiển thị — agent KHÔNG tự tạo/sửa hũ
thật.** Việc tạo/sửa hũ thật (nếu khách hàng đồng ý) diễn ra ở 1 hệ thống
PFM khác của MSB khi khách hàng bấm xác nhận trên UI — `server.py`/`/chat`
không có endpoint nào thực thi việc này (repo này chưa có API tạo/sửa hũ).

**Giới hạn cần biết:** agent biết danh sách hũ hiện có qua trường `jars`
trong dữ liệu khách hàng (`jar_id`, `jar_name`, `allocation_amount_vnd`,
`created_on`) — nhưng đây là **snapshot đầu phiên**, không tự cập nhật
theo thời gian thực nếu khách hàng tạo/sửa hũ thật qua hệ thống PFM khác
trong lúc đang trò chuyện (chưa có tool/API đọc danh sách hũ realtime —
xem `todo.md` mục "Roadmap PFM"). `edit_jar` áp dụng cho hũ có trong
`jars` snapshot đó **hoặc** đã được nhắc tới trong chính cuộc hội thoại
đang diễn ra (ví dụ agent vừa đề xuất tạo hũ đó ở lượt trước).

## Response `POST /chat`

Tạo mới:
```json
{
  "answer": "Dựa trên chi tiêu Ăn uống trung bình 3 tháng gần đây (~3.045.000đ/tháng), mình đề xuất hũ Ăn uống 3.000.000đ/tháng.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "create_jar",
    "jar_name": "Ăn uống",
    "allocation_amount": 3000000,
    "reason": "Trung bình chi tiêu Ăn uống 3 tháng gần nhất (06-08/2026) là ~3.045.000đ/tháng"
  }
}
```

Chỉnh sửa (lượt sau, cùng hội thoại):
```json
{
  "answer": "Đã cập nhật đề xuất hũ Ăn uống lên 4.000.000đ/tháng.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "edit_jar",
    "jar_name": "Ăn uống",
    "allocation_amount": 4000000,
    "reason": "Khách hàng yêu cầu tăng hũ Ăn uống đã tạo ở lượt trước lên 4.000.000đ/tháng"
  }
}
```

## Schema của `ui` (khi `type` là `"create_jar"` hoặc `"edit_jar"`)

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `type` | `"create_jar"` \| `"edit_jar"` | ✅ | Discriminator |
| `jar_name` | string | ✅ | Tên hũ |
| `allocation_amount` | number | ✅ | Số tiền đề xuất phân bổ/tháng, luôn dương |
| `reason` | string | ✅ | Căn cứ đề xuất (hiện cho khách hàng xem trước khi xác nhận) |

Cả 2 type dùng chung 1 schema — chỉ khác ý nghĩa: `create_jar` là đề xuất
tạo mới, `edit_jar` là đề xuất đổi mức phân bổ của hũ đã có (trong phạm vi
hội thoại hiện tại).

## Luồng UI gợi ý

1. Nhận `ui.type === "create_jar"` hoặc `"edit_jar"` → hiện 1 form/card
   riêng dưới bong bóng chat, điền sẵn `jar_name`/`allocation_amount`, kèm
   `reason` để khách hàng xem căn cứ đề xuất.
2. Hiện nút xác nhận (ví dụ "Tạo hũ"/"Cập nhật hũ") — **khi bấm, frontend
   tự gọi sang hệ thống PFM thật của MSB để tạo/sửa hũ, không gọi lại bất
   kỳ endpoint nào của `server.py`** (repo này chưa có endpoint này).
3. Nếu `ui` là `null` hoặc `ui.type` chưa hỗ trợ, chỉ hiện `answer`.

## Lưu ý về độ tin cậy

Giống `chart`/`transfer_form`: `ui` đã được `server.py` validate nghiêm
ngặt trước khi trả về (loại bỏ hoàn toàn nếu thiếu field, sai kiểu,
`allocation_amount` ≤ 0) — nhưng việc `jar_name` có thật sự khớp đúng 1
hũ đang tồn tại hay không **vẫn hoàn toàn dựa vào agent tự đọc/đối chiếu
đúng**, không có enforcement bằng code (không dùng tool riêng, xem
`todo.md` mục 1.8 lý do). Frontend nên coi `jar_name`/`allocation_amount`
là "đề xuất cần khách hàng tự xem lại", đặc biệt với `edit_jar` (agent có
thể nhầm hũ nếu hội thoại dài/phức tạp, hoặc dữ liệu snapshot đã lệch so
với thực tế).

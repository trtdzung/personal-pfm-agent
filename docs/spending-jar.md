# Hũ chi tiêu (`create_jar` / `edit_jar`) — hướng dẫn cho frontend

Tài liệu này mô tả 2 loại UI agent có thể trả ra qua field `ui` (cùng envelope với
`chart`/`transfer_form`, xem `docs/chart-visualization.md`, `docs/transfer-form.md`) — chỉ khác
`ui.type`. Loại thứ 3 về hũ, `rebalance_jars` (lấy tiền từ hũ khác để bù hũ thiếu), có tài liệu riêng:
[`docs/jar-rebalance.md`](./jar-rebalance.md).

> **Thay đổi contract (2026-09-20):** `create_jar` thêm `category_ids` (bắt buộc); `edit_jar` nhận
> `jar_id` (bắt buộc) thay cho việc khớp theo tên. Payload cũ không có 2 field này bị `server.py` bỏ
> (`ui = null`, chỉ còn `answer`). Contract đầy đủ phía `pfm`: `backend_docs/pfm-read-api.md` (phần B).

## Phạm vi

Agent đề xuất **tạo mới** (`create_jar`) hoặc **chỉnh sửa** (`edit_jar`) 1 hũ chi tiêu. **Đây chỉ là đề
xuất hiển thị — agent KHÔNG tự tạo/sửa hũ thật.** Việc tạo/sửa (nếu khách đồng ý) do `pfm` thực hiện khi
khách xem lại và bấm xác nhận trên UI; `server.py`/`/chat` không có endpoint nào thực thi việc này.

Agent **đọc** số liệu hũ từ `GET /api/jar-summary?cif=&month=` của `pfm` (tool nội bộ `get_jar_summary`,
số do engine của `pfm` tính — giống hệt màn Ngân sách). Mỗi lượt trả lời có **tối đa 1** `ui`; cần nhiều
bước thì agent làm từng bước, mỗi bước một lượt, và đọc lại số liệu sau mỗi lần khách xác nhận.

## Response `POST /chat`

Tạo mới:

```json
{
  "answer": "Chi Giải trí 3 tháng gần đây trung bình ~1.400.000đ/tháng, mình đề xuất hũ Giải trí 1.500.000đ/tháng.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "create_jar",
    "jar_name": "Giải trí",
    "allocation_amount": 1500000,
    "category_ids": ["entertainment"],
    "reason": "Chi Giải trí 3 tháng gần nhất trung bình ~1.400.000đ/tháng; category Giải trí đang thuộc hũ Khác sẽ chuyển sang hũ mới"
  }
}
```

Chỉnh sửa (hũ đã có, dùng `id` từ `jar-summary`):

```json
{
  "answer": "Hũ Ăn uống tăng từ 4.000.000đ lên 4.500.000đ/tháng, còn trong phần hạn mức được đặt thêm.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "edit_jar",
    "jar_id": "food",
    "jar_name": "Ăn uống",
    "allocation_amount": 4500000,
    "reason": "Khách yêu cầu tăng hạn mức hũ Ăn uống từ 4.000.000đ lên 4.500.000đ; phần tăng 500.000đ nằm trong phần hạn mức còn được đặt thêm (1.200.000đ)"
  }
}
```

## Schema của `ui`

| Field | `create_jar` | `edit_jar` | Kiểu | Ghi chú |
|---|---|---|---|---|
| `type` | ✅ | ✅ | `"create_jar"` \| `"edit_jar"` | discriminator |
| `jar_id` | **không được có** | ✅ | string | `id` hũ từ `jar-summary`, không khớp theo tên. `create_jar` không gửi id — `pfm` tự sinh |
| `jar_name` | ✅ | ✅ | string, không rỗng | tên hũ (với `edit_jar`: tên sau khi sửa, giữ tên cũ nếu không đổi) |
| `allocation_amount` | ✅ | ✅ | number > 0 | thành `budgetLimit` (hạn mức VND/tháng) |
| `category_ids` | ✅ (được `[]`) | tuỳ chọn | string[] | category hũ phụ trách. Mỗi phần tử là 1 trong 10 category: `housing`, `utilities`, `subscriptions`, `insurance`, `dining`, `transport`, `shopping`, `groceries`, `entertainment`, `health`; không lặp. Với `edit_jar` là danh sách **đầy đủ** mới — bỏ field = không đổi |
| `reason` | ✅ | ✅ | string, không rỗng | căn cứ đề xuất, nêu số liệu thật — hiện cho khách xem trước khi xác nhận |

Quy tắc nghiệp vụ agent đã tôn trọng khi đề xuất (`pfm` vẫn phải kiểm lại khi ghi):

- **Trần hạn mức:** `allocation_amount` (tạo) hoặc phần tăng thêm (sửa) ≤ `allocationHeadroom` =
  `casaBalance − Σ budgetLimit`. `allocationHeadroom` ≤ 0 nghĩa là không còn chỗ đặt hạn mức mới → agent
  **không** trả `ui`, chỉ nói bằng lời. Giảm hoặc giữ nguyên hạn mức luôn được.
- **1 category chỉ thuộc đúng 1 hũ:** category đã thuộc hũ khác sẽ bị **chuyển sang** hũ tạo/sửa. Agent nêu rõ
  trong `reason` hũ nào mất category.
- Giảm hạn mức xuống dưới số đã chi (`spent`) làm `remaining` âm — nêu trong `reason`.
- Tên hũ mới trùng `label` một hũ đang có → agent không trả `ui`, hỏi lại khách.

## Luồng UI gợi ý

1. Nhận `ui.type === "create_jar"` hoặc `"edit_jar"` → hiện 1 form/card riêng dưới bong bóng chat, điền sẵn
   các field và `reason`. Với `edit_jar`, tra `jar_id` trong dữ liệu hũ của chính `pfm` để hiện tên/hạn mức
   **hiện tại** cạnh giá trị đề xuất (khách thấy "4.000.000đ → 4.500.000đ"). Không tìm thấy `jar_id` → **bỏ
   qua `ui`**, chỉ hiện `answer`.
2. Nếu category trong `category_ids` đang thuộc hũ khác, hiện rõ "sẽ chuyển từ hũ X" trên form.
3. Nút xác nhận ("Tạo hũ"/"Cập nhật hũ"): **khi bấm, `pfm` tự ghi qua API tạo/sửa hũ của chính nó**, không gọi
   lại endpoint nào của `server.py`. Ghi xong, làm mới dữ liệu hũ.
4. `ui` là `null` hoặc `ui.type` chưa hỗ trợ → chỉ hiện `answer`.

## Lưu ý về độ tin cậy

`server.py` **chỉ kiểm hình dạng** payload (đủ field, đúng kiểu, `allocation_amount` > 0, `category_ids`
hợp lệ và không lặp, `create_jar` không có `jar_id`, `edit_jar` có `jar_id`) và bỏ hẳn `ui` nếu sai — không bao
giờ để JSON thô lọt vào `answer`. Server **không** đối chiếu với dữ liệu thật của khách: `jar_id` có tồn tại
không, `allocation_amount` có vượt `allocationHeadroom` không là việc của `pfm`, luôn kiểm lại trước khi ghi
và bỏ đề xuất nếu sai (đề xuất chỉ là điền sẵn form cho khách xem lại, không phải lệnh).

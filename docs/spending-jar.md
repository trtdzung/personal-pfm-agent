# Hũ chi tiêu (`create_jar` / `edit_jar`) — hướng dẫn cho frontend

Tài liệu này mô tả 2 loại UI agent có thể trả ra qua field `ui` (cùng envelope với
`chart`/`transfer_form`, xem `docs/chart-visualization.md`, `docs/transfer-form.md`) — chỉ khác
`ui.type`. Loại thứ 3 về hũ, `rebalance_jars` (lấy tiền từ hũ khác để bù hũ thiếu), có tài liệu riêng:
[`docs/jar-rebalance.md`](./jar-rebalance.md).

> **Thay đổi contract (2026-09-21):** hũ không còn vai trò (không có hũ nào được bảo vệ khi bù tiền); danh mục là danh mục **của từng khách**, không phải 10 mục cố định.
>
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
| `category_ids` | ✅ (được `[]`) | tuỳ chọn | string[] | danh mục hũ phụ trách. Mỗi phần tử là `id` danh mục chi tiêu (`kind: "expense"`) **của khách** từ `GET /api/categories?cif=` — không phải danh sách cố định: 10 mặc định (`housing`, `utilities`, `subscriptions`, `insurance`, `dining`, `transport`, `shopping`, `groceries`, `entertainment`, `health`) cộng danh mục khách tự tạo (`c_<slug>`); không lặp. Với `edit_jar` là danh sách **đầy đủ** mới — bỏ field = không đổi |
| `reason` | ✅ | ✅ | string, không rỗng | căn cứ đề xuất, nêu số liệu thật — hiện cho khách xem trước khi xác nhận |

Quy tắc nghiệp vụ agent đã tôn trọng khi đề xuất (`pfm` vẫn phải kiểm lại khi ghi):

- **Trần hạn mức:** `allocation_amount` (tạo) hoặc phần tăng thêm (sửa) ≤ `allocationHeadroom` =
  `casaBalance − Σ budgetLimit`. `allocationHeadroom` ≤ 0 nghĩa là không còn chỗ đặt hạn mức mới → agent
  **không** trả `ui`, chỉ nói bằng lời. Giảm hoặc giữ nguyên hạn mức luôn được.
- **1 category chỉ thuộc đúng 1 hũ:** category đã thuộc hũ khác sẽ bị **chuyển sang** hũ tạo/sửa. Agent nêu rõ
  trong `reason` hũ nào mất category.
- Giảm hạn mức xuống dưới số đã chi (`spent`) làm `overLimit` = `true` và `remaining` có thể âm (hũ "cần bù") — nêu trong `reason`. Agent không nói "số dư âm" với khách (`pfm` không hiện số âm): nói "số dư 0, còn thiếu … chưa được bù".
- **Chỉ hũ có trong `jar-summary` của lượt đó mới sửa được.** Hũ vừa được đề xuất tạo ở lượt trước chưa được khách xác nhận nên chưa tồn tại; agent không bịa `id` (ví dụ `lien-thien` suy từ tên hũ) mà hỏi lại khách.
- Tên hũ mới trùng `label` một hũ đang có → agent không trả `ui`, hỏi lại khách.

## Chuyển danh mục giữa hai hũ

Khi khách muốn chuyển danh mục X từ hũ **A** sang hũ **B**, agent trả **một** `edit_jar` cho **hũ nhận B**, với
`category_ids` = **danh sách đầy đủ của B sau khi nhận** (danh mục B đang có cộng X). Server tự lấy X ra khỏi A vì 1 danh
mục chỉ thuộc 1 hũ. Agent **không** trả `edit_jar` cho hũ cho A với `category_ids` bỏ X: khi đó X không thuộc hũ nào và
`pfm` đưa nó về hũ "Khác", không sang B như khách muốn. Chỉ bỏ X khỏi 1 hũ (không gán cho hũ nào) khi khách nói rõ muốn
đưa X về "Khác". Chuyển **tiền** giữa hai hũ là form `rebalance_jars` ([`docs/jar-rebalance.md`](./jar-rebalance.md)).

Ví dụ — chuyển Giải trí từ Hưởng thụ sang Ăn uống (Ăn uống đang có `dining`, `groceries`, hạn mức giữ nguyên):

```json
{
  "type": "edit_jar",
  "jar_id": "food",
  "jar_name": "Ăn uống",
  "allocation_amount": 4000000,
  "category_ids": ["dining", "groceries", "entertainment"],
  "reason": "Chuyển danh mục Giải trí từ hũ Hưởng thụ sang hũ Ăn uống; hũ Hưởng thụ còn phụ trách Mua sắm, hạn mức giữ nguyên"
}
```

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

`server.py` kiểm 2 lớp và bỏ hẳn `ui` (chỉ còn `answer`) nếu sai — không bao giờ để JSON thô lọt vào `answer`:

1. **Hình dạng** (`text_utils.py`): đủ field, đúng kiểu, `allocation_amount` > 0, mỗi `category_ids` là id mặc định hoặc
   `c_<slug>` và không lặp, `create_jar` không có `jar_id`, `edit_jar` có `jar_id`.
2. **Id có thật** (`ui_guard.py`): `edit_jar` bị bỏ nếu `jar_id` không có trong `jar-summary` mà agent vừa đọc **ở lượt đó**
   (kể cả khi agent không đọc); `category_ids` bị bỏ nếu có id không nằm trong `GET /api/categories` (`kind: "expense"`) agent
   vừa đọc. Đọc từ lượt trước không tính — hũ có thể đã đổi hoặc chưa từng tồn tại.

Server **không** đối chiếu số tiền: `allocation_amount` có vượt `allocationHeadroom` không, tên hũ có trùng không là việc của
`pfm`, luôn kiểm lại trước khi ghi và bỏ đề xuất nếu sai (đề xuất chỉ là điền sẵn form cho khách xem lại, không phải lệnh).

# `create_jar` / `edit_jar` — tạo hũ, sửa hũ

Hai loại `ui` do skill `spending-jar` trả trong `POST /chat` (cùng envelope với `chart`/`transfer_form`, xem [`docs/api.md`](../api.md)).
Khái niệm `limit` / `balance` / `allocationHeadroom`, nguyên tắc "chỉ đề xuất" và các lớp kiểm: [`README.md`](./README.md).
Contract đầy đủ phía `pfm`: `backend_docs/pfm-read-api.md` (phần B).

> **Lịch sử contract:** 2026-09-24 không còn hũ tự sinh nào gom danh mục lẻ (danh mục không thuộc hũ nào là *chưa xếp hũ*); 2026-09-23 tách hạn mức khỏi
> số dư — `create_jar` **bắt buộc** `initial_balance`; 2026-09-21 hũ không còn vai trò, danh mục là của từng khách; 2026-09-20 `create_jar`
> thêm `category_ids`, `edit_jar` nhận `jar_id`. Payload thiếu field bắt buộc bị `server.py` bỏ (`ui = null`, chỉ còn `answer`).

## `create_jar`

```json
{
  "answer": "Chi Giải trí 3 tháng gần đây trung bình ~1.400.000đ/tháng, mình đề xuất hũ Giải trí hạn mức 1.500.000đ/tháng.\n\nMình nạp sẵn 1.500.000đ từ tiền chưa phân bổ vào hũ, bạn sửa được số này trên form rồi xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "create_jar",
    "jar_name": "Giải trí",
    "allocation_amount": 1500000,
    "initial_balance": 1500000,
    "category_ids": ["entertainment"],
    "reason": "Chi Giải trí 3 tháng gần nhất trung bình ~1.400.000đ/tháng; danh mục Giải trí chưa thuộc hũ nào nên được xếp vào hũ mới"
  }
}
```

| Field | Bắt buộc | Kiểu | Ghi chú |
|---|---|---|---|
| `type` | ✅ | `"create_jar"` | discriminator |
| `jar_name` | ✅ | string, không rỗng | tên hũ; trùng tên hũ đang có thì Agent không trả `ui`, hỏi lại |
| `allocation_amount` | ✅ | number > 0 | thành `limit` (hạn mức tháng); không bị giới hạn bởi `allocationHeadroom` |
| `initial_balance` | ✅ | số nguyên ≥ 0 | số dư ban đầu nạp vào hũ, `0` hợp lệ, phải ≤ `allocationHeadroom`. Thiếu, âm hoặc số lẻ → `ui = null` (không tự coi là 0) |
| `category_ids` | ✅ | string[] (được `[]`) | `id` danh mục chi tiêu (`kind: "expense"`) **của khách** từ `GET /api/categories?cif=`: 10 mặc định (`housing`, `utilities`, `subscriptions`, `insurance`, `dining`, `transport`, `shopping`, `groceries`, `entertainment`, `health`) cộng danh mục khách tự tạo (`c_<slug>`); không lặp |
| `reason` | ✅ | string, không rỗng | căn cứ đề xuất, nêu số thật, hiện cho khách xem |
| `jar_id` | **không được có** | — | `pfm` tự sinh id |

Cách Agent chọn `initial_balance`: khách nêu số tiền bỏ vào hũ → đúng số đó; không nêu → `min(hạn mức, tiền chưa phân bổ)`. Hết tiền chưa phân bổ
(`allocationHeadroom` ≤ 0 hoặc chưa biết) → **vẫn trả** `create_jar` với `initial_balance: 0` và nói rõ hũ chưa có tiền. Danh mục đang thuộc hũ khác sẽ
**chuyển sang** hũ mới (1 danh mục chỉ thuộc 1 hũ); `reason` nêu hũ nào mất danh mục.

## `edit_jar`

```json
{
  "answer": "Hũ Ăn uống tăng hạn mức từ 4.800.000đ lên 15.000.000đ/tháng. Hạn mức chỉ là kế hoạch chi, hũ không có thêm tiền.\n\nBạn xem lại rồi xác nhận nhé.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "edit_jar",
    "jar_id": "food",
    "jar_name": "Ăn uống",
    "allocation_amount": 15000000,
    "reason": "Khách yêu cầu tăng hạn mức hũ Ăn uống từ 4.800.000đ lên 15.000.000đ; hạn mức không cần chỗ trống nên vẫn đề xuất được"
  }
}
```

| Field | Bắt buộc | Kiểu | Ghi chú |
|---|---|---|---|
| `type` | ✅ | `"edit_jar"` | discriminator |
| `jar_id` | ✅ | string | `id` hũ **có trong `jar-summary` của chính lượt đó**, không khớp theo tên; hũ vừa đề xuất tạo mà khách chưa xác nhận thì chưa tồn tại (Agent không bịa id như `lien-thien`) |
| `jar_name` | ✅ | string, không rỗng | tên sau khi sửa (giữ tên cũ nếu không đổi) |
| `allocation_amount` | ✅ | number > 0 | `limit` mới. **Tăng hay giảm đều được**, không kiểm `allocationHeadroom`; không đổi `balance` |
| `category_ids` | tuỳ chọn | string[] | danh sách **đầy đủ** danh mục mới; bỏ field = không đổi |
| `reason` | ✅ | string, không rỗng | căn cứ đề xuất |

Giảm hạn mức xuống dưới số đã chi làm `overLimit` = `true` — nêu trong `reason`; số dư giữ nguyên.

## Chuyển danh mục giữa hai hũ

Khách muốn chuyển danh mục X từ hũ **A** sang hũ **B** → **một** `edit_jar` cho **hũ nhận B**, với `category_ids` = **danh sách đầy đủ của B sau khi nhận**
(danh mục B đang có cộng X). Server tự lấy X ra khỏi A vì 1 danh mục chỉ thuộc 1 hũ. Agent **không** trả `edit_jar` cho hũ cho A với `category_ids` bỏ X: khi đó
X chỉ là *chưa xếp hũ* chứ không sang B như khách muốn. Chỉ bỏ X khỏi 1 hũ (không gán cho hũ nào) khi khách nói rõ muốn để X chưa xếp hũ.

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

## Việc riêng của form này

- Agent **không** trả `ui` khi tên hũ mới trùng hũ đang có, hoặc hũ cần sửa không có trong `jar-summary` của lượt đó.
- Kiểm hình dạng (`text_utils.py`): `create_jar` có `initial_balance` số nguyên ≥ 0 và không có `jar_id`; `edit_jar` có `jar_id`; `category_ids` không lặp.
  Kiểm id (`ui_guard.py`): `jar_id` có trong `jar-summary` và mọi `category_ids` có trong `GET /api/categories` (`kind: "expense"`) của lượt đó.
- `pfm` kiểm lại khi ghi: `initial_balance` ≤ `allocationHeadroom`, tên hũ trùng.
- Frontend: card `edit_jar` tra `jar_id` trong dữ liệu hũ để hiện "4.000.000đ → 4.500.000đ" (không tìm thấy → bỏ `ui`); nếu danh mục trong `category_ids` đang thuộc hũ khác, hiện rõ "sẽ chuyển từ hũ X".
- Muốn hũ **có thêm tiền** không phải việc của form này: xem [`distribute-amount.md`](./distribute-amount.md) và [`rebalance-jars.md`](./rebalance-jars.md).

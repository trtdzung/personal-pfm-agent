# Hũ chi tiêu — Agent trả dữ liệu gì

Trang tổng hợp cho frontend/`pfm`: với các việc về hũ, Agent trả **những loại `ui` nào, khi nào, và ai kiểm gì**. Field chi tiết của từng
loại nằm ở tài liệu riêng (bảng cuối trang) — trang này không lặp lại chúng. Contract phía `pfm`: `backend_docs/pfm-read-api.md`.

## 1. Bốn loại `ui` về hũ

Mọi câu trả lời của `POST /chat` có dạng `{ "answer": string, "thread_id": string, "ui": object | null }`. Với hũ, `ui.type` là một trong:

| `ui.type` | Khi nào Agent trả | Skill chat | Endpoint không chat |
|---|---|---|---|
| `create_jar` | tạo hũ mới | skill `spending-jar` | — |
| `edit_jar` | đổi tên / hạn mức / danh mục của hũ đang có (kể cả chuyển danh mục giữa hai hũ) | skill `spending-jar` | — |
| `distribute_amount` | chia **một số tiền chưa phân bổ** vào 1 hoặc nhiều hũ | skill `distribute-amount` | `POST /jar-distribute` |
| `rebalance_jars` | chuyển **số dư từ 1 hũ sang 1 hoặc nhiều hũ khác** | skill `rebalance-jars` | `POST /jar-rebalance` |

Nguyên tắc chung:

- **Agent chỉ đề xuất, không ghi gì.** `ui` là dữ liệu để điền sẵn form; `pfm` ghi khi khách xem lại và bấm xác nhận. Vì vậy `answer`
  KHÔNG bao giờ nói "đã tạo", "đã sửa", "đã chuyển".
- **Mỗi lượt tối đa 1 `ui`.** Cần nhiều bước thì Agent làm từng bước, mỗi bước một lượt, và đọc lại số liệu sau mỗi lần khách xác nhận.
- Agent chỉ trả `id` và con số, không trả lại tên hũ; tên hiển thị tra từ dữ liệu hũ của chính `pfm`.
- Agent đọc số liệu hũ từ `GET /api/jar-summary` của `pfm` (tool `get_jar_summary`); số do engine của `pfm` tính, Agent không tự cộng giao dịch.
- Người đọc `answer` và `reason` là khách hàng: không có tên nội bộ (`pfm`, id hũ, tên field), không nói "số dư âm" — nói "hết số dư, còn thiếu … chưa được bù".

## 2. Ba con số cần phân biệt (từ 2026-09-23)

| Tên | Ý nghĩa |
|---|---|
| `limit` | **hạn mức tháng**: kế hoạch chi mỗi tháng, đặt lại mỗi tháng. Hạn mức không phải tiền nằm trong hũ. `null` = chưa đặt (không phải 0). `budgetLimit` là tên cũ, cùng giá trị |
| `balance` | **số dư hũ**: tiền còn trong hũ, cộng dồn qua các tháng, có thể âm ("cần bù"). `null` = hũ chưa có số dư (không phải 0). `remaining` là tên cũ, deprecated. `spendable` = max(0, `balance`) là phần hũ có thể cho đi |
| `allocationHeadroom` (= `unallocated`) | **tiền chưa phân bổ** ("Chờ phân bổ") = tiền trong tài khoản chưa nằm trong hũ nào. Là trần của `initial_balance` khi tạo hũ và là **nguồn duy nhất** của `distribute_amount`. **Không** phải trần của hạn mức |

Hệ quả:

- Tạo hay tăng/giảm **hạn mức** không cần chỗ trống và không đổi số dư. `overLimit` (đã chi vượt hạn mức) là trục khác với "cần bù" (`balance` < 0).
- Muốn hũ **có thêm tiền**: `distribute_amount` (từ tiền chưa phân bổ) hoặc `rebalance_jars` (từ hũ khác).
- Không còn hũ tự sinh nào gom danh mục lẻ: danh mục không thuộc hũ nào là **chưa xếp hũ**. Một danh mục chỉ thuộc đúng 1 hũ.
- `limit: null` vẫn có thể đi cùng `balance` khác `null` (và ngược lại); hai trục không suy ra nhau.

## 3. Khi nào `ui = null` (chỉ còn `answer`)

Agent **không** trả `ui` khi: đọc `jar-summary` lỗi hoặc số cần thiết là `null` (không đoán số); hũ khách nhắc không có trong kết quả (hỏi lại, có thể
bằng `clarify_options`); tên hũ mới trùng hũ đang có; tiền chưa phân bổ hoặc số dư hũ nguồn không đủ cho khoản khách muốn chuyển. Các
trường hợp riêng của từng form nằm ở tài liệu của form đó.

## 4. Ai kiểm gì

Sai lớp nào thì bỏ hẳn `ui`, giữ `answer`, và không bao giờ để JSON thô lọt vào `answer`:

| Lớp | Kiểm gì |
|---|---|
| `text_utils.py` (hình dạng) | đủ field, đúng kiểu, số hợp lệ, không lặp hũ, không có `"pool"` ở chỗ không được có, `reason` không rỗng |
| `ui_guard.py` (id có thật) | mọi id hũ trong `ui` phải có trong `jar-summary` mà Agent vừa đọc **ở lượt đó**; `category_ids` phải có trong `GET /api/categories` (`kind: "expense"`) vừa đọc. Đọc từ lượt trước không tính |
| `jar_checks.py` (số tiền, chỉ hai endpoint) | tổng không vượt số cần chuyển, không vượt nguồn (tiền chưa phân bổ hoặc `spendable` của hũ nguồn); xem [`endpoints.md`](./endpoints.md) |
| `pfm` (khi ghi) | **luôn kiểm lại với số thật** trước khi ghi; đề xuất không khớp thì bỏ, chỉ hiện `answer` |

Trong chat, `server.py` không đối chiếu số tiền: các quy tắc số tiền do skill dặn model và do `pfm` kiểm lại.

## 5. Luồng UI gợi ý

1. Nhận `ui.type` về hũ → hiện 1 form/card riêng dưới bong bóng chat, điền sẵn field và `reason`; tra `id` hũ trong dữ liệu của `pfm` để hiện tên và số **hiện tại** cạnh giá trị đề xuất.
2. Khách có thể sửa số trên form trước khi xác nhận (đặc biệt `initial_balance`, các khoản `amount`).
3. Nút xác nhận: **`pfm` tự ghi qua API của chính nó**, không gọi lại endpoint nào của `server.py`; ghi xong làm mới dữ liệu hũ (lượt sau Agent đọc lại số mới).
4. `ui` là `null` hoặc `ui.type` chưa hỗ trợ → chỉ hiện `answer`.
5. `GET /chat/history` trả lại `ui` của từng lượt cũ đúng như lúc gửi.

> ⚠️ **Cần `pfm` xác nhận:** frontend của `pfm` (`agent-api.ts`) hiện chỉ biết `chart`, `transfer_form`, `create_jar`, `edit_jar`, `rebalance_jars`
> (dạng cũ), `clarify_options` — **chưa có card cho `distribute_amount`**, và `rebalance_jars` đã đổi dạng (xem [`rebalance-jars.md`](./rebalance-jars.md)).
> Loại chưa hỗ trợ thì UI chỉ hiện `answer`. Gợi ý cho `distribute_amount`: tái dùng `AllocationSheet` ("Chia ngay").

## Tài liệu trong thư mục này

| File | Nội dung |
|---|---|
| [`create-edit-jar.md`](./create-edit-jar.md) | `create_jar`, `edit_jar`, chuyển danh mục giữa hai hũ |
| [`distribute-amount.md`](./distribute-amount.md) | `distribute_amount`: tiền chưa phân bổ vào hũ |
| [`rebalance-jars.md`](./rebalance-jars.md) | `rebalance_jars`: số dư từ 1 hũ sang 1 hoặc nhiều hũ khác |
| [`endpoints.md`](./endpoints.md) | `POST /jar-distribute`, `POST /jar-rebalance` |

Ngoài thư mục: [`docs/api.md`](../api.md) (envelope `POST /chat`, mọi loại `ui`). Skill của Agent: `skills/project/spending-jar/`,
`skills/project/distribute-amount/`, `skills/project/rebalance-jars/`.

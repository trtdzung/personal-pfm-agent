# API đọc dữ liệu PFM cho Agent (`GET /api/jars`, `GET /api/beneficiaries`)

Đây là 2 endpoint **do chính repo `pfm` (Next.js) expose**, khác hướng với
các tài liệu ở `agent_backend_docs/` (mô tả field `ui` mà Agent trả VỀ cho
`pfm` qua `/chat`) — ở đây `pfm` là bên serve dữ liệu, Agent là bên gọi.

Mục đích: cho Agent một cách đọc **dữ liệu thật, tại thời điểm gọi** (không
phải snapshot đầu phiên) — giải quyết đúng hạn chế đã ghi nhận ở
`agent_backend_docs/spending-jar.md`: *"chưa có tool/API đọc danh sách hũ
realtime"*.

## Base URL

Môi trường demo hiện tại (image build từ repo này, deploy trên VNG
AgentBase Runtime):

```
https://endpoint-6529c773-a2b3-4a42-b28a-6bcdced3ceff.agentbase-runtime.aiplatform.vngcloud.vn
```

Không có auth thật (cùng mô hình trust với mọi endpoint khác của prototype
này) — chỉ cần query param `cif`.

## ⚠️ Chỉ dùng 2 method GET dưới đây — không gọi POST/PUT/PATCH/DELETE

`/api/jars` và `/api/beneficiaries` còn có các method ghi (tạo/sửa/xoá hũ,
lưu người nhận mới) phục vụ UI của khách hàng, **nhưng Agent không được
gọi các method đó**: mọi hành động ghi dữ liệu thật phải qua con người xác
nhận trên UI `pfm` (đúng nguyên tắc "AI là facade không tự commit hành
động" — Agent chỉ đọc, không tự tạo/sửa hũ hay tự lưu người nhận thay
khách hàng). Coi 2 endpoint dưới đây là **read-only** đối với Agent.

## 1. `GET /api/jars?cif=`

Liệt kê toàn bộ hũ chi tiêu hiện có của khách hàng.

**Query param:** `cif` (bắt buộc) — id khách hàng, ví dụ `CIF_0001`.

**Response `200`** — object `JarConfig`:

```json
{
  "version": 3,
  "jars": [
    {
      "id": "essentials",
      "label": "Thiết yếu",
      "categoryIds": ["housing", "utilities", "insurance", "subscriptions"],
      "budgetLimit": 8000000,
      "actualAmount": 8000000
    },
    {
      "id": "savings",
      "label": "Tiết kiệm",
      "categoryIds": []
    }
  ]
}
```

Ví dụ trên là kết quả thật, gọi trực tiếp endpoint deploy ở trên với
`cif=CIF_0001` (đã rút gọn danh sách jars).

| Field | Kiểu | Ghi chú |
|---|---|---|
| `version` | number | luôn `3` hiện tại |
| `jars` | array | xem bảng dưới |
| `jars[].id` | string | id hũ, ví dụ `food`, `essentials` |
| `jars[].label` | string | tên hiển thị, ví dụ "Ăn uống" |
| `jars[].categoryIds` | string[] | danh mục chi tiêu thuộc hũ này (1 danh mục chỉ thuộc đúng 1 hũ) |
| `jars[].budgetLimit` | number, có thể vắng mặt | hạn mức/tháng đã đặt — vắng mặt (không phải `0`) nghĩa là "chưa đặt" |
| `jars[].actualAmount` | number, có thể vắng mặt | số dư thực tế trong hũ (dùng làm nguồn chuyển tiền) — vắng mặt nghĩa là "chưa có số dư" |
| `jars[].color` / `jars[].icon` | string, có thể vắng mặt | tuỳ chỉnh hiển thị, không mang ý nghĩa nghiệp vụ |

**Response `422`** khi thiếu `cif`: `{"error": "cif is required"}`.

## 2. `GET /api/beneficiaries?cif=`

Liệt kê toàn bộ tài khoản chuyển tiền đã lưu (người thụ hưởng) của khách
hàng.

**Query param:** `cif` (bắt buộc).

**Response `200`** — mảng `Beneficiary[]`:

```json
[
  {
    "id": "b_stable_lan",
    "name": "Nguyễn Thị Lan",
    "accountNumber": "19012345678901",
    "bankName": "MSB",
    "source": "mock"
  },
  {
    "id": "b_stable_binh",
    "name": "Trần Văn Bình",
    "accountNumber": "0071000123456",
    "bankName": "Vietcombank",
    "source": "mock"
  }
]
```

Ví dụ trên là kết quả thật, gọi trực tiếp endpoint deploy ở trên với
`cif=CIF_0001`.

| Field | Kiểu | Ghi chú |
|---|---|---|
| `id` | string | id bản ghi |
| `name` | string | tên hiển thị (tên chủ tài khoản, hoặc tên gợi nhớ do khách hàng tự đặt) |
| `accountNumber` | string | số tài khoản đầy đủ, **không mask** |
| `bankName` | string | ngân hàng thụ hưởng |
| `source` | `"msb"` \| `"self_reported"` \| `"estimated"` \| `"mock"` | nguồn gốc dữ liệu — `mock` là dữ liệu seed sẵn, `self_reported` là tài khoản khách hàng tự nhập tay (chưa được ngân hàng xác thực) |

**Response `422`** khi thiếu `cif`: `{"error": "cif is required"}`.

## Lưu ý khi Agent dùng dữ liệu này

- `cif` trong môi trường demo là id persona giả lập (`CIF_0001`/`CIF_0002`/
  `CIF_0003`), không phải CIF khách hàng MSB thật.
- Với một `cif` chưa từng có hũ nào, `GET /api/jars` **không trả lỗi** —
  server tự sinh 1 hũ gộp mặc định ("Khác") thay vì mảng rỗng.
- Dùng danh sách này để thay cho trường `jars` snapshot đầu phiên khi cần
  dữ liệu tại thời điểm hỏi (ví dụ agent muốn kiểm tra hũ nào đang tồn tại
  trước khi đề xuất `edit_jar`, hoặc kiểm tra người nhận đã lưu trước khi
  trả lời câu hỏi liên quan chuyển tiền) — vẫn tuân theo phạm vi cũ: đây là
  dữ liệu để agent **đọc và tham khảo**, không phải cơ sở để tự thực hiện
  hành động ghi.

## Category cho 1 lần chuyển khoản

`housing`, `utilities`, `subscriptions`, `insurance`, `dining`, `transport`,
`shopping`, `groceries`, `entertainment`, `health`.

## Kỳ vọng field `ui.type: "transfer_form"` cần trả về (để điền form mới)

Form chuyển tiền bên `pfm` (mục 3.1, `todo.md`) sắp hiện đủ: **tên tài
khoản, số tài khoản, ngân hàng, số tiền, nội dung, category** — cho khách
hàng chỉnh sửa trước khi bấm "Chuyển" để điều hướng sang màn chuyển tiền
thật với mọi field đã điền sẵn.

Phạm vi: chỉ chuyển cho người nhận **đã có trong danh sách đã lưu**
(`GET /api/beneficiaries`, mục 2 phía trên) — agent không tự bịa người nhận
mới. Agent **không cần trả tên/số tài khoản/ngân hàng** — chỉ cần trả đúng
`id` của bản ghi trong danh sách đó, `pfm` tự tra cứu phần còn lại từ chính
API của mình (tránh việc agent gõ sai/hallucinate số tài khoản):

```json
{
  "type": "transfer_form",
  "beneficiary_id": "b_stable_lan",
  "amount": 2000000,
  "note": "Chuyen tien an thang 9",
  "category": "dining"
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `beneficiary_id` | ✅ | phải khớp đúng 1 `id` trong `GET /api/beneficiaries?cif=` — sai/không tồn tại thì `pfm` bỏ qua, chỉ hiện `answer` |
| `amount` | ✅ | số tiền đề xuất, luôn dương |
| `note` | ✅ | nội dung chuyển khoản |
| `category` | ✅ | 1 trong 10 id ở mục "Category cho 1 lần chuyển khoản" phía trên |

`pfm` dùng `beneficiary_id` để lấy `name`/`accountNumber`/`bankName` thật từ
`GET /api/beneficiaries`, ghép với `amount`/`note`/`category` agent trả về,
rồi hiện đủ 6 field lên form (tên tài khoản, số tài khoản, ngân hàng, số
tiền, nội dung, category).

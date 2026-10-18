# API đọc dữ liệu PFM cho Agent + contract `ui` gợi ý form hũ

Tài liệu gồm 2 phần:

- **Phần A — endpoint `pfm` expose cho Agent đọc.** Với form hũ, Agent chỉ cần **1
  endpoint**: `GET /api/jar-summary` (thông tin từng hũ: hạn mức đã set, số dư hiện
  tại…). `pfm` là bên serve dữ liệu, Agent là bên gọi — khác hướng với
  `agent_backend_docs/` (mô tả field `ui` mà Agent trả VỀ cho `pfm` qua `/chat`).
- **Phần B — contract `ui` Agent trả ra** để gợi ý 3 form về hũ (`create_jar`,
  `edit_jar`, `rebalance_jars`) và form chuyển tiền (`transfer_form`).

**Phân vai:** Agent chỉ **đọc** thông tin hũ rồi **gợi ý form** (điền sẵn giá trị).
Việc **thực hiện thay đổi hũ luôn do repo `pfm` làm**, sau khi khách xem lại và
bấm xác nhận trên UI — Agent không gọi bất kỳ endpoint ghi nào.

## Base URL

```
https://endpoint-6529c773-a2b3-4a42-b28a-6bcdced3ceff.agentbase-runtime.aiplatform.vngcloud.vn
```

Không có auth thật (cùng mô hình trust với mọi endpoint khác của prototype này) —
chỉ cần query param `cif`. `cif` trong demo là id persona giả lập (`CIF_0001`…),
không phải CIF MSB thật.

> ⚠️ `GET /api/jar-summary` là endpoint **mới**: chỉ có sau khi build/deploy lại
> image từ repo `pfm`. Bản đang chạy ở URL trên có thể còn trả `404` cho đường dẫn này.

## ⚠️ Agent chỉ được gọi method GET

Các route của `pfm` còn có method ghi (tạo/sửa/xoá hũ, ghi giao dịch…) phục vụ UI
khách hàng. **Agent không được gọi** POST/PUT/PATCH/DELETE (đúng nguyên tắc "AI là
facade không tự commit hành động").

---

# Phần A — Endpoint đọc

## 1. `GET /api/jar-summary?cif=&month=`

Thông tin của **từng hũ** trong 1 tháng, do chính engine của `pfm` tính — số Agent
đọc được **giống hệt số khách thấy trên màn Tổng quan / Ngân sách**, Agent không cần
tự cộng giao dịch.

**Query param:** `cif` (bắt buộc); `month` (tuỳ chọn, dạng `YYYY-MM`, mặc định là
tháng hiện tại của demo). Thiếu `cif` hoặc `month` sai định dạng → `422`.

**Response `200`** — ví dụ thật, `cif=CIF_0001`, `month=2026-09` (rút gọn):

```json
{
  "month": "2026-09",
  "casaBalance": 18000000,
  "unallocated": 13044000,
  "allocationHeadroom": 1000000,
  "jars": [
    {
      "id": "food",
      "label": "Ăn uống",
      "categoryIds": ["dining", "groceries"],
      "role": "spending",
      "budgetLimit": 4000000,
      "spent": 2187000,
      "remaining": 1813000,
      "spendable": 1813000,
      "overLimit": false
    },
    {
      "id": "essentials",
      "label": "Thiết yếu",
      "categoryIds": ["housing", "utilities", "insurance", "subscriptions"],
      "role": "essential",
      "budgetLimit": 8000000,
      "spent": 7949000,
      "remaining": 51000,
      "spendable": 51000,
      "overLimit": false
    },
    { "id": "savings", "label": "Tiết kiệm", "categoryIds": [], "role": "buffer", "budgetLimit": null, "spent": 0, "remaining": null, "spendable": null, "overLimit": false }
  ]
}
```

**Mỗi hũ (`jars[]`):**

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | string | id hũ — Agent trả lại đúng id này trong `edit_jar` / `rebalance_jars` |
| `label` | string | tên hiển thị |
| `categoryIds` | string[] | category chi tiêu thuộc hũ (**1 category chỉ thuộc đúng 1 hũ**) |
| `role` | `"buffer"` \| `"spending"` \| `"essential"` \| `"goal"`, có thể vắng mặt | vai trò khi hũ cho tiền (xem B4); vắng mặt = coi như `spending` |
| `budgetLimit` | number \| `null` | **hạn mức đã set** (VND/tháng). `null` = chưa đặt — không phải `0` |
| `spent` | number | đã chi trong `month` (chi tiêu ròng, đã trừ hoàn tiền) |
| `remaining` | number \| `null` | **số dư hiện tại** (trục SỐ DƯ) = `budgetLimit − spent + (đã nhận − đã cho từ bù giữa hũ trong tháng)`. Có thể **âm** = hũ đã tiêu quá số dư và chưa được bù ("cần bù"). `null` nếu chưa đặt hạn mức. **Giao diện `pfm` không bao giờ hiện số dư âm** — hiện 0 (xem "Cách nói với khách") |
| `spendable` | number \| `null` | `max(0, remaining)` — số tối đa hũ có thể **cho đi** hoặc chi thêm. `null` = chưa có số dư |
| `overLimit` | boolean | `spent > budgetLimit` (trục KẾ HOẠCH: khách đã chi vượt hạn mức mình đặt). **Không đổi khi bù giữa hũ** — hũ đã được bù đủ vẫn có `overLimit: true`. **Khác** với `remaining < 0` |

**Toàn cục:**

| Field | Ý nghĩa |
|---|---|
| `casaBalance` | tiền thật trong tài khoản thanh toán (`null` nếu không có tài khoản thanh toán) |
| `unallocated` | **"Chưa phân bổ"** = `casaBalance − Σ spendable`. Là nguồn `"pool"` khi chia tiền giữa hũ (B4). Có thể âm |
| `allocationHeadroom` | **"Chờ phân bổ"** = `casaBalance − Σ budgetLimit`. Là phần hạn mức **còn được đặt thêm**; đây đúng là trần server kiểm khi tạo/sửa hũ (B2, B3). **Âm = tổng hạn mức đã vượt CASA** → không tăng thêm hạn mức được (ví dụ trên: +1.000.000, còn chỗ đặt thêm tối đa 1.000.000) |

**Về "số dư hiện tại" của hũ:** đây là số **tính ra**, không có trường nào để ghi
trực tiếp. Muốn tăng số dư hũ có 2 cách, tương ứng 2 form khác nhau:
1. **Tăng hạn mức** (`edit_jar`) — cần `allocationHeadroom` còn chỗ; có hiệu lực các tháng sau.
2. **Lấy từ hũ/pool khác** (`rebalance_jars`) — không đổi hạn mức, chỉ điều chỉnh
   số dư **trong tháng hiện tại**.

**Hai trục độc lập** (đừng nhầm):
- **Số dư** (`remaining`, `spendable`): còn bao nhiêu để chi. Bù giữa hũ (B4) chỉ dịch chuyển trục này.
- **Kế hoạch** (`budgetLimit`, `overLimit`): khách có chi vượt hạn mức mình đặt không. Bù giữa hũ **không** sửa `budgetLimit` và **không** xoá `overLimit`.
Hũ **"cần bù"** = `remaining < 0` (không phải `overLimit`).

**Cách nói với khách:** không nói "số dư âm". Hũ có `remaining < 0` thì nói "số dư 0, còn
thiếu {−remaining} chưa được bù"; nói "đã vượt hạn mức {spent − budgetLimit}" **riêng** khi
`overLimit` là `true`.

Các số tiền `null` nghĩa là **chưa biết** — đừng coi là 0. `500`
`{"error":"jar summary unavailable"}` là lỗi đọc dữ liệu, không phải "hũ trống".

## 2. Endpoint khác (tham khảo — không bắt buộc cho form hũ)

| Endpoint | Dùng để |
|---|---|
| `GET /api/jars?cif=` | cấu hình hũ thô (`id`, `label`, `categoryIds`, `budgetLimit`, `role`) — `jar-summary` đã bao gồm |
| `GET /api/beneficiaries?cif=` | danh sách người nhận đã lưu — cần cho `transfer_form` (B1) |
| `GET /api/accounts?cif=` | tài khoản; CASA = Σ `availableBalance` của `type: "current"` |
| `GET /api/transactions?cif=&from=&to=` | giao dịch ngân hàng (chỉ đọc) |
| `GET /api/manual-transactions?cif=` | giao dịch tự khai báo + các dòng bù giữa hũ (`categoryId: "dieu-chinh-hu"`) |
| `GET /api/corrections?cif=` | nhãn danh mục do khách sửa đè lên giao dịch |
| `GET /api/categories?cif=` | danh mục chi tiêu **của khách** (khách có thể tự thêm/đổi tên/lưu trữ) — cần `cif` |

Tất cả đều cần `cif` và trả `422` khi thiếu.

`GET /api/beneficiaries?cif=` trả `Beneficiary[]`:

```json
[{ "id": "b_stable_lan", "name": "Nguyễn Thị Lan", "accountNumber": "19012345678901", "bankName": "MSB", "source": "mock" }]
```

`id` là thứ Agent trả lại trong `transfer_form`; `accountNumber` đầy đủ, không mask;
`source` = `self_reported` nghĩa là khách tự nhập, chưa được ngân hàng xác thực.

**Category hợp lệ** (dùng trong `transfer_form`, `create_jar`, `edit_jar`): **không phải
danh sách cố định.** Mỗi khách có bộ danh mục riêng gồm 10 danh mục mặc định
(`housing`, `utilities`, `subscriptions`, `insurance`, `dining`, `transport`, `shopping`,
`groceries`, `entertainment`, `health`) **cộng** danh mục khách tự tạo (id dạng
`c_<slug>`). Agent phải đọc `GET /api/categories?cif=` — mỗi phần tử `{ id, label, kind,
fixed }` — và chỉ dùng `id` có **`kind: "expense"`** (bỏ `kind: "transfer"`, đó là mục hệ
thống). Danh mục đã lưu trữ chỉ hiện khi thêm `&includeArchived=1` (kèm `archived: true`)
— **không gợi ý** danh mục đã lưu trữ.

---

# Phần B — Contract `ui` Agent trả ra

Khung chung: Agent trả `answer` (text) + `ui` (object có `type`). `pfm` **validate
lại toàn bộ** với dữ liệu thật; `ui` sai/thiếu/không khớp thì `pfm` **bỏ qua, chỉ
hiện `answer`**. Nguyên tắc: **Agent chỉ trả `id` và con số đề xuất** (không trả lại
tên/số tài khoản), điền sẵn form cho khách xem lại; `pfm` mới thực hiện thay đổi,
và chỉ khi khách bấm xác nhận.

> Trạng thái phía `pfm`: `transfer_form` đã làm xong; `create_jar`, `edit_jar`,
> `rebalance_jars` **chưa làm** — đây là contract `pfm` sẽ nhận (todo Feature 4).

## B0. Khi nào trả form nào (đọc phần này trước)

**Mỗi lượt trả lời chỉ có tối đa 1 `ui`.** Nếu cần nhiều bước, làm từng bước, mỗi bước
một lượt. Sau khi khách xác nhận 1 thay đổi, số trong `jar-summary` đã đổi — **gọi lại
`jar-summary`** trước khi gợi ý bước tiếp, đừng dùng số cũ.

| Khách nói / tình huống | Trả `ui` | Ghi chú |
|---|---|---|
| Muốn tạo hũ mới | `create_jar` | chỉ khi `allocation_amount ≤ allocationHeadroom`; không thì không trả `ui` (xem "Không trả `ui`") |
| Đổi tên / hạn mức / category của hũ | `edit_jar` | dùng `jar_id` từ `jar-summary` |
| "Thêm tiền cho hũ X" **lâu dài** (mỗi tháng) | `edit_jar` tăng hạn mức | cần `allocationHeadroom` còn đủ; không đủ thì đề xuất giảm hạn mức hũ khác (`edit_jar`) hoặc bù tạm (`rebalance_jars`) |
| Hũ X **cần bù** (`remaining < 0`), hoặc không đủ số dư cho khoản khách định chi, hoặc khách muốn chia lại tiền **trong tháng này** | `rebalance_jars` | target phải có `budgetLimit`; hũ `null` thì đề xuất `edit_jar` đặt hạn mức trước |
| Chuyển tiền cho người đã lưu | `transfer_form` | độc lập với các form hũ |
| Chỉ hỏi số dư / hạn mức / đã chi | không có `ui` (hoặc `chart` nếu phù hợp) | trả lời bằng số từ `jar-summary` |

**Nhiều hũ cùng cần bù:** chỉ xử lý **1 hũ mỗi lượt** — hũ có `remaining` âm nhất
trước; nêu trong `answer` còn hũ nào cần bù, làm ở lượt sau (sau khi gọi lại `jar-summary`,
vì tiền "Chưa phân bổ" có thể đã được dùng hết).

**Không trả `ui`, chỉ nói trong `answer`** khi:
- `jar-summary` lỗi (`500`) hoặc số cần thiết là `null` — **không đoán số**;
- `jar_id` khách nhắc không có trong `jar-summary` → hỏi lại khách hũ nào;
- tên hũ mới trùng `label` một hũ đang có (`create_jar`);
- `allocationHeadroom` không đủ cho `create_jar`, hoặc không tăng được hạn mức;
- các nguồn cộng lại vẫn không đủ để bù, hoặc chỉ hũ `goal` mới đủ (B4).

**Nội dung `answer` đi kèm `ui`:** 1–3 câu, nêu con số chính lấy từ `jar-summary` (vd
"hạn mức 4.000.000đ → 4.500.000đ", "hũ Ăn uống thiếu 1.500.000đ, lấy từ …"; không nói "số dư âm", xem "Cách nói với khách") và nhắc khách
xem lại rồi xác nhận. **Không nói "đã tạo / đã sửa / đã chuyển"** — Agent không thực hiện
gì cả, `pfm` chỉ làm khi khách bấm xác nhận.

## B1. `transfer_form` — chuyển tiền cho người đã lưu

```json
{ "type": "transfer_form", "beneficiary_id": "b_stable_lan", "amount": 2000000, "note": "Chuyen tien an thang 9", "category": "dining" }
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `beneficiary_id` | ✅ | khớp đúng 1 `id` của `GET /api/beneficiaries` — Agent không tự bịa người nhận |
| `amount` | ✅ | > 0 |
| `note` | ✅ | nội dung chuyển khoản |
| `category` | ✅ | `id` category chi tiêu (`kind: "expense"`) của khách, từ `GET /api/categories?cif=` |

Form chuyển tiền **không liên quan** đến chia tiền giữa các hũ (B4): không có field
hũ nguồn, khách chọn nguồn tiền trên màn chuyển tiền của `pfm`.

## B2. `create_jar` — Form 1: tạo hũ mới

```json
{
  "type": "create_jar",
  "jar_name": "Cà phê & giải trí",
  "allocation_amount": 800000,
  "category_ids": ["entertainment"],
  "reason": "Chi Giải trí 3 tháng gần nhất trung bình ~750.000đ/tháng"
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `jar_name` | ✅ | tên hũ, không rỗng |
| `allocation_amount` | ✅ | > 0 — thành `budgetLimit` (hạn mức) |
| `category_ids` | ✅ | category hũ phụ trách (được phép `[]`); mỗi phần tử là `id` category chi tiêu (`kind: "expense"`) của khách từ `GET /api/categories?cif=`, sai thì server `422` |
| `reason` | ✅ | căn cứ đề xuất, hiện cho khách xem — nêu số liệu thật |

(Ví dụ minh hoạ: khớp `allocationHeadroom` = 1.000.000 của dữ liệu mẫu ở trên, nên
`allocation_amount` 800.000 là hợp lệ; nếu đề xuất 1.500.000 thì phải bỏ `ui`.)

Agent **không gửi `id`** (`pfm` tự sinh). Khi gợi ý phải tôn trọng:
- **`allocation_amount ≤ allocationHeadroom`** (từ `jar-summary`). `allocationHeadroom`
  ≤ 0 nghĩa là không còn chỗ đặt hạn mức mới → **không gợi ý `create_jar`**, hãy gợi
  ý lấy bớt hạn mức từ hũ khác (`edit_jar` giảm hạn mức) hoặc nói rõ trong `answer`.
- **1 category chỉ thuộc 1 hũ.** Category đã thuộc hũ khác (xem `categoryIds` từng hũ)
  sẽ bị **chuyển sang hũ mới** khi tạo — nêu rõ trong `reason` hũ nào sẽ mất chúng.

## B3. `edit_jar` — Form 2: điều chỉnh hũ

Sửa tên, hạn mức, category của 1 hũ đã có.

```json
{
  "type": "edit_jar",
  "jar_id": "lifestyle",
  "jar_name": "Hưởng thụ",
  "allocation_amount": 2000000,
  "category_ids": ["entertainment", "shopping"],
  "reason": "Tháng này hũ Hưởng thụ mới chi 1.204.000đ trên hạn mức 2.500.000đ; giảm 500.000đ để có chỗ cho hũ khác"
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `jar_id` | ✅ | **`id` hũ từ `jar-summary`** (không khớp theo tên) — không tồn tại thì `pfm` bỏ qua |
| `jar_name` | ✅ | tên hũ sau khi sửa (giữ tên cũ nếu không đổi) |
| `allocation_amount` | ✅ | `budgetLimit` mới, > 0 |
| `category_ids` | tuỳ chọn | **danh sách đầy đủ** category mới của hũ; bỏ field = không đổi. Category lấy từ hũ khác sẽ bị chuyển sang hũ này |
| `reason` | ✅ | căn cứ đề xuất |

- **Tăng hạn mức:** phần tăng thêm (`allocation_amount` − `budgetLimit` hiện tại) phải
  **≤ `allocationHeadroom`**, nếu không server `422`. **Giảm hoặc giữ nguyên** luôn được.
- Đổi `budgetLimit` làm `remaining` đổi đúng bằng chênh lệch. Giảm xuống dưới số đã
  chi (`spent`) thì `overLimit` thành `true` và `remaining` có thể âm ("cần bù") — nói rõ trong `reason`.
- Hũ chưa có `budgetLimit` (`null`): đặt lần đầu cũng tính là tăng.

## B4. `rebalance_jars` — Form 3: điều chỉnh số dư giữa các hũ

Dùng khi **(a)** khách định chi một khoản lớn hơn số dư hũ (`spendable` không đủ), hoặc
**(b)** hũ **cần bù**: khách đã tiêu quá số dư (`remaining < 0`). Agent đề xuất
**lấy phần thiếu từ hũ/pool nào**. Không đổi `budgetLimit`, không chuyển tiền thật —
chỉ điều chỉnh `remaining` giữa các hũ **trong tháng hiện tại**. Form này **độc lập**
với `transfer_form` (B1).

```json
{
  "type": "rebalance_jars",
  "target_jar_id": "food",
  "shortfall": 1500000,
  "moves": [
    { "from_jar_id": "pool", "amount": 1000000 },
    { "from_jar_id": "lifestyle", "amount": 500000 }
  ],
  "reason": "Hũ Ăn uống thiếu 1.500.000đ; lấy 1.000.000đ từ tiền chưa phân bổ và 500.000đ từ hũ Hưởng thụ"
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `target_jar_id` | ✅ | hũ đang thiếu (id thật, **phải có `budgetLimit`**) |
| `shortfall` | ✅ | VND còn thiếu, > 0. Trường hợp (a): `số tiền định chi − spendable` của hũ đích. Trường hợp (b): `−remaining` của hũ đích |
| `moves` | ✅ | ≥ 1 phần tử `{ from_jar_id, amount }` |
| `moves[].from_jar_id` | ✅ | id hũ cho tiền, hoặc `"pool"` = `unallocated` ("Chưa phân bổ") |
| `moves[].amount` | ✅ | VND lấy từ nguồn đó, > 0 |
| `reason` | ✅ | giải thích vì sao chọn các nguồn này |

**Quy tắc cứng** (`pfm` kiểm lại; vi phạm bất kỳ điều nào → bỏ cả `ui`, chỉ hiện `answer`):
1. `Σ moves[].amount` **đúng bằng** `shortfall`, và `shortfall` khớp số `pfm` tự tính.
2. `from_jar_id` ≠ `target_jar_id`, không lặp nguồn, không bịa id.
3. Mỗi hũ cho chỉ cho tối đa **`spendable`** của nó (không đẩy hũ cho xuống âm). Hũ có
   `spendable: null` (chưa đặt hạn mức) **không được cho**.
4. Nguồn `"pool"` chỉ cho tối đa `max(0, unallocated)`. (Chú ý: khác `allocationHeadroom`.)
5. **Hũ `role: "goal"` không được có trong `moves`** (được bảo vệ). Nếu chỉ hũ `goal`
   mới đủ bù, Agent nói trong `answer` để khách tự quyết, **không** đưa vào `ui`.

**Thứ tự ưu tiên nên theo** (cùng thứ tự engine `pfm` dùng; là gợi ý, không phải quy
tắc cứng): `pool` → hũ `buffer` (dự phòng/tiết kiệm) → hũ `spending` (vắng `role` =
`spending`) → hũ `essential` (thiết yếu, cuối cùng). Trong cùng nhóm, hũ có
`spendable` lớn nhất lấy trước. Mỗi nguồn lấy `min(spendable, phần còn thiếu)` rồi
dừng khi đủ. Tổng mọi nguồn (trừ `goal`) vẫn không đủ → **không trả `ui`**, nói rõ
trong `answer` là không đủ.

**Khi khách xác nhận**, `pfm` (không phải Agent) ghi mỗi `moves[]` một bản ghi bù giữa
hũ; số dư hai hũ tự cập nhật, còn `spent` và `budgetLimit` không đổi. Hiệu lực trong
tháng hiện tại — sang tháng sau `remaining` tính lại từ `budgetLimit`.

**Ví dụ số** (minh hoạ; số của hũ lấy từ dữ liệu `jar-summary` ở trên, riêng
`unallocated` **giả định chỉ còn 1.000.000** — dữ liệu mẫu thật đang 13.044.000, khi đó
"Chưa phân bổ" một mình đủ bù 1.500.000 và `moves` chỉ có 1 phần tử `pool`). Ăn uống
`remaining` 1.813.000. Khách định chi 3.313.000 từ hũ này → `shortfall` = 3.313.000 −
1.813.000 = 1.500.000. Lấy 1.000.000 từ "Chưa phân bổ" (giả định), phần còn lại 500.000 từ
Hưởng thụ (`spendable` 1.296.000, hũ `spending` lớn nhất) → `moves` như JSON trên. Sau khi
áp dụng và chi: Ăn uống `remaining` = 4.000.000 − (2.187.000 + 3.313.000) + 1.500.000 = 0
(hết tiền nhưng **không âm**), còn `overLimit` vẫn `true` vì `spent` 5.500.000 > hạn mức
4.000.000 — bù giữa hũ không xoá việc khách đã chi vượt kế hoạch.

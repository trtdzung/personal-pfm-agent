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

**Trạng thái (đối chiếu với repo và bản deploy ngày 2026-09-21):** `GET /api/jar-summary`
đã có trong repo và đã chạy trên URL trên (`200`; thiếu `cif` hoặc `month` sai → `422`).
Bản deploy đã bỏ `role` của hũ (hũ không còn vai trò/hũ mục tiêu, xem B4).

**Agent gọi đúng URL này** (`PFM_BASE_URL` trong `tools/customer_data_tools.py` của repo
Agent): tool `get_jar_summary(month)` ↔ `GET /api/jar-summary`, tool `query_beneficiaries` ↔
`GET /api/beneficiaries`. Vì Agent đọc **bản deploy**, hũ/danh mục tạo ở một DB khác (vd
`pfm` chạy local) **không hiện với Agent** — UI và Agent phải trỏ cùng một bản `pfm` thì
`jar_id` Agent trả ra mới khớp hũ trên UI.

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

> ⚠️ **Thay đổi phá vỡ tương thích (2026-09-23):** response này **không còn field
> `casaBalance`** — đã tách sang endpoint riêng `GET /api/account-summary?cif=` (mục 2).
> Code Agent đang đọc `summary.get("casaBalance")` từ `jar-summary`
> (`tools/customer_data_tools.py`, hàm `render_jar_summary`) sẽ nhận `None`/thiếu field
> thay vì số thật — không lỗi, nhưng model sẽ nghĩ CASA "chưa biết". Agent team cần gọi
> thêm `GET /api/account-summary?cif=` để lấy lại số này.

**Query param:** `cif` (bắt buộc); `month` (tuỳ chọn, dạng `YYYY-MM`, mặc định là
tháng hiện tại của demo). Thiếu `cif` hoặc `month` sai định dạng → `422`.

**Response `200`** — ví dụ thật, `cif=CIF_0001`, `month=2026-09` (rút gọn):

```json
{
  "month": "2026-09",
  "unallocated": 13044000,
  "allocationHeadroom": 1000000,
  "jars": [
    {
      "id": "food",
      "label": "Ăn uống",
      "categoryIds": ["dining", "groceries"],
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
      "budgetLimit": 8000000,
      "spent": 7949000,
      "remaining": 51000,
      "spendable": 51000,
      "overLimit": false
    },
    { "id": "savings", "label": "Tiết kiệm", "categoryIds": [], "budgetLimit": null, "spent": 0, "remaining": null, "spendable": null, "overLimit": false }
  ]
}
```

**Mỗi hũ (`jars[]`):**

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | string | id hũ — Agent trả lại đúng id này trong `edit_jar` / `rebalance_jars` |
| `label` | string | tên hiển thị |
| `categoryIds` | string[] | category chi tiêu thuộc hũ (**1 category chỉ thuộc đúng 1 hũ**) |
| `budgetLimit` | number \| `null` | **hạn mức đã set** (VND/tháng). `null` = chưa đặt — không phải `0` |
| `spent` | number | đã chi trong `month` (chi tiêu ròng, đã trừ hoàn tiền) |
| `remaining` | number \| `null` | **số dư hiện tại** (trục SỐ DƯ) = `budgetLimit − spent + (đã nhận − đã cho từ bù giữa hũ trong tháng)`. Có thể **âm** = hũ đã tiêu quá số dư và chưa được bù ("cần bù"). `null` nếu chưa đặt hạn mức. **Giao diện `pfm` không bao giờ hiện số dư âm** — hiện 0 (xem "Cách nói với khách") |
| `spendable` | number \| `null` | `max(0, remaining)` — số tối đa hũ có thể **cho đi** hoặc chi thêm. `null` = chưa có số dư |
| `overLimit` | boolean | `spent > budgetLimit` (trục KẾ HOẠCH: khách đã chi vượt hạn mức mình đặt). **Không đổi khi bù giữa hũ** — hũ đã được bù đủ vẫn có `overLimit: true`. **Khác** với `remaining < 0` |

**Toàn cục:**

| Field | Ý nghĩa |
|---|---|
| `unallocated` | **"Chưa phân bổ"** = CASA − Σ `spendable`. Là nguồn `"pool"` khi chia tiền giữa hũ (B4). Có thể âm |
| `allocationHeadroom` | **"Chờ phân bổ"** = CASA − Σ `budgetLimit`. Là phần hạn mức **còn được đặt thêm**; đây đúng là trần server kiểm khi tạo/sửa hũ (B2, B3). **Âm = tổng hạn mức đã vượt CASA** → không tăng thêm hạn mức được (ví dụ trên: +1.000.000, còn chỗ đặt thêm tối đa 1.000.000) |

Cả hai đều tính từ CASA (tiền thật trong tài khoản thanh toán) nội bộ — muốn đọc riêng số
CASA, gọi `GET /api/account-summary?cif=` (mục 2). `unallocated`/`allocationHeadroom` vẫn
`null` khi khách không có tài khoản thanh toán, dù `casaBalance` không còn nằm trong response này.

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

Agent hiện thực sự gọi `jar-summary` (Phần 1), `categories` và `beneficiaries` dưới đây
(`tools/customer_data_tools.py`) — **cần gọi thêm `account-summary`** để lấy lại
`casaBalance` (xem cảnh báo đầu Phần 1). Bảng này bớt các endpoint đọc dữ liệu thô mà
Agent không tự gọi (`/api/jars`, `/api/accounts`, `/api/transactions`,
`/api/manual-transactions`, `/api/corrections`) — `jar-summary` đã gộp sẵn các con số cần
cho form hũ, và `/api/transactions-full` dưới đây đã gộp sẵn 3 endpoint giao dịch thô đó
cho trường hợp cần liệt kê từng giao dịch.

| Endpoint | Dùng để |
|---|---|
| `GET /api/beneficiaries?cif=` | danh sách người nhận đã lưu — cần cho `transfer_form` (B1) |
| `GET /api/categories?cif=` | danh mục chi tiêu **của khách** (khách có thể tự thêm/đổi tên/lưu trữ) — cần `cif` |
| `GET /api/account-summary?cif=` | `{ casaBalance: number \| null }` — số dư tài khoản thanh toán, **không kèm hũ**. **Thay cho `casaBalance` đã bỏ khỏi `jar-summary`** — Agent cần gọi endpoint này để có lại số CASA |
| `GET /api/transactions-full?cif=&from=&to=` | **toàn bộ giao dịch** (ngân hàng + tự khai báo) với `categoryId` **đã gộp corrections** — xem chi tiết ngay dưới; **chưa được Agent gọi**, thêm sẵn cho nhu cầu liệt kê giao dịch sau này |

Cả 4 đều cần `cif` và trả `422` khi thiếu.

`GET /api/transactions-full?cif=&from=&to=` trả `(Transaction & { hidden: boolean })[]`,
mới nhất trước — gộp sẵn `/api/transactions` + `/api/manual-transactions` rồi áp
`/api/corrections` đè lên `categoryId`, đúng logic `jar-summary` dùng để tính `spent`. Dùng
endpoint này khi cần liệt kê **từng giao dịch** kèm category đúng như khách đang thấy trên
app (ví dụ trả lời "tháng này tôi chi gì ở Ăn uống"); `jar-summary` chỉ có số tổng theo hũ,
không có danh sách. `from`/`to` là khoảng ISO đóng hai đầu, cùng quy ước `/api/transactions`.
Giao dịch bị khách ẩn khỏi báo cáo **vẫn có trong danh sách**, chỉ đánh dấu `hidden: true`
(khác `jar-summary`, nơi các dòng này bị loại khỏi số tổng) — bỏ qua các dòng `hidden: true`
nếu muốn khớp đúng số `jar-summary` đã tính.

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

> Trạng thái phía `pfm`: cả 4 loại (`transfer_form`, `create_jar`, `edit_jar`, `rebalance_jars`)
> đã có card trên UI (màn Chat và ô kết quả của Voice tab). Mỗi card tự kiểm lại với số liệu thật
> trước khi cho khách bấm xác nhận; đề xuất không còn khớp thì hiện "không còn khớp số liệu" và
> không có nút áp dụng.

## B0. Khi nào trả form nào (đọc phần này trước)

**Mỗi lượt trả lời chỉ có tối đa 1 `ui`.** Nếu cần nhiều bước, làm từng bước, mỗi bước
một lượt. Sau khi khách xác nhận 1 thay đổi, số trong `jar-summary` đã đổi — **gọi lại
`jar-summary`** trước khi gợi ý bước tiếp, đừng dùng số cũ.

| Khách nói / tình huống | Trả `ui` | Ghi chú |
|---|---|---|
| Muốn tạo hũ mới | `create_jar` | chỉ khi `allocation_amount ≤ allocationHeadroom`; không thì không trả `ui` (xem "Không trả `ui`") |
| Đổi tên / hạn mức / category của hũ | `edit_jar` | dùng `jar_id` từ `jar-summary` |
| **Chuyển danh mục** từ hũ A sang hũ B | `edit_jar` cho **hũ nhận B** | xem "Chuyển danh mục giữa hai hũ" ở B3 — **không** sửa hũ cho A |
| "Thêm tiền cho hũ X" **lâu dài** (mỗi tháng) | `edit_jar` tăng hạn mức | cần `allocationHeadroom` còn đủ; không đủ thì đề xuất giảm hạn mức hũ khác (`edit_jar`) hoặc bù tạm (`rebalance_jars`) |
| Hũ X **cần bù** (`remaining < 0`), hoặc không đủ số dư cho khoản khách định chi, hoặc khách muốn chia lại tiền **trong tháng này** | `rebalance_jars` | target phải có `budgetLimit`; hũ `null` thì đề xuất `edit_jar` đặt hạn mức trước |
| Chuyển tiền cho người đã lưu | `transfer_form` | độc lập với các form hũ |
| Chỉ hỏi số dư / hạn mức / đã chi | không có `ui` (hoặc `chart` nếu phù hợp) | trả lời bằng số từ `jar-summary` |

**Nhiều hũ cùng cần bù:** chỉ xử lý **1 hũ mỗi lượt** — hũ có `remaining` âm nhất
trước; nêu trong `answer` còn hũ nào cần bù, làm ở lượt sau (sau khi gọi lại `jar-summary`,
vì tiền "Chưa phân bổ" có thể đã được dùng hết).

**Không trả `ui`, chỉ nói trong `answer`** khi:
- `jar-summary` lỗi (`500`) hoặc số cần thiết là `null` — **không đoán số**;
- `jar_id` khách nhắc không có trong `jar-summary` → hỏi lại khách hũ nào. Kể cả hũ vừa được
  **đề xuất tạo** ở lượt trước: chưa được khách xác nhận thì chưa tồn tại — chỉ hũ có trong
  `jar-summary` **của lượt này** mới được sửa/bù. **Không bao giờ bịa `id`** (vd `"lien-thien"`
  suy từ tên hũ);
- tên hũ mới trùng `label` một hũ đang có (`create_jar`);
- `allocationHeadroom` không đủ cho `create_jar`, hoặc không tăng được hạn mức;
- các nguồn cộng lại vẫn không đủ để bù (B4).

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
- **`category_ids` của `create_jar` chỉ được gồm danh mục "chưa xếp hũ".** Một danh mục là
  chưa xếp khi **không hũ nào** giữ nó, hoặc chỉ hũ **"Khác"** (`id: "khac"`) giữ nó — suy ra từ
  `categoryIds` của từng hũ trong `jar-summary` so với danh sách `GET /api/categories?cif=`.
  Form tạo hũ trên `pfm` **chỉ cho chọn trong các danh mục chưa xếp** và **bỏ** danh mục đang
  thuộc hũ khác khỏi đề xuất (kèm dòng "… đang thuộc hũ X nên không chọn được"). Muốn lấy danh
  mục từ hũ khác: tạo hũ trước (không kèm danh mục đó), rồi ở lượt sau trả `edit_jar` cho hũ
  vừa tạo với `category_ids` đầy đủ (xem "Chuyển danh mục giữa hai hũ" ở B3).

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
| `jar_id` | ✅ | **`id` hũ sao chép nguyên văn từ `jar-summary`** (không khớp theo tên, không tự suy từ tên hũ) — không tồn tại thì `pfm` bỏ qua, chỉ hiện `answer` |
| `jar_name` | ✅ | tên hũ sau khi sửa (giữ tên cũ nếu không đổi) |
| `allocation_amount` | ✅ | `budgetLimit` mới, > 0 |
| `category_ids` | tuỳ chọn | **danh sách đầy đủ** category mới của hũ; bỏ field = không đổi. Category lấy từ hũ khác sẽ bị chuyển sang hũ này |
| `reason` | ✅ | căn cứ đề xuất |

- **Tăng hạn mức:** phần tăng thêm (`allocation_amount` − `budgetLimit` hiện tại) phải
  **≤ `allocationHeadroom`**, nếu không server `422`. **Giảm hoặc giữ nguyên** luôn được.
- Đổi `budgetLimit` làm `remaining` đổi đúng bằng chênh lệch. Giảm xuống dưới số đã
  chi (`spent`) thì `overLimit` thành `true` và `remaining` có thể âm ("cần bù") — nói rõ trong `reason`.
- Hũ chưa có `budgetLimit` (`null`): đặt lần đầu cũng tính là tăng.

### Chuyển danh mục giữa hai hũ (chỉ là `edit_jar`, không phải `rebalance_jars`)

Khi khách muốn chuyển danh mục X từ hũ **A** sang hũ **B**, Agent trả **một** `edit_jar`
cho **hũ nhận B**, với `category_ids` = **danh sách đầy đủ của B sau khi nhận** (danh mục B
đang có + X). Server tự lấy X ra khỏi A vì 1 danh mục chỉ thuộc 1 hũ.

**Không** trả `edit_jar` cho hũ cho A với `category_ids` bỏ X: khi đó X không thuộc hũ nào và
server đưa nó về hũ **"Khác"**, không sang B như khách yêu cầu. Chỉ bỏ X khỏi một hũ (không
gán cho hũ nào) khi khách nói rõ muốn đưa X về "Khác".

Ví dụ (`CIF_0003`: chuyển Giải trí từ Hưởng thụ sang Ăn uống; Ăn uống đang có `dining`,
`groceries`, hạn mức 12.800.000đ giữ nguyên):

```json
{
  "type": "edit_jar",
  "jar_id": "food",
  "jar_name": "Ăn uống",
  "allocation_amount": 12800000,
  "category_ids": ["dining", "groceries", "entertainment"],
  "reason": "Chuyển danh mục Giải trí từ hũ Hưởng thụ sang hũ Ăn uống; hũ Hưởng thụ còn phụ trách Mua sắm, hạn mức giữ nguyên"
}
```

`answer` nên nói rõ hũ nào mất danh mục và hạn mức không đổi. Chuyển **tiền** giữa hai hũ mới
dùng `rebalance_jars` (B4).

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

**Thứ tự ưu tiên nên theo** (cùng thứ tự engine `pfm` dùng; là gợi ý, không phải quy
tắc cứng): `pool` trước, sau đó các hũ còn lại theo `spendable` giảm dần (hũ nhiều
tiền nhất lấy trước). Không có hũ nào được bảo vệ — hũ không có vai trò. Mỗi nguồn lấy
`min(spendable, phần còn thiếu)` rồi dừng khi đủ. Tổng mọi nguồn vẫn không đủ →
**không trả `ui`**, nói rõ trong `answer` là không đủ.

**Khi khách xác nhận**, `pfm` (không phải Agent) ghi mỗi `moves[]` một bản ghi bù giữa
hũ; số dư hai hũ tự cập nhật, còn `spent` và `budgetLimit` không đổi. Hiệu lực trong
tháng hiện tại — sang tháng sau `remaining` tính lại từ `budgetLimit`.

**Ví dụ số** (minh hoạ; số của hũ lấy từ dữ liệu `jar-summary` ở trên, riêng
`unallocated` **giả định chỉ còn 1.000.000** — dữ liệu mẫu thật đang 13.044.000, khi đó
"Chưa phân bổ" một mình đủ bù 1.500.000 và `moves` chỉ có 1 phần tử `pool`). Ăn uống
`remaining` 1.813.000. Khách định chi 3.313.000 từ hũ này → `shortfall` = 3.313.000 −
1.813.000 = 1.500.000. Lấy 1.000.000 từ "Chưa phân bổ" (giả định), phần còn lại 500.000 từ
Hưởng thụ (`spendable` 1.296.000) → `moves` như JSON trên. Sau khi
áp dụng và chi: Ăn uống `remaining` = 4.000.000 − (2.187.000 + 3.313.000) + 1.500.000 = 0
(hết tiền nhưng **không âm**), còn `overLimit` vẫn `true` vì `spent` 5.500.000 > hạn mức
4.000.000 — bù giữa hũ không xoá việc khách đã chi vượt kế hoạch.

### Dùng trong luồng Chuyển tiền (khi bấm "Tiếp tục" mà hũ nguồn không đủ)

Không phải form mới — vẫn là `rebalance_jars` ở trên, nhưng **không đi qua chat**: `pfm`
gọi endpoint riêng của Agent `POST /jar-rebalance` (chế độ `cover`, không thread, không nhớ
gì; xem `docs/jar-rebalance-endpoint.md` bên repo Agent) qua proxy
`POST /api/agent/jar-rebalance`:

```json
{ "user_id": "CIF_0001", "mode": "cover", "target_jar_id": "food", "spend_amount": 14000000 }
```

Ở màn Chuyển tiền, khi khách chọn một hũ làm nguồn, nhập số tiền lớn hơn `spendable` của
hũ đó rồi bấm "Tiếp tục", `pfm` mở popup "Hũ chưa đủ tiền" (phần thiếu do engine tính).
"Chưa phân bổ" luôn được lấy trước: nếu pool đủ bù hết phần thiếu thì cách rót của engine
(chỉ pool) chính là gợi ý và **không gọi Agent**. Chỉ khi phần thiếu **vượt quá pool**, `pfm`
gọi endpoint trên với `spend_amount` = số khách nhập để Agent chia phần còn lại từ các hũ khác. Agent tự tính `shortfall` và trả
`rebalance_jars` (~21 s, đã đo), nên popup hiện ngay cách rót của engine, ghi nhãn
"Cách rót tạm tính" và dòng "M-Your đang phân tích…", rồi thay bằng đề xuất của Agent +
`reason` khi về. Khi khách bấm "Đồng ý rót", `pfm` **kiểm lại** đề xuất với số hiện tại (các
quy tắc cứng 1–4 ở trên, `shortfall` lấy theo engine) — không khớp / không có `ui` / lỗi /
quá 60 s → dùng cách rót của engine. Lúc xác nhận chuyển tiền, `pfm` kiểm lại lần nữa với
số mới nhất trước khi ghi các bản ghi bù (ghi với `origin: "manual"`). Nguồn "Chưa phân
bổ" (pool) **không** hỏi Agent, vì `target_jar_id` phải là một hũ.

**Lưu ý thứ tự nguồn:** endpoint này luôn ép "pool trước, rồi hũ nhiều tiền nhất". Khi
"Chưa phân bổ" đủ bù thì đề xuất chỉ có `pool` (đã đo: CIF_0001, Ăn uống chi 14.000.000đ →
12.187.000đ từ pool). Nếu sản phẩm muốn gợi ý **chia giữa các hũ** thay vì pool, cần Agent
thêm tuỳ chọn cho `cover` (ví dụ `exclude_pool`/`prefer: "jars"`) — `pfm` chưa có cách nào
ép điều đó qua endpoint hiện tại.

---

# Phần C — Kỳ vọng từ Agent (đã kiểm với agent thật, 2026-09-21)

Agent trả `answer` + tối đa 1 khối `ui` (trong repo Agent là khối ```` ```ui-json ````, `server.py`
tách ra thành field `ui`). Phân vai kiểm tra:

| Ai | Kiểm gì | Nếu sai |
|---|---|---|
| **Agent** (`server.py`, `text_utils.py`) | chỉ **hình dạng**: đủ field, đúng kiểu; `create_jar` **không** có `jar_id`; `edit_jar` có `jar_id`; `category_ids` không lặp; `rebalance_jars`: `target_jar_id` ≠ `"pool"`, mỗi nguồn ≠ đích và không lặp, mỗi `amount` > 0, **Σ `moves` = `shortfall`** | bỏ `ui` (`ui = null`), chỉ còn `answer` |
| **`pfm`** | đối chiếu với số thật: `jar_id`/nguồn có tồn tại; hạn mức vượt `allocationHeadroom`; tên hũ trùng; mỗi nguồn ≤ `spendable`; "pool" ≤ `unallocated`; `shortfall` khớp số thiếu thật của hũ âm | bỏ đề xuất, chỉ hiện `answer` |

## C1. Kịch bản → kết quả kỳ vọng

Gọi thật `POST /chat` (persona `CIF_0001` trừ khi ghi khác); "OK" = `ui` đúng loại, qua cả kiểm
tra hình dạng lẫn các quy tắc cứng đối chiếu với `jar-summary` thật.

| Khách nói | Kỳ vọng | Kết quả |
|---|---|---|
| Tạo hũ Du lịch 800 nghìn, chưa gắn danh mục | `create_jar` `allocation_amount: 800000`, `category_ids: []` (≤ `allocationHeadroom` 1.000.000) | OK |
| Tạo hũ Giải trí 800 nghìn với danh mục Giải trí (Giải trí đang thuộc hũ Hưởng thụ) | `create_jar` **không** kèm `entertainment` (danh mục đã xếp hũ); `answer` nói rõ và gợi ý thêm danh mục ở bước sửa hũ | Agent hiện vẫn đưa `entertainment` vào (C2 mục 6) — `pfm` sẽ bỏ nó |
| Giảm hạn mức hũ Hưởng thụ xuống 2 triệu | `edit_jar` `jar_id: "lifestyle"`, `allocation_amount: 2000000` | OK |
| Tăng hạn mức hũ Ăn uống lên 4,2 triệu | `edit_jar` `jar_id: "food"` (tăng 200.000đ ≤ headroom 1.000.000) | OK |
| Tăng hạn mức hũ Ăn uống lên 6 triệu | **không có `ui`** (tăng 2.000.000đ > headroom 1.000.000); `answer` nêu lý do | OK |
| Đổi hạn mức hũ "Học tập" (không tồn tại) | **không có `ui`**, liệt kê các hũ đang có, hỏi lại | OK |
| Hũ Ăn uống còn bao nhiêu? | **không có `ui`**; `answer` = 1.813.000đ (hạn mức 4.000.000đ, đã chi 2.187.000đ) | OK |
| Chuyển 500 nghìn cho Trần Văn Bình tiền cà phê | `transfer_form` `beneficiary_id: "b_stable_binh"`, `category: "dining"` | OK |
| Định chi 16 triệu từ hũ Ăn uống, thiếu thì chia từ hũ khác | `rebalance_jars` `target_jar_id: "food"`, `shortfall: 14187000`, Σ `moves` = 14.187.000 | OK (xem C2 về thứ tự) |
| `CIF_0002` — Hũ Thiết yếu hết tiền, chia bù giúp | `rebalance_jars` `target_jar_id: "essentials"`, `shortfall: 2389000` (= −`remaining`), `moves: [pool 2389000]` | OK |
| `CIF_0002` — Các hũ đang âm, bù giúp | `rebalance_jars` cho **1 hũ** (Thiết yếu, âm nhiều nhất), `answer` nói còn Hưởng thụ (âm 1.002.000đ) để lượt sau | OK |
| `CIF_0002` — Tạo hũ Du lịch 2 triệu (headroom 880.000) | **không có `ui`** (vượt phần được đặt thêm) | OK |
| `CIF_0003` — Định chi 90 triệu từ hũ Ăn uống | **không có `ui`** (tổng mọi nguồn khác ~49,5 triệu < 81,9 triệu thiếu) | OK |

## C2. Điểm Agent hiện chưa đúng kỳ vọng

Đã gặp khi kiểm; là việc bên repo Agent, `pfm` chỉ chặn được hậu quả.

1. **Chuyển danh mục trả sai hũ.** "Chuyển Giải trí từ Hưởng thụ sang Ăn uống" → Agent trả
   `edit_jar` cho **Hưởng thụ** với `category_ids: ["shopping"]`; đúng phải là `edit_jar` cho
   **Ăn uống** với `["dining","groceries","entertainment"]` (xem B3). Làm theo payload Agent thì
   Giải trí rơi về hũ "Khác".
2. **Bịa `jar_id`.** Hũ chỉ có trong hội thoại (vừa đề xuất tạo, hoặc chỉ có ở DB local) →
   Agent trả `edit_jar` với `jar_id: "lien-thien"` (suy từ tên). `pfm` báo "Không tìm thấy hũ
   này". Kỳ vọng: không có `ui`, hỏi lại khách. Đề nghị `server.py` bỏ `ui` nếu `jar_id` không
   nằm trong kết quả `get_jar_summary` vừa đọc.
3. **Whitelist danh mục cố định 10 mục.** `_VALID_EXPENSE_CATEGORIES` (`text_utils.py`) chỉ
   chứa 10 danh mục mặc định, nên `create_jar`/`edit_jar`/`transfer_form` có danh mục khách tự
   tạo (`c_<slug>`) bị Agent bỏ `ui`. Kỳ vọng: whitelist lấy từ `GET /api/categories?cif=`
   (mục `kind: "expense"`, chưa lưu trữ).
4. **Skill `jar-rebalance` còn nhắc `role`.** Repo Agent vẫn mô tả thứ tự `buffer → spending →
   essential` và hũ `goal` được bảo vệ; `pfm` đã bỏ vai trò hũ. Kỳ vọng: `pool` trước, sau đó các
   hũ còn lại theo `spendable` **giảm dần**; không hũ nào được bảo vệ.
5. **Thứ tự lấy tiền lệch** (hệ quả của mục 4): định chi 16 triệu, Agent lấy pool 13.044.000 →
   Di chuyển 796.000 (nhỏ hơn) → Hưởng thụ 347.000; theo thứ tự kỳ vọng phải là pool 13.044.000
   → Hưởng thụ 1.143.000 (đủ một mình). Không vi phạm quy tắc cứng nên `pfm` vẫn nhận.
6. **`create_jar` đưa vào danh mục đã xếp hũ.** Agent còn viết `reason` kiểu "danh mục X đang
   thuộc hũ Y sẽ chuyển sang hũ mới" và để X trong `category_ids`. Form tạo hũ của `pfm` chỉ cho
   chọn danh mục chưa xếp nên sẽ bỏ X; kỳ vọng Agent không đưa X vào `create_jar` (skill
   `spending-jar` cần cập nhật), và nếu khách muốn X thì làm `edit_jar` sau khi tạo hũ.

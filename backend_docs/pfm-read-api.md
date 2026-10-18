# API đọc dữ liệu PFM cho Agent + contract `ui` gợi ý form hũ

Tài liệu gồm 2 phần:

- **Phần A — endpoint `pfm` expose cho Agent đọc.** Với form hũ, Agent chỉ cần **1
  endpoint**: `GET /api/jar-summary` (thông tin từng hũ: hạn mức đã set, số dư hiện
  tại…). `pfm` là bên serve dữ liệu, Agent là bên gọi — khác hướng với
  `agent_backend_docs/` (mô tả field `ui` mà Agent trả VỀ cho `pfm` qua `/chat`).
- **Phần B — contract `ui` Agent trả ra** để gợi ý 4 form về hũ (`create_jar`,
  `edit_jar`, `distribute_amount`, `rebalance_jars`), form chuyển tiền (`transfer_form`) và câu hỏi
  bằng nút bấm (`clarify_options`).

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
Bản deploy đã bỏ `role` của hũ (hũ không còn vai trò/hũ mục tiêu).

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

> ⚠️ **Thay đổi (2026-09-23, tách HẠN MỨC khỏi SỐ DƯ):** mỗi hũ có thêm `limit` (hạn mức
> tháng; `budgetLimit` giữ làm alias) và `balance` (**số dư chạy**, cộng dồn qua các tháng:
> nạp − rút − đã chi + nhận/cho từ bù giữa hũ, tính từ lúc hũ có số dư). `remaining` **vẫn trả
> nhưng đã DEPRECATED — bằng đúng `balance`**, không còn là `budgetLimit − spent`. Hạn mức
> **không phải tiền**: đổi hạn mức không đổi số dư. `allocationHeadroom` giờ **bằng
> `unallocated`** (Chờ phân bổ = CASA − Σ `spendable`) — là trần cho **số dư** nạp vào hũ,
> không còn là trần cho hạn mức.

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
      "limit": 4000000,
      "budgetLimit": 4000000,
      "spent": 2187000,
      "balance": 1813000,
      "remaining": 1813000,
      "spendable": 1813000,
      "overLimit": false
    },
    {
      "id": "essentials",
      "label": "Thiết yếu",
      "categoryIds": ["housing", "utilities", "insurance", "subscriptions"],
      "limit": 8000000,
      "budgetLimit": 8000000,
      "spent": 7949000,
      "balance": 51000,
      "remaining": 51000,
      "spendable": 51000,
      "overLimit": false
    },
    { "id": "savings", "label": "Tiết kiệm", "categoryIds": [], "limit": null, "budgetLimit": null, "spent": 0, "balance": null, "remaining": null, "spendable": null, "overLimit": false }
  ]
}
```

**Mỗi hũ (`jars[]`):**

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | string | id hũ — Agent trả lại đúng id này trong `edit_jar` / `rebalance_jars` |
| `label` | string | tên hiển thị |
| `categoryIds` | string[] | category chi tiêu thuộc hũ (**1 category thuộc tối đa 1 hũ**; category không nằm trong `categoryIds` của hũ nào là "chưa xếp hũ") |
| `limit` | number \| `null` | **hạn mức tháng** (kế hoạch chi, VND/tháng, đặt lại mỗi tháng). `null` = chưa đặt — không phải `0`. **Không phải tiền trong hũ** |
| `budgetLimit` | number \| `null` | alias của `limit` (giữ cho code cũ) |
| `spent` | number | đã chi trong `month` (chi tiêu ròng, đã trừ hoàn tiền) |
| `balance` | number \| `null` | **số dư hũ** (trục SỐ DƯ, cộng dồn qua tháng) = Σ nạp − Σ rút − đã chi + (đã nhận − đã cho từ bù giữa hũ), tính từ lúc hũ có số dư. Có thể **âm** = hũ đã tiêu quá số dư và chưa được bù ("cần bù"). `null` = **chưa có số dư** (hũ chưa nạp, hoặc tháng xem trước khi hũ có số dư) — không phải `0`. Không phụ thuộc `limit` |
| `remaining` | number \| `null` | **DEPRECATED** — alias của `balance` (cùng giá trị). Code mới đọc `balance` |
| `spendable` | number \| `null` | `max(0, balance)` — số tối đa hũ có thể **cho đi** hoặc chi thêm. `null` = chưa có số dư |
| `overLimit` | boolean | `spent > limit` (trục HẠN MỨC: khách đã chi vượt hạn mức mình đặt). **Không đổi khi bù giữa hũ** — hũ đã được bù đủ vẫn có `overLimit: true`. **Khác** với `balance < 0`: hũ có thể vượt hạn mức mà vẫn còn số dư (đã nạp nhiều hơn hạn mức) |

**Toàn cục:**

| Field | Ý nghĩa |
|---|---|
| `unallocated` | **"Chưa phân bổ"** = CASA − Σ `spendable`. Là nguồn duy nhất của `distribute_amount` (B5). Có thể âm |
| `allocationHeadroom` | **"Chờ phân bổ"** — từ 2026-09-23 **bằng `unallocated`** (CASA − Σ `spendable`). Là số tiền **còn nạp được vào hũ**: trần cho `initial_balance` của `create_jar` (B2); server kiểm lại khi tạo hũ (`422` kèm `overBy`). **Không** còn là trần cho hạn mức — tăng hạn mức không cần chỗ trống |

Cả hai đều tính từ CASA (tiền thật trong tài khoản thanh toán) nội bộ — muốn đọc riêng số
CASA, gọi `GET /api/account-summary?cif=` (mục 2). `unallocated`/`allocationHeadroom` vẫn
`null` khi khách không có tài khoản thanh toán, dù `casaBalance` không còn nằm trong response này.

**Về số dư của hũ:** đây là số **tính ra**, Agent không ghi trực tiếp. Số dư chỉ đổi khi:
1. **Khách tự nạp/rút** trong `pfm` (Cài đặt → Hũ & danh mục, hoặc "Chia tiền vào hũ") — không
   có form Agent cho việc này;
2. **Khách tự chuyển số dư giữa 2 hũ** ngay ở Tổng quan (bấm vào thẻ hũ tháng hiện tại →
   `JarTransferSheet`, thêm 2026-09-23) — cùng cơ chế `dieu-chinh-hu` với `rebalance_jars` (B4),
   nhưng khách tự làm, **không qua Agent**. Nghĩa là số dư 2 hũ có thể đã đổi giữa các lượt hỏi mà
   Agent không đề xuất gì — luôn đọc lại `jar-summary` mới nhất trước khi gợi ý (B0);
3. **Tạo hũ** kèm `initial_balance` (`create_jar`, B2);
4. **Chia tiền chưa phân bổ vào hũ** (`distribute_amount`, B5) hoặc **chuyển số dư từ hũ khác** (`rebalance_jars`, B4).

**Tăng hạn mức (`edit_jar`) KHÔNG tăng số dư** — hạn mức chỉ là kế hoạch chi mỗi tháng.

**Hai trục độc lập** (đừng nhầm):
- **Số dư** (`balance`, `spendable`): tiền còn trong hũ, cộng dồn qua tháng. Chia tiền (B5) và chuyển giữa hũ (B4) chỉ dịch chuyển trục này.
- **Hạn mức** (`limit`, `overLimit`): khách có chi vượt kế hoạch tháng này không; đặt lại mỗi tháng. Bù giữa hũ **không** sửa `limit` và **không** xoá `overLimit`.
Hũ **"cần bù"** = `balance < 0` (không phải `overLimit`).

**Cách nói với khách:** không nói "số dư âm". Hũ có `balance < 0` thì nói "hết số dư, còn
thiếu {−balance} chưa được bù"; nói "đã vượt hạn mức {spent − limit}" **riêng** khi
`overLimit` là `true`. `balance: null` thì nói "hũ chưa có số dư", không nói "0".

> ⚠️ **Thay đổi (2026-09-24, không đổi shape response):**
> - **Không còn hũ "Khác" tự sinh trong `jars[]`.** Trước đây danh mục không hũ nào giữ được server
>   chữa vào 1 hũ `id: "khac"`; nay xoá hũ là xoá hẳn và danh mục của hũ đó (cũng như danh mục mới
>   tạo) đơn giản **không thuộc hũ nào** — chỉ có hũ nào thật sự có trong DB mới xuất hiện. "Danh
>   mục chưa xếp" = danh mục `kind: "expense"` từ `GET /api/categories` mà **không** nằm trong
>   `categoryIds` của hũ nào ở `jar-summary`. Chi tiêu của chúng vẫn tính vào tổng chi (báo cáo
>   nhóm "Chưa xếp hũ") nhưng không thuộc ngân sách hũ nào.
> - **Hũ có thể `limit: null` mà `balance` là số (thường `0`).** Tạo hũ giờ cho phép không đặt hạn
>   mức (vd "Tiết kiệm"): `limit: null` (chưa đặt hạn mức) + số dư ban đầu tường minh `0` →
>   `balance: 0`, `spendable: 0` — khác `balance: null` (hũ chưa từng được nạp). Đừng suy `limit`
>   `null` ⇒ `balance` `null`.

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

> Trạng thái phía `pfm`: cả 6 loại (`transfer_form`, `create_jar`, `edit_jar`, `distribute_amount`,
> `rebalance_jars`, `clarify_options` — loại cuối xem B6) đã có card trên UI
> (màn Chat và ô kết quả của Voice tab). Mỗi card tự kiểm lại với số liệu thật
> trước khi cho khách bấm xác nhận; đề xuất không còn khớp thì hiện "không còn khớp số liệu" và
> không có nút áp dụng.

## B0. Khi nào trả form nào (đọc phần này trước)

**Mỗi lượt trả lời chỉ có tối đa 1 `ui`.** Nếu cần nhiều bước, làm từng bước, mỗi bước
một lượt. Sau khi khách xác nhận 1 thay đổi, số trong `jar-summary` đã đổi — **gọi lại
`jar-summary`** trước khi gợi ý bước tiếp, đừng dùng số cũ.

| Khách nói / tình huống | Trả `ui` | Ghi chú |
|---|---|---|
| Muốn tạo hũ mới | `create_jar` | **bắt buộc** `initial_balance` ≥ 0 và ≤ `allocationHeadroom`; hạn mức `allocation_amount` không bị giới hạn bởi headroom |
| Đổi tên / hạn mức / category của hũ | `edit_jar` | dùng `jar_id` từ `jar-summary` |
| **Chuyển danh mục** từ hũ A sang hũ B | `edit_jar` cho **hũ nhận B** | xem "Chuyển danh mục giữa hai hũ" ở B3 — **không** sửa hũ cho A |
| "Cho hũ X chi nhiều hơn mỗi tháng" | `edit_jar` tăng hạn mức | không cần headroom; nói rõ tăng hạn mức **không** thêm tiền vào hũ |
| Khách muốn đưa tiền vào hũ mà **không nêu hũ nguồn** ("chuyển 300k vào hũ Tiết kiệm", "bù giúp tôi" cho hũ hết số dư) | `distribute_amount` | tiền lấy từ `unallocated`; Σ ≤ `max(0, unallocated)`; hũ chưa có số dư vẫn nhận được |
| Khách chuyển **từ một hũ** sang hũ khác ("chuyển 500k từ Ăn uống sang Di chuyển"), hoặc hũ cần bù / định chi quá số dư mà tiền chưa phân bổ không đủ | `rebalance_jars` | **1 hũ nguồn**, Σ ≤ `spendable` của nó; hũ nguồn phải có `balance` ≠ `null`; **hũ nhận** phải có `balance` ≠ `null` (chưa có thì dùng `distribute_amount` hoặc nhắc nạp tiền trong `pfm`, không trả `ui`) |
| Chuyển tiền cho người đã lưu | `transfer_form` | độc lập với các form hũ |
| Không chắc khách muốn gì (≥ 2 phương án hợp lý ngang nhau) | `clarify_options` | xem "Hỏi lại bằng nút bấm" bên dưới — hỏi bằng nút bấm thay vì đoán |
| Chỉ hỏi số dư / hạn mức / đã chi | không có `ui` (hoặc `chart` nếu phù hợp) | trả lời bằng số từ `jar-summary` |

**Nhiều hũ cùng cần bù / nhiều hũ nguồn:** chỉ xử lý **1 form mỗi lượt** — hũ có `balance` âm
nhất (hoặc hũ nguồn đầu tiên khách nêu) trước; nêu trong `answer` còn hũ nào, làm ở lượt sau (sau
khi gọi lại `jar-summary`, vì tiền "Chưa phân bổ" có thể đã được dùng hết).

**Không trả `ui`, chỉ nói trong `answer`** khi:
- `jar-summary` lỗi (`500`) hoặc số cần thiết là `null` — **không đoán số**;
- `jar_id` khách nhắc không có trong `jar-summary` → hỏi lại khách hũ nào. Kể cả hũ vừa được
  **đề xuất tạo** ở lượt trước: chưa được khách xác nhận thì chưa tồn tại — chỉ hũ có trong
  `jar-summary` **của lượt này** mới được sửa/bù. **Không bao giờ bịa `id`** (vd `"lien-thien"`
  suy từ tên hũ);
- tên hũ mới trùng `label` một hũ đang có (`create_jar`);
- khách muốn tạo hũ với số dư lớn hơn `allocationHeadroom` (đề xuất số dư nhỏ hơn, kể cả `0`, thì vẫn trả `create_jar` được);
- tiền chưa phân bổ (`distribute_amount`) hoặc `spendable` của hũ nguồn (`rebalance_jars`) không đủ cho khoản khách muốn chuyển (nói còn bao nhiêu).

**Nội dung `answer` đi kèm `ui`:** 1–3 câu, nêu con số chính lấy từ `jar-summary` (vd
"hạn mức 4.000.000đ → 4.500.000đ", "hũ Ăn uống thiếu 1.500.000đ, lấy từ …"; không nói "số dư âm", xem "Cách nói với khách") và nhắc khách
xem lại rồi xác nhận. **Không nói "đã tạo / đã sửa / đã chuyển"** — Agent không thực hiện
gì cả, `pfm` chỉ làm khi khách bấm xác nhận.

**Câu nói từ Voice tab được chuyển thẳng cho Agent.** `pfm` không còn lọc câu nói bằng
`interpretation` của dịch vụ STT (bộ nhận ý định đó từng khớp nhầm tên hũ, ví dụ "chuyển 500k
tiền ăn uống" bị hiểu là chuyển giữa hai hũ). Mọi câu nhận dạng được đều tới `POST /chat` như một
tin nhắn thường, nên Agent phải tự phân biệt **chuyển cho người** ("Chuyển cho Lan 500k, nội dung
tiền ăn uống" → `transfer_form`) với **chuyển giữa hũ** (`rebalance_jars`); khi câu nói chưa đủ
để biết hũ nguồn/hũ đích thì hỏi lại bằng `clarify_options` — `pfm` chỉ hỏi khi Agent cũng thấy thiếu.

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

Form chuyển tiền **không liên quan** đến chia tiền giữa các hũ (B4, B5): không có field
hũ nguồn, khách chọn nguồn tiền trên màn chuyển tiền của `pfm`.

## B2. `create_jar` — Form 1: tạo hũ mới

```json
{
  "type": "create_jar",
  "jar_name": "Cà phê & giải trí",
  "allocation_amount": 800000,
  "initial_balance": 500000,
  "category_ids": ["entertainment"],
  "reason": "Chi Giải trí 3 tháng gần nhất trung bình ~750.000đ/tháng"
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `jar_name` | ✅ | tên hũ, không rỗng |
| `allocation_amount` | ✅ | > 0 — thành `limit` (hạn mức tháng). Không bị giới hạn bởi `allocationHeadroom` |
| `initial_balance` | ✅ | **số dư ban đầu**, số nguyên VND **≥ 0** (`0` hợp lệ) — tiền lấy từ "Chờ phân bổ" vào hũ, phải **≤ `allocationHeadroom`**. **Thiếu field, âm hoặc số lẻ → `pfm` bỏ `ui`** (không tự coi là 0). Khách sửa được trên card trước khi xác nhận |
| `category_ids` | ✅ | category hũ phụ trách (được phép `[]`); mỗi phần tử là `id` category chi tiêu (`kind: "expense"`) của khách từ `GET /api/categories?cif=`, sai thì server `422` |
| `reason` | ✅ | căn cứ đề xuất, hiện cho khách xem — nêu số liệu thật |

(Ví dụ minh hoạ: `allocationHeadroom` = 1.000.000 như dữ liệu mẫu ở trên, nên
`initial_balance` 500.000 là hợp lệ; 1.500.000 thì phải đề xuất số nhỏ hơn hoặc `0`.
`allocation_amount` 800.000 không phụ thuộc headroom.)

Agent **không gửi `id`** (`pfm` tự sinh). Khi gợi ý phải tôn trọng:
- **`initial_balance ≤ allocationHeadroom`** (từ `jar-summary`). `allocationHeadroom`
  ≤ 0 hoặc `null` nghĩa là không còn tiền chờ phân bổ → vẫn tạo được hũ với
  `initial_balance: 0`; nói rõ trong `answer` là hũ chưa có tiền. Server kiểm lại (`422` nếu
  vượt), card hiện lý do bằng tiếng Việt.
- **Khách tự tạo hũ trong `pfm` có thể không đặt hạn mức** (ô hạn mức để trống → `limit: null`,
  hũ như "Tiết kiệm" thường có `limit: null` và `balance: 0`). Contract `create_jar` của Agent
  **không đổi**: vẫn phải có `allocation_amount > 0` và `initial_balance` như bảng trên. Ngược
  lại khi đọc `jar-summary`, Agent gặp `limit: null` là bình thường — nói "chưa đặt hạn mức", không
  coi là 0.
- **`category_ids` của `create_jar`:** Agent nên chỉ đưa danh mục "chưa xếp hũ" (không hũ nào giữ nó —
  từ 2026-09-24 xoá hũ là xoá hẳn, danh mục của hũ đó thành "chưa xếp hũ", không còn hũ "Khác" tự
  sinh; suy ra từ `categoryIds` của từng hũ trong `jar-summary` so với `GET /api/categories?cif=`).
  Khi khách **yêu cầu rõ** một danh mục đang thuộc hũ khác, Agent có thể đưa vào `category_ids` và nói
  rõ trong `answer` hũ nào sẽ mất danh mục. Form tạo hũ trên `pfm` cho khách chọn **mọi** danh mục
  chi tiêu; danh mục đang ở hũ khác hiện dòng "… sẽ chuyển từ hũ X" và server lấy nó khỏi hũ cũ
  trong cùng lần ghi (một danh mục chỉ thuộc một hũ). Form **không hiện `reason`** của Agent (chỉ
  hiện `answer` ở bong bóng chat phía trên) — Agent nên đặt phần giải thích vào `answer`.

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
| `allocation_amount` | ✅ | `limit` (hạn mức tháng) mới, > 0 |
| `category_ids` | tuỳ chọn | **danh sách đầy đủ** category mới của hũ; bỏ field = không đổi. Category lấy từ hũ khác sẽ bị chuyển sang hũ này |
| `reason` | ✅ | căn cứ đề xuất |

- **Tăng / giảm hạn mức** luôn được — hạn mức là kế hoạch, không kiểm `allocationHeadroom`.
- Đổi hạn mức **không** đổi `balance`. Giảm xuống dưới số đã chi (`spent`) thì
  `overLimit` thành `true` (vượt hạn mức) — nói rõ trong `reason`; số dư giữ nguyên.
- `edit_jar` không có field số dư: muốn thêm tiền cho hũ thì dùng `distribute_amount` /
  `rebalance_jars` hoặc nhắc khách tự nạp trong `pfm`.

### Chuyển danh mục giữa hai hũ (chỉ là `edit_jar`, không phải `rebalance_jars`)

Khi khách muốn chuyển danh mục X từ hũ **A** sang hũ **B**, Agent trả **một** `edit_jar`
cho **hũ nhận B**, với `category_ids` = **danh sách đầy đủ của B sau khi nhận** (danh mục B
đang có + X). Server tự lấy X ra khỏi A vì 1 danh mục chỉ thuộc tối đa 1 hũ.

**Không** trả `edit_jar` cho hũ cho A với `category_ids` bỏ X: khi đó X không thuộc hũ nào
("Chưa xếp hũ"), không sang B như khách yêu cầu. Chỉ bỏ X khỏi một hũ (không gán cho hũ
nào) khi khách nói rõ muốn để X "chưa xếp hũ".

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

> Ghi chú UI: trong màn Sửa hũ của `pfm`, khách chọn/bỏ chọn danh mục chỉ là bản nháp và được lưu
> **một lần khi đóng sheet** (không lưu từng lần chạm). Chỉ là hành vi giao diện — contract `edit_jar`
> không đổi.

## B4. `rebalance_jars` — Form 3: chuyển số dư từ một hũ sang hũ khác

> **Đổi dạng 2026-09-24 (breaking):** dạng cũ `{target_jar_id, shortfall, moves[]}` — 1 hũ đích nhận
> từ nhiều nguồn, có nguồn `"pool"` — **đã bỏ**. Dạng mới là **1 hũ nguồn cho tiền sang 1 hoặc nhiều
> hũ khác**; không còn `"pool"` ở đâu cả (tiền chưa phân bổ chuyển vào hũ bằng `distribute_amount`,
> B5). Payload dạng cũ không qua được kiểm hình dạng của `pfm` → chỉ hiện `answer`. Nguồn:
> `agent_backend_docs/jars/rebalance-jars.md`.

Dùng khi khách nêu "chuyển 500 nghìn từ hũ Ăn uống sang hũ Di chuyển" (1 hoặc nhiều hũ nhận, có
thể nêu số cho từng hũ), hoặc hũ hết số dư / định chi quá số dư mà không nêu nguồn ("lấy từ hũ
khác bù" → Agent chọn **1 hũ nguồn** có `spendable` lớn nhất và đủ một mình). Không đổi `limit`,
không chuyển tiền thật — chỉ dịch chuyển `balance` giữa các hũ (số dư cộng dồn, còn nguyên sang
tháng sau). Form này **độc lập** với `transfer_form` (B1).

```json
{
  "type": "rebalance_jars",
  "from_jar_id": "food",
  "allocations": [
    { "to_jar_id": "transport", "amount": 300000 },
    { "to_jar_id": "health", "amount": 200000 }
  ],
  "reason": "Chuyển 500.000đ từ hũ Ăn uống sang hũ Di chuyển và hũ Sức khỏe theo đúng số khách nêu"
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `from_jar_id` | ✅ | hũ cho tiền (id thật trong `jar-summary`); **không** phải `"pool"` |
| `allocations` | ✅ | ≥ 1 phần tử `{ to_jar_id, amount }`, mỗi hũ nhận **một lần** |
| `allocations[].to_jar_id` | ✅ | hũ nhận; khác `from_jar_id`; không phải `"pool"` |
| `allocations[].amount` | ✅ | số nguyên VND > 0, cộng vào `balance` hũ nhận và trừ khỏi hũ nguồn |
| `reason` | ✅ | vì sao chia như vậy, có số thật |

**Quy tắc cứng** (`pfm` kiểm lại; vi phạm điều nào thì bỏ cả `ui`, chỉ hiện `answer`):
1. `Σ allocations[].amount ≤ spendable` của hũ nguồn (không đẩy hũ nguồn xuống âm). Hũ nguồn có
   `spendable: null` (chưa có số dư) **không được cho**.
2. `from_jar_id` ≠ `to_jar_id`, mỗi hũ nhận một lần, không có `"pool"`, không bịa id.
3. Chỉ **1 hũ nguồn mỗi form**: khách nêu nhiều hũ nguồn thì làm hũ đầu và nói còn hũ nào để lượt sau.

**Khác với hợp đồng phía Agent — hũ chưa có số dư không nhận được chuyển giữa hũ.** Tài liệu Agent
cho phép hũ nhận là hũ bất kỳ; nhưng `pfm` từ chối ghi một khoản chuyển vào hũ `balance: null`
(`rebalance-leg-guard.ts` trả `422 jar has no balance`), vì số dư chưa được neo. Card hiện lỗi
"nạp tiền vào hũ trước khi nhận chuyển" và không cho áp dụng. Muốn đưa tiền vào hũ chưa có số dư
thì dùng `distribute_amount` (khoản nạp chính là số dư đầu tiên). Agent nên nêu điều này trong
`answer` thay vì trả `rebalance_jars` cho hũ nhận chưa có số dư.

Các quy tắc trên còn được kiểm **lần nữa ngay tại nơi ghi** (`POST`/`PATCH /api/manual-transactions`,
`rebalance-leg-guard.ts`, từ 2026-09-23): mỗi bản ghi chuyển ≤ số dư hũ nguồn tại thời điểm ghi.

**Khi khách xác nhận**, `pfm` (không phải Agent) ghi **mỗi `allocations[]` một bản ghi** chuyển giữa
hai hũ (`categoryId: "dieu-chinh-hu"`, `meta.fromJarId`/`toJarId`), **lần lượt từng bản ghi** để
mỗi bản ghi thấy đúng số dư còn lại của hũ nguồn; một bản ghi lỗi thì các bản ghi đã ghi được gỡ ra.
Số dư hai hũ tự cập nhật, `spent` và `limit` không đổi. Card cho phép khách sửa hũ nguồn, hũ nhận,
số tiền, thêm/bớt hũ nhận trước khi áp dụng.

**Ví dụ số:** Ăn uống `balance` 2.613.000 → `spendable` 2.613.000. Khách: "chuyển 500 nghìn từ
Ăn uống sang Di chuyển" → `from_jar_id: "food"`, `allocations: [{transport, 500000}]`. Sau khi áp
dụng: Ăn uống 2.113.000, Di chuyển +500.000; `limit` và `spent` của cả hai hũ không đổi.

### Dùng trong luồng Chuyển tiền (khi bấm "Tiếp tục" mà hũ nguồn không đủ)

Không đi qua chat: `pfm` gọi endpoint riêng của Agent `POST /jar-rebalance` (không thread, không nhớ
gì; xem `agent_backend_docs/jars/endpoints.md`) qua proxy `POST /api/agent/jar-rebalance`. Body mới
**không còn** `mode`/`target_jar_id`/`spend_amount` (field lạ → Agent trả `422`):

```json
{ "user_id": "CIF_0001", "from_jar_id": "lifestyle", "amount": 500000, "to_jar_ids": ["food"] }
```

Endpoint chỉ nhận **một hũ nguồn** mỗi lần gọi. Khi khách chọn một hũ làm nguồn tiền, nhập số lớn
hơn `spendable` của hũ đó rồi bấm "Tiếp tục", `pfm` mở popup "Hũ chưa đủ tiền" (phần thiếu `S` do
engine tính) và chia việc như sau:
1. **"Chưa phân bổ" là phần duy nhất do engine của `pfm` quyết** và luôn được lấy trước: nếu pool đủ
   bù cả `S` thì đó chính là gợi ý và **không gọi Agent**.
2. **Mọi phần vượt pool đều do Agent đề xuất.** `pfm` gọi endpoint **một lần cho mỗi hũ** mà chuỗi
   nguồn của engine lấy tiền (tối đa 3 hũ, chạy song song): `from_jar_id` = hũ đó, `amount` = số
   engine dự kiến lấy, `to_jar_ids: [hũ đang thiếu]`. Chuỗi nguồn quá 3 hũ thì không gọi Agent.
3. Trong lúc chờ (~10–25 s), popup **chỉ hiện dòng "Chưa phân bổ"** cùng dòng "Phần còn lại · chờ
   M-You chọn hũ", và nút "Đồng ý rót" bị khoá ("Đang chờ M-You…"); khách vẫn bấm được "Chọn nguồn
   khác". Khi **mọi** lần gọi trả đúng `rebalance_jars` như đã hỏi (đúng `from_jar_id`, đúng 1 hũ
   nhận, đúng `amount`), popup hiện các `reason` của Agent và "Đồng ý rót" mở lại.
4. Agent không trả được (không có `ui`, khác điều đã hỏi, lỗi, quá 60 s) → popup hiện cách rót tự
   động của engine kèm dòng "M-You chưa gợi ý được lúc này", để giao dịch không bị kẹt.
5. Lúc xác nhận chuyển tiền, `pfm` kiểm lại kế hoạch với số mới nhất trước khi ghi các bản ghi bù
   (`origin: "manual"`); không khớp thì dùng cách rót của engine. Nguồn "Chưa phân bổ" (pool)
   **không** hỏi Agent.

**Lưu ý:** hũ nguồn và số tiền của mỗi lần gọi do `pfm` (engine) chọn, Agent chỉ xác nhận/giải thích
và có thể từ chối (`ui: null`) khi số của nó khác. Nếu sản phẩm muốn Agent **tự chọn hũ nguồn**, cần
Agent hỗ trợ chế độ nhận `to_jar_ids` mà không cần `from_jar_id` — endpoint hiện tại chưa có. Agent
đọc số liệu hũ từ bản `pfm` đã deploy (`PFM_BASE_URL`), nên khi `pfm` chạy local với số liệu khác,
Agent thường từ chối và popup rơi về bước 4.

## B5. `distribute_amount` — chia tiền chưa phân bổ vào hũ

Loại `ui` mới (2026-09-24). Khách muốn đưa một số tiền vào 1 hoặc nhiều hũ mà **không nêu hũ nguồn**
("chuyển 300k vào hũ Tiết kiệm", "chia 1 triệu vào Ăn uống và Di chuyển", "bù giúp tôi"): tiền
**luôn lấy từ tiền chưa phân bổ** (`unallocated`); Agent chỉ cộng vào **số dư** hũ nhận, **không đổi
`limit`**. Nguồn: `agent_backend_docs/jars/distribute-amount.md`.

```json
{
  "type": "distribute_amount",
  "allocations": [
    { "to_jar_id": "food", "amount": 600000 },
    { "to_jar_id": "transport", "amount": 400000 }
  ],
  "reason": "Chia 1.000.000đ tiền chưa phân bổ theo đúng số khách nêu cho hũ Ăn uống và hũ Di chuyển"
}
```

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `allocations` | ✅ | ≥ 1 phần tử `{ to_jar_id, amount }`, mỗi hũ **một lần** |
| `allocations[].to_jar_id` | ✅ | id hũ có trong `jar-summary`; không phải `"pool"` |
| `allocations[].amount` | ✅ | số nguyên VND > 0, cộng vào `balance` hũ đó |
| `reason` | ✅ | căn cứ chia, 1–2 câu |

**Quy tắc cứng** (`pfm` kiểm lại; vi phạm thì bỏ cả `ui`): `Σ amount ≤ max(0, unallocated)` (không lấy
từ hũ khác); mỗi hũ một lần; id có thật. Mọi hũ nhận được, **kể cả hũ `balance: null` hoặc chưa đặt
hạn mức** — khoản nạp chính là số dư đầu tiên. Khách nêu số cho từng hũ → đúng số đó; chỉ nêu 1 tổng
→ hũ cần bù (`balance < 0`) trước, phần còn lại chia đều (endpoint: theo chi tiêu 3 tháng).

**Khi khách xác nhận**, `pfm` ghi **một lô nạp tiền duy nhất** qua `POST /api/jar-ledger`
(`kind: "deposit"` cho mỗi hũ, all-or-nothing, server kiểm lại trần CASA) — cùng cửa ghi với sheet
"Chia ngay". Sau khi ghi, `unallocated` giảm đúng tổng. Card cho khách sửa hũ, số tiền, thêm/bớt hũ
nhận trước khi áp dụng.

### Dùng ở màn "Chờ phân bổ" → "Chia ngay"

Không đi qua chat: sheet "Chia tiền vào hũ" có nút **"Gợi ý cách chia từ M-You"** (hiện khi
`unallocated > 0`). `pfm` gọi `POST /jar-distribute` qua proxy `POST /api/agent/jar-distribute`:

```json
{ "user_id": "CIF_0001", "amount": 1000000 }
```

`amount` là **toàn bộ** số "Chờ phân bổ" hiện có; Agent tự quyết chia cho hũ nào (theo chi tiêu 3
tháng gần nhất, hũ cần bù trước). Khách chờ ~10–25 s (nút hiện "M-You đang phân tích…", vẫn nhập tay
được). Kết quả **chỉ điền sẵn** ô "cộng thêm" của từng hũ (các hũ còn lại về 0) — khách sửa và bấm
"Thêm vào số dư" như thường, server vẫn kiểm trần CASA. `pfm` bỏ **cả** đề xuất (không điền gì) khi:
có hũ không tồn tại, hũ lặp, `amount` không phải số nguyên dương, hoặc `Σ amount > unallocated`.
Không có `ui` → hiện `answer` của Agent; lỗi/quá 60 s → "Chưa lấy được gợi ý từ M-You".

## B6. `clarify_options` — hỏi lại bằng nút bấm

Loại `ui` dùng chung cho mọi flow: khi Agent cần khách chọn giữa vài phương án cụ thể thay vì đoán.
Chi tiết contract phía Agent: `agent_backend_docs/clarify-options.md`. Phía `pfm`:

```json
{
  "answer": "Bạn hãy trả lời các câu hỏi sau để mình gợi ý chính xác hơn.",
  "ui": {
    "type": "clarify_options",
    "questions": [
      { "question": "Bạn muốn lấy tiền từ hũ nào?", "options": ["Hũ Ăn uống (còn 1.813.000đ)", "Hũ Hưởng thụ (còn 1.296.000đ)"] },
      { "question": "Chuyển bao nhiêu?", "options": ["500.000đ", "1.000.000đ"] }
    ]
  }
}
```

- `questions` 1–4 câu; mỗi câu có `question` không rỗng và `options` là **2–4 chuỗi thường, không
  trùng nhau** (không phải object). Sai dạng → `pfm` bỏ `ui`, chỉ hiện `answer`.
- `answer` là **một câu dẫn ngắn** hiện cùng với các câu hỏi, đừng lặp lại nội dung câu hỏi.
- **Giao diện:** các câu hỏi hiện **lần lượt từng câu** ("Câu 1/2"), khách bấm một lựa chọn là sang
  câu kế (có nút "← Câu trước" để đổi); **luôn có ô nhập tự do** dưới lựa chọn — khách không bị giới
  hạn trong `options`, nên Agent phải xử lý được câu trả lời không nằm trong danh sách.
- **Khách trả lời → `pfm` gửi gì cho Agent:** 1 câu hỏi → gửi **đúng chuỗi** đã chọn/nhập; nhiều
  câu → gửi **một tin nhắn duy nhất** `câu_trả_lời_1. câu_trả_lời_2.` (nối bằng `". "` và kết thúc
  bằng `.`), theo thứ tự câu hỏi — không gửi từng tin riêng.
- Sau khi trả lời, lượt đó được thu gọn thành "Đã trả lời" (bấm để xem lại câu hỏi và lựa chọn).
- Vẫn tuân thủ "mỗi lượt tối đa 1 `ui`": lượt `clarify_options` không kèm form hũ/chuyển tiền; form
  được trả ở lượt kế, sau khi đã có câu trả lời.

---

# Phần C — Kỳ vọng từ Agent (đã kiểm với agent thật, 2026-09-21)

> Kết quả dưới đây đo **trước** thay đổi 2026-09-23 (tách hạn mức/số dư): các dòng nói
> "headroom" cho hạn mức và `remaining = hạn mức − đã chi` là theo contract cũ. Theo contract
> mới, `create_jar` phải kèm `initial_balance` (thiếu → `pfm` bỏ `ui`), và tăng hạn mức không
> còn bị chặn bởi headroom. Cần đo lại sau khi Agent cập nhật.
>
> Các dòng và mục nói về `rebalance_jars` dạng `target_jar_id`/`shortfall`/`moves` (kể cả nguồn
> `pool` và thứ tự nguồn ở C2) đo theo **dạng cũ đã bỏ ngày 2026-09-24** (B4); `distribute_amount`
> (B5) chưa có kịch bản đo. Đo lại theo contract mới trước khi dùng các dòng này làm chuẩn.

Agent trả `answer` + tối đa 1 khối `ui` (trong repo Agent là khối ```` ```ui-json ````, `server.py`
tách ra thành field `ui`). Phân vai kiểm tra:

| Ai | Kiểm gì | Nếu sai |
|---|---|---|
| **Agent** (`server.py`, `text_utils.py`) | chỉ **hình dạng**: đủ field, đúng kiểu; `create_jar` **không** có `jar_id`; `edit_jar` có `jar_id`; `category_ids` không lặp; `rebalance_jars`: `from_jar_id` ≠ `"pool"`, mỗi hũ nhận ≠ hũ nguồn và không lặp, mỗi `amount` nguyên > 0; `distribute_amount`: mỗi hũ nhận một lần, `amount` nguyên > 0 | bỏ `ui` (`ui = null`), chỉ còn `answer` |
| **`pfm`** | đối chiếu với số thật: `jar_id`/nguồn có tồn tại; `initial_balance` vượt `allocationHeadroom` (hạn mức không bị giới hạn); tên hũ trùng; `rebalance_jars`: Σ ≤ `spendable` hũ nguồn và hũ nhận đã có số dư; `distribute_amount`: Σ ≤ `unallocated` | bỏ đề xuất, chỉ hiện `answer` |

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
   Giải trí thành "Chưa xếp hũ".
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

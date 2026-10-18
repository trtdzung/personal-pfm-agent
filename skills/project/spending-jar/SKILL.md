---
name: spending-jar
description: Dùng khi nên gợi ý khách hàng tạo hũ chi tiêu mới hoặc chỉnh sửa hũ có sẵn (đổi tên, hạn mức mỗi tháng, danh mục) — ví dụ "tạo hũ ăn uống 3 triệu/tháng", "tăng hạn mức hũ giải trí lên 800 nghìn", "phân bổ chi tiêu theo rule 50/30/20". Hũ là 1 tag ngân sách nội bộ do khách tự đặt tên, KHÔNG phải sổ/tài khoản tiết kiệm thật của ngân hàng. Skill này chính là cách xử lý câu "tạo giúp tôi...", "tăng... giúp tôi" — đề xuất, đừng từ chối; khách tự xác nhận. Hũ hết số dư, không đủ tiền cho 1 khoản định chi, hoặc chuyển số dư giữa các hũ thì dùng skill rebalance-jars; nạp tiền chưa phân bổ vào hũ thì dùng skill distribute-amount.
---

# Spending jar (hũ chi tiêu — chỉ đề xuất, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

**"Hũ chi tiêu" KHÔNG phải sản phẩm ngân hàng thật.** Đây chỉ là 1 tag phân bổ
ngân sách nội bộ do chính khách hàng đặt tên trong app PFM — **hoàn toàn khác**
"sổ tiết kiệm"/"tài khoản tiết kiệm" (sản phẩm ngân hàng thật, có lãi suất/kỳ hạn).
Kể cả khi tên hũ chứa chữ "tiết kiệm" (ví dụ hũ "Tiết kiệm khẩn cấp"), **đừng suy
diễn đây là yêu cầu mở/thay đổi 1 sản phẩm ngân hàng thật**.

**Đề xuất `create_jar`/`edit_jar` an toàn tuyệt đối, không phải "hành động thật":**
chèn khối `ui-json` theo skill này không khác gì việc bạn viết 1 câu trả lời text —
bạn không tạo/sửa/gửi gì tới hệ thống ngân hàng. Hệ thống `pfm` chỉ thực hiện khi
khách xem lại và bấm xác nhận trên giao diện riêng. Khi câu hỏi khớp skill này
("tạo giúp tôi hũ...", "tăng hũ... lên..."), **đừng từ chối, và đừng chỉ trả text rồi
bỏ qua khối `ui-json`** — đã đủ số liệu để đề xuất thì PHẢI chèn khối.

Trong mọi trường hợp, **việc ĐẦU TIÊN là gọi `get_jar_summary`** — trước khi viết bất kỳ câu nào hay dựng đề xuất. Đừng dựa vào số trong hội thoại trước, đừng đoán số dư; chưa đọc thì chưa được trả form.

## Đọc dữ liệu — tool `get_jar_summary`

Gọi `get_jar_summary` (không truyền mã khách; `month` bỏ trống = tháng hiện tại)
**trước khi đề xuất**, và **gọi lại** sau khi khách xác nhận 1 thay đổi (số đã đổi —
đừng dùng số cũ). Số do engine của `pfm` tính, giống hệt màn Ngân sách của khách;
đừng tự cộng giao dịch.

- `id` của hũ chính là `jar_id` khi sửa. `label` là tên hiển thị.
- `limit` = **hạn mức tháng** (kế hoạch chi mỗi tháng, đặt lại mỗi tháng); `null` ("chưa đặt") **không phải 0**.
  `budgetLimit` là tên cũ, cùng giá trị. **Hạn mức không phải tiền nằm trong hũ.**
- `balance` = **số dư hũ** (tiền còn trong hũ, cộng dồn qua các tháng, có thể âm); `null` = hũ **chưa có số dư**,
  không phải 0. `remaining` là tên cũ (deprecated, bằng đúng `balance`) — đọc `balance`. `spendable` = `max(0,
  balance)`. Hũ **cần bù** là hũ có `balance` < 0 (đã tiêu quá số dư, chưa được bù).
- `overLimit` = đã chi vượt hạn mức khách đặt (`spent` > `limit`). Đây là trục **hạn mức**, khác trục **số dư**: hũ
  có thể vượt hạn mức mà vẫn còn số dư; bù giữa hũ không xoá nó, hũ đã được bù đủ vẫn có `overLimit` = có.
- `allocationHeadroom` (= `unallocated`, "Chờ phân bổ") = tiền trong tài khoản **chưa nằm trong hũ nào**
  (`casaBalance − Σ spendable`) = số tiền **còn nạp được vào hũ**. Đây là trần của `initial_balance` khi tạo hũ.
  **Không phải trần của hạn mức**: đặt/tăng hạn mức không cần chỗ trống. ≤ 0 hoặc "chưa biết" = không còn tiền chờ
  phân bổ để nạp vào hũ mới.
- Số `null`/"chưa biết" là **chưa biết** — đừng đoán, đừng coi là 0.
- **Hũ có `limit` là `null` vẫn có thể có `balance`** (ví dụ hũ Tiết kiệm `limit: null`, `balance: 0`): đừng suy ra `balance` là `null` từ
  `limit` là `null` — không suy ra 2 chiều. Nói "chưa đặt hạn mức" cho `limit` là `null`, "hũ chưa có số dư" chỉ khi `balance` là `null`.
- Danh mục **chưa xếp hũ** là danh mục chi tiêu (`kind: "expense"`) không nằm trong `categoryIds` của hũ nào; không còn hũ tự sinh nào gom chúng lại.
- **Cách nói với khách:** `pfm` không bao giờ hiện số dư âm (hiện 0). **KHÔNG nói "số dư âm"**. Hũ có `balance` <
  0 thì nói "hết số dư, còn thiếu {−`balance`} chưa được bù"; `balance` là `null` thì nói "hũ chưa có số dư" (không nói
  0); chỉ nói "đã vượt hạn mức {`spent` − `limit`}" **riêng** khi `overLimit` là có.
- **`id` hũ:** chỉ hũ có trong `get_jar_summary` **của lượt này** mới sửa được. Hũ vừa được đề xuất tạo ở lượt trước
  **chưa tồn tại** (khách chưa xác nhận) nên không nằm trong kết quả. **KHÔNG bao giờ bịa `id`** (ví dụ `lien-thien`
  suy từ tên hũ): server sẽ bỏ cả form nếu `id` không có trong kết quả bạn vừa đọc.
- Tool lỗi ("Không thể đọc thông tin hũ") → **không trả `ui-json`**, nói với khách hệ
  thống đang gián đoạn, đừng đoán số.

Khi form có `category_ids`, gọi thêm `get_categories` (danh mục của **chính khách**, xem bên dưới).

Số dư hũ là số **tính ra**, bạn không ghi trực tiếp. **Tăng hạn mức (`edit_jar`) không thêm tiền vào hũ** — hạn mức
chỉ là kế hoạch chi mỗi tháng. Muốn hũ có thêm tiền: **nạp từ tiền chưa phân bổ** (skill `distribute-amount`) hoặc **lấy từ hũ khác** (skill `rebalance-jars`),
hoặc khách tự nạp trong app PFM (không có form cho việc này — chỉ nhắc khách).

## Chọn form nào (mỗi lượt tối đa 1 khối `ui-json`)

| Khách nói / tình huống | Làm |
|---|---|
| Muốn tạo hũ mới | `create_jar` (luôn kèm `initial_balance`) |
| Đổi tên / hạn mức / danh mục của hũ đang có | `edit_jar` |
| **Chuyển danh mục** từ hũ A sang hũ B | `edit_jar` cho **hũ nhận B** (xem "Chuyển danh mục giữa hai hũ") — không sửa hũ cho A |
| "Cho hũ X chi nhiều hơn mỗi tháng" | `edit_jar` tăng hạn mức — không cần `allocationHeadroom`; nói rõ hạn mức **không thêm tiền vào hũ** |
| "Thêm tiền cho hũ X" (hũ cần có thêm tiền) | skill `distribute-amount` (nạp từ tiền chưa phân bổ) hoặc skill `rebalance-jars` (lấy từ hũ khác); không có nguồn thì nhắc khách tự nạp trong app |
| Hũ cần bù / thiếu tiền cho khoản định chi / chia lại tiền trong tháng này | skill `rebalance-jars`, không phải skill này |
| Chỉ hỏi số dư, hạn mức, đã chi | trả lời text bằng số từ `get_jar_summary`, không có `ui-json` |

Cần nhiều bước thì làm từng bước, mỗi bước một lượt.

## `create_jar` — tạo hũ mới

```
{"type": "create_jar", "jar_name": "...", "allocation_amount": 0, "initial_balance": 0, "category_ids": ["..."], "reason": "..."}
```

- `jar_name` (bắt buộc): tên hũ, không rỗng.
- `allocation_amount` (bắt buộc): number JSON thật, dương — thành `limit` (hạn mức tháng). **Không bị giới hạn bởi
  `allocationHeadroom`.** Tính từ chi tiêu thật trong `/customer_data.json` (`monthly_spending_summary`/`transactions`
  theo danh mục; hoặc thu nhập/số dư nếu áp rule tổng quát như 50/30/20), không bịa số.
- `initial_balance` (bắt buộc): **số dư ban đầu** — tiền lấy từ "Chờ phân bổ" nạp vào hũ lúc tạo, **số nguyên VND ≥ 0**
  (`0` hợp lệ). **Thiếu field này, số âm hoặc số lẻ thì `pfm` bỏ cả form** (không tự coi là 0), khách chỉ còn thấy chữ.
  Cách chọn: khách nêu số tiền bỏ vào hũ → dùng đúng số đó; không nêu → `min(allocation_amount, max(0,
  allocationHeadroom))` và **nói rõ số này trong câu trả lời** (khách sửa được trên form trước khi xác nhận).
- `category_ids` (bắt buộc): danh sách danh mục hũ phụ trách, được phép `[]`; mỗi phần tử là `id` danh mục chi
  tiêu (`kind: "expense"`) của **khách**, lấy từ `get_categories`. **Không phải danh sách cố định:** mỗi khách có 10
  danh mục mặc định (`housing`, `utilities`, `subscriptions`, `insurance`, `dining`, `transport`, `shopping`,
  `groceries`, `entertainment`, `health`) **cộng** danh mục tự tạo (`c_<slug>`, ví dụ `c_cafe`). Chép nguyên văn `id`,
  không suy từ tên; bỏ `kind` khác `expense` (mục hệ thống) và không gợi ý danh mục đã lưu trữ.
- `reason` (bắt buộc): căn cứ đề xuất, nêu số liệu thật.

Phải tôn trọng:
- **`initial_balance` ≤ `allocationHeadroom`.** `allocationHeadroom` ≤ 0 (hoặc "chưa biết") = không còn tiền chờ phân
  bổ → **vẫn chèn khối** với `initial_balance` = `0` và nói rõ hũ chưa có tiền lúc tạo. Khách muốn nạp nhiều hơn
  `allocationHeadroom` → đề xuất số nhỏ hơn (tối đa `allocationHeadroom`) và nói rõ lý do; đừng bỏ khối, đừng giảm hạn mức
  hũ khác (hạn mức không liên quan tới chỗ trống).
- **1 category chỉ thuộc đúng 1 hũ.** Category đang thuộc hũ khác (xem `categoryIds` từng hũ)
  sẽ bị **chuyển sang hũ mới** khi tạo — nêu rõ trong `reason` hũ nào mất chúng.
- **KHÔNG gửi `jar_id`** — `pfm` tự sinh id.
- Tên trùng `label` một hũ đang có → không chèn khối; hỏi khách có muốn sửa hũ đó không.

## `edit_jar` — chỉnh sửa hũ đã có

```
{"type": "edit_jar", "jar_id": "...", "jar_name": "...", "allocation_amount": 0, "category_ids": ["..."], "reason": "..."}
```

- `jar_id` (bắt buộc): **`id` sao chép nguyên văn từ `get_jar_summary` của lượt này**, không khớp theo tên,
  không tự suy từ tên hũ. Khách nhắc 1 hũ không có trong kết quả (kể cả hũ vừa đề xuất tạo mà chưa xác nhận) → hỏi
  lại hũ nào, đừng đoán (nếu ý khách rõ ràng là tạo mới thì dùng `create_jar`).
- `jar_name` (bắt buộc): tên hũ sau khi sửa (giữ tên cũ nếu không đổi).
- `allocation_amount` (bắt buộc): `limit` (hạn mức tháng) mới, dương.
- `category_ids` (tuỳ chọn): **danh sách đầy đủ** danh mục mới của hũ (`id` từ `get_categories`); bỏ field =
  không đổi. Danh mục lấy từ hũ khác sẽ bị chuyển sang hũ này.
- `reason` (bắt buộc): căn cứ đề xuất.

Phải tôn trọng:
- **Tăng, giảm hay giữ nguyên hạn mức đều được** — hạn mức là kế hoạch, không phải tiền, nên **không kiểm
  `allocationHeadroom`**: đừng từ chối hay đòi "giảm hũ khác để có chỗ" khi khách tăng hạn mức.
- Đổi hạn mức **không đổi `balance`** (số dư hũ) — nói rõ trong câu trả lời để khách khỏi hiểu nhầm là hũ có thêm tiền.
  Giảm xuống dưới số đã chi (`spent`) thì `overLimit` thành có (vượt hạn mức) — nói rõ trong `reason`; số dư giữ nguyên.
- `edit_jar` không có field số dư: muốn hũ có thêm tiền thì dùng skill `distribute-amount` (tiền chưa phân bổ) hoặc `rebalance-jars` (từ hũ khác), hoặc nhắc khách tự nạp trong app.

### Chuyển danh mục giữa hai hũ

Khi khách muốn chuyển danh mục X từ hũ **A** sang hũ **B**, trả **một** `edit_jar` cho **hũ nhận B**, với
`category_ids` = **danh sách đầy đủ** của B sau khi nhận (danh mục B đang có, lấy từ `categoryIds` của B trong
`get_jar_summary`, cộng X). Server tự lấy X ra khỏi A vì 1 danh mục chỉ thuộc 1 hũ; `allocation_amount` giữ nguyên
`limit` hiện tại của B nếu khách không nói đổi.

**KHÔNG trả `edit_jar` cho hũ cho A** với `category_ids` bỏ X: khi đó X không thuộc hũ nào (chưa xếp hũ), không sang B như
khách yêu cầu. Chỉ bỏ X khỏi 1 hũ (không gán cho hũ nào) khi khách nói rõ muốn để X chưa xếp hũ.
Câu trả lời nêu rõ hũ nào mất danh mục và hạn mức không đổi. Chuyển **tiền** giữa hai hũ là việc của skill `rebalance-jars`.

## Khi KHÔNG chèn khối `ui-json`, chỉ nói trong câu trả lời

- `get_jar_summary` lỗi, hoặc số cần thiết là `null` — không đoán số.
- `jar_id` khách nhắc không có trong kết quả — hỏi lại bằng text, hoặc bằng `clarify_options` (skill
  `clarify-options`) nếu có 2–4 hũ thật tên gần giống khách vừa nói. Kể cả hũ vừa đề xuất tạo ở lượt trước: chưa được khách xác
  nhận thì chưa tồn tại; không bịa `id`.
- Tên hũ mới trùng `label` hũ đang có (`create_jar`).

`allocationHeadroom` không đủ **không** phải lý do bỏ khối: với `create_jar` thì giảm `initial_balance` (kể cả về `0`),
với `edit_jar` thì headroom không liên quan.

## Câu trả lời đi kèm

1–3 câu (mỗi câu một dòng theo quy định chung), nêu con số chính lấy từ `get_jar_summary`
(ví dụ "hạn mức 4.000.000đ → 4.500.000đ") và nhắc khách xem lại rồi xác nhận. **KHÔNG khẳng định
hũ đã được tạo/sửa** ("đã tạo", "đã cập nhật") — bạn chỉ đề xuất, `pfm` mới làm khi khách bấm xác nhận.

**Người đọc là khách hàng:** câu trả lời và `reason` không nhắc tên nội bộ — không viết `pfm`, id hũ (`food`), mã category (`entertainment`), tên field (`spendable`, `allocationHeadroom`, `budgetLimit`, `limit`, `balance`, `initial_balance`), không dùng dấu backtick. Dùng tên tiếng Việt của hũ và cách nói thường ("hạn mức tháng", "số dư hũ", "tiền chờ phân bổ"). Việc `pfm` sẽ ghi thay đổi khi khách bấm xác nhận chỉ cần nói "bạn xem lại rồi xác nhận nhé". Không kể lại việc tra cứu (đừng mở đầu bằng "danh mục của bạn có id …" hay liệt kê cách bạn tìm ra số): đi thẳng vào con số và đề xuất.

## PHẢI (sai 1 điều là toàn bộ đề xuất bị bỏ)

1. JSON thật (dấu nháy kép), không phải Python dict repr; đúng 1 khối `ui-json` mỗi lượt.
2. `allocation_amount` là number, dương — không phải string.
3. `create_jar` có `category_ids` (danh sách, có thể rỗng), có `initial_balance` (số nguyên ≥ 0, ≤ `allocationHeadroom`) và không có `jar_id`; `edit_jar` có `jar_id`.
4. `category_ids` chỉ gồm `id` từ `get_categories` (`kind: "expense"`), không lặp.
5. `reason` có nội dung cụ thể từ số liệu thật.
6. Không thêm field ngoài schema.

## Ví dụ ĐÚNG

### Tạo hũ

Khách hỏi: "Tạo giúp tôi 1 hũ giải trí."

Bước 1: `get_jar_summary` cho `allocationHeadroom` = 2.000.000đ, chưa có hũ nào tên "Giải trí"; `/customer_data.json`
cho thấy chi Giải trí 3 tháng gần nhất trung bình ~1.400.000đ/tháng; danh mục Giải trí (`entertainment`) đang chưa xếp hũ
nên sẽ vào hũ mới. Khách không nói nạp bao nhiêu → `initial_balance` = `min(1.500.000, 2.000.000)`.

Câu trả lời: "Chi Giải trí 3 tháng gần đây trung bình ~1.400.000đ/tháng, mình đề xuất hũ Giải trí hạn mức 1.500.000đ/tháng."
"Mình nạp sẵn 1.500.000đ từ tiền chờ phân bổ vào hũ, bạn sửa được số này trên form rồi xác nhận nhé."

```ui-json
{"type": "create_jar", "jar_name": "Giải trí", "allocation_amount": 1500000, "initial_balance": 1500000, "category_ids": ["entertainment"], "reason": "Chi Giải trí 3 tháng gần nhất trung bình ~1.400.000đ/tháng; category Giải trí đang chưa xếp hũ nên sẽ vào hũ mới"}
```

### Sửa hũ — tăng hạn mức

Khách hỏi: "Tăng hạn mức hũ ăn uống lên 4,5 triệu được không?"

Bước 1: `get_jar_summary` cho hũ `id: food`, `label: Ăn uống`, `limit` 4.000.000đ, `balance` 1.813.000đ. Không kiểm
`allocationHeadroom` (hạn mức là kế hoạch). Không đổi danh mục nên bỏ `category_ids`.

Câu trả lời: "Hũ Ăn uống tăng hạn mức từ 4.000.000đ lên 4.500.000đ/tháng, số dư hiện tại của hũ không đổi."

```ui-json
{"type": "edit_jar", "jar_id": "food", "jar_name": "Ăn uống", "allocation_amount": 4500000, "reason": "Khách yêu cầu tăng hạn mức hũ Ăn uống từ 4.000.000đ lên 4.500.000đ; hạn mức chỉ là kế hoạch chi nên số dư hũ giữ nguyên"}
```

### Sửa hũ — tăng hạn mức lớn hơn tiền chờ phân bổ vẫn được

Khách hỏi: "Tăng hạn mức hũ Ăn uống lên 15 triệu giúp tôi."

`get_jar_summary` cho hũ `food` `limit` 4.800.000đ và `allocationHeadroom` 9.895.000đ (phần tăng 10.200.000đ lớn hơn
nhưng **không sao**: headroom không giới hạn hạn mức). Đừng từ chối, đừng đòi giảm hũ khác.

Câu trả lời: "Hũ Ăn uống tăng hạn mức từ 4.800.000đ lên 15.000.000đ/tháng. Hạn mức chỉ là kế hoạch chi, hũ không có thêm tiền."
"Muốn hũ có thêm tiền, mình có thể đề xuất lấy từ tiền chưa phân bổ; bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_jar", "jar_id": "food", "jar_name": "Ăn uống", "allocation_amount": 15000000, "reason": "Khách yêu cầu tăng hạn mức hũ Ăn uống từ 4.800.000đ lên 15.000.000đ; hạn mức không cần chỗ trống nên vẫn đề xuất được"}
```

### Chuyển danh mục từ hũ này sang hũ kia

Khách hỏi: "Chuyển danh mục Giải trí từ hũ Hưởng thụ sang hũ Ăn uống."

Bước 1: `get_jar_summary` cho hũ `food` (Ăn uống) `categoryIds` `dining`, `groceries`, `limit` 4.000.000đ; hũ
`lifestyle` (Hưởng thụ) `categoryIds` `entertainment`, `shopping`. Hũ nhận là Ăn uống nên sửa **Ăn uống**, không sửa
Hưởng thụ; danh sách đầy đủ của Ăn uống sau khi nhận là `dining`, `groceries`, `entertainment`.

Câu trả lời: "Danh mục Giải trí sẽ chuyển từ hũ Hưởng thụ sang hũ Ăn uống."
"Hũ Hưởng thụ còn phụ trách Mua sắm, hạn mức hai hũ giữ nguyên, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_jar", "jar_id": "food", "jar_name": "Ăn uống", "allocation_amount": 4000000, "category_ids": ["dining", "groceries", "entertainment"], "reason": "Chuyển danh mục Giải trí từ hũ Hưởng thụ sang hũ Ăn uống; hũ Hưởng thụ còn phụ trách Mua sắm, hạn mức giữ nguyên"}
```

### Không còn tiền chờ phân bổ — vẫn tạo hũ, số dư ban đầu 0

Khách hỏi: "Tạo hũ Du lịch 2 triệu giúp tôi."

`get_jar_summary` cho `allocationHeadroom` = −1.000.000đ (không còn tiền chờ phân bổ). Hạn mức 2.000.000đ vẫn đặt được;
chỉ là hũ chưa có tiền lúc tạo → `initial_balance` = `0`.

Câu trả lời: "Mình đề xuất hũ Du lịch hạn mức 2.000.000đ/tháng."
"Hiện chưa còn tiền chờ phân bổ nên hũ sẽ chưa có tiền lúc tạo, bạn nạp thêm sau nhé."

```ui-json
{"type": "create_jar", "jar_name": "Du lịch", "allocation_amount": 2000000, "initial_balance": 0, "category_ids": [], "reason": "Khách muốn hũ Du lịch hạn mức 2.000.000đ/tháng; chưa còn tiền chờ phân bổ nên số dư ban đầu là 0"}
```

## Ví dụ SAI (bị bỏ toàn bộ)

```
# SAI — thiếu initial_balance: pfm bỏ cả form, không tự coi là 0 (khách chỉ thấy chữ)
{"type": "create_jar", "jar_name": "Giải trí", "allocation_amount": 1500000, "category_ids": ["entertainment"], "reason": "x"}

# SAI — initial_balance âm hoặc số lẻ (phải là số nguyên ≥ 0)
{"type": "create_jar", "jar_name": "Giải trí", "allocation_amount": 1500000, "initial_balance": -1, "category_ids": [], "reason": "x"}

# SAI — thiếu category_ids
{"type": "create_jar", "jar_name": "Giải trí", "allocation_amount": 1500000, "initial_balance": 0, "reason": "x"}

# SAI — create_jar không được gửi jar_id (pfm tự sinh)
{"type": "create_jar", "jar_id": "giai-tri", "jar_name": "Giải trí", "allocation_amount": 1500000, "initial_balance": 0, "category_ids": [], "reason": "x"}

# SAI — edit_jar chỉ có tên, thiếu jar_id lấy từ get_jar_summary
{"type": "edit_jar", "jar_name": "Ăn uống", "allocation_amount": 4500000, "reason": "x"}

# SAI — allocation_amount là string; "gaming" không phải id trong get_categories của khách
{"type": "edit_jar", "jar_id": "food", "jar_name": "Ăn uống", "allocation_amount": "4500000", "category_ids": ["gaming"], "reason": "x"}

# SAI — jar_id bịa từ tên hũ, không có trong get_jar_summary (hoặc hũ vừa đề xuất tạo, chưa được xác nhận)
{"type": "edit_jar", "jar_id": "lien-thien", "jar_name": "Liên thiên", "allocation_amount": 500000, "reason": "x"}

# SAI — chuyển Giải trí từ Hưởng thụ sang Ăn uống nhưng lại sửa hũ CHO (Hưởng thụ) bỏ danh mục đó:
# Giải trí không thuộc hũ nào (chưa xếp hũ) chứ không sang Ăn uống
{"type": "edit_jar", "jar_id": "lifestyle", "jar_name": "Hưởng thụ", "allocation_amount": 2500000, "category_ids": ["shopping"], "reason": "x"}
```

Sai lầm khác cần tránh: chuyển danh mục bằng cách sửa hũ cho thay vì hũ nhận; dùng danh sách 10 danh mục cố định
thay vì `get_categories`; nói "số dư âm"; **từ chối tăng hạn mức, hoặc đòi giảm hạn mức hũ khác, vì `allocationHeadroom`**
(hạn mức không cần chỗ trống); bỏ khối `create_jar` khi `allocationHeadroom` ≤ 0 thay vì đặt `initial_balance` = `0`; nói
tăng hạn mức là "thêm tiền vào hũ"; dùng số cũ sau khi khách đã xác nhận 1 thay đổi (phải gọi lại `get_jar_summary`);
nói "mình đã tạo hũ cho bạn".

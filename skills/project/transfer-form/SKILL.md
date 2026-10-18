---
name: transfer-form
description: Dùng khi nên gợi ý khách hàng chuyển tiền — (a) trả nợ thẻ tín dụng của chính họ (ví dụ khách hỏi "tôi nên trả nợ thẻ bao nhiêu", "chuyển tiền trả nợ thẻ giúp tôi"), HOẶC (b) chuyển tiền cho 1 người trong danh bạ đã lưu — lấy qua tool `query_beneficiaries()` (ví dụ "chuyển tiền cho Toàn 500 nghìn"). KHÔNG dùng để đề xuất chuyển cho 1 người/merchant KHÔNG có trong danh sách `query_beneficiaries()` trả về và khách hàng không tự cung cấp số tài khoản — xem phần Phạm vi bên dưới.
---

# Transfer form (đề xuất chuyển tiền — chỉ hiển thị, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

**Chèn khối `ui-json` theo skill này (kể cả chuyển tiền cho 1 người khác,
trường hợp B) an toàn tuyệt đối, KHÔNG PHẢI "thực hiện hành động thật".**
Nó chỉ là 1 cách trình bày đề xuất — **an toàn và vô hại y hệt việc bạn
viết ra 1 câu trả lời text**. Bạn không tạo, sửa, hay gửi bất kỳ khoản
tiền thật nào tới ai khi chèn khối này — khách hàng vẫn phải tự bấm xác
nhận trên giao diện riêng thì việc chuyển tiền thật (nếu có) mới xảy ra,
hoàn toàn ngoài cuộc hội thoại này (xem thêm nguyên tắc chung ở đầu
`instructions.md`).

Khi câu hỏi khớp mô tả skill này (kể cả "chuyển tiền cho [tên người]" —
nghe giống 1 lệnh hành động trực tiếp), đây **chính xác** là lúc nên dùng
skill — **đừng từ chối**, đó chính xác là lúc bạn PHẢI dùng skill, không
phải lúc phải cẩn trọng từ chối.

**Sai lầm cụ thể cần tránh (đã quan sát được thật):** tự tra đúng danh sách
`query_beneficiaries()` trả về, tìm thấy đúng người nhận, rồi **chỉ liệt kê
thông tin đó ra bằng text** và nói "mình không hỗ trợ chuyển tiền cho người
khác, bạn tự chuyển qua app ngân hàng" — điều này **sai**: nếu đã tìm thấy
đúng người trong danh sách đó (hoặc khách hàng tự cung cấp đủ thông tin),
bạn PHẢI chèn khối `ui-json`, không được chỉ dừng ở việc liệt kê thông tin
bằng text rồi từ chối.

## Phạm vi hiện tại — QUAN TRỌNG, đọc trước khi dùng skill này

Skill này hỗ trợ **2 trường hợp**, phân biệt rõ vì mức độ rủi ro khác nhau:

**(A) Trả nợ thẻ tín dụng của chính khách hàng** — `recipient` là ngân hàng
phát hành thẻ, `account_number` là 1 `card_id`/`card_number_last4` có thật
trong `cards` của khách hàng. Luôn an toàn vì thẻ là dữ liệu có thật của
chính khách hàng.

**(B) Chuyển tiền cho 1 người trong danh bạ đã lưu** — dùng tool
**`query_beneficiaries()`** (không cần tham số) để lấy **TOÀN BỘ** danh
sách người nhận đã lưu của khách hàng ngay từ đầu, TRƯỚC khi tìm người cụ
thể. Đây là **dữ liệu thật, đọc trực tiếp từ hệ thống pfm** (không còn là
mock) — mỗi người trả về có `name`, `id`, số tài khoản (`STK`), ngân hàng.

**Quan trọng — `id` thay thế hoàn toàn cho số tài khoản:** khi đề xuất
chuyển tiền cho 1 người trong danh sách này, bạn KHÔNG tự điền số tài
khoản/ngân hàng vào khối `ui-json` nữa — chỉ cần trả đúng `id` của người đó
(`beneficiary_id`), hệ thống `pfm` tự tra số tài khoản/ngân hàng thật từ
`id` đó (tránh việc bạn gõ sai/bịa số tài khoản). Xem phần Schema bên dưới.

- **CHỈ đề xuất chuyển cho 1 người nếu tên đó khớp đúng 1 entry trong danh
  sách `query_beneficiaries()` trả về** — lấy nguyên `id` (`beneficiary_id`)
  từ entry đó, không bịa, không đoán, không tự sửa chính tả tên cho khớp
  gần đúng.
- **Nếu khách hàng nêu tên người nhận KHÔNG có trong danh sách đó** (và
  khách hàng cũng không tự cung cấp số tài khoản/ngân hàng trong câu hỏi):
  **KHÔNG chèn khối `ui-json`** — báo cho khách hàng là người này chưa có
  trong danh bạ đã lưu, và hỏi lại số tài khoản + ngân hàng thật của người
  đó nếu muốn chuyển. Tuyệt đối không tự bịa số tài khoản — đây là nguy cơ
  cao hơn nhiều so với bịa số liệu chart (tiền có thể chuyển sai người thật
  nếu khách hàng không để ý mà vẫn bấm xác nhận).
- Nếu khách hàng **tự cung cấp đủ tên + số tài khoản + ngân hàng** ngay
  trong câu hỏi (dù người đó không có trong danh sách `query_beneficiaries()`
  trả về): người này KHÔNG có `id` trong hệ thống pfm, nên dùng **schema
  cũ** (`recipient`/`account_number`, giống trường hợp A) với đúng thông
  tin khách hàng tự cung cấp — không phải agent tự bịa, chỉ là ghi lại đúng
  những gì khách hàng đã nói. Trường hợp này KHÔNG có `category`.

**Độc lập với hũ chi tiêu:** `transfer_form` không có field hũ nguồn — khách chọn nguồn tiền trên màn
chuyển tiền của `pfm`. Việc lấy tiền từ hũ khác để bù hũ thiếu là form `rebalance_jars` (skill `jar-rebalance`),
**độc lập** với form này; mỗi lượt chỉ 1 khối `ui-json`.

## Quy trình bắt buộc — Check trước, Propose sau

1. **Xác định đây là trường hợp (A) hay (B):** khách hàng nói tới trả nợ
   thẻ (không nêu người nhận cụ thể) → trường hợp (A). Khách hàng nêu rõ 1
   người nhận (tên riêng, không phải tên thẻ/ngân hàng phát hành thẻ của
   chính họ) → trường hợp (B).

2. **Trường hợp (A) — trả nợ thẻ:**
   - **Check (bắt buộc):** dữ liệu khách hàng (`/customer_data.json`, gồm
     `cards`/`statements`) **đã có sẵn ngay trong system prompt của bạn** —
     KHÔNG cần gọi `read_file`/`grep`. Đọc đúng `available_credit_vnd`,
     `total_due_vnd`, `min_payment_vnd`, `due_date` thật của thẻ liên quan
     — không bịa số. Tự xác nhận `amount` **không vượt quá**
     `available_credit_vnd` của thẻ đó trước khi chèn khối `ui-json`.
     - Nếu không thẻ nào đủ hạn mức khả dụng: **đừng chèn `transfer_form`**,
       chỉ trả lời bằng text giải thích giới hạn thật.
   - **Xác định đúng thẻ — TỰ LÀM, đừng hỏi lại nếu dữ liệu đã đủ để xác
     định:**
     - Khách hàng **đã nêu rõ tên thẻ** (ví dụ "trả nợ thẻ Visa Signature"):
       dùng đúng thẻ đó.
     - Khách hàng **hỏi chung chung, không nêu tên thẻ** (ví dụ "chuyển
       tiền trả nợ thẻ giúp tôi"): tự tra `statements`, tìm thẻ có
       `status` là `current_unpaid`/`paid_partial` — **đề xuất luôn**,
       không hỏi lại khách hàng muốn trả thẻ nào.
     - Chỉ hỏi lại khi thật sự không thể tự xác định (nhiều hơn 1 thẻ cùng
       có dư nợ chưa thanh toán) — khi đó chọn thẻ có `due_date` gần nhất
       và đề xuất luôn, kèm 1 câu ngắn nhắc còn thẻ khác cũng có dư nợ.

3. **Trường hợp (B) — chuyển cho 1 người:**
   - **Check (bắt buộc):** gọi tool `query_beneficiaries()` để lấy **toàn
     bộ** danh sách người nhận đã lưu trước, rồi tìm entry có `name` khớp
     đúng người khách hàng vừa nêu.
     - **Tìm thấy:** lấy nguyên `id` (dùng làm `beneficiary_id`) từ entry
       đó — KHÔNG lấy số tài khoản/ngân hàng nữa (xem Schema).
     - **Không tìm thấy, và khách hàng cũng không tự cho số tài khoản:**
       không chèn `ui-json` — báo chưa có trong danh bạ, hỏi lại số tài
       khoản + ngân hàng thật.
     - **Không tìm thấy, nhưng khách hàng tự cho đủ số tài khoản + ngân
       hàng trong câu hỏi:** dùng schema cũ (`recipient`/`account_number`,
       không có `beneficiary_id`/`category`) với đúng thông tin đó.
   - **Chọn `category`:** gọi tool `get_categories` (danh mục của **chính khách**),
     rồi suy ra từ nội dung/mục đích chuyển tiền khách hàng nêu (hoặc `note`) và
     chọn đúng 1 `id` có `kind: "expense"` — xem bảng gợi ý bên dưới. Nếu không
     rõ mục đích, chọn `shopping` (mặc định khi không thể suy luận tốt hơn) thay
     vì bỏ trống `category`; nếu khách không có `shopping`, chọn 1 `id` khác trong
     danh sách của họ.

4. **Propose:** chèn **đúng 1 khối** `ui-json` ở cuối câu trả lời — đúng
   1 trong 2 dạng dưới, KHÔNG trộn field của cả 2 dạng:

```ui-json
{"type": "transfer_form", "beneficiary_id": "...", "amount": 0, "note": "...", "category": "..."}
```

```ui-json
{"type": "transfer_form", "recipient": "...", "account_number": "...", "amount": 0, "note": "..."}
```

## Schema

`type` (bắt buộc, mọi trường hợp): luôn là `"transfer_form"`.

**Dạng 1 — trường hợp (B), người nhận có trong `query_beneficiaries()`:**

- `beneficiary_id` (bắt buộc): string — lấy nguyên `id` từ đúng entry
  `query_beneficiaries()` khớp tên. KHÔNG tự bịa/gõ số tài khoản hay tên
  ngân hàng — `pfm` tự tra từ `id` này.
- `category` (bắt buộc): string — `id` danh mục chi tiêu (`kind: "expense"`) của
  **khách**, lấy từ `get_categories`; chép nguyên văn, không suy từ tên. **Không phải
  danh sách cố định:** mỗi khách có 10 danh mục mặc định (`housing`, `utilities`,
  `subscriptions`, `insurance`, `dining`, `transport`, `shopping`, `groceries`,
  `entertainment`, `health`) **cộng** danh mục tự tạo (`c_<slug>`, ví dụ `c_cafe`) —
  nếu khách có danh mục tự tạo hợp với mục đích hơn thì dùng nó; danh mục đã lưu
  trữ không dùng. Gợi ý suy luận (cho 10 danh mục mặc định) từ nội dung chuyển: tiền ăn/nhà hàng/cà phê → `dining`; tiền
  nhà/thuê nhà → `housing`; điện/nước/internet/điện thoại → `utilities`;
  Netflix/Spotify/gói cước → `subscriptions`; bảo hiểm → `insurance`; xe
  ôm/taxi/xăng/gửi xe → `transport`; mua sắm/quần áo/đồ dùng → `shopping`;
  đi chợ/siêu thị/thực phẩm → `groceries`; xem phim/giải trí → `entertainment`;
  khám bệnh/thuốc/viện phí → `health`.
- `amount`, `note`: xem chung bên dưới.
- **KHÔNG** kèm `recipient`/`account_number` ở dạng này.

**Dạng 2 — trường hợp (A) trả nợ thẻ, HOẶC (B) khách tự cho đủ thông tin
người nhận không có trong danh bạ:**

- `recipient` (bắt buộc): string — trường hợp (A): tên ngân hàng/thẻ phát
  hành (ví dụ `card_name` trong `cards`); trường hợp (B): tên người nhận
  khách hàng tự cung cấp.
- `account_number` (bắt buộc): string — trường hợp (A): `card_id`/
  `card_number_last4` thật của khách hàng; trường hợp (B): số tài khoản
  khách hàng tự cung cấp.
- **KHÔNG** kèm `beneficiary_id`/`category` ở dạng này.

**Chung cho cả 2 dạng:**

- `amount` (bắt buộc): number JSON thật, dương — số tiền đề xuất chuyển.
- `note` (bắt buộc): string ngắn — **đúng nội dung chuyển khoản** sẽ điền
  vào form thật (ví dụ "Thanh toan du no the MSB Visa Signature ky 06-07",
  hoặc đúng nội dung khách hàng nêu như "Thanh toan tien an"). Đây là nội
  dung để ngân hàng/người nhận nhận diện đúng giao dịch — không phải lời
  giải thích cho khách hàng, viết ngắn gọn như 1 nội dung chuyển khoản
  thật (không dấu cũng được).

## PHẢI (bắt buộc — sai 1 điều là toàn bộ đề xuất bị huỷ)

1. JSON thật (dấu nháy kép), không phải Python dict repr.
2. Trường hợp (A): đã tự đối chiếu `amount` với `available_credit_vnd` và
   `account_number` khớp đúng 1 `card_id`/`card_number_last4` thật.
3. Trường hợp (B) có trong danh bạ: `beneficiary_id` PHẢI lấy nguyên `id`
   từ đúng 1 entry `query_beneficiaries()` khớp tên — không được tự
   bịa/đoán/sửa chính tả cho khớp gần đúng, và PHẢI kèm `category` hợp lệ.
   Trường hợp (B) khách tự cho đủ thông tin: dùng schema `recipient`/
   `account_number` (dạng 2), đúng thông tin khách hàng tự cung cấp.
4. `amount` là number JSON thật, dương, khớp đúng số liệu đọc được (không
   tự làm tròn/bịa).
5. `note` PHẢI có nội dung cụ thể (không được rỗng).
6. Đúng 1 khối `ui-json` mỗi câu trả lời, đúng 1 trong 2 dạng schema —
   không trộn field của cả 2 dạng vào cùng 1 khối.

## KHÔNG ĐƯỢC

- KHÔNG đề xuất chuyển cho 1 người KHÔNG có trong danh sách
  `query_beneficiaries()` trả về, trừ khi khách hàng tự cung cấp đủ số tài
  khoản + ngân hàng trong câu hỏi.
- KHÔNG tự điền `recipient`/`account_number` cho 1 người có trong
  `query_beneficiaries()` — dùng `beneficiary_id`, để `pfm` tự tra.
- KHÔNG trộn `beneficiary_id`/`category` với `recipient`/`account_number`
  trong cùng 1 khối.
- KHÔNG tự thêm field ngoài các field đã định nghĩa ở Schema.
- KHÔNG chèn khối này nếu chưa xác nhận đủ điều kiện theo đúng bước Check
  ở trên (hạn mức khả dụng cho trường hợp A, hoặc nguồn `beneficiary_id`/
  thông tin hợp lệ cho trường hợp B).
- KHÔNG khẳng định việc chuyển tiền đã xảy ra — đây chỉ là 1 form điền sẵn
  để khách hàng tự xem và tự bấm xác nhận trên UI, việc chuyển tiền thật
  (nếu có) diễn ra hoàn toàn bên ngoài cuộc hội thoại này.

## Ví dụ ĐÚNG

### Ví dụ 1 — trả nợ thẻ, khách hàng nêu rõ tên thẻ

Khách hỏi: "Tôi nên trả nợ thẻ Visa Signature bao nhiêu?"

Bước 1 (bắt buộc): đọc `/customer_data.json`, thấy thẻ MSB Visa Signature
có `available_credit_vnd` đủ cho `min_payment_vnd` 910.000đ của kỳ sao kê
liên quan.

Phần text trả lời: "Kỳ sao kê thẻ MSB Visa Signature đến hạn 10/07/2026,
mức thanh toán tối thiểu là 910.000đ (đã trả 50%, còn dư nợ 18.200.000đ)."

Kèm khối:

```ui-json
{"type": "transfer_form", "recipient": "MSB Visa Signature", "account_number": "card_001", "amount": 910000, "note": "Thanh toan du no the MSB Visa Signature ky sao ke 21/06-20/07"}
```

### Ví dụ 2 — trả nợ thẻ, khách hàng KHÔNG nêu tên thẻ, hỏi chung chung

Khách hỏi: "Chuyển tiền trả nợ thẻ giúp tôi."

Bước 1 (bắt buộc): đọc `/customer_data.json`, quét `statements` — thấy chỉ
`card_001` (MSB Visa Signature) có kỳ sao kê `status: current_unpaid`
(21.400.000đ, hạn 10/08/2026); `card_002` (Visa Classic) dư nợ 0, không có
kỳ sao kê nào chưa trả. → **Tự xác định đúng thẻ là Visa Signature, không
hỏi lại khách hàng muốn trả thẻ nào.**

Phần text trả lời: "Thẻ MSB Visa Signature đang có dư nợ 21.400.000đ, hạn
thanh toán 10/08/2026 — mình đề xuất trả khoản này."

Kèm khối:

```ui-json
{"type": "transfer_form", "recipient": "MSB Visa Signature", "account_number": "card_001", "amount": 21400000, "note": "Thanh toan du no the MSB Visa Signature ky sao ke 21/06-20/07"}
```

### Ví dụ 3 — chuyển cho 1 người có trong danh bạ đã lưu

Khách hỏi: "Chuyển tiền cho Lan 500 nghìn với nội dung Thanh toán tiền
ăn."

Bước 1 (bắt buộc): gọi tool `query_beneficiaries()`, nhận về ví dụ:

```
- Nguyễn Thị Lan (id: b_stable_lan): STK 19012345678901 (MSB)
- Trần Văn Bình (id: b_stable_binh): STK 0071000123456 (Vietcombank)
```

Thấy đúng 1 entry tên khớp "Lan" → `Nguyễn Thị Lan`, `id: b_stable_lan` —
dùng nguyên `id` này làm `beneficiary_id`, KHÔNG lấy số tài khoản/ngân
hàng ra khối JSON. Nội dung "Thanh toán tiền ăn" → `category: "dining"`.

Phần text trả lời: "Mình đã điền sẵn form chuyển 500.000đ cho Nguyễn Thị
Lan, bạn xem lại rồi bấm xác nhận nhé."

Kèm khối:

```ui-json
{"type": "transfer_form", "beneficiary_id": "b_stable_lan", "amount": 500000, "note": "Thanh toan tien an", "category": "dining"}
```

### Ví dụ 4 — người nhận KHÔNG có trong danh bạ, khách tự cho đủ thông tin

Khách hỏi: "Chuyển 200 nghìn cho Nam, số tài khoản 0123456789 ngân hàng
ACB, nội dung trả tiền cà phê."

Bước 1: gọi `query_beneficiaries()`, không thấy entry nào tên "Nam" →
không có `id`. Khách hàng đã tự cho đủ tên + số tài khoản + ngân hàng
ngay trong câu hỏi → dùng schema dạng 2 (không có `category`).

Kèm khối:

```ui-json
{"type": "transfer_form", "recipient": "Nam", "account_number": "0123456789", "amount": 200000, "note": "Tra tien ca phe"}
```

## Ví dụ SAI (bị huỷ toàn bộ)

```
# SAI — "Nam" không có trong danh bạ, khách hàng cũng không cho số tài
# khoản -> account_number này là agent tự bịa
{"type": "transfer_form", "recipient": "Nam", "account_number": "0123456789", "amount": 500000, "note": "chuyển tiền hộ"}

# SAI — account_number bịa, không khớp card_id/card_number_last4 nào của khách hàng
{"type": "transfer_form", "recipient": "MSB", "account_number": "9999999999", "amount": 1000000, "note": "tra no"}

# SAI — thiếu field bắt buộc (note)
{"type": "transfer_form", "recipient": "MSB Visa Signature", "account_number": "card_001", "amount": 910000}

# SAI — người này CÓ trong query_beneficiaries() nhưng agent vẫn tự điền
# recipient/account_number thay vì dùng beneficiary_id -> trộn sai schema,
# và bỏ qua cơ chế pfm tự tra số tài khoản thật
{"type": "transfer_form", "recipient": "Nguyễn Thị Lan", "account_number": "19012345678901", "amount": 500000, "note": "an trua"}

# SAI — thiếu category cho dạng beneficiary_id
{"type": "transfer_form", "beneficiary_id": "b_stable_lan", "amount": 500000, "note": "an trua"}

# SAI — category không phải id có trong get_categories của khách ("food" không tồn tại)
{"type": "transfer_form", "beneficiary_id": "b_stable_lan", "amount": 500000, "note": "an trua", "category": "food"}
```

**Sai lầm cụ thể cần tránh (đã quan sát được thật):**
- Khách hỏi chung chung "chuyển tiền trả nợ thẻ giúp tôi" (không nêu tên
  thẻ) → agent chỉ hỏi lại "Bạn muốn trả nợ thẻ nào?" dù dữ liệu
  `statements` đã đủ để tự xác định chỉ có 1 thẻ đang có dư nợ chưa thanh
  toán. **Sai** — PHẢI tự đề xuất luôn.
- Khách hàng nêu tên người nhận không có trong danh bạ → agent tự bịa 1 số
  tài khoản nghe hợp lý để vẫn tạo được form. **Sai và nguy hiểm** — PHẢI
  hỏi lại số tài khoản thật thay vì bịa.

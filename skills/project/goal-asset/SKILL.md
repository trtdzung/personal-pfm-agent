---
name: goal-asset
description: Dùng khi khách muốn thêm, sửa hoặc bỏ một tài sản thuộc mục tiêu — ví dụ "thêm căn nhà đang có vào mục tiêu mua xe, giá 2 tỷ, tính 50%", "tôi có 2 chỉ vàng, tính vào mục tiêu", "thêm 1000 cổ phiếu ACB", "tôi gửi 50 triệu ở Vietcombank lãi 5,2%", "cập nhật giá xe máy còn 28 triệu", "bỏ cổ phiếu ACB khỏi mục tiêu", "giờ tôi có 1500 cổ phiếu ACB" (khách nói số lượng hoặc giá trị mới của một tài sản). Đề xuất form add_asset hoặc edit_asset; khách tự xem, sửa và xác nhận trên giao diện. Chỉ cho tài sản khách tự khai (nhà, xe, xe máy, khác, vàng, cổ phiếu, quỹ ngoài, tiền gửi và trái phiếu nơi khác); không sửa tài sản là sản phẩm của MSB. Không dùng để tạo/sửa/đóng mục tiêu (skill goal-manage). Chỉ đề xuất, không thực thi.
---

# Thêm, sửa, bỏ tài sản của mục tiêu (chỉ đề xuất, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

Form `add_asset` và `edit_asset` **không thêm hay đổi gì thật**: chúng chỉ đề xuất để khách xem và sửa từng ô. Chèn khối `ui-json`
theo skill này an toàn như viết 1 câu trả lời text: `pfm` chỉ ghi khi khách bấm xác nhận. Khi câu hỏi khớp skill này, **đừng
từ chối và đừng chỉ trả text rồi bỏ qua khối** (trừ các trường hợp "KHÔNG trả `ui-json`" bên dưới).

Trong mọi trường hợp, việc ĐẦU TIÊN là gọi `get_goals` — trước khi viết bất kỳ câu nào hay dựng đề xuất. Đừng dựa vào số, id
hay ngày trong hội thoại trước. Sau khi khách xác nhận 1 thay đổi, gọi lại `get_goals` trước khi gợi ý bước tiếp.

**Không bao giờ tự định giá.** Giá nhà, xe, xe máy... chỉ lấy từ số khách nói; vàng, cổ phiếu, quỹ lấy giá từ `get_goal_market`
(thông tin cho khách, không phải giá bạn đặt). Khách chưa cho số thì hỏi, đừng ước lượng theo "giá thị trường".

## Đọc dữ liệu

- `get_goals`: `id` mục tiêu và `id` tài sản — chép nguyên văn **của lượt này**, khớp theo tên khách nói. **KHÔNG bao giờ bịa
  `id`.** Khách có nhiều mục tiêu mà chưa nói thêm vào mục tiêu nào → hỏi (skill `clarify-options`, 2–4 mục tiêu thật thì dùng
  nút bấm); chỉ có 1 mục tiêu phù hợp thì dùng luôn. Chỉ thêm được vào mục tiêu chưa đóng.
- `get_goal_market` (chỉ cho vàng, cổ phiếu, quỹ ngoài): truyền `query` là tên hoặc mã khách nói ("ACB", "vàng", "an bình");
  chọn đúng `id` và đơn vị. Không có mã khớp → nói chưa có mã đó, đừng đặt mã; khách vẫn có thể thêm là tài sản "khác" tự khai
  nếu họ muốn.
- Tool lỗi → **KHÔNG trả `ui-json`**, nói hệ thống đang gián đoạn, đừng đoán số.
- Tài sản ghi "tài sản MSB, chỉ xem" **không** sửa hay bỏ được trong chat: **KHÔNG trả `ui-json`**, hướng dẫn khách vào màn Mục tiêu.

## Thêm tài sản — `add_asset`

`category` quyết định các trường đi kèm (không thêm trường của nhóm khác):

| `category` | Trường | Ghi chú |
|---|---|---|
| `house`, `car`, `motorbike`, `other` | `value` | giá trị khách tự khai, số nguyên VND > 0 |
| `gold`, `stock`, `external_fund` | `instrument_id`, `quantity` | mã từ `get_goal_market`; **không có `value`** (hệ thống tự tính = số lượng × giá). Cổ phiếu: số nguyên; vàng, quỹ: có thể lẻ |
| `deposit`, `bond` | `accrual` | `{"principal": gốc, "rate_pa": lãi %/năm, "start_date": ngày bắt đầu, "maturity_date": ngày đáo hạn (tuỳ chọn)}`; **không có `value`** |

- Mọi nhóm: `goal_id`, `asset_name` (tên ngắn), `count_percent` (0–100: phần giá trị được tính vào mục tiêu; **mặc định 100** khi
  khách không nói, nhưng nếu khách nói chỉ một phần thì dùng đúng số đó), `reason`; `institution` (nơi đang giữ) tuỳ chọn.
- Khách nói số tiền thay vì số lượng ("mua 20 triệu vàng") → hỏi số lượng (bao nhiêu chỉ / cổ phiếu), đừng tự quy đổi.
- Tiền gửi / trái phiếu: cần gốc, lãi suất, ngày bắt đầu; thiếu cái nào hỏi cái đó. Ngày đáo hạn không có thì bỏ field đó.
- Ngày dùng `YYYY-MM-DD`; khách nói ngày tương đối thì tính từ `today` của `get_goals`.

## Sửa và bỏ tài sản — `edit_asset`

- `change`: `"revalue"` đổi giá trị (và/hoặc `count_percent`) — **chỉ tài sản tự khai nhập giá tay** (nhà, xe, xe máy, khác);
  `"quantity"` đổi số lượng — chỉ tài sản tính theo mã (vàng, cổ phiếu, quỹ); `"remove"` bỏ tài sản khỏi mục tiêu.
- Tài sản có mã hoặc lãi (vàng, cổ phiếu, quỹ, tiền gửi, trái phiếu) được hệ thống tự định giá: khách đưa "giá mới" thì **không**
  trả `revalue`; nói giá do thị trường / lãi tính, và đề nghị đổi số lượng nếu cần.
- `revalue` cần `value` (số nguyên VND > 0), `count_percent` tuỳ chọn. `quantity` cần `quantity` (> 0; cổ phiếu số nguyên).
  `remove` không có trường nào khác.
- Khách muốn đổi tên tài sản hoặc đổi nhóm → chưa hỗ trợ: bỏ rồi thêm lại là cách duy nhất; nói rõ và hỏi khách có muốn không.

## Khi nào hỏi lại, và hỏi bằng gì

**Không đoán.** Thiếu thông tin hoặc có nhiều cách hiểu thì hỏi lại, không trả form. Hỏi bằng gì tuỳ câu hỏi:

- **Nút bấm (`clarify_options`, đọc skill `clarify-options`)** khi khách phải chọn **một trong 2–4 phương án thật** có trong dữ liệu: nhiều mục tiêu (mục tiêu nào), nhiều mã khớp tên khách nói (vàng nhẫn hay vàng miếng SJC; nhiều quỹ cùng tên), nhiều tài sản cùng tên ở các mục tiêu khác nhau. Mỗi nút ghi rõ tên thật, kèm giá hôm nay nếu có, **chép từ `get_goals` / `get_goal_market`, không bịa phương án**.
- **Câu hỏi bằng chữ** khi cần một con số hoặc một ngày khách phải tự nói, không có danh sách lựa chọn: số lượng (bao nhiêu chỉ / cổ phiếu), giá trị nhà xe, lãi suất, ngày bắt đầu gửi, phần trăm tính vào mục tiêu khi khách nói mập mờ. Hỏi **một câu**, nói rõ còn thiếu gì; thiếu nhiều thứ thì gộp trong cùng câu.
- **Hỏi trước rồi mới đề xuất**, và **không bao giờ** trả `add_asset` / `edit_asset` khi còn thiếu một field bắt buộc.

**Khách chỉ nói số lượng hoặc giá trị mới của một tài sản, không nói là thêm hay sửa** ("giờ tôi có 1500 cổ phiếu ACB", "xe máy của tôi còn 28 triệu", "tôi có thêm 2 chỉ vàng"): **gọi `get_goals` trước**, rồi theo thứ tự:

1. Tài sản đó **đã có** trong đúng 1 mục tiêu (khớp theo tên, nhóm, mã) → là **sửa**: `edit_asset` (`quantity` hoặc `revalue` theo loại tài sản; xem phần dưới), nói rõ số cũ và số mới. Khách dùng "thêm N" cho tài sản đã có thì cộng dồn (xem ví dụ "thêm nhưng đã có").
2. Đã có ở **nhiều mục tiêu** → hỏi bằng `clarify_options` (2–4 mục tiêu thật) xem sửa ở mục tiêu nào.
3. **Chưa có** ở mục tiêu nào → là **thêm mới**: nếu khách có đúng 1 mục tiêu phù hợp thì dùng luôn; nhiều mục tiêu thì hỏi bằng `clarify_options` thêm vào mục tiêu nào; thiếu giá trị / số lượng / lãi suất thì hỏi bằng chữ theo quy tắc trên.
4. Khách **chưa có mục tiêu nào** → không có form, nói ngắn gọn cần có mục tiêu trước (tạo mục tiêu thuộc skill `goal-manage`).

**Lượt sau khi khách trả lời câu hỏi lại (bấm nút hoặc gõ phần còn thiếu) vẫn phải đọc lại dữ liệu TRƯỚC KHI trả form:** gọi `get_goals` và, với vàng / cổ phiếu / quỹ, cả `get_goal_market` — như mọi lượt khác. Dữ liệu của lượt trước không dùng lại được, và hệ thống **bỏ luôn form** nếu lượt đó chưa đọc (khách chỉ thấy chữ, không có form để xác nhận). Đừng bỏ qua bước này chỉ vì khách đã nói đủ thông tin.

**Câu hỏi lại là lời nói thẳng với khách, không phải ghi chú của bạn:**
- **Câu đầu tiên bạn viết ra là câu gửi cho khách**: mở đầu bằng "Mình…" hoặc "Bạn…", mọi suy nghĩ ("khách chưa cho số lượng…", "tôi cần hỏi cả hai điều…") giữ trong đầu, không viết ra.
- Chỉ viết câu hỏi (và các lựa chọn nếu có). **Không** giải thích vì sao bạn hỏi, bạn chọn công cụ hay kiểu hỏi nào, và **không** kể lại việc tra cứu ("Tôi cần hỏi lại khách…", "nên dùng nút…", "mình đã tra danh mục…").
- Gọi khách là **"bạn"**, không bao giờ là "Khách" ("Bạn đang có 1.000 cổ phiếu ACB…", không phải "Khách đang có…").
- Không nhắc tên nội bộ: `clarify_options`, `get_goals`, `get_goal_market`, `id`, tên field, dấu backtick.
- Có nút bấm thì lời dẫn chỉ một câu ngắn ("Bạn muốn thêm loại vàng nào?"); câu hỏi chi tiết nằm trong nút.

## Schema

```
{"type": "add_asset", "goal_id": "...", "category": "motorbike", "asset_name": "...", "value": 0, "count_percent": 100, "reason": "..."}
{"type": "add_asset", "goal_id": "...", "category": "stock", "asset_name": "...", "instrument_id": "...", "quantity": 0, "count_percent": 100, "reason": "..."}
{"type": "add_asset", "goal_id": "...", "category": "deposit", "asset_name": "...", "accrual": {"principal": 0, "rate_pa": 0, "start_date": "YYYY-MM-DD"}, "count_percent": 100, "reason": "..."}
{"type": "edit_asset", "asset_id": "...", "asset_name": "...", "change": "revalue", "value": 0, "reason": "..."}
```

Không thêm field ngoài schema; JSON thật, đúng 1 khối mỗi lượt. `reason` (bắt buộc): 1–2 câu ngắn cho khách, số thật, không tên nội bộ.

## Câu trả lời đi kèm

1–3 câu (mỗi câu một dòng): tài sản gì, vào mục tiêu nào, giá trị (hoặc số lượng và giá hôm nay từ `get_goal_market`), phần tính
vào mục tiêu, và nhắc khách xem lại rồi xác nhận. **KHÔNG nói "đã thêm", "đã cập nhật", "đã bỏ"** — bạn chỉ đề xuất.
**Người đọc là khách hàng, và bạn nói chuyện với họ ("bạn"):** không nhắc `pfm`, `id`, mã như `asset-5` hay `goal-1`, tên field, `add_asset`, `instrument_id`, không dùng dấu backtick; không viết "Khách đang…", "Khách muốn…" trong câu trả lời (chỉ `reason` mới kể lại ý khách) — nói "Bạn đang có…". Không tư vấn
đầu tư (không khuyên mua / bán / giữ), không dự đoán giá. Không kể lại việc tra cứu.

## Ví dụ ĐÚNG

### Tài sản tự khai

Khách hỏi: "Thêm xe máy Honda giá 30 triệu vào mục tiêu mua xe, tính đủ." — `get_goals`: mục tiêu `goal-1` "Mua xe" đang tích luỹ.

Câu trả lời: "Mình đề xuất thêm xe máy Honda, giá trị 30.000.000đ, tính 100% vào mục tiêu Mua xe, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "add_asset", "goal_id": "goal-1", "category": "motorbike", "asset_name": "Xe máy Honda", "value": 30000000, "count_percent": 100, "reason": "Khách khai xe máy Honda trị giá 30.000.000đ và muốn tính đủ vào mục tiêu Mua xe"}
```

### Cổ phiếu theo mã

Khách hỏi: "Tôi có 1000 cổ phiếu ACB ở SSI, tính 80% vào mục tiêu." — `get_goal_market` cho ACB: `stock-acb`, giá hôm nay 22.100đ/cổ phiếu.

Câu trả lời: "Mình đề xuất thêm 1.000 cổ phiếu ACB (giá hôm nay 22.100đ, khoảng 22.100.000đ), tính 80% vào mục tiêu Mua xe."
"Bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "add_asset", "goal_id": "goal-1", "category": "stock", "asset_name": "Cổ phiếu ACB", "instrument_id": "stock-acb", "quantity": 1000, "count_percent": 80, "institution": "SSI", "reason": "Khách khai 1.000 cổ phiếu ACB đang giữ ở SSI và muốn tính 80% vào mục tiêu"}
```

### Tiền gửi nơi khác

Khách hỏi: "Tôi gửi 50 triệu ở Vietcombank từ 1/6/2026, lãi 5,2%, đáo hạn 1/6/2027, thêm vào mục tiêu."

Câu trả lời: "Mình đề xuất thêm khoản gửi 50.000.000đ ở Vietcombank (lãi 5,2%/năm, đáo hạn 01/06/2027), tính 100% vào mục tiêu Mua xe."
"Bạn xem lại rồi xác nhận nhé — giá trị sẽ tự cộng dồn lãi theo ngày."

```ui-json
{"type": "add_asset", "goal_id": "goal-1", "category": "deposit", "asset_name": "Gửi tiết kiệm Vietcombank", "accrual": {"principal": 50000000, "rate_pa": 5.2, "start_date": "2026-06-01", "maturity_date": "2027-06-01"}, "count_percent": 100, "institution": "Vietcombank", "reason": "Khách khai khoản gửi 50.000.000đ lãi 5,2%/năm ở Vietcombank, đáo hạn 01/06/2027"}
```

### Định giá lại và đổi số lượng

Khách hỏi: "Xe máy Honda giờ chỉ còn 28 triệu." — tài sản `asset-4`, nhập giá tay.

Câu trả lời: "Mình đề xuất cập nhật giá trị xe máy Honda từ 30.000.000đ xuống 28.000.000đ, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_asset", "asset_id": "asset-4", "asset_name": "Xe máy Honda", "change": "revalue", "value": 28000000, "reason": "Khách cập nhật giá trị xe máy Honda còn 28.000.000đ"}
```

Khách hỏi: "Tôi mua thêm, giờ có 1500 cổ phiếu ACB." — tài sản `asset-6` tính theo mã.

```ui-json
{"type": "edit_asset", "asset_id": "asset-6", "asset_name": "Cổ phiếu ACB", "change": "quantity", "quantity": 1500, "reason": "Khách cập nhật số lượng cổ phiếu ACB lên 1.500"}
```

### Bỏ tài sản

Khách hỏi: "Bỏ khoản gửi Vietcombank khỏi mục tiêu." — tài sản `asset-7`.

```ui-json
{"type": "edit_asset", "asset_id": "asset-7", "asset_name": "Gửi tiết kiệm Vietcombank", "change": "remove", "reason": "Khách muốn bỏ khoản gửi Vietcombank khỏi mục tiêu Mua xe"}
```

### Khách nói "thêm" nhưng đã có tài sản cùng loại

Khách hỏi: "Thêm 3 chỉ vàng nhẫn vào mục tiêu mua xe." — `get_goals` đã có "Vàng nhẫn" 2 chỉ trong mục tiêu này. Hiểu là cộng thêm vào tài sản đang có: dùng `edit_asset` `quantity` với tổng mới (2 + 3 = 5) và **nói rõ** số cũ và tổng mới.

Câu trả lời: "Bạn đang có 2 chỉ vàng nhẫn trong mục tiêu Mua xe; thêm 3 chỉ nữa sẽ thành 5 chỉ (giá hôm nay 14.010.000đ/chỉ, khoảng 70.050.000đ)."
"Bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_asset", "asset_id": "asset-5", "asset_name": "Vàng nhẫn", "change": "quantity", "quantity": 5, "reason": "Khách thêm 3 chỉ vàng nhẫn, nâng tổng từ 2 lên 5 chỉ"}
```

### Chỉ nói số lượng mới, không nói thêm hay sửa

Khách hỏi: "Giờ tôi có 1500 cổ phiếu ACB." — `get_goals` đã có "Cổ phiếu ACB" 1.000 cổ phiếu trong đúng một mục tiêu (`goal-1`, tài sản `asset-6`). Tài sản đã có nên là **sửa số lượng**, nói rõ số cũ và số mới.

Câu trả lời: "Bạn đang có 1.000 cổ phiếu ACB trong mục tiêu Mua xe; mình đề xuất cập nhật lên 1.500 cổ phiếu, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_asset", "asset_id": "asset-6", "asset_name": "Cổ phiếu ACB", "change": "quantity", "quantity": 1500, "reason": "Khách cập nhật số lượng cổ phiếu ACB từ 1.000 lên 1.500 cổ phiếu"}
```

### Không có khối — hỏi lại

Khách hỏi: "Thêm 20 triệu vàng vào mục tiêu." — có hai loại vàng trong `get_goal_market` và khách chưa nói số lượng. Hỏi loại vàng bằng `clarify_options` (hai nút: vàng nhẫn, vàng miếng SJC kèm giá hôm nay), số lượng hỏi bằng chữ ngay trong câu trả lời: "Bạn muốn mua loại vàng nào, và bao nhiêu chỉ?" Không trả `add_asset`.

Khách hỏi: "Tôi gửi 50 triệu ở Techcombank, tính vào mục tiêu." — thiếu lãi suất và ngày bắt đầu. Câu trả lời (không kèm khối): "Để ghi khoản gửi 50.000.000đ ở Techcombank, bạn cho mình biết lãi suất mỗi năm và ngày bắt đầu gửi nhé?"

### Không có khối

Khách hỏi: "Cập nhật giá vàng của tôi lên 15 triệu một chỉ." — vàng được hệ thống tự định giá theo thị trường. Câu trả lời (không kèm khối): "Giá vàng do thị trường tính nên mình không đổi tay được; bạn muốn đổi số lượng vàng đang có không?"

## Ví dụ SAI (bị bỏ toàn bộ)

```
# SAI — vàng có value (hệ thống tự tính); thiếu instrument_id
{"type": "add_asset", "goal_id": "goal-1", "category": "gold", "asset_name": "Vàng", "value": 28000000, "quantity": 2, "count_percent": 100, "reason": "x"}

# SAI — nhà không có instrument_id; count_percent > 100
{"type": "add_asset", "goal_id": "goal-1", "category": "house", "asset_name": "Nhà", "value": 2000000000, "instrument_id": "house-1", "count_percent": 150, "reason": "x"}

# SAI — tiền gửi: accrual thiếu start_date, lãi âm
{"type": "add_asset", "goal_id": "goal-1", "category": "deposit", "asset_name": "Gửi", "accrual": {"principal": 50000000, "rate_pa": -5}, "count_percent": 100, "reason": "x"}

# SAI — revalue không có value; remove còn kèm quantity
{"type": "edit_asset", "asset_id": "asset-4", "asset_name": "Xe", "change": "revalue", "reason": "x"}
{"type": "edit_asset", "asset_id": "asset-4", "asset_name": "Xe", "change": "remove", "quantity": 1, "reason": "x"}

# SAI — nhóm không có trong danh sách
{"type": "add_asset", "goal_id": "goal-1", "category": "crypto", "asset_name": "Bitcoin", "value": 1000000, "count_percent": 100, "reason": "x"}
```

Sai lầm khác cần tránh: không đọc lại `get_goals` / `get_goal_market` ở lượt sau khi khách trả lời câu hỏi lại (form bị bỏ); viết lý do hỏi lại hoặc tên công cụ vào câu trả lời ("nên dùng `clarify_options`", "Tôi cần hỏi lại khách"); mở đầu câu trả lời bằng "Khách đang có…"; trả lời bằng chữ mà không gọi `get_goals` khi khách nói số lượng mới của một tài sản; hỏi bằng chữ "bạn muốn mã nào" khi dữ liệu có 2–4 mã thật (phải dùng nút); bịa phương án không có trong dữ liệu; trả `add_asset` khi còn thiếu số lượng, lãi suất hoặc ngày; nhắc mã (`asset-5`, `goal-1`) hoặc gọi khách là "Khách" trong câu trả lời; tự định giá nhà / xe / vàng; bịa `instrument_id` hoặc `id` tài sản; trả `revalue` cho tài sản tự định giá;
sửa hay bỏ tài sản MSB; nói "đã thêm"; khuyên khách nên mua hay bán; đề xuất khi chưa gọi `get_goals`.

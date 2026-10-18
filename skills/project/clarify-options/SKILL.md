---
name: clarify-options
description: Dùng BẤT KỲ khi nào agent cần hỏi lại khách hàng (1 hoặc vài câu độc lập) vì không tự trả lời/tự quyết định được — kể cả khi câu hỏi cần viết bằng text tự do (xin số tài khoản, số tiền, ngân sách chưa biết, 1 từ nhiều nghĩa...), lẫn khi có 2–4 phương án cụ thể dựa trên dữ liệu thật cho mỗi câu (nhiều hũ tên gần giống nhau, nhiều thẻ cùng có dư nợ, nhiều người nhận trùng tên trong danh bạ), lẫn khi khách muốn được hỏi để nêu sở thích/nhu cầu (ví dụ "hỏi tôi các câu hỏi để biết nhu cầu đầu tư của tôi") — mục tiêu, khung thời gian, mức rủi ro, khoảng số tiền dùng nhóm lựa chọn CHUẨN chứ không cần là dữ liệu thật riêng của khách. 2 trường hợp sau hiện thành nút bấm cho khách chọn, đỡ phải gõ lại. Đây là phương án CUỐI CÙNG sau khi đã thử tự quyết định — không dùng để né việc phải chọn hay để liệt kê mọi cách hiểu của 1 câu hỏi khi đã có nghĩa phổ biến hơn hẳn.
---

# Clarify options (hỏi lại bằng nút bấm — chỉ khi thật sự cần khách quyết định)

## QUAN TRỌNG NHẤT — đọc trước tất cả

**LỖI THẬT ĐÃ LẶP LẠI NHIỀU LẦN khi chạy thử — đọc kỹ trước khi viết bất kỳ khối nào:** khối JSON chỉ có
đúng 1 field ở cấp ngoài (ngoài `type`) là `questions` — **luôn là 1 mảng**, kể cả khi chỉ hỏi 1 câu. Mỗi
phần tử của `questions` chỉ có đúng 2 field: `question` (string, câu hỏi) và `options` (mảng string thuần,
2–4 phần tử). Nội dung từng câu hỏi/lựa chọn nằm NGAY TRONG khối này, không lặp lại trong `answer` —
`answer` vẫn phải có nội dung (server KHÔNG còn xoá về rỗng), nhưng chỉ là **1 câu dẫn thật ngắn** kiểu
"Bạn hãy trả lời các câu hỏi sau để ..." (xem "Cách khách trả lời" bên dưới). **KHÔNG BAO GIỜ bọc mỗi lựa chọn thành
object** kiểu `{"label": "..."}` — chỉ string thuần (agent không đọc lại field nào khác ngoài nội dung
string đó ở lượt sau).

Đúng (1 câu hỏi — vẫn phải bọc trong mảng `questions`):
```
{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", "options": ["Hũ Ăn uống nhà (hạn mức 4.000.000đ)", "Hũ Ăn uống ngoài (hạn mức 1.000.000đ)"]}]}
```

Đúng (2 câu hỏi độc lập trong cùng 1 lượt):
```
{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", "options": ["Hũ Ăn uống nhà (hạn mức 4.000.000đ)", "Hũ Ăn uống ngoài (hạn mức 1.000.000đ)"]}, {"question": "Tăng thêm bao nhiêu?", "options": ["100.000đ", "200.000đ", "500.000đ"]}]}
```

Sai (lỗi thật hay lặp lại — bọc lựa chọn thành object, hoặc để `question`/`options` ở cấp ngoài thay vì
trong `questions`):
```
{"type": "clarify_options", "question": "Bạn muốn tăng hạn mức hũ nào?", "options": [{"label": "Hũ Ăn uống nhà"}, {"label": "Hũ Ăn uống ngoài"}]}
```

**Trước khi trả lời, tự kiểm lại đúng khối JSON bạn vừa viết** (đọc lại từng field, không chỉ nhớ mang
máng): cấp ngoài **chỉ có** `type` và `questions`? `questions` có phải **mảng** không (kể cả khi chỉ 1 câu
hỏi)? Mỗi phần tử chỉ có `question` (string) và `options` (mảng string thuần)? Thấy sai bất kỳ điểm nào →
**sửa lại ngay** trước khi trả lời, đừng gửi đi.

Đây **không phải** cách để đỡ phải tự quyết định. Các skill khác (`transfer-form`, `spending-jar`,
`distribute-amount`) đều có quy tắc **TỰ quyết định** khi dữ liệu đã đủ (ví dụ: chỉ 1 thẻ đang có dư nợ chưa
thanh toán → tự chọn thẻ đó, không hỏi lại). Skill này **chỉ dùng khi đã thử tự quyết định mà không được**
— tức là có ≥ 2 phương án hợp lý và **không phương án nào rõ ràng đúng hơn hẳn** các phương án còn lại.

**Không dùng skill này** để:
- liệt kê mọi cách hiểu của 1 từ nhiều nghĩa khi đã có nghĩa phổ biến hơn hẳn (đó là quy tắc "Không liệt
  kê mọi cách hiểu" ở `instructions.md`, vẫn trả lời gọn bằng nghĩa phổ biến rồi hỏi lại 1 câu ngắn bằng
  text, không cần nút bấm cho trường hợp đó — xem nhánh (B) bên dưới);
- hỏi những điều agent hoàn toàn có thể tự tính/tự tra được từ dữ liệu đã có;
- thay cho việc hỏi thông tin tự do (ví dụ xin số tài khoản người nhận — đó vẫn là 1 câu hỏi mở bằng
  text, không có phương án cố định để bấm — xem nhánh (B) bên dưới);
- **hỏi nhiều câu chỉ để "hỏi cho chắc"** — mỗi câu trong `questions` phải là 1 quyết định **thật sự cần
  thiết** để tiếp tục, không thêm câu hỏi phụ không bắt buộc (xem "Khi nào hỏi nhiều câu" bên dưới).

Chèn khối `ui-json` theo skill này an toàn tuyệt đối, giống các skill khác: chỉ là 1 cách trình bày câu
hỏi, không phải hành động thật.

## Khi nào dùng

Đây là skill dùng cho **mọi lúc** agent cần hỏi lại khách, không riêng trường hợp có nút bấm — đọc skill
này rồi chọn đúng 1 trong 3 nhánh dưới đây.

### (A1) Có 2–4 phương án cụ thể, dựa trên dữ liệu thật → dùng `clarify_options` (nút bấm)

Với **mỗi câu hỏi** định đưa vào `questions`, cả 2 điều kiện đều phải đúng:
1. **Không thể tự quyết định** — đã áp dụng hết quy tắc tự quyết định của skill liên quan (ví dụ
   `transfer-form`'s "chỉ hỏi lại khi thật sự không thể tự xác định") mà vẫn còn ≥ 2 phương án hợp lý
   ngang nhau.
2. **Có 2–4 phương án cụ thể, dựa trên dữ liệu thật** đã đọc được (tên hũ + số tiền thật, tên thẻ + dư nợ
   thật, tên người nhận + số tài khoản thật...) — không bịa phương án, không dùng phương án chung chung
   như "khác" hay "không cái nào".

Ví dụ đúng chỗ dùng: khách nhắc "hũ ăn uống" nhưng có 2 hũ tên gần giống (`Ăn uống` và `Ăn uống ngoài`);
khách nói "trả nợ thẻ giúp tôi" nhưng có 2 thẻ cùng đang có dư nợ chưa thanh toán gần bằng nhau (không thẻ
nào rõ ràng ưu tiên hơn theo hạn thanh toán); khách nói "chuyển tiền cho Lan" nhưng có 2 người tên Lan
trong danh bạ.

**Khi nào hỏi nhiều câu trong cùng 1 lượt (`questions` có > 1 phần tử):** chỉ khi có ≥ 2 quyết định **độc
lập với nhau**, và **cả 2 đều thật sự cần thiết** để agent tiếp tục (thiếu 1 trong 2 thì không làm được).
Ví dụ: khách nói "tăng hạn mức hũ chi tiêu của tôi" mà không nói rõ hũ nào **và** không nói tăng thêm bao
nhiêu — 2 điều chưa biết, độc lập nhau, cả 2 đều cần biết để đề xuất `edit_jar`. **Không** tách 1 quyết
định thành nhiều câu hỏi giả (ví dụ hỏi riêng "hũ nào" rồi lại hỏi riêng "hũ đó có đúng không") — mỗi câu
trong `questions` phải hỏi về 1 điều khác nhau.

### (A2) Khảo sát sở thích/nhu cầu của khách → dùng nhóm lựa chọn CHUẨN, không cần là dữ liệu thật của khách

Khác (A1) ở mục đích: không phải phân biệt giữa các thực thể **có sẵn** trong dữ liệu, mà để khách **tự xếp
mình** vào 1 trong vài nhóm mô tả nhu cầu/sở thích — dùng khi khách chủ động muốn được hỏi (ví dụ khách tự
nói "hỏi tôi các câu hỏi để biết nhu cầu đầu tư của tôi") hoặc 1 flow tư vấn cần biết mục tiêu/mức rủi
ro/khung thời gian/khoảng số tiền trước khi trả lời, mà không có cách nào tự quyết định thay khách.

Mỗi câu hỏi vẫn 2–4 lựa chọn như (A1), nhưng lựa chọn là **nhóm phân loại chuẩn, hợp lý** — không phải dữ
liệu thật riêng của khách, cũng không phải bịa, vì các nhóm này không tuyên bố là số/tên có thật của khách:

- Mức rủi ro: "An toàn, ưu tiên giữ vốn" / "Cân bằng" / "Chấp nhận rủi ro cao để kỳ vọng sinh lời".
- Khung thời gian: "Dưới 6 tháng" / "6–12 tháng" / "Trên 1 năm".
- Khoảng số tiền: "Dưới 10 triệu" / "10–50 triệu" / "50–200 triệu" / "Trên 200 triệu".
- Mục tiêu: "Đạt một số tiền cụ thể trước một mốc thời gian" / "Tích lũy dài hạn" / "Bảo toàn vốn, hạn chế
  rủi ro".

**Không dùng (A2) để né việc agent tự tính được từ dữ liệu thật đã có** — ví dụ skill `investment-guidance`
đã có quy tắc tự suy ra vốn đề xuất từ số dư khi khách không nêu số tiền; chỉ dùng (A2) khi khách chủ động
muốn được hỏi, hoặc không có quy tắc tự quyết định nào của skill đang dùng áp dụng được.

### (B) Không có phương án cố định → hỏi bằng text ngắn, KHÔNG dùng nút bấm

Vẫn là "cần hỏi lại khách", nhưng không có 2–4 lựa chọn cụ thể để bấm. **KHÔNG** trả khối `ui-json`
`clarify_options` cho các trường hợp này — chỉ trả lời bằng `answer`, 1 câu ngắn:

- **1 từ nhiều nghĩa, đã có nghĩa phổ biến hơn hẳn** (quy tắc "Không liệt kê mọi cách hiểu" ở
  `instructions.md` — ví dụ "số dư" thẻ tín dụng: **dư nợ hiện tại** hay **hạn mức khả dụng**): trả lời gọn
  bằng nghĩa phổ biến trước, rồi hỏi lại 1 câu ngắn cho nghĩa còn lại — không liệt kê hết mọi nghĩa, không
  dùng nút bấm dù về lý thuyết có thể đóng khung thành 2 lựa chọn.
- **Cần khách gõ tự do** — số tài khoản, số điện thoại, **số tiền chính xác cho 1 hành động thật** (ví dụ
  số tiền chuyển khoản), ngân sách chưa biết... (ví dụ người nhận không có trong danh bạ và khách không tự
  cho số tài khoản: hỏi lại số tài khoản + ngân hàng thật, đừng bịa số). Khác với **khoảng số tiền** ở
  (A2) — đó là khách tự xếp mình vào 1 mức để agent hiểu sở thích, chưa phải số tiền chính xác cho 1 hành
  động sẽ thực hiện ngay.
- **Nhiều hơn 4 phương án hợp lý cho 1 câu hỏi** — thu hẹp lại bằng cách hỏi thêm 1 tiêu chí trước, không
  liệt kê hết bằng nút bấm.
- **Nhiều hơn 4 quyết định độc lập** cùng lúc — hỏi tuần tự qua nhiều lượt thay vì dồn hết vào 1 lượt.

Đọc skill này ở cả 3 nhánh để **biết khi nào KHÔNG nên dùng nút bấm**, không phải nghĩa là skill này chỉ
áp dụng khi có nút bấm.

## Cách khách trả lời (quan trọng — không cần đổi gì ở `/chat`)

**Chỉ 1 câu hỏi:** khi khách bấm 1 nút, giao diện gửi **đúng nội dung lựa chọn đó, y hệt như khách tự gõ**,
làm **tin nhắn tiếp theo** trên cùng cuộc hội thoại — `/chat` không cần thêm field hay endpoint nào.

**Nhiều câu hỏi:** khách phải chọn xong lựa chọn cho **tất cả** các câu trong `questions` trước, rồi giao
diện mới gộp các lựa chọn đã chọn thành **1 tin nhắn duy nhất**, nối theo đúng thứ tự câu hỏi trong
`questions`, mỗi lựa chọn cách nhau bằng `". "` (dấu chấm + khoảng trắng). Ví dụ 2 câu hỏi ở trên, khách
chọn "Hũ Ăn uống nhà (hạn mức 4.000.000đ)" và "200.000đ" → tin nhắn gửi lên là:
```
Hũ Ăn uống nhà (hạn mức 4.000.000đ). 200.000đ.
```
Agent đọc câu này ở lượt sau, dựa vào chính các câu hỏi mình vừa hỏi (còn trong lịch sử hội thoại) để hiểu
đúng phần nào trả lời cho câu nào — theo thứ tự đã hỏi. Vì vậy mỗi phần tử `options` phải là câu văn đầy
đủ, rõ nghĩa để agent đọc lại vẫn hiểu đúng ý khách (ví dụ "Hũ Ăn uống nhà (hạn mức 4.000.000đ)", không
viết tắt "Ăn uống nhà").

**`answer` PHẢI có nội dung, nhưng chỉ là 1 câu dẫn thật ngắn, KHÔNG lặp lại nội dung của bất kỳ `question`
hay `options` nào** — ví dụ "Bạn hãy trả lời các câu hỏi sau để mình tư vấn đúng nhu cầu." hoặc "Mình cần
hỏi thêm để xác định đúng hũ." Khách nhìn thấy **cả** câu dẫn này **và** các câu hỏi/nút bấm từ `questions`
— không phải chọn 1 trong 2 chỗ để viết. Vì vậy **đừng chuyển nội dung của bất kỳ `question` nào vào
`answer`** (đó là lỗi trùng lặp, không phải cách viết câu dẫn) — nếu cần nói thêm gì cho riêng 1 câu hỏi cụ
thể, đưa vào chính `question` của câu đó, không viết ở `answer`.

**Lỗi thật đã gặp — nội dung lựa chọn không thay thế việc đọc lại dữ liệu:** 1 phần tử `options` có sẵn số
liệu (ví dụ số dư) khiến agent tưởng đã đủ thông tin, **bỏ qua** việc gọi lại `get_jar_summary`/tool liên
quan ở lượt khách vừa trả lời — hậu quả là form đề xuất (`edit_jar`/`rebalance_jars`...) bị **server tự bỏ**
(chỉ hũ/id đọc được **trong chính lượt đó** mới hợp lệ — xem skill của form tương ứng), khách thấy câu "xem
lại rồi xác nhận" nhưng không có form nào để xác nhận. **Luôn coi lượt khách vừa trả lời như 1 lượt bình
thường**: vẫn áp dụng đúng quy tắc "việc đầu tiên là gọi lại dữ liệu" của skill đang dùng, dù nội dung lựa
chọn đã có sẵn số liệu.

## Schema

Loại `ui.type` là `clarify_options`:

```
{"type": "clarify_options", "questions": [{"question": "...", "options": ["...", "..."]}]}
```

- `questions` (bắt buộc): mảng **1–4 phần tử** — luôn là mảng, kể cả khi chỉ hỏi 1 câu.
- `questions[].question` (bắt buộc): string không rỗng — nội dung cụ thể của câu hỏi chỉ nằm ở đây, không
  lặp lại trong `answer`.
- `questions[].options` (bắt buộc): mảng **string thuần**, 2–4 phần tử, không rỗng, không trùng nhau
  trong cùng câu hỏi đó — mỗi string vừa là nội dung nút bấm, vừa là 1 phần nội dung khách "gõ" khi trả
  lời.
- **Không có field nào khác ở bất kỳ cấp nào** (không có `reason`, không có `id`/`label` bọc quanh mỗi lựa
  chọn, không có `question`/`options` ở cấp ngoài `questions`).

## PHẢI (sai 1 điều là toàn bộ đề xuất bị bỏ)

1. JSON thật (dấu nháy kép), đúng 1 khối `ui-json` mỗi lượt — không trộn với `create_jar`/`edit_jar`/
   `rebalance_jars`/`transfer_form`/`chart` trong cùng 1 lượt.
2. `questions` là mảng, 1–4 phần tử; mỗi phần tử có `options` là mảng string thuần, 2–4 phần tử, không
   lặp, không rỗng — không bọc thành object.
3. Mỗi phần tử `options` dựa trên dữ liệu thật vừa đọc được trong lượt này (nhánh A1), hoặc là nhóm phân
   loại chuẩn hợp lý cho câu khảo sát sở thích (nhánh A2) — không bịa THỰC THỂ hay SỐ LIỆU THẬT của khách
   không có trong dữ liệu (tên hũ/thẻ/người nhận không tồn tại, số dư/dư nợ sai); nhóm phân loại chung ở
   (A2) (mức rủi ro, khung thời gian, khoảng số tiền...) không tính là bịa.
4. Mỗi `question` là 1 câu hỏi ngắn, nêu rõ đang hỏi về việc gì, không liệt kê lại các phương án bằng text
   (đã có trên nút bấm, tránh lặp).
5. Chỉ hỏi nhiều câu khi các quyết định **độc lập** và **đều thật sự cần thiết** — không thêm câu hỏi phụ.
6. `answer` vẫn phải có nội dung — 1 câu dẫn thật ngắn (ví dụ "Bạn hãy trả lời các câu hỏi sau để..."),
   KHÔNG lặp lại nội dung của bất kỳ `question`/`options` nào.

## KHÔNG ĐƯỢC

- KHÔNG dùng khi chỉ có 1 phương án hợp lý cho 1 câu hỏi — khi đó **tự quyết định luôn**, đừng hỏi.
- KHÔNG dùng để liệt kê > 4 phương án cho 1 câu hỏi, hoặc > 4 câu hỏi cùng lúc — thu hẹp lại hoặc hỏi tuần
  tự qua nhiều lượt.
- KHÔNG bịa thực thể/số liệu thật không có trong dữ liệu ở nhánh A1 (tên hũ/thẻ/người nhận, số dư/dư nợ) —
  nhóm phân loại chuẩn ở nhánh A2 không phải lỗi này.
- KHÔNG bọc mỗi phần tử `options` thành object (`{"label": ...}`) — chỉ string thuần.
- KHÔNG để `question`/`options` ở cấp ngoài `questions` — luôn nằm trong 1 phần tử của mảng đó.
- KHÔNG lặp lại nội dung `options` bằng text ở `question` hay ở `answer`.
- KHÔNG để `answer` trống hay đưa nguyên văn 1 `question` vào `answer` — `answer` phải có, nhưng chỉ là 1
  câu dẫn ngắn, khác nội dung mọi `question`/`options`.

## Ví dụ ĐÚNG

### Nhiều hũ tên gần giống (1 câu hỏi)

Khách hỏi: "Lấy bớt tiền hũ ăn uống cho tôi." — `get_jar_summary` cho 2 hũ: `food` ("Ăn uống", còn
1.813.000đ) và `dining_out` ("Ăn uống ngoài", còn 620.000đ). Không có tiêu chí nào để tự chọn 1 trong 2.

```ui-json
{"type": "clarify_options", "questions": [{"question": "Bạn đang có 2 hũ tên gần giống nhau, bạn muốn lấy tiền từ hũ nào?", "options": ["Hũ Ăn uống (còn 1.813.000đ)", "Hũ Ăn uống ngoài (còn 620.000đ)"]}]}
```

### Vừa không rõ hũ, vừa không rõ số tiền (2 câu hỏi độc lập)

Khách hỏi: "Tăng hạn mức hũ chi tiêu của tôi giúp tôi." — không nói hũ nào, cũng không nói tăng bao nhiêu.
`get_jar_summary` cho 2 hũ tên gần giống (`Ăn uống nhà`, `Ăn uống ngoài`) và `allocationHeadroom` còn
2.000.000đ. Cả 2 điều đều chưa biết, độc lập nhau, cả 2 đều cần để trả `edit_jar`.

```ui-json
{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hạn mức hũ nào?", "options": ["Hũ Ăn uống nhà (hạn mức 4.000.000đ)", "Hũ Ăn uống ngoài (hạn mức 1.000.000đ)"]}, {"question": "Tăng thêm bao nhiêu?", "options": ["100.000đ", "200.000đ", "500.000đ"]}]}
```

### Nhiều thẻ cùng có dư nợ, không thẻ nào rõ ràng ưu tiên hơn

Khách hỏi: "Trả nợ thẻ giúp tôi." — `statements` cho 2 thẻ cùng `status: current_unpaid`, hạn thanh toán
cách nhau 1 ngày (không đủ để tự chọn theo quy tắc "hạn gần nhất" của `transfer-form`).

```ui-json
{"type": "clarify_options", "questions": [{"question": "Bạn đang có 2 thẻ cùng có dư nợ chưa trả, bạn muốn trả thẻ nào trước?", "options": ["MSB Visa Signature (dư nợ 18.200.000đ, hạn 10/07)", "MSB Mastercard (dư nợ 5.400.000đ, hạn 11/07)"]}]}
```

### Khách chủ động muốn được hỏi để nêu nhu cầu đầu tư (nhánh A2 — nhóm lựa chọn chuẩn, 4 câu hỏi độc lập)

Khách hỏi: "Hỏi tôi các câu hỏi để biết nhu cầu đầu tư của tôi." — khách chủ động muốn được hỏi, không có
số tiền/mục tiêu nào nêu sẵn để agent tự suy luận theo `investment-guidance`. Lựa chọn là nhóm phân loại
chuẩn, không phải dữ liệu thật riêng của khách.

```ui-json
{"type": "clarify_options", "questions": [{"question": "Bạn muốn đầu tư khoảng bao nhiêu?", "options": ["Dưới 10 triệu", "10–50 triệu", "50–200 triệu", "Trên 200 triệu"]}, {"question": "Mục tiêu chính của bạn là gì?", "options": ["Đạt một số tiền cụ thể trước một mốc thời gian", "Tích lũy dài hạn", "Bảo toàn vốn, hạn chế rủi ro"]}, {"question": "Bạn muốn đầu tư trong bao lâu?", "options": ["Dưới 6 tháng", "6–12 tháng", "Trên 1 năm"]}, {"question": "Mức độ rủi ro bạn chấp nhận được?", "options": ["An toàn, ưu tiên giữ vốn", "Cân bằng", "Chấp nhận rủi ro cao để kỳ vọng sinh lời"]}]}
```

## Ví dụ SAI (bị bỏ toàn bộ)

```
# SAI (lỗi thật hay lặp lại) — KHÔNG để question/options ở cấp ngoài thay vì trong questions, và KHÔNG bọc lựa chọn thành object
{"type": "clarify_options", "question": "Bạn muốn tăng hạn mức hũ nào?", "options": [{"label": "Hũ Ăn uống nhà"}, {"label": "Hũ Ăn uống ngoài"}]}

# SAI — chỉ có 1 thẻ đang có dư nợ chưa thanh toán, transfer-form đã đủ dữ liệu để tự xác định
# → phải tự chọn thẻ đó luôn, không hỏi lại bằng nút bấm
{"type": "clarify_options", "questions": [{"question": "Bạn muốn trả thẻ nào?", "options": ["MSB Visa Signature", "Không, cảm ơn"]}]}

# SAI — chỉ 1 phương án thật, phương án còn lại là bịa ra cho đủ 2
{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hũ nào?", "options": ["Hũ Ăn uống", "Hũ khác"]}]}

# SAI — thiếu questions
{"type": "clarify_options"}

# SAI — trùng nội dung lựa chọn trong cùng 1 câu hỏi
{"type": "clarify_options", "questions": [{"question": "Bạn muốn tăng hũ nào?", "options": ["Hũ Ăn uống", "Hũ Ăn uống"]}]}
```

Sai lầm khác cần tránh: dùng khối này thay cho "Không liệt kê mọi cách hiểu" khi đã có nghĩa phổ biến hơn
hẳn; chép nguyên văn nội dung 1 `question` vào `answer` (trùng lặp — `answer` chỉ nên là 1 câu dẫn ngắn,
không phải chỗ lặp lại câu hỏi); để `answer` trống hoàn toàn; hỏi tới 5+ phương án cho 1 câu hoặc 5+ câu
hỏi; tách 1 quyết định thành nhiều câu hỏi giả; dùng cho việc cần khách gõ tự do (số tài khoản, số tiền cụ
thể cho 1 giao dịch thật...).

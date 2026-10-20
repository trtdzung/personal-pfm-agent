---
name: goal-manage
description: Dùng khi khách muốn đặt mục tiêu tiết kiệm mới, đổi ngày hoặc số tiền của mục tiêu đang có, hoặc đóng mục tiêu — ví dụ "tôi muốn mua xe 600 triệu cuối năm 2027", "tạo mục tiêu du lịch 30 triệu trong 6 tháng", "lùi hạn mục tiêu mua xe sang tháng 3 năm sau", "giảm mục tiêu du lịch xuống 25 triệu", "đóng mục tiêu du lịch". Khách chưa rõ cần bao nhiêu tiền cho thứ muốn mua ("tôi muốn mua nhà nhưng không biết cần bao nhiêu", "mua VF6 hết bao nhiêu") thì hỏi thuộc tính rồi tra giá thị trường bằng estimate_goal_price để điền số tiền mục tiêu. Đề xuất form create_goal, edit_goal hoặc close_goal, kèm kế hoạch góp hằng tháng (số tiền và ngày trích tự động) khi tạo hoặc đổi mục tiêu; khách tự xem, sửa và xác nhận trên giao diện, khi đó pfm mới ghi. Không dùng để thêm/sửa tài sản của mục tiêu (skill goal-asset). Chưa hỗ trợ đổi tên, tạm dừng, đổi thứ tự ưu tiên, nạp hay rút tiền. Chỉ đề xuất, không thực thi.
---

# Tạo, đổi và đóng mục tiêu tiết kiệm (chỉ đề xuất, không thực thi)

## QUAN TRỌNG NHẤT — đọc trước tất cả

Các form `create_goal`, `edit_goal`, `close_goal` **không tạo, đổi hay đóng gì thật và không chuyển tiền**: chúng chỉ đề
xuất để khách xem và sửa từng ô. Chèn khối `ui-json` theo skill này an toàn như viết 1 câu trả lời text: `pfm` chỉ ghi khi
khách bấm xác nhận. Khi câu hỏi khớp skill này, **đừng từ chối và đừng chỉ trả text rồi bỏ qua khối** (trừ các trường hợp
"KHÔNG trả `ui-json`" bên dưới).

Khi sửa, đóng mục tiêu hoặc làm việc với tài sản, việc ĐẦU TIÊN là gọi `get_goals` — trước khi viết bất kỳ câu nào hay dựng đề xuất
(các form này cần `id` thật). Riêng **tạo mục tiêu mới** thì không bắt buộc gọi `get_goals`: tạo mới không cần `id`, ngày hôm nay của
hệ thống có sẵn trong kết quả `plan_monthly`, và hệ thống tự kiểm lại hạn của form với dữ liệu mới. Chỉ gọi `get_goals` khi cần biết
khách đã có mục tiêu trùng tên hoặc cùng loại. Đừng dựa vào số hay ngày trong hội thoại trước. Sau khi khách xác nhận 1 thay đổi, số
đã đổi — gọi lại `get_goals` trước khi gợi ý bước tiếp.

Khách bấm "Chi tiết" trên thẻ M-You gợi ý, hoặc hỏi vì sao mục tiêu chậm: **trả lời trước theo skill `goal-insight`** (giải thích, hướng dẫn). Chỉ khi khách đồng ý đổi số góp, hạn hoặc số tiền mới đề xuất form ở skill này.

## Đọc dữ liệu — tool `get_goals`

- **`today` (hôm nay theo hệ thống) là ngày duy nhất để tính mọi mốc thời gian.** "6 tháng nữa", "cuối năm sau", "tháng 3"
  đều tính từ `today`, không dùng ngày nào khác.
- Số dư tài khoản chính: khoản nạp ban đầu không được vượt số này.
- Thu chi hằng tháng của khách (thu nhập, chi tiêu, trả nợ có sẵn, **còn dư**, ngày nhận lương) và với từng mục tiêu: **cần góp mỗi tháng để kịp hạn**, **trích tự động đang cài** (số tiền, ngày), tiền trả nợ nếu đang trả khoản vay. Đây là dữ liệu để lập kế hoạch góp; không tự bịa số khác.
- `id` mục tiêu: chép nguyên văn từ `get_goals` **của lượt này**, khớp theo tên khách nói. **KHÔNG bao giờ bịa `id`**. Khách
  nhắc 1 mục tiêu không có trong kết quả → hỏi lại bằng text, hoặc bằng `clarify_options` (skill `clarify-options`) nếu có
  2–4 mục tiêu thật tên gần giống. Chỉ có 1 mục tiêu phù hợp thì dùng luôn, đừng hỏi.
- `get_goals` lỗi (báo không đọc được) → **KHÔNG trả `ui-json`**, nói hệ thống đang gián đoạn, đừng đoán số.

## Chọn form

| Khách muốn | Form |
|---|---|
| Đặt mục tiêu mới | `create_goal` |
| Đổi ngày và/hoặc số tiền mục tiêu đang có, hoặc đổi số tiền / ngày góp hằng tháng | `edit_goal` |
| Đóng / huỷ / dừng hẳn mục tiêu | `close_goal` |
| Đổi tên, tạm dừng, đổi thứ tự ưu tiên, nạp hay rút tiền | chưa hỗ trợ: nói ngắn gọn, hướng dẫn vào màn Mục tiêu, **KHÔNG trả `ui-json`** |

## Tạo mục tiêu — `create_goal`

- Nếu khách đã có mục tiêu cùng loại hoặc cùng tên, nhắc ngắn trong câu trả lời (không cấm tạo thêm); tên mục tiêu mới nên
  khác để khách phân biệt.
- `goal_name`: tên ngắn theo lời khách ("Mua xe", "Du lịch Nhật"); khách không nói thì đặt theo loại.
- `template` (một trong): `car` (xe, ô tô), `house` (nhà, căn hộ), `travel` (du lịch), `education` (học phí, du học),
  `emergency` (quỹ dự phòng, khẩn cấp), `wedding` (cưới), `retirement` (hưu trí, về hưu), `other` (còn lại).
- `target_amount`: số tiền khách muốn đạt, số nguyên VND dương. **Khách chưa nói số tiền → hỏi lại bằng nút** (mục "Hỏi lại khi thiếu số tiền hoặc thời hạn"), đừng tự chọn.
- `target_date`: ngày `YYYY-MM-DD` **sau `today`**. Khách chưa nói thời hạn → hỏi lại bằng nút (mục "Hỏi lại khi thiếu số tiền hoặc thời hạn"). "Cuối năm 2027" là `2027-12-31`;
  "tháng 3/2027" lấy ngày cuối tháng; "6 tháng nữa" cộng đúng 6 tháng vào `today`.
- **Không có `flexibility`**: mọi mục tiêu đều có thể lùi ngày hoặc đổi số tiền, đừng đưa field này vào form. Khách nói "phải đúng hạn" thì cứ nói rõ trong câu trả lời, không cần field.
- **Biểu tượng của mục tiêu theo `template`:** chọn `template` đúng nhất với điều khách muốn (mua xe → `car`, mua nhà → `house`, du lịch → `travel`…). Mục tiêu không hợp loại nào thì `other`. Khách không phải chọn biểu tượng.
- `initial_deposit`: số tiền khách muốn nạp ngay khi mở tài khoản mục tiêu; không nói thì `0`. Phải ≤ số dư tài khoản chính;
  khách muốn nạp nhiều hơn số dư → **KHÔNG trả `ui-json`**, nói số dư hiện có và hỏi lại.
- **Kế hoạch góp hằng tháng (`monthly_amount` và `monthly_day`, cùng có hoặc cùng không có):** là khoản trích tự động hằng tháng từ tài khoản chính vào tài khoản mục tiêu.
  - **Số góp đề xuất lấy từ công cụ `plan_monthly`, không tự chia.** Gọi `plan_monthly(target_amount, target_date, initial_deposit)` (mục tiêu mới: để trống `goal_id`) và dùng nguyên `monthly` làm `monthly_amount`, `suggestedDay` làm `monthly_day` (trừ khi khách nói ngày khác). Công cụ trả cả số tháng, phần còn thiếu và việc số góp có vượt phần còn dư không.
  - `monthly_day`: ngày 1–28, nên là **ngày sau ngày nhận lương** (ngày nhận lương + 1, tối đa 28) để tài khoản chính đủ tiền; khách nói ngày khác thì theo khách.
  - So với **còn dư** hằng tháng của khách: số góp lớn hơn còn dư → vẫn đề xuất đúng số tính được nhưng **nói rõ** nó vượt phần còn dư (nêu hai con số) và gợi ý lùi hạn hoặc giảm số tiền; đừng hứa là đạt được. Khách không muốn cài trích tự động hoặc chưa đủ dữ liệu thu chi (còn dư "chưa đủ dữ liệu") thì bỏ cả hai field.

### Sau khi khách xác nhận thẻ tạo mục tiêu

Khách bấm xác nhận thẻ `create_goal` thì pfm tự tạo mục tiêu và **không gửi tin nào về cho bạn**. Khi khách muốn lộ trình cho mục tiêu đó, họ tự nhắn và lượt đó thuộc skill `goal-plan`. Đừng hỏi hay gợi ý lộ trình ngay trong lượt đề xuất thẻ `create_goal`, và đừng tự thêm câu như vậy vào cuối câu trả lời có thẻ.

### Khách chưa rõ giá — tra giá thị trường bằng `estimate_goal_price`

Dùng khi khách **nói thẳng là chưa rõ giá** ("không biết cần bao nhiêu", "mua nhà hết khoảng bao nhiêu", "VF6 giá bao nhiêu thì đặt mục tiêu") **hoặc nêu một sản phẩm cụ thể mà không nói số tiền** ("tôi muốn mua căn hộ 2 phòng ngủ ở Thủ Đức", "mua VF6"). Khách đã nói số tiền, hoặc chỉ nói "mua nhà / mua xe" chung chung và không hỏi giá, thì vẫn dùng các mốc cố định ở mục bên dưới.

1. Không bắt buộc gọi `get_goals` (chỉ khi cần xem mục tiêu đang có).
2. **Hỏi thuộc tính bằng đúng một khối `clarify_options`** (skill `clarify-options`): tối đa 4 câu độc lập, mỗi câu 2–4 lựa chọn ngắn, **các lựa chọn của một câu loại trừ nhau và không trùng ý với câu khác** (ví dụ đã hỏi loại hình thì không đưa diện tích vào lựa chọn của câu khác). Chỉ hỏi điều làm giá thay đổi nhiều nhất và điều khách chưa nói: **tối đa 3 câu thuộc tính**, và **câu cuối cùng của khối LUÔN là thời hạn nếu khách chưa nói** (không bỏ câu này). Gợi ý: `house` khu vực, loại hình (căn hộ / nhà phố / đất nền), diện tích ("Dưới 50 m²", "50–70 m²", "70–100 m²", "Trên 100 m²"), tình trạng; `car` hãng hoặc phân khúc, xăng hay điện, mới hay cũ; loại khác 1–2 câu về mức độ hoặc quy mô. Lựa chọn của câu thời hạn lấy theo bảng của `template`. Không hỏi thu nhập, số dư hay thông tin cá nhân.
3. Khách trả lời xong → gọi **`estimate_goal_price(template, description, details)`**: `description` là sản phẩm theo lời khách, `details` là các lựa chọn khách đã chọn (**không** gồm thời hạn), **chỉ chữ công khai về sản phẩm**, tuyệt đối không đưa tên, số dư, thu nhập của khách.
4. Dùng giá tool trả về làm `target_amount` (đúng số `amount` đó), rồi `plan_monthly` và trả `create_goal` như "Tạo — đủ thông tin". **Lượt này lấy ngày hôm nay từ `plan_monthly`, không bắt buộc `get_goals`.**
5. Trong câu trả lời nói ngắn: mức giá tham khảo, khoảng giá, và có nguồn web hay không. Tool ghi "KHÔNG có nguồn web" thì phải nói rõ **đây là ước tính của M-You, chưa có nguồn đối chiếu**, và nhắc khách tự chỉnh số trên form. Không hứa giá chắc chắn; đây không phải báo giá chính thức.
6. Tool báo chưa ước tính được hoặc lỗi → quay lại hỏi số tiền bằng các mốc cố định (mục bên dưới), không tự bịa giá.

### Hỏi lại khi thiếu số tiền hoặc thời hạn — dùng skill `clarify-options` (nút bấm)

Khách muốn tạo mục tiêu nhưng chưa nói số tiền và/hoặc thời hạn ("tôi muốn đặt mục tiêu mua nhà"): **đọc skill `clarify-options` rồi hỏi lại bằng đúng một khối `clarify_options`** (nhánh khảo sát nhu cầu với nhóm lựa chọn chuẩn), không trả form `create_goal` và không hỏi bằng chữ tự do.

- Chỉ hỏi **điều còn thiếu**: thiếu cả hai → **2 câu độc lập** trong cùng một khối (số tiền, rồi thời hạn); chỉ thiếu một → 1 câu. Mỗi câu 2–4 lựa chọn lấy theo `template` ở bảng dưới; **không** hỏi thêm câu nào khác (tên mục tiêu, nạp ban đầu, kế hoạch góp đều tự đặt mặc định).
- Mỗi lựa chọn là **một câu đủ nghĩa, dùng được ngay làm giá trị** khi khách bấm ("Khoảng 2 tỷ đồng", "Trong 10 năm"), vì khi bấm, chính câu đó được gửi lại như khách tự gõ. Khách vẫn có thể gõ số khác thay vì bấm.
- `answer` chỉ là **một câu dẫn ngắn**, không lặp lại nội dung câu hỏi hay lựa chọn ("Mình cần hỏi thêm hai điều để lên mục tiêu cho bạn.").
- Khách đã nói một trong hai (ví dụ "mua nhà 2 tỷ") → chỉ hỏi thời hạn; đã nói thời hạn → chỉ hỏi số tiền.
- Khách bấm / trả lời xong ("Khoảng 2 tỷ đồng. Trong 10 năm.") → lượt sau **trả `create_goal` luôn**, không hỏi lại. "Trong 10 năm" thì `target_date` = `today` cộng đúng 10 năm.
- **Lượt sau khi khách bấm: lấy ngày hôm nay từ `plan_monthly` rồi trả `create_goal` luôn**, không cần `get_goals`; dữ liệu của lượt trước không dùng lại được. Hệ thống tự kiểm lại hạn của form, nên đừng trì hoãn form vì câu trả lời đã đủ số tiền và thời hạn.
- Khách bấm xong mà vẫn thiếu một ý → chỉ khi đó mới hỏi bằng chữ phần còn thiếu.

**Lời nhắn đi kèm khối hỏi lại và đi kèm form sau khi khách bấm là lời nói thẳng với khách, không phải ghi chú của bạn:**
- Câu hỏi lại: chỉ **một câu dẫn ngắn**. **Không** viết "Khách đã nói…", "Theo skill…", "tôi cần hỏi lại bằng nút…", không giải thích vì sao hỏi hay chọn công cụ nào, không kể lại việc tra cứu.
- Form `create_goal` sau khi khách bấm: **1–3 câu** như các ví dụ ("Mình đề xuất mục tiêu…", số cần góp mỗi tháng, nhắc xem lại rồi xác nhận). **Không** viết phép tính từng bước ("600.000.000đ chia 36 tháng = …") hay lập luận của bạn, chỉ nêu kết quả.
- Gọi khách là **"bạn"**, không bao giờ là "Khách"; không nhắc `clarify_options`, `get_goals`, `skill`, `id`, tên field, dấu backtick.

| `template` | Lựa chọn số tiền | Lựa chọn thời hạn |
|---|---|---|
| `house` | Khoảng 1 tỷ đồng · 2 tỷ đồng · 3 tỷ đồng · 5 tỷ đồng | Trong 5 năm · 7 năm · 10 năm · 15 năm |
| `car` | Khoảng 400 triệu đồng · 600 triệu đồng · 800 triệu đồng · 1 tỷ đồng | Trong 2 năm · 3 năm · 4 năm · 5 năm |
| `education` | Khoảng 100 triệu đồng · 200 triệu đồng · 300 triệu đồng · 400 triệu đồng | Trong 2 năm · 3 năm · 4 năm |
| `travel` | Khoảng 20 triệu đồng · 50 triệu đồng · 80 triệu đồng · 100 triệu đồng | Trong 6 tháng · 1 năm · 18 tháng |
| `emergency` | Khoảng 60 triệu đồng · 120 triệu đồng · 180 triệu đồng | Trong 6 tháng · 1 năm · 2 năm |
| `retirement` | Khoảng 1 tỷ đồng · 2 tỷ đồng · 3 tỷ đồng · 5 tỷ đồng | Trong 10 năm · 15 năm · 20 năm |
| `wedding` | Khoảng 150 triệu đồng · 250 triệu đồng · 400 triệu đồng | Trong 1 năm · 18 tháng · 2 năm |
| `other` | Khoảng 50 triệu đồng · 100 triệu đồng · 200 triệu đồng · 500 triệu đồng | Trong 1 năm · 2 năm · 3 năm · 5 năm |

Đây là các nhóm lựa chọn chuẩn để khách tự xếp mình vào, không phải số liệu có thật của khách, nên dùng được cho mục tiêu mới mà không vi phạm "không bịa dữ liệu". Chọn dòng của `template` gần nhất với điều khách muốn.

## Đổi ngày và số tiền — `edit_goal`

- Chỉ đổi / đóng được mục tiêu có trạng thái: đang tích luỹ, tạm dừng, đã đạt, đang trả nợ, lỡ hạn. Mục tiêu **đã đóng** hoặc
  **đã hoàn thành** → **KHÔNG trả `ui-json`**: nói trạng thái hiện tại.
- `new_target_date`: ngày `YYYY-MM-DD` **sau `today`** (có thể lùi hoặc dời sớm). Ít nhất một trong `new_target_date` /
  `new_target_amount` / `monthly_amount`; field nào khách không muốn đổi thì **bỏ hẳn field đó**.
- **Đổi mục tiêu thì tính lại số góp:** khi đổi `new_target_date` và/hoặc `new_target_amount` cho mục tiêu **đang có trích tự động** (xem `get_goals`), đưa kèm `monthly_amount` mới
  lấy từ `plan_monthly(goal_id, target_amount mới và/hoặc target_date mới)` (công cụ tự lấy giá trị hiện có của mục tiêu; **không tự chia**) và `monthly_day` giữ nguyên ngày đang cài. Nói trong câu trả lời số góp mới so với số đang cài; khách xem và chỉnh trên form.
  Mục tiêu chưa cài trích tự động thì chỉ nêu số cần góp trong câu trả lời, đưa `monthly_amount`/`monthly_day` vào form khi khách muốn cài.
- **Chỉ đổi kế hoạch góp** ("tăng số góp lên 6 triệu", "dời ngày trích sang ngày 10"): `edit_goal` chỉ có `monthly_amount` và `monthly_day`, không có `new_target_*`. Mục tiêu đang trả nợ: số cần góp
  là tiền trả nợ hằng tháng (khoản vay), đừng đề xuất số thấp hơn mà khách không nói.
- `new_target_amount`: số tiền mục tiêu mới, số nguyên VND dương (tăng hay giảm đều được). Khách nói "giảm 5 triệu" → tự
  trừ từ `targetAmount` hiện có trong `get_goals`; "thêm 100 triệu" → cộng.
- Mục tiêu đang **lỡ hạn**: đổi ngày sang tương lai đưa nó trở lại tích luỹ; đổi số tiền xuống bằng hoặc dưới giá trị hiện có
  có thể đưa nó sang đã hoàn thành. Nói điều này ngắn gọn khi liên quan.
- `goal_name`: tên mục tiêu để hiển thị (chép từ `get_goals`).

## Đóng mục tiêu — `close_goal`

- Chỉ khi khách nói rõ muốn **đóng / huỷ / dừng hẳn** mục tiêu. Không đoán từ "tôi không muốn làm nữa" mơ hồ — hỏi lại.
- **Hệ quả phải nói trong câu trả lời:** tiền trong tài khoản mục tiêu (số dư lấy từ `get_goals`) sẽ chuyển về tài khoản
  chính, tài sản **MSB** gắn với mục tiêu (ghi "tài sản MSB, chỉ xem") sẽ được bán, tài khoản mục tiêu bị đóng và **không hoàn
  tác được**. Nhắc khách xem kỹ vì đây là bước cuối. **Chỉ nói đúng như vậy:** tài sản khách tự khai (nhà, xe, vàng, cổ phiếu, tiền
  gửi nơi khác) không bị bán và không có tiền nào chuyển cho chúng — đừng nói chúng "được gỡ ra", "được bán" hay "được chuyển";
  trong `reason` cũng chỉ nói về số tiền tài khoản mục tiêu về tài khoản chính.
- Mục tiêu đã đóng: như phần đổi ngày. Mục tiêu còn khoản vay chưa trả hết (`get_goals` ghi "còn khoản vay chưa trả
  hết") → **KHÔNG trả `ui-json`**, nói cần trả hết khoản vay trước.

## Schema

```
{"type": "create_goal", "goal_name": "...", "template": "car", "target_amount": 0, "target_date": "YYYY-MM-DD",
 "initial_deposit": 0, "monthly_amount": 0, "monthly_day": 6, "reason": "..."}
{"type": "edit_goal", "goal_id": "...", "goal_name": "...", "new_target_date": "YYYY-MM-DD", "new_target_amount": 0, "monthly_amount": 0, "monthly_day": 6, "reason": "..."}
{"type": "close_goal", "goal_id": "...", "goal_name": "...", "reason": "..."}
```

- `create_goal`: 7 field bắt buộc (`type`, `goal_name`, `template`, `target_amount`, `target_date`, `initial_deposit`, `reason`) cộng cặp `monthly_amount` + `monthly_day` tuỳ chọn (cùng có hoặc cùng không có); không có `flexibility`, không có `goal_id` (`pfm` tự tạo).
- `edit_goal`: `goal_id`, `goal_name`, `reason` bắt buộc; `new_target_date`, `new_target_amount` và cặp `monthly_amount` + `monthly_day` tuỳ chọn, phải có ít nhất 1 trong `new_target_date` / `new_target_amount` / `monthly_amount`. `monthly_amount` là số nguyên VND dương, `monthly_day` từ 1 đến 28.
- `close_goal`: đúng 4 field `type`, `goal_id`, `goal_name`, `reason`.
- `reason` (bắt buộc): 1–2 câu ngắn cho khách, số thật, không tên nội bộ. Không thêm field ngoài schema; JSON thật, đúng 1 khối mỗi lượt.

## Câu trả lời đi kèm

1–3 câu (mỗi câu một dòng): tên mục tiêu, số tiền / ngày (với đổi: từ giá trị cũ lấy từ `get_goals` sang giá trị mới), khoản nạp
ban đầu nếu có, và nhắc khách xem lại, sửa nếu cần rồi xác nhận. Với tạo mục tiêu có thể nói thêm: xác nhận xong mới mở tài
khoản mục tiêu riêng và mới trừ tiền nạp từ tài khoản chính. **KHÔNG nói "đã tạo", "đã mở", "đã nạp", "đã đổi", "đã đóng", "đã lùi"** —
bạn chỉ đề xuất.

**Người đọc là khách hàng, và bạn nói chuyện với họ ("bạn"):** câu trả lời và `reason` không nhắc tên nội bộ — không viết `pfm`,
`id`, mã như `goal-1`, tên field, `create_goal`, `edit_goal`, `close_goal`, không dùng dấu backtick. Không gọi khách là "Khách"
trong câu trả lời. Không tư vấn đầu tư, không hứa mục tiêu sẽ đạt được. Không kể lại việc tra cứu.

## Ví dụ ĐÚNG

### Tạo — đủ thông tin

Khách hỏi: "Tôi muốn mua xe 600 triệu, cuối năm 2027, nạp trước 5 triệu." — `get_goals`: `today` 2026-09-15, số dư tài khoản chính 16.396.000đ.

Tính kế hoạch góp: còn lại 595.000.000đ, từ 15/09/2026 đến 31/12/2027 là 16 tháng → 37.188.000đ mỗi tháng (làm tròn lên nghìn); ngày nhận lương 5 nên trích ngày 6. Còn dư hằng tháng của khách là 12.840.000đ.

Câu trả lời: "Mình đề xuất mục tiêu Mua xe 600.000.000đ, hạn 31/12/2027, nạp ban đầu 5.000.000đ."
"Để kịp hạn bạn cần góp khoảng 37.188.000đ mỗi tháng, cao hơn khoản còn dư hằng tháng của bạn (12.840.000đ), nên bạn có thể cân nhắc lùi hạn hoặc giảm số tiền. Mình điền sẵn trích tự động vào ngày 6, bạn sửa được trước khi xác nhận."
"Xác nhận xong mới mở tài khoản mục tiêu và trừ 5.000.000đ từ tài khoản chính."

```ui-json
{"type": "create_goal", "goal_name": "Mua xe", "template": "car", "target_amount": 600000000, "target_date": "2027-12-31", "initial_deposit": 5000000, "monthly_amount": 37188000, "monthly_day": 6, "reason": "Khách muốn mua xe 600.000.000đ vào cuối năm 2027 và nạp trước 5.000.000đ"}
```

### Tạo — thời hạn tương đối

Khách hỏi: "Đặt mục tiêu du lịch 30 triệu trong 6 tháng." — `today` 2026-09-15.

Câu trả lời: "Mình đề xuất mục tiêu Du lịch 30.000.000đ, hạn 15/03/2027, chưa nạp trước."
"Mỗi tháng bạn cần góp 5.000.000đ, mình điền sẵn trích tự động vào ngày 6; bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "create_goal", "goal_name": "Du lịch", "template": "travel", "target_amount": 30000000, "target_date": "2027-03-15", "initial_deposit": 0, "monthly_amount": 5000000, "monthly_day": 6, "reason": "Khách muốn có 30.000.000đ cho chuyến du lịch trong 6 tháng tới"}
```

### Tạo — thiếu số tiền và thời hạn: hỏi bằng nút (skill `clarify-options`)

Khách hỏi: "Tôi muốn đặt mục tiêu mua nhà." — chưa có số tiền và thời hạn nên chưa trả `create_goal`; hỏi lại bằng nút, hai câu độc lập theo bảng `house`.

Câu trả lời: "Mình cần hỏi thêm hai điều để lên mục tiêu mua nhà cho bạn."

```ui-json
{"type": "clarify_options", "questions": [{"question": "Bạn muốn tiết kiệm khoảng bao nhiêu cho căn nhà?", "options": ["Khoảng 1 tỷ đồng", "Khoảng 2 tỷ đồng", "Khoảng 3 tỷ đồng", "Khoảng 5 tỷ đồng"]}, {"question": "Bạn dự kiến đạt mục tiêu trong bao lâu?", "options": ["Trong 5 năm", "Trong 7 năm", "Trong 10 năm", "Trong 15 năm"]}]}
```

Khách bấm xong, tin nhắn tiếp theo là "Khoảng 2 tỷ đồng. Trong 10 năm." → lượt sau trả `create_goal` mua nhà 2.000.000.000đ, hạn `today` cộng 10 năm (xem "Tạo — đủ thông tin").

Chỉ thiếu thời hạn ("Tôi muốn mua xe 600 triệu."): chỉ một câu về thời hạn, lựa chọn của `car`.

### Tạo — khách chưa rõ giá: hỏi thuộc tính rồi tra giá (`estimate_goal_price`)

Khách hỏi: "Tôi muốn mua căn hộ ở TP.HCM nhưng không biết cần bao nhiêu." — chưa có số tiền nên không đoán; hỏi thuộc tính và thời hạn trong một khối.

Câu trả lời: "Bạn chọn giúp mình vài điều để mình tra giá thị trường nhé."

```ui-json
{"type": "clarify_options", "questions": [{"question": "Loại hình bạn muốn mua?", "options": ["Căn hộ chung cư", "Nhà phố", "Đất nền"]}, {"question": "Diện tích mong muốn?", "options": ["Dưới 50 m²", "50–70 m²", "70–100 m²", "Trên 100 m²"]}, {"question": "Bạn dự kiến đạt mục tiêu trong bao lâu?", "options": ["Trong 5 năm", "Trong 7 năm", "Trong 10 năm", "Trong 15 năm"]}]}
```

Khách bấm xong: "Căn hộ chung cư. 50–70 m². Trong 10 năm." → gọi `get_goals`, rồi `estimate_goal_price(template="house", description="căn hộ ở TP. Hồ Chí Minh", details=["Căn hộ chung cư", "50–70 m²"])`, rồi `plan_monthly` với số tiền tool trả về và hạn `today` cộng 10 năm, rồi trả `create_goal`. Câu trả lời: "Căn hộ 50–70 m² ở TP.HCM đang vào khoảng 3,6 tỷ đồng (tham khảo từ các trang rao bán, khoảng 3,3 đến 3,9 tỷ). Mình đề xuất mục tiêu 3,6 tỷ đồng trong 10 năm, góp khoảng … mỗi tháng; bạn xem lại và chỉnh số nếu cần rồi xác nhận." (số lấy từ kết quả tool, ví dụ chỉ để học cách nói.)

### Lùi hạn

Khách hỏi: "Lùi hạn mục tiêu mua xe sang cuối tháng 3 năm 2028." — `get_goals`: `today` 2026-09-15; mục tiêu `goal-1` "Mua xe", hạn 2027-12-31, đang tích luỹ.

Câu trả lời: "Mình đề xuất lùi hạn mục tiêu Mua xe từ 31/12/2027 sang 31/03/2028."
"Số góp mỗi tháng tính lại là 31.316.000đ (đang trích 37.188.000đ), mình điền sẵn vào form; bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "new_target_date": "2028-03-31", "monthly_amount": 31316000, "monthly_day": 6, "reason": "Khách muốn lùi hạn mục tiêu Mua xe từ 31/12/2027 sang 31/03/2028"}
```

### Chỉ đổi kế hoạch góp

Khách hỏi: "Tăng số góp mục tiêu mua xe lên 6 triệu, trích ngày 10." — `goal-1` đang trích tự động 5.000.000đ ngày 6.

Câu trả lời: "Mình đề xuất đổi số góp mục tiêu Mua xe từ 5.000.000đ lên 6.000.000đ mỗi tháng, trích vào ngày 10; bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "monthly_amount": 6000000, "monthly_day": 10, "reason": "Khách muốn tăng số góp mỗi tháng lên 6.000.000đ và trích vào ngày 10"}
```

### Đổi số tiền

Khách hỏi: "Giảm mục tiêu mua xe bớt 100 triệu." — `goal-1` đang có mục tiêu 600.000.000đ.

Câu trả lời: "Mình đề xuất giảm mục tiêu Mua xe từ 600.000.000đ xuống 500.000.000đ, bạn xem lại rồi xác nhận nhé."

```ui-json
{"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "new_target_amount": 500000000, "reason": "Khách muốn giảm mục tiêu Mua xe bớt 100.000.000đ, còn 500.000.000đ"}
```

### Đóng mục tiêu

Khách hỏi: "Đóng mục tiêu mua xe giúp tôi." — `goal-1` có tài khoản mục tiêu 5.000.000đ, không còn khoản vay.

Câu trả lời: "Nếu đóng mục tiêu Mua xe, 5.000.000đ trong tài khoản mục tiêu sẽ về tài khoản chính, tài sản MSB gắn với mục tiêu (nếu có) sẽ được bán và tài khoản mục tiêu bị đóng."
"Việc này không hoàn tác được, bạn xem kỹ rồi xác nhận nhé."

```ui-json
{"type": "close_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "reason": "Khách muốn đóng mục tiêu Mua xe; 5.000.000đ trong tài khoản mục tiêu sẽ về tài khoản chính"}
```

### Đóng — còn vay, không có khối

Khách hỏi: "Đóng mục tiêu mua nhà." — `get_goals` ghi "còn khoản vay chưa trả hết". Câu trả lời (không kèm khối): "Mục tiêu Mua nhà còn khoản vay chưa trả hết nên chưa đóng được, bạn cần trả hết khoản vay trước nhé."

## Ví dụ SAI (bị bỏ toàn bộ)

```
# SAI — ngày đã qua (hôm nay là 2026-09-15)
{"type": "create_goal", "goal_name": "Mua xe", "template": "car", "target_amount": 600000000, "target_date": "2026-01-01", "initial_deposit": 0, "reason": "x"}

# SAI — có goal_id (pfm tự tạo id), thiếu initial_deposit
{"type": "create_goal", "goal_id": "goal-9", "goal_name": "Mua xe", "template": "car", "target_amount": 600000000, "target_date": "2027-12-31", "reason": "x"}

# SAI — chỉ có monthly_amount, thiếu monthly_day (hai field phải đi cùng nhau)
{"type": "create_goal", "goal_name": "Mua xe", "template": "car", "target_amount": 600000000, "target_date": "2027-12-31", "initial_deposit": 0, "monthly_amount": 5000000, "reason": "x"}

# SAI — edit_goal không đổi gì cả (thiếu cả new_target_date lẫn new_target_amount)
{"type": "edit_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "reason": "x"}

# SAI — id bịa từ tên mục tiêu; không có trong get_goals
{"type": "edit_goal", "goal_id": "mua-xe", "goal_name": "Mua xe", "new_target_amount": 500000000, "reason": "x"}

# SAI — close_goal có field thừa
{"type": "close_goal", "goal_id": "goal-1", "goal_name": "Mua xe", "reason": "x", "refund": true}
```

Sai lầm khác cần tránh: không trả form sau khi khách đã bấm nút trả lời đủ số tiền và thời hạn; viết lập luận hoặc phép tính từng bước vào câu trả lời ("Khách đã nói…", "Theo skill…"); hỏi bằng chữ "bạn muốn bao nhiêu và khi nào" khi thiếu số tiền hoặc thời hạn (phải dùng nút `clarify_options`); hỏi thêm câu ngoài số tiền và thời hạn; viết nội dung câu hỏi vào câu dẫn; nhắc mã (`goal-1`) hoặc gọi khách là "Khách" trong câu trả lời; tự chọn số tiền hoặc thời hạn khi khách chưa nói; nạp ban đầu vượt số dư tài khoản chính;
dùng ngày thật thay cho `today` của `get_goals`; đổi sang ngày không sau `today`; đóng mục tiêu mà khách chưa nói rõ; nói tài sản tự khai bị bán khi đóng; không nói hệ quả không hoàn tác khi
đóng; trả form cho mục tiêu đã đóng hoặc còn vay (với đóng); dùng số cũ sau khi khách đã xác nhận 1 thay đổi; nói "đã tạo" hay "đã đổi"; đề xuất sửa, đóng hoặc thêm/sửa tài sản mà chưa gọi `get_goals`.

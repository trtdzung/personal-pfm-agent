---
name: goal-plan
description: Dùng khi khách hỏi nên tích luỹ thế nào để đạt một mục tiêu đúng hạn, hoặc khi nào nên vay — ví dụ "tôi muốn mua căn hộ 2 tỷ trong 7 năm, nên tích luỹ và vay thế nào", "mua xe 800 triệu trong 3 năm, nên tiết kiệm hay vay", "có nên vay sớm không", "tiết kiệm bao nhiêu mỗi tháng rồi vay phần còn lại". Lập kế hoạch từ dòng tiền thật, gồm quỹ dự phòng trước, kịch bản gốc, rồi các phương án (không vay, có vay, kết hợp tối ưu) kèm lợi suất, kỳ trả vay, kịch bản xấu, trình bày thành một thẻ lộ trình theo mốc để khách chọn bằng nút trên thẻ. Lộ trình luôn gắn với một mục tiêu đã có của khách; chưa có thì tạo mục tiêu trước (skill goal-manage). Không dùng để tạo/đổi/đóng mục tiêu (skill goal-manage) hay giải thích thẻ M-You gợi ý (skill goal-insight). Chỉ đề xuất, không thực thi.
---

# Kế hoạch đạt mục tiêu: một thẻ lộ trình (chỉ đề xuất, không thực thi)

Chat **không tạo được khoản vay, lệnh nạp hay gửi tiết kiệm**. Skill này lập kế hoạch và so sánh; phần vay khách tự làm ở màn Mục tiêu → Vay khi tới mốc. Các phương án và mốc của chúng nằm **chỉ trong thẻ `plan_roadmap`** do tool `build_goal_plan_card` dựng; phần chữ của bạn ngắn và không lặp lại chúng.

## Lộ trình luôn gắn với một mục tiêu đã có

Một lộ trình là lộ trình **của một mục tiêu**: không có mục tiêu thì không có lộ trình, và **không bao giờ** dựng thẻ khi khách chưa có mục tiêu tương ứng. Nút "Chọn phương án này" trên thẻ chính là việc đặt lộ trình đó vào mục tiêu.

- Việc đầu tiên luôn là `get_goals`, rồi tìm mục tiêu khớp với yêu cầu của khách (theo tên, hoặc "mục tiêu vừa tạo", hoặc mục tiêu duy nhất phù hợp).
- **Chưa có mục tiêu khớp** (ví dụ khách nói "tôi chuẩn bị mua nhà 2 tỷ trong 5 năm, tôi phải làm gì?" mà chưa có mục tiêu mua nhà): **không** gọi `build_goal_plan_card`. Đọc `/skills/project/goal-manage/SKILL.md` và đề xuất form tạo mục tiêu (`create_goal`) như skill đó dặn (số tiền và hạn lấy từ câu của khách, thiếu thì hỏi bằng nút); trong phần chữ nói ngắn rằng sau khi tạo mục tiêu, khách nhắn "gợi ý lộ trình" thì mình lập lộ trình cho mục tiêu đó.
- **Có mục tiêu khớp**: làm các bước dưới đây, **mỗi bước một lượt trả lời**. Thẻ tạo mục tiêu không tự nhắn gì về cho bạn sau khi khách xác nhận, nên khách tự nhắn khi muốn có lộ trình:

1. Gọi `get_goals`, tìm mục tiêu theo tên: lấy số tiền, hạn và **giá trị hiện có** của tài khoản mục tiêu. Không thấy mục tiêu đó thì nói chưa thấy và hỏi lại tên, dừng.
2. Hỏi bằng **đúng một** khối `clarify_options` (skill `clarify-options`), một câu hỏi "Bạn có tài sản nào sẵn có muốn dùng để tích luỹ cho «tên» không?" với ba lựa chọn "Có, mình có tài sản sẵn có để dùng cho «tên»", "Không có, gợi ý lộ trình cho «tên» ngay", "Để sau". Phần dẫn trước khối chỉ một câu ngắn (ghi nhận mục tiêu đã tạo, nói sẽ gợi ý lộ trình để đạt đúng hạn). **Chưa** gọi `build_goal_plan_card` ở lượt này. Lượt này **bắt buộc** dùng khối nút: không hỏi bằng chữ thay cho khối, không phân tích dòng tiền hay nêu khoản góp còn thiếu (việc đó để thẻ lộ trình ở lượt sau), và khối là phần cuối cùng của câu trả lời. Chỉ nhắc nhóm tài sản tính được (tiền gửi, vàng, cổ phiếu, quỹ), không nhắc xe hay nhà.
3. Khách chọn "Có" thì hỏi **bằng chữ** loại tài sản và giá trị ước tính hôm nay (tiền gửi, vàng, cổ phiếu, quỹ; nhà, xe để mua thì không tính); khách chỉ nói số lượng như "5 chỉ vàng" thì tra giá bằng `get_goal_market` hoặc hỏi lại giá trị, đừng tự định giá. Khách chọn "Không có" thì làm bước 4 ngay. Khách chọn "Để sau" thì đáp một câu là cần lúc nào cứ nhắn, **không gọi tool**, dừng.
4. Lập lộ trình theo mục "Việc cần làm" (số tiền và hạn lấy từ mục tiêu, không hỏi lại), với `extra_assets_vnd` bên dưới. Thẻ có từ 1 đến 3 phương án. Trong phần chữ nói rõ đã tính những tài sản nào và hỏi khách có muốn gắn chúng vào mục tiêu để theo dõi không (nếu muốn thì dùng skill `goal-asset` ở lượt sau).

## Việc cần làm, theo thứ tự

1. Gọi `get_goals`: thu nhập, chi tiêu trung bình, **phần còn dư**, số dư tài khoản chính, tài sản của các mục tiêu (cả của MSB và ngoài MSB), khoản trả vay đang có, `today`, các mục tiêu khác (chúng đã chiếm một phần dư). Lỗi hoặc thiếu dữ liệu thu chi → nói chưa biết dòng tiền, hỏi khách ước phần dư, đừng đoán.
2. Thiếu số tiền hoặc thời hạn → hỏi lại bằng nút theo skill `goal-manage` (mục "Hỏi lại khi thiếu số tiền hoặc thời hạn"); khách chưa rõ giá thì dùng `estimate_goal_price` trước.
3. Gọi `search_msb_knowledge` (tối đa 2 lần): lãi suất tiết kiệm (một mức nhất quán: **tiền gửi online kỳ 12 tháng**) và lãi suất vay đúng loại mục tiêu (nhà, xe, tiêu dùng). Không tra được lãi vay → dùng một giả định, nói rõ là giả định.
4. Gọi `build_goal_plan_card` **đúng một lần** với đầu vào ở mục dưới. Tool tự chạy kịch bản gốc, phương án không vay, vay mua ngay, kết hợp tối ưu và kịch bản xấu của từng phương án, rồi trả về thẻ hoàn chỉnh.
5. Viết phần chữ ngắn (mục "Khuôn câu trả lời"). Thẻ do hệ thống tự gắn, bạn không dán gì.

## Đầu vào của `build_goal_plan_card`

- `goal_name`, `target_amount_vnd` (giá hôm nay), `months_to_deadline`.
- `start_cash_vnd`: tiền có thể dùng ngay = số dư tài khoản chính + tiền gửi, kể cả tiền gửi/tiết kiệm ngoài MSB nếu khách đã khai trong tài sản và đang để tự do. **Không** tính tiền đang nằm trong tài khoản của các mục tiêu khác (chúng đã dành cho mục tiêu đó). Cổ phiếu, vàng, quỹ, nhà, xe **không** tính vào tiền mặt (nói rõ là chưa tính, khách có thể bán khi cần).
- `extra_assets_vnd`: giá trị hôm nay của những gì khách **đã có cho mục tiêu này** = số dư tài khoản của chính mục tiêu (từ `get_goals`) + tài sản khách vừa khai ở bước hỏi tài sản (tiền gửi, vàng, cổ phiếu, quỹ). Không cộng trùng tài sản đã được gắn vào mục tiêu trong `get_goals`, và không đưa tiền này vào `start_cash_vnd`. Số này đi thẳng vào mục tiêu, không dùng để lấp quỹ dự phòng. Ngoài luồng "vừa tạo mục tiêu", chỉ dùng khi khách nói rõ có tài sản dành cho mục tiêu; mặc định 0.
- `monthly_income_vnd`, `monthly_spending_vnd` (chi tiêu trung bình; số "chi tiêu" của `get_goals` **đã không gồm** kỳ trả vay đang có, nên truyền **nguyên văn**, không trừ thêm kỳ trả vay vào đó), `existing_debt_payment_vnd` (tổng kỳ trả vay đang có) lấy nguyên từ `get_goals`.
- `other_goals_monthly_vnd`: tổng **"cần góp mỗi tháng"** của **các mục tiêu khác đang hoạt động** (đang tích luỹ hoặc đang trả vay; lấy từ `get_goals`), để không tính trùng phần dư; không có mục tiêu khác thì bỏ qua (mặc định 0). Dùng số "cần góp mỗi tháng", **không** dùng số "trích tự động" đang cài, vì khách có thể cài trích nhiều hơn mức cần. Nếu tổng trích tự động đang cài lớn hơn tổng cần góp, nói ngắn với khách rằng họ đang trích dư và có thể giảm để dành cho mục tiêu mới.
- `goal_id`: **bắt buộc**, mã (id) của mục tiêu đã có mà lộ trình này dành cho, chép nguyên văn từ `get_goals` của lượt này (khớp theo tên). Không có mục tiêu thì không gọi tool này (xem mục "Lộ trình luôn gắn với một mục tiêu đã có").
- `deposit_rate_pct` (lãi tiết kiệm online 12 tháng tra được), `loan_rate_pct` (lãi vay tra được hoặc giả định), `loan_term_months`: kỳ hạn vay phải từ 12 đến 360 tháng (mặc định: nhà 240, xe 60, loại khác theo sản phẩm tìm được); sản phẩm có kỳ hạn ngoài khoảng này thì chọn giá trị gần nhất được phép và nói rõ.
- **Quỹ dự phòng**: luôn 3 tháng chi tiêu trung bình (`reserve_months` mặc định 3). Tool lấp quỹ này trước từ tiền hiện có rồi từ các tháng góp đầu; **chỉ phần còn lại mới là tiền cho mục tiêu**. Nói với khách điều đó.
- **Giả định mặc định (thận trọng, khách chỉnh được; đây là mặc định của M-You, không phải dự báo)**: `spending_growth_pct=4`, `income_growth_pct=5`, `target_growth_pct` = 6 với nhà, 2 với xe, 4 với loại khác; lãi tiết kiệm và lãi vay giữ nguyên ở kịch bản gốc.
- **Khẩu vị rủi ro** (khách chịu được bao nhiêu biến động) lấy từ hồ sơ của khách nếu có (`riskAppetite`); không có thì coi là trung bình và nói rõ. **Khả năng chịu rủi ro** xét từ thời gian còn lại, quỹ dự phòng đã đủ chưa và mức trả vay trên thu nhập.

## Luật chọn và ràng buộc

- **Khả thi** nhất quán (ngưỡng của M-You, không phải quy định của ngân hàng): giai đoạn nào kỳ trả vay vượt 70% phần còn dư, hoặc trả vay trên thu nhập vượt 40%, hoặc số vay quá 80% giá mục tiêu thì **không khả thi**. Không khả thi thì không được gọi là "khả thi về dòng tiền" và không được khuyến nghị.
- Khẩu vị thận trọng hoặc khả năng chịu rủi ro thấp (còn ít thời gian, quỹ dự phòng chưa đủ, trả vay sát ngưỡng) → ủng hộ không vay hoặc vay muộn, nói rõ vì sao. Mục tiêu nhỏ hoặc dòng tiền dư dả: nói thẳng **không cần vay**; không bao giờ gợi ý vay tiêu dùng để bù một mục tiêu khách tiết kiệm đủ.
- Thẻ có từ **1 đến 3** phương án, tool tự lọc: "Không vay" luôn có; "Vay mua ngay" chỉ hiện khi khả thi; "Kết hợp tối ưu" chỉ hiện khi thực sự cần vay và có tháng khả thi. Đừng nhắc tới phương án không có trên thẻ như thể nó tồn tại; thẻ chỉ có "Không vay" mà vẫn trễ hạn thì nói thẳng là vay cũng chưa khả thi với dòng tiền hiện tại.
- Phương án và lời khuyên chỉ lấy từ thẻ của tool; không tự đổi phương án khuyến nghị.

## Mọi con số lấy từ tool

- Mọi số tiền, năm đạt, kỳ trả vay, tổng lãi, lãi tiết kiệm, giá sau khi tăng và các mốc nằm trong thẻ của `build_goal_plan_card`. Nếu phần chữ nêu số, chép nguyên văn từ nội dung tool trả về. Không tự nhân, cộng, chia, làm tròn; số nào không có trong kết quả tool thì không nêu. Không dùng `calculate_deposit_interest` cho khoản vay.
- `simulate_goal_plan`, `loan_quote`, `savings_projection`, `project_target`, `plan_monthly` chỉ dùng để trả lời một câu hỏi lẻ khách hỏi thêm sau đó, không dùng để dựng phương án.
- Tool báo tham số không hợp lệ hoặc lỗi → nói chưa tính được, đừng bịa thẻ.
- Lãi suất, điều kiện, hotline và mọi con số về sản phẩm MSB chỉ nêu khi có trong kết quả `search_msb_knowledge`, kèm đúng URL của đoạn đó; chép **nguyên văn** URL, không sửa, không rút gọn. Mức giả định của bạn (ví dụ 8%/năm) ghi là "giả định" và **không** gắn link nguồn vào nó. Không nói về lãi khi rút trước hạn, bảo hiểm tiền gửi hay điều gì khác không có trong kết quả tra cứu. Đừng nêu tỷ lệ vốn tự có tối thiểu, mức ưu đãi hay thời hạn ưu đãi của lãi vay nếu kết quả tra cứu không ghi; đừng tự tính số góp hằng tháng cần có.
- **Điều chỉnh** (kéo dài thời hạn, giảm số tiền mục tiêu, đổi tỷ lệ vay): chỉ nêu con số cụ thể khi đã chạy lại `build_goal_plan_card` (hoặc `simulate_goal_plan` cho một câu hỏi lẻ) với đúng con số đó. Chưa chạy lại thì chỉ nêu hướng bằng lời và đề nghị tính lại cho con số khách chọn; không tự đoán một mức "sẽ đủ".
- Luôn dùng "trả vay" khi nói về kỳ trả của khoản vay, kể cả khoản khách đang có (viết "khoản trả vay đang có 3,5 triệu/tháng"; không dùng chữ "nợ" cho kỳ trả hằng tháng).

## Khi khách chọn một phương án trên thẻ (hướng dẫn cho bạn, không viết ra trong lượt gọi tool)

Nút "Chọn phương án này" tự đặt phương án làm lộ trình của mục tiêu (màn Mục tiêu → Lộ trình) và **không gửi tin nào về cho bạn**, nên bạn sẽ không nhận được câu "Tôi chọn phương án …". Vì vậy ngay trong phần chữ trước thẻ hãy nói một câu: bấm "Chọn phương án này" để đặt lộ trình đó cho mục tiêu «tên»; nếu cần, nhắc khách có thể nhờ bạn chỉnh mức trích tự động bằng `edit_goal` (skill `goal-manage`). Không dựng lại thẻ trừ khi khách đổi số liệu.

## Lỗi hay gặp, tránh

- Viết hoàn toàn bằng tiếng Việt: không lẫn từ tiếng Anh ("cost", "feasible"...).
- Trạng thái của một mục tiêu trong `get_goals` có chữ "nợ" thì khi nhắc lại, thay bằng "vay" (ví dụ "đang trả vay").
- Khi đề xuất điều chỉnh (kéo dài thời hạn, giảm số tiền mục tiêu), **không nêu con số cụ thể chưa tính lại**. Sai: nêu một mức tiền hoặc một số năm cụ thể mà chưa chạy lại tool, kể cả dạng "ví dụ" hay "khoảng". Đúng: "giảm số tiền mục tiêu", "kéo dài thời hạn", rồi hỏi khách muốn thử mức nào để mình tính lại; khi khách nêu con số thì gọi lại `build_goal_plan_card` với đúng con số đó.

## Khuôn câu trả lời (chỉ phần chữ, thẻ do hệ thống gắn)

Câu đầu tiên đã là nội dung trả lời cho khách, **không** nhắc tới skill, quy tắc, công cụ hay việc "không dùng khối nút"; **cấm** câu dẫn kiểu "Tôi đã có đủ số liệu", "Giờ tôi soạn các phương án", "Tóm tắt dữ liệu:". Thẻ chỉ vẽ tên phương án, một dòng tóm tắt và các mốc, nên phần chữ **thật ngắn: 3 đến 4 câu, không quá 70 từ**, không gạch đầu dòng, không bảng:

1. **Kịch bản gốc** trong một câu: dòng tiền còn dư mỗi tháng và, nếu không vay, đạt mục tiêu năm nào hoặc thiếu bao nhiêu ở hạn. Không kể lại thu nhập, chi tiêu, quỹ dự phòng.
2. **Phương án khuyến nghị và vì sao** trong một câu, theo khẩu vị rủi ro và khả năng chịu rủi ro của khách, kèm khoản trả vay mỗi tháng nếu có vay. Nếu thẻ không có phương án nào chọn được, nói thẳng là chưa phương án nào khả thi và hỏi bằng **một câu** khách muốn thử cách nào (kéo dài thời hạn, giảm số tiền mục tiêu, tăng phần dành cho mục tiêu), không liệt kê từng cách thành danh sách; tổng vẫn không quá 90 từ.
3. **Một câu cuối** gộp: giả định là mặc định để minh hoạ, không phải dự báo (chỉ nêu lãi suất tiết kiệm và lãi vay đã dùng), vay thật làm ở Mục tiêu → Vay khi tới mốc, và bấm "Chọn phương án này" để đặt lộ trình đó cho mục tiêu «tên». Không nhắc ngày lưu của dữ liệu lãi suất, không trích dẫn số nguồn.

**Không lặp lại các mốc hay số liệu theo từng phương án trong phần chữ**: chúng đã có trong thẻ, chỉ tên phương án và mốc, không có chip số liệu. Không kèm khối `clarify_options` trong cùng câu trả lời: thẻ đã có nút "Chọn phương án này" của riêng nó. Thẻ do `build_goal_plan_card` dựng và **hệ thống tự gắn** vào câu trả lời: **không dán, không viết khối `ui-json`** (viết lại thẻ vừa chậm vừa dễ sai), chỉ viết phần chữ và dừng. Không tự viết khối `plan_roadmap`.

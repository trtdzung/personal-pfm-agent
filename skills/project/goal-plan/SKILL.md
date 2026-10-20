---
name: goal-plan
description: Dùng khi khách hỏi nên tích luỹ thế nào để đạt một mục tiêu đúng hạn, hoặc khi nào nên vay — ví dụ "tôi muốn mua căn hộ 2 tỷ trong 7 năm, nên tích luỹ và vay thế nào", "mua xe 800 triệu trong 3 năm, nên tiết kiệm hay vay", "có nên vay sớm không", "tiết kiệm bao nhiêu mỗi tháng rồi vay phần còn lại". Lập kế hoạch từ dòng tiền thật, gồm quỹ dự phòng trước, kịch bản gốc, rồi các phương án (không vay, có vay, kết hợp tối ưu) kèm lợi suất, kỳ trả vay, kịch bản xấu, trình bày thành một thẻ lộ trình theo mốc để khách chọn bằng nút trên thẻ. Cũng dùng ngay sau khi khách tạo mục tiêu trên thẻ, khi tin nhắn của khách bắt đầu bằng "Mình đã tạo mục tiêu", để hỏi khách có tài sản sẵn có nào muốn dùng cho mục tiêu rồi gợi ý lộ trình. Không dùng để tạo/đổi/đóng mục tiêu (skill goal-manage) hay giải thích thẻ M-You gợi ý (skill goal-insight). Chỉ đề xuất, không thực thi.
---

# Kế hoạch đạt mục tiêu: một thẻ lộ trình (chỉ đề xuất, không thực thi)

Chat **không tạo được khoản vay, lệnh nạp hay gửi tiết kiệm**. Skill này lập kế hoạch và so sánh; phần vay khách tự làm ở màn Mục tiêu → Vay khi tới mốc. Các phương án và mốc của chúng nằm **chỉ trong thẻ `plan_roadmap`** do tool `build_goal_plan_card` dựng; phần chữ của bạn ngắn và không lặp lại chúng.

## Ngay sau khi khách tạo mục tiêu

Khi tin nhắn của khách có dạng "Mình đã tạo mục tiêu «tên»." (pfm gửi tự động sau khi khách xác nhận thẻ tạo mục tiêu), làm lần lượt, **mỗi bước một lượt trả lời**:

1. Gọi `get_goals`, tìm mục tiêu theo tên: lấy số tiền, hạn và **giá trị hiện có** của tài khoản mục tiêu. Không thấy mục tiêu đó thì nói chưa thấy và hỏi lại tên, dừng.
2. Hỏi bằng **đúng một** khối `clarify_options` (skill `clarify-options`), một câu hỏi "Bạn có tài sản nào sẵn có muốn dùng để tích luỹ cho «tên» không?" với ba lựa chọn "Có, mình có tài sản sẵn có để dùng cho «tên»", "Không có, gợi ý lộ trình cho «tên» ngay", "Để sau". Phần dẫn trước khối chỉ một câu ngắn (ghi nhận mục tiêu đã tạo, nói sẽ gợi ý lộ trình để đạt đúng hạn). **Chưa** gọi `build_goal_plan_card` ở lượt này. Lượt này **bắt buộc** dùng khối nút: không hỏi bằng chữ thay cho khối, không phân tích dòng tiền hay nêu khoản góp còn thiếu (việc đó để thẻ lộ trình ở lượt sau), và khối là phần cuối cùng của câu trả lời. Chỉ nhắc nhóm tài sản tính được (tiền gửi, vàng, cổ phiếu, quỹ), không nhắc xe hay nhà.
3. Khách chọn "Có" thì hỏi **bằng chữ** loại tài sản và giá trị ước tính hôm nay (tiền gửi, vàng, cổ phiếu, quỹ; nhà, xe để mua thì không tính); khách chỉ nói số lượng như "5 chỉ vàng" thì tra giá bằng `get_goal_market` hoặc hỏi lại giá trị, đừng tự định giá. Khách chọn "Không có" thì làm bước 4 ngay. Khách chọn "Để sau" thì đáp một câu là cần lúc nào cứ nhắn, **không gọi tool**, dừng.
4. Lập lộ trình theo mục "Việc cần làm" (số tiền và hạn lấy từ mục tiêu, không hỏi lại), với `extra_assets_vnd` bên dưới. Thẻ có từ 1 đến 3 phương án. Trong phần chữ nói rõ đã tính những tài sản nào và hỏi khách có muốn gắn chúng vào mục tiêu để theo dõi không (nếu muốn thì dùng skill `goal-asset` ở lượt sau).

## Việc cần làm, theo thứ tự

1. Gọi `get_goals`: thu nhập, chi tiêu trung bình, **phần còn dư**, số dư tài khoản chính, tài sản của các mục tiêu (cả của MSB và ngoài MSB), khoản trả vay đang có, `today`, các mục tiêu khác (chúng đã chiếm một phần dư). Lỗi hoặc thiếu dữ liệu thu chi → nói chưa biết dòng tiền, hỏi khách ước phần dư, đừng đoán.
2. Thiếu số tiền hoặc thời hạn → hỏi lại bằng nút theo skill `goal-manage` (mục "Hỏi lại khi thiếu số tiền hoặc thời hạn"); khách chưa rõ giá thì dùng `estimate_goal_price` trước.
3. Gọi `search_msb_knowledge` (tối đa 2 lần): lãi suất tiết kiệm (một mức nhất quán: **tiền gửi online kỳ 12 tháng**) và lãi suất vay đúng loại mục tiêu (nhà, xe, tiêu dùng). Không tra được lãi vay → dùng một giả định, nói rõ là giả định.
4. Gọi `build_goal_plan_card` **đúng một lần** với đầu vào ở mục dưới. Tool tự chạy kịch bản gốc, phương án không vay, vay mua ngay, kết hợp tối ưu và kịch bản xấu của từng phương án, rồi trả về thẻ hoàn chỉnh.
5. Viết phần chữ ngắn và dán khối ```ui-json của tool ở cuối (mục "Khuôn câu trả lời").

## Đầu vào của `build_goal_plan_card`

- `goal_name`, `target_amount_vnd` (giá hôm nay), `months_to_deadline`.
- `start_cash_vnd`: tiền có thể dùng ngay = số dư tài khoản chính + tiền gửi, kể cả tiền gửi/tiết kiệm ngoài MSB nếu khách đã khai trong tài sản và đang để tự do. **Không** tính tiền đang nằm trong tài khoản của các mục tiêu khác (chúng đã dành cho mục tiêu đó). Cổ phiếu, vàng, quỹ, nhà, xe **không** tính vào tiền mặt (nói rõ là chưa tính, khách có thể bán khi cần).
- `extra_assets_vnd`: giá trị hôm nay của những gì khách **đã có cho mục tiêu này** = số dư tài khoản của chính mục tiêu (từ `get_goals`) + tài sản khách vừa khai ở bước hỏi tài sản (tiền gửi, vàng, cổ phiếu, quỹ). Không cộng trùng tài sản đã được gắn vào mục tiêu trong `get_goals`, và không đưa tiền này vào `start_cash_vnd`. Số này đi thẳng vào mục tiêu, không dùng để lấp quỹ dự phòng. Ngoài luồng "vừa tạo mục tiêu", chỉ dùng khi khách nói rõ có tài sản dành cho mục tiêu; mặc định 0.
- `monthly_income_vnd`, `monthly_spending_vnd` (chi tiêu trung bình; số "chi tiêu" của `get_goals` **đã không gồm** kỳ trả vay đang có, nên truyền **nguyên văn**, không trừ thêm kỳ trả vay vào đó), `existing_debt_payment_vnd` (tổng kỳ trả vay đang có) lấy nguyên từ `get_goals`.
- `other_goals_monthly_vnd`: tổng **"cần góp mỗi tháng"** của **các mục tiêu khác đang hoạt động** (đang tích luỹ hoặc đang trả vay; lấy từ `get_goals`), để không tính trùng phần dư; không có mục tiêu khác thì bỏ qua (mặc định 0). Dùng số "cần góp mỗi tháng", **không** dùng số "trích tự động" đang cài, vì khách có thể cài trích nhiều hơn mức cần. Nếu tổng trích tự động đang cài lớn hơn tổng cần góp, nói ngắn với khách rằng họ đang trích dư và có thể giảm để dành cho mục tiêu mới.
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

Khách bấm "Chọn phương án này" sẽ gửi câu "Tôi chọn phương án ...". Xác nhận lại ngắn phương án và hỏi có tạo hoặc đổi mục tiêu theo số góp đó không; nếu có thì chuyển sang skill `goal-manage` (`create_goal` hoặc `edit_goal`, gọi `get_goals` trước như skill đó yêu cầu). Không dựng lại thẻ trừ khi khách đổi số liệu.

## Lỗi hay gặp, tránh

- Viết hoàn toàn bằng tiếng Việt: không lẫn từ tiếng Anh ("cost", "feasible"...).
- Trạng thái của một mục tiêu trong `get_goals` có chữ "nợ" thì khi nhắc lại, thay bằng "vay" (ví dụ "đang trả vay").
- Khi đề xuất điều chỉnh (kéo dài thời hạn, giảm số tiền mục tiêu), **không nêu con số cụ thể chưa tính lại**. Sai: nêu một mức tiền hoặc một số năm cụ thể mà chưa chạy lại tool, kể cả dạng "ví dụ" hay "khoảng". Đúng: "giảm số tiền mục tiêu", "kéo dài thời hạn", rồi hỏi khách muốn thử mức nào để mình tính lại; khi khách nêu con số thì gọi lại `build_goal_plan_card` với đúng con số đó.

## Khuôn câu trả lời (khối thẻ là phần cuối cùng)

Câu đầu tiên đã là nội dung trả lời cho khách (nhận định về dòng tiền của họ), **không** nhắc tới skill, quy tắc, công cụ hay việc "không dùng khối nút"; **cấm** câu dẫn kiểu "Tôi đã có đủ số liệu", "Giờ tôi soạn các phương án", "Tóm tắt dữ liệu:". Phần chữ **ngắn** (khoảng 5 đến 8 câu), theo thứ tự:

1. **Nền kế hoạch**: dòng tiền thật (thu, chi, phần còn dư), quỹ dự phòng 3 tháng cần bao nhiêu, phần tiền thực sự dành cho mục tiêu.
2. **Kịch bản gốc** trong một câu (không vay thì đạt mục tiêu năm nào hoặc thiếu bao nhiêu ở hạn).
3. **Vì sao phương án được khuyến nghị** theo khẩu vị rủi ro và khả năng chịu rủi ro; hoặc, nếu thẻ không có phương án nào chọn được, nói thẳng là chưa phương án nào khả thi, đề xuất các cách điều chỉnh **bằng lời** (kéo dài thời hạn, giảm số tiền mục tiêu, tăng phần dành cho mục tiêu) rồi hỏi bằng chữ khách muốn thử cách nào (thẻ vẫn hiển thị các phương án).
4. **Giả định cần khách xác nhận** (lãi suất, mức tăng; mặc định để minh hoạ, không phải dự báo, không hứa lợi nhuận) và nhắc: vay thật làm ở Mục tiêu → Vay khi tới mốc; tổng lãi vay chỉ là ước tính.

**Không lặp lại các mốc hay số liệu theo từng phương án trong phần chữ**: chúng đã có trong thẻ. Không kèm khối `clarify_options` trong cùng câu trả lời: thẻ đã có nút "Chọn phương án này" của riêng nó. Sau phần chữ, dán khối ```ui-json do `build_goal_plan_card` trả về **nguyên văn, không sửa một ký tự**, làm **phần cuối cùng** của câu trả lời, không viết thêm gì sau khối. Không tự viết khối `plan_roadmap`: thẻ không phải do tool dựng sẽ bị loại.

Dưới đây chỉ là ví dụ về hình dạng của khối (số liệu minh hoạ, không được dùng lại); luôn dán khối của tool.

```ui-json
{"type": "plan_roadmap", "title": "Xe 300 triệu · 3 năm", "baseline": "Đạt mục tiêu ở tháng 19 (năm thứ 2), đúng hạn", "assumptions": ["Lãi tiết kiệm 6,8%/năm", "Lãi vay 8%/năm, 60 tháng", "Giá mục tiêu +2%/năm", "Quỹ dự phòng 3 tháng chi tiêu"], "plans": [{"id": "no_loan", "name": "Không vay", "verdict": "recommended", "headline": "Đạt mục tiêu ở tháng 19 (năm thứ 2), đúng hạn", "metrics": [{"label": "Lãi tiết kiệm", "value": "13,75 triệu–16,3 triệu"}], "milestones": [{"when": "Tháng 0", "kind": "reserve", "title": "Lập quỹ dự phòng", "detail": "Cần 45 triệu, đang có 45 triệu (chưa tính vào mục tiêu)"}, {"when": "Tháng 1–19", "kind": "save", "title": "Góp phần còn dư vào tiết kiệm", "action": "Góp khoảng 15 triệu/tháng vào tiết kiệm MSB"}, {"when": "Tháng 19 (năm thứ 2)", "kind": "buy", "title": "Mua mục tiêu"}], "risk": "Nếu thu nhập không tăng, lãi vay +2 điểm và lãi tiết kiệm -1 điểm: đạt mục tiêu ở tháng 20 (năm thứ 2)", "choice_text": "Tôi chọn phương án Không vay: đạt mục tiêu ở tháng 19 (năm thứ 2), đúng hạn"}, {"id": "loan_now", "name": "Vay mua ngay", "verdict": "not_recommended", "headline": "Mua ngay hôm nay, vay 285 triệu", "reason": "số vay vượt 80% giá mục tiêu", "metrics": [], "milestones": []}]}
```

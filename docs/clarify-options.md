# Hỏi lại bằng nút bấm (`clarify_options`) — hướng dẫn cho frontend

Loại UI thứ 7 agent có thể trả ra qua field `ui` (cùng envelope với `chart`/`transfer_form`/các form hũ —
xem [`docs/api.md`](./api.md)) — chỉ khác `ui.type`. **Cross-cutting:** không gắn với 1 flow cụ thể (hũ,
chuyển tiền...) mà dùng chung cho mọi skill khi agent cần khách quyết định giữa vài phương án cụ thể thay
vì hỏi lại bằng 1 câu mở. Model-facing rules: `skills/project/clarify-options/SKILL.md`.

## `answer` vẫn có nội dung — nhưng chỉ là 1 câu dẫn ngắn, câu hỏi cụ thể nằm trong `ui`

Với mọi loại `ui`, `answer` luôn có nội dung. Với `clarify_options`, nội dung `answer` là **1 câu dẫn thật
ngắn** (ví dụ "Bạn hãy trả lời các câu hỏi sau để..."), KHÔNG lặp lại nội dung của bất kỳ câu hỏi/lựa chọn
nào — nội dung cụ thể của từng câu hỏi nằm trong `ui.questions[].question`, lựa chọn nằm trong
`ui.questions[].options`. **Frontend hiện cả 2**: `answer` làm câu dẫn, rồi `ui.questions` làm các câu hỏi
kèm nút bấm ngay bên dưới — không phải chỉ hiện 1 trong 2 chỗ.

## Có thể có nhiều hơn 1 câu hỏi trong cùng 1 lượt

`ui.questions` là **mảng 1–4 câu hỏi độc lập** — giống cách công cụ hỏi-lại-người-dùng của Claude
(`AskUserQuestion`) cho phép hỏi vài điều cùng lúc. Agent chỉ hỏi nhiều câu khi cả các quyết định đó đều
thật sự cần thiết (ví dụ vừa không rõ hũ nào, vừa không rõ tăng bao nhiêu tiền) — phần lớn các lượt vẫn chỉ
có đúng 1 câu hỏi, nhưng frontend cần dựng UI cho được cả 2 trường hợp.

## Khi nào agent trả `clarify_options`

Hai trường hợp:

1. **Phân biệt giữa các thực thể có thật** (hũ/thẻ/người nhận...) — chỉ khi **cả 2** điều kiện đúng cho
   mỗi câu hỏi: (1) agent đã thử tự quyết định theo quy tắc riêng của flow đang dùng mà vẫn còn ≥ 2 phương
   án hợp lý ngang nhau, và (2) có **2–4** phương án cụ thể dựa trên dữ liệu thật (tên hũ + số tiền, tên
   thẻ + dư nợ, tên người nhận + số tài khoản...). Đây là phương án cuối cùng — không phải cách để agent
   né việc tự quyết định, nên tần suất xuất hiện nên hiếm.
2. **Khảo sát sở thích/nhu cầu của khách** (ví dụ khách tự nói "hỏi tôi các câu hỏi để biết nhu cầu đầu tư
   của tôi") — lựa chọn là **nhóm phân loại chuẩn** (mức rủi ro, khung thời gian, khoảng số tiền, mục
   tiêu...), không cần và không nên giả là dữ liệu thật riêng của khách. Chỉ dùng khi khách chủ động muốn
   được hỏi kiểu này, không thay cho việc agent tự suy luận được từ dữ liệu thật đã có.

## Response `POST /chat`

Ví dụ 1 câu hỏi:

```json
{
  "answer": "Bạn đang có 2 hũ tên gần giống nhau, mình cần hỏi rõ hơn.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "clarify_options",
    "questions": [
      {
        "question": "Bạn muốn lấy tiền từ hũ nào?",
        "options": ["Hũ Ăn uống (còn 1.813.000đ)", "Hũ Ăn uống ngoài (còn 620.000đ)"]
      }
    ]
  }
}
```

Ví dụ 2 câu hỏi độc lập trong cùng 1 lượt:

```json
{
  "answer": "Mình cần hỏi thêm 2 điều để tăng đúng hạn mức bạn muốn.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "clarify_options",
    "questions": [
      {
        "question": "Bạn muốn tăng hạn mức hũ nào?",
        "options": ["Hũ Ăn uống nhà (hạn mức 4.000.000đ)", "Hũ Ăn uống ngoài (hạn mức 1.000.000đ)"]
      },
      {
        "question": "Tăng thêm bao nhiêu?",
        "options": ["100.000đ", "200.000đ", "500.000đ"]
      }
    ]
  }
}
```

Ví dụ khảo sát sở thích (nhóm lựa chọn chuẩn, không phải dữ liệu thật của khách):

```json
{
  "answer": "Bạn hãy trả lời các câu hỏi sau để mình tư vấn đúng nhu cầu.",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "clarify_options",
    "questions": [
      {"question": "Bạn muốn đầu tư khoảng bao nhiêu?", "options": ["Dưới 10 triệu", "10–50 triệu", "50–200 triệu", "Trên 200 triệu"]},
      {"question": "Mục tiêu chính của bạn là gì?", "options": ["Đạt một số tiền cụ thể trước một mốc thời gian", "Tích lũy dài hạn", "Bảo toàn vốn, hạn chế rủi ro"]},
      {"question": "Bạn muốn đầu tư trong bao lâu?", "options": ["Dưới 6 tháng", "6–12 tháng", "Trên 1 năm"]},
      {"question": "Mức độ rủi ro bạn chấp nhận được?", "options": ["An toàn, ưu tiên giữ vốn", "Cân bằng", "Chấp nhận rủi ro cao để kỳ vọng sinh lời"]}
    ]
  }
}
```

## Schema của `ui`

| Field | Bắt buộc | Kiểu | Ghi chú |
|---|---|---|---|
| `type` | ✅ | `"clarify_options"` | discriminator |
| `questions` | ✅ | mảng **1–4 phần tử** | luôn là mảng, kể cả khi chỉ có 1 câu hỏi |
| `questions[].question` | ✅ | string, không rỗng | nội dung câu hỏi cho khách — không lặp lại trong `answer` |
| `questions[].options` | ✅ | mảng **string thuần**, 2–4 phần tử | mỗi string là nội dung 1 nút bấm; không rỗng, không trùng nhau trong cùng câu hỏi |

Không có field nào khác ở bất kỳ cấp nào (không có `reason`, không có `id` — mỗi lựa chọn chỉ là 1 string,
**không** phải object `{"label": ..., "id": ...}`; không có `question`/`options` ở cấp ngoài `questions`).

## Luồng UI gợi ý — quan trọng nhất là cách gửi lại lựa chọn

1. Nhận `ui.type === "clarify_options"` → hiện `answer` làm câu dẫn, rồi với mỗi phần tử của
   `ui.questions`, hiện `question` làm câu hỏi kèm 2–4 nút bấm theo đúng thứ tự và nội dung `options`.
   Nhiều câu hỏi thì hiện tuần tự hoặc cùng lúc trên 1 màn hình, tuỳ UX — miễn khách trả lời được hết
   trước khi gửi.
2. **Chỉ 1 câu hỏi:** khi khách bấm 1 nút, gọi `POST /chat` như 1 tin nhắn bình thường của khách, với
   `message` = **đúng nguyên văn string của lựa chọn đó**.
3. **Nhiều câu hỏi:** đợi khách chọn xong lựa chọn cho **tất cả** các câu, rồi gộp các lựa chọn đã chọn
   thành **1 tin nhắn duy nhất**, nối theo đúng thứ tự các câu hỏi trong `questions`, mỗi lựa chọn cách
   nhau bằng `". "` (dấu chấm + khoảng trắng). Ví dụ 2 câu hỏi ở trên, khách chọn "Hũ Ăn uống nhà (hạn mức
   4.000.000đ)" và "200.000đ" → gửi:
   ```
   Hũ Ăn uống nhà (hạn mức 4.000.000đ). 200.000đ.
   ```
   Đây **không phải** 1 cơ chế riêng — dùng lại y hệt request `POST /chat` thông thường
   (`{"message": "<đã gộp>", "user_id": ..., "thread_id": ...}` trên cùng `thread_id` đang chat), agent
   nhận nó như 1 câu khách tự gõ, dựa vào chính các câu hỏi vừa hỏi (còn trong lịch sử) để hiểu đúng phần
   nào ứng với câu nào. Không có endpoint hay field nào khác để "gửi lựa chọn" — `/chat` hoàn toàn không
   đổi để hỗ trợ loại `ui` này.
4. Khách vẫn có thể **bỏ qua nút bấm và tự gõ câu trả lời khác** (kể cả khi có nhiều câu hỏi, khách có thể
   gõ 1 câu tự nhiên trả lời cả 2 việc luôn) — kênh chat vẫn mở bình thường, nút bấm chỉ là lối tắt.
5. Nếu `ui` là `null` hoặc `ui.type` chưa hỗ trợ, chỉ hiện `answer` như bình thường.

## `GET /chat/history`

Một lượt `clarify_options` trong lịch sử có `content` = đúng câu dẫn ngắn mà model đã viết (không rỗng) và
`ui` giữ nguyên — hiện lại y hệt lúc gửi live: `content` làm câu dẫn, `ui.questions` làm các câu hỏi/nút
bấm.

## Lưu ý về độ tin cậy

`server.py` chỉ kiểm **hình dạng**: đủ field `questions` (1–4 phần tử), mỗi phần tử đủ `question`/`options`
đúng kiểu, `options` là mảng 2–4 string không rỗng và không lặp trong cùng câu hỏi, không có field ngoài
schema ở bất kỳ cấp nào. Server **không** đối chiếu nội dung mỗi lựa chọn với dữ liệu thật của khách (số
tiền, tên hũ/thẻ có đúng không) — không có tool nào để làm việc đó cho mọi loại dữ liệu khác nhau agent có
thể hỏi (hũ, thẻ, người nhận...); frontend nên coi nội dung mỗi lựa chọn là "agent tự đọc dữ liệu và tóm
tắt", không phải số đã qua kiểm định như `rebalance_jars`/`distribute_amount`.

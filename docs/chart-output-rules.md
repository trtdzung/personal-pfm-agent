# Rule: Output field `chart` — bắt buộc Agent và Backend tuân thủ

**Đối tượng áp dụng: cả 2 tầng phía backend** —
1. **Agent (LLM)** — nơi quyết định có chèn khối JSON mô tả chart hay
   không (skill nội bộ `skills/project/data-visualization/` được nhắc
   tới trong `chart-visualization.md`).
2. **`server.py`** — tầng parse/validate output của agent và trả field
   `chart` ra response `POST /chat`.

Đây không phải tài liệu tham khảo — đây là **rule bắt buộc**. Sai bất kỳ
điều "MUST" nào bên dưới (ở tầng nào cũng vậy) sẽ khiến frontend tự động
huỷ toàn bộ chart (ẩn khỏi UI, không có ngoại lệ, không cảnh báo).

## Bối cảnh: frontend render bằng gì

Frontend (Next.js 16 + React 19) render field `chart` bằng thư viện
**Recharts `^3.10.1`**, map gần như 1-1 từ JSON sang component
`<BarChart>`/`<LineChart>`/`<PieChart>`. Frontend **không tự sửa, không
tự suy luận** dữ liệu sai — chỉ có 2 khả năng: vẽ đúng như JSON nhận
được, hoặc bỏ qua toàn bộ (im lặng, không báo lỗi cho khách hàng). Vì
vậy đúng định dạng ở phía agent là điều kiện duy nhất để chart hiển thị.

## Phần A — Yêu cầu đối với Agent (LLM)

### A.MUST (bắt buộc)

1. Khi chèn chart, PHẢI sinh đúng 1 khối JSON hợp lệ theo chuẩn JSON
   thật (dấu nháy kép `"..."`), không phải Python dict repr (dấu nháy
   đơn `'...'`).
2. `chart_type` PHẢI là đúng 1 trong 3 giá trị, chữ thường tuyệt đối:
   `"bar"` | `"line"` | `"pie"`.
3. `labels` PHẢI là mảng string, KHÔNG được rỗng.
4. `series` PHẢI là mảng KHÔNG rỗng; mỗi phần tử PHẢI có đúng 2 field:
   `name` (string) và `data` (mảng number).
5. **Quan trọng nhất:** với MỌI phần tử trong `series`, PHẢI đảm bảo
   `len(data) == len(labels)`. Đây là điều kiện duy nhất frontend
   validate cứng để quyết định vẽ hay huỷ chart — lệch dù chỉ 1 phần tử
   ở 1 series là toàn bộ chart bị ẩn.
6. Giá trị trong `data` PHẢI là number JSON thật, ví dụ `5130000` —
   TUYỆT ĐỐI KHÔNG dùng string số như `"5130000"`.
7. Với `chart_type: "pie"`, PHẢI chỉ sinh đúng 1 phần tử trong `series`
   (pie không có khái niệm nhiều series — frontend chỉ đọc `series[0]`,
   phần còn lại bị bỏ qua).
8. Khi câu hỏi không cần chart, PHẢI không sinh khối JSON chart (để
   backend tự set `chart: null` — xem Phần B).

### A.MUST NOT (tuyệt đối không được)

- KHÔNG tự thêm field ngoài 4 field đã định nghĩa (`chart_type`,
  `title`, `labels`, `series`).
- KHÔNG dùng `chart_type` nào khác ngoài 3 giá trị ở mục A.MUST-2.
- KHÔNG để `series` rỗng, `labels` rỗng, hoặc `data` rỗng khi đã quyết
  định chèn chart (nếu không có dữ liệu để vẽ, đừng chèn khối JSON,
  đừng chèn chart với mảng rỗng).

## Phần B — Yêu cầu đối với Backend (`server.py`)

Backend là **lớp phòng thủ cuối cùng** trước khi dữ liệu ra tới frontend
— không được tin tưởng tuyệt đối là agent luôn tuân thủ đúng Phần A.

### B.MUST (bắt buộc)

1. PHẢI tách (parse + strip) khối JSON chart ra khỏi `answer` bằng một
   parser ổn định (không dùng string-matching thô sơ) — `answer` trả về
   client TUYỆT ĐỐI không được lẫn khối JSON/dict thô, dù agent sinh
   đúng hay sai định dạng.
2. PHẢI tự validate lại toàn bộ theo đúng schema trước khi set field
   `chart` — không tin agent đã làm đúng Phần A:
   - `chart_type` thuộc đúng `{"bar", "line", "pie"}`
   - `labels` là mảng string, không rỗng
   - `series` là mảng không rỗng, mỗi phần tử có `name` (string) +
     `data` (mảng number)
   - **mọi** `len(data) == len(labels)`
3. Nếu bất kỳ điều nào ở B.MUST-2 fail, hoặc khối JSON agent sinh ra
   không parse được — PHẢI fallback về `chart: null`. KHÔNG được để lọt
   JSON thiếu field/sai kiểu ra ngoài, dù chỉ 1 field.
4. Với `chart_type: "pie"` mà agent lỡ sinh nhiều hơn 1 phần tử trong
   `series`: PHẢI tự cắt còn đúng `series[0]` trước khi trả (không dựa
   hoàn toàn vào việc agent tuân thủ A.MUST-7).
5. Field `chart` PHẢI luôn xuất hiện trong response `POST /chat` (kể cả
   khi giá trị là `null`) — KHÔNG được omit field này.
6. `GET /chat/history` và `DELETE /chat/history` PHẢI KHÔNG BAO GIỜ trả
   field `chart` — giữ đúng hành vi đã mô tả trong `chart-visualization.md`,
   ghi rõ thành rule ở đây để tránh bị đổi ngoài ý muốn về sau.

### B.NÊN CÓ (khuyến nghị, không bắt buộc)

- Khi fallback về `chart: null` do sai định dạng (B.MUST-3), nên log
  lại raw output của agent (khối JSON gốc trước khi validate fail) để
  dễ debug khi agent sinh sai — tương tự cách `todo.md` đang track lỗi
  lọt tool-call JSON vào `GET /chat/history`.

## Ví dụ ĐÚNG

```json
{
  "chart_type": "pie",
  "title": "Chi tiêu theo danh mục - Tháng 8/2026",
  "labels": ["Mua sắm", "Siêu thị", "Ăn uống", "Di chuyển", "Hoá đơn", "Giải trí"],
  "series": [
    { "name": "VND", "data": [5130000, 2870000, 2585000, 2100000, 900000, 599000] }
  ]
}
```

```json
{
  "chart_type": "bar",
  "title": "So sánh chi tiêu Tháng 7 vs Tháng 8",
  "labels": ["Mua sắm", "Siêu thị", "Ăn uống", "Di chuyển", "Hoá đơn", "Giải trí"],
  "series": [
    { "name": "Tháng 7", "data": [5730000, 2600000, 2400000, 7100000, 850000, 620000] },
    { "name": "Tháng 8", "data": [5130000, 2870000, 2585000, 2100000, 900000, 599000] }
  ]
}
```

## Ví dụ SAI (frontend sẽ huỷ chart nếu lọt tới đó — Backend PHẢI chặn trước ở tầng B, không được để những case này ra tới response)

```
# SAI 1 — Python dict repr, không phải JSON (nháy đơn, không phải nháy kép)
# → agent vi phạm A.MUST-1; nếu server.py không tự parse/chuẩn hoá được,
#   PHẢI fallback chart: null theo B.MUST-3, không được trả nguyên văn.
{'chart_type': 'pie', 'title': '...', 'labels': [...], 'series': [...]}

# SAI 2 — data.length (5) không khớp labels.length (6)
# → vi phạm A.MUST-5; server.py PHẢI bắt được ở B.MUST-2 và trả null,
#   không được để lọt ra response.
{
  "chart_type": "bar",
  "labels": ["A", "B", "C", "D", "E", "F"],
  "series": [{ "name": "VND", "data": [1, 2, 3, 4, 5] }]
}

# SAI 3 — data là string số, không phải number
{ "series": [{ "name": "VND", "data": ["5130000", "2870000"] }] }

# SAI 4 — pie nhưng có 2 series
# → server.py PHẢI tự cắt còn series[0] theo B.MUST-4, không để nguyên
{ "chart_type": "pie", "series": [{...}, {...}] }
```

## Phân chia trách nhiệm

- **Agent** chịu trách nhiệm sinh đúng định dạng ngay từ đầu (Phần A) —
  đây là hàng phòng thủ thứ nhất.
- **Backend (`server.py`)** chịu trách nhiệm là hàng phòng thủ cuối
  cùng (Phần B): validate lại toàn bộ, tự chuẩn hoá hoặc fallback về
  `null` khi agent lỡ sai — client (frontend) không bao giờ nên là nơi
  phát hiện ra lỗi định dạng của agent.

## Việc frontend đã làm để đảm bảo tương thích

Đã render thật (không phải giả lập) bằng Recharts cho cả 3 loại chart —
bar (single + multi-series dạng grouped), line (single + multi-series
nhiều đường), pie (xác nhận toạ độ arc tính đúng từ dữ liệu thật lấy từ
agent) — và xác nhận case dữ liệu sai (mục A.MUST NOT ở trên) bị huỷ
đúng như thiết kế, không crash app. Frontend không cần đổi gì thêm —
việc còn lại là Agent + Backend tuân thủ đúng rule ở Phần A và Phần B.

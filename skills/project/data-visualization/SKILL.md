---
name: data-visualization
description: Dùng khi câu hỏi cần phân tích xu hướng, so sánh, hoặc breakdown chi tiêu theo danh mục/thời gian mà biểu đồ sẽ rõ hơn bảng số liệu thuần text (ví dụ "phân tích chi tiêu của tôi", "so sánh chi tiêu các tháng", "chi tiêu theo danh mục", "vẽ biểu đồ"). Không dùng cho câu hỏi chỉ cần 1 con số hoặc 1 câu trả lời ngắn.
---

# Data visualization (chart)

Khi câu hỏi phù hợp (xem mô tả skill ở trên), sau phần trả lời văn bản ngắn
gọn như bình thường, chèn thêm **đúng 1 khối code** ở cuối câu trả lời theo
định dạng (`ui-json` là khối chung cho mọi loại UI agent có thể trả ra —
chart là 1 loại, phân biệt bằng field `type`):

```ui-json
{"type": "chart", "chart_type": "bar", "title": "...", "labels": ["..."], "series": [{"name": "...", "data": [0]}]}
```

**Quan trọng:** server validate lại khối này rất chặt trước khi gửi cho
frontend (Recharts) vẽ. Sai bất kỳ điều "PHẢI"/"KHÔNG ĐƯỢC" nào bên dưới —
dù chỉ 1 chi tiết nhỏ — server sẽ **huỷ toàn bộ chart** (không sửa giúp,
không có ngoại lệ). Nếu không chắc chắn tạo đúng định dạng, hoặc dữ liệu
không đủ để vẽ, **đừng chèn khối này** — chỉ trả lời bằng text là đủ.

## Schema

- `type` (bắt buộc): luôn là `"chart"` cho skill này.
- `chart_type` (bắt buộc): đúng 1 trong 3 giá trị, **chữ thường**:
  `"bar"`, `"line"`, hoặc `"pie"`.
- `title` (bắt buộc): string ngắn mô tả nội dung chart.
- `labels` (bắt buộc): mảng string, **không được rỗng** — nhãn trục X
  (`bar`/`line`) hoặc tên từng lát (`pie`).
- `series` (bắt buộc): mảng object **không được rỗng**, mỗi phần tử **chỉ**
  có đúng 2 field: `name` (string) và `data` (mảng number). Mỗi phần tử là
  1 đường (`line`) hoặc 1 nhóm cột (`bar`).

## PHẢI (bắt buộc — sai 1 điều là toàn bộ chart bị huỷ)

1. JSON thật (dấu nháy kép `"..."`) — **không phải** Python dict repr
   (nháy đơn `'...'`).
2. `type` luôn là `"chart"`.
3. `chart_type` đúng 1 trong 3 giá trị ở trên, chữ thường tuyệt đối.
4. `labels` là mảng string, không rỗng.
5. `series` là mảng không rỗng; mỗi phần tử có đúng 2 field `name`+`data`.
6. **Quan trọng nhất:** với **mọi** phần tử trong `series`,
   `len(data) == len(labels)` — đếm lại số phần tử trước khi trả lời, lệch
   dù chỉ 1 là bị huỷ cả chart.
7. Giá trị trong `data` là number JSON thật, ví dụ `5130000` — **không**
   phải string như `"5130000"`.
8. `chart_type: "pie"` thì `series` **chỉ có đúng 1 phần tử** — server sẽ
   huỷ chart nếu pie có từ 2 phần tử `series` trở lên (không tự cắt bớt
   giúp).
9. Câu hỏi không cần chart thì không chèn khối này.

## KHÔNG ĐƯỢC

- Không tự thêm field ngoài 5 field đã định nghĩa (`type`, `chart_type`,
  `title`, `labels`, `series`), không thêm field lạ vào từng phần tử
  `series`.
- Không dùng `chart_type` nào khác ngoài 3 giá trị ở trên.
- Không để `series`/`labels`/`data` rỗng khi đã quyết định chèn chart —
  không đủ dữ liệu để vẽ thì đừng chèn, đừng chèn mảng rỗng cho có.
- Không chèn quá 1 khối `ui-json` trong 1 câu trả lời.

## Quy tắc khác

1. Toàn bộ số liệu trong `data` phải tính đúng từ `/customer_data.json` thật
   của khách hàng đang trò chuyện — không bịa số, giống mọi câu trả lời
   khác. **Ngoại lệ:** biểu đồ mô phỏng đầu tư (skill `investment-guidance`)
   lấy số từ tool `project_investment_growth` — khi đó **sao chép nguyên văn**
   khối `ui-json` tool trả về, không tự tính lại hay sửa số/nhãn/tên đường.
2. Sau khi đã có chart, KHÔNG lặp lại toàn bộ bảng số liệu trong phần text —
   chỉ nêu ngắn gọn kết luận chính (ví dụ danh mục nào cao nhất), chart đã
   thể hiện chi tiết.
3. Khối `ui-json` không hiển thị trực tiếp cho khách hàng — server tự
   tách khối này ra khỏi câu trả lời để gửi riêng cho frontend vẽ, nên đừng
   giải thích hay nhắc tới JSON trong phần text.

## Ví dụ ĐÚNG

Khách hỏi: "Phân tích chi tiêu theo danh mục tháng này giúp tôi."

Phần text trả lời: "Tháng này bạn chi nhiều nhất cho Mua sắm (16.280.000đ),
tiếp theo là Ăn uống (10.500.000đ)."

Kèm khối:

```ui-json
{"type": "chart", "chart_type": "pie", "title": "Chi tiêu theo danh mục - Tháng 8/2026", "labels": ["Mua sắm", "Ăn uống", "Di chuyển", "Hoá đơn", "Giải trí", "Khác"], "series": [{"name": "VND", "data": [16280000, 10500000, 4200000, 3800000, 2100000, 1200000]}]}
```

So sánh 2 tháng (dùng `bar`, nhiều phần tử `series` — chỉ `pie` mới bị giới
hạn 1 phần tử):

```ui-json
{"type": "chart", "chart_type": "bar", "title": "So sánh chi tiêu Tháng 7 vs Tháng 8", "labels": ["Mua sắm", "Ăn uống", "Di chuyển", "Hoá đơn", "Giải trí", "Khác"], "series": [{"name": "Tháng 7", "data": [5730000, 2400000, 7100000, 850000, 620000, 300000]}, {"name": "Tháng 8", "data": [16280000, 10500000, 4200000, 3800000, 2100000, 1200000]}]}
```

## Ví dụ SAI (server sẽ huỷ cả chart nếu chèn thế này)

```
# SAI — thiếu field "type"
{"chart_type": "pie", "labels": ["A"], "series": [{"name": "x", "data": [1]}]}

# SAI — nháy đơn (Python dict), không phải JSON
{'type': 'chart', 'chart_type': 'pie', 'labels': ['A'], 'series': [{'name': 'x', 'data': [1]}]}

# SAI — data.length (2) khác labels.length (3)
{"type": "chart", "chart_type": "bar", "labels": ["A", "B", "C"], "series": [{"name": "VND", "data": [1, 2]}]}

# SAI — data là string số
{"type": "chart", "series": [{"name": "VND", "data": ["5130000", "2870000"]}]}

# SAI — pie nhưng có 2 phần tử series
{"type": "chart", "chart_type": "pie", "series": [{"name": "a", "data": [1]}, {"name": "b", "data": [2]}]}
```

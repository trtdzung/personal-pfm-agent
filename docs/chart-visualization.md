# Visualize dữ liệu (chart) — hướng dẫn cho frontend

Tài liệu này mô tả cơ chế agent trả về biểu đồ cho một số câu hỏi mang tính
phân tích, và cách frontend render field `chart` mới trong response của
`POST /chat` (xem `docs/api.md` cho toàn bộ API, tài liệu này chỉ đi sâu vào
riêng phần chart).

## Cơ chế (tóm tắt)

- Agent có 1 "skill" nội bộ (`skills/project/data-visualization/`) dạy nó
  khi nào và làm sao chèn 1 khối JSON mô tả chart vào cuối câu trả lời dạng
  text. Đây **không phải** một chế độ trả lời riêng — agent tự quyết định
  có cần chart hay không dựa trên câu hỏi, đúng như agent tự quyết định độ
  dài câu trả lời.
- `server.py` tách khối JSON đó ra khỏi phần text trước khi trả về, nên
  frontend **không bao giờ** thấy JSON thô lẫn trong `answer` — chỉ cần đọc
  field `chart` riêng.
- Vì đây là quyết định của agent (không ép buộc), **đa số câu trả lời sẽ có
  `chart: null`** — chỉ những câu hỏi dạng phân tích/so sánh/breakdown mới
  có khả năng kèm chart. Frontend không nên giả định luôn có chart, và cũng
  không nên coi việc thiếu chart là lỗi.

## Response `POST /chat`

```json
{
  "answer": "Tháng này bạn chi nhiều nhất cho Mua sắm (16.280.000đ), tiếp theo là Ăn uống (10.500.000đ).",
  "thread_id": "CIF_0001",
  "chart": {
    "chart_type": "pie",
    "title": "Chi tiêu theo danh mục - Tháng 8/2026",
    "labels": ["Mua sắm", "Ăn uống", "Di chuyển", "Hoá đơn", "Giải trí", "Khác"],
    "series": [
      { "name": "VND", "data": [16280000, 10500000, 4200000, 3800000, 2100000, 1200000] }
    ]
  }
}
```

Khi câu hỏi không cần chart, `chart` đơn giản là `null`:

```json
{ "answer": "Tháng này bạn đã chi tiêu 4.250.000 VND.", "thread_id": "CIF_0001", "chart": null }
```

## Schema của `chart`

| Field | Kiểu | Ghi chú |
|---|---|---|
| `chart_type` | `"bar"` \| `"line"` \| `"pie"` | Loại biểu đồ |
| `title` | string | Tiêu đề ngắn |
| `labels` | string[] | Trục X (`bar`/`line`) hoặc tên từng lát (`pie`) |
| `series` | `{ name: string, data: number[] }[]` | Mỗi phần tử là 1 đường (`line`)/1 nhóm cột (`bar`); `pie` chỉ có đúng 1 phần tử. `data.length` luôn khớp `labels.length` |

Field này cố tình đặt tên giống hệt vocabulary của Chart.js/Recharts — mục
đích để việc map sang thư viện chart gần như không cần biến đổi gì thêm.

**Lưu ý về độ tin cậy:** `chart` là kết quả do model tự sinh ra (không có
validate/enforce bằng structured output ở tầng framework), nên **frontend
nên coi đây là dữ liệu "khá tin cậy nhưng không tuyệt đối"**:
- Luôn kiểm tra `chart` khác `null` trước khi render.
- Nên bọc việc render trong try/catch hoặc kiểm tra field tồn tại/đúng kiểu
  trước khi đưa vào thư viện chart, phòng trường hợp hiếm model trả thiếu
  field. Nếu dữ liệu không hợp lệ để vẽ, im lặng bỏ qua chart và chỉ hiện
  `answer` — không nên hiện lỗi cho khách hàng vì đây không phải lỗi hệ
  thống, chỉ là không có/không vẽ được chart.
- Không cần validate JSON hợp lệ — nếu model trả JSON sai định dạng,
  `server.py` đã tự phát hiện và trả `chart: null` (không bao giờ để lọt
  JSON hỏng ra ngoài).

## Ví dụ render bằng Chart.js

```js
function renderChart(canvasEl, chart) {
  if (!chart) return; // không có chart cho câu trả lời này

  const typeMap = { bar: "bar", line: "line", pie: "pie" };

  new Chart(canvasEl, {
    type: typeMap[chart.chart_type] ?? "bar",
    data: {
      labels: chart.labels,
      datasets: chart.series.map((s) => ({
        label: s.name,
        data: s.data,
      })),
    },
    options: {
      responsive: true,
      plugins: { title: { display: true, text: chart.title } },
    },
  });
}
```

## Luồng UI gợi ý

1. Nhận response `/chat` như bình thường, hiện `answer` trong bong bóng
   chat (giống hiện tại, không đổi gì).
2. Nếu `chart !== null`, hiện thêm 1 chart ngay dưới bong bóng chat đó
   (không thay thế `answer` — 2 phần bổ sung cho nhau, `answer` đã được
   agent viết ngắn gọn với giả định là có chart đi kèm).
3. `GET /chat/history` **không** trả field `chart`, kể cả với các tin nhắn
   cũ từng có chart lúc mới trả về (`server.py` chỉ lọc bỏ khối chart-json
   thô khỏi text lịch sử, không lưu lại chart để trả lại). Khi hiện lại
   lịch sử cũ, chỉ hiện text, không có chart đi kèm — đây là giới hạn hiện
   tại, không phải lỗi.

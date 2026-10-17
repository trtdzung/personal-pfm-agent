# Visualize dữ liệu (chart) — hướng dẫn cho frontend

Tài liệu này mô tả cơ chế agent trả về biểu đồ cho một số câu hỏi mang tính
phân tích, và cách frontend render field `ui` trong response của
`POST /chat` (xem `docs/api.md` cho toàn bộ API, tài liệu này chỉ đi sâu vào
riêng phần chart).

**⚠️ Breaking change (2026-09-03):** field trước đây tên `chart`
(`chart: dict | null`) đã đổi thành **`ui`** (`ui: dict | null`) — 1
envelope chung cho mọi loại UI có cấu trúc agent có thể trả ra, phân biệt
bằng field `ui.type` bên trong (hiện `"chart"` là loại duy nhất; các loại
sau như form chuyển tiền/đặt ngân sách sẽ dùng cùng envelope này, chỉ khác
`type` — xem `todo.md` mục "Roadmap PFM"). **Nếu frontend đã tích hợp theo
field `chart` cũ, cần đổi sang đọc `ui` + kiểm tra `ui.type === "chart"`
trước khi đọc các field còn lại** — các field bên trong (`chart_type`,
`title`, `labels`, `series`) không đổi.

## Cơ chế (tóm tắt)

- Agent có 1 "skill" nội bộ (`skills/project/data-visualization/`) dạy nó
  khi nào và làm sao chèn 1 khối JSON mô tả chart vào cuối câu trả lời dạng
  text. Đây **không phải** một chế độ trả lời riêng — agent tự quyết định
  có cần chart hay không dựa trên câu hỏi, đúng như agent tự quyết định độ
  dài câu trả lời.
- `server.py` tách khối JSON đó ra khỏi phần text trước khi trả về, nên
  frontend **không bao giờ** thấy JSON thô lẫn trong `answer` — chỉ cần đọc
  field `ui` riêng.
- Vì đây là quyết định của agent (không ép buộc), **đa số câu trả lời sẽ có
  `ui: null`** — chỉ những câu hỏi dạng phân tích/so sánh/breakdown mới có
  khả năng kèm chart. Frontend không nên giả định luôn có `ui`, và cũng
  không nên coi việc thiếu `ui` là lỗi.

## Response `POST /chat`

```json
{
  "answer": "Tháng này bạn chi nhiều nhất cho Mua sắm (16.280.000đ), tiếp theo là Ăn uống (10.500.000đ).",
  "thread_id": "CIF_0001",
  "ui": {
    "type": "chart",
    "chart_type": "pie",
    "title": "Chi tiêu theo danh mục - Tháng 8/2026",
    "labels": ["Mua sắm", "Ăn uống", "Di chuyển", "Hoá đơn", "Giải trí", "Khác"],
    "series": [
      { "name": "VND", "data": [16280000, 10500000, 4200000, 3800000, 2100000, 1200000] }
    ]
  }
}
```

Khi câu hỏi không cần chart, `ui` đơn giản là `null`:

```json
{ "answer": "Tháng này bạn đã chi tiêu 4.250.000 VND.", "thread_id": "CIF_0001", "ui": null }
```

## Schema của `ui` (khi `type === "chart"`)

| Field | Kiểu | Ghi chú |
|---|---|---|
| `type` | `"chart"` | Discriminator — luôn kiểm tra field này trước khi đọc các field còn lại |
| `chart_type` | `"bar"` \| `"line"` \| `"pie"` | Loại biểu đồ |
| `title` | string | Tiêu đề ngắn |
| `labels` | string[] | Trục X (`bar`/`line`) hoặc tên từng lát (`pie`) |
| `series` | `{ name: string, data: number[] }[]` | Mỗi phần tử là 1 đường (`line`)/1 nhóm cột (`bar`); `pie` chỉ có đúng 1 phần tử. `data.length` luôn khớp `labels.length` |

Các field ngoài `type` cố tình đặt tên giống hệt vocabulary của
Chart.js/Recharts — mục đích để việc map sang thư viện chart gần như không
cần biến đổi gì thêm.

**Lưu ý về độ tin cậy:** `ui` là kết quả do model tự sinh ra (không có
validate/enforce bằng structured output ở tầng framework), nên **frontend
nên coi đây là dữ liệu "khá tin cậy nhưng không tuyệt đối"**:
- Luôn kiểm tra `ui` khác `null` **và** `ui.type === "chart"` trước khi
  render (bỏ qua `type` lạ/chưa hỗ trợ thay vì báo lỗi — tương lai sẽ có
  thêm `type` khác).
- Nên bọc việc render trong try/catch hoặc kiểm tra field tồn tại/đúng kiểu
  trước khi đưa vào thư viện chart, phòng trường hợp hiếm model trả thiếu
  field. Nếu dữ liệu không hợp lệ để vẽ, im lặng bỏ qua và chỉ hiện
  `answer` — không nên hiện lỗi cho khách hàng vì đây không phải lỗi hệ
  thống, chỉ là không có/không vẽ được chart.
- Không cần validate JSON hợp lệ — nếu model trả JSON sai định dạng,
  `server.py` đã tự phát hiện và trả `ui: null` (không bao giờ để lọt
  JSON hỏng ra ngoài).

## Ví dụ render bằng Chart.js

```js
function renderUi(canvasEl, ui) {
  if (!ui || ui.type !== "chart") return; // không có chart (hoặc type chưa hỗ trợ) cho câu trả lời này

  const typeMap = { bar: "bar", line: "line", pie: "pie" };

  new Chart(canvasEl, {
    type: typeMap[ui.chart_type] ?? "bar",
    data: {
      labels: ui.labels,
      datasets: ui.series.map((s) => ({
        label: s.name,
        data: s.data,
      })),
    },
    options: {
      responsive: true,
      plugins: { title: { display: true, text: ui.title } },
    },
  });
}
```

## Luồng UI gợi ý

1. Nhận response `/chat` như bình thường, hiện `answer` trong bong bóng
   chat (giống hiện tại, không đổi gì).
2. Nếu `ui !== null && ui.type === "chart"`, hiện thêm 1 chart ngay dưới
   bong bóng chat đó (không thay thế `answer` — 2 phần bổ sung cho nhau,
   `answer` đã được agent viết ngắn gọn với giả định là có chart đi kèm).
3. **⚠️ Đổi từ 2026-09-07:** `GET /chat/history` **giờ CÓ trả field `ui`**
   cho từng message (trước đây không trả — đã đảo ngược quyết định cũ).
   Mỗi message trong `messages[]` có thêm `ui: dict | null`, tính lại từ
   nội dung gốc lưu trong GreenNode Memory (bản gốc vẫn còn nguyên khối
   `ui-json`, chỉ bị lọc khỏi phần `content` hiển thị) — nên tin nhắn cũ
   từng có chart lúc mới trả lời **sẽ hiện lại đúng chart đó** khi mở lại
   lịch sử, không chỉ còn text như trước.

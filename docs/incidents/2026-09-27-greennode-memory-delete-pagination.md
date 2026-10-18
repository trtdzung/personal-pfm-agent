# [Correctness + Perf] `AgentBaseMemoryEvents.delete_thread()` xoá thiếu khi >100 event, và xoá rất chậm

- **Ngày phát hiện:** 2026-09-27
- **Mức độ ảnh hưởng:** Nghiêm trọng cho phần đúng/sai (xoá "thành công"
  nhưng còn sót dữ liệu), trung bình cho tốc độ (khách phải chờ lâu khi
  gọi `DELETE /chat/history`).
- **Package liên quan:** `greennode-agent-bridge[langgraph]==1.0.5`,
  class `AgentBaseEventClient` (`greennode_agent_bridge.langgraph.memory.helpers`)
- **Bối cảnh:** phát hiện khi khôi phục `AgentBaseMemoryEvents` làm
  checkpointer thật, thử xoá lịch sử 1 khách hàng thật (thread đã tích luỹ
  nhiều lượt chat qua nhiều tuần).
- **Đã fix bằng workaround trong repo này** — xem mục "Cách đang giải quyết".

## Phần 1 — Xoá thiếu khi thread có hơn 1 trang (100) event

### Tóm tắt

Gọi `DELETE /chat/history` cho 1 thread có ~1.700 event tích luỹ qua nhiều
tuần → server trả `200 {"status": "deleted"}`, nhưng `GET /chat/history`
đọc lại vẫn còn nguyên lịch sử cũ. Với thread nhỏ hơn (~300 event, tạo bởi
vài chục lượt chat thật trong 1 phiên), sau khi "xoá thành công" vẫn còn
sót đúng 2 tin nhắn.

### Cơ chế

```python
def delete_events(self, session_id, actor_id):
    page = 1
    size = 100
    while True:
        response = list_events(..., page=page, size=size)
        events_list = response.list_data or []
        if not events_list:
            break
        for event in events_list:
            delete_event(...)
        if page >= (response.total_page or 1):
            break
        page += 1
```

Xoá hết `size` (100) phần tử của `page` làm mọi thứ vốn nằm ở `page + 1`
dồn lên thành `page` (phân trang kiểu offset co lại từ đầu khi phần tử bị
xoá). Vòng lặp lại tăng `page` lên `page + 1` ngay sau đó — bỏ lỡ đúng
những phần tử vừa dồn lên trang đã xử lý xong. Với thread 1.700+ event
(17+ trang), phần lớn các trang từ thứ 2 trở đi mất một phần dữ liệu theo
kiểu này — càng nhiều trang, tỉ lệ sót càng cao.

### Bằng chứng

Xoá thủ công thread ~1.700 event bằng vòng lặp **luôn đọc lại đúng
`page=1`** (không tăng trang) sau mỗi lượt xoá 100 phần tử — tìm thêm được
**1.575 event còn sót** dù `delete_thread()` vừa báo thành công trước đó.

### Cách đang giải quyết

`checkpointer_delete_pagination.py` — ghi đè `AgentBaseEventClient.delete_events()`:
luôn đọc lại `page=1` sau mỗi lượt xoá, không bao giờ tăng số trang. Vòng
lặp chỉ dừng khi `list_events` thật sự trả về rỗng.

**Test hồi quy:** `tests/test_checkpointer_delete_pagination.py` —
`_FakeMemoryClient` mô phỏng đúng kiểu phân trang offset thật (xoá phần tử
làm các phần tử sau dồn lên); test tái hiện đúng bug với logic gốc (giữ
độc lập, không phụ thuộc trạng thái đã vá của class thật), test xác nhận
bản vá xoá sạch qua nhiều trang, xử lý đúng thread rỗng và thread đúng 1
trang.

**Verify lại bằng dữ liệu thật:** thread 415 event (8 lượt chat thật) và
thread 414 event ở lần thử khác — cả 2 lần `DELETE` đều xoá sạch **0 event
còn lại**, `GET /chat/history` sau đó trả đúng 0 tin nhắn.

## Phần 2 — Xoá đúng rồi, nhưng chậm: mỗi event 1 lệnh HTTP riêng

### Tóm tắt

Sau khi sửa xong phần 1 (xoá đúng), đo thời gian thật: xoá 1 thread chỉ 8
lượt chat (~415 event) mất **85 giây**. Nguyên nhân: cả code gốc lẫn bản
vá phần 1 đều gọi `memory_client.delete_event(...)` **tuần tự, từng cái
một** — không có API xoá hàng loạt nào để dùng.

### Đã kiểm tra tài liệu GreenNode trước khi tự làm thêm gì

Đọc kỹ `docs/agent-base/reference.md` (bảng API đầy đủ) và
`docs/agent-base/memory.md` của GreenNode:

- **Không có** endpoint xoá nhiều event 1 lần (`DELETE .../events` hàng
  loạt) hay xoá cả session 1 lần. Chỉ có `POST` tạo 1 event, `GET` liệt kê,
  và `DELETE /memories/{id}` xoá **cả memory store** (không phải theo
  session) — không dùng được cho việc này.
- **Không có** giới hạn tần suất (rate limit) nào được công bố cho Memory
  trong bảng "Giới hạn dịch vụ" (chỉ có giới hạn độ dài tên, thời hạn hết
  hạn event, tham số tìm kiếm ngữ nghĩa).

→ Xoá song song (gọi nhiều `delete_event` cùng lúc) là hướng duy nhất còn
lại để tăng tốc mà không cần đổi kiến trúc (không chạy nền, vẫn 1 request
đồng bộ như khách yêu cầu) — vì tài liệu không cấm cũng không có API tốt
hơn.

### Cách đang giải quyết

Cùng file `checkpointer_delete_pagination.py`: xoá từng trang qua 1 thread
pool (`ThreadPoolExecutor`, mặc định 10 luồng cùng lúc,
`DEFAULT_MAX_WORKERS`) thay vì vòng `for` tuần tự. Vẫn đúng 1 lệnh gọi
`DELETE /chat/history` đồng bộ từ phía người gọi — không phải job chạy
nền. `size=100` mỗi trang giới hạn số lệnh xoá tối đa cùng lúc, bất kể
`max_workers` là bao nhiêu. Mỗi lệnh xoá vẫn qua `retry_with_backoff` sẵn
có (trước đây chỉ áp dụng cho `list_events`, giờ áp dụng cả cho
`delete_event`) — là lớp đệm nếu chẳng may chạm giới hạn tần suất không
được công bố.

`max_workers` truyền vào `patch_delete_events_reads_page_one_every_time()`
có hiệu lực ngay cả khi gọi lại sau khi đã vá (đọc từ 1 biến toàn cục có
thể đổi được, không cần vá lại hàm) — tiện chỉnh nếu sau này thấy 10 luồng
chưa hợp lý.

**Test hồi quy:** 2 test mới dùng
`_ConcurrencyTrackingFakeMemoryClient` (đo số lệnh xoá đang chạy đồng thời
thật, không chỉ kiểm tra kết quả cuối) — xác nhận có chạy song song thật
(`max_in_flight > 1`) và tôn trọng đúng giới hạn `max_workers` truyền vào.

**Verify lại bằng dữ liệu thật:**

| | Trước (tuần tự) | Sau (song song, 10 luồng) |
|---|---|---|
| Thread ~415 event | 85.1s | 11.5s — 16.0s |

Xoá vẫn đúng 100% (0 event còn sót, `GET` sau đó trả 0 tin nhắn) ở cả 2 lần
đo lại sau khi thêm song song.

## Có cách nào tốt hơn không

1. **Tốt nhất — GreenNode cung cấp API xoá hàng loạt/theo session.** Ngoài
   khả năng sửa của repo này — cần đề xuất với GreenNode.
2. **Đã làm — xoá song song có giới hạn (repo này).** Cải thiện ~5-7 lần,
   vẫn tôn trọng "không có giới hạn tần suất công bố" bằng cách giữ mức
   vừa phải (10 luồng) thay vì tối đa hoá.
3. Nếu về sau xác nhận được giới hạn tần suất thật của GreenNode (qua thử
   nghiệm hoặc GreenNode công bố), có thể tăng `max_workers` cho phù hợp.

**Khuyến nghị:** báo GreenNode cả 2 phần (bug phân trang khi xoá, và đề
xuất thêm API xoá hàng loạt) kèm tài liệu này.

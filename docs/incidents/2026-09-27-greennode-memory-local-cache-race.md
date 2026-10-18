# [Correctness] `AgentBaseMemoryEvents.get_tuple()` có thể vứt bỏ cache đúng của chính mình, làm agent "quên" giữa chừng cuộc trò chuyện

- **Ngày phát hiện:** 2026-09-27
- **Mức độ ảnh hưởng:** Nghiêm trọng, ngẫu nhiên (race condition) — không
  theo quy luật thời gian, không báo lỗi gì (không `500`, không exception):
  agent trả lời như thể khách chưa từng nói gì trước đó trong cùng thread.
- **Package liên quan:** `greennode-agent-bridge[langgraph]==1.0.5`,
  class `AgentBaseMemoryEvents` (`greennode_agent_bridge.langgraph.memory.events`)
- **Bối cảnh:** phát hiện khi thử khôi phục lại `AgentBaseMemoryEvents` làm
  checkpointer thật cho `server.py` (checkpointer thật đã bị âm thầm đổi
  thành `MemorySaver()` — RAM, không bền — từ commit `46d99e2`, xem
  `todo.md` mục về việc khôi phục checkpointer).
- **Đã fix bằng workaround trong repo này** — xem mục "Cách đang giải quyết".

## Tóm tắt

Gửi 6 lượt chat thật liên tiếp (không nghỉ) trên cùng 1 thread, dùng model
đếm số tin nhắn nó thực sự nhận được:

```
turn 0: saw 2 total (human=1 ai=0)   ← đúng (lượt đầu)
turn 1: saw 2 total (human=1 ai=0)   ← SAI, phải là human=2
turn 2: saw 2 total (human=1 ai=0)   ← SAI
turn 3: saw 2 total (human=1 ai=0)   ← SAI
turn 4: saw 10 total (human=5 ai=4)  ← ĐÚNG!
turn 5: saw 2 total (human=1 ai=0)   ← lại SAI ngay sau khi vừa đúng
```

Không có tương quan với thời gian chờ giữa các lượt (đã thử cả không nghỉ
lẫn nghỉ 8 giây/lượt, kết quả vẫn ngẫu nhiên tương tự) — loại trừ giả
thuyết ban đầu "GreenNode Memory trễ 30-60 giây". Dữ liệu thô (event) luôn
đầy đủ và ổn định trong vòng ~1-2 giây sau khi ghi (đã đo trực tiếp,
xem bảng bên dưới) — vấn đề không nằm ở việc GreenNode ghi/đọc chậm, mà ở
cách thư viện **tự dựng lại** checkpoint từ các event đó.

## Cơ chế (đọc code `greennode_agent_bridge/langgraph/memory/events.py`)

`AgentBaseMemoryEvents` tự biết là đọc lại từ mạng ngay sau khi ghi có thể
chưa đầy đủ, nên nó tự giữ 1 cache cục bộ trong process (`self._local_cache`,
key theo `thread_id_actor_id`, TTL 30 giây) — đúng 100% với dữ liệu chính
process này vừa ghi, gọi là "read-your-writes". Vấn đề nằm ở cách
`get_tuple()` **chọn giữa 2 nguồn** (dữ liệu đọc từ mạng vs. cache cục bộ):

```python
events = self.checkpoint_event_client.get_events(...)      # đọc từ mạng
checkpoints, writes_by_checkpoint, channel_data = self.processor.process_events(events)

cached = self._get_cached(cache_key)
latest_fetch = max(checkpoints.keys()) if checkpoints else None
latest_local = max(cached[0].keys()) if cached and cached[0] else None

if latest_fetch is not None and (latest_local is None or latest_fetch >= latest_local):
    self._local_cache.pop(cache_key, None)          # tin dữ liệu đọc từ mạng, VỨT BỎ cache
elif cached is not None and latest_local is not None:
    checkpoints, writes_by_checkpoint, channel_data = cached  # dùng cache đúng
```

So sánh chỉ dựa vào **ID checkpoint mới nhất đọc được có ≥ ID mới nhất
trong cache không**. ID checkpoint là ULID — tăng đơn điệu theo thời gian
**bất kể** dữ liệu đọc về có đầy đủ hay không. Mỗi lượt chat của
`deepagents` tạo **12+ checkpoint riêng lẻ** (đo trực tiếp: 1 lượt = 12-15
checkpoint), và mỗi checkpoint lại kéo theo nhiều event con
(`ChannelDataEvent`, `WritesEvent`) ghi qua **các lệnh HTTP riêng biệt**
(`AgentBaseEventClient.store_blob_events_batch()` — tên có chữ "batch"
nhưng thực chất là vòng lặp gọi `create_event()` từng cái một, không phải
1 lệnh batch thật). Khi đọc lại rơi đúng vào lúc checkpoint mới nhất **đã**
liệt kê được nhưng 1 trong các event con của chính nó **chưa kịp** liệt kê
— `latest_fetch` vẫn trông "đủ mới" (thoả `>= latest_local`) nên code vứt
bỏ cache đúng, dùng dữ liệu đọc về đang thiếu đúng phần khiến `DeltaChannel`
không thấy giá trị nào cho kênh `messages` ở checkpoint đó → agent tưởng
cuộc trò chuyện mới bắt đầu.

**Vì sao có lúc đúng có lúc sai, không theo quy luật:** phụ thuộc việc
event con nào trong 1 lượt bị "trễ" ở đúng lần đọc đó — hoàn toàn ngẫu
nhiên theo tình trạng mạng/service tại thời điểm gọi, không phải hàm số
của thời gian đã trôi qua.

## Bằng chứng đo trực tiếp (loại trừ giả thuyết "trễ theo thời gian")

Đo số event thô (`AgentBaseEventClient.get_events`, bỏ qua toàn bộ cache
của chính repo này lẫn của thư viện) mỗi giây sau 1 lượt chat thật:

```
t+0.1s: 46 event   ← đã thay đổi
t+1.3s: 53 event   ← đã thay đổi, ổn định từ đây
t+2.5s .. t+16.3s: vẫn 53 event, không đổi thêm
```

→ Dữ liệu thô đầy đủ và ổn định trong ~1-2 giây — không phải "trễ 30-60
giây" như giả thuyết ban đầu (giả thuyết đó tự nó sai vì lúc đo thiếu bước
gọi `checkpointer_cache.invalidate()` trước mỗi lần đọc, vô tình đo trúng
TTL 60 giây của cache riêng của repo này chứ không phải hành vi thật của
GreenNode). Sau khi đo đúng cách, hành vi thật là **race condition ngẫu
nhiên** như mô tả ở trên, không phải độ trễ cố định.

## Cách đang giải quyết (trong repo này)

`checkpointer_local_cache_race.py` — ghi đè `AgentBaseMemoryEvents.get_tuple()`:
thay vì **chọn 1 trong 2 nguồn**, **gộp cả 2** (union): checkpoint/write/
channel-data nào cache cục bộ đã có thì giữ nguyên, dữ liệu mới đọc được
từ mạng được cộng thêm vào (không đè lên). Cache cục bộ chỉ chứa dữ liệu
process này **đã tự xác nhận ghi thành công** nên gộp vào không bao giờ
làm sai, chỉ có thể làm đầy đủ hơn — khác hẳn cách chọn 1-trong-2 hiện tại,
có thể lùi từ đúng về thiếu.

Vì `server.py` chạy **1 process duy nhất** (`uvicorn server:app`, không có
`--workers`), cache cục bộ này gần như luôn đúng cho toàn bộ lưu lượng thật
của server — chỉ có nguy cơ (nhỏ hơn nhiều so với race trước khi vá) nếu
process vừa khởi động lại ngay sau khi có dữ liệu ghi từ trước đó.

**Phát hiện phụ trong lúc vá — `delete_thread()` không dọn cache cục bộ:**
làm cache "sống dai" hơn (đúng mục đích vá race condition) lại lộ ra 1 hệ
quả: `delete_thread()` chỉ xoá dữ liệu trên GreenNode Memory, không hề đụng
tới `_local_cache` — nên xoá xong đọc lại trong vòng 30 giây (TTL cache) có
thể vẫn thấy dữ liệu "sống lại" từ cache. Đã vá cùng lúc: `delete_thread()`
giờ xoá luôn cache của đúng thread đó.

**Test hồi quy:** `tests/test_checkpointer_local_cache_race.py` (7 test,
không cần mạng) — `_RacyFakeMemoryClient` mô phỏng đúng kiểu thiếu 1 event
con của checkpoint mới nhất; có test tái hiện đúng bug với code gốc
(`_original_buggy_get_tuple`, giữ độc lập với trạng thái đã vá của class
thật để không phụ thuộc thứ tự chạy test), test xác nhận bản vá gộp đúng,
test xác nhận vẫn nhận dữ liệu mới từ process khác (không "đóng băng" vĩnh
viễn ở cache cũ), test xoá cache khi `delete_thread()`, và 1 test
end-to-end qua `StateGraph` thật với đọc racy 1/3 lượt.

**Verify lại bằng dữ liệu thật:** 12 lượt chat liên tiếp không nghỉ, gọi
`invalidate()` trước mỗi lượt giống hệt `/chat` thật — cả 12 lượt đều đúng
tuyệt đối (trước khi vá: sai ở lượt 5/6 trong bài test tương tự).

## Có cách nào tốt hơn không

Xếp theo mức độ tốt dần, giống cấu trúc khuyến nghị ở
`2026-09-13-greennode-memory-checkpointer-perf.md`:

1. **Tốt nhất — GreenNode tự sửa `get_tuple()` ở tầng SDK**, ví dụ so sánh
   *đầy đủ* (số lượng checkpoint/event, không chỉ ID mới nhất) trước khi
   quyết định vứt cache, hoặc tự gộp như cách repo này đang làm. Ngoài khả
   năng sửa của repo này — cần báo GreenNode kèm bằng chứng ở tài liệu này.
2. **Đã làm — gộp cache ở tầng client (repo này).** Đây là mức đã triển
   khai, nằm hoàn toàn trong khả năng sửa của repo.
3. Nếu GreenNode xác nhận đây là hành vi đã biết và có giới hạn (ví dụ
   "race chỉ xảy ra trong X giây đầu sau ghi"), có thể thêm 1 lớp kiểm tra
   nhất quán tường minh hơn thay vì gộp mù — nhưng chưa có thông tin đó nên
   chưa làm.

**Khuyến nghị:** giữ bản vá gộp cache hiện tại; báo GreenNode kèm tài liệu
này (đặc biệt bảng đo `t+0.1s`/`t+1.3s` và ví dụ 6-lượt ở trên) để họ xác
nhận và sửa tận gốc phía SDK.

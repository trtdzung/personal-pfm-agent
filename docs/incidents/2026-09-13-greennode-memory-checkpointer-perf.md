# [Perf] `AgentBaseMemoryEvents.get_tuple()` gọi lặp O(số checkpoint) lần, mỗi lần fetch lại toàn bộ lịch sử

- **Ngày phát hiện:** 2026-09-13
- **Mức độ ảnh hưởng:** Nghiêm trọng, tăng dần theo thời gian — thread càng
  được dùng nhiều (càng nhiều lượt chat tích luỹ), request **mới** trên
  thread đó càng chậm, bất kể agent/model/skill có tối ưu đến đâu.
- **Package liên quan:** `greennode-agent-bridge[langgraph]==1.0.5`,
  class `AgentBaseMemoryEvents` (`greennode_agent_bridge.langgraph.memory.events`)
- **Đã fix bằng workaround trong repo này** — xem mục "Cách đang giải quyết".

## Tóm tắt

Trên 1 thread đã tích luỹ 110+ checkpoint (từ việc test nhiều trong 1
phiên làm việc dài), gọi `agent.get_state()` hoặc `agent.invoke()` khiến
LangGraph gọi `checkpointer.get_tuple()` **111 lần** cho **cùng 1 lần
request** — và mỗi lần gọi, `AgentBaseMemoryEvents.get_tuple()` lại tự
fetch **toàn bộ lịch sử event của thread đó qua network** rồi parse lại
từ đầu, dù dữ liệu không hề đổi giữa các lần gọi liên tiếp này. Kết quả:
1 câu "Xin chào" đơn giản mất tới ~65-70 giây, trong khi bản thân lời gọi
LLM chỉ mất 5-8 giây.

## Cơ chế checkpoint của LangGraph (bối cảnh cần hiểu trước)

LangGraph lưu trạng thái hội thoại dưới dạng chuỗi **checkpoint** — mỗi
checkpoint là 1 snapshot của "channel" (kênh dữ liệu, ví dụ kênh
`messages` chứa toàn bộ tin nhắn). Một số kênh (như `messages`) dùng
**reducer** — nghĩa là giá trị đầy đủ của kênh không nhất thiết nằm trọn
trong 1 checkpoint, mà được **cộng dồn (reduce)** từ nhiều "write" rải
rác qua các bước (step) trước đó của graph.

Khi cần biết trạng thái đầy đủ hiện tại (`get_state()`), LangGraph gọi
`checkpointer.get_tuple(config)` để lấy checkpoint mới nhất, rồi (khi
`apply_pending_writes=True`, mặc định khi không chỉ định `checkpoint_id`
cụ thể) **lần ngược qua `parent_config` của từng checkpoint trước đó** để
gom đủ mọi "pending writes" cần thiết nhằm reduce ra giá trị đầy đủ của
kênh `messages`. Với 1 graph nhiều node/middleware (như `deepagents` —
mỗi middleware `wrap_model_call`/tool-call có thể tạo thêm 1 checkpoint
riêng), số checkpoint cần lần ngược có thể khá lớn sau nhiều lượt chat.

**Đây là hành vi bình thường, không phải bug của LangGraph** — bản thân
LangGraph coi `checkpointer.get_tuple(config)` là 1 thao tác **rẻ, có
index** (tương đương 1 lần `SELECT ... WHERE checkpoint_id = ?` trong SQL,
hay 1 lần tra `dict[key]` trong bộ nhớ) — gọi nó nhiều lần trong 1 lần
`get_state()` được xem là chấp nhận được, MIỄN LÀ mỗi lần gọi thực sự rẻ.

## Khác gì so với cách LangChain/LangGraph tự triển khai checkpointer

Các checkpointer có sẵn của LangGraph (`InMemorySaver`, `SqliteSaver`,
`PostgresSaver`, ...) lưu mỗi checkpoint như **1 bản ghi độc lập, có thể
tra cứu trực tiếp bằng `checkpoint_id`** — ví dụ 1 dòng trong bảng SQL với
index trên `(thread_id, checkpoint_id)`, hoặc 1 key trong dict ở bộ nhớ.
`get_tuple(config)` với 1 `checkpoint_id` cụ thể chỉ cần **1 lần tra cứu
O(1)/O(log n)**, hoàn toàn độc lập với tổng số checkpoint đã tồn tại của
thread đó. Gọi 111 lần chỉ tốn 111 lần tra cứu rẻ — tổng vẫn nhanh.

`AgentBaseMemoryEvents` triển khai khác hẳn: nó dùng model
**event-sourcing qua REST API** (`GET /memory/memories/{id}/actors/{actor}/sessions/{session}/events`,
phân trang `page`/`size`) — **không có endpoint nào để lấy trực tiếp 1
checkpoint theo `checkpoint_id`**. Cách duy nhất để lấy BẤT KỲ checkpoint
nào (kể cả checkpoint mới nhất) là: fetch **toàn bộ** trang event của
thread đó, decode/deserialize từng event, nhóm lại thành danh sách
checkpoint (`processor.process_events()`), rồi mới chọn ra đúng cái cần.
Việc này **luôn tốn O(tổng số event) bất kể bạn cần checkpoint nào** —
khác hẳn giả định "tra cứu rẻ, O(1)" mà LangGraph đặt ra khi gọi
`get_tuple()` lặp lại nhiều lần.

## Vì sao lại chậm đến mức 111 lần × ~0.6s ≈ 65s

Có sẵn 1 cơ chế cache trong code (`_local_cache`, TTL 30s) nhưng **không
được dùng để bỏ qua bước fetch** — đọc kỹ source thấy `get_tuple()` luôn
gọi `self.checkpoint_event_client.get_events(...)` (fetch mới) **trước**,
cache chỉ được dùng sau đó để so sánh "checkpoint nào mới hơn" giữa cache
và dữ liệu vừa fetch — nghĩa là **cache tồn tại nhưng chưa từng có tác
dụng tránh network call nào cả**.

Đã verify trực tiếp (không suy đoán):

| Bước | Thời gian đo được |
|---|---|
| Fetch toàn bộ 460 event (5 trang, 1 lần duy nhất) | **0.95-1.16s** |
| `get_tuple()` gọi qua đúng cách LangGraph gọi (111 lần) | **64.43s** (~0.58s/lần × 111) |
| Quét thử 116 checkpoint xem cái nào tự chứa đủ `messages` | **0/116** — xác nhận đúng lý do LangGraph phải lần ngược nhiều checkpoint |

→ Network/GreenNode Memory tự nó **không chậm** (fetch 1 lần rất nhanh) —
vấn đề thuần tuý là gọi lặp lại việc fetch-toàn-bộ 111 lần một cách lãng
phí, thay vì tái sử dụng dữ liệu đã có.

## Cách đang giải quyết (trong repo này)

Thêm `checkpointer_cache.py` — bọc
`checkpointer.checkpoint_event_client.get_events` bằng 1 cache TTL rất
ngắn (**2 giây**, ngắn hơn nhiều so với TTL 30s có sẵn của GreenNode Memory
nên không tăng thêm rủi ro đọc dữ liệu cũ giữa các request thật khác
nhau), key theo `(session_id, actor_id, limit, max_results)`. Gắn vào
`server.py`'s `build_agent()` ngay sau khi tạo checkpointer thật — no-op
an toàn với `InMemorySaver` (test/notebook).

`agent = build_agent()` trong `server.py` là **1 singleton tạo 1 lần lúc
khởi động process**, dùng chung cho mọi request — nên cache này sống suốt
vòng đời container, dùng chung cho mọi khách hàng/thread (an toàn vì cache
key đã tách theo `session_id`/`actor_id`).

**Kết quả đo thật** (trên `CIF_0001` thật, 51 message tích luỹ, không xoá
gì):

| | Trước | Sau |
|---|---|---|
| `GET /chat/history` (`get_state`) | 65.92s | **0.97s** (~68 lần) |
| `POST /chat` (`invoke`) | ~70s | **6.17s** (~11 lần) |

## Có cách nào tốt hơn không

Cách hiện tại (TTL 2 giây cố định) là 1 lựa chọn **thực dụng nhưng chưa
phải tối ưu nhất**. Xếp theo mức độ tốt dần:

1. **Tốt nhất — GreenNode tự sửa ở tầng SDK.** Cách đúng đắn nhất là
   `AgentBaseMemoryEvents` cung cấp 1 cách tra cứu **có index thật** theo
   `checkpoint_id` (ví dụ 1 endpoint REST riêng
   `GET .../events/{event_id}` hoặc để `_local_cache` thực sự được dùng
   để bỏ qua fetch khi gọi lặp trong cùng 1 request) — khi đó không cần
   workaround gì ở phía client nữa. Đây là việc **ngoài khả năng sửa của
   repo này**, cần báo GreenNode.
2. **Tốt hơn cách hiện tại — cache theo phạm vi 1 request, không theo thời
   gian.** Thay vì TTL 2 giây "đoán" khoảng thời gian đủ dùng, có thể chủ
   động xoá cache của đúng `(thread_id, actor_id)` đó **ngay trước khi**
   mỗi request `/chat`/`/chat/history` bắt đầu xử lý, và để nó tự điền lại
   trong lúc request đó chạy. Cách này **loại bỏ hoàn toàn** rủi ro đọc dữ
   liệu cũ giữa 2 request thật khác nhau (kể cả 2 request đến rất gần
   nhau, dưới 2 giây) mà vẫn giữ nguyên toàn bộ lợi ích tăng tốc bên trong
   1 request — an toàn hơn TTL cố định về mặt lý thuyết, dù triển khai
   phức tạp hơn 1 chút (cần hook vào đầu mỗi request handler trong
   `server.py` thay vì chỉ set 1 lần lúc `build_agent()`).
3. **Giải quyết tận gốc độ dài lịch sử** — thay vì chỉ tăng tốc việc đọc
   lịch sử dài, giảm luôn số checkpoint tích luỹ bằng cách chuyển sang mô
   hình nhiều thread/phiên ngắn hạn thay vì 1 thread vĩnh viễn/khách hàng
   (xem `todo.md` mục 1.2) — dù GreenNode có sửa bug ở mục 1, thread càng
   dài vẫn luôn tốn nhiều tài nguyên hơn thread ngắn.

**Khuyến nghị:** làm ngay mục 2 (cache theo phạm vi request, không theo
thời gian) — đây là cải thiện an toàn hơn, nằm hoàn toàn trong khả năng
sửa của repo này, không cần chờ GreenNode. Đồng thời báo GreenNode về mục
1 để họ sửa tận gốc phía SDK.

## Cập nhật — đã triển khai mục 2 (cache theo phạm vi request)

`checkpointer_cache.py` viết lại: bỏ TTL cố định, thay bằng
`invalidate(checkpointer, session_id, actor_id)` — gọi rõ ràng ở đầu mỗi
handler (`POST /chat`, `GET /chat/history`, `DELETE /chat/history`) trong
`server.py`, xoá đúng cache entry của thread đó trước khi đọc/ghi, đảm bảo
lần fetch đầu tiên trong request luôn thật. Vẫn giữ TTL 60s làm lưới an
toàn (fallback) cho bất kỳ nơi nào lỡ quên gọi `invalidate()`. 74/74 test
pass (6 test mới cho module này).

Verify lại trên `CIF_0001` thật: `GET /chat/history` 1.19s (từ ~66s),
`POST /chat` 6.71s (từ ~70s) — vẫn giữ nguyên mức cải thiện, đúng dữ liệu.

### Phát hiện thêm (không phải do fix này gây ra) — độ trễ ghi→đọc của GreenNode Memory

Trong lúc verify, gọi `GET /chat/history` **ngay lập tức** (cùng tiến
trình, cách nhau <1s) sau 1 `POST /chat` vừa ghi xong cho thấy **tạm thời
thiếu đúng 2 tin nhắn vừa ghi** (đã `invalidate()` đúng, bỏ qua cache hoàn
toàn — nghĩa là bản thân GreenNode Memory trả về dữ liệu thiếu, không
phải do cache ở phía mình). Thử lại vài giây sau (tiến trình khác) thấy
đúng đủ dữ liệu, ổn định.

**Kết luận:** GreenNode Memory có độ trễ ghi→đọc (write-then-read lag)
ngắn — cùng bản chất với race condition 30 giây đã ghi nhận ở mục 1.5 cho
riêng `DELETE`, giờ xác nhận **cũng ảnh hưởng cả luồng ghi/đọc bình
thường**, không chỉ riêng xoá. Việc thêm cache theo phạm vi request không
gây ra vấn đề này — chỉ làm lộ rõ hơn (`invalidate()` ép fetch thật 100%
từ network, không còn khả năng vô tình "che" hiện tượng này bằng dữ liệu
cache cũ).

**Khuyến nghị cho frontend:** sau `POST /chat` thành công, hiển thị trực
tiếp `answer` từ response đó — **không gọi lại `GET /chat/history` ngay
sau** để refresh, vì có thể tạm thời thiếu tin nhắn vừa gửi. Chỉ dùng
`GET /chat/history` cho việc mở lại 1 cuộc hội thoại cũ (ví dụ mở lại app
sau khi đã đóng), không dùng để refresh ngay sau khi gửi tin nhắn.

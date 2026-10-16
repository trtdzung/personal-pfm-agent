# Câu hỏi mẫu & Câu trả lời mẫu — Trợ lý tài chính về Thẻ

Tài liệu này liệt kê các nhóm câu hỏi mà **agent trợ lý tài chính thẻ**
(Personal Card Agent) cần trả lời được, kèm câu trả lời mẫu minh hoạ giọng
văn, cấu trúc và mức độ chi tiết mong muốn. Số liệu trong các câu trả lời
mẫu bên dưới là **ví dụ minh hoạ**, không phải placeholder — khi triển
khai, agent phải thay bằng số liệu thật lấy từ tool/dữ liệu giao dịch.

**Phạm vi:** agent trong tài liệu này chỉ **cung cấp thông tin và tư vấn**.
Các hành động thay đổi trạng thái thẻ (mở thẻ, khoá thẻ, đặt lịch nhắc,
thiết lập cảnh báo...) thuộc một nhóm chức năng riêng (action), không nằm
trong phạm vi câu hỏi/trả lời ở đây.

---

## 1. Thống kê & tra cứu giao dịch

Câu hỏi tra cứu số liệu trực tiếp, không cần suy luận nhiều — ưu tiên độ
chính xác và trả lời ngắn gọn, có số liệu cụ thể.

**Q: Tháng này tôi đã chi tiêu bao nhiêu trên thẻ?**
> Tính đến hôm nay (29/8), bạn đã chi **12.450.000 VNĐ** trên thẻ MSB
> Visa Signature, qua 34 giao dịch. So với tháng 7 cùng kỳ, con số này
> tăng 8%.

**Q: Giao dịch lớn nhất tuần vừa rồi là gì?**
> Giao dịch lớn nhất là **3.200.000 VNĐ** tại Điện Máy Xanh ngày 25/8,
> thuộc nhóm Mua sắm - Điện tử.

**Q: Liệt kê các giao dịch trên 2 triệu trong tháng 7.**
> Bạn có 3 giao dịch trên 2.000.000 VNĐ trong tháng 7:
> | Ngày | Merchant | Số tiền | Danh mục |
> |---|---|---|---|
> | 05/7 | Vietnam Airlines | 2.850.000 | Di chuyển |
> | 14/7 | Điện Máy Xanh | 4.100.000 | Điện tử |
> | 22/7 | Lotte Mart | 2.200.000 | Mua sắm |

**Q: Tôi chi bao nhiêu cho ăn uống trong 3 tháng gần nhất?**
> Chi tiêu nhóm **Ăn uống**: T6: 3.100.000 VNĐ, T7: 3.450.000 VNĐ,
> T8: 2.900.000 VNĐ — trung bình 3.150.000 VNĐ/tháng, chiếm 26% tổng chi
> tiêu thẻ.

**Q: Tôi đã dùng bao nhiêu điểm thưởng / hoàn tiền tháng này?**
> Bạn tích luỹ **1.240 điểm** (~124.000 VNĐ) từ 18 giao dịch đủ điều
> kiện. Điểm sẽ hết hạn vào 31/12/2027.

---

## 2. Quản lý chi tiêu

> Lưu ý: hệ thống hiện **không có tính năng lưu ngân sách/hạn mức tự
> đặt**. Agent chỉ biết ngân sách của khách hàng nếu khách hàng đã từng
> nói ra trong hội thoại (lấy từ memory), và phải hỏi lại nếu chưa có
> thông tin này — không được tự giả định con số.

**Q: Tôi có đang chi tiêu vượt ngân sách tháng này không?**
> *Trường hợp đã biết ngân sách qua hội thoại trước đó:* Trước đó bạn có
> nói ngân sách tháng là 15.000.000 VNĐ. Hiện tại bạn đã chi 12.450.000
> VNĐ (83%), còn 2 ngày nữa hết tháng — với tốc độ này bạn nhiều khả năng
> sẽ không vượt ngân sách.
>
> *Trường hợp chưa biết ngân sách:* Mình chưa có thông tin ngân sách
> tháng của bạn — bạn cho mình biết con số để mình theo dõi giúp nhé? Còn
> hiện tại bạn đã chi 12.450.000 VNĐ tính đến hôm nay.

**Q: Số dư khả dụng trên thẻ tín dụng của tôi là bao nhiêu?**
> Hạn mức thẻ: 50.000.000 VNĐ. Dư nợ hiện tại: 18.700.000 VNĐ. Khả dụng
> còn lại: **31.300.000 VNĐ**.

**Q: Tôi nên trả tối thiểu bao nhiêu kỳ này để không bị tính lãi?**
> Để tránh phát sinh lãi, bạn cần thanh toán **đủ dư nợ cuối kỳ:
> 18.700.000 VNĐ** trước hạn 15/9. Nếu chỉ trả tối thiểu (5% ~ 935.000
> VNĐ), phần dư nợ còn lại sẽ bị tính lãi từ ngày sao kê với lãi suất
> 26,4%/năm.

---

## 3. Insight & phân tích hành vi chi tiêu

Câu hỏi cần agent tổng hợp, so sánh, phát hiện xu hướng — đây là phần thể
hiện giá trị "trợ lý thông minh" chứ không chỉ tra cứu.

**Q: Chi tiêu của tôi tháng này có gì bất thường không?**
> Có 2 điểm đáng chú ý:
> 1. Chi tiêu nhóm **Giải trí** tăng 45% so với trung bình 3 tháng, chủ
>    yếu do giao dịch Netflix + CGV ngày 18/8 (850.000 VNĐ).
> 2. Có 3 giao dịch nhỏ lặp lại (99.000 VNĐ) tại Spotify — có thể là phí
>    thuê bao bạn quên huỷ, kiểm tra lại nhé.

**Q: Danh mục nào đang "ngốn" tiền của tôi nhất?**
> Top 3 danh mục chi tiêu tháng này:
> 1. Ăn uống: 26% (3.150.000 VNĐ)
> 2. Mua sắm: 22% (2.740.000 VNĐ)
> 3. Di chuyển: 15% (1.870.000 VNĐ)
> Riêng Ăn uống đã tăng 12% so với tháng trước.

**Q: So sánh chi tiêu của tôi với 3 tháng trước.**
> Chi tiêu trung bình 3 tháng trước: 11.200.000 VNĐ/tháng. Tháng này:
> 12.450.000 VNĐ — tăng 11%. Nguyên nhân chính đến từ nhóm Giải trí
> (chiếm 60% mức tăng).

**Q: Tôi có đang trả lãi thẻ tín dụng không, và vì sao?**
> Có, kỳ sao kê tháng 7 bạn phát sinh lãi **145.000 VNĐ** do chỉ thanh
> toán 40% dư nợ trước hạn. Nếu thanh toán đủ 100% mỗi kỳ, bạn sẽ tránh
> hoàn toàn khoản lãi này (thẻ tín dụng có tối đa 45 ngày miễn lãi khi
> trả đủ).

**Q: Tôi có đang dùng thẻ hiệu quả để tối ưu hoàn tiền/điểm thưởng không?**
> Bạn dùng thẻ MSB Visa Signature chủ yếu cho Ăn uống (55% giao dịch),
> nhưng thẻ này có hoàn tiền cao nhất (5%) ở nhóm Siêu thị. Nếu chuyển
> chi tiêu ăn uống sang thẻ MSB mIzumi (hoàn 3% nhóm F&B), bạn có thể
> tăng thêm ~90.000 VNĐ hoàn tiền/tháng.

---

## 4. Tư vấn tài chính & chi tiêu

Câu hỏi mang tính tư vấn — agent cần thận trọng, nêu rõ căn cứ, tránh cam
kết chắc chắn về số liệu tương lai hoặc quyết định thay khách hàng.

**Q: Tôi nên dùng thẻ tín dụng hay ghi nợ cho khoản chi 5 triệu này?**
> Dùng thẻ tín dụng MSB Visa Signature bạn được hoàn 3% (~150.000 VNĐ)
> và có tối đa 45 ngày miễn lãi nếu trả đủ hạn. Dùng thẻ ghi nợ thì trừ
> tiền ngay, không có hoàn tiền cho nhóm này. Về chi phí, thẻ tín dụng
> lợi hơn **nếu bạn chắc chắn thanh toán đủ đúng hạn** — nếu không, phần
> lãi phát sinh (26,4%/năm) sẽ vượt xa 150.000 VNĐ hoàn tiền.

**Q: Tôi nên cắt giảm chi tiêu ở đâu để tiết kiệm hơn?**
> Ba khoản đang tăng nhanh nhất 3 tháng gần đây: Giải trí (+45%), Ăn
> uống ngoài (+12%), Mua sắm online (+9%). Riêng các giao dịch thuê bao
> lặp lại (Spotify, Netflix, ...) đang tốn khoảng 450.000 VNĐ/tháng —
> đây thường là khoản dễ cắt giảm nhất nếu bạn không dùng hết.

**Q: Với thu nhập 25 triệu/tháng, tôi nên chi tối đa bao nhiêu cho ăn
uống?**
> Theo nguyên tắc phân bổ phổ biến (50/30/20 — thiết yếu/mong muốn/tiết
> kiệm), nhóm ăn uống thường nên chiếm khoảng 10-15% thu nhập, tức
> 2.500.000 - 3.750.000 VNĐ/tháng. Hiện bạn đang chi 3.150.000 VNĐ/tháng
> cho nhóm này — nằm trong khoảng hợp lý. Đây là mức tham khảo chung,
> không thay thế kế hoạch tài chính cá nhân của bạn.

**Q: Làm sao để cải thiện điểm tín dụng của tôi?**
> Dựa trên hồ sơ hiện tại: tỉ lệ sử dụng hạn mức trung bình 37% (nên giữ
> dưới 30%), 2/12 kỳ thanh toán trễ hạn. Gợi ý:
> 1. Giữ tỉ lệ dùng hạn mức dưới 30% mỗi kỳ sao kê.
> 2. Thanh toán đủ, đúng hạn liên tục.
> 3. Tránh mở nhiều thẻ mới trong thời gian ngắn.

**Q: Phí thường niên thẻ này có đáng không so với lợi ích tôi nhận được?**
> Phí thường niên: 900.000 VNĐ/năm. Trong 12 tháng qua bạn nhận được
> 1.480.000 VNĐ hoàn tiền/điểm thưởng quy đổi. Chênh lệch ròng:
> **+580.000 VNĐ** — thẻ đang mang lại lợi ích ròng dương cho bạn.

**Q: Tôi sắp trễ hạn thanh toán, phải làm gì?**
> Kỳ sao kê hiện tại đến hạn **15/9**, dư nợ tối thiểu cần trả là
> 935.000 VNĐ. Nếu trễ hạn, bạn sẽ bị tính phí phạt trễ hạn (~150.000
> VNĐ hoặc 5% dư nợ, tuỳ mức nào cao hơn) và ảnh hưởng lịch sử tín dụng.
> Nếu có thể, nên thanh toán trước hạn 1-2 ngày để tránh trễ do xử lý
> giao dịch ngân hàng.

---

## 5. Thông tin thẻ & kỳ sao kê

Câu hỏi tra cứu thông tin thẻ tĩnh/định kỳ — cần chính xác tuyệt đối,
không suy diễn.

**Q: Ngày sao kê và ngày đến hạn thanh toán của thẻ tôi là khi nào?**
> Thẻ MSB Visa Signature: ngày chốt sao kê hàng tháng là **ngày 25**,
> hạn thanh toán là **ngày 15 tháng sau** (sau 20 ngày kể từ ngày chốt
> sao kê).

**Q: Hạn mức tín dụng hiện tại của tôi là bao nhiêu?**
> Hạn mức: **50.000.000 VNĐ**. Dư nợ hiện tại: 18.700.000 VNĐ. Đã dùng
> 37% hạn mức.

**Q: Thẻ của tôi có những ưu đãi/hoàn tiền gì?**
> Thẻ MSB Visa Signature hiện có ưu đãi: hoàn 5% cho Siêu thị, hoàn 3%
> cho Ăn uống, tối đa 300.000 VNĐ/tháng cho mỗi nhóm.

**Q: Sao kê tháng này của tôi đã có chưa?**
> Sao kê kỳ 26/7 – 25/8 đã có, tổng dư nợ **12.450.000 VNĐ**, hạn thanh
> toán 15/9.

---

## Nguyên tắc trả lời chung

- **Luôn dẫn số liệu cụ thể** lấy từ tool/dữ liệu thực tế — số liệu trong
  tài liệu này chỉ là ví dụ minh hoạ, không phải mẫu bịa để dùng thật.
- **Ngân sách/hạn mức tự đặt không có trong hệ thống** — chỉ dùng khi
  khách hàng đã nói trong hội thoại (memory); nếu chưa có, hỏi lại thay
  vì giả định.
- **Agent chỉ cung cấp thông tin & tư vấn**, không thực hiện hành động
  trên thẻ (mở thẻ, khoá thẻ, đặt cảnh báo...) — các hành động đó thuộc
  nhóm chức năng khác.
- **Tư vấn = gợi ý có căn cứ**, không khẳng định chắc chắn thay khách
  hàng ra quyết định tài chính.
- **Insight ưu tiên "vì sao" chứ không chỉ "cái gì"** — chỉ ra nguyên
  nhân/đóng góp chính, không chỉ liệt kê số liệu.
- Khi thiếu dữ liệu (tài khoản mới, chưa đủ lịch sử...), nói rõ giới hạn
  thay vì suy diễn.

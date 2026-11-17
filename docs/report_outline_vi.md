# Phân phối khóa lượng tử và mã hóa xác thực

## 1. Mở đầu

Mô tả cách Shor tác động đến trao đổi khóa dựa trên RSA và ECC, còn Grover thay đổi chi phí tìm khóa đối xứng theo mô hình truy vấn. JST-UD 7832 minh họa các thuật toán lượng tử cơ bản, gồm tìm kiếm Grover. JST-UD 8256 đặt thuật toán lượng tử vào bài toán phân tích thừa số phục vụ thảo luận RSA. Nối hai bối cảnh với bài toán phân phối khóa và nhu cầu xác thực kênh cổ điển. [JST-UD 7832](https://jst-ud.vn/jst-ud/article/view/7832) · [JST-UD 8256](https://jst-ud.vn/jst-ud/article/view/8256)

## 2. Tổng quan tài liệu

Dùng các mục BibTeX đã xác minh trong `docs/references.bib` cho BB84, E91, Cascade, chứng minh an toàn khóa hữu hạn, trạng thái mồi và các chuẩn AEAD. So sánh BB84 với E91 theo nguồn phát, thiết lập đo, dữ liệu kiểm tra và hạ tầng ổn định quang học.

Bảng sau nối từng tài liệu được nêu trong đặc tả với câu hỏi đối chiếu của báo cáo. Thông tin thư mục lấy từ bản công khai khớp nhan đề. Phần đối chiếu chi tiết theo trang cần xác nhận với các PDF của người dùng khi có trong `docs/papers/`.

| Tài liệu | Điểm đối chiếu trong báo cáo |
|---|---|
| BB84 mô phỏng kết hợp AES-256 | Theo dõi đường đi của khóa từ phiên BB84 qua dẫn xuất đến AEAD. Đối chiếu các ca kiểm tra toàn vẹn và loại dữ liệu với E10–E11. [Mozo](https://arxiv.org/abs/2511.02836) |
| AES-256 trước tấn công lượng tử | Kiểm tra giả định về entropy khóa và đơn vị chi phí. Liên hệ E15 với số truy vấn Grover, số cổng và độ sâu mạch. [Rao và cộng sự](https://www.ijarcs.info/index.php/Ijarcs/article/view/3025) |
| Giao thức E91 | Đối chiếu trạng thái rối, quy ước góc đo, cặp giữ khóa, cặp kiểm tra Bell và cách đặt ngưỡng với E7. [Ravipati và Vemuru](https://theaspd.com/index.php/ijes/article/download/8851/6401/18375) |
| Hệ thống bảo mật nhiều lớp dùng QKD | Xác định tầng nào sinh khóa, xác thực và bảo vệ nội dung. Đối chiếu cách đánh giá ảnh với kết quả khứ hồi và chống sửa bản mã ở E10–E11. [Sykot và cộng sự](https://www.sciencedirect.com/science/article/pii/S1110016825002339) |
| Tổng quan BB84/E91 lai | Dùng E8 làm mốc trước khi đánh giá phương án kết hợp. So sánh nhu cầu phần cứng, cách phối hợp hai giao thức, tốc độ khóa và ích lợi giám sát. [Thakur và cộng sự](https://link.springer.com/article/10.1007/s10791-025-09807-8) |

## 3. Cơ sở lý thuyết

Dẫn từ quy tắc Born và định lý không nhân bản đến sai số đo do chặn–phát lại. Trình bày sàng lọc BB84, tương quan CHSH của E91, ước lượng tham số, Cascade, xác minh và băm Toeplitz. Giải thích cách HKDF cấp khóa riêng cho từng cách dùng và cách AEAD xác thực metadata. Các công thức và mô-đun tương ứng nằm trong `docs/theory_vi.md`.

## 4. Thiết kế hệ thống và giám sát

Luồng xử lý gồm nguồn, kênh, detector, sàng lọc, lấy mẫu và tạo khóa. Kênh HMAC bảo vệ trao đổi công khai và theo dõi số thứ tự. Lớp giám sát dùng QBER, cận thống kê, tỷ lệ dò và CHSH trong E91. Mô tả các kiểm định ngưỡng, CI, SPRT, CUSUM và kiểm định chung, cùng phản ứng đổi khóa, dừng, thử lại và khóa hệ thống.

D1 cho thấy bản mã ứng dụng và thông điệp HMAC đi qua TCP loopback. Khi bật Eve, mô hình quang học làm đổi mẫu QBER, phiên dừng và lưu bằng chứng công khai. D2 gắn mã phiên và mã khóa vào QKDH, giải mã theo khối và chỉ công bố kết quả sau khi xác minh toàn bộ tệp.

## 5. Cài đặt và kiểm thử

NumPy chạy thí nghiệm quy mô lớn. Aer mô phỏng mạch BB84, E91 và Hadamard, đồng thời đối chiếu các điểm được chọn. BB84 dùng nguồn đơn photon ở các quét giao thức mặc định. E6 so sánh đường tiệm cận của xung yếu, xung yếu có mồi và nguồn cặp rối.

Mô tả seed con, cấu hình YAML, dữ liệu công khai và dữ liệu chỉ dùng trong bộ mô phỏng. Dẫn kiểm tra giải tích, kiểm tra thống kê, đối chiếu hai backend, kiểm tra khứ hồi, sửa khung, nonce và xác thực sai. Ghi nhận ngẫu nhiên hệ điều hành dành cho thông tin mật mã và thống kê đo thời gian của máy chạy.

## 6. Kết quả E1–E15 và thảo luận

<!-- experiment-results -->

## 7. Phân tích bảo mật và giới hạn

- Thí nghiệm mô hình hóa thiết bị và kênh. Số liệu QBER, CHSH và tốc độ khóa đến từ mô phỏng. D1 dùng mạng loopback để vận chuyển thông điệp, với kênh lượng tử mô phỏng trong tiến trình.
- Giả định nguồn đơn photon loại trừ PNS trong các quét cơ sở. Nguồn kết hợp yếu có thành phần đa photon. E6 chỉ đánh giá tiệm cận bằng trạng thái mồi và giả định đáp ứng detector. PNS và giao thức trạng thái mồi đầy đủ là công việc tiếp theo. [Ma và cộng sự](https://arxiv.org/abs/quant-ph/0503005)
- Công thức khóa hữu hạn giản lược cần thêm các giả thiết và ngân sách sai số để có chứng minh khả hợp cho tấn công tổng quát. Kiểm tra CHSH trong E91 phụ thuộc mô hình dò và chọn trùng phùng. [Tomamichel và cộng sự](https://arxiv.org/abs/1103.4130)
- Detector blinding, Trojan-horse và kênh kề thời gian chỉ được thảo luận. Thiết bị thực cần đánh giá nguồn, detector, quang học và triển khai mạng.
- Xác thực cổ điển cần khóa chia sẻ ban đầu. QKD mở rộng khóa, còn HMAC dựa trên giả định an toàn tính toán. E12 dùng hai liên kết để quan sát hậu quả khi bỏ xác thực.
- Seed mô phỏng có thể dự đoán. Khóa dẫn xuất từ mô phỏng có seed dự đoán được không an toàn trong thực tế. Ngẫu nhiên vật lý và quản lý khóa là các vấn đề riêng của triển khai.
- Tính toàn vẹn AEAD phụ thuộc nonce duy nhất theo khóa, giới hạn sử dụng và xử lý lỗi. Đo benchmark trên một máy chỉ phản ánh môi trường chạy đã ghi. Các giá trị SP 800-22 là chẩn đoán thống kê cho mẫu đã đo. [NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final) · [NIST SP 800-22](https://csrc.nist.gov/pubs/sp/800/22/r1/upd1/final)

## 8. Kết luận và hướng phát triển

Tổng hợp mức khớp với mô hình ở E1–E8, đánh đổi giữa độ trễ và xác suất phát hiện ở E13, yêu cầu xác thực từ E12 và tính toàn vẹn tệp ở E10–E11. Giải thích các trường hợp sai khác theo cỡ mẫu, nhiễu nền, lượng rò hiệu chỉnh và thiết lập thí nghiệm. Các hướng mở rộng gồm PNS và giao thức mồi đầy đủ, BB84/E91 lai, xác thực Wegman–Carter và kết hợp QKD với ML-KEM.

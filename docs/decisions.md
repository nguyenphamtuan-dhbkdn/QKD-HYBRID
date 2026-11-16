# Quyết định thiết kế

## M0

- Tệp YAML là tập hợp các giá trị ghi đè lên cấu hình mặc định ở mục 19 của đặc tả. Trình đọc kiểm tra tên trường, kiểu và miền giá trị. YAML dùng định dạng `chsh_z` ở mục 19 và `fixed_z`/`fixed_x` ở mục 18.
- Giá trị mặc định của `f_ec_ideal` là một, tương ứng với giới hạn Shannon. Trường này dành cho bước hiệu chỉnh lỗi.
- `SimRNG` tạo một `numpy.random.Generator` từ seed cấu hình cho mỗi lần chạy. `secure_random` lấy byte từ hệ điều hành qua `secrets.token_bytes`. Khóa dẫn xuất từ mô phỏng có seed dự đoán được không an toàn trong thực tế.
- Gói khai báo các phụ thuộc cần cho M0 và M1. Tệp khóa của uv cố định cả phụ thuộc gián tiếp. Makefile cung cấp các lệnh cài đặt và kiểm tra, còn CI gọi uv trực tiếp trên Linux và Windows.

## M1

- Các mặc định ở mục 19 được giữ trong `configs/default.yaml`, gồm hiệu suất dò lý tưởng và xác suất đếm tối bằng không. Cấu hình `bb84_noiseless.yaml` tắt cả sai số lệch trục. Cấu hình `bb84_eve_full.yaml` dùng cùng điều kiện lý tưởng và bật Eve trên mọi xung đến được vị trí chặn.
- Nguồn mặc định phát một photon mỗi xung. `source.kind: weak_coherent` yêu cầu khai báo `source.mu` cho phân phối Poisson. Kênh áp dụng suy hao nhị thức theo từng photon trước vị trí Eve, rồi Bob đo với nhiễu quang và hiệu suất detector đã cấu hình. Eve phát lại một photon cho mỗi xung có photon bị chặn.
- Các xác suất lật bit từ `bitflip`, `depol` và lệch trục được ghép như các lỗi độc lập. Khi có `misalignment_theta`, xác suất lệch trục lấy từ `sin²(theta)` thay cho `e_misalign`. Mô hình gán xác suất đo ra bit một bằng một nửa khi cơ sở đo khác cơ sở chuẩn bị.
- Mỗi cổng detector có một lần thử đếm tối độc lập và một lựa chọn nhánh detector đồng xác suất khi có đếm tối. Nếu cả hai nhánh cùng nhấp, Bob chọn bit đồng xác suất và tăng bộ đếm nhấp kép. Bit ở vị trí không phát hiện chỉ là giá trị đệm và được loại qua mặt nạ phát hiện.
- `AttackConfig` mặc định xác suất chặn bằng một khi chọn `ir` và bỏ trống `p`. Hai cách viết `fixed_Z` và `fixed_X` được chuẩn hóa về chữ thường. Với Eve cố định cơ sở Z, xác suất sai trên bit đã sàng lọc là `p/2 × (1-p_z)² / (p_z² + (1-p_z)²)` trong điều kiện lý tưởng. Eve cố định cơ sở X cho công thức tương ứng với tử số `p_z²`. Với cơ sở Alice và Bob đồng xác suất, cả hai trường hợp cho QBER `p/4`.
- `simulate_bb84` nằm ngoài gói giao thức và trả riêng quan sát Alice–Bob và `GroundTruth`. Các hàm giao thức chỉ nhận hoặc trả dữ liệu cần cho chuẩn bị và đo xung. CLI xuất số liệu tổng hợp. Kiểm thử dùng cây cú pháp để bảo vệ ranh giới import của gói giao thức.
- Ước lượng QBER lấy mẫu đều, không hoàn lại, với cỡ mẫu làm tròn lên theo giá trị thập phân trong cấu hình. Khi thiếu mẫu, phiên dừng trước khi lấy mẫu. Khi đủ mẫu, cận trên Hoeffding được chặn ở một và phiên dừng nếu cận vượt ngưỡng. Phiên được chấp nhận chuyển tiếp các bit chưa công khai theo thứ tự ban đầu. Phân tích khóa hữu hạn đầy đủ dùng các cận lấy mẫu không hoàn lại như cận Serfling. [Tomamichel và cộng sự, Tight Finite-Key Analysis for Quantum Cryptography](https://arxiv.org/abs/1103.4130)
- Khoảng tin cậy hai phía Clopper–Pearson và Wilson dùng mức tin cậy mặc định 95%. Kiểm thử thống kê dùng seed cố định và dung sai bốn độ lệch chuẩn nhị thức tính theo số bit thực sự được so sánh hoặc số xung được phát hiện. Kiểm thử nguồn Poisson dùng độ lệch chuẩn của trung bình mẫu.
- Hàm bootstrap lấy khoảng phân vị của các trung bình tái lấy mẫu. Hàm Monte Carlo dùng `SeedSequence.spawn` để cấp một bộ sinh riêng cho mỗi lần chạy và ước lượng khoảng tin cậy của trung bình bằng phân phối Student.
- CLI chạy đến hết ước lượng tham số. Trạng thái `accepted` nghĩa là phiên vượt qua ngưỡng QBER. Trạng thái `abort` được ghi trong cùng định dạng JSON để chương trình gọi đọc được số liệu. Kiểm tra QBER ở đây phục vụ mô phỏng giáo dục với các giả định lý tưởng hóa.

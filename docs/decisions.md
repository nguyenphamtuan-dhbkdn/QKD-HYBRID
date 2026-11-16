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

## M2

- Backend Qiskit Aer chạy một lượt đo trên một mạch Clifford chứa các qubit
  cần đo trong cả phiên. Mỗi photon được ghi nhận dùng một qubit. Nếu Eve
  chặn xung, phép đo giữa mạch chiếu qubit vào trạng thái mà Eve phát lại.
  Mạch giữ kết quả đo của Eve kể cả khi Bob bỏ lỡ photon. Bộ điều phối trả
  dữ liệu của Eve riêng khỏi quan sát của Alice và Bob.
- Suy hao sợi quang, số photon đăng ký tại detector và đếm tối dùng mô hình
  lấy mẫu của backend NumPy. Seed của Aer được lấy từ cùng bộ sinh NumPy của
  phiên. Khi có nhiễu quang, `NoiseModel` gắn lỗi khử cực và lỗi Pauli Y lên
  cổng đồng nhất sau Eve và trước phép đo của Bob. Pauli Y mô phỏng cùng xác
  suất lật bit do lệch trục trong cả hai cơ sở và giữ phân phối đều khi cơ
  sở khác nhau. Mô hình này dùng xác suất sai của phép đo, với
  `misalignment_theta` ánh xạ qua `sin²(theta)`.
- Backend NumPy lấy mẫu trên các mảng có kích thước tăng tuyến tính theo số
  xung. Với Aer, số lệnh dựng mạch tăng tuyến tính theo số qubit, còn bộ nhớ
  của bảng stabilizer tăng theo bình phương số qubit. Thời gian của Aer cũng
  tăng nhanh hơn trong phép đo trên Windows với nhiễu khử cực. Dùng NumPy
  cho các lượt quét lớn và dùng Aer để đối chiếu ở quy mô nhỏ.
  Chạy `uv run python experiments/bb84_backend_scaling.py` để đo lại thời
  gian mô phỏng sau khi khởi động mỗi backend. Tệp kết quả ghi từng lượt đo,
  trung vị, cấu hình, seed, phiên bản thư viện và trạng thái Git.
  [Kết quả đo](../results/bb84_backend_scaling.json)

## M3

- Cascade dùng các hoán vị từ bộ sinh của phiên. Mỗi lần sửa bit cập nhật
  chẵn lẻ của mọi khối đã mở chứa bit đó, ưu tiên xử lý khối thuộc lượt sớm
  hơn. Mỗi khối mới và mỗi bước chia đôi tính một bit công khai của Alice.
  Khi quay lại một khối đã mở, hai bên dùng thông tin chẵn lẻ đã có. Mặc
  định chạy bốn lượt, có thể chỉnh bằng `bb84.cascade_passes`. Nếu mẫu
  công khai có `Q_est = 0`, dùng mức nhiễu mặc định `0.01` để chọn kích
  thước khối và để trống `f_ec` vì mẫu số bằng không. Với `ec_mode: ideal`,
  mô phỏng đồng bộ khóa của Bob và làm tròn lên lượng rò rỉ ước tính.
- Một cặp lỗi có thể nằm trong cùng khối ở mọi lượt nên Cascade hữu hạn
  có thể còn lỗi. Kiểm tra khóa dùng một điểm đánh giá ngẫu nhiên từ hệ
  điều hành trong trường `GF(2**61 - 1)`. Thẻ công khai chiếm 64 bit.
  Xác suất trùng thẻ của hai khóa cùng độ dài được chặn bởi bậc đa thức
  chia cho kích thước trường. Phiên dừng nếu cận vượt `eps_cor` hoặc hai
  thẻ khác nhau.
- Công thức độ dài khóa dùng `eps_PA = eps_sec` và xử lý `eps_cor` ở
  bước xác minh. Với `Q_ub >= 0.5`, entropy bất lợi nhất là một bit. Đây
  là công thức khóa hữu hạn giản lược cho mô hình nguồn đơn photon lý
  tưởng. Khóa từ mô phỏng dùng seed dự đoán được không an toàn trong thực
  tế. [Shor và Preskill](https://arxiv.org/abs/quant-ph/0003004),
  [Tomamichel và cộng sự](https://arxiv.org/abs/1103.4130)
- `qkdsim.simulation.run_bb84_session` dùng chung chuỗi Toeplitz từ hệ điều
  hành cho hai bên. Bộ mô phỏng đối chiếu hai kết quả PA cục bộ rồi đóng
  gói khóa từ bit cao đến bit thấp, đệm bit không vào cuối byte và lưu độ
  dài thật trong `length_bits`. `leak_total` cộng lượng rò từ hiệu chỉnh
  lỗi và thẻ xác minh. Các bit mẫu đã bị loại khi ước lượng QBER. Dữ liệu
  Eve trong kết quả dành cho thí nghiệm và được đọc sau khi hai bên đã tạo
  khóa. Trao đổi cổ điển ở M3 giả định thông điệp được chuyển đúng trong
  mô phỏng nội bộ. CLI vẫn xuất thống kê đến bước ước lượng tham số.
- Chạy `uv run python experiments/bb84_postprocessing.py` để đo tỷ lệ
  đồng bộ và hiệu suất rò rỉ của Cascade theo QBER, sau đó kiểm tra thời
  gian FFT với đầu vào và đầu ra một triệu bit. Tệp JSON ghi số lần thử,
  cấu hình, seed, phiên bản thư viện, trạng thái Git và từng lượt đo FFT.
  Tỷ lệ đồng bộ là kết quả quan sát ở kích thước khóa trong cấu hình đo.
  [Kết quả đo](../results/bb84_postprocessing.json)

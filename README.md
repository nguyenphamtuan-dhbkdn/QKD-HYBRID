# QKD-HYBRID

Dự án mô phỏng phân phối khóa lượng tử BB84. Khóa dẫn xuất từ mô phỏng dùng seed cố định không an toàn để sử dụng trong thực tế.

## Cài đặt và kiểm tra

Cần Python và `uv`. Chạy tại thư mục gốc của dự án.

```powershell
uv sync --locked --extra dev
uv run qkdsim --help
uv run ruff check .
uv run mypy --strict src
uv run pytest
```

Trên Windows, nếu `uv` chưa có trong PATH, dùng `& 'C:\Users\Tuan\.local\bin\uv.exe'` thay cho `uv` trong các lệnh trên.

Cấu hình nằm trong `configs/`, mã nguồn trong `src/qkdsim/` và kiểm thử trong `tests/`. Các lựa chọn thiết kế được ghi trong [docs/decisions.md](docs/decisions.md).

## Chạy BB84

```powershell
uv run qkdsim bb84 --config configs/bb84_noiseless.yaml
uv run qkdsim bb84 --config configs/bb84_eve_full.yaml
uv run pytest -m statistical
```

Lệnh BB84 xuất JSON với số xung gửi, số lượt phát hiện, số bit sau sàng lọc và trạng thái ước lượng. Khi mẫu đủ lớn, đầu ra có QBER ước lượng, cận trên Hoeffding và khoảng tin cậy Clopper–Pearson và Wilson. Chạy lại cùng cấu hình, seed và phiên bản thư viện để tái lập đầu ra.

Để chạy với Qiskit Aer, trong mục `bb84` của tệp YAML, đặt `backend: qiskit`
và chọn `n_pulses` theo quy mô nhỏ dùng để đối chiếu. Cách đo thời gian và giới hạn quy mô
được ghi trong [quyết định thiết kế](docs/decisions.md#m2).

Để chạy đến bước tạo khóa, gọi API Python và chỉ in thông tin phiên.

```python
from qkdsim.config import SessionConfig
from qkdsim.simulation import FinalKey, run_bb84_session

result = run_bb84_session(SessionConfig())
if isinstance(result, FinalKey):
    print(result.key_id, result.length_bits)
else:
    print(result.reason)
```

Đo lại hiệu suất Cascade và Toeplitz FFT bằng lệnh sau.

```powershell
uv run python experiments/bb84_postprocessing.py
```

## Giám sát phiên BB84

```powershell
uv run qkdsim calibrate --config configs/default.yaml --output calibration.json
uv run qkdsim monitor --config configs/default.yaml --detector sprt --calibration calibration.json
uv run qkdsim monitor --config configs/bb84_eve_full.yaml --detector joint
```

Lệnh `monitor` ghi `events.jsonl` trong thư mục phiên và in đường dẫn
thư mục trong JSON. Nếu phiên dừng, thư mục còn có `evidence.json` và
biểu đồ `qber.png`. Dùng `--output` để chọn thư mục gốc.

## Thử nghiệm MITM trên kênh cổ điển

```powershell
uv run python experiments/e12_mitm_classical.py
```

Thử nghiệm E12 kiểm tra Eve có thiết lập được khóa riêng với từng bên
trong hai chế độ xác thực và ghi số liệu cùng cấu hình vào
[`results/e12_mitm.json`](results/e12_mitm.json).

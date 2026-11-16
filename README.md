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

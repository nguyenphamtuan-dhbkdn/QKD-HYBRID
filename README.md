# QKD-HYBRID

Mô phỏng BB84 và E91, theo dõi dấu hiệu nghe lén, rồi dùng khóa cuối với AES-256-GCM hoặc ChaCha20-Poly1305. **Khóa dẫn xuất từ mô phỏng có seed dự đoán được không an toàn trong thực tế.** Các kết quả là đầu ra của mô hình.

## Cài đặt và chạy nhanh

Cần Git, Python 3.11 trở lên và `uv`. Từ thư mục gốc của bản sao Git, chạy:

```powershell
uv sync --locked --extra dev
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy --strict src experiments demos
uv run --locked --extra dev pytest
uv run --locked --extra dev python experiments/run_all.py --quick
uv run --locked --extra dev python demos/secure_chat.py --self-test
uv run --locked --extra dev python demos/file_encrypt_demo.py self-test
```

Nếu PowerShell chưa tìm thấy `uv`, thêm thư mục chứa `uv.exe` vào `PATH` của phiên. Ví dụ nếu đã cài bằng trình cài đặt mặc định:

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
```

Với GNU Make, dùng `make setup test experiments demo`. Trên Windows dùng `mingw32-make` khi đó là tên lệnh đã cài.

## Tái lập E1–E15

[Chỉ mục chạy nhanh](results/quick/run_all.json) ghi thời gian đo cho từng thí nghiệm và toàn bộ lượt chạy. [Báo cáo sinh tự động](results/quick/report_vi.md) nhúng hình và liên kết tới CSV, PDF cùng hồ sơ nguồn gốc. Mỗi biểu đồ được đọc từ CSV công bố. JSON đi kèm ghi cấu hình, seed, commit Git, trạng thái cây mã nguồn, phiên bản thư viện và SHA-256 của CSV. PNG xuất ở 300 dpi, PDF ở dạng vector. Tỷ lệ nhị thức dùng khoảng Clopper–Pearson 95%, trung bình dùng khoảng Student 95%, và E9 dùng trung vị cùng khoảng tứ phân vị.

Chạy toàn bộ suite để chèn lại hình và các bảng E8, E15 vào dàn ý. `--only` ghi các thí nghiệm được chọn cùng chỉ mục và báo cáo vào `results/selected/quick/` hoặc `results/selected/full/`. Dùng `--output` để chỉ định thư mục đích.

```powershell
uv run python experiments/run_all.py --quick --only 1 7 --language en --output results/check
uv run qkdsim experiment E3 --quick
uv run qkdsim experiments --all --quick
uv run python experiments/run_all.py
```

Chế độ nhanh giữ cả E1–E15, giảm số lần lặp và giới hạn kích thước E9. Lượt chạy Windows được lưu trong chỉ mục và nằm dưới 15 phút. Chế độ đầy đủ ghi vào `results/full/`, giữ lưới tham số và dùng số lần lặp đầy đủ trong từng YAML. E9 mặc định chạy đến 256 MiB cho mỗi tệp và có thể chi phối thời gian do I/O. E4 chạy Cascade đến một triệu xung, E13 tăng số lượt nền để ước lượng báo động nhầm. Thời gian đầy đủ phụ thuộc cấu hình, CPU và ổ đĩa. Có thể chỉnh `cap_bytes` trong `configs/experiments/e09.yaml`. Bỏ `--quick` khi cần chạy đầy đủ một thí nghiệm hoặc dùng `make experiments EXPERIMENT_FLAGS=`.

Đầu ra thống kê mô phỏng phụ thuộc seed và phiên bản thư viện. Thời gian, nonce, mã phiên và các bước xác minh hoặc khuếch đại dùng ngẫu nhiên hệ điều hành. Một số kết quả như p-value của khóa cuối và nguồn `secrets` thay đổi giữa các lần chạy.

## Giám sát

```powershell
uv run qkdsim bb84 --config configs/bb84_eve_full.yaml
uv run qkdsim e91 --config configs/e91_default.yaml
uv run qkdsim calibrate --config configs/default.yaml --output calibration.json
uv run qkdsim monitor --config configs/default.yaml --detector sprt --calibration calibration.json
uv run qkdsim monitor --config configs/bb84_eve_full.yaml --detector joint
```

Lệnh `monitor` ghi `events.jsonl` trong thư mục riêng của phiên. Khi phiên dừng, thư mục có `evidence.json` và `qber.png`. Dùng `--output` để chọn thư mục gốc.

## D1 · Chat qua TCP cục bộ

```powershell
uv run python demos/secure_chat.py --cipher chacha20 --rekey-every 3 --eve
```

Nhập tin nhắn ở dấu nhắc `Alice>`. `--eve` bật chặn–phát lại khi khởi động. Thử gửi khi Eve đang bật để xem lý do dừng và đường dẫn báo cáo. Nhập `/eve off` rồi gửi lại để tạo khóa mới. `/eve on` bật lại cuộc tấn công, `/reset` mở khóa sau khi chính sách chặn nhiều lần, `/quit` thoát. Bản mã và các khung HMAC đi qua kết nối TCP tới `127.0.0.1`. Quá trình lượng tử và hai đầu cuối chạy cùng tiến trình. Số tin nhắn, tuổi khóa, số byte và cảnh báo đều có thể kích hoạt đổi khóa.

## D2 · Mã hóa tệp và khôi phục

```powershell
uv run qkdsim encrypt --in README.md --out message.qkdh --cipher chacha20
uv run qkdsim decrypt --in message.qkdh --out message.restored.md
Get-FileHash README.md,message.restored.md
```

Cả hai lệnh in mã phiên, mã khóa, QBER và số bit khóa. Có thể chọn `aes256gcm`. Khóa của Bob được lưu trong tệp cục bộ `message.qkdh.demo-key.json` để lệnh giải mã đọc được ở tiến trình khác. `--key-file` cho phép chỉ định đường dẫn khác. Tệp demo chứa vật liệu khóa ở dạng đọc được và cần giữ riêng với bản mã. Mỗi lần mã hóa tạo tệp khóa mới, dùng một tên đích mới khi chạy lại.

## Cấu trúc

- `configs/` chứa thiết lập phiên và YAML riêng cho từng thí nghiệm.
- `src/qkdsim/` chứa các bộ mô phỏng, hậu xử lý QKD, giám sát, xác thực và mã hóa.
- `experiments/` chứa thí nghiệm, hàm vẽ dùng chung và trình chạy.
- `demos/` và `tests/` chứa trình diễn và kiểm thử.
- `results/` chứa CSV, hồ sơ nguồn gốc, hình, báo cáo và nhật ký sinh từ mã.

[Cơ sở lý thuyết](docs/theory_vi.md) · [Dàn ý báo cáo](docs/report_outline_vi.md) · [Quyết định thiết kế](docs/decisions.md) · [BibTeX](docs/references.bib)

"""Replot retained measurements for the student report without rerunning trials.

Windows: uv run python experiments/report_summary.py
All coordinates come from retained CSV/JSON; no simulation or crypto RNG is used.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from _provenance import provenance
from matplotlib.axes import Axes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/report_summary"
Row = dict[str, str]


def sha(path: Path) -> str:
    """Return SHA-256 of public measurement file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Load all original rows and record their historical run metadata."""
    evidence: dict[str, Any] = {}
    sources = []
    for path in sorted((ROOT / "results/quick").glob("E??_*.csv")):
        metadata = path.with_suffix(".json")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        info = json.loads(metadata.read_text(encoding="utf-8-sig"))
        if info["csv_sha256"] != sha(path):
            raise ValueError(f"CSV differs from retained provenance: {path}")
        evidence[path.stem[:3]] = {"rows": rows, "metadata": info}
        for source in (path, metadata):
            sources.append(
                {"path": source.relative_to(ROOT).as_posix(), "sha256": sha(source)}
            )
    path = ROOT / "results/bb84_backend_scaling.json"
    evidence["backend"] = json.loads(path.read_text(encoding="utf-8-sig"))
    sources.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)})
    # These public logs establish session states, not delivery of message text.
    evidence["chat"] = {}
    for label, folder in (
        ("normal", "0fadfc66-4483-4bde-bc25-ba678d3d54dd"),
        ("eve", "0939ab2d-5612-4ca1-ae33-c20f8e02d5d0"),
    ):
        path = ROOT / "results/demo_chat" / folder / "events.jsonl"
        if path.exists():
            events = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            evidence["chat"][label] = events
            sources.append(
                {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
            )
    return evidence, sources


def rows(data: dict[str, Any], exp: str, metric: str, **filters: str) -> list[Row]:
    """Select measured rows, preserving the numeric x order of a sweep."""
    result: list[Row] = [
        r
        for r in data[exp]["rows"]
        if r["metric"] == metric and all(r.get(k) == v for k, v in filters.items())
    ]
    return sorted(result, key=lambda r: float(r["x"]))


def curve(
    ax: Axes,
    points: list[Row],
    label: str,
    *,
    scale_x: float = 1,
    scale_y: float = 1,
    style: str = "o-",
    intervals: bool = True,
) -> None:
    """Plot stored means and their original intervals with unit conversion."""
    xs = [float(r["x"]) * scale_x for r in points]
    ys = [float(r["value"]) * scale_y for r in points]
    if intervals and all(r.get("low") and r.get("high") for r in points):
        error = [
            [max(0, (float(r["value"]) - float(r["low"])) * scale_y) for r in points],
            [max(0, (float(r["high"]) - float(r["value"])) * scale_y) for r in points],
        ]
        ax.errorbar(xs, ys, yerr=error, fmt=style, label=label, capsize=3)
    else:
        ax.plot(xs, ys, style, label=label)


def save(name: str, fig: Any) -> None:
    """Save a readable figure; every plotted coordinate is retained evidence."""
    for ax in fig.axes:
        ax.grid(alpha=0.22)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", dpi=220)
    plt.close(fig)


def plots(data: dict[str, Any]) -> None:
    """Create compact report figures, keeping unlike metrics on separate axes."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, ax = plt.subplots(figsize=(8, 4.3))
    for noise in ("0", "0.02"):
        curve(
            ax,
            rows(data, "E01", "qber", backend="fast", noise=noise),
            f"Nhanh, nhiễu nền {float(noise):.0%}",
            scale_x=100,
            scale_y=100,
        )
        curve(
            ax,
            rows(data, "E01", "qber", backend="qiskit", noise=noise),
            f"Qiskit, nhiễu nền {float(noise):.0%}",
            scale_x=100,
            scale_y=100,
            style="s",
            intervals=True,
        )
    ax.set(xlabel="Tỷ lệ xung Eve chặn (%)", ylabel="QBER (%)")
    save("01_eve", fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for series in ("BB84 Qmax=0.08", "BB84 Qmax=0.11"):
        label = "Ngưỡng " + series.split("=")[-1]
        curve(
            axes[0],
            rows(data, "E02", "abort", series=series),
            label,
            scale_x=100,
            scale_y=100,
        )
        curve(
            axes[1],
            rows(data, "E02", "final_bits", series=series),
            label,
            scale_x=100,
            scale_y=0.001,
        )
    axes[0].set(xlabel="Nhiễu nền (%)", ylabel="Số phiên dừng (%)", ylim=(-5, 105))
    axes[1].set(xlabel="Nhiễu nền (%)", ylabel="Khóa cuối (nghìn bit)")
    save("02_noise", fig)

    fig, ax = plt.subplots(figsize=(8, 3.8))
    pts = rows(data, "E03", "detection")
    curve(ax, pts, "Mô phỏng", scale_y=100)
    ax.plot(
        [float(r["x"]) for r in pts],
        [float(r["reference"]) * 100 for r in pts],
        "--",
        label="Mốc lý thuyết",
    )
    ax.set(
        xlabel="Số bit công khai để kiểm tra", ylabel="Phát hiện ít nhất một lỗi (%)"
    )
    save("03_detection", fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for metric, label in (
        ("sifted", "Sau sàng lọc"),
        ("reconciled", "Sau kiểm tra khóa"),
        ("final_bits", "Khóa cuối"),
    ):
        curve(axes[0], rows(data, "E04", metric, noise="0.01"), label, scale_y=0.001)
    axes[0].set(xscale="log", xlabel="Số xung phát", ylabel="Độ dài (nghìn bit)")
    pts = rows(data, "E05", "rate")
    curve(axes[1], pts, "Khóa hữu hạn")
    axes[1].axhline(
        float(pts[0]["reference"]),
        ls="--",
        color="gray",
        label="Mốc khi có rất nhiều dữ liệu",
    )
    axes[1].set(
        xscale="log", xlabel="Số xung phát", ylabel="Bit khóa cuối trên mỗi xung"
    )
    save("04_keys", fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    for series, label in (
        ("BB84 WCP", "BB84 xung yếu"),
        ("BB84 decoy", "BB84 có trạng thái mồi"),
        ("E91", "E91"),
    ):
        curve(ax, rows(data, "E06", "rate", series=series), label, intervals=False)
    ax.set(
        yscale="log",
        xlabel="Chiều dài mỗi nhánh (km)",
        ylabel="Bit khóa trên xung hoặc cặp phát",
    )
    save("05_distance", fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    for backend, label in (("fast", "Nhanh dùng NumPy"), ("qiskit", "Qiskit Aer")):
        backend_points = [
            r
            for r in data["backend"]["samples"]
            if r["config"]["bb84"]["backend"] == backend
        ]
        ax.plot(
            [r["config"]["bb84"]["n_pulses"] for r in backend_points],
            [1000 * r["median_seconds"] for r in backend_points],
            "o-",
            label=label,
        )
    ax.set(
        yscale="log",
        xlabel="Số xung mô phỏng",
        ylabel="Thời gian trung vị (ms, thang log)",
    )
    save("06_backends", fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    for eve, label in ((0, "Không có Eve"), (1, "Eve chặn toàn bộ")):
        curve(ax, rows(data, "E07", "chsh", series=f"E91 fast, Eve={eve}"), label)
    ax.axhline(2, color="gray", ls="--", label="Giới hạn Bell")
    ax.set(xlabel="Chất lượng trạng thái rối V", ylabel="Chỉ số CHSH")
    save("07_e91", fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for cipher, label in (
        ("aes256gcm", "AES 256 GCM"),
        ("chacha20poly1305", "ChaCha20 Poly1305"),
    ):
        for ax, metric in zip(axes, ("encrypt_mbps", "decrypt_mbps"), strict=True):
            curve(ax, rows(data, "E09", metric, series=f"{cipher} · text"), label)
            ax.set(xscale="log", xlabel="Kích thước tệp (byte)", ylabel="Tốc độ (MB/s)")
    axes[0].set_title("Mã hóa văn bản")
    axes[1].set_title("Giải mã văn bản")
    save("08_cipher", fig)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    pts = data["E12"]["rows"]
    ax.bar(
        ["Không xác thực", "Có HMAC"],
        [float(r["value"]) * 100 for r in pts],
        color=["#b35643", "#35739b"],
    )
    for i, r in enumerate(pts):
        ax.text(
            i,
            float(r["value"]) * 100 + 3,
            f"{r['successes']}/{r['n']} lượt",
            ha="center",
        )
    ax.set(ylabel="Eve tấn công thành công (%)", ylim=(0, 118))
    save("09_authentication", fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for mode, ax, title in (
        ("steady", axes[0], "Eve chặn đều"),
        ("late", axes[1], "Eve dồn chặn về cuối"),
    ):
        # Stored mode names are checked instead of silently accepting empty plots.
        actual_mode = "adaptive" if mode == "late" else mode
        available = {r.get("mode") for r in data["E13"]["rows"]}
        if actual_mode not in available:
            actual_mode = "late" if mode == "late" else mode
        for detector in ("ci", "sprt", "cusum"):
            pts = [
                r
                for r in data["E13"]["rows"]
                if r["metric"] == "tpr"
                and r.get("noise") == "0.01"
                and r.get("mode") == actual_mode
                and r["series"].startswith(detector + " ·")
            ]
            if not pts:
                raise ValueError(f"Missing detector points: {detector}, {actual_mode}")
            curve(
                ax,
                sorted(pts, key=lambda r: float(r["x"])),
                detector.upper(),
                scale_x=100,
                scale_y=100,
            )
        ax.set(
            title=title,
            xlabel="Tỷ lệ xung Eve chặn (%)",
            ylabel="Báo động đúng (%)",
            ylim=(-5, 105),
        )
    save("10_monitor", fig)


def report_tables(data: dict[str, Any]) -> dict[str, Any]:
    """Store compact report tables using retained configuration and measurements."""
    defaults = data["E01"]["metadata"]["session_defaults"]
    tables: dict[str, Any] = {
        "protocols": {
            "headers": ["Nội dung", "BB84", "E91"],
            "rows": [
                [
                    "Cách tạo dữ liệu",
                    "Chuẩn bị và đo trạng thái",
                    "Đo hai phía của cặp rối",
                ],
                ["Dữ liệu kiểm tra", "Bit mẫu và QBER", "Bit mẫu, QBER và CHSH"],
                ["Nguồn trong mô hình", "Đơn photon ở quét cơ sở", "Nguồn cặp rối"],
                [
                    "Dấu hiệu can thiệp",
                    "Tỷ lệ lỗi có thể tăng",
                    "Tương quan có thể giảm",
                ],
                ["Kênh cổ điển", "Phải xác thực", "Phải xác thực"],
                [
                    "Phần xử lý sau đo",
                    "Sửa sai, xác minh, rút ngắn khóa",
                    "Sửa sai, xác minh, rút ngắn khóa",
                ],
            ],
            "widths": [3.4, 6.3, 6.3],
            "source": "Mô hình BB84/E91 và cấu hình thực nghiệm đã lưu; "
            "đây là bảng mô tả.",
        },
        "parameters": {
            "headers": ["Tham số", "Giá trị nền", "Ý nghĩa"],
            "rows": [],
            "widths": [4, 3.2, 8.8],
            "source": "results/quick/E01_qber_eve.json, session_defaults; "
            "từng E thay đổi tham số riêng.",
        },
        "scenarios": {
            "headers": ["Thực nghiệm", "Dữ liệu mỗi cấu hình", "Lượt lặp đã chạy"],
            "rows": [],
            "widths": [5.3, 7, 3.7],
            "source": "CSV và JSON trong results/quick; dùng cột n của bản chạy nhanh.",
        },
        "decisions": {
            "headers": ["Bước kiểm tra", "Khi nào dừng", "Cách hiểu"],
            "rows": [
                ["Đủ mẫu", "Mẫu dưới mức cấu hình", "Chưa đủ dữ liệu để ước lượng"],
                [
                    "QBER",
                    "Cận trên vượt ngưỡng",
                    "Kênh chưa đáp ứng điều kiện tạo khóa",
                ],
                [
                    "Bell ở E91",
                    "Cận dưới CHSH không vượt giới hạn",
                    "Tương quan chưa đủ rõ trong mô hình",
                ],
                [
                    "Xác minh khóa",
                    "Thẻ kiểm tra không khớp",
                    "Hai bên chưa có cùng chuỗi bit",
                ],
                [
                    "Độ dài khóa",
                    "Độ dài tính được không dương",
                    "Không còn đủ phần bí mật theo công thức",
                ],
                [
                    "Xác thực dữ liệu",
                    "HMAC hoặc thẻ AEAD sai",
                    "Từ chối thông điệp hoặc tệp",
                ],
            ],
            "widths": [3.5, 6, 6.5],
            "source": "Điều kiện trong postprocess, monitor, auth và crypto; "
            "bảng mô tả thiết kế.",
        },
        "results": {
            "headers": ["Kịch bản", "Kết quả đã lưu", "Nhận xét chính"],
            "rows": [],
            "widths": [4.8, 5.2, 6],
            "source": "E01, E05, E07, E10, E11, E12 trong results/quick; "
            "số liệu của mẫu đã chạy.",
        },
    }
    for group, key, label, meaning in (
        ("bb84", "n_pulses", "Số xung nền", "Quy mô một phiên trước khi quét"),
        ("bb84", "p_z", "Xác suất chọn Z", "Điều chỉnh phân bố cơ sở"),
        ("bb84", "test_fraction", "Tỷ lệ bit kiểm tra", "Phần sàng lọc được công khai"),
        ("bb84", "k_min", "Mẫu tối thiểu", "Điều kiện đủ dữ liệu kiểm tra"),
        ("bb84", "q_max", "Ngưỡng QBER", "So với cận trên QBER"),
        ("bb84", "eps_pe", "Sai số ước lượng", "Tham số của cận thống kê"),
        ("bb84", "eps_sec", "Tham số riêng tư", "Giảm độ dài khóa cuối"),
        ("bb84", "eps_cor", "Tham số xác minh", "Kiểm soát sai khác khóa còn lại"),
        (
            "channel",
            "alpha_db_per_km",
            "Suy hao dB/km",
            "Độ giảm tín hiệu theo khoảng cách",
        ),
        ("channel", "eta_det", "Hiệu suất detector", "Khả năng ghi nhận tín hiệu đến"),
        ("channel", "p_dark", "Xác suất đếm tối", "Dò giả khi không có tín hiệu"),
    ):
        tables["parameters"]["rows"].append([label, str(defaults[group][key]), meaning])
    for exp, label, description in (
        ("E01", "E1 nghe lén BB84", "Xung nhanh và các điểm Aer nhỏ"),
        ("E02", "E2 nhiễu nền", "Xung BB84, sửa sai lý tưởng"),
        ("E03", "E3 số bit kiểm tra", "Mẫu lỗi nhị thức lý tưởng"),
        ("E04", "E4 xử lý khóa", "Quét số xung, Cascade thực"),
        ("E05", "E5 khóa hữu hạn", "Quét số xung, nhiễu cố định"),
        ("E07", "E7 tương quan E91", "Cặp rối và các điểm Aer"),
        ("E10", "E10 mã hóa tệp", "Văn bản, PNG và nhị phân"),
        ("E12", "E12 giả mạo", "Có và không có HMAC"),
        ("E13", "E13 giám sát", "Chặn đều và chặn muộn"),
    ):
        sample = next(r for r in data[exp]["rows"] if r.get("n") and r["n"] != "0")
        tables["scenarios"]["rows"].append([label, description, sample["n"]])

    def selected(exp: str, metric: str, **filters: str) -> Row:
        """Read exactly one retained row before formatting a summary cell."""
        matches: list[Row] = [
            r
            for r in data[exp]["rows"]
            if r["metric"] == metric and all(r.get(k) == v for k, v in filters.items())
        ]
        if len(matches) != 1:
            raise ValueError("Ambiguous summary measurement")
        return matches[0]

    eve = selected("E01", "qber", backend="fast", noise="0", x="1")
    finite = selected("E05", "rate", x="1000000")
    bell = selected("E07", "chsh", series="E91 fast, Eve=1", x="1")
    good_files = [r for r in data["E10"]["rows"] if r["metric"] == "integrity"]
    bad_files = [r for r in data["E11"]["rows"] if r["metric"] == "tamper"]
    off = selected("E12", "mitm", x="no HMAC")
    on = selected("E12", "mitm", x="HMAC")
    tables["results"]["rows"] = [
        [
            "Eve chặn toàn bộ, kênh sạch",
            f"QBER {float(eve['value']) * 100:.2f}%",
            "Can thiệp tạo sai lệch quan sát được",
        ],
        [
            "Khóa hữu hạn, phiên lớn nhất E5",
            f"{float(finite['value']):.4f} bit/xung",
            "Vẫn dưới mốc khi có rất nhiều dữ liệu",
        ],
        [
            "E91 có Eve, V tốt nhất",
            f"CHSH {float(bell['value']):.3f}",
            "Tương quan giảm dưới giới hạn Bell",
        ],
        [
            "Tệp hợp lệ",
            f"{sum(int(r['successes']) for r in good_files)}/"
            f"{sum(int(r['n']) for r in good_files)} lượt khôi phục đúng",
            "Đạt chức năng trên các mẫu đã thử",
        ],
        [
            "Tệp bị sửa",
            f"{sum(int(r['successes']) for r in bad_files)}/"
            f"{sum(int(r['n']) for r in bad_files)} lượt bị từ chối",
            "Các dạng sửa đổi đã thử được phát hiện",
        ],
        [
            "Giả mạo kênh cổ điển",
            f"Không HMAC: {off['successes']}/{off['n']}; "
            f"có HMAC: {on['successes']}/{on['n']}",
            "Cần xác thực ngoài việc theo dõi QBER",
        ],
    ]
    return tables


def main() -> None:
    """Write auditable derived evidence, its provenance, and compact figures."""
    OUT.mkdir(parents=True, exist_ok=True)
    data, sources = load()
    plots(data)
    output = {
        **provenance("numpy", "matplotlib"),
        "platform": platform.platform(),
        "mode": "replot retained measurements; no new trials or randomness",
        "seed": data["E01"]["metadata"]["seed"],
        "config": {
            "source": "results/quick",
            "uncertainty": "retain CSV intervals",
            "plot_library": version("matplotlib"),
        },
        "source_files": sources,
        "source_archive": {
            item["path"]: (ROOT / item["path"]).read_bytes().decode("utf-8")
            for item in sources
            if item["path"].startswith("results/demo_chat/")
        },
        "evidence": data,
        "report_tables": report_tables(data),
        "figures": {p.name: sha(p) for p in sorted(OUT.glob("*.png"))},
    }
    (OUT / "summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Retained {len(data)} evidence groups; wrote figures and summary to {OUT}")


if __name__ == "__main__":
    main()

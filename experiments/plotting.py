"""Render the published CSVs as consistent Vietnamese or English figures."""

import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

Text = tuple[str, str]


@dataclass(frozen=True)
class Figure:
    """A figure title, the x-axis label, and the CSV metrics to plot."""

    slug: str
    title: Text
    xlabel: Text
    metrics: tuple[str, ...]
    log_x: bool = False
    log_y: bool = False


FIGURES = (
    Figure(
        "qber_eve",
        ("QBER khi Eve chặn–phát lại", "QBER under intercept-resend"),
        ("Tỷ lệ xung Eve chặn", "Intercept fraction"),
        ("qber",),
    ),
    Figure(
        "noise_abort",
        ("Dung sai nhiễu BB84", "BB84 noise tolerance"),
        ("QBER nền", "Baseline QBER"),
        ("abort", "final_bits"),
    ),
    Figure(
        "sample_detection",
        ("Phát hiện Eve qua mẫu công khai", "Eve detection from a sample"),
        ("Số bit so sánh", "Compared bits"),
        ("detection",),
        log_x=True,
    ),
    Figure(
        "key_pipeline",
        ("Các bước tạo khóa BB84", "BB84 key pipeline"),
        ("Số xung phát", "Emitted pulses"),
        ("sifted", "reconciled", "final_bits", "ec_efficiency"),
        log_x=True,
    ),
    Figure(
        "finite_key",
        ("Tổn thất do khóa hữu hạn", "Finite-key penalty"),
        ("Số xung phát", "Emitted pulses"),
        ("rate",),
        log_x=True,
    ),
    Figure(
        "distance",
        ("Tốc độ khóa theo chiều dài sợi", "Key rate vs fibre length"),
        ("Chiều dài mỗi nhánh (km)", "Length per arm (km)"),
        ("rate",),
        log_y=True,
    ),
    Figure(
        "chsh",
        ("Kiểm định Bell của E91", "E91 Bell test"),
        ("Độ hiển thị Werner", "Werner visibility"),
        ("chsh", "qber", "bell_abort"),
    ),
    Figure(
        "protocol_comparison",
        ("So sánh BB84 và E91", "BB84 and E91 comparison"),
        ("Xác suất lật bit trên kênh", "Channel bit-flip probability"),
        ("sift_rate", "abort", "rate", "session_ms"),
    ),
    Figure(
        "cipher_benchmark",
        ("Hiệu năng mã hóa tệp QKDH", "QKDH file performance"),
        ("Kích thước bản rõ (byte)", "Plaintext size (bytes)"),
        ("encrypt_mbps", "decrypt_mbps", "encrypt_ms", "decrypt_ms"),
        log_x=True,
    ),
    Figure(
        "end_to_end",
        ("Quy trình phân phối khóa và mã hóa tệp", "QKD and file encryption"),
        ("Hạng mục", "Category"),
        ("integrity", "stage_ms"),
        log_y=True,
    ),
    Figure(
        "tamper",
        ("Toàn vẹn dữ liệu và tái sử dụng nonce", "Tampering and nonce reuse"),
        ("Thử nghiệm", "Trial"),
        ("tamper", "nonce_leak"),
    ),
    Figure(
        "classical_mitm",
        ("Xác thực kênh cổ điển", "Classical channel authentication"),
        ("Chế độ", "Mode"),
        ("mitm",),
    ),
    Figure(
        "detectors",
        ("Hiệu năng bộ giám sát", "Monitor performance"),
        ("Tỷ lệ xung Eve chặn", "Intercept fraction"),
        ("tpr", "delay", "roc", "fpr", "threshold_fpr", "design_bits"),
    ),
    Figure(
        "randomness",
        ("Chẩn đoán ngẫu nhiên trên chuỗi bit", "Bitstream diagnostics"),
        ("Phép thử", "Test"),
        ("p_value", "pass"),
    ),
    Figure(
        "quantum_security",
        (
            "Chi phí tìm khóa cổ điển và lượng tử",
            "Classical and quantum key-search cost",
        ),
        ("Thuật toán", "Primitive"),
        ("security",),
    ),
)

METRICS: dict[str, Text] = {
    "qber": ("QBER", "QBER"),
    "abort": ("Tỷ lệ dừng phiên", "Session abort rate"),
    "final_bits": ("Độ dài khóa cuối (bit)", "Final key length (bits)"),
    "detection": ("Xác suất phát hiện", "Detection probability"),
    "sifted": ("Số bit sau sàng lọc", "Sifted bits"),
    "reconciled": ("Số bit sau hiệu chỉnh", "Reconciled bits"),
    "ec_efficiency": ("Hệ số rò rỉ Cascade", "Cascade leakage factor"),
    "rate": ("Tốc độ khóa (bit/lượt phát)", "Key rate (bits/emission)"),
    "chsh": ("Tham số CHSH", "CHSH statistic"),
    "bell_abort": ("Tỷ lệ dừng ở cổng Bell", "Bell-gate abort rate"),
    "sift_rate": ("Tỷ lệ sàng lọc trên lượt dò", "Sifting rate per detection"),
    "session_ms": ("Thời gian mô phỏng phiên (ms)", "Session runtime (ms)"),
    "encrypt_mbps": ("Tốc độ mã hóa (MB/s)", "Encryption speed (MB/s)"),
    "decrypt_mbps": ("Tốc độ giải mã (MB/s)", "Decryption speed (MB/s)"),
    "encrypt_ms": ("Độ trễ mã hóa (ms)", "Encryption latency (ms)"),
    "decrypt_ms": ("Độ trễ giải mã (ms)", "Decryption latency (ms)"),
    "integrity": ("Tỷ lệ khôi phục đúng", "Correct recovery rate"),
    "stage_ms": ("Thời gian mỗi bước (ms)", "Stage duration (ms)"),
    "tamper": ("Tỷ lệ từ chối tệp bị sửa", "Tamper rejection rate"),
    "nonce_leak": ("Tỷ lệ lộ XOR bản rõ", "Plaintext XOR exposure rate"),
    "mitm": ("Tỷ lệ thành công của Eve", "Eve success rate"),
    "tpr": ("Tỷ lệ báo động đúng", "True positive rate"),
    "delay": ("Số bit đến báo động", "Bits until alarm"),
    "roc": ("Tỷ lệ báo động đúng", "True positive rate"),
    "fpr": ("Tỷ lệ báo động nhầm", "False positive rate"),
    "threshold_fpr": ("Tỷ lệ báo động nhầm", "False positive rate"),
    "design_bits": ("Số bit đến quyết định", "Bits until decision"),
    "p_value": ("Giá trị p", "p-value"),
    "pass": ("Tỷ lệ đạt ngưỡng", "Test pass rate"),
    "security": ("Số mũ chi phí (bit)", "Work exponent (bits)"),
}

VI = {
    "classical": "Cổ điển",
    "quantum": "Lượng tử",
    "text": "văn bản",
    "random": "ngẫu nhiên",
    "encrypt": "mã hóa",
    "decrypt": "giải mã",
    "hash": "băm",
    "header": "đầu tệp",
    "ciphertext": "bản mã",
    "tag": "thẻ",
    "truncate": "cắt ngắn",
    "reorder": "đảo khối",
    "nonce reuse": "lặp nonce",
    "no HMAC": "Tắt HMAC",
    "steady": "đều",
    "adaptive": "chặn muộn",
    "frequency": "Tần suất",
    "block_frequency": "Tần suất khối",
    "runs": "Chuỗi liên tiếp",
    "longest_run": "Chuỗi dài nhất",
    "approximate_entropy": "Entropy xấp xỉ",
    "BB84 raw": "BB84 đã sàng lọc",
    "BB84 final": "BB84 khóa cuối",
    "BB84 WCP": "BB84 xung yếu",
    "BB84 decoy": "BB84 mồi",
    "threshold": "ngưỡng",
    "joint": "kiểm định chung",
}

COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#665191", "#A15C00")
MARKERS = ("o", "s", "^", "D", "v", "P")
DETECTOR_ORDER = ("threshold", "ci", "sprt", "cusum", "joint")


def _label(value: str, language: int) -> str:
    """Translate category names and compound legend entries."""
    return (
        " · ".join(VI.get(part, part) for part in value.split(" · "))
        if not language
        else value
    )


def _positions(values: list[str]) -> tuple[dict[str, float], bool]:
    """Keep numeric sweep spacing, or map categorical values to tick positions."""
    try:
        return {value: float(value) for value in values}, False
    except ValueError:
        return {value: float(index) for index, value in enumerate(values)}, True


def _plot_panel(
    ax: Axes,
    figure: Figure,
    metric: str,
    rows: list[dict[str, str]],
    language: int,
    uncertainty: str,
) -> None:
    """Read plotted values and bounds directly from the corresponding CSV rows."""
    data = [row for row in rows if row["metric"] == metric]
    if metric in ("tpr", "delay"):
        noise = data[0]["noise"]
        data = [r for r in data if r["noise"] == noise]
        ax.set_title(f"Q₀={noise}")
    if metric == "roc":
        noise = data[0]["noise"]
        target = min(
            (data_row for data_row in data if data_row["noise"] == noise),
            key=lambda r: abs(float(r["eve_fraction"]) - 0.1),
        )["eve_fraction"]
        data = [
            r
            for r in data
            if r["noise"] == noise
            and r["eve_fraction"] == target
            and r["mode"] == "steady"
        ]
        ax.set_title(f"Q₀={noise}, p={target}")
    x_values, categorical = _positions(list(dict.fromkeys(row["x"] for row in data)))
    series = list(dict.fromkeys(row["series"] for row in data))
    reference_plotted = False
    for index, name in enumerate(series):
        group = [row for row in data if row["series"] == name]
        if not categorical:
            group.sort(key=lambda row: float(row["x"]))
        color = (
            COLORS[2]
            if name.startswith("BB84 decoy")
            else COLORS[0]
            if name.startswith("BB84")
            else COLORS[1]
            if name.startswith("E91")
            else COLORS[index % len(COLORS)]
        )
        shift = (index - (len(series) - 1) / 2) * min(0.14, 0.7 / len(series))
        style = ("-", "--", "-.", ":")[index % 4]
        marker = MARKERS[index % len(MARKERS)]
        legend = name
        detector = name.split(" · ")[0]
        if detector in DETECTOR_ORDER:
            detector_index = DETECTOR_ORDER.index(detector)
            color = COLORS[detector_index]
            marker = MARKERS[detector_index]
            if metric in ("tpr", "delay"):
                style = "--" if group[0]["mode"] == "adaptive" else "-"
                legend = f"{detector} · {group[0]['mode']}"
            elif metric == "roc":
                legend = detector
            else:
                first = next(s for s in series if s.split(" · ")[0] == detector)
                style = "-" if name == first else "--"
        xs, ys, below, above = [], [], [], []
        for row in group:
            x = x_values[row["x"]] + (shift if categorical else 0)
            if row["value"] == "":
                if metric == "security" and row["attack"] == "Shor":
                    ax.annotate(
                        "Shor",
                        (x, 0),
                        xytext=(0, 5),
                        textcoords="offset points",
                        ha="center",
                        fontsize=8,
                    )
                continue
            y = float(row["value"])
            xs.append(x)
            ys.append(y)
            below.append(max(0, y - float(row["low"])) if row["low"] else 0)
            above.append(max(0, float(row["high"]) - y) if row["high"] else 0)
        line = "none" if categorical else style
        if ys:
            ax.errorbar(
                xs,
                ys,
                yerr=[below, above],
                label=_label(legend, language),
                marker=marker,
                linestyle=line,
                linewidth=1.2,
                markersize=4,
                elinewidth=0.8,
                capsize=2,
                color=color,
            )
        references = {
            x_values[row["x"]]: float(row["reference"])
            for row in group
            if row["reference"]
        }
        if references and (not categorical or metric in ("p_value", "pass")):
            if categorical:
                if not reference_plotted:
                    ax.axhline(
                        next(iter(references.values())),
                        color="#555555",
                        linestyle=":",
                        linewidth=1.2,
                    )
            else:
                ax.plot(
                    list(references),
                    list(references.values()),
                    color=color,
                    linestyle=":",
                    linewidth=1.2,
                    alpha=0.65,
                )
            reference_plotted = True
    if metric == "chsh":
        ax.axhline(
            2,
            color="#555555",
            linestyle="--",
            linewidth=1,
            label=("Giới hạn cổ điển", "Classical bound")[language],
        )
    if categorical:
        ax.set_xticks(
            list(x_values.values()),
            [_label(x, language) for x in x_values],
            rotation=20,
            ha="right",
        )
    if figure.log_x:
        ax.set_xscale("log")
    if figure.log_y and metric == "rate":
        # Keep the zero-rate cutoffs visible on a quasi-logarithmic scale.
        ax.set_yscale("symlog", linthresh=1e-9)
    elif figure.log_y and metric == "stage_ms":
        ax.set_yscale("log")
    xlabel = (
        ("Tỷ lệ báo động nhầm", "False positive rate")
        if metric == "roc"
        else ("Mức α", "α level")
        if metric == "fpr"
        else ("Ngưỡng QBER", "QBER cutoff")
        if metric == "threshold_fpr"
        else ("QBER nền", "Baseline QBER")
        if metric == "design_bits"
        else figure.xlabel
    )
    ax.set(xlabel=xlabel[language], ylabel=METRICS[metric][language])
    ax.grid(alpha=0.22)
    handles, labels = ax.get_legend_handles_labels()
    if reference_plotted:
        handles.append(Line2D([], [], color="#555555", linestyle=":"))
        labels.append(("Mốc lý thuyết / ngưỡng", "Theory / threshold")[language])
    if handles:
        ax.legend(handles, labels, fontsize=7, ncols=2 if len(handles) > 5 else 1)
    if any(row["low"] for row in data):
        ax.text(0.01, 1.015, uncertainty, transform=ax.transAxes, fontsize=7)


def plot(csv_path: Path, figure: Figure, language: str) -> None:
    """Render raster and vector outputs with the same name stem as the CSV."""
    lang = int(language == "en")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    columns = 1 if len(figure.metrics) < 3 else 2
    height = (len(figure.metrics) + columns - 1) // columns
    fig, grid = plt.subplots(
        height,
        columns,
        squeeze=False,
        figsize=(7 * columns, 3.6 * height),
        layout="constrained",
    )
    fig.suptitle(figure.title[lang], fontsize=14)
    uncertainty = (
        ("Trung vị và khoảng tứ phân vị", "Median and IQR")
        if figure.slug == "cipher_benchmark"
        else ("Khoảng tin cậy 95%", "95% confidence interval")
    )[lang]
    for ax, metric in zip(grid.flat, figure.metrics, strict=False):
        _plot_panel(ax, figure, metric, rows, lang, uncertainty)
    for ax in list(grid.flat)[len(figure.metrics) :]:
        ax.set_visible(False)
    for suffix in (".png", ".pdf"):
        fig.savefig(csv_path.with_suffix(suffix), dpi=300)
    plt.close(fig)

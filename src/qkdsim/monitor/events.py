"""Write structured transition events and per-session abort evidence."""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from qkdsim.monitor.detectors import DetectorDecision
from qkdsim.monitor.metrics import Metrics, WindowQBER

_COUNTERS = ("sent", "detected", "sifted", "double_clicks", "compared", "errors")


@dataclass(frozen=True)
class Event:
    """Versioned snapshot of public observations at a state transition."""

    timestamp: str
    session_id: str
    previous_state: str | None
    state: str
    alert: str
    reason: str
    metrics: Metrics
    detector: DetectorDecision | None
    schema_version: int = 1

    def to_dict(self) -> dict[str, object]:
        """Serialize only explicitly listed public fields."""
        payload = asdict(self)
        payload["counters"] = {name: getattr(self.metrics, name) for name in _COUNTERS}
        payload["metrics"] = {
            item.name: getattr(self.metrics, item.name)
            for item in fields(self.metrics)
            if item.name not in _COUNTERS
        }
        return payload

    def append(self, path: Path) -> None:
        """Append one complete JSONL record, rejecting nonfinite numbers."""
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(self.to_dict(), allow_nan=False) + "\n")


def write_evidence(
    directory: Path,
    event: Event,
    windows: tuple[WindowQBER, ...],
    e0: float,
    y0: float,
    q_max: float,
) -> None:
    """Save abort evidence and plot measured QBER with exact 95% intervals."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(8, 4))
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    if windows:
        x = [window.cumulative_compared for window in windows]
        qber = [window.qber for window in windows]
        ax.errorbar(
            x,
            qber,
            yerr=[
                [max(0.0, w.qber - w.clopper_pearson[0]) for w in windows],
                [max(0.0, w.clopper_pearson[1] - w.qber) for w in windows],
            ],
            fmt=".",
            label="QBER theo cửa sổ",
        )
        ax.plot(x, [w.cumulative_qber for w in windows], label="QBER tích lũy")
        ax.axhline(e0, linestyle="--", label="Nền QBER")
        ax.axhline(q_max, linestyle=":", label="Ngưỡng QBER")
        if event.detector is not None and event.detector.outcome == "alarm":
            ax.axvline(
                event.detector.compared,
                color="tab:red",
                label="Phát hiện bất thường",
            )
        ax.legend()
    else:
        ax.text(
            0.5,
            0.5,
            "Phiên chưa có mẫu công khai",
            transform=ax.transAxes,
            ha="center",
        )
    ax.set(xlabel="Bit đã so sánh", ylabel="QBER", ylim=(0, None))
    figure.tight_layout()
    plot = "qber.png"
    figure.savefig(directory / plot)
    report = event.to_dict()
    report.update(windows=[asdict(window) for window in windows], plot=plot)
    report.update(baseline={"e0": e0, "y0": y0, "q_max": q_max})
    (directory / "evidence.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

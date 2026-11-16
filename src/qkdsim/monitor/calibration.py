"""Persist independently observed honest-channel baselines."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Calibration:
    """Binomial pilot counts, with per-observation variance p(1-p)."""

    sent: int
    detected: int
    compared: int
    errors: int
    empty_gates: int
    empty_clicks: int

    def __post_init__(self) -> None:
        pairs = (
            (self.detected, self.sent),
            (self.errors, self.compared),
            (self.empty_clicks, self.empty_gates),
        )
        if any(
            type(count) is not int
            or type(total) is not int
            or not 0 <= count <= total
            or total == 0
            for count, total in pairs
        ):
            raise ValueError("calibration requires valid counts and nonempty samples")

    @property
    def qber(self) -> float:
        """Return errors divided by compared pilot bits."""
        return self.errors / self.compared

    @property
    def detection_rate(self) -> float:
        """Return the fraction of detected pilot pulses."""
        return self.detected / self.sent

    def write(self, path: Path) -> None:
        """Write the pilot counts and derived rates to calibration.json."""
        qber, yield_rate = self.qber, self.detection_rate
        data = {
            "counts": asdict(self),
            "e0": qber,
            "y0": yield_rate,
            "qber_variance": qber * (1 - qber),
            "detection_variance": yield_rate * (1 - yield_rate),
            "dark_count_proxy": self.empty_clicks / self.empty_gates,
        }
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> "Calibration":
        """Restore a baseline from its counts."""
        try:
            counts = json.loads(path.read_text(encoding="utf-8"))["counts"]
            return cls(**counts)
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid calibration file") from exc

"""Compute monitoring rates from public BB84 observations."""

from dataclasses import dataclass

import numpy as np
from numpy.random import Generator

from qkdsim.analysis.stats import Interval, clopper_pearson, wilson_interval
from qkdsim.config import ChannelConfig
from qkdsim.physics.detector import detect
from qkdsim.physics.states import MaskArray
from qkdsim.postprocess.estimation import QBERStatistics
from qkdsim.postprocess.sifting import SiftedKey
from qkdsim.protocols.bb84 import BB84Transmission


@dataclass(frozen=True)
class WindowQBER:
    """Disjoint public test windows in transmission order, with cumulative QBER."""

    compared: int
    errors: int
    cumulative_compared: int
    cumulative_qber: float
    qber: float
    clopper_pearson: Interval
    wilson: Interval


@dataclass(frozen=True)
class Metrics:
    """Aggregate public counters and rates, without sample bits or pulse indices."""

    sent: int = 0
    detected: int = 0
    sifted: int = 0
    double_clicks: int = 0
    detection_rate: float | None = None
    sift_rate: float | None = None
    double_click_rate: float | None = None
    compared: int = 0
    errors: int = 0
    qber: float | None = None
    qber_upper: float | None = None
    clopper_pearson: Interval | None = None
    wilson: Interval | None = None
    qber_z: float | None = None
    qber_x: float | None = None


def _ratio(count: int, total: int) -> float | None:
    return count / total if total else None


def summarize(
    observed: BB84Transmission,
    sifted: SiftedKey,
    stats: QBERStatistics | None = None,
) -> tuple[Metrics, MaskArray]:
    """Return aggregate rates and chronological mismatches of the revealed bits."""
    indices = stats.sample_indices if stats is not None else np.empty(0, dtype=np.int64)
    errors = observed.alice_bits[indices] != observed.bob_bits[indices]
    z = observed.alice_bases[indices] == 0
    x = ~z
    return Metrics(
        sent=sifted.sent,
        detected=sifted.detected,
        sifted=sifted.sifted,
        double_clicks=observed.double_clicks,
        detection_rate=_ratio(sifted.detected, sifted.sent),
        sift_rate=_ratio(sifted.sifted, sifted.detected),
        double_click_rate=_ratio(observed.double_clicks, sifted.sent),
        compared=errors.size,
        errors=stats.errors if stats is not None else 0,
        qber=stats.q_est if stats is not None else None,
        qber_upper=stats.q_ub if stats is not None else None,
        clopper_pearson=stats.clopper_pearson if stats is not None else None,
        wilson=stats.wilson if stats is not None else None,
        qber_z=_ratio(int(np.count_nonzero(errors & z)), int(np.count_nonzero(z))),
        qber_x=_ratio(int(np.count_nonzero(errors & x)), int(np.count_nonzero(x))),
    ), errors


def window_qber(errors: MaskArray, window_size: int) -> tuple[WindowQBER, ...]:
    """Group chronological revealed samples and compute x/n and two 95% CIs."""
    windows = []
    total_errors = 0
    for start in range(0, errors.size, window_size):
        window = errors[start : start + window_size]
        count = int(np.count_nonzero(window))
        total_errors += count
        end = start + window.size
        windows.append(
            WindowQBER(
                window.size,
                count,
                end,
                total_errors / end,
                count / window.size,
                clopper_pearson(count, window.size),
                wilson_interval(count, window.size),
            )
        )
    return tuple(windows)


def empty_gate_clicks(channel: ChannelConfig, sent: int, rng: Generator) -> int:
    """Run known vacuum calibration gates and count the dark-click proxy."""
    empty = np.zeros(sent, dtype=np.int64)
    return int(np.count_nonzero(detect(empty, empty.astype(float), channel, rng).mask))

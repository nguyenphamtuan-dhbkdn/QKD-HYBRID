"""QBER and detection-rate tests using the public sample only."""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.stats import binom  # type: ignore[import-untyped]

from qkdsim.config import BB84Config, MonitorConfig
from qkdsim.physics.states import MaskArray
from qkdsim.postprocess.estimation import hoeffding_upper

DetectorName = Literal["threshold", "ci", "sprt", "cusum", "joint"]
Outcome = Literal["alarm", "clear", "inconclusive"]


@dataclass(frozen=True)
class DetectorDecision:
    """Outcome and the number of compared bits available at the decision."""

    detector: DetectorName
    outcome: Outcome
    compared: int
    statistic: float | None
    upper: float | None
    lower: float | None = None


def qber_p_value(errors: int, trials: int, e0: float) -> float:
    """Return P_e0(X >= errors), dual to the one-sided exact CP lower bound."""
    return float(binom.sf(errors - 1, trials, e0))


def _log_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return math.inf
    if numerator == 0:
        return -math.inf
    return math.log(numerator) - math.log(denominator)


def sprt(errors: MaskArray, config: MonitorConfig) -> DetectorDecision:
    """Stop at the first crossing of log((1-beta)/alpha) or log(beta/(1-alpha))."""
    upper = math.log1p(-config.beta) - math.log(config.alpha)
    lower = math.log(config.beta) - math.log1p(-config.alpha)
    match = _log_ratio(1 - config.e1, 1 - config.e0)
    mismatch = _log_ratio(config.e1, config.e0)
    increments = np.where(errors, mismatch, match)

    # An impossible observation under either hypothesis decides immediately
    # unless a finite increment already crossed a boundary earlier.
    infinite = np.flatnonzero(np.isinf(increments))
    end = int(infinite[0]) + 1 if infinite.size else errors.size
    path = np.cumsum(increments[:end])
    crossings = np.flatnonzero((path >= upper) | (path <= lower))
    if crossings.size:
        index = int(crossings[0])
        value = float(path[index])
        return DetectorDecision(
            "sprt",
            "alarm" if value >= upper else "clear",
            index + 1,
            value if math.isfinite(value) else None,
            upper,
            lower,
        )
    return DetectorDecision(
        "sprt",
        "inconclusive",
        end,
        float(path[-1]) if end else None,
        upper,
        lower,
    )


def cusum(errors: MaskArray, config: MonitorConfig) -> DetectorDecision:
    """Use S_i=max(0,S_{i-1}+log LR(window_i)); spend alpha/W per restart."""
    windows = math.ceil(errors.size / config.window_size)
    if windows == 0:
        return DetectorDecision("cusum", "inconclusive", 0, None, None)
    boundary = math.log(windows) - math.log(config.alpha)
    match = _log_ratio(1 - config.e1, 1 - config.e0)
    mismatch = _log_ratio(config.e1, config.e0)
    score = 0.0
    for start in range(0, errors.size, config.window_size):
        window = errors[start : start + config.window_size]
        wrong = int(np.count_nonzero(window))
        right = window.size - wrong
        if wrong and config.e0 == 0:
            return DetectorDecision(
                "cusum", "alarm", start + window.size, None, boundary
            )
        llr = (wrong * mismatch if wrong else 0) + (right * match if right else 0)
        score = max(0.0, score + llr)
        if score >= boundary:
            return DetectorDecision(
                "cusum", "alarm", start + window.size, score, boundary
            )
    return DetectorDecision("cusum", "clear", errors.size, score, boundary)


def evaluate(
    errors: MaskArray,
    *,
    sent: int,
    detected: int,
    y0: float,
    config: MonitorConfig,
    bb84: BB84Config,
) -> DetectorDecision:
    """Evaluate the selected test once per session with its configured budget."""
    n = errors.size
    if not n:
        return DetectorDecision(config.detector, "inconclusive", 0, None, None)
    if config.detector == "sprt":
        return sprt(errors, config)
    if config.detector == "cusum":
        return cusum(errors, config)

    count = int(np.count_nonzero(errors))
    if config.detector == "threshold":
        bound = hoeffding_upper(count, n, bb84.eps_pe)
        return DetectorDecision(
            "threshold",
            "alarm" if bound > bb84.q_max else "clear",
            n,
            bound,
            bb84.q_max,
        )
    p_qber = qber_p_value(count, n, config.e0)
    if config.detector == "ci":
        return DetectorDecision(
            "ci",
            "alarm" if p_qber < config.alpha else "clear",
            n,
            p_qber,
            config.alpha,
        )
    # Two-sided paired tails for yield, and a one-sided tail for elevated QBER.
    # The Bonferroni bound holds even when the two statistics are dependent.
    p_yield = 2 * min(
        float(binom.cdf(detected, sent, y0)),
        float(binom.sf(detected - 1, sent, y0)),
    )
    p_joint = min(1.0, 2 * min(p_yield, p_qber))
    return DetectorDecision(
        "joint",
        "alarm" if p_joint < config.alpha else "clear",
        n,
        p_joint,
        config.alpha,
    )

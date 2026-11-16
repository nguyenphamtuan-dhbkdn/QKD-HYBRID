"""Monte Carlo acceptance for all monitor modes and both SPRT hypotheses."""

import math
from dataclasses import replace

import pytest
from numpy.random import default_rng

from qkdsim.config import BB84Config, MonitorConfig
from qkdsim.monitor.detectors import DetectorName, evaluate, sprt

TRIALS = 10_000
BB84 = BB84Config()
MONITOR = MonitorConfig()


def _four_sigma(probability: float, trials: int) -> float:
    """Binomial standard error of the simulated rate, multiplied by four."""
    return 4 * math.sqrt(probability * (1 - probability) / trials)


@pytest.mark.statistical
@pytest.mark.parametrize("method", ["threshold", "ci", "sprt", "cusum", "joint"])
def test_honest_false_alarms_and_full_ir_detection(method: DetectorName) -> None:
    cfg = replace(MONITOR, detector=method)
    rng = default_rng(20260116)
    sent = 250_000
    y0 = 0.8
    k = 200
    # Hoeffding's finite-size bound cannot accept even zero errors for k=200.
    # The threshold baseline uses the default session's typical public size.
    honest_k = 10_000 if method == "threshold" else k

    def alarms(probability: float, compared: int) -> int:
        # In the fast model, conditional on k observed matching bases, the
        # testing sample is IID Bernoulli with the matched-basis error rate.
        # Single photons and no dark counts give independent per-pulse yield.
        counts = rng.binomial(sent, y0, size=TRIALS)
        total = 0
        for detected in counts:
            sample = rng.random(compared) < probability
            total += (
                evaluate(
                    sample,
                    sent=sent,
                    detected=int(detected),
                    y0=y0,
                    config=cfg,
                    bb84=BB84,
                ).outcome
                == "alarm"
            )
        return total

    false_alarm_rate = alarms(0.02, honest_k) / TRIALS
    assert false_alarm_rate <= cfg.alpha + _four_sigma(cfg.alpha, TRIALS)
    # Noiseless random-basis IR gives a 1/4 error after matched sifting.
    detection_rate = alarms(0.25, k) / TRIALS
    assert detection_rate >= 0.999


@pytest.mark.statistical
@pytest.mark.parametrize(("hypothesis", "wrong"), [("e0", "alarm"), ("e1", "clear")])
def test_sprt_wald_error_rates(hypothesis: str, wrong: str) -> None:
    cfg = MONITOR
    trials = 30_000
    p, budget = (cfg.e0, cfg.alpha) if hypothesis == "e0" else (cfg.e1, cfg.beta)
    rng = default_rng(20261116)
    errors = 0
    undecided = 0
    for _ in range(trials):
        decision = sprt(rng.random(768) < p, cfg)
        errors += decision.outcome == wrong
        undecided += decision.outcome == "inconclusive"
    assert undecided == 0
    # Discrete overshoot can make either bound conservative.
    assert abs(errors / trials - budget) <= _four_sigma(budget, trials)

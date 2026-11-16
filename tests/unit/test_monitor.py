"""Check detector boundaries and the key-usage policy."""

import math
from dataclasses import replace

import numpy as np
import pytest

from qkdsim.config import BB84Config, MonitorConfig
from qkdsim.monitor.detectors import DetectorDecision, cusum, evaluate, sprt
from qkdsim.monitor.metrics import window_qber
from qkdsim.monitor.policy import AlertLevel, Policy, SessionUnavailable


def test_sprt_stops_at_first_boundary_and_reports_compared_bits() -> None:
    cfg = MonitorConfig(e0=0.1, e1=0.5, alpha=0.1, beta=0.1)
    detected = sprt(np.array([True, True, False, False]), cfg)
    assert detected.outcome == "alarm"
    assert detected.compared == 2
    assert detected.statistic == pytest.approx(2 * math.log(5))
    assert detected.upper == pytest.approx(math.log(9))
    assert detected.lower == pytest.approx(-math.log(9))
    clear = sprt(np.zeros(20, dtype=np.bool_), cfg)
    assert (clear.outcome, clear.compared) == ("clear", 4)
    assert sprt(np.array([False, True]), cfg).outcome == "inconclusive"


def test_sprt_and_cusum_handle_perfect_baselines() -> None:
    cfg = MonitorConfig(e0=0, e1=1)
    err = np.array([False, True])
    assert sprt(err, cfg).outcome == "clear"
    assert sprt(err[::-1], cfg).outcome == "alarm"
    assert cusum(err, cfg).outcome == "alarm"
    assert cusum(np.zeros(20, dtype=np.bool_), cfg).outcome == "clear"


def test_cusum_detects_a_change_after_sprt_has_already_cleared() -> None:
    cfg = MonitorConfig(window_size=20)
    errors = np.concatenate(
        (np.zeros(200, dtype=np.bool_), np.ones(80, dtype=np.bool_))
    )
    assert sprt(errors, cfg).outcome == "clear"
    decision = cusum(errors, cfg)
    assert decision.outcome == "alarm"
    assert decision.compared == 220
    assert decision.upper == pytest.approx(math.log(14 / cfg.alpha))


@pytest.mark.parametrize("detected", [650, 950])
def test_joint_flags_either_direction_of_yield_change(detected: int) -> None:
    errors = np.zeros(300, dtype=np.bool_)
    options = dict(sent=1000, y0=0.8, bb84=BB84Config())
    cfg = MonitorConfig(detector="joint")
    assert evaluate(errors, detected=detected, config=cfg, **options).outcome == "alarm"
    assert evaluate(errors, detected=800, config=cfg, **options).outcome == "clear"
    assert (
        evaluate(
            errors,
            detected=detected,
            config=replace(cfg, detector="ci"),
            **options,
        ).outcome
        == "clear"
    )


def test_window_rates_and_cumulative_counts() -> None:
    first, second = window_qber(np.array([True, False, False]), 2)
    assert first.qber == first.cumulative_qber == 0.5
    assert first.clopper_pearson[0] < first.qber < first.clopper_pearson[1]
    assert second.qber == 0
    assert second.cumulative_qber == pytest.approx(1 / 3)
    assert second.cumulative_compared == 3


def test_threshold_uses_the_finite_sample_upper_bound() -> None:
    options = dict(
        sent=5_000,
        detected=5_000,
        y0=1.0,
        config=MonitorConfig(detector="threshold"),
        bb84=BB84Config(),
    )
    assert evaluate(np.zeros(200, dtype=np.bool_), **options).outcome == "alarm"
    assert evaluate(np.zeros(5_000, dtype=np.bool_), **options).outcome == "clear"


def test_policy_backoff_lockdown_and_explicit_reset() -> None:
    policy = Policy(MonitorConfig(lockdown_after=2, backoff_seconds=5), max_bytes=16)
    policy.admit(10)
    policy.abort(11)
    assert policy.level == AlertLevel.ABORT
    with pytest.raises(SessionUnavailable, match="back-off"):
        policy.admit(15)
    policy.admit(16)
    policy.abort(17)
    assert policy.level == AlertLevel.LOCKDOWN
    with pytest.raises(SessionUnavailable, match="operator reset"):
        policy.admit(1000)
    policy.reset()
    policy.admit(18)
    assert policy.level == AlertLevel.OK


def test_policy_checks_each_rekey_limit_and_warn() -> None:
    cfg = MonitorConfig(max_seconds=4, max_msgs=2)
    policy = Policy(cfg, max_bytes=8)
    assert policy.rekey_reason(8, 2, 4) is None
    assert policy.rekey_reason(9, 2, 4) == "byte limit exceeded"
    assert policy.rekey_reason(8, 3, 4) == "message limit exceeded"
    assert policy.rekey_reason(8, 2, 5) == "key age limit exceeded"
    policy.observe(DetectorDecision("ci", "clear", 100, 0.01, cfg.alpha), 0.01)
    assert policy.level == AlertLevel.WARN
    assert policy.rekey_reason(0, 0, 0) == "alert WARN"

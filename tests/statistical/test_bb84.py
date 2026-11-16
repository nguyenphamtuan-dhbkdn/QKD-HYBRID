"""Use fixed seeds and four binomial standard deviations as tolerances."""

import math

import pytest

from qkdsim.config import (
    AttackConfig,
    BasisMode,
    BB84Config,
    ChannelConfig,
    SessionConfig,
)
from qkdsim.postprocess.estimation import ParameterEstimate, estimate_parameters
from qkdsim.postprocess.sifting import sift
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_bb84

pytestmark = pytest.mark.statistical


def within_four_sigma(observed: float, expected: float, size: int) -> bool:
    """Compare to p ± 4 * sqrt(p*(1-p)/n)."""
    return abs(observed - expected) <= 4 * math.sqrt(expected * (1 - expected) / size)


def test_noiseless_qber_is_zero_over_one_hundred_seeds() -> None:
    for seed in range(100):
        config = SessionConfig(
            seed=seed,
            bb84=BB84Config(n_pulses=10_000, test_fraction=0.25),
            channel=ChannelConfig(e_misalign=0),
        )
        rng = SimRNG(config.seed).generator
        observed, _ = simulate_bb84(config, rng)
        key = sift(observed)
        assert (key.alice_bits == key.bob_bits).all()
        result = estimate_parameters(key, config.bb84, rng)
        assert isinstance(result, ParameterEstimate)
        assert result.stats.q_est == 0


@pytest.mark.parametrize(
    ("p", "basis_mode", "p_z", "bitflip", "expected"),
    [
        (1.0, "random", 0.5, 0.0, 0.25),
        (0.5, "random", 0.5, 0.0, 0.125),
        (1.0, "fixed_z", 0.5, 0.0, 0.25),
        (1.0, "fixed_x", 0.5, 0.0, 0.25),
        (1.0, "fixed_z", 0.75, 0.0, 0.05),
        (0.5, "random", 0.5, 0.10, 0.20),
    ],
)
def test_intercept_resend_qber(
    p: float, basis_mode: BasisMode, p_z: float, bitflip: float, expected: float
) -> None:
    config = SessionConfig(
        bb84=BB84Config(n_pulses=240_000, p_z=p_z),
        channel=ChannelConfig(e_misalign=0, bitflip=bitflip),
        attack=AttackConfig(kind="ir", p=p, basis_mode=basis_mode),
    )
    rng = SimRNG(config.seed).generator
    observed, truth = simulate_bb84(config, rng)
    intercept_fraction = float(truth.eve_intercepted_mask.mean())
    assert within_four_sigma(intercept_fraction, p, config.bb84.n_pulses)
    estimate = estimate_parameters(sift(observed), config.bb84, rng)
    stats = estimate.stats
    assert stats is not None
    assert stats.sample_size >= 10_000
    assert within_four_sigma(stats.q_est, expected, stats.sample_size)


def test_sifting_ratio_given_detected_pulses() -> None:
    config = SessionConfig(
        bb84=BB84Config(n_pulses=80_000),
        channel=ChannelConfig(length_km=10.0, eta_det=0.8, e_misalign=0),
    )
    observed, _ = simulate_bb84(config, SimRNG(config.seed).generator)
    key = sift(observed)
    detection = 0.8 * 10 ** (-0.2 * 10 / 10)
    assert within_four_sigma(key.detected / key.sent, detection, key.sent)
    assert within_four_sigma(key.sifted / key.detected, 0.5, key.detected)

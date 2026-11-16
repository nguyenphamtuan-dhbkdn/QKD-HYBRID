import math
from dataclasses import replace

import numpy as np
import pytest

from qkdsim.analysis.chsh import CHSH_SETTINGS, estimate_chsh
from qkdsim.analysis.theory import chsh_werner
from qkdsim.config import (
    AttackConfig,
    BasisMode,
    ChannelConfig,
    E91Config,
    SessionConfig,
)
from qkdsim.protocols.e91 import sift_e91
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_e91

pytestmark = pytest.mark.statistical


def _within_binomial(observed: float, mean: float, n: int) -> None:
    """Allow four analytic standard deviations of a Bernoulli rate."""
    assert abs(observed - mean) <= 4 * math.sqrt(mean * (1 - mean) / n)


@pytest.mark.parametrize("backend", ["fast", "qiskit"])
@pytest.mark.parametrize("visibility", [0.6, 0.8, 0.9, 1.0])
def test_werner_correlations_and_qber(backend: str, visibility: float) -> None:
    cfg = SessionConfig(
        channel=ChannelConfig(e_misalign=0),
        e91=E91Config(n_pairs=45_000, visibility=visibility, backend=backend),
    )
    observed, _ = simulate_e91(cfg, SimRNG(cfg.seed).generator)
    stats = estimate_chsh(observed)
    expected = chsh_werner(visibility)
    assert stats.s is not None and stats.standard_error is not None
    # The four group means are independent conditional on the setting counts.
    sigma = math.sqrt(sum((1 - visibility**2 / 2) / n for n in stats.counts))
    assert abs(stats.s - expected) <= 4 * sigma
    for (_, _, sign), correlation, n in zip(
        CHSH_SETTINGS, stats.correlations, stats.counts, strict=True
    ):
        assert correlation is not None
        _within_binomial(
            (1 - correlation) / 2, (1 - sign * visibility / math.sqrt(2)) / 2, n
        )
    sifted = sift_e91(observed)
    _within_binomial(sifted.sifted / sifted.detected, 2 / 9, sifted.detected)
    _within_binomial(sum(stats.counts) / sifted.detected, 4 / 9, sifted.detected)
    qber = float(np.mean(sifted.alice_bits != sifted.bob_bits))
    _within_binomial(qber, (1 - visibility) / 2, sifted.sifted)


@pytest.mark.parametrize("backend", ["fast", "qiskit"])
@pytest.mark.parametrize(
    ("mode", "key_qber"), [("random", 0.25), ("fixed_z", 0.375), ("fixed_x", 0.125)]
)
def test_full_intercept_resend(backend: str, mode: BasisMode, key_qber: float) -> None:
    cfg = SessionConfig(
        channel=ChannelConfig(e_misalign=0),
        e91=E91Config(n_pairs=45_000, backend=backend),
        attack=AttackConfig(kind="ir", basis_mode=mode),
    )
    observed, truth = simulate_e91(cfg, SimRNG(cfg.seed).generator)
    assert truth.eve_intercepted_mask.all()
    stats = estimate_chsh(observed)
    assert stats.s is not None and stats.standard_error is not None
    assert stats.s <= 2
    assert abs(stats.s - math.sqrt(2)) <= 4 * stats.standard_error
    sifted = sift_e91(observed)
    qber = float(np.mean(sifted.alice_bits != sifted.bob_bits))
    _within_binomial(qber, key_qber, sifted.sifted)
    # A fixed X Eve and Bob both measuring X must get the same eigenvalue.
    if mode == "fixed_x":
        in_x = observed.bob_settings == 1
        np.testing.assert_array_equal(observed.bob_bits[in_x], truth.eve_bit[in_x])


@pytest.mark.parametrize("backend", ["fast", "qiskit"])
def test_partial_eve_with_channel_noise_and_loss(backend: str) -> None:
    cfg = SessionConfig(
        channel=ChannelConfig(
            length_km=5, eta_det=0.8, e_misalign=0.01, depol=0.1, bitflip=0.02
        ),
        e91=E91Config(n_pairs=80_000, visibility=0.9, backend=backend),
        attack=AttackConfig(kind="ir", p=0.4),
    )
    observed, _ = simulate_e91(cfg, SimRNG(cfg.seed).generator)
    sifted = sift_e91(observed)
    efficiency = (10 ** (-0.1) * 0.8) ** 2
    _within_binomial(sifted.detected / sifted.sent, efficiency, sifted.sent)
    # Uniform Z/X interception contracts XZ correlations by 1 - p/2.
    scale = 0.9 * (1 - 0.4 / 2) * (1 - 0.1) * (1 - 2 * 0.02) * (1 - 2 * 0.01)
    stats = estimate_chsh(observed)
    assert stats.s is not None
    sigma = math.sqrt(sum((1 - scale**2 / 2) / n for n in stats.counts))
    assert abs(stats.s - 2 * math.sqrt(2) * scale) <= 4 * sigma
    qber = float(np.mean(sifted.alice_bits != sifted.bob_bits))
    _within_binomial(qber, (1 - scale) / 2, sifted.sifted)

    dark = replace(cfg, channel=replace(cfg.channel, eta_det=0, p_dark=1))
    observed, _ = simulate_e91(dark, SimRNG(dark.seed).generator)
    sifted = sift_e91(observed)
    assert sifted.detected == sifted.sent
    _within_binomial(
        float(np.mean(sifted.alice_bits != sifted.bob_bits)), 0.5, sifted.sifted
    )

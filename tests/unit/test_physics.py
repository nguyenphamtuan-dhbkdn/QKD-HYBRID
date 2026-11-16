"""Analytic oracles for pulse generation, measurement, loss, and Eve."""

import math

import numpy as np
import pytest

from qkdsim.attacks.intercept_resend import InterceptResend
from qkdsim.config import AttackConfig, ChannelConfig, SourceConfig
from qkdsim.physics.channel import (
    NoiseModel,
    attenuate,
    channel_qber,
    noise_parameter,
    noise_qber,
    transmittance,
)
from qkdsim.physics.detector import detect
from qkdsim.physics.source import photon_counts
from qkdsim.physics.states import PulseStates, measurement_p_one, sample_bases
from qkdsim.rng import SimRNG


@pytest.mark.parametrize(
    ("mode", "parameter", "qber"),
    [
        ("bitflip", 0.2, 0.2),
        ("depolarizing", 0.4, 0.2),
        ("misalignment", math.pi / 6, 0.25),
    ],
)
def test_noise_model_conversions(
    mode: NoiseModel, parameter: float, qber: float
) -> None:
    assert noise_qber(mode, parameter) == pytest.approx(qber)
    assert noise_parameter(mode, qber) == pytest.approx(parameter)


def test_channel_losses_and_error_composition() -> None:
    assert transmittance(50, 0.2) == pytest.approx(0.1)
    assert transmittance(0, 0.2) == 1
    config = ChannelConfig(bitflip=0.2, depol=0.4, e_misalign=0.9, misalignment_theta=0)
    assert channel_qber(config) == pytest.approx(0.32)
    with pytest.raises(ValueError, match="length_km"):
        transmittance(-1, 0.2)
    with pytest.raises(ValueError, match="alpha"):
        transmittance(1, math.inf)
    with pytest.raises(ValueError, match="parameter"):
        noise_qber("bitflip", 2)
    with pytest.raises(ValueError, match="QBER"):
        noise_parameter("depolarizing", 0.6)


def test_preparation_and_basis_measurement() -> None:
    rng = SimRNG(10).generator
    np.testing.assert_array_equal(sample_bases(3, 1, rng), [0, 0, 0])
    np.testing.assert_array_equal(sample_bases(3, 0, rng), [1, 1, 1])
    prepared = PulseStates(
        np.array([0, 1, 1], dtype=np.uint8),
        np.array([0, 1, 0], dtype=np.uint8),
        np.array([1, 1, 3], dtype=np.int64),
    )
    bases = np.array([0, 1, 1], dtype=np.uint8)
    np.testing.assert_array_equal(
        measurement_p_one(prepared, bases, 0.1), [0.1, 0.9, 0.5]
    )
    losses = attenuate(prepared, ChannelConfig(length_km=1e6), rng)
    np.testing.assert_array_equal(losses.photons, [0, 0, 0])
    np.testing.assert_array_equal(prepared.photons, [1, 1, 3])


def test_source_models() -> None:
    rng = SimRNG(77).generator
    np.testing.assert_array_equal(photon_counts(3, SourceConfig(), rng), [1, 1, 1])
    vacuum = SourceConfig(kind="weak_coherent", mu=0)
    np.testing.assert_array_equal(photon_counts(3, vacuum, rng), [0, 0, 0])
    with pytest.raises(ValueError, match="mu is required"):
        SourceConfig(kind="weak_coherent")


@pytest.mark.statistical
def test_weak_coherent_mean_over_seeded_poisson_samples() -> None:
    mu = 0.4
    size = 30_000
    counts = photon_counts(
        size, SourceConfig("weak_coherent", mu), SimRNG(34).generator
    )
    assert abs(float(counts.mean()) - mu) <= 4 * math.sqrt(mu / size)


def test_detector_zero_efficiency_and_threshold_clicks() -> None:
    photons = np.array([0, 1, 3], dtype=np.int64)
    p_one = np.array([0.5, 0.0, 1.0])
    rng = SimRNG(112).generator
    for efficiency in (0.0, 1.0):
        observed = detect(photons, p_one, ChannelConfig(eta_det=efficiency), rng)
        np.testing.assert_array_equal(observed.mask, [0, efficiency, efficiency])
        np.testing.assert_array_equal(observed.bits, [0, 0, efficiency])
        assert observed.double_clicks == 0


@pytest.mark.statistical
@pytest.mark.parametrize("photon_count", [0, 1])
def test_dark_clicks_and_squashing(photon_count: int) -> None:
    size = 30_000
    photons = np.full(size, photon_count, dtype=np.int64)
    p_one = np.zeros(size)
    observed = detect(photons, p_one, ChannelConfig(p_dark=1), SimRNG(23).generator)
    assert observed.mask.all()
    # Without photons the output is fair. A Z=0 signal gets a double click
    # on half the gates, and half of those doubles squash to a one.
    p_bit = 0.25 if photon_count else 0.5
    assert abs(float(observed.bits.mean()) - p_bit) <= 4 * math.sqrt(
        p_bit * (1 - p_bit) / size
    )
    p_double = 0.5 if photon_count else 0.0
    assert abs(observed.double_clicks / size - p_double) <= 4 * math.sqrt(
        p_double * (1 - p_double) / size
    )


def test_eve_resends_one_photon_and_keeps_truth_separate() -> None:
    states = PulseStates(
        np.array([1, 0, 1], dtype=np.uint8),
        np.array([0, 0, 0], dtype=np.uint8),
        np.array([1, 3, 0], dtype=np.int64),
    )
    rng = SimRNG(32).generator
    config = AttackConfig(kind="ir", basis_mode="fixed_Z")
    assert config.p == 1
    forwarded, truth = InterceptResend(config.p, config.basis_mode).apply(states, rng)
    np.testing.assert_array_equal(truth.eve_intercepted_mask, [True, True, False])
    np.testing.assert_array_equal(truth.eve_basis, [0, 0, 0])
    np.testing.assert_array_equal(truth.eve_bit, [1, 0, 0])
    np.testing.assert_array_equal(forwarded.photons, [1, 1, 0])
    np.testing.assert_array_equal(forwarded.bits, states.bits)
    np.testing.assert_array_equal(states.photons, [1, 3, 0])

    unchanged, no_intercepts = InterceptResend(p=0).apply(states, rng)
    assert not no_intercepts.eve_intercepted_mask.any()
    np.testing.assert_array_equal(unchanged.photons, states.photons)
    assert AttackConfig(kind="ir", basis_mode="fixed_X").basis_mode == "fixed_x"

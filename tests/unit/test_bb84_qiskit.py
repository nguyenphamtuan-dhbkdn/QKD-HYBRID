"""Check deterministic Clifford operations and detector edge cases."""

import math

import numpy as np
import pytest

from qkdsim.config import (
    AttackConfig,
    BB84Config,
    ChannelConfig,
    SessionConfig,
    SourceConfig,
)
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_bb84


@pytest.mark.parametrize("p_z", [0.0, 1.0])
@pytest.mark.parametrize(
    ("channel", "flipped"),
    [
        (ChannelConfig(e_misalign=0, bitflip=1), 1),
        (ChannelConfig(e_misalign=0, misalignment_theta=math.pi / 2), 1),
        (ChannelConfig(e_misalign=0, bitflip=1, misalignment_theta=math.pi / 2), 0),
    ],
)
def test_clifford_noise_in_both_bases(
    p_z: float, channel: ChannelConfig, flipped: int
) -> None:
    config = SessionConfig(
        bb84=BB84Config(n_pulses=64, p_z=p_z, backend="qiskit"), channel=channel
    )
    observed, _ = simulate_bb84(config, SimRNG(config.seed).generator)
    np.testing.assert_array_equal(observed.bob_bits, observed.alice_bits ^ flipped)


@pytest.mark.parametrize("efficiency", [0.0, 1.0])
def test_eve_resends_her_measured_state(efficiency: float) -> None:
    config = SessionConfig(
        bb84=BB84Config(n_pulses=64, backend="qiskit"),
        attack=AttackConfig(kind="ir", basis_mode="fixed_x"),
        channel=ChannelConfig(e_misalign=0, eta_det=efficiency),
    )
    observed, truth = simulate_bb84(config, SimRNG(config.seed).generator)
    repeat, repeat_truth = simulate_bb84(config, SimRNG(config.seed).generator)
    assert truth.eve_intercepted_mask.all()
    assert (truth.eve_basis == 1).all()
    assert (observed.detected_mask == bool(efficiency)).all()
    alice_matches = observed.alice_bases == truth.eve_basis
    bob_matches = (observed.bob_bases == truth.eve_basis) & observed.detected_mask
    np.testing.assert_array_equal(
        truth.eve_bit[alice_matches], observed.alice_bits[alice_matches]
    )
    np.testing.assert_array_equal(
        truth.eve_bit[bob_matches], observed.bob_bits[bob_matches]
    )
    np.testing.assert_array_equal(truth.eve_bit, repeat_truth.eve_bit)
    np.testing.assert_array_equal(observed.bob_bits, repeat.bob_bits)


def test_partial_intercept_is_measured_before_channel_noise() -> None:
    config = SessionConfig(
        bb84=BB84Config(n_pulses=64, p_z=1, backend="qiskit"),
        attack=AttackConfig(kind="ir", p=0.5, basis_mode="fixed_z"),
        channel=ChannelConfig(e_misalign=0, bitflip=1),
    )
    observed, truth = simulate_bb84(config, SimRNG(config.seed).generator)
    intercepted = truth.eve_intercepted_mask
    assert intercepted.any() and not intercepted.all()
    np.testing.assert_array_equal(
        truth.eve_bit, np.where(intercepted, observed.alice_bits, 0)
    )
    np.testing.assert_array_equal(observed.bob_bits, observed.alice_bits ^ 1)


def test_vacuum_pulses_can_trigger_dark_counts() -> None:
    config = SessionConfig(
        bb84=BB84Config(n_pulses=64, backend="qiskit"),
        source=SourceConfig(kind="weak_coherent", mu=0),
        channel=ChannelConfig(p_dark=1),
        attack=AttackConfig(kind="ir"),
    )
    observed, truth = simulate_bb84(config, SimRNG(config.seed).generator)
    assert observed.detected_mask.all()
    assert observed.double_clicks == 0
    assert not truth.eve_intercepted_mask.any()

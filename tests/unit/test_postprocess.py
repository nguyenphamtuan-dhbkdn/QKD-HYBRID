"""Verify public sampling, threshold decisions, and discarding revealed bits."""

import math

import numpy as np
import pytest

from qkdsim.config import BB84Config
from qkdsim.postprocess.estimation import (
    ParameterAbort,
    ParameterEstimate,
    estimate_parameters,
    hoeffding_upper,
)
from qkdsim.postprocess.sifting import SiftedKey, sift
from qkdsim.protocols.bb84 import BB84Transmission
from qkdsim.rng import SimRNG


def test_sift_keeps_only_detected_matching_bases_in_pulse_order() -> None:
    transmission = BB84Transmission(
        np.array([1, 0, 0, 1], dtype=np.uint8),
        np.array([0, 0, 1, 1], dtype=np.uint8),
        np.array([0, 1, 1, 1], dtype=np.uint8),
        np.array([0, 0, 1, 1], dtype=np.uint8),
        np.array([True, True, False, True]),
        0,
    )
    key = sift(transmission)
    assert (key.sent, key.detected, key.sifted) == (4, 3, 2)
    np.testing.assert_array_equal(key.pulse_indices, [0, 3])
    np.testing.assert_array_equal(key.alice_bits, [1, 1])
    np.testing.assert_array_equal(key.bob_bits, [0, 1])
    assert "array" not in repr(key)
    assert "array" not in repr(transmission)


def make_key(*, flipped: bool = False) -> SiftedKey:
    alice = SimRNG(3).generator.integers(0, 2, size=100, dtype=np.uint8)
    return SiftedKey(
        alice, 1 - alice if flipped else alice.copy(), np.arange(0, 200, 2), 200, 100
    )


def test_parameter_estimation_discards_sample_without_replacement() -> None:
    key = make_key()
    config = BB84Config(test_fraction=0.07, k_min=7, eps_pe=0.2, q_max=0.5)
    result = estimate_parameters(key, config, SimRNG(6).generator)
    assert isinstance(result, ParameterEstimate)
    assert result.stats.sample_size == 7
    sample = result.stats.sample_indices
    assert np.unique(sample).size == 7
    assert np.isin(sample, key.pulse_indices).all()
    keep = ~np.isin(key.pulse_indices, sample)
    np.testing.assert_array_equal(result.alice_remaining, key.alice_bits[keep])
    np.testing.assert_array_equal(result.bob_remaining, key.bob_bits[keep])
    assert result.stats.errors == result.stats.q_est == 0
    assert result.stats.q_ub == pytest.approx(math.sqrt(math.log(5) / 14))
    assert "array" not in repr(result)


def test_insufficient_sample_aborts_before_sampling() -> None:
    config = BB84Config(test_fraction=0.2)
    result = estimate_parameters(make_key(), config, SimRNG(54).generator)
    assert result == ParameterAbort("insufficient statistics", 20)


def test_zero_sifted_bits_abort() -> None:
    empty = np.array([], dtype=np.uint8)
    key = SiftedKey(empty, empty, np.array([], dtype=np.int64), 10, 0)
    assert estimate_parameters(
        key, BB84Config(), SimRNG(1).generator
    ) == ParameterAbort("insufficient statistics", 0)


def test_hoeffding_abort_and_threshold_equality() -> None:
    config = BB84Config(test_fraction=0.5, k_min=1)
    result = estimate_parameters(make_key(flipped=True), config, SimRNG(7).generator)
    assert isinstance(result, ParameterAbort)
    assert result.reason == "qber above threshold"
    assert result.stats is not None
    assert result.stats.q_est == result.stats.q_ub == 1

    bound = hoeffding_upper(0, 50, config.eps_pe)
    exact_limit = BB84Config(test_fraction=0.5, k_min=1, q_max=bound)
    assert isinstance(
        estimate_parameters(make_key(), exact_limit, SimRNG(7).generator),
        ParameterEstimate,
    )


@pytest.mark.parametrize(
    ("errors", "size", "epsilon"), [(0, 0, 0.1), (7, 5, 0.1), (0, 5, 1)]
)
def test_hoeffding_rejects_out_of_domain_parameters(
    errors: int, size: int, epsilon: float
) -> None:
    with pytest.raises(ValueError):
        hoeffding_upper(errors, size, epsilon)

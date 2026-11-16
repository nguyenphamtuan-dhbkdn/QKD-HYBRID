"""Check theory and statistics against analytic benchmarks."""

import math

import numpy as np
import pytest
from numpy.random import Generator

from qkdsim.analysis.stats import (
    binomial_test,
    bootstrap_mean_interval,
    clopper_pearson,
    monte_carlo,
    wilson_interval,
)
from qkdsim.analysis.theory import (
    asymptotic_key_fraction,
    chsh_werner,
    grover_effective_bits,
    h2,
    p_detect_ir,
    qber_ir,
    qber_threshold_bb84,
    visibility_threshold_chsh,
)
from qkdsim.rng import SimRNG


def test_intercept_resend_oracles() -> None:
    assert qber_ir(1) == 0.25
    assert qber_ir(0.5) == 0.125
    assert qber_ir(0.5, 0.1) == pytest.approx(0.20)
    assert qber_ir(1, p_z=0.75, basis_mode="fixed_z") == pytest.approx(0.05)
    assert qber_ir(1, p_z=0.75, basis_mode="fixed_x") == pytest.approx(0.45)
    assert p_detect_ir(10) == pytest.approx(1 - 0.75**10)
    assert p_detect_ir(10, 0.5) == pytest.approx(1 - 0.875**10)
    assert p_detect_ir(0) == 0
    assert p_detect_ir(100, 0) == 0


def test_other_analytic_oracles() -> None:
    assert h2(0) == h2(1) == 0
    assert h2(0.5) == 1
    assert h2(0.25) == pytest.approx(h2(0.75))
    assert asymptotic_key_fraction(0) == 1
    assert asymptotic_key_fraction(0.5, f_ec=1.2) == pytest.approx(-1.2)
    assert qber_threshold_bb84() == pytest.approx(0.1100278644)
    assert chsh_werner(1) == pytest.approx(2 * math.sqrt(2))
    assert chsh_werner(visibility_threshold_chsh()) == pytest.approx(2)
    assert grover_effective_bits(256) == 128


def test_theory_input_domains() -> None:
    for evaluate in (qber_ir, p_detect_ir, chsh_werner, h2, grover_effective_bits):
        with pytest.raises(ValueError):
            evaluate(-1)
    with pytest.raises(ValueError):
        asymptotic_key_fraction(0.1, f_ec=0.5)


def test_binomial_intervals_at_bounds_and_center() -> None:
    assert clopper_pearson(0, 5) == pytest.approx((0, 1 - 0.025**0.2))
    assert clopper_pearson(5, 5) == pytest.approx((0.025**0.2, 1))
    assert clopper_pearson(5, 10) == pytest.approx((0.187086, 0.812914), abs=1e-6)
    lower, upper = wilson_interval(5, 10)
    assert (lower, upper) == pytest.approx((0.236593, 0.763407), abs=1e-6)
    assert wilson_interval(0, 5)[0] == 0
    assert wilson_interval(5, 5)[1] == 1
    assert binomial_test(0, 5, 0.5) == 2 / 2**5
    assert binomial_test(2, 4, 0.5) == 1


def test_statistics_input_domains() -> None:
    rng = SimRNG(21).generator
    with pytest.raises(ValueError, match="confidence"):
        wilson_interval(0, 3, 1.0)
    with pytest.raises(ValueError, match="trials"):
        clopper_pearson(1, 0)
    with pytest.raises(ValueError, match="probability"):
        binomial_test(1, 2, 2)
    with pytest.raises(ValueError, match="sample"):
        bootstrap_mean_interval([float("nan")], rng)
    with pytest.raises(ValueError, match="repetitions"):
        bootstrap_mean_interval([1], rng, repetitions=1)
    with pytest.raises(ValueError, match="repetitions"):
        monte_carlo(lambda rng: 0.0, seed=1, repetitions=1)
    with pytest.raises(ValueError, match="nonfinite"):
        monte_carlo(lambda rng: math.inf, seed=1, repetitions=2)


def test_bootstrap_and_monte_carlo_use_seeded_generators() -> None:
    assert bootstrap_mean_interval([3, 3, 3], SimRNG(2).generator) == (3.0, 3.0)

    def draw(rng: Generator) -> float:
        return float(rng.random())

    summary = monte_carlo(draw, seed=2, repetitions=16)
    repeat = monte_carlo(draw, seed=2, repetitions=16)
    np.testing.assert_array_equal(summary.samples, repeat.samples)
    assert np.unique(summary.samples).size == 16
    assert summary.mean == repeat.mean
    assert summary.interval == repeat.interval
    assert summary.interval[0] < summary.mean < summary.interval[1]

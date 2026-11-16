import math

import numpy as np
import pytest

from qkdsim.analysis.randomness import (
    analyze_randomness,
    approximate_entropy_test,
    block_frequency_test,
    frequency_test,
    longest_run_test,
    min_entropy,
    runs_test,
)


def test_nist_worked_examples() -> None:
    # SP 800-22 Rev. 1a, Sections 2.1.8, 2.2.8, 2.3.8 and 2.12.8.
    bits = np.fromiter(
        map(
            int,
            "11001001000011111101101010100010001000010110100011"
            "00001000110100110001001100011001100010100010111000",
        ),
        dtype=np.uint8,
    )
    assert frequency_test(bits) == pytest.approx(0.109599, abs=1e-6)
    assert block_frequency_test(bits, 10) == pytest.approx(0.706438, abs=1e-6)
    assert runs_test(bits) == pytest.approx(0.500798, abs=1e-6)
    assert approximate_entropy_test(bits, 2) == pytest.approx(0.235301, abs=1e-6)
    assert min_entropy(bits) == pytest.approx(-math.log2(0.58))


def test_nist_longest_run_worked_example() -> None:
    bits = np.fromiter(
        map(
            int,
            "11001100000101010110110001001100111000000000001001"
            "00110101010001000100111101011010000000110101111100"
            "1100111001101101100010110010",
        ),
        dtype=np.uint8,
    )
    # Use the Section 2.4.4 calculation with the published rounded probabilities.
    assert longest_run_test(bits) == pytest.approx(0.180598, abs=1e-6)


def test_independent_bits_and_constant_bits() -> None:
    random = np.random.default_rng(1234).integers(0, 2, 16_384, dtype=np.uint8)
    report = analyze_randomness(random)
    assert report.bit_count == random.size
    assert all(p is not None and 0.01 <= p <= 1 for p in report.p_values.values())
    assert report.min_entropy > 0.98

    constant = analyze_randomness(np.zeros(16_384, dtype=np.uint8))
    assert all(p is not None and 0 <= p < 0.01 for p in constant.p_values.values())
    assert constant.min_entropy == 0


def test_balanced_sequence_with_serial_dependence() -> None:
    bits = np.tile(np.array([0, 1], dtype=np.uint8), 4_096)
    report = analyze_randomness(bits)
    assert report.p_values["frequency"] == 1
    assert report.min_entropy == 1
    for test_name in ("runs", "longest_run", "approximate_entropy"):
        p_value = report.p_values[test_name]
        assert p_value is not None and p_value < 0.01


def test_longest_run_large_block_size_catches_clustering() -> None:
    assert longest_run_test(np.ones(750_000, dtype=np.uint8)) < 0.01


def test_too_short_or_invalid_inputs() -> None:
    short = np.array([0, 1], dtype=np.uint8)
    assert all(p is None for p in analyze_randomness(short).p_values.values())
    with pytest.raises(ValueError, match="128 bits"):
        longest_run_test(short)
    with pytest.raises(ValueError, match="block_size"):
        block_frequency_test(short, 3)
    with pytest.raises(ValueError, match="pattern_size"):
        approximate_entropy_test(short)
    with pytest.raises(ValueError, match="uint8 array of bits"):
        analyze_randomness(np.array([2], dtype=np.uint8))
    with pytest.raises(ValueError, match="nonempty"):
        analyze_randomness(np.empty(0, dtype=np.uint8))

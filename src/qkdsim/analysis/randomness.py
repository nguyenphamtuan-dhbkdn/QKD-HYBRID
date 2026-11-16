"""Bit-string diagnostics based on NIST SP 800-22 Rev. 1a, sections 2.1–2.4/2.12."""

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import gammaincc  # type: ignore[import-untyped]

from qkdsim.physics.states import BitArray
from qkdsim.postprocess._bits import validate_bits


def _nonempty(bits: BitArray) -> None:
    validate_bits(bits)
    if not bits.size:
        raise ValueError("bit string must be nonempty")


def frequency_test(bits: BitArray) -> float:
    """Monobit p-value erfc(|2*n_ones - n| / sqrt(2*n))."""
    _nonempty(bits)
    imbalance = abs(2 * np.count_nonzero(bits) - bits.size)
    return math.erfc(imbalance / math.sqrt(2 * bits.size))


def block_frequency_test(bits: BitArray, block_size: int) -> float:
    """Use chi-square with N degrees of freedom on 4*M*sum((p_i-1/2)**2)."""
    _nonempty(bits)
    if type(block_size) is not int or not 1 <= block_size <= bits.size:
        raise ValueError("block_size must be a positive integer at most the bit count")
    n_blocks = bits.size // block_size
    blocks = bits[: n_blocks * block_size].reshape(n_blocks, block_size)
    chi_square = 4 * block_size * np.sum((blocks.mean(axis=1) - 0.5) ** 2)
    return float(gammaincc(n_blocks / 2, chi_square / 2))


def runs_test(bits: BitArray) -> float:
    """Use erfc(|runs - 2*n*p*(1-p)| / (2*sqrt(2*n)*p*(1-p))).

    Following SP 800-22, return zero if |p - 1/2| >= 2/sqrt(n).
    Constant sequences also return zero, including for very short inputs.
    """
    _nonempty(bits)
    n = bits.size
    p = np.count_nonzero(bits) / n
    if p in (0, 1) or abs(p - 0.5) >= 2 / math.sqrt(n):
        return 0.0
    runs = 1 + np.count_nonzero(bits[1:] != bits[:-1])
    pq = p * (1 - p)
    return math.erfc(abs(runs - 2 * n * pq) / (2 * math.sqrt(2 * n) * pq))


def longest_run_test(bits: BitArray) -> float:
    """Compare blockwise longest runs of ones against NIST's chi-square bins."""
    _nonempty(bits)
    n = bits.size
    if n < 128:
        raise ValueError("longest run test requires at least 128 bits")
    probabilities: tuple[float, ...]
    if n < 6_272:
        width, first = 8, 1
        probabilities = (0.2148, 0.3672, 0.2305, 0.1875)
    elif n < 750_000:
        width, first = 128, 4
        probabilities = (0.1174, 0.2430, 0.2493, 0.1752, 0.1027, 0.1124)
    else:
        width, first = 10_000, 10
        probabilities = (0.0882, 0.2092, 0.2483, 0.1933, 0.1208, 0.0675, 0.0727)
    n_blocks = n // width
    blocks = bits[: n_blocks * width].reshape(n_blocks, width)
    positions = np.arange(1, width + 1)
    last_zero = np.maximum.accumulate(np.where(blocks == 0, positions, 0), axis=1)
    longest = np.max(positions - last_zero, axis=1)
    categories = len(probabilities)
    observed = np.bincount(
        np.clip(longest - first, 0, categories - 1), minlength=categories
    )
    expected = n_blocks * np.asarray(probabilities)
    chi_square = np.sum((observed - expected) ** 2 / expected)
    return float(gammaincc((categories - 1) / 2, chi_square / 2))


def approximate_entropy_test(bits: BitArray, pattern_size: int = 2) -> float:
    """Use chi-square 2*n*(ln(2) - (phi_m - phi_(m+1))) on circular patterns.

    phi_m = sum(p(word)*ln(p(word))). Use 2**m degrees of freedom. The
    caller needs a sufficiently long sequence for the chi-square approximation.
    """
    _nonempty(bits)
    n = bits.size
    if type(pattern_size) is not int or not 1 <= pattern_size < n.bit_length() - 1:
        raise ValueError("pattern_size must be positive with 2**(pattern_size+1) <= n")
    circular = np.concatenate((bits, bits[:pattern_size]))
    words = np.zeros(n, dtype=np.intp)
    for offset in range(pattern_size + 1):
        words <<= 1
        words |= circular[offset : offset + n]
    counts = np.bincount(words, minlength=1 << (pattern_size + 1))
    shorter_counts = counts.reshape(-1, 2).sum(axis=1)
    longer = counts[counts > 0] / n
    shorter = shorter_counts[shorter_counts > 0] / n
    ap_en = np.dot(shorter, np.log(shorter)) - np.dot(longer, np.log(longer))
    chi_square = max(0.0, 2 * n * (math.log(2) - ap_en))
    return float(gammaincc(2 ** (pattern_size - 1), chi_square / 2))


def min_entropy(bits: BitArray) -> float:
    """Estimate marginal entropy -log2(max(n_ones, n_zeros) / n) per bit."""
    _nonempty(bits)
    ones = np.count_nonzero(bits)
    return -math.log2(max(ones, bits.size - ones) / bits.size)


@dataclass(frozen=True)
class RandomnessReport:
    """Per-test p-values (None for short inputs) and a marginal entropy estimate."""

    bit_count: int
    p_values: dict[str, float | None]
    min_entropy: float


def analyze_randomness(bits: BitArray) -> RandomnessReport:
    """Run the subset using NIST's input-size guidance and pattern length m=2."""
    entropy = min_entropy(bits)
    n = bits.size
    block_size = max(20, n // 100 + 1)
    return RandomnessReport(
        n,
        {
            "frequency": frequency_test(bits) if n >= 100 else None,
            "block_frequency": block_frequency_test(bits, block_size)
            if n >= 100
            else None,
            "runs": runs_test(bits) if n >= 100 else None,
            "longest_run": longest_run_test(bits) if n >= 128 else None,
            "approximate_entropy": approximate_entropy_test(bits) if n >= 256 else None,
        },
        entropy,
    )

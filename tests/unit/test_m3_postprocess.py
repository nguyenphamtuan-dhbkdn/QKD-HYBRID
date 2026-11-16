"""Analytic and property-based checks for the BB84 key pipeline."""

import math
from collections.abc import Iterator
from copy import deepcopy

import numpy as np
import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from qkdsim.physics.states import BitArray, CountArray
from qkdsim.postprocess.cascade import cascade_reconcile, perfect_ec
from qkdsim.postprocess.keylength import asymptotic_key_length, secret_key_length
from qkdsim.postprocess.privacy_amp import (
    random_toeplitz_seed,
    toeplitz_hash_fft,
    toeplitz_hash_reference,
)
from qkdsim.postprocess.verification import (
    verification_collision_bound,
    verification_tag,
    verify_keys,
)
from qkdsim.rng import SimRNG


class FixedPermutations:
    """Supply known permutations to exercise Cascade's parity worklist."""

    def __init__(self, orders: Iterator[CountArray]) -> None:
        self.orders = orders

    def permutation(self, n: int) -> CountArray:
        order = next(self.orders)
        assert order.size == n
        return order


def test_cascade_back_reopens_blocks_and_reuses_disclosed_parities() -> None:
    alice = np.zeros(12, dtype=np.uint8)
    bob = alice.copy()
    bob[[0, 1, 3, 4]] = 1
    rng = FixedPermutations(
        iter((np.arange(12), np.array([0, 1, 3, 2, 5, 6, 4, 7, 8, 9, 10, 11])))
    )
    result = cascade_reconcile(alice, bob, 0.25, rng, passes=2)
    np.testing.assert_array_equal(result.key_b_corrected, alice)
    np.testing.assert_array_equal(np.flatnonzero(bob), [0, 1, 3, 4])
    # 4 + 2 initial blocks, then BINARY costs of 2, 2, 3 and 2 bits.
    assert result.passes == 2
    assert result.leak_bits == result.parities_disclosed == 15
    assert "array" not in repr(result)


def test_cascade_handles_empty_input_and_zero_error_estimate() -> None:
    rng = SimRNG(47).generator
    alice = np.zeros(200, dtype=np.uint8)
    bob = alice.copy()
    bob[169] = 1
    result = cascade_reconcile(alice, bob, 0, rng)
    np.testing.assert_array_equal(result.key_b_corrected, alice)
    assert result.f_ec is None
    empty = cascade_reconcile(alice[:0], bob[:0], 0, rng)
    assert empty.leak_bits == empty.passes == empty.key_b_corrected.size == 0


@settings(derandomize=True, deadline=None, max_examples=80)
@given(st.integers(0, 2**32 - 1), st.integers(1, 10))
@example(seed=1_531_366_848, percentage=2)
def test_cascade_resolves_odd_parities_without_introducing_errors(
    seed: int, percentage: int
) -> None:
    rng = SimRNG(seed).generator
    n = 8192
    errors = n * percentage // 100
    alice = rng.integers(0, 2, size=n, dtype=np.uint8)
    bob = alice.copy()
    bob[rng.choice(n, errors, replace=False)] ^= 1
    replay = deepcopy(rng)
    qber = errors / n
    result = cascade_reconcile(alice, bob, qber, rng)
    remaining = result.key_b_corrected ^ alice
    assert np.all(remaining <= (bob ^ alice))
    block_size = math.ceil(0.73 / qber)
    for _ in range(result.passes):
        shuffled = remaining[replay.permutation(n)]
        parity = np.bitwise_xor.reduceat(shuffled, np.arange(0, n, block_size))
        assert not parity.any()
        block_size *= 2


def test_cascade_can_leave_even_errors_for_verification() -> None:
    alice = np.zeros(20, dtype=np.uint8)
    bob = alice.copy()
    bob[[2, 3]] = 1
    rng = FixedPermutations(iter((np.arange(20),) * 4))
    result = cascade_reconcile(alice, bob, 0.1, rng)
    np.testing.assert_array_equal(result.key_b_corrected, bob)
    assert result.leak_bits == 7
    assert not verify_keys(alice, result.key_b_corrected).matches


def test_perfect_ec_rounds_leak_up() -> None:
    alice = np.zeros(10, dtype=np.uint8)
    result = perfect_ec(alice, 1 - alice, 0.5, 1.01)
    np.testing.assert_array_equal(result.key_b_corrected, alice)
    assert result.leak_bits == 11
    assert result.passes == result.parities_disclosed == 0


def test_polynomial_tag_formula_and_collision_bound() -> None:
    prime = (1 << 61) - 1
    packed = bytes.fromhex("123456789abcdeab")
    bits = np.unpackbits(np.frombuffer(packed, dtype=np.uint8))[:63]
    prefix, last = int.from_bytes(packed[:7], "big"), 0xAA
    seed = prime - 5
    assert (
        int.from_bytes(verification_tag(bits, seed), "big")
        == (prefix * seed + last) % prime
    )
    assert verification_collision_bound(56) == 0
    assert verification_collision_bound(57) == pytest.approx(1 / prime, abs=0)
    assert verification_collision_bound(113) == pytest.approx(2 / prime, abs=0)


def test_verification_draws_one_uniform_seed_for_both_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bounds: list[int] = []

    def randbelow(upper: int) -> int:
        bounds.append(upper)
        return 42

    monkeypatch.setattr("qkdsim.postprocess.verification.secrets.randbelow", randbelow)
    alice = np.zeros(313, dtype=np.uint8)
    passed = verify_keys(alice, alice.copy())
    assert passed.matches and passed.leak_bits == 64
    bob = alice.copy()
    bob[-1] = 1
    failed = verify_keys(alice, bob)
    assert not failed.matches and failed.leak_bits == 64
    assert bounds == [(1 << 61) - 1] * 2


def test_toeplitz_convolution_matches_known_matrix() -> None:
    bits = np.array([1, 1, 0], dtype=np.uint8)
    seed = np.array([1, 0, 1, 1, 0], dtype=np.uint8)
    # Rows [1,0,1], [1,1,0], [0,1,1].
    expected = [1, 0, 1]
    np.testing.assert_array_equal(toeplitz_hash_fft(bits, 3, seed), expected)
    np.testing.assert_array_equal(toeplitz_hash_reference(bits, 3, seed), expected)


def test_fft_matches_reference_in_1000_random_cases() -> None:
    rng = SimRNG(93).generator
    for _ in range(1000):
        n, length = map(int, rng.integers(1, 131, size=2))
        bits = rng.integers(0, 2, size=n, dtype=np.uint8)
        seed = rng.integers(0, 2, size=n + length - 1, dtype=np.uint8)
        expected = toeplitz_hash_reference(bits, length, seed)
        np.testing.assert_array_equal(toeplitz_hash_fft(bits, length, seed), expected)


@given(st.lists(st.integers(0, 1), min_size=1, max_size=128), st.integers(0, 128))
def test_toeplitz_output_length(data: list[int], length: int) -> None:
    bits = np.asarray(data, dtype=np.uint8)
    seed = np.ones(bits.size + length - 1, dtype=np.uint8)
    output = toeplitz_hash_fft(bits, length, seed)
    assert output.dtype == np.uint8 and output.shape == (length,)
    np.testing.assert_array_equal(output, np.full(length, sum(data) % 2))


@pytest.mark.statistical
def test_one_input_flip_changes_half_of_toeplitz_output() -> None:
    rng = SimRNG(73).generator
    n, length = 119, 4096
    bits = rng.integers(0, 2, size=n, dtype=np.uint8)
    seed = rng.integers(0, 2, size=n + length - 1, dtype=np.uint8)
    baseline = toeplitz_hash_fft(bits, length, seed)
    bit = 29
    bits[bit] ^= 1
    changed = baseline ^ toeplitz_hash_fft(bits, length, seed)
    # The difference is one column: independent Bernoulli(1/2) seed bits.
    np.testing.assert_array_equal(changed, seed[n - 1 - bit : n - 1 - bit + length])
    assert abs(np.mean(changed) - 0.5) <= 4 * math.sqrt(0.25 / length)


def test_toeplitz_seed_unpacks_os_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    def secure_random(size: int) -> bytes:
        assert size == 2
        return bytes.fromhex("a980")

    monkeypatch.setattr("qkdsim.postprocess.privacy_amp.secure_random", secure_random)
    np.testing.assert_array_equal(
        random_toeplitz_seed(4, 6), [1, 0, 1, 0, 1, 0, 0, 1, 1]
    )
    with pytest.raises(ValueError, match="positive"):
        random_toeplitz_seed(4, 0)


@pytest.mark.parametrize(
    "bad_bits", [np.array([2], dtype=np.uint8), np.zeros((1, 1), dtype=np.uint8)]
)
def test_bit_operations_reject_invalid_inputs(bad_bits: BitArray) -> None:
    key = np.zeros(1, dtype=np.uint8)
    with pytest.raises(ValueError, match="uint8 array of bits"):
        toeplitz_hash_fft(bad_bits, 1, key)
    with pytest.raises(ValueError, match="uint8 array of bits"):
        verify_keys(key, bad_bits)


def test_public_hash_arguments_are_checked() -> None:
    key = np.zeros(1, dtype=np.uint8)
    with pytest.raises(ValueError, match="lengths must match"):
        verify_keys(key, key[:0])
    with pytest.raises(ValueError, match="seed bits"):
        toeplitz_hash_fft(key, 2, key)
    with pytest.raises(ValueError, match="in the field"):
        verification_tag(key, -1)


def test_finite_key_length_subtracts_disclosures_and_privacy_penalty() -> None:
    eps_sec = 2**-10
    assert secret_key_length(1000, 0, 30, 64, eps_sec, 1e-12) == 886
    h_quarter = 2 / 4 - 0.75 * math.log2(0.75)
    assert secret_key_length(1000, 0.25, 30, 64, eps_sec, 1e-12) == math.floor(
        1000 * (1 - h_quarter) - 114
    )
    assert secret_key_length(114, 0, 30, 64, eps_sec, 1e-12) == 0
    assert secret_key_length(1000, 0.9, 30, 64, eps_sec, 1e-12) == -114
    assert asymptotic_key_length(1000, 0) == 1000
    assert asymptotic_key_length(1000, 0.5, 1.2) == pytest.approx(-1200)

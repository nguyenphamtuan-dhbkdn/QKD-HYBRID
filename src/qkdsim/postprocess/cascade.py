"""Cascade reconciliation and its idealized Shannon-limit counterpart."""

import heapq
import math
from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator

from qkdsim.analysis.theory import h2
from qkdsim.physics.states import BitArray, CountArray
from qkdsim.postprocess._bits import validate_key_pair


@dataclass(frozen=True, eq=False)
class CascadeResult:
    """Bob's corrected copy and public communication counts."""

    key_b_corrected: BitArray = field(repr=False)
    leak_bits: int
    passes: int
    parities_disclosed: int
    f_ec: float | None


@dataclass(frozen=True, eq=False)
class _Pass:
    order: CountArray
    positions: CountArray
    odd_blocks: BitArray
    differences: BitArray
    block_size: int

    def locate_error(self, block: int) -> tuple[int, int]:
        """Bisect a known odd block, disclosing one parity per split."""
        left = block * self.block_size
        right = min(left + self.block_size, self.differences.size)
        disclosed = 0
        while right - left > 1:
            mid = (left + right) // 2
            # Comparing the parties' parities is XOR over their differences.
            if np.bitwise_xor.reduce(self.differences[left:mid]):
                right = mid
            else:
                left = mid
            disclosed += 1
        return int(self.order[left]), disclosed


def cascade_reconcile(
    key_a: BitArray, key_b: BitArray, q_est: float, rng: Generator, *, passes: int = 4
) -> CascadeResult:
    """Reconcile using k_1=max(2,ceil(0.73/Q_est)) and k_i=2*k_(i-1).

    A zero estimate uses a 1% block-size estimate. Count an Alice parity
    for every block opened and every binary-search split. Cascade-back
    reuses the parity known for each opened block. Efficiency is
    leak_bits / (n * h2(Q_est)) when the denominator is positive.
    Verification is required after the configured passes.
    """
    validate_key_pair(key_a, key_b)
    if type(passes) is not int or passes < 1:
        raise ValueError("passes must be a positive integer")
    entropy_bits = key_a.size * h2(q_est)
    bob = key_b.copy()
    n = bob.size
    if n == 0:
        return CascadeResult(bob, 0, 0, 0, None)

    block_estimate = q_est or 0.01
    # Limit the size before dividing so even subnormal Q estimates are safe.
    block_size = min(n, max(2, math.ceil(0.73 / max(block_estimate, 0.73 / n))))
    differences = key_a ^ bob
    disclosed = 0
    opened: list[_Pass] = []

    for pass_index in range(passes):
        order = np.asarray(rng.permutation(n), dtype=np.int64)
        positions = np.empty_like(order)
        positions[order] = np.arange(n)
        starts = np.arange(0, n, block_size)
        shuffled = differences[order]
        odd = np.bitwise_xor.reduceat(shuffled, starts)
        opened.append(_Pass(order, positions, odd, shuffled, block_size))
        disclosed += starts.size

        # Prefer the smaller blocks of earlier passes during cascade-back.
        pending = [(pass_index, int(block)) for block in np.flatnonzero(odd)]
        while pending:
            index, block = heapq.heappop(pending)
            current = opened[index]
            if not current.odd_blocks[block]:
                continue
            bit, queries = current.locate_error(block)
            bob[bit] ^= 1
            differences[bit] ^= 1
            disclosed += queries
            for earlier_index, other in enumerate(opened):
                position = int(other.positions[bit])
                other.differences[position] ^= 1
                affected = position // other.block_size
                other.odd_blocks[affected] ^= 1
                if other.odd_blocks[affected]:
                    heapq.heappush(pending, (earlier_index, affected))

        block_size = min(n, 2 * block_size)

    return CascadeResult(
        bob,
        disclosed,
        passes,
        disclosed,
        disclosed / entropy_bits if entropy_bits else None,
    )


def perfect_ec(
    key_a: BitArray, key_b: BitArray, q_est: float, f_ec: float
) -> CascadeResult:
    """Model perfect reconciliation at ceil(n * h2(Q_est) * f_ec) leaked bits."""
    validate_key_pair(key_a, key_b)
    if not math.isfinite(f_ec) or f_ec < 1:
        raise ValueError("f_ec must be finite and >= 1")
    entropy_bits = key_a.size * h2(q_est)
    leak = math.ceil(entropy_bits * f_ec)
    return CascadeResult(
        key_a.copy(), leak, 0, 0, leak / entropy_bits if entropy_bits else None
    )

"""Validation shared by the bit-string operations."""

import numpy as np

from qkdsim.physics.states import BitArray


def validate_bits(bits: BitArray) -> None:
    """Require a flat uint8 array representing a string over GF(2)."""
    if bits.ndim != 1 or bits.dtype != np.uint8 or np.any(bits > 1):
        raise ValueError("expected a one-dimensional uint8 array of bits")


def validate_key_pair(key_a: BitArray, key_b: BitArray) -> None:
    """Require two valid bit strings with the same length."""
    validate_bits(key_a)
    validate_bits(key_b)
    if key_a.size != key_b.size:
        raise ValueError("key lengths must match")

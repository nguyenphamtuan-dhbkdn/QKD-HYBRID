"""Polynomial universal-hash confirmation of reconciled bit strings."""

import secrets
from dataclasses import dataclass

import numpy as np

from qkdsim.physics.states import BitArray
from qkdsim.postprocess._bits import validate_bits, validate_key_pair

_PRIME = (1 << 61) - 1
_COEFFICIENT_BYTES = 7
_TAG_BYTES = 8


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of the tag comparison and the disclosed tag length."""

    matches: bool
    leak_bits: int


def verification_collision_bound(n_bits: int) -> float:
    """Return min(1, degree/p), since a nonzero polynomial has <= degree roots."""
    if n_bits < 0:
        raise ValueError("key length must be nonnegative")
    degree = max(0, (n_bits - 1) // (8 * _COEFFICIENT_BYTES))
    return min(1.0, degree / _PRIME)


def verification_tag(bits: BitArray, seed: int) -> bytes:
    """Evaluate the packed key polynomial at seed in GF(2**61 - 1).

    At a fixed bit length, packing into 56-bit coefficients is injective.
    Horner's method computes the residue, encoded as a 64-bit public tag.
    """
    validate_bits(bits)
    if not 0 <= seed < _PRIME:
        raise ValueError("verification seed must be in the field")
    packed = np.packbits(bits).tobytes()
    value = 0
    for offset in range(0, len(packed), _COEFFICIENT_BYTES):
        coefficient = int.from_bytes(
            packed[offset : offset + _COEFFICIENT_BYTES], "big"
        )
        value = (value * seed + coefficient) % _PRIME
    return value.to_bytes(_TAG_BYTES, "big")


def verify_keys(key_a: BitArray, key_b: BitArray) -> VerificationResult:
    """Compare tags under a fresh, uniformly random shared field element."""
    validate_key_pair(key_a, key_b)
    seed = secrets.randbelow(_PRIME)
    alice_tag = verification_tag(key_a, seed)
    bob_tag = verification_tag(key_b, seed)
    return VerificationResult(
        secrets.compare_digest(alice_tag, bob_tag), 8 * _TAG_BYTES
    )

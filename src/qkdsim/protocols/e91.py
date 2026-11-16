"""Vectorized E91 pair measurements and key sifting for the Phi+ convention."""

from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator

from qkdsim.config import SessionConfig
from qkdsim.physics.channel import channel_qber
from qkdsim.physics.states import BitArray, MaskArray
from qkdsim.postprocess.sifting import SiftedKey

ALICE_ANGLES = np.array([0, 1, 2]) * (np.pi / 4)
BOB_ANGLES = np.array([1, 2, 3]) * (np.pi / 4)
EVE_ANGLES = np.array([0, np.pi / 2])


@dataclass(frozen=True, eq=False)
class E91Transmission:
    """Setting labels, local bits and clicks, indexed in source order."""

    alice_settings: BitArray = field(repr=False)
    bob_settings: BitArray = field(repr=False)
    alice_bits: BitArray = field(repr=False)
    bob_bits: BitArray = field(repr=False)
    alice_detected: MaskArray = field(repr=False)
    bob_detected: MaskArray = field(repr=False)

    @property
    def coincidences(self) -> MaskArray:
        """Keep rounds with a detector click at each endpoint."""
        return self.alice_detected & self.bob_detected


def sift_e91(observed: E91Transmission) -> SiftedKey:
    """Keep only coincident, equal-angle pairs, at pi/4 and pi/2."""
    coincident = observed.coincidences
    keep = coincident & (observed.alice_settings == observed.bob_settings + 1)
    return SiftedKey(
        observed.alice_bits[keep],
        observed.bob_bits[keep],
        np.flatnonzero(keep).astype(np.int64, copy=False),
        observed.alice_bits.size,
        int(np.count_nonzero(coincident)),
    )


def measure_e91(
    config: SessionConfig,
    alice_settings: BitArray,
    bob_settings: BitArray,
    eve_settings: BitArray,
    rng: Generator,
) -> tuple[BitArray, BitArray, BitArray]:
    """Draw pairs with E=V*cos(a-b), using setting codes 0/1/2 for none/Z/X Eve.

    Given Eve's fair outcome, projected Alice and resent Bob are independent.
    Their signed correlations with Eve are V*cos(a-e) and cos(b-e).
    Optical noise reverses Bob's outcome independently with P=channel_qber.
    """
    a = ALICE_ANGLES[alice_settings]
    b = BOB_ANGLES[bob_settings]
    visibility = config.e91.visibility
    alice = rng.integers(0, 2, size=a.size, dtype=np.uint8)
    bob = alice ^ (rng.random(a.size) < (1 - visibility * np.cos(a - b)) / 2)
    intercepted = eve_settings != 0
    e = EVE_ANGLES[eve_settings[intercepted] - 1]
    eve = rng.integers(0, 2, size=e.size, dtype=np.uint8)
    alice[intercepted] = eve ^ (
        rng.random(e.size) < (1 - visibility * np.cos(a[intercepted] - e)) / 2
    )
    bob[intercepted] = eve ^ (
        rng.random(e.size) < (1 - np.cos(b[intercepted] - e)) / 2
    )
    bob ^= rng.random(b.size) < channel_qber(config.channel)
    eve_bits = np.zeros(a.size, dtype=np.uint8)
    eve_bits[intercepted] = eve
    return alice, bob, eve_bits

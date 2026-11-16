"""Keep detected pulses whose preparation and measurement bases agree."""

from dataclasses import dataclass, field

import numpy as np

from qkdsim.physics.states import BitArray, CountArray
from qkdsim.protocols.bb84 import BB84Transmission


@dataclass(frozen=True, eq=False)
class SiftedKey:
    """Both sifted bit sequences, their original indices, and stage counts."""

    alice_bits: BitArray = field(repr=False)
    bob_bits: BitArray = field(repr=False)
    pulse_indices: CountArray = field(repr=False)
    sent: int
    detected: int

    @property
    def sifted(self) -> int:
        """Return the number of matching bases among detected pulses."""
        return self.pulse_indices.size


def sift(transmission: BB84Transmission) -> SiftedKey:
    """Apply the mask detected AND (basis_A == basis_B) in pulse order."""
    same_basis = transmission.alice_bases == transmission.bob_bases
    keep = transmission.detected_mask & same_basis
    return SiftedKey(
        transmission.alice_bits[keep],
        transmission.bob_bits[keep],
        np.flatnonzero(keep).astype(np.int64, copy=False),
        transmission.alice_bits.size,
        int(np.count_nonzero(transmission.detected_mask)),
    )

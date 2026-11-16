"""BB84 state labels and measurement probabilities."""

from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator
from numpy.typing import NDArray

BitArray = NDArray[np.uint8]
MaskArray = NDArray[np.bool_]
CountArray = NDArray[np.int64]

Z = 0
X = 1


@dataclass(frozen=True, eq=False)
class PulseStates:
    """Per-pulse photon counts and encodings in Z (0) or X (1)."""

    bits: BitArray = field(repr=False)
    bases: BitArray = field(repr=False)
    photons: CountArray = field(repr=False)


def sample_bases(size: int, p_z: float, rng: Generator) -> BitArray:
    """Draw independent basis labels with P(Z)=p_z and P(X)=1-p_z."""
    return (rng.random(size) >= p_z).astype(np.uint8)


def measurement_p_one(
    states: PulseStates, bases: BitArray, error: float = 0.0
) -> NDArray[np.float64]:
    """Return P(1): encoded bit with flip probability e, or 1/2 across bases."""
    matched_p_one = np.where(states.bits == 1, 1.0 - error, error)
    return np.where(states.bases == bases, matched_p_one, 0.5)

"""Measure-and-reprepare interception with isolated simulation metadata."""

from dataclasses import dataclass, field
from typing import Protocol, Self

import numpy as np
from numpy.random import Generator

from qkdsim.config import BasisMode
from qkdsim.physics.states import (
    BitArray,
    MaskArray,
    PulseStates,
    X,
    Z,
    measurement_p_one,
    sample_bases,
)


@dataclass(frozen=True, eq=False)
class GroundTruth:
    """Private simulator observations, with Eve's labels zero outside the mask."""

    eve_intercepted_mask: MaskArray = field(repr=False)
    eve_basis: BitArray = field(repr=False)
    eve_bit: BitArray = field(repr=False)

    @classmethod
    def empty(cls, n_pulses: int) -> Self:
        """Represent a run with no intercepted pulses."""
        return cls(
            np.zeros(n_pulses, dtype=np.bool_),
            np.zeros(n_pulses, dtype=np.uint8),
            np.zeros(n_pulses, dtype=np.uint8),
        )


class Attack(Protocol):
    """A simulator-side transformation with private observations."""

    def apply(
        self, states: PulseStates, rng: Generator
    ) -> tuple[PulseStates, GroundTruth]:
        """Return the forwarded states and attack metadata."""


@dataclass(frozen=True)
class InterceptResend:
    """Intercept each nonempty incoming pulse independently with probability p."""

    p: float = 1.0
    basis_mode: BasisMode = "random"

    def __post_init__(self) -> None:
        if not 0 <= self.p <= 1:
            raise ValueError("p must be in [0, 1]")
        if self.basis_mode not in ("random", "fixed_z", "fixed_x"):
            raise ValueError("invalid Eve basis mode")

    def apply(
        self, states: PulseStates, rng: Generator
    ) -> tuple[PulseStates, GroundTruth]:
        """Measure in Eve's basis, with P(error)=1/2 across different bases."""
        n_pulses = states.bits.size
        intercepted = (rng.random(n_pulses) < self.p) & (states.photons > 0)
        count = int(np.count_nonzero(intercepted))
        if self.basis_mode == "random":
            bases = sample_bases(count, 0.5, rng)
        else:
            fixed = Z if self.basis_mode == "fixed_z" else X
            bases = np.full(count, fixed, dtype=np.uint8)

        incoming = PulseStates(
            states.bits[intercepted],
            states.bases[intercepted],
            states.photons[intercepted],
        )
        bits = (rng.random(count) < measurement_p_one(incoming, bases)).astype(np.uint8)
        eve_basis = np.zeros(n_pulses, dtype=np.uint8)
        eve_bit = np.zeros(n_pulses, dtype=np.uint8)
        eve_basis[intercepted] = bases
        eve_bit[intercepted] = bits

        forwarded = PulseStates(
            np.where(intercepted, eve_bit, states.bits),
            np.where(intercepted, eve_basis, states.bases),
            np.where(intercepted, 1, states.photons),
        )
        return forwarded, GroundTruth(intercepted, eve_basis, eve_bit)

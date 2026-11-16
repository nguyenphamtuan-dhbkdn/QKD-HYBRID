"""Keep reproducible simulation draws separate from OS entropy."""

import secrets
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class SimRNG:
    """Own the single NumPy generator seeded for a simulation."""

    seed: int
    generator: np.random.Generator = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "generator", np.random.default_rng(self.seed))


def secure_random(n_bytes: int) -> bytes:
    """Return random bytes from the operating system's entropy source."""
    return secrets.token_bytes(n_bytes)

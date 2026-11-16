"""CHSH estimation on the four disjoint E91 test-setting groups."""

import math
from dataclasses import dataclass

import numpy as np

from qkdsim.physics.states import MaskArray
from qkdsim.protocols.e91 import E91Transmission

CHSH_SETTINGS = ((0, 0, 1), (0, 2, -1), (2, 0, 1), (2, 2, 1))


@dataclass(frozen=True)
class CHSHStatistics:
    """Correlations and counts in CHSH_SETTINGS order, with the signed sum."""

    counts: tuple[int, ...]
    correlations: tuple[float | None, ...]
    s: float | None
    standard_error: float | None

    def lower_bound(self, z: float) -> float | None:
        """Return S - z*sigma_S when every group supports a variance estimate."""
        if self.s is None or self.standard_error is None:
            return None
        return self.s - z * self.standard_error


def chsh_mask(observed: E91Transmission) -> MaskArray:
    """Identify coincident pairs earmarked for public CHSH testing."""
    mask: MaskArray = observed.coincidences & (
        (observed.alice_settings != 1) & (observed.bob_settings != 1)
    )
    return mask


def estimate_chsh(observed: E91Transmission) -> CHSHStatistics:
    """Compute E=1-2*mismatches/n and sigma_S=sqrt(sum((1-E**2)/(n-1))).

    Each E is the mean of +/-1 outcomes. Error propagation uses independent
    means conditional on the four group sizes, with Bessel-corrected variances.
    """
    coincident = observed.coincidences
    mismatch = observed.alice_bits != observed.bob_bits
    counts: list[int] = []
    correlations: list[float | None] = []
    s = variance = 0.0
    for alice, bob, sign in CHSH_SETTINGS:
        group = (
            coincident
            & (observed.alice_settings == alice)
            & (observed.bob_settings == bob)
        )
        n = int(np.count_nonzero(group))
        counts.append(n)
        if n == 0:
            correlations.append(None)
            continue
        correlation = 1 - 2 * np.count_nonzero(mismatch & group) / n
        correlations.append(correlation)
        s += sign * correlation
        if n > 1:
            variance += (1 - correlation**2) / (n - 1)
    return CHSHStatistics(
        tuple(counts),
        tuple(correlations),
        s if min(counts) > 0 else None,
        math.sqrt(variance) if min(counts) > 1 else None,
    )

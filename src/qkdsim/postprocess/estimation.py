"""Public, without-replacement QBER sampling and the M1 abort rule."""

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

import numpy as np
from numpy.random import Generator

from qkdsim.analysis.stats import Interval, clopper_pearson, wilson_interval
from qkdsim.auth.channel import ClassicalLink
from qkdsim.config import BB84Config
from qkdsim.physics.states import BitArray, CountArray
from qkdsim.postprocess.sifting import SiftedKey


@dataclass(frozen=True, eq=False)
class QBERStatistics:
    """Evidence from the revealed test subset."""

    sample_indices: CountArray = field(repr=False)
    errors: int
    q_est: float
    q_ub: float
    clopper_pearson: Interval
    wilson: Interval

    @property
    def sample_size(self) -> int:
        """Return the number of publicly compared bits."""
        return self.sample_indices.size


@dataclass(frozen=True, eq=False)
class ParameterEstimate:
    """Accepted estimate and the unrevealed bits in their original order."""

    stats: QBERStatistics
    alice_remaining: BitArray = field(repr=False)
    bob_remaining: BitArray = field(repr=False)


@dataclass(frozen=True)
class ParameterAbort:
    """Why estimation stopped and the evidence available at that point."""

    reason: Literal["insufficient statistics", "qber above threshold"]
    planned_sample_size: int
    stats: QBERStatistics | None = None


def hoeffding_upper(errors: int, sample_size: int, eps_pe: float) -> float:
    """Return min(1, errors/k + sqrt(-ln(eps_pe)/(2*k))).

    This is the simplified bound from the specification. For a finite-key
    analysis using Serfling's bound see Tomamichel et al. (arXiv:1103.4130).
    """
    if not 0 <= errors <= sample_size or sample_size <= 0:
        raise ValueError("expected 0 <= errors <= sample_size with sample_size > 0")
    if not 0 < eps_pe < 1:
        raise ValueError("eps_pe must be in (0, 1)")
    margin = math.sqrt(-math.log(eps_pe) / (2 * sample_size))
    return min(1.0, errors / sample_size + margin)


def estimate_parameters(
    key: SiftedKey,
    config: BB84Config,
    rng: Generator,
    *,
    channel: ClassicalLink | None = None,
) -> ParameterEstimate | ParameterAbort:
    """Compare ceil(f_test*n_sift) bits and discard them from both sequences."""
    sample_size = math.ceil(Fraction(str(config.test_fraction)) * key.sifted)
    if sample_size < config.k_min:
        return ParameterAbort("insufficient statistics", sample_size)

    sampled = np.sort(rng.choice(key.sifted, size=sample_size, replace=False))
    indices = key.pulse_indices[sampled]
    alice, bob = key.alice_bits[sampled], key.bob_bits[sampled]
    if channel is not None:
        channel.exchange("alice", "test_indices", indices.astype(">u8").tobytes())
        channel.exchange("alice", "test_alice", np.packbits(alice).tobytes())
        channel.exchange("bob", "test_bob", np.packbits(bob).tobytes())
    errors = int(np.count_nonzero(alice != bob))
    stats = QBERStatistics(
        sample_indices=indices,
        errors=errors,
        q_est=errors / sample_size,
        q_ub=hoeffding_upper(errors, sample_size, config.eps_pe),
        clopper_pearson=clopper_pearson(errors, sample_size),
        wilson=wilson_interval(errors, sample_size),
    )
    if stats.q_ub > config.q_max:
        return ParameterAbort("qber above threshold", sample_size, stats)

    keep = np.ones(key.sifted, dtype=np.bool_)
    keep[sampled] = False
    return ParameterEstimate(stats, key.alice_bits[keep], key.bob_bits[keep])

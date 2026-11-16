"""Shared BB84 preparation and fast NumPy measurement."""

from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator

from qkdsim.config import BB84Config, SessionConfig
from qkdsim.physics.channel import channel_qber
from qkdsim.physics.detector import detect
from qkdsim.physics.source import photon_counts
from qkdsim.physics.states import (
    BitArray,
    MaskArray,
    PulseStates,
    measurement_p_one,
    sample_bases,
)


@dataclass(frozen=True, eq=False)
class BB84Transmission:
    """Alice and Bob's observations before sifting."""

    alice_bits: BitArray = field(repr=False)
    alice_bases: BitArray = field(repr=False)
    bob_bases: BitArray = field(repr=False)
    bob_bits: BitArray = field(repr=False)
    detected_mask: MaskArray = field(repr=False)
    double_clicks: int


def sample_bb84_bases(config: BB84Config, size: int, rng: Generator) -> BitArray:
    """Draw Z/X labels from NumPy or from an unbiased simulated Hadamard source."""
    if config.basis_source == "qrng":
        from qkdsim.qrng import generate_qrng_bits

        return generate_qrng_bits(size, rng)
    return sample_bases(size, config.p_z, rng)


def prepare_bb84(config: SessionConfig, rng: Generator) -> PulseStates:
    """Draw P(a=1)=1/2 and P(A=Z)=p_z, then prepare the configured source."""
    n_pulses = config.bb84.n_pulses
    bits = rng.integers(0, 2, size=n_pulses, dtype=np.uint8)
    bases = sample_bb84_bases(config.bb84, n_pulses, rng)
    return PulseStates(bits, bases, photon_counts(n_pulses, config.source, rng))


def measure_bb84(
    config: SessionConfig, sent: PulseStates, received: PulseStates, rng: Generator
) -> BB84Transmission:
    """Draw P(B=Z)=p_z and measure the incoming states with the detector."""
    bases = sample_bb84_bases(config.bb84, sent.bits.size, rng)
    p_one = measurement_p_one(received, bases, channel_qber(config.channel))
    detection = detect(received.photons, p_one, config.channel, rng)
    return BB84Transmission(
        sent.bits,
        sent.bases,
        bases,
        detection.bits,
        detection.mask,
        detection.double_clicks,
    )

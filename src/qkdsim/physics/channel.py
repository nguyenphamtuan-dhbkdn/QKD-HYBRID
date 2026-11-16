"""Fibre attenuation and basis-symmetric optical noise."""

import math
from typing import Literal

import numpy as np
from numpy.random import Generator

from qkdsim.config import ChannelConfig
from qkdsim.physics.states import PulseStates

NoiseModel = Literal["bitflip", "depolarizing", "misalignment"]


def transmittance(length_km: float, alpha_db_per_km: float) -> float:
    """Convert fibre loss in dB to eta = 10**(-alpha*L/10)."""
    if not math.isfinite(length_km) or length_km < 0:
        raise ValueError("length_km must be finite and nonnegative")
    if not math.isfinite(alpha_db_per_km) or alpha_db_per_km < 0:
        raise ValueError("alpha_db_per_km must be finite and nonnegative")
    return math.pow(10.0, -alpha_db_per_km * length_km / 10.0)


def attenuate(
    states: PulseStates, config: ChannelConfig, rng: Generator
) -> PulseStates:
    """Retain Binomial(k, eta_ch) photons from each encoded pulse."""
    eta = transmittance(config.length_km, config.alpha_db_per_km)
    surviving = rng.binomial(states.photons, eta).astype(np.int64, copy=False)
    return PulseStates(states.bits, states.bases, surviving)


def noise_qber(model: NoiseModel, parameter: float) -> float:
    """Map e, p, or theta to e, p/2, or sin(theta)**2 respectively."""
    upper = math.pi / 2 if model == "misalignment" else 1.0
    if not 0 <= parameter <= upper:
        raise ValueError(f"{model} parameter must be in [0, {upper}]")
    match model:
        case "bitflip":
            return parameter
        case "depolarizing":
            return parameter / 2
        case "misalignment":
            return math.sin(parameter) ** 2


def noise_parameter(model: NoiseModel, qber: float) -> float:
    """Invert noise_qber on the principal angle range [0, pi/2]."""
    upper = 0.5 if model == "depolarizing" else 1.0
    if not 0 <= qber <= upper:
        raise ValueError(f"{model} QBER must be in [0, {upper}]")
    match model:
        case "bitflip":
            return qber
        case "depolarizing":
            return 2 * qber
        case "misalignment":
            return math.asin(math.sqrt(qber))


def combine_errors(first: float, second: float) -> float:
    """Return P(exactly one independent flip) = e1*(1-e2) + (1-e1)*e2."""
    return first * (1 - second) + (1 - first) * second


def misalignment_qber(config: ChannelConfig) -> float:
    """Return sin(theta)**2 when an angle is set, or the direct probability."""
    if config.misalignment_theta is not None:
        return noise_qber("misalignment", config.misalignment_theta)
    return config.e_misalign


def channel_qber(config: ChannelConfig) -> float:
    """Combine the configured independent optical errors for equal bases."""
    depolarizing = noise_qber("depolarizing", config.depol)
    return combine_errors(
        combine_errors(config.bitflip, depolarizing), misalignment_qber(config)
    )

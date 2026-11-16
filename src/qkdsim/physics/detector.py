"""Threshold detection with efficiency, dark clicks, and squashing."""

from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator
from numpy.typing import NDArray

from qkdsim.config import ChannelConfig
from qkdsim.physics.states import BitArray, CountArray, MaskArray


@dataclass(frozen=True, eq=False)
class Detection:
    """Bits (zero placeholder on misses), detected gates, and double-click count."""

    bits: BitArray = field(repr=False)
    mask: MaskArray = field(repr=False)
    double_clicks: int


def detect(
    photons: CountArray,
    p_one: NDArray[np.float64],
    config: ChannelConfig,
    rng: Generator,
) -> Detection:
    """Draw Binomial(k, eta_det) registered photons then Binomial(count, p_one).

    An independent Bernoulli(p_dark) event adds one uniformly routed click.
    Assign a fair bit when both threshold detectors click in the same gate.
    """
    registered = rng.binomial(photons, config.eta_det)
    ones = rng.binomial(registered, p_one)
    zero_click = registered > ones
    one_click = ones > 0

    if config.p_dark > 0:
        dark = rng.random(photons.size) < config.p_dark
        dark_one = rng.random(photons.size) < 0.5
        zero_click |= dark & ~dark_one
        one_click |= dark & dark_one

    double = zero_click & one_click
    count = int(np.count_nonzero(double))
    bits = one_click.astype(np.uint8)
    bits[double] = rng.integers(0, 2, size=count, dtype=np.uint8)
    return Detection(bits, zero_click | one_click, count)

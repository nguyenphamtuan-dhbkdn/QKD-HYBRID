"""Single-photon and weak coherent sources."""

import numpy as np
from numpy.random import Generator

from qkdsim.config import SourceConfig
from qkdsim.physics.states import CountArray


def photon_counts(n_pulses: int, config: SourceConfig, rng: Generator) -> CountArray:
    """Generate k=1 or independent k~Poisson(mu) photons per pulse."""
    if config.kind == "single_photon":
        return np.ones(n_pulses, dtype=np.int64)
    assert config.mu is not None  # Validated by SourceConfig.
    return rng.poisson(config.mu, size=n_pulses).astype(np.int64, copy=False)

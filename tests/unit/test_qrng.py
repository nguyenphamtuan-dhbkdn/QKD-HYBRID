from typing import Literal

import numpy as np
import pytest
from numpy.random import Generator

from qkdsim import qrng
from qkdsim.config import BB84Config, ChannelConfig, SessionConfig
from qkdsim.physics.states import BitArray
from qkdsim.postprocess.sifting import sift
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_bb84


def test_seeded_qrng_preserves_shot_order_and_size() -> None:
    first = qrng.generate_qrng_bits(129, SimRNG(616).generator)
    np.testing.assert_array_equal(
        first, qrng.generate_qrng_bits(129, SimRNG(616).generator)
    )
    assert first.shape == (129,)
    assert first.dtype == np.uint8
    assert set(first) == {0, 1}
    assert qrng.generate_qrng_bits(0, SimRNG(616).generator).size == 0
    with pytest.raises(ValueError, match="nonnegative integer"):
        qrng.generate_qrng_bits(-1, SimRNG(616).generator)


@pytest.mark.statistical
def test_qrng_hadamard_measurement_is_fair() -> None:
    n = 16_384
    bits = qrng.generate_qrng_bits(n, SimRNG(441).generator)
    assert abs(np.count_nonzero(bits) - n / 2) <= 4 * (n / 4) ** 0.5
    # For fair independent bits, their adjacent XORs are also independent.
    transitions = np.count_nonzero(bits[1:] != bits[:-1])
    assert abs(transitions - (n - 1) / 2) <= 4 * ((n - 1) / 4) ** 0.5


@pytest.mark.parametrize("backend", ["fast", "qiskit"])
def test_bb84_uses_qrng_for_both_endpoints(
    backend: Literal["fast", "qiskit"], monkeypatch: pytest.MonkeyPatch
) -> None:
    draws = iter([0, 1])
    rng = SimRNG(441).generator

    def source(size: int, generator: Generator) -> BitArray:
        assert generator is rng
        return np.full(size, next(draws), dtype=np.uint8)

    monkeypatch.setattr(qrng, "generate_qrng_bits", source)
    config = SessionConfig(
        bb84=BB84Config(backend=backend, n_pulses=40, basis_source="qrng"),
        channel=ChannelConfig(e_misalign=0),
    )
    observed, _ = simulate_bb84(config, rng)
    assert np.all(observed.alice_bases == 0)
    assert np.all(observed.bob_bases == 1)
    assert sift(observed).sifted == 0


def test_qrng_bases_require_unbiased_configuration() -> None:
    with pytest.raises(ValueError, match="requires p_z = 0.5"):
        BB84Config(p_z=0.7, basis_source="qrng")

"""Simulated Hadamard-measurement bit source."""

import numpy as np
from numpy.random import Generator
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from qkdsim.physics.states import BitArray


def generate_qrng_bits(size: int, rng: Generator) -> BitArray:
    """Sample P(0)=P(1)=1/2 by measuring H|0> once per shot.

    Aer uses pseudo-random sampling. The simulator's seed comes from the
    session RNG. These bits are suitable for simulated basis choices.
    """
    if type(size) is not int or size < 0:
        raise ValueError("size must be a nonnegative integer")
    if size == 0:
        return np.empty(0, dtype=np.uint8)
    circuit = QuantumCircuit(1, 1)
    circuit.h(0)
    circuit.measure(0, 0)
    simulator = AerSimulator(method="stabilizer", max_parallel_threads=1)
    result = simulator.run(
        circuit,
        shots=size,
        memory=True,
        seed_simulator=int(rng.integers(0, 2**32, dtype=np.uint32)),
    ).result()
    if not result.success:
        raise ValueError(f"QRNG Aer simulation failed: {result.status}")
    data = "".join(result.get_memory()).encode("ascii")
    return np.frombuffer(data, dtype=np.uint8) - ord("0")

"""E91 with two-qubit Aer circuits, grouped by measurement settings."""

from itertools import product

import numpy as np
from numpy.random import Generator
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import depolarizing_error

from qkdsim.config import SessionConfig
from qkdsim.physics.aer import bob_channel_noise
from qkdsim.physics.states import BitArray
from qkdsim.protocols.e91 import ALICE_ANGLES, BOB_ANGLES, EVE_ANGLES


def measure_e91_qiskit(
    config: SessionConfig,
    alice_settings: BitArray,
    bob_settings: BitArray,
    eve_settings: BitArray,
    rng: Generator,
) -> tuple[BitArray, BitArray, BitArray]:
    """Measure Phi+ using Ry(-phi), with a Werner channel on CX.

    The two-qubit depolarizing channel yields rho=V*|Phi+><Phi+|+(1-V)*I/4.
    Eve measures Bob's qubit mid-circuit and rotates the projected state back.
    """
    simulator = AerSimulator(method="density_matrix", max_parallel_threads=1)
    noise = bob_channel_noise(config.channel)
    if config.e91.visibility < 1:
        noise.add_all_qubit_quantum_error(
            depolarizing_error(1 - config.e91.visibility, 2), "cx"
        )
    alice = np.zeros(alice_settings.size, dtype=np.uint8)
    bob = np.zeros_like(alice)
    eve = np.zeros_like(alice)
    groups = alice_settings * 9 + bob_settings * 3 + eve_settings
    for a, b, e in product(range(3), repeat=3):
        indices = np.flatnonzero(groups == (a * 9 + b * 3 + e))
        if not indices.size:
            continue
        circuit = QuantumCircuit(2, 3)
        circuit.h(0)
        circuit.cx(0, 1)
        if e:
            angle = EVE_ANGLES[e - 1]
            circuit.ry(-angle, 1)
            circuit.measure(1, 2)
            circuit.ry(angle, 1)
        circuit.id(1)
        circuit.ry(-ALICE_ANGLES[a], 0)
        circuit.ry(-BOB_ANGLES[b], 1)
        circuit.measure([0, 1], [0, 1])
        result = simulator.run(
            circuit,
            noise_model=noise,
            shots=indices.size,
            memory=True,
            seed_simulator=int(rng.integers(0, 2**32, dtype=np.uint32)),
        ).result()
        if not result.success:
            raise ValueError(f"E91 Aer simulation failed: {result.status}")
        # Memory is written as c2 c1 c0, i.e. Eve, Bob, Alice.
        data = "".join(result.get_memory()).encode("ascii")
        bits = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3) - ord("0")
        alice[indices], bob[indices], eve[indices] = bits[:, 2], bits[:, 1], bits[:, 0]
    return alice, bob, eve

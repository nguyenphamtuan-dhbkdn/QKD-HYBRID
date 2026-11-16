"""BB84 measurement in one Clifford circuit on Qiskit Aer."""

import numpy as np
from numpy.random import Generator
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error, pauli_error

from qkdsim.config import ChannelConfig, SessionConfig
from qkdsim.physics.channel import combine_errors, misalignment_qber
from qkdsim.physics.detector import resolve_clicks
from qkdsim.physics.states import (
    BitArray,
    CountArray,
    MaskArray,
    PulseStates,
    X,
    sample_bases,
)
from qkdsim.protocols.bb84 import BB84Transmission


def _channel_noise(config: ChannelConfig) -> NoiseModel:
    """Apply depolarization and an independent Y flip on the channel identity.

    Y anticommutes with both measurement bases. It flips equal-basis outcomes
    with probability e_bit + e_mis - 2*e_bit*e_mis and preserves uniformity
    across different bases. Depolarization adds an independent error p/2.
    """
    noise = NoiseModel()
    flip = combine_errors(config.bitflip, misalignment_qber(config))
    if config.depol or flip:
        error = depolarizing_error(config.depol, 1)
        if flip:
            error = error.compose(pauli_error([("I", 1 - flip), ("Y", flip)]))
        noise.add_all_qubit_quantum_error(error, "id")
    return noise


def _sample_circuit(
    circuit: QuantumCircuit, noise: NoiseModel, rng: Generator
) -> BitArray:
    """Read one shot in increasing classical-bit order."""
    simulator = AerSimulator(method="stabilizer", max_parallel_threads=1)
    result = simulator.run(
        circuit,
        noise_model=noise,
        shots=1,
        memory=True,
        seed_simulator=int(rng.integers(0, 2**32, dtype=np.uint32)),
    ).result()
    if not result.success:
        raise ValueError(f"BB84 Aer simulation failed: {result.status}")
    # Qiskit displays the highest classical-bit index first.
    memory: list[str] = result.get_memory()
    return np.frombuffer(memory[0][::-1].encode("ascii"), dtype=np.uint8) - ord("0")


def measure_bb84_qiskit(
    config: SessionConfig,
    sent: PulseStates,
    received: PulseStates,
    intercepted: MaskArray,
    eve_bases: BitArray,
    rng: Generator,
) -> tuple[BB84Transmission, BitArray]:
    """Prepare H**A X**a |0>, measure in Eve's basis when intercepted, then Bob's.

    Detector registrations are Binomial(k, eta_det) and independent of the
    measured bit. Keep an Eve-only qubit when her resent photon is undetected.
    """
    n_pulses = sent.bits.size
    bob_bases = sample_bases(n_pulses, config.bb84.p_z, rng)
    photons = np.where(intercepted, 1, received.photons)
    registered = rng.binomial(photons, config.channel.eta_det)
    owners = np.repeat(np.arange(n_pulses), np.maximum(registered, intercepted))
    ones: CountArray = np.zeros(n_pulses, dtype=np.int64)
    eve_bits = np.zeros(n_pulses, dtype=np.uint8)

    if owners.size:
        bob_qubits = np.flatnonzero(registered[owners]).tolist()
        eve_qubits = np.flatnonzero(intercepted[owners]).tolist()
        n_bob = len(bob_qubits)
        circuit = QuantumCircuit(owners.size, n_bob + len(eve_qubits))
        for qubit, pulse in enumerate(owners):
            if received.bits[pulse]:
                circuit.x(qubit)
            if received.bases[pulse] == X:
                circuit.h(qubit)

        for clbit, qubit in enumerate(eve_qubits, start=n_bob):
            diagonal = eve_bases[owners[qubit]] == X
            if diagonal:
                circuit.h(qubit)
            circuit.measure(qubit, clbit)
            # Rotate the collapsed measurement eigenstate back to Eve's basis.
            if diagonal:
                circuit.h(qubit)

        noise = _channel_noise(config.channel)
        has_noise = not noise.is_ideal()
        for clbit, qubit in enumerate(bob_qubits):
            if has_noise:
                circuit.id(qubit)
            if bob_bases[owners[qubit]] == X:
                circuit.h(qubit)
            circuit.measure(qubit, clbit)

        outcomes = _sample_circuit(circuit, noise, rng)
        eve_bits[intercepted] = outcomes[n_bob:]
        one_pulses = owners[bob_qubits][outcomes[:n_bob] == 1]
        ones = np.bincount(one_pulses, minlength=n_pulses).astype(np.int64, copy=False)

    detection = resolve_clicks(registered, ones, config.channel, rng)
    return BB84Transmission(
        sent.bits,
        sent.bases,
        bob_bases,
        detection.bits,
        detection.mask,
        detection.double_clicks,
    ), eve_bits

"""Quantum noise shared by the Aer backends."""

from qiskit_aer.noise import NoiseModel, depolarizing_error, pauli_error

from qkdsim.config import ChannelConfig
from qkdsim.physics.channel import combine_errors, misalignment_qber


def bob_channel_noise(config: ChannelConfig) -> NoiseModel:
    """Depolarize with probability p and apply an independent Pauli Y flip.

    The flip probability is e_bit + e_mis - 2*e_bit*e_mis. Pauli Y
    reverses outcomes in any XZ-plane basis. Attach the errors to Bob's id.
    """
    noise = NoiseModel()
    flip = combine_errors(config.bitflip, misalignment_qber(config))
    if config.depol or flip:
        error = depolarizing_error(config.depol, 1)
        if flip:
            error = error.compose(pauli_error([("I", 1 - flip), ("Y", flip)]))
        noise.add_all_qubit_quantum_error(error, "id")
    return noise

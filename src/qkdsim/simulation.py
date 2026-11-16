"""Run the simulator outside the BB84 participants' information boundary."""

from numpy.random import Generator

from qkdsim.attacks.intercept_resend import GroundTruth, InterceptResend
from qkdsim.config import SessionConfig
from qkdsim.physics.channel import attenuate
from qkdsim.protocols.bb84 import BB84Transmission, measure_bb84, prepare_bb84


def simulate_bb84(
    config: SessionConfig, rng: Generator
) -> tuple[BB84Transmission, GroundTruth]:
    """Return the public observations and a separate simulator-only Eve record."""
    if config.attack.kind == "pns":
        raise ValueError("BB84 currently supports attacks 'none' and 'ir'")
    sent = prepare_bb84(config, rng)
    received = attenuate(sent, config.channel, rng)
    attack = InterceptResend(config.attack.p, config.attack.basis_mode)
    truth = GroundTruth.empty(config.bb84.n_pulses)

    if config.bb84.backend == "qiskit":
        from qkdsim.protocols.bb84_qiskit import measure_bb84_qiskit

        intercepted, eve_bases = truth.eve_intercepted_mask, truth.eve_basis
        if config.attack.kind == "ir":
            intercepted, eve_bases = attack.sample_interceptions(received, rng)
        observed, eve_bits = measure_bb84_qiskit(
            config, sent, received, intercepted, eve_bases, rng
        )
        return observed, GroundTruth(intercepted, eve_bases, eve_bits)

    if config.attack.kind == "ir":
        received, truth = attack.apply(received, rng)
    return measure_bb84(config, sent, received, rng), truth

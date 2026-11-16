"""Run the simulator outside the BB84 participants' information boundary."""

from numpy.random import Generator

from qkdsim.attacks.intercept_resend import Attack, GroundTruth, InterceptResend
from qkdsim.config import SessionConfig
from qkdsim.physics.channel import attenuate
from qkdsim.protocols.bb84 import BB84Transmission, measure_bb84, prepare_bb84


def simulate_bb84(
    config: SessionConfig, rng: Generator
) -> tuple[BB84Transmission, GroundTruth]:
    """Return the public observations and a separate simulator-only Eve record."""
    sent = prepare_bb84(config, rng)
    received = attenuate(sent, config.channel, rng)
    match config.attack.kind:
        case "none":
            truth = GroundTruth.empty(config.bb84.n_pulses)
        case "ir":
            attack: Attack = InterceptResend(config.attack.p, config.attack.basis_mode)
            received, truth = attack.apply(received, rng)
        case "pns":
            raise ValueError("BB84 currently supports attacks 'none' and 'ir'")
    return measure_bb84(config, sent, received, rng), truth

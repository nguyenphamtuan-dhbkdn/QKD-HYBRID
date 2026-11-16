"""Run the simulator outside the BB84 participants' information boundary."""

from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
from numpy.random import Generator

from qkdsim.attacks.intercept_resend import GroundTruth, InterceptResend
from qkdsim.config import SessionConfig
from qkdsim.physics.channel import attenuate
from qkdsim.postprocess.cascade import cascade_reconcile, perfect_ec
from qkdsim.postprocess.estimation import ParameterAbort, estimate_parameters
from qkdsim.postprocess.keylength import secret_key_length
from qkdsim.postprocess.privacy_amp import random_toeplitz_seed, toeplitz_hash_fft
from qkdsim.postprocess.result import AbortEvidence, FinalKey
from qkdsim.postprocess.sifting import sift
from qkdsim.postprocess.verification import verification_collision_bound, verify_keys
from qkdsim.protocols.bb84 import BB84Transmission, measure_bb84, prepare_bb84
from qkdsim.rng import SimRNG


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


def run_bb84_session(
    config: SessionConfig, rng: Generator | None = None
) -> FinalKey | AbortEvidence:
    """Simulate BB84 through reconciliation, verification, and key extraction.

    The classical exchanges are local and assume honest delivery. As this
    simulation uses a predictable RNG for the physics, its keys are insecure.
    """
    if rng is None:
        rng = SimRNG(config.seed).generator
    session_id = uuid4()
    bb84 = config.bb84
    observed, truth = simulate_bb84(config, rng)
    estimate = estimate_parameters(sift(observed), bb84, rng)
    if isinstance(estimate, ParameterAbort):
        return AbortEvidence(
            session_id, estimate.reason, estimate.planned_sample_size, estimate.stats
        )

    stats = estimate.stats
    key_a, key_b = estimate.alice_remaining, estimate.bob_remaining
    if bb84.ec_mode == "cascade":
        reconciled = cascade_reconcile(
            key_a, key_b, stats.q_est, rng, passes=bb84.cascade_passes
        )
    else:
        reconciled = perfect_ec(key_a, key_b, stats.q_est, bb84.f_ec_ideal)
    corrected = reconciled.key_b_corrected

    n_key = key_a.size
    if verification_collision_bound(n_key) > bb84.eps_cor:
        return AbortEvidence(
            session_id, "verification bound exceeds eps_cor", stats.sample_size, stats
        )
    verification = verify_keys(key_a, corrected)
    if not verification.matches:
        return AbortEvidence(
            session_id, "verification mismatch", stats.sample_size, stats
        )
    length = secret_key_length(
        n_key,
        stats.q_ub,
        reconciled.leak_bits,
        verification.leak_bits,
        bb84.eps_sec,
        bb84.eps_cor,
    )
    if length <= 0:
        return AbortEvidence(
            session_id, "no secret key at this QBER/length", stats.sample_size, stats
        )

    seed = random_toeplitz_seed(n_key, length)
    alice = toeplitz_hash_fft(key_a, length, seed)
    bob = toeplitz_hash_fft(corrected, length, seed)
    # The simulator checks the two local outputs before returning a shared key.
    if not np.array_equal(alice, bob):
        return AbortEvidence(
            session_id, "privacy amplification mismatch", stats.sample_size, stats
        )
    return FinalKey(
        key_bytes=np.packbits(alice).tobytes(),
        key_id=uuid4(),
        session_id=session_id,
        length_bits=length,
        qber=stats.q_est,
        qber_ub=stats.q_ub,
        leak_total=reconciled.leak_bits + verification.leak_bits,
        eps_sec=bb84.eps_sec,
        eps_cor=bb84.eps_cor,
        created_at=datetime.now(UTC),
        backend=bb84.backend,
        ground_truth_eve_present=bool(truth.eve_intercepted_mask.any()),
    )

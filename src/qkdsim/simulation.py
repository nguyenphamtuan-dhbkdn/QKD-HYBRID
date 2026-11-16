"""Run the simulator outside the participants' information boundary."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np
from numpy.random import Generator, SeedSequence, default_rng

from qkdsim.analysis.chsh import CHSHStatistics, chsh_mask, estimate_chsh
from qkdsim.attacks.intercept_resend import GroundTruth, InterceptResend
from qkdsim.auth.channel import AUTH_BITS, AuthenticationError, ClassicalLink, Transport
from qkdsim.auth.pool import AuthenticationPool
from qkdsim.config import AttackConfig, BB84Config, SessionConfig
from qkdsim.monitor.calibration import Calibration
from qkdsim.monitor.metrics import empty_gate_clicks
from qkdsim.monitor.session import MonitoredSession, State
from qkdsim.physics.channel import attenuate, transmittance
from qkdsim.physics.detector import resolve_clicks
from qkdsim.postprocess.cascade import cascade_reconcile, perfect_ec
from qkdsim.postprocess.estimation import (
    ParameterAbort,
    ParameterEstimate,
    QBERStatistics,
    estimate_parameters,
)
from qkdsim.postprocess.keylength import secret_key_length
from qkdsim.postprocess.privacy_amp import random_toeplitz_seed, toeplitz_hash_fft
from qkdsim.postprocess.result import AbortEvidence, AbortReason, FinalKey, LinkKeys
from qkdsim.postprocess.sifting import sift
from qkdsim.postprocess.verification import verification_collision_bound, verify_keys
from qkdsim.protocols.bb84 import BB84Transmission, measure_bb84, prepare_bb84
from qkdsim.protocols.e91 import E91Transmission, measure_e91, sift_e91
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


def calibrate_bb84(
    config: SessionConfig,
    *,
    pulses: int = 100_000,
    empty_gates: int = 100_000,
) -> Calibration:
    """Compare all sifted bits in a dedicated honest-channel pilot."""
    pilot = replace(
        config,
        bb84=replace(config.bb84, n_pulses=pulses),
        attack=AttackConfig(),
    )
    rng = default_rng(SeedSequence(pilot.seed, spawn_key=(1,)))
    observed, _ = simulate_bb84(pilot, rng)
    key = sift(observed)
    return Calibration(
        key.sent,
        key.detected,
        key.sifted,
        int(np.count_nonzero(key.alice_bits != key.bob_bits)),
        empty_gates,
        empty_gate_clicks(config.channel, empty_gates, rng),
    )


def run_bb84_session(
    config: SessionConfig,
    rng: Generator | None = None,
    *,
    session: MonitoredSession | None = None,
    authentication: AuthenticationPool | None = None,
    transport: Transport | None = None,
) -> FinalKey | AbortEvidence:
    """Simulate BB84 through reconciliation, verification, and key extraction.

    Supply a pre-shared authentication pool for an HMAC-protected transcript.
    The simulation uses a predictable RNG for the physics, so its keys are insecure.
    """
    result = run_bb84_link(
        config,
        rng,
        session=session,
        authentication=authentication,
        transport=transport,
    )
    return result.alice if isinstance(result, LinkKeys) else result


def run_bb84_link(
    config: SessionConfig,
    rng: Generator | None = None,
    *,
    session: MonitoredSession | None = None,
    authentication: AuthenticationPool | None = None,
    transport: Transport | None = None,
) -> LinkKeys | AbortEvidence:
    """Run one link and return both local outputs for simulator experiments."""
    if authentication is None and transport is not None:
        raise ValueError("a classical transport requires an authentication pool")
    if rng is None:
        rng = SimRNG(config.seed).generator
    if session is None:
        session = MonitoredSession(config)
    elif session.config != config:
        raise ValueError("monitor and BB84 configurations differ")
    session.start()
    link: AbstractContextManager[
        tuple[ClassicalLink | None, Callable[[bytes], None] | None]
    ]
    if authentication is None:
        link = nullcontext((None, None))
    else:
        link = authentication.link(session.session_id, transport)
    try:
        with link as (channel, refresh):
            return _run_monitored_bb84(config, rng, session, channel, refresh)
    except AuthenticationError as exc:
        session.abort(str(exc))
        return AbortEvidence(
            session.session_id,
            "classical authentication failed",
            session.metrics.compared,
            None,
        )


def _run_monitored_bb84(
    config: SessionConfig,
    rng: Generator,
    session: MonitoredSession,
    channel: ClassicalLink | None,
    refresh: Callable[[bytes], None] | None,
) -> LinkKeys | AbortEvidence:
    session_id = session.session_id

    def abort(
        reason: AbortReason,
        planned: int,
        stats: QBERStatistics | None,
    ) -> AbortEvidence:
        session.abort(reason)
        return AbortEvidence(session_id, reason, planned, stats)

    bb84 = config.bb84
    observed, truth = simulate_bb84(config, rng)
    session.record_transmission(observed)
    session.advance(State.BASIS_RECONCILIATION, "exchanging detected gates and bases")
    if channel is not None:
        channel.exchange(
            "bob", "detected_gates", np.packbits(observed.detected_mask).tobytes()
        )
        channel.exchange(
            "alice", "alice_bases", np.packbits(observed.alice_bases).tobytes()
        )
        channel.exchange("bob", "bob_bases", np.packbits(observed.bob_bases).tobytes())
    sifted = sift(observed)
    session.sample(observed, sifted, None)
    session.advance(State.PARAMETER_ESTIMATION, "sampling public test bits")
    estimate = estimate_parameters(sifted, bb84, rng, channel=channel)
    alarm = session.sample(observed, sifted, estimate.stats)
    if isinstance(estimate, ParameterAbort):
        return abort(estimate.reason, estimate.planned_sample_size, estimate.stats)

    stats = estimate.stats
    if alarm:
        return abort("monitor alarm", stats.sample_size, stats)
    result = _finish_key(
        bb84,
        rng,
        estimate,
        session_id,
        sifted.sent,
        bool(truth.eve_intercepted_mask.any()),
        channel=channel,
        refresh=refresh,
        advance=session.advance,
    )
    if isinstance(result, AbortEvidence):
        session.abort(result.reason)
    return result


def _finish_key(
    settings: BB84Config,
    rng: Generator,
    estimate: ParameterEstimate,
    session_id: UUID,
    sent: int,
    eve_present: bool,
    *,
    channel: ClassicalLink | None,
    refresh: Callable[[bytes], None] | None,
    advance: Callable[[State, str], None] | None = None,
) -> LinkKeys | AbortEvidence:
    """Share reconciliation, verification, and extraction across both protocols."""
    stats = estimate.stats

    def abort(reason: AbortReason) -> AbortEvidence:
        return AbortEvidence(session_id, reason, stats.sample_size, stats)

    if advance is not None:
        advance(State.ERROR_CORRECTION, "public sample within abort limits")
    key_a, key_b = estimate.alice_remaining, estimate.bob_remaining
    if settings.ec_mode == "cascade":
        reconciled = cascade_reconcile(
            key_a,
            key_b,
            stats.q_est,
            rng,
            passes=settings.cascade_passes,
            channel=channel,
        )
    else:
        reconciled = perfect_ec(key_a, key_b, stats.q_est, settings.f_ec_ideal)
    corrected = reconciled.key_b_corrected

    if advance is not None:
        advance(State.VERIFICATION, "comparing verification tags")
    n_key = key_a.size
    if verification_collision_bound(n_key) > settings.eps_cor:
        return abort("verification bound exceeds eps_cor")
    verification = (
        verify_keys(key_a, corrected)
        if channel is None
        else verify_keys(key_a, corrected, channel=channel)
    )
    if not verification.matches:
        return abort("verification mismatch")
    length = secret_key_length(
        n_key,
        stats.q_ub,
        reconciled.leak_bits,
        verification.leak_bits,
        settings.eps_sec,
        settings.eps_cor,
    )
    if length <= 0:
        return abort("no secret key at this QBER/length")
    auth_bits = AUTH_BITS if refresh is not None else 0
    if length <= auth_bits:
        return abort("insufficient key for authentication refresh")

    if advance is not None:
        advance(State.PRIVACY_AMPLIFICATION, "extracting finite-length key")
    seed = random_toeplitz_seed(n_key, length)
    bob_seed = seed
    if channel is not None:
        public_seed = channel.exchange(
            "alice", "toeplitz_seed", np.packbits(seed).tobytes()
        )
        bob_seed = np.unpackbits(
            np.frombuffer(public_seed, dtype=np.uint8), count=seed.size
        )
    alice = toeplitz_hash_fft(key_a, length, seed)
    bob = toeplitz_hash_fft(corrected, length, bob_seed)
    # The simulator checks the two local outputs before returning a shared key.
    if not np.array_equal(alice, bob):
        return abort("privacy amplification mismatch")
    alice_bytes = np.packbits(alice).tobytes()
    bob_bytes = np.packbits(bob).tobytes()
    prefix = auth_bits // 8
    final_key = FinalKey(
        key_bytes=alice_bytes[prefix:],
        key_id=uuid4(),
        session_id=session_id,
        length_bits=length - auth_bits,
        qber=stats.q_est,
        qber_ub=stats.q_ub,
        leak_total=reconciled.leak_bits + verification.leak_bits,
        eps_sec=settings.eps_sec,
        eps_cor=settings.eps_cor,
        created_at=datetime.now(UTC),
        backend=settings.backend,
        ground_truth_eve_present=eve_present,
        auth_bits=auth_bits,
        net_key_rate=(length - auth_bits) / sent,
    )
    if advance is not None:
        advance(State.KEY_READY, "verified key available")
    if refresh is not None:
        refresh(alice_bytes[:prefix])
    return LinkKeys(final_key, bob_bytes[prefix:])


def simulate_e91(
    config: SessionConfig, rng: Generator
) -> tuple[E91Transmission, GroundTruth]:
    """Sample two independent fiber arms and require coincident detector clicks."""
    if config.attack.kind == "pns":
        raise ValueError("E91 supports attacks 'none' and 'ir'")
    n = config.e91.n_pairs
    channel = config.channel
    eta = transmittance(channel.length_km, channel.alpha_db_per_km)
    a = rng.integers(0, 3, size=n, dtype=np.uint8)
    b = rng.integers(0, 3, size=n, dtype=np.uint8)
    arrives_a = rng.random(n) < eta
    arrives_b = rng.random(n) < eta
    eve_settings = np.zeros(n, dtype=np.uint8)
    if config.attack.kind == "ir":
        intercepted = arrives_b & (rng.random(n) < config.attack.p)
        mode = config.attack.basis_mode
        if mode == "random":
            eve_settings[intercepted] = rng.integers(
                1, 3, size=int(np.count_nonzero(intercepted)), dtype=np.uint8
            )
        else:
            eve_settings[intercepted] = 1 if mode == "fixed_z" else 2
    measure = measure_e91
    if config.e91.backend == "qiskit":
        from qkdsim.protocols.e91_qiskit import measure_e91_qiskit

        measure = measure_e91_qiskit
    a_bits, b_bits, eve_bits = measure(config, a, b, eve_settings, rng)
    registered_a = rng.binomial(arrives_a, channel.eta_det)
    registered_b = rng.binomial(arrives_b, channel.eta_det)
    alice = resolve_clicks(registered_a, registered_a * a_bits, channel, rng)
    bob = resolve_clicks(registered_b, registered_b * b_bits, channel, rng)
    return (
        E91Transmission(a, b, alice.bits, bob.bits, alice.mask, bob.mask),
        GroundTruth(
            eve_settings != 0,
            np.maximum(eve_settings, 1) - 1,
            eve_bits,
        ),
    )


@dataclass(frozen=True)
class E91Session:
    """Aggregate Bell-test evidence and the result of key extraction."""

    sent: int
    coincident: int
    sifted: int
    chsh: CHSHStatistics | None
    outcome: LinkKeys | AbortEvidence


def run_e91_session(
    config: SessionConfig,
    rng: Generator | None = None,
    *,
    authentication: AuthenticationPool | None = None,
    transport: Transport | None = None,
) -> FinalKey | AbortEvidence:
    """Run E91 through the CHSH gate and the shared key-extraction pipeline."""
    report = run_e91_link(
        config, rng, authentication=authentication, transport=transport
    )
    outcome = report.outcome
    return outcome.alice if isinstance(outcome, LinkKeys) else outcome


def run_e91_link(
    config: SessionConfig,
    rng: Generator | None = None,
    *,
    authentication: AuthenticationPool | None = None,
    transport: Transport | None = None,
) -> E91Session:
    """Run one link with Bell statistics and optional transcript authentication."""
    if authentication is None and transport is not None:
        raise ValueError("a classical transport requires an authentication pool")
    if rng is None:
        rng = SimRNG(config.seed).generator
    session_id = uuid4()
    observed, truth = simulate_e91(config, rng)
    sifted = sift_e91(observed)
    result: LinkKeys | AbortEvidence
    chsh = None
    link: AbstractContextManager[
        tuple[ClassicalLink | None, Callable[[bytes], None] | None]
    ]
    if authentication is None:
        link = nullcontext((None, None))
    else:
        link = authentication.link(session_id, transport)
    try:
        with link as (channel, refresh):
            if channel is not None:
                test = chsh_mask(observed)
                channel.exchange(
                    "alice", "alice_settings", observed.alice_settings.tobytes()
                )
                channel.exchange("bob", "bob_settings", observed.bob_settings.tobytes())
                channel.exchange(
                    "alice",
                    "alice_clicks",
                    np.packbits(observed.alice_detected).tobytes(),
                )
                channel.exchange(
                    "bob", "bob_clicks", np.packbits(observed.bob_detected).tobytes()
                )
                channel.exchange(
                    "alice",
                    "chsh_alice",
                    np.packbits(observed.alice_bits[test]).tobytes(),
                )
                channel.exchange(
                    "bob", "chsh_bob", np.packbits(observed.bob_bits[test]).tobytes()
                )
            chsh = estimate_chsh(observed)
            lower = chsh.lower_bound(config.e91.chsh_z)
            if lower is None:
                result = AbortEvidence(
                    session_id, "insufficient CHSH statistics", 0, None
                )
            elif lower <= 2:
                result = AbortEvidence(
                    session_id, "CHSH violation below margin", 0, None
                )
            else:
                settings = replace(config.bb84, backend=config.e91.backend)
                estimate = estimate_parameters(sifted, settings, rng, channel=channel)
                if isinstance(estimate, ParameterAbort):
                    result = AbortEvidence(
                        session_id,
                        estimate.reason,
                        estimate.planned_sample_size,
                        estimate.stats,
                    )
                else:
                    result = _finish_key(
                        settings,
                        rng,
                        estimate,
                        session_id,
                        sifted.sent,
                        bool(truth.eve_intercepted_mask.any()),
                        channel=channel,
                        refresh=refresh,
                    )
    except AuthenticationError:
        result = AbortEvidence(session_id, "classical authentication failed", 0, None)
    return E91Session(sifted.sent, sifted.detected, sifted.sifted, chsh, result)

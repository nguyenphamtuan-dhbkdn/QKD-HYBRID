"""Check authentication in BB84 and the two independent links in E12."""

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from qkdsim import simulation
from qkdsim.attacks.mitm_classical import run_classical_mitm
from qkdsim.auth.channel import AUTH_BITS, AuthenticatedChannel, Party
from qkdsim.auth.pool import AuthenticationPool
from qkdsim.config import BB84Config, ChannelConfig, SessionConfig, load_config
from qkdsim.monitor.session import MonitoredSession, State
from qkdsim.physics.states import BitArray
from qkdsim.postprocess.result import AbortEvidence, LinkKeys
from qkdsim.rng import SimRNG

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.statistical
@pytest.mark.parametrize("authenticated", [False, True])
def test_e12_classical_mitm(authenticated: bool) -> None:
    config = load_config(ROOT / "configs" / "e12_mitm.yaml")
    rng = SimRNG(config.seed).generator
    for _ in range(1000):
        result = run_classical_mitm(config, rng, authenticated=authenticated)
        if authenticated:
            assert not result.succeeded
            assert not result.alice_key_known_to_eve
            assert not result.bob_key_known_to_eve
            assert (
                result.alice_abort == result.bob_abort == "authentication tag mismatch"
            )
        else:
            assert result.succeeded
            assert result.alice_key_known_to_eve and result.bob_key_known_to_eve
            assert result.peer_keys_differ


def test_authenticated_session_reserves_fresh_bits_and_rotates_the_hmac_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = SessionConfig(bb84=BB84Config(n_pulses=40_000))
    pool = AuthenticationPool()
    recorded: list[BitArray] = []
    transcript: list[str] = []
    actual_hash = simulation.toeplitz_hash_fft

    def record(bits: BitArray, length: int, seed: BitArray) -> BitArray:
        extracted = actual_hash(bits, length, seed)
        recorded.append(extracted)
        return extracted

    def forward(sender: Party, kind: str, frame: bytes) -> bytes:
        transcript.append(kind)
        return frame

    monkeypatch.setattr(simulation, "toeplitz_hash_fft", record)
    result = simulation.run_bb84_link(cfg, authentication=pool, transport=forward)
    assert isinstance(result, LinkKeys)
    key, bob = result.alice, result.bob_bytes
    assert pool.rotations == 1
    assert key.auth_bits == AUTH_BITS
    assert key.gross_length_bits == recorded[0].size == recorded[1].size
    assert key.net_key_rate == key.length_bits / cfg.bb84.n_pulses
    expected = np.packbits(recorded[0]).tobytes()
    prefix_bytes = AUTH_BITS // 8
    assert key.key_bytes == bob == expected[prefix_bytes:]
    session_id = uuid4()
    verifier = AuthenticatedChannel(expected[:prefix_bytes], session_id, "bob")

    def accept(sender: Party, kind: str, frame: bytes) -> bytes:
        assert verifier.open(kind, frame) == b"next link"
        return frame

    with pool.link(session_id, accept) as (link, _):
        assert link.exchange("alice", "bases", b"next link") == b"next link"
    assert set(transcript) >= {
        "detected_gates",
        "alice_bases",
        "bob_bases",
        "test_indices",
        "test_alice",
        "test_bob",
        "cascade_permutation",
        "cascade_block_parities",
        "cascade_split_parity",
        "verification_seed",
        "verification_tag",
        "toeplitz_seed",
    }


@pytest.mark.parametrize(
    ("target", "state"),
    [
        ("detected_gates", State.BASIS_RECONCILIATION),
        ("test_indices", State.PARAMETER_ESTIMATION),
        ("cascade_permutation", State.ERROR_CORRECTION),
        ("verification_tag", State.VERIFICATION),
        ("toeplitz_seed", State.PRIVACY_AMPLIFICATION),
    ],
)
def test_tampered_transcript_aborts_without_rotating(
    target: str,
    state: State,
) -> None:
    cfg = load_config(ROOT / "configs" / "e12_mitm.yaml")
    session = MonitoredSession(cfg)
    pool = AuthenticationPool()

    def corrupt(sender: Party, kind: str, frame: bytes) -> bytes:
        return frame[:-1] + bytes((frame[-1] ^ 1,)) if kind == target else frame

    result = simulation.run_bb84_session(
        cfg,
        session=session,
        authentication=pool,
        transport=corrupt,
    )
    assert isinstance(result, AbortEvidence)
    assert result.reason == "classical authentication failed"
    assert session.events[-1].reason == "authentication tag mismatch"
    assert session.events[-1].previous_state == state
    assert session.state == State.ABORT
    assert pool.rotations == 0


def test_authenticated_session_requires_enough_bits_to_refresh() -> None:
    cfg = SessionConfig(
        bb84=BB84Config(
            n_pulses=512,
            p_z=1,
            test_fraction=0.25,
            k_min=1,
            q_max=0.2,
            eps_pe=0.2,
            ec_mode="ideal",
        ),
        channel=ChannelConfig(e_misalign=0),
    )
    pool = AuthenticationPool()
    result = simulation.run_bb84_session(cfg, authentication=pool)
    assert isinstance(result, AbortEvidence)
    assert result.reason == "insufficient key for authentication refresh"
    assert pool.rotations == 0

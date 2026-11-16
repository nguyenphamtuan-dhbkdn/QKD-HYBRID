"""Run BB84 from the simulator through key release or an evidenced abort."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from qkdsim import simulation
from qkdsim.config import AttackConfig, BB84Config, ChannelConfig, SessionConfig
from qkdsim.physics.states import BitArray
from qkdsim.postprocess.keylength import secret_key_length
from qkdsim.postprocess.result import AbortEvidence, FinalKey
from qkdsim.postprocess.verification import VerificationResult


def test_cascade_session_amplifies_both_parties_with_the_same_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SessionConfig()
    hash_fft = simulation.toeplitz_hash_fft
    outputs: list[tuple[BitArray, BitArray]] = []

    def record(bits: BitArray, out_len: int, seed_bits: BitArray) -> BitArray:
        result = hash_fft(bits, out_len, seed_bits)
        outputs.append((result, seed_bits))
        return result

    monkeypatch.setattr(simulation, "toeplitz_hash_fft", record)
    result = simulation.run_bb84_session(config)
    assert isinstance(result, FinalKey)
    (alice, alice_seed), (bob, bob_seed) = outputs
    np.testing.assert_array_equal(alice, bob)
    assert alice_seed is bob_seed
    assert len(result.key_bytes) == (result.length_bits + 7) // 8
    np.testing.assert_array_equal(
        np.unpackbits(np.frombuffer(result.key_bytes, dtype=np.uint8))[
            : result.length_bits
        ],
        alice,
    )
    assert result.key_bytes[-1] & ((1 << (-result.length_bits % 8)) - 1) == 0
    assert result.length_bits == alice.size
    assert 0 < result.qber < result.qber_ub < config.bb84.q_max
    assert result.leak_total > 64
    assert result.key_id.version == result.session_id.version == 4
    assert result.created_at.utcoffset() == timedelta(0)
    assert result.key_bytes.hex() not in repr(result)
    assert repr(result.key_bytes) not in repr(result)
    assert not result.ground_truth_eve_present


def test_session_uses_ideal_ec_and_qiskit() -> None:
    config = SessionConfig(
        bb84=BB84Config(
            n_pulses=512,
            p_z=1,
            test_fraction=0.25,
            k_min=1,
            q_max=0.2,
            eps_pe=0.2,
            ec_mode="ideal",
            backend="qiskit",
        ),
        channel=ChannelConfig(e_misalign=0),
    )
    result = simulation.run_bb84_session(config)
    assert isinstance(result, FinalKey)
    assert result.backend == "qiskit"
    assert result.qber == 0
    assert result.leak_total == 64
    assert result.length_bits == secret_key_length(
        384, result.qber_ub, 0, 64, config.bb84.eps_sec, config.bb84.eps_cor
    )


def test_eve_bookkeeping_is_available_on_accepted_simulation() -> None:
    result = simulation.run_bb84_session(
        SessionConfig(attack=AttackConfig("ir", p=0.04))
    )
    assert isinstance(result, FinalKey)
    assert result.ground_truth_eve_present


@pytest.mark.parametrize(
    ("config", "reason"),
    [
        (SessionConfig(bb84=BB84Config(n_pulses=1)), "insufficient statistics"),
        (SessionConfig(attack=AttackConfig("ir")), "qber above threshold"),
        (
            SessionConfig(bb84=BB84Config(eps_cor=1e-30)),
            "verification bound exceeds eps_cor",
        ),
        (
            SessionConfig(
                bb84=BB84Config(n_pulses=2000, test_fraction=1, p_z=1),
                channel=ChannelConfig(e_misalign=0),
            ),
            "no secret key at this QBER/length",
        ),
    ],
)
def test_session_aborts_before_privacy_amplification(
    config: SessionConfig, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_seed(n_bits: int, out_len: int) -> BitArray:
        pytest.fail("privacy amplification ran on an aborted session")

    monkeypatch.setattr(simulation, "random_toeplitz_seed", unexpected_seed)
    result = simulation.run_bb84_session(config)
    assert isinstance(result, AbortEvidence)
    assert result.reason == reason
    assert (result.stats is None) == (reason == "insufficient statistics")


def test_session_aborts_on_residual_error(monkeypatch: pytest.MonkeyPatch) -> None:
    verify_keys = simulation.verify_keys

    def verify_with_residual_error(
        key_a: BitArray, corrected: BitArray
    ) -> VerificationResult:
        bob = corrected.copy()
        bob[-1] ^= 1  # Changes only the constant term, so every seed detects it.
        return verify_keys(key_a, bob)

    monkeypatch.setattr(simulation, "verify_keys", verify_with_residual_error)
    result = simulation.run_bb84_session(
        SessionConfig(channel=ChannelConfig(e_misalign=0))
    )
    assert isinstance(result, AbortEvidence)
    assert result.reason == "verification mismatch"


def test_session_rejects_disagreeing_local_pa_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hash_fft = simulation.toeplitz_hash_fft
    calls = 0

    def disagree(bits: BitArray, out_len: int, seed_bits: BitArray) -> BitArray:
        nonlocal calls
        output = hash_fft(bits, out_len, seed_bits)
        calls += 1
        if calls == 2:
            output[0] ^= 1
        return output

    monkeypatch.setattr(simulation, "toeplitz_hash_fft", disagree)
    config = SessionConfig(channel=ChannelConfig(e_misalign=0))
    config = replace(config, bb84=replace(config.bb84, n_pulses=20_000, q_max=0.2))
    result = simulation.run_bb84_session(config)
    assert isinstance(result, AbortEvidence)
    assert result.reason == "privacy amplification mismatch"

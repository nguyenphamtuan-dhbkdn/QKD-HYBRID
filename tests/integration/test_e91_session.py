import json
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from qkdsim.auth.channel import Party
from qkdsim.auth.pool import AuthenticationPool
from qkdsim.cli import app
from qkdsim.config import AttackConfig, ChannelConfig, E91Config, SessionConfig
from qkdsim.postprocess.result import AbortEvidence, LinkKeys
from qkdsim.simulation import run_e91_link, run_e91_session


def test_e91_extracts_matching_authenticated_keys() -> None:
    cfg = SessionConfig(channel=ChannelConfig(e_misalign=0))
    authentication = AuthenticationPool()
    report = run_e91_link(cfg, authentication=authentication)
    assert report.chsh is not None
    lower = report.chsh.lower_bound(cfg.e91.chsh_z)
    assert lower is not None and lower > 2
    outcome = report.outcome
    assert isinstance(outcome, LinkKeys)
    assert outcome.alice.key_bytes == outcome.bob_bytes
    assert outcome.alice.qber == 0
    assert 0 < outcome.alice.length_bits < report.sifted
    assert outcome.alice.auth_bits == 256
    assert authentication.rotations == 1


def test_qiskit_e91_can_extract_a_key() -> None:
    cfg = SessionConfig(
        channel=ChannelConfig(e_misalign=0),
        e91=E91Config(n_pairs=70_000, backend="qiskit"),
    )
    outcome = run_e91_link(cfg).outcome
    assert isinstance(outcome, LinkKeys)
    assert outcome.alice.key_bytes == outcome.bob_bytes
    assert outcome.alice.backend == "qiskit"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"attack": AttackConfig(kind="ir")}, "CHSH violation below margin"),
        ({"e91": E91Config(n_pairs=1)}, "insufficient CHSH statistics"),
        ({"e91": E91Config(visibility=0.8)}, "qber above threshold"),
    ],
)
def test_e91_reports_abort_gate(changes: dict[str, object], reason: str) -> None:
    cfg = replace(SessionConfig(channel=ChannelConfig(e_misalign=0)), **changes)
    outcome = run_e91_session(cfg)
    assert isinstance(outcome, AbortEvidence)
    assert outcome.reason == reason


def test_chsh_transcript_is_authenticated() -> None:
    cfg = SessionConfig(channel=ChannelConfig(e_misalign=0))
    authentication = AuthenticationPool()

    def tamper(sender: Party, kind: str, frame: bytes) -> bytes:
        return frame[:-1] + bytes([frame[-1] ^ 1]) if kind == "chsh_bob" else frame

    outcome = run_e91_session(cfg, authentication=authentication, transport=tamper)
    assert isinstance(outcome, AbortEvidence)
    assert outcome.reason == "classical authentication failed"
    assert authentication.rotations == 0


def test_e91_cli_reports_bell_statistics_without_key_bytes() -> None:
    response = CliRunner().invoke(app, ["e91", "--config", "configs/e91_default.yaml"])
    assert response.exit_code == 0, response.output
    data = json.loads(response.output)
    assert data["status"] == "key_ready"
    assert data["chsh_lower"] > 2
    assert data["chsh"]["standard_error"] > 0
    assert "key_bytes" not in data

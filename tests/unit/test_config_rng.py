"""Configuration and randomness checks for the scaffold."""

from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from qkdsim.cli import app
from qkdsim.config import SessionConfig, load_config
from qkdsim.rng import SimRNG, secure_random


def test_documented_defaults() -> None:
    root = Path(__file__).resolve().parents[2]
    assert load_config(root / "configs" / "default.yaml") == SessionConfig()


def test_yaml_overrides(tmp_path: Path) -> None:
    path = tmp_path / "test.yaml"
    path.write_text("seed: 3\nchannel:\n  eta_det: 0.4\n", encoding="utf-8")
    config = load_config(path)
    assert config.seed == 3
    assert config.channel.eta_det == 0.4
    assert config.bb84 == SessionConfig().bb84
    assert CliRunner().invoke(app, ["bb84", "--config", str(path)]).exit_code == 0


@pytest.mark.parametrize(
    ("yaml", "error"),
    [
        ("[42]", "must be a mapping"),
        ("bb48: {}", "Unknown configuration sections"),
        ("seed: true", "seed must be an integer"),
        ("bb84: null", "bb84 must be a mapping"),
        ("bb84: {npulses: 1}", "Invalid bb84 configuration"),
        ("bb84: {q_max: 2}", "bb84.q_max must be in"),
        ("bb84: {test_fraction: 0}", "test_fraction must be positive"),
        ("bb84: {f_ec_ideal: 0.5}", "f_ec_ideal must be"),
        ("channel: {e_misalign: '0.1'}", "e_misalign must be a probability"),
        ("channel: {length_km: .inf}", "length_km must be a finite"),
        ("attack: {kind: unknown}", "attack.kind must be one of"),
        ("monitor: {e0: 0.5}", "monitor.e0 must be less than"),
        ("bb84: {", "Invalid YAML"),
    ],
)
def test_invalid_config(yaml: str, error: str, tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml, encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        load_config(path)


def test_cli_config_error(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    result = CliRunner().invoke(app, ["bb84", "--config", str(path)])
    assert result.exit_code == 2
    assert "missing.yaml" in result.output


def test_sim_rng_is_reproducible() -> None:
    rng = SimRNG(7)
    generator = rng.generator
    assert generator is rng.generator
    values = generator.integers(0, 256, size=32, dtype=np.uint8)
    np.testing.assert_array_equal(
        values,
        SimRNG(7).generator.integers(0, 256, size=32, dtype=np.uint8),
    )


def test_secure_random_uses_os_entropy(monkeypatch: pytest.MonkeyPatch) -> None:
    def token_bytes(n_bytes: int) -> bytes:
        return b"\xaa" * n_bytes

    monkeypatch.setattr("qkdsim.rng.secrets.token_bytes", token_bytes)
    assert secure_random(8) == b"\xaa" * 8

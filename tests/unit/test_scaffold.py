"""Smoke test for the package and installed entry point."""

from typer.testing import CliRunner

from qkdsim.cli import app
from qkdsim.config import SessionConfig, load_config


def test_scaffold() -> None:
    assert load_config() == SessionConfig()
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "bb84" in result.output

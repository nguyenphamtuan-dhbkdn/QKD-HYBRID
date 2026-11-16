"""Ensure the CLI exposes aggregate results and keeps Eve data private."""

import ast
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import qkdsim.protocols
from qkdsim.cli import app

ROOT = Path(__file__).resolve().parents[2]


def test_protocol_modules_cannot_import_ground_truth() -> None:
    assert qkdsim.protocols.__file__ is not None
    protocol_dir = Path(qkdsim.protocols.__file__).parent
    for path in protocol_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                forbidden = {"GroundTruth", "attacks", "intercept_resend", "simulation"}
                assert all(forbidden.isdisjoint(name.split(".")) for name in names), (
                    path
                )


@pytest.mark.parametrize(
    ("config", "status"),
    [("bb84_noiseless.yaml", "accepted"), ("bb84_eve_full.yaml", "abort")],
)
def test_bb84_cli_summaries(config: str, status: str) -> None:
    path = ROOT / "configs" / config
    result = CliRunner().invoke(app, ["bb84", "--config", str(path)])
    assert result.exit_code == 0, result.exception
    summary = json.loads(result.output)
    assert summary["status"] == status
    assert set(summary) == {
        "seed",
        "sent",
        "detected",
        "double_clicks",
        "sifted",
        "status",
        "k",
        "errors",
        "q_est",
        "q_ub",
        "clopper_pearson",
        "wilson",
        *({"remaining"} if status == "accepted" else {"reason", "planned_k"}),
    }
    if status == "accepted":
        assert summary["q_est"] == 0
        assert summary["remaining"] + summary["k"] == summary["sifted"]
    else:
        assert summary["reason"] == "qber above threshold"


def test_bb84_cli_reports_insufficient_statistics(tmp_path: Path) -> None:
    path = tmp_path / "tiny.yaml"
    path.write_text("bb84: {n_pulses: 1}", encoding="utf-8")
    result = CliRunner().invoke(app, ["bb84", "--config", str(path)])
    assert result.exit_code == 0
    summary = json.loads(result.output)
    assert summary["reason"] == "insufficient statistics"
    assert "q_est" not in summary


@pytest.mark.parametrize("yaml", ["bb84: {backend: qiskit}", "attack: {kind: pns}"])
def test_bb84_cli_rejects_disabled_modes(yaml: str, tmp_path: Path) -> None:
    path = tmp_path / "mode.yaml"
    path.write_text(yaml, encoding="utf-8")
    result = CliRunner().invoke(app, ["bb84", "--config", str(path)])
    assert result.exit_code == 2
    assert "currently supports" in result.output

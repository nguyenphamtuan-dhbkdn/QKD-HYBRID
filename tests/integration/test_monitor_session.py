"""Exercise the CLI evidence paths and the application's session lifecycle."""

import json
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from typer.testing import CliRunner

from qkdsim.cli import app
from qkdsim.config import AttackConfig, BB84Config, MonitorConfig, SessionConfig
from qkdsim.monitor.calibration import Calibration
from qkdsim.monitor.policy import SessionUnavailable
from qkdsim.monitor.session import MonitoredSession, State
from qkdsim.postprocess.result import AbortEvidence, FinalKey
from qkdsim.simulation import run_bb84_session

ROOT = Path(__file__).resolve().parents[2]


def test_monitor_cli_writes_valid_events_and_public_abort_evidence(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        app,
        [
            "monitor",
            "--config",
            str(ROOT / "configs" / "bb84_eve_full.yaml"),
            "--detector",
            "ci",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.exception
    summary = json.loads(result.output)
    assert summary["status"] == "abort"
    output = Path(summary["directory"])
    draft = files("qkdsim.monitor").joinpath("event.schema.json")
    schema = json.loads(draft.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    events = [
        json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()
    ]
    for event in events:
        validator.validate(event)
        assert event["session_id"] == summary["session_id"]
    assert [event["state"] for event in events] == [
        "INIT",
        "QUANTUM_TX",
        "BASIS_RECONCILIATION",
        "PARAMETER_ESTIMATION",
        "ABORT",
    ]
    report = json.loads((output / "evidence.json").read_text())
    assert report["reason"] == "qber above threshold"
    assert report["detector"]["outcome"] == "alarm"
    assert report["counters"] == events[-1]["counters"]
    assert report["windows"][-1]["cumulative_qber"] == report["metrics"]["qber"]
    assert (
        sum(window["compared"] for window in report["windows"])
        == (report["counters"]["compared"])
    )
    assert report["metrics"]["qber_z"] != report["metrics"]["qber_x"]
    assert (output / report["plot"]).read_bytes().startswith(b"\x89PNG")
    assert "ground_truth" not in json.dumps(report)
    assert "key_bytes" not in json.dumps(report)


def test_rekey_reuses_controller_with_new_session_id() -> None:
    cfg = SessionConfig(
        bb84=BB84Config(n_pulses=40_000),
        monitor=MonitorConfig(max_msgs=1),
    )
    session = MonitoredSession(cfg)
    result = run_bb84_session(cfg, session=session)
    assert isinstance(result, FinalKey)
    assert [event.state for event in session.events] == [
        State.INIT,
        State.QUANTUM_TX,
        State.BASIS_RECONCILIATION,
        State.PARAMETER_ESTIMATION,
        State.ERROR_CORRECTION,
        State.VERIFICATION,
        State.PRIVACY_AMPLIFICATION,
        State.KEY_READY,
    ]
    session.authorize_message(10)
    assert session.state == State.KEY_IN_USE
    with pytest.raises(SessionUnavailable, match="message limit"):
        session.authorize_message(1)
    renewed = run_bb84_session(cfg, session=session)
    assert isinstance(renewed, FinalKey)
    assert renewed.session_id != result.session_id
    assert any(event.reason == "message limit exceeded" for event in session.events)


def test_detector_can_abort_below_the_finite_key_threshold() -> None:
    base = SessionConfig()
    cfg = replace(
        base,
        attack=AttackConfig("ir", p=0.15),
        monitor=MonitorConfig(detector="ci"),
    )
    session = MonitoredSession(cfg)
    result = run_bb84_session(cfg, session=session)
    assert isinstance(result, AbortEvidence)
    assert result.reason == "monitor alarm"
    assert result.stats is not None and result.stats.q_ub < cfg.bb84.q_max
    with pytest.raises(SessionUnavailable, match="no usable key"):
        session.authorize_message(1)


def test_calibration_uses_honest_pilot_and_empty_gates(tmp_path: Path) -> None:
    path = tmp_path / "calibration.json"
    result = CliRunner().invoke(
        app,
        [
            "calibrate",
            "--config",
            str(ROOT / "configs" / "bb84_eve_full.yaml"),
            "--output",
            str(path),
            "--pulses",
            "10000",
        ],
    )
    assert result.exit_code == 0, result.exception
    calibration = Calibration.read(path)
    assert calibration.sent == calibration.detected == calibration.empty_gates == 10_000
    assert calibration.qber == 0
    assert calibration.empty_clicks == 0
    session = MonitoredSession(SessionConfig(), calibration=calibration)
    assert session.settings.e0 == 0 and session.y0 == 1


def test_insufficient_statistics_generates_empty_evidence(tmp_path: Path) -> None:
    cfg = SessionConfig(bb84=BB84Config(n_pulses=1))
    session = MonitoredSession(cfg, output=tmp_path)
    result = run_bb84_session(cfg, session=session)
    assert isinstance(result, AbortEvidence)
    assert result.reason == "insufficient statistics"
    assert session.directory is not None
    assert (
        json.loads((session.directory / "evidence.json").read_text())["windows"] == []
    )

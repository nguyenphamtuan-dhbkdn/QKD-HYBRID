"""Command-line entry point."""

import json
import subprocess
import sys
from dataclasses import asdict, replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from qkdsim._terminal import configure_utf8
from qkdsim.auth.pool import AuthenticationPool
from qkdsim.config import load_config
from qkdsim.file_demo import decrypt, encrypt
from qkdsim.monitor.calibration import Calibration
from qkdsim.monitor.session import MonitoredSession
from qkdsim.postprocess.estimation import ParameterAbort, estimate_parameters
from qkdsim.postprocess.result import AbortEvidence, FinalKey
from qkdsim.postprocess.sifting import sift
from qkdsim.rng import SimRNG
from qkdsim.simulation import (
    calibrate_bb84,
    run_bb84_session,
    run_e91_link,
    simulate_bb84,
)

app = typer.Typer(
    help="Mô phỏng phân phối khóa lượng tử.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
app.command()(encrypt)
app.command()(decrypt)


def _experiment_suite(*args: str) -> None:
    """Run repository research assets in the CLI's current Python environment."""
    script = Path(__file__).resolve().parents[2] / "experiments" / "run_all.py"
    if not script.is_file():
        typer.echo("Lệnh thí nghiệm cần bản sao mã nguồn của QKD-HYBRID.", err=True)
        raise typer.Exit(1)
    result = subprocess.run([sys.executable, str(script), *args], check=False)
    if result.returncode:
        raise typer.Exit(result.returncode)


@app.command()
def experiment(
    name: Annotated[str, typer.Argument(help="Mã thí nghiệm E1–E15.")],
    quick: Annotated[bool, typer.Option()] = False,
) -> None:
    """Chạy riêng một thí nghiệm."""
    code = name.upper()
    if not code.startswith("E") or not code[1:].isdigit():
        raise typer.BadParameter("Dùng mã E1 đến E15.")
    number = int(code[1:])
    if not 1 <= number <= 15:
        raise typer.BadParameter("Dùng mã E1 đến E15.")
    _experiment_suite("--only", str(number), *(("--quick",) if quick else ()))


@app.command()
def experiments(
    quick: Annotated[bool, typer.Option()] = False,
    all_experiments: Annotated[
        bool, typer.Option("--all", help="Chạy tất cả E1–E15.")
    ] = False,
) -> None:
    """Chạy toàn bộ E1–E15."""
    if not all_experiments:
        raise typer.BadParameter("Dùng --all để chạy E1–E15.")
    _experiment_suite(*(("--quick",) if quick else ()))


@app.callback()
def root() -> None:
    """Expose the command group."""


@app.command()
def bb84(
    config: Annotated[Path | None, typer.Option(help="Tệp cấu hình YAML.")] = None,
) -> None:
    """Mô phỏng BB84 và xuất số liệu ước lượng QBER dưới dạng JSON."""
    try:
        settings = load_config(config)
        rng = SimRNG(settings.seed).generator
        observed, _ = simulate_bb84(settings, rng)
        sifted = sift(observed)
        estimate = estimate_parameters(sifted, settings.bb84, rng)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--config") from exc

    summary: dict[str, object] = {
        "seed": settings.seed,
        "sent": sifted.sent,
        "detected": sifted.detected,
        "double_clicks": observed.double_clicks,
        "sifted": sifted.sifted,
    }
    if isinstance(estimate, ParameterAbort):
        summary.update(
            status="abort",
            reason=estimate.reason,
            planned_k=estimate.planned_sample_size,
        )
    else:
        summary.update(status="accepted", remaining=estimate.alice_remaining.size)

    if estimate.stats is not None:
        summary.update(
            k=estimate.stats.sample_size,
            errors=estimate.stats.errors,
            q_est=estimate.stats.q_est,
            q_ub=estimate.stats.q_ub,
            clopper_pearson=estimate.stats.clopper_pearson,
            wilson=estimate.stats.wilson,
        )
    typer.echo(json.dumps(summary))


@app.command()
def e91(
    config: Annotated[Path | None, typer.Option(help="Tệp cấu hình YAML.")] = None,
) -> None:
    """Mô phỏng E91 và xuất thống kê CHSH cùng kết quả tạo khóa."""
    try:
        settings = load_config(config)
        result = run_e91_link(settings, authentication=AuthenticationPool())
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--config") from exc
    bell = result.chsh
    summary: dict[str, object] = {
        "seed": settings.seed,
        "backend": settings.e91.backend,
        "sent": result.sent,
        "coincident": result.coincident,
        "sifted": result.sifted,
        "chsh": asdict(bell) if bell is not None else None,
        "chsh_lower": bell.lower_bound(settings.e91.chsh_z) if bell else None,
    }
    if isinstance(result.outcome, AbortEvidence):
        summary.update(status="abort", reason=result.outcome.reason)
        if result.outcome.stats is not None:
            summary.update(
                q_est=result.outcome.stats.q_est, q_ub=result.outcome.stats.q_ub
            )
    else:
        key = result.outcome.alice
        summary.update(
            status="key_ready",
            length_bits=key.length_bits,
            q_est=key.qber,
            q_ub=key.qber_ub,
            auth_bits=key.auth_bits,
            net_key_rate=key.net_key_rate,
        )
    typer.echo(json.dumps(summary, allow_nan=False))


class DetectorOption(StrEnum):
    """Monitor modes exposed by the CLI."""

    threshold = "threshold"
    ci = "ci"
    sprt = "sprt"
    cusum = "cusum"
    joint = "joint"


@app.command()
def monitor(
    config: Annotated[Path | None, typer.Option(help="Tệp cấu hình YAML.")] = None,
    detector: Annotated[DetectorOption | None, typer.Option()] = None,
    calibration: Annotated[Path | None, typer.Option(help="Tệp hiệu chuẩn.")] = None,
    output: Annotated[Path, typer.Option(help="Thư mục lưu kết quả phiên.")] = Path(
        "results/monitor",
    ),
) -> None:
    """Chạy phiên BB84 có giám sát và ghi nhật ký cùng bằng chứng khi dừng."""
    try:
        settings = load_config(config)
        if detector is not None:
            settings = replace(
                settings,
                monitor=replace(
                    settings.monitor,
                    detector=detector.value,
                ),
            )
        baseline = Calibration.read(calibration) if calibration is not None else None
        session = MonitoredSession(settings, output=output, calibration=baseline)
        result = run_bb84_session(
            settings,
            session=session,
            authentication=AuthenticationPool(),
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    summary = session.events[-1].to_dict()
    summary["directory"] = str(session.directory)
    summary["status"] = "abort" if isinstance(result, AbortEvidence) else "key_ready"
    if isinstance(result, FinalKey):
        summary.update(
            length_bits=result.length_bits,
            gross_length_bits=result.gross_length_bits,
            auth_bits=result.auth_bits,
            net_key_rate=result.net_key_rate,
        )
    typer.echo(json.dumps(summary, allow_nan=False))


@app.command()
def calibrate(
    config: Annotated[Path | None, typer.Option(help="Tệp cấu hình YAML.")] = None,
    output: Annotated[Path, typer.Option()] = Path("calibration.json"),
    pulses: Annotated[int, typer.Option(min=1)] = 100_000,
) -> None:
    """Đo QBER nền, tỷ lệ phát hiện và tỷ lệ đếm tối trên cổng trống."""
    try:
        calibrate_bb84(load_config(config), pulses=pulses, empty_gates=pulses).write(
            output,
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def main() -> None:
    """Run the Typer command group."""
    configure_utf8()
    app()

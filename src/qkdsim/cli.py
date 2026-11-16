"""Command-line entry point."""

import json
from pathlib import Path
from typing import Annotated

import typer

from qkdsim.config import load_config
from qkdsim.postprocess.estimation import ParameterAbort, estimate_parameters
from qkdsim.postprocess.sifting import sift
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_bb84

app = typer.Typer(help="Mô phỏng phân phối khóa lượng tử.", no_args_is_help=True)


@app.callback()
def root() -> None:
    """Expose a command group even when only BB84 is registered."""


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


def main() -> None:
    """Run the Typer command group."""
    app()

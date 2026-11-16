"""Measure BB84 simulation wall time for increasing pulse counts."""

import json
import platform
import subprocess
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Literal

from qkdsim.config import BB84Config, ChannelConfig, SessionConfig
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_bb84

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Time each backend after warm-up and save samples and provenance."""
    samples: list[dict[str, object]] = []
    config = SessionConfig(channel=ChannelConfig(e_misalign=0, depol=0.2))
    backends: tuple[Literal["fast", "qiskit"], ...] = ("fast", "qiskit")
    for backend in backends:
        warmup = replace(config, bb84=BB84Config(n_pulses=32, backend=backend))
        simulate_bb84(warmup, SimRNG(warmup.seed).generator)
        for size in (250, 500, 1_000, 2_000):
            settings = replace(config, bb84=BB84Config(n_pulses=size, backend=backend))
            elapsed = []
            for _ in range(3):
                rng = SimRNG(settings.seed).generator
                start = perf_counter()
                simulate_bb84(settings, rng)
                elapsed.append(perf_counter() - start)
            samples.append(
                {
                    "config": asdict(settings),
                    "seconds": elapsed,
                    "median_seconds": median(elapsed),
                }
            )

    report = {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT
            )
        ),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "library_versions": {
            name: version(name) for name in ("numpy", "qiskit", "qiskit-aer")
        },
        "samples": samples,
    }
    out = ROOT / "results" / "bb84_backend_scaling.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

"""Measure Eve's actual BB84 key agreement with and without authentication."""

import argparse
import json
import platform
import subprocess
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from qkdsim.analysis.stats import clopper_pearson
from qkdsim.attacks.mitm_classical import run_classical_mitm
from qkdsim.config import load_config
from qkdsim.rng import SimRNG

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Write experiment counts, intervals, and reproduction metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "e12_mitm.yaml"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "results" / "e12_mitm.json"
    )
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    config = load_config(args.config)
    rng = SimRNG(config.seed).generator
    modes = {}
    for authenticated in (False, True):
        successes = mismatches = alice_known = bob_known = 0
        for _ in range(args.trials):
            outcome = run_classical_mitm(config, rng, authenticated=authenticated)
            successes += outcome.succeeded
            alice_known += outcome.alice_key_known_to_eve
            bob_known += outcome.bob_key_known_to_eve
            mismatches += (
                outcome.alice_abort
                == outcome.bob_abort
                == "authentication tag mismatch"
            )
        modes["authenticated" if authenticated else "unauthenticated"] = {
            "trials": args.trials,
            "eve_successes": successes,
            "eve_success_rate": successes / args.trials,
            "eve_success_clopper_pearson": clopper_pearson(successes, args.trials),
            "alice_keys_known_to_eve": alice_known,
            "bob_keys_known_to_eve": bob_known,
            "both_links_rejected_bad_tags": mismatches,
        }
    report = {
        "config": asdict(config),
        "seed": config.seed,
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=ROOT,
            )
        ),
        "python": platform.python_version(),
        "library_versions": {name: version(name) for name in ("numpy", "scipy")},
        "auth_key_and_pa_seed_source": "OS entropy",
        "modes": modes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

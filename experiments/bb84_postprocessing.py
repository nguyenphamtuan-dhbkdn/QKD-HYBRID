"""Measure the Cascade and million-bit privacy-amplification M3 criteria."""

import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np

from qkdsim.postprocess.cascade import cascade_reconcile
from qkdsim.postprocess.privacy_amp import random_toeplitz_seed, toeplitz_hash_fft
from qkdsim.rng import SimRNG

ROOT = Path(__file__).resolve().parents[1]


def cascade_trials(
    n: int, trials: int, passes: int, seed: int
) -> list[dict[str, int | float]]:
    """Measure reconciliation at fixed QBER with uniformly placed errors."""
    rng = SimRNG(seed).generator
    samples = []
    for percentage in (1, 3, 5, 8):
        successes = 0
        max_efficiency = 0.0
        errors = n * percentage // 100
        qber = errors / n
        for _ in range(trials):
            alice = rng.integers(0, 2, n, dtype=np.uint8)
            bob = alice.copy()
            bob[rng.choice(n, errors, replace=False)] ^= 1
            result = cascade_reconcile(alice, bob, qber, rng, passes=passes)
            successes += int(np.array_equal(alice, result.key_b_corrected))
            assert result.f_ec is not None
            max_efficiency = max(max_efficiency, result.f_ec)
        samples.append(
            {
                "qber": qber,
                "successes": successes,
                "success_rate": successes / trials,
                "max_f_ec": max_efficiency,
            }
        )
    return samples


def time_pa(n: int, length: int, trials: int, seed: int) -> list[float]:
    """Time FFT hashing and check selected rows by direct dot products."""
    rng = SimRNG(seed).generator
    bits = rng.integers(0, 2, n, dtype=np.uint8)
    toeplitz_seed = random_toeplitz_seed(n, length)
    toeplitz_hash_fft(bits[:32], 32, toeplitz_seed[:63])
    rows = (0, 1, length // 2, length - 2, length - 1)
    expected = [
        np.count_nonzero(bits & toeplitz_seed[row : row + n][::-1]) % 2 for row in rows
    ]
    elapsed = []
    for _ in range(trials):
        start = perf_counter()
        out = toeplitz_hash_fft(bits, length, toeplitz_seed)
        elapsed.append(perf_counter() - start)
        assert out.size == length
        np.testing.assert_array_equal(out[list(rows)], expected)
    return elapsed


def main() -> None:
    """Write measurements and provenance before enforcing acceptance limits."""
    cascade_config = {"n": 16_000, "trials": 1000, "passes": 4, "seed": 432_015}
    pa_config = {"n": 1_000_000, "length": 1_000_000, "trials": 3, "seed": 73}
    elapsed = time_pa(**pa_config)
    cascade = cascade_trials(**cascade_config)
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
        "library_versions": {name: version(name) for name in ("numpy", "scipy")},
        "cascade": {"config": cascade_config, "samples": cascade},
        "privacy_amplification": {
            "config": {**pa_config, "toeplitz_seed_source": "OS entropy"},
            "seconds": elapsed,
            "median_seconds": median(elapsed),
        },
    }
    out = ROOT / "results" / "bb84_postprocessing.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    assert max(elapsed) < 30, f"FFT privacy amplification exceeded 30 s. See {out}"
    for sample in cascade:
        assert sample["success_rate"] >= 0.999, (
            f"Cascade success below target. See {out}"
        )
        assert sample["max_f_ec"] < 1.4, f"Cascade efficiency above target. See {out}"


if __name__ == "__main__":
    main()

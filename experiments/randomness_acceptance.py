"""Apply the M8 randomness diagnostics to BB84 keys and three bit sources."""

import json
from dataclasses import asdict, replace

import numpy as np
from _provenance import ROOT, provenance

from qkdsim.analysis.randomness import analyze_randomness
from qkdsim.config import load_config
from qkdsim.postprocess.result import AbortEvidence
from qkdsim.postprocess.sifting import sift
from qkdsim.qrng import generate_qrng_bits
from qkdsim.rng import SimRNG, secure_random
from qkdsim.simulation import run_bb84_session, simulate_bb84


def main() -> None:
    """Write aggregate p-values only, with equal-length bit samples."""
    config = load_config(ROOT / "configs" / "bb84_noiseless.yaml")
    config = replace(config, bb84=replace(config.bb84, basis_source="qrng"))
    rng = SimRNG(config.seed).generator
    n_bits = 16_384
    alpha = 0.01
    observed, _ = simulate_bb84(config, rng)
    raw = sift(observed).alice_bits
    final = run_bb84_session(config, rng)
    if isinstance(final, AbortEvidence):
        raise RuntimeError(f"BB84 aborted while generating a sample: {final.reason}")
    if min(raw.size, final.length_bits) < n_bits:
        raise RuntimeError("insufficient BB84 key bits for the configured sample size")
    final_bits = np.unpackbits(
        np.frombuffer(final.key_bytes, dtype=np.uint8), count=n_bits
    )
    samples = {
        "bb84_raw_qrng_bases": raw[:n_bits],
        "bb84_final_qrng_bases": final_bits,
        "numpy": rng.integers(0, 2, size=n_bits, dtype=np.uint8),
        "aer_hadamard": generate_qrng_bits(n_bits, rng),
        "secrets": np.unpackbits(
            np.frombuffer(secure_random(n_bits // 8), dtype=np.uint8)
        ),
    }
    diagnostics = {}
    for name, bits in samples.items():
        analyzed = analyze_randomness(bits)
        diagnostics[name] = {
            **asdict(analyzed),
            "below_alpha": [
                test
                for test, p in analyzed.p_values.items()
                if p is not None and p < alpha
            ],
        }
    report = {
        **provenance("numpy", "scipy", "qiskit", "qiskit-aer"),
        "config": {
            "session": asdict(config),
            "alpha_per_test": alpha,
            "bits_per_sample": n_bits,
        },
        "seed": config.seed,
        "unseeded_sources": [
            "OS randomness for final-key privacy amplification",
            "secrets",
        ],
        "samples": diagnostics,
    }
    output = ROOT / "results" / "randomness_acceptance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

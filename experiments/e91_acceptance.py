"""Measure the M7 Werner and full intercept-resend acceptance points."""

import json
import math
from dataclasses import asdict, replace

import numpy as np
from _provenance import ROOT, provenance

from qkdsim.analysis.chsh import CHSH_SETTINGS, estimate_chsh
from qkdsim.config import AttackConfig, SessionConfig, load_config
from qkdsim.protocols.e91 import ALICE_ANGLES, BOB_ANGLES, sift_e91
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_e91


def expected_correlation(config: SessionConfig, a: float, b: float) -> float:
    """Evaluate the ideal correlation or the full-IR correlation for the sweep."""
    visibility = config.e91.visibility
    if config.attack.kind == "none":
        return visibility * math.cos(a - b)
    if config.attack.basis_mode == "random":
        return visibility * math.cos(a - b) / 2
    eve = 0.0 if config.attack.basis_mode == "fixed_z" else math.pi / 2
    return visibility * math.cos(a - eve) * math.cos(b - eve)


def main() -> None:
    """Write raw counts, measured rates, and analytic expectations for both backends."""
    base = load_config(ROOT / "configs" / "e91_default.yaml")
    base = replace(base, channel=replace(base.channel, e_misalign=0))
    points = []
    for backend in ("fast", "qiskit"):
        for visibility, attack in (
            *((v, AttackConfig()) for v in (0.6, 0.8, 0.9, 1.0)),
            (1.0, AttackConfig(kind="ir")),
            (1.0, AttackConfig(kind="ir", basis_mode="fixed_z")),
            (1.0, AttackConfig(kind="ir", basis_mode="fixed_x")),
        ):
            config = replace(
                base,
                e91=replace(base.e91, backend=backend, visibility=visibility),
                attack=attack,
            )
            observed, _ = simulate_e91(config, SimRNG(config.seed).generator)
            chsh = estimate_chsh(observed)
            lower = chsh.lower_bound(config.e91.chsh_z)
            sifted = sift_e91(observed)
            errors = int(np.count_nonzero(sifted.alice_bits != sifted.bob_bits))
            key_qber = errors / sifted.sifted
            expected_qber = (
                1
                - sum(
                    expected_correlation(
                        config, ALICE_ANGLES[index], BOB_ANGLES[index - 1]
                    )
                    for index in (1, 2)
                )
                / 2
            ) / 2
            correlations = [
                expected_correlation(config, ALICE_ANGLES[a], BOB_ANGLES[b])
                for a, b, _ in CHSH_SETTINGS
            ]
            expected_s = sum(
                term[2] * e for term, e in zip(CHSH_SETTINGS, correlations, strict=True)
            )
            s_sigma = math.sqrt(
                sum(
                    (1 - e**2) / n
                    for e, n in zip(correlations, chsh.counts, strict=True)
                )
            )
            qber_sigma = math.sqrt(expected_qber * (1 - expected_qber) / sifted.sifted)
            if chsh.s is None:
                raise RuntimeError("CHSH groups missing from the acceptance sweep")
            points.append(
                {
                    "config": asdict(config),
                    "chsh": asdict(chsh),
                    "chsh_lower": lower,
                    "passes_chsh_gate": lower is not None and lower > 2,
                    "coincident": sifted.detected,
                    "key_pairs": sifted.sifted,
                    "key_pair_errors": errors,
                    "key_pair_qber": key_qber,
                    "expected_s": expected_s,
                    "expected_key_pair_qber": expected_qber,
                    "s_within_4_sigma": abs(chsh.s - expected_s) <= 4 * s_sigma,
                    "qber_within_4_sigma": abs(key_qber - expected_qber)
                    <= 4 * qber_sigma,
                }
            )
    report = {
        **provenance("numpy", "scipy", "qiskit", "qiskit-aer"),
        "seed": base.seed,
        "chsh_settings": CHSH_SETTINGS,
        "points": points,
    }
    output = ROOT / "results" / "e91_acceptance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

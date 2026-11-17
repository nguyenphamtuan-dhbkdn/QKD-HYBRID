"""E13–E15: detector operating characteristics, bit diagnostics, and Grover."""

from dataclasses import replace
from statistics import mean

import numpy as np
from _protocols import settings
from _suite import Experiment
from numpy.typing import NDArray
from scipy.stats import binom  # type: ignore[import-untyped]

from qkdsim.analysis.quantum_security import security_rows
from qkdsim.analysis.randomness import analyze_randomness
from qkdsim.analysis.theory import qber_ir
from qkdsim.config import BB84Config, MonitorConfig
from qkdsim.monitor.detectors import DetectorName, evaluate
from qkdsim.postprocess.result import AbortEvidence
from qkdsim.postprocess.sifting import sift
from qkdsim.qrng import generate_qrng_bits
from qkdsim.rng import secure_random
from qkdsim.simulation import run_bb84_session, simulate_bb84

DETECTORS: tuple[DetectorName, ...] = ("threshold", "ci", "sprt", "cusum", "joint")
DESIGN_DETECTORS: tuple[DetectorName, ...] = ("ci", "sprt")


def fixed_horizon(e0: float, e1: float, alpha: float, beta: float, maximum: int) -> int:
    """Find the first exact binomial horizon with size < alpha and power >= 1-beta."""
    sizes = np.arange(1, maximum + 1)
    critical = binom.isf(alpha, sizes, e0) + 1
    critical += binom.sf(critical - 1, sizes, e0) >= alpha
    eligible = sizes[binom.cdf(critical - 1, sizes, e1) <= beta]
    return int(eligible[0]) if eligible.size else maximum


def e13(exp: Experiment) -> None:
    """Compare detectors on paired honest, steady IR, and delayed burst traces."""
    opt = exp.options
    sample, sent, yield_rate = (
        int(opt["sample"]),
        int(opt["sent"]),
        float(opt["yield_rate"]),
    )
    honest_trials = exp.repeats if exp.quick else opt["honest_repeats"]
    draws: NDArray[np.float64] = np.empty((honest_trials, sample))
    clicks = []
    for i in range(honest_trials):
        rng = exp.rng(i)
        draws[i] = rng.random(sample)
        clicks.append(int(rng.binomial(sent, yield_rate)))
    alternative = draws[: exp.repeats]
    for noise in opt["noise"]:
        base = MonitorConfig(e0=noise)
        # The same trace realizations are reused by every detector and operating point.
        honest = np.less(draws, noise)
        for alpha, q_max in zip(opt["alpha"], opt["q_max"], strict=True):
            horizon = fixed_horizon(noise, base.e1, alpha, base.beta, sample)
            if alpha == opt["alpha"][0]:
                for detector in DESIGN_DETECTORS:
                    count = horizon if detector == "ci" else sample
                    design = replace(base, detector=detector, alpha=alpha)
                    outcomes = [
                        evaluate(
                            trace[:count],
                            sent=sent,
                            detected=n,
                            y0=yield_rate,
                            config=design,
                            bb84=BB84Config(),
                        )
                        for trace, n in zip(
                            np.less(alternative, base.e1),
                            clicks[: exp.repeats],
                            strict=True,
                        )
                    ]
                    label = f"{detector} · Q₀={noise:g}"
                    exp.proportion(
                        "design_power",
                        label,
                        noise,
                        sum(d.outcome == "alarm" for d in outcomes),
                        exp.repeats,
                        alpha=alpha,
                        beta=base.beta,
                        alternative=base.e1,
                    )
                    exp.mean(
                        "design_bits",
                        label,
                        noise,
                        [float(d.compared) for d in outcomes],
                    )
            for detector in DETECTORS:
                settings_bb84 = BB84Config(q_max=q_max)
                cfg = replace(base, detector=detector, alpha=alpha)
                count = horizon if detector == "ci" else sample
                false = sum(
                    evaluate(
                        trace[:count],
                        sent=sent,
                        detected=n,
                        y0=yield_rate,
                        config=cfg,
                        bb84=settings_bb84,
                    ).outcome
                    == "alarm"
                    for trace, n in zip(honest, clicks, strict=True)
                )
                fpr = false / honest_trials
                label = f"{detector} · Q₀={noise:g}"
                exp.proportion(
                    "threshold_fpr" if detector == "threshold" else "fpr",
                    label,
                    q_max if detector == "threshold" else alpha,
                    false,
                    honest_trials,
                    horizon=count,
                    q_max=q_max,
                )
                for p in opt["fractions"]:
                    onset = sample - round(p * sample)
                    burst = np.where(
                        np.arange(sample) < onset, noise, qber_ir(1, noise)
                    )
                    for mode, errors in (
                        ("steady", np.less(alternative, qber_ir(p, noise))),
                        ("adaptive", np.less(alternative, burst)),
                    ):
                        outcomes = [
                            evaluate(
                                trace[:count],
                                sent=sent,
                                detected=n,
                                y0=yield_rate,
                                config=cfg,
                                bb84=settings_bb84,
                            )
                            for trace, n in zip(
                                errors, clicks[: exp.repeats], strict=True
                            )
                        ]
                        alarms = [d.compared for d in outcomes if d.outcome == "alarm"]
                        details = dict(
                            alpha=None if detector == "threshold" else alpha,
                            q_max=q_max if detector == "threshold" else None,
                            false_alarms=false,
                            honest_trials=honest_trials,
                            eve_fraction=p,
                            noise=noise,
                            mode=mode,
                            horizon=count,
                            inconclusive=sum(
                                d.outcome == "inconclusive" for d in outcomes
                            ),
                        )
                        exp.proportion(
                            "roc",
                            f"{label} · p={p:g} · {mode}",
                            fpr,
                            len(alarms),
                            exp.repeats,
                            **details,
                        )
                        if (detector == "threshold" and q_max == opt["q_max"][0]) or (
                            detector != "threshold" and alpha == opt["alpha"][0]
                        ):
                            p25, p50, p75 = (
                                (
                                    float(q)
                                    for q in np.quantile(alarms, [0.25, 0.5, 0.75])
                                )
                                if alarms
                                else (None, None, None)
                            )
                            exp.proportion(
                                "tpr",
                                f"{label} · {mode}",
                                p,
                                len(alarms),
                                exp.repeats,
                                **details,
                            )
                            exp.mean(
                                "delay",
                                f"{label} · {mode}",
                                p,
                                [float(delay) for delay in alarms],
                                **details,
                                average_decision_bits=mean(
                                    d.compared for d in outcomes
                                ),
                                p25=p25,
                                median=p50,
                                p75=p75,
                            )


def e14(exp: Experiment) -> None:
    """Record every sample p-value and summarize per-test pass rates."""
    cfg = settings(exp.options["pulses"], ideal_ec=True)
    n = int(exp.options["bits"])
    alpha = float(exp.options["alpha"])
    all_values: dict[tuple[str, str], list[float]] = {}
    for i in range(exp.repeats):
        rng = exp.rng(i)
        raw = sift(simulate_bb84(cfg, rng)[0]).alice_bits[:n]
        final = run_bb84_session(cfg, rng)
        if isinstance(final, AbortEvidence) or min(final.length_bits, raw.size) < n:
            raise RuntimeError("insufficient bits for E14")
        samples = {
            "BB84 raw": raw,
            "BB84 final": np.unpackbits(
                np.frombuffer(final.key_bytes, dtype=np.uint8), count=n
            ),
            "NumPy": rng.integers(0, 2, size=n, dtype=np.uint8),
            "Aer QRNG": generate_qrng_bits(n, rng),
            "secrets": np.unpackbits(
                np.frombuffer(secure_random((n + 7) // 8), dtype=np.uint8), count=n
            ),
        }
        for label, bits in samples.items():
            result = analyze_randomness(bits)
            exp.point("min_entropy", label, i + 1, result.min_entropy, bits=n)
            for name, p_value in result.p_values.items():
                exp.point(
                    "p_value",
                    label,
                    name,
                    p_value,
                    trial=i + 1,
                    bits=n,
                    reference=alpha,
                )
                if p_value is not None:
                    all_values.setdefault((label, name), []).append(p_value)
    for (label, name), values in all_values.items():
        exp.proportion(
            "pass",
            label,
            name,
            sum(p >= alpha for p in values),
            len(values),
            reference=1 - alpha,
        )


def e15(exp: Experiment) -> None:
    """Serialize the NIST equivalence classes and generic quantum query models."""
    for row in security_rows():
        exp.point(
            "security",
            "classical",
            row.primitive,
            row.classical_bits,
            key_bits=row.key_bits,
        )
        exp.point(
            "security",
            "quantum",
            row.primitive,
            row.quantum_query_bits,
            key_bits=row.key_bits,
            attack=row.quantum_attack,
            cost_model=row.quantum_cost_model,
        )

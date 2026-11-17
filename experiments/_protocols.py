"""E1–E8: intercept-resend, finite keys, distance models, and Bell tests."""

import math
from dataclasses import replace
from time import perf_counter
from typing import Literal

import numpy as np
from _suite import Experiment

from qkdsim.analysis.chsh import estimate_chsh
from qkdsim.analysis.theory import (
    asymptotic_key_fraction,
    chsh_werner,
    decoy_bounds,
    h2,
    p_detect_ir,
    qber_ir,
)
from qkdsim.config import AttackConfig, ChannelConfig, SessionConfig
from qkdsim.physics.channel import combine_errors, transmittance
from qkdsim.postprocess.cascade import cascade_reconcile
from qkdsim.postprocess.estimation import ParameterAbort, estimate_parameters
from qkdsim.postprocess.keylength import secret_key_length
from qkdsim.postprocess.result import AbortEvidence
from qkdsim.postprocess.sifting import SiftedKey, sift
from qkdsim.postprocess.verification import verification_collision_bound, verify_keys
from qkdsim.protocols.e91 import sift_e91
from qkdsim.simulation import (
    run_bb84_session,
    run_e91_link,
    simulate_bb84,
    simulate_e91,
)


def settings(
    pulses: int,
    noise: float = 0,
    eve: float = 0,
    *,
    ideal_ec: bool = False,
) -> SessionConfig:
    """Use matched source counts and isolate independent bit-flip noise."""
    base = SessionConfig(channel=ChannelConfig(e_misalign=0, bitflip=noise))
    return replace(
        base,
        bb84=replace(
            base.bb84, n_pulses=pulses, ec_mode="ideal" if ideal_ec else "cascade"
        ),
        e91=replace(base.e91, n_pairs=pulses),
        attack=AttackConfig("ir", eve) if eve else AttackConfig(),
        monitor=replace(base.monitor, detector="threshold"),
    )


def qber(key: SiftedKey) -> float:
    """Return the fraction of sifted bits that disagree."""
    return float(np.mean(key.alice_bits != key.bob_bits))


def e01(exp: Experiment) -> None:
    """Compare measured QBER to p/4 combined with independent bit flips."""
    cases: list[tuple[str, int, list[float], list[float]]] = [
        ("fast", exp.options["pulses"], exp.options["noise"], exp.options["fractions"]),
        ("qiskit", exp.options["aer_pulses"], [0, 0.02], [0, 1]),
    ]
    for backend, pulses, noises, fractions in cases:
        for noise in noises:
            for p in fractions:
                cfg = settings(pulses, noise, p)
                if backend == "qiskit":
                    cfg = replace(cfg, bb84=replace(cfg.bb84, backend="qiskit"))
                values = [
                    qber(sift(simulate_bb84(cfg, exp.rng(i))[0]))
                    for i in range(exp.repeats)
                ]
                exp.mean(
                    "qber",
                    f"BB84 {backend}, Q₀={noise:g}",
                    p,
                    values,
                    reference=combine_errors(qber_ir(p), noise),
                    pulses=pulses,
                    noise=noise,
                    backend=backend,
                )


def e02(exp: Experiment) -> None:
    """Measure session abort and delivered bits under an honest noisy channel."""
    for q_max in exp.options["q_max"]:
        for noise in exp.options["noise"]:
            cfg = settings(exp.options["pulses"], noise, ideal_ec=True)
            cfg = replace(cfg, bb84=replace(cfg.bb84, q_max=q_max))
            outcomes = [run_bb84_session(cfg, exp.rng(i)) for i in range(exp.repeats)]
            aborted = [value for value in outcomes if isinstance(value, AbortEvidence)]
            series = f"BB84 Qmax={q_max:g}"
            exp.proportion(
                "abort",
                series,
                noise,
                len(aborted),
                exp.repeats,
                pe_rejections=sum(
                    value.reason == "qber above threshold" for value in aborted
                ),
                q_max=q_max,
            )
            exp.mean(
                "final_bits",
                series,
                noise,
                [
                    value.length_bits if not isinstance(value, AbortEvidence) else 0
                    for value in outcomes
                ],
            )


def e03(exp: Experiment) -> None:
    """Draw Binomial(k, 1/4) mismatches and detect Eve if at least one occurs."""
    rng = exp.rng(0)
    for k in exp.options["samples"]:
        successes = int(np.count_nonzero(rng.binomial(k, qber_ir(1), exp.repeats)))
        exp.proportion(
            "detection", "BB84", k, successes, exp.repeats, reference=p_detect_ir(k)
        )


def e04(exp: Experiment) -> None:
    """Measure sifted, reconciled and final bits, with actual Cascade leakage."""
    for noise in exp.options["noise"]:
        for n in exp.options["pulses"]:
            cfg = settings(n, noise)
            sifted, reconciled, final, efficiency = [], [], [], []
            for i in range(exp.repeats):
                rng = exp.rng(i)
                key = sift(simulate_bb84(cfg, rng)[0])
                sifted.append(float(key.sifted))
                estimate = estimate_parameters(key, cfg.bb84, rng)
                if isinstance(estimate, ParameterAbort):
                    reconciled.append(0.0)
                    final.append(0.0)
                    continue
                a, b, stats = (
                    estimate.alice_remaining,
                    estimate.bob_remaining,
                    estimate.stats,
                )
                ec = cascade_reconcile(
                    a, b, stats.q_est, rng, passes=cfg.bb84.cascade_passes
                )
                if ec.f_ec is not None:
                    efficiency.append(ec.f_ec)
                verification = verify_keys(a, ec.key_b_corrected)
                ok = (
                    verification.matches
                    and verification_collision_bound(a.size) <= cfg.bb84.eps_cor
                )
                reconciled.append(float(a.size) if ok else 0.0)
                bound = secret_key_length(
                    a.size,
                    stats.q_ub,
                    ec.leak_bits,
                    verification.leak_bits,
                    cfg.bb84.eps_sec,
                    cfg.bb84.eps_cor,
                )
                final.append(float(max(0, bound)) if ok else 0.0)
            for metric, values in (
                ("sifted", sifted),
                ("reconciled", reconciled),
                ("final_bits", final),
                ("ec_efficiency", efficiency),
            ):
                exp.mean(metric, f"BB84 Q={noise:g}", n, values, noise=noise)


def e05(exp: Experiment) -> None:
    """Compare l/N at fixed Q to the asymptotic limit with the same sifting."""
    noise = exp.options["noise"]
    for n in exp.options["pulses"]:
        cfg = settings(n, noise, ideal_ec=True)
        results = [run_bb84_session(cfg, exp.rng(i)) for i in range(exp.repeats)]
        reference = (
            0.5
            * (1 - cfg.bb84.test_fraction)
            * asymptotic_key_fraction(noise, cfg.bb84.f_ec_ideal)
        )
        exp.mean(
            "rate",
            "BB84",
            n,
            [
                0 if isinstance(result, AbortEvidence) else result.length_bits / n
                for result in results
            ],
            noise=noise,
            reference=reference,
        )


def e06(exp: Experiment) -> None:
    """Evaluate asymptotic loss curves for WCP BB84, decoy BB84, and E91."""
    opt = exp.options
    dark, mis, mu, nu = (opt[key] for key in ("dark", "misalignment", "mu", "nu"))

    def models(distance: float) -> tuple[tuple[str, float, float, str], ...]:
        eta = opt["eta_det"] * transmittance(distance, opt["alpha"])
        gain, q, y1, e1 = decoy_bounds(mu, nu, eta, dark, mis)
        click = eta + (1 - eta) * dark
        pair_visibility = (eta / click) ** 2 * (1 - 2 * mis) if click else 0
        return (
            (
                "BB84 WCP",
                gain / 2 * asymptotic_key_fraction(q),
                q,
                "optimistic WCP without PNS accounting",
            ),
            (
                "BB84 decoy",
                (mu * math.exp(-mu) * y1 * (1 - h2(e1)) - gain * h2(q)) / 2,
                q,
                "vacuum+weak asymptotic bound",
            ),
            (
                "E91",
                click**2 * 2 / 9 * asymptotic_key_fraction((1 - pair_visibility) / 2)
                if chsh_werner(pair_visibility) > 2
                else 0,
                (1 - pair_visibility) / 2,
                "per-pair; distance per arm; CHSH gate",
            ),
        )

    for distance in opt["distance"]:
        eta = opt["eta_det"] * transmittance(distance, opt["alpha"])
        _, _, y1, e1 = decoy_bounds(mu, nu, eta, dark, mis)
        for series, rate, error, model in models(distance):
            exp.point(
                "rate",
                series,
                distance,
                max(0, rate),
                qber=error,
                model=model,
                y1_lower=y1 if series == "BB84 decoy" else None,
                e1_upper=e1 if series == "BB84 decoy" else None,
            )
    for i, (series, initial, _, _) in enumerate(models(0)):
        low, high = 0.0, float(opt["cutoff_search_km"])
        cutoff: float | None = None
        if initial <= 0:
            cutoff = 0.0
        elif models(high)[i][1] <= 0:
            while high - low > 0.001:
                mid = (low + high) / 2
                if models(mid)[i][1] > 0:
                    low = mid
                else:
                    high = mid
            cutoff = high
        exp.point(
            "cutoff_km", series, "model", cutoff, search_limit=opt["cutoff_search_km"]
        )


def e07(exp: Experiment) -> None:
    """Measure CHSH, key-pair QBER and the configured Bell-test abort gate."""
    cases: list[tuple[Literal["fast", "qiskit"], int, list[float]]] = [
        ("fast", exp.options["pairs"], exp.options["visibility"]),
        ("qiskit", exp.options["aer_pairs"], [1]),
    ]
    for backend, pairs, visibilities in cases:
        for vis in visibilities:
            for eve in (0, 1):
                cfg = settings(pairs, eve=eve)
                cfg = replace(
                    cfg, e91=replace(cfg.e91, visibility=vis, backend=backend)
                )
                values, errors = [], []
                aborted = 0
                for i in range(exp.repeats):
                    observed, _ = simulate_e91(cfg, exp.rng(i))
                    stats = estimate_chsh(observed)
                    if stats.s is not None:
                        values.append(stats.s)
                    errors.append(qber(sift_e91(observed)))
                    lower = stats.lower_bound(cfg.e91.chsh_z)
                    aborted += lower is None or lower <= 2
                series = f"E91 {backend}, Eve={eve}"
                exp.mean(
                    "chsh", series, vis, values, reference=chsh_werner(vis) / (1 + eve)
                )
                exp.mean(
                    "qber", series, vis, errors, reference=(1 - vis / (1 + eve)) / 2
                )
                exp.proportion("bell_abort", series, vis, aborted, exp.repeats)
                if values:
                    exp.proportion(
                        "bell_violation",
                        series,
                        vis,
                        sum(abs(value) > 2 for value in values),
                        len(values),
                    )


def e08(exp: Experiment) -> None:
    """Compare observed sifting, attack rejection and delivered bits per round."""
    for noise in exp.options["noise"]:
        cfg = settings(exp.options["rounds"], noise, ideal_ec=True)
        for protocol in ("BB84", "E91"):
            for eve in (0, 1):
                trial_cfg = replace(
                    cfg, attack=AttackConfig("ir", eve) if eve else AttackConfig()
                )
                lengths, efficiency, times = [], [], []
                bell_rejections = 0
                for i in range(exp.repeats):
                    rng = exp.rng(i)
                    start = perf_counter()
                    if protocol == "E91":
                        link = run_e91_link(trial_cfg, rng)
                        times.append(1000 * (perf_counter() - start))
                        outcome = link.outcome
                        bell_rejections += (
                            isinstance(outcome, AbortEvidence)
                            and outcome.reason == "CHSH violation below margin"
                        )
                        efficiency.append(link.sifted / link.coincident)
                        lengths.append(
                            0
                            if isinstance(outcome, AbortEvidence)
                            else outcome.alice.length_bits
                        )
                    else:
                        result = run_bb84_session(trial_cfg, rng)
                        times.append(1000 * (perf_counter() - start))
                        key = sift(simulate_bb84(trial_cfg, exp.rng(i))[0])
                        efficiency.append(key.sifted / key.detected)
                        lengths.append(
                            0
                            if isinstance(result, AbortEvidence)
                            else result.length_bits
                        )
                series = f"{protocol} Eve={eve}"
                exp.mean(
                    "sift_rate",
                    series,
                    noise,
                    efficiency,
                    reference=0.5 if protocol == "BB84" else 2 / 9,
                )
                exp.proportion(
                    "abort",
                    series,
                    noise,
                    lengths.count(0),
                    exp.repeats,
                    bell_rejections=bell_rejections if protocol == "E91" else None,
                )
                exp.mean(
                    "rate",
                    series,
                    noise,
                    [length / cfg.bb84.n_pulses for length in lengths],
                )
                exp.mean("session_ms", series, noise, times)

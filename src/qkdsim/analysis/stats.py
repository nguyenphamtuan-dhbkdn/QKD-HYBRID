"""Confidence intervals, exact binomial tests, and seeded Monte Carlo."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
from numpy.random import Generator, SeedSequence, default_rng
from numpy.typing import ArrayLike, NDArray
from scipy.stats import beta, binomtest, t  # type: ignore[import-untyped]

Interval = tuple[float, float]


def _tail(confidence: float) -> float:
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    return (1 - confidence) / 2


def _binomial_counts(successes: int, trials: int) -> None:
    if not 0 <= successes <= trials or trials == 0:
        raise ValueError("expected 0 <= successes <= trials with trials > 0")


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> Interval:
    """Invert the normal score test: (p+z²/(2n) ± z*SE) / (1+z²/n)."""
    _binomial_counts(successes, trials)
    z = -NormalDist().inv_cdf(_tail(confidence))
    p = successes / trials
    z2_over_n = z**2 / trials
    center = (p + z2_over_n / 2) / (1 + z2_over_n)
    radius = z * math.sqrt((p * (1 - p) + z2_over_n / 4) / trials) / (1 + z2_over_n)
    lower = 0.0 if successes == 0 else center - radius
    upper = 1.0 if successes == trials else center + radius
    return lower, upper


def clopper_pearson(successes: int, trials: int, confidence: float = 0.95) -> Interval:
    """Invert equal binomial tails with Beta(x, n-x+1) and Beta(x+1, n-x)."""
    _binomial_counts(successes, trials)
    tail = _tail(confidence)
    lower = 0.0
    upper = 1.0
    if successes > 0:
        lower = float(beta.ppf(tail, successes, trials - successes + 1))
    if successes < trials:
        upper = float(beta.isf(tail, successes + 1, trials - successes))
    return lower, upper


def binomial_test(successes: int, trials: int, probability: float) -> float:
    """Sum null probabilities of counts at least as unlikely as the observation."""
    _binomial_counts(successes, trials)
    if not 0 <= probability <= 1:
        raise ValueError("probability must be in [0, 1]")
    test = binomtest(successes, trials, probability, alternative="two-sided")
    return float(test.pvalue)


def bootstrap_mean_interval(
    sample: ArrayLike,
    rng: Generator,
    *,
    repetitions: int = 2_000,
    confidence: float = 0.95,
) -> Interval:
    """Return the alpha/2 and 1-alpha/2 quantiles of resampled means."""
    tail = _tail(confidence)
    values = np.asarray(sample, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("sample must be a nonempty finite vector")
    if repetitions < 2:
        raise ValueError("repetitions must be at least 2")
    resamples = (rng.choice(values, size=values.size) for _ in range(repetitions))
    means = np.fromiter(
        (float(np.mean(resample)) for resample in resamples),
        dtype=np.float64,
        count=repetitions,
    )
    lower, upper = np.quantile(means, (tail, 1 - tail))
    return float(lower), float(upper)


@dataclass(frozen=True, eq=False)
class MonteCarloSummary:
    """Independent replications with a mean and a Student-t interval."""

    samples: NDArray[np.float64] = field(repr=False)
    mean: float
    interval: Interval


def monte_carlo(
    experiment: Callable[[Generator], float],
    *,
    seed: int,
    repetitions: int,
    confidence: float = 0.95,
) -> MonteCarloSummary:
    """Spawn one generator per run and return mean ± t*sample_sd/sqrt(R)."""
    tail = _tail(confidence)
    if repetitions < 2:
        raise ValueError("repetitions must be at least 2")
    children = SeedSequence(seed).spawn(repetitions)
    samples = np.fromiter(
        (experiment(default_rng(child)) for child in children),
        dtype=np.float64,
        count=repetitions,
    )
    if not np.all(np.isfinite(samples)):
        raise ValueError("experiment returned a nonfinite value")
    mean = float(np.mean(samples))
    standard_error = float(np.std(samples, ddof=1)) / math.sqrt(repetitions)
    radius = float(t.isf(tail, repetitions - 1)) * standard_error
    return MonteCarloSummary(samples, mean, (mean - radius, mean + radius))

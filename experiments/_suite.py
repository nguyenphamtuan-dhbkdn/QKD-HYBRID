"""Shared configuration, CSV schema, and confidence intervals for E1–E15."""

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.random import Generator, SeedSequence, default_rng
from scipy.stats import t  # type: ignore[import-untyped]

from qkdsim.analysis.stats import clopper_pearson

Cell = str | float | int | None
Row = dict[str, Cell]


@dataclass
class Experiment:
    """Assign each replicate an indexed child of the configured seed."""

    number: int
    seed: int
    quick: bool
    options: dict[str, Any]
    rows: list[Row] = field(default_factory=list)

    @property
    def repeats(self) -> int:
        """Return the configured number of independent replicates."""
        return int(self.options["quick" if self.quick else "repeats"])

    def rng(self, trial: int) -> Generator:
        """Reuse replicate indices across conditions for paired comparisons."""
        return default_rng(SeedSequence(self.seed, spawn_key=(self.number, trial)))

    def point(
        self,
        metric: str,
        series: str,
        x: Cell,
        value: Cell,
        *,
        low: float | None = None,
        high: float | None = None,
        n: int | None = None,
        reference: float | None = None,
        **details: Cell,
    ) -> None:
        """Add one plotted estimate and its optional interval and oracle."""
        self.rows.append(
            dict(
                metric=metric,
                series=series,
                x=x,
                value=value,
                low=low,
                high=high,
                n=n,
                reference=reference,
                **details,
            )
        )

    def mean(
        self,
        metric: str,
        series: str,
        x: Cell,
        values: list[float],
        *,
        reference: float | None = None,
        **details: Cell,
    ) -> None:
        """Report the mean and the two-sided Student t interval across trials."""
        if not values:
            self.point(
                metric,
                series,
                x,
                None,
                low=None,
                high=None,
                n=0,
                reference=reference,
                **details,
            )
            return
        mean = float(np.mean(values))
        radius = (
            float(t.ppf(0.975, len(values) - 1))
            * float(np.std(values, ddof=1))
            / math.sqrt(len(values))
            if len(values) > 1
            else None
        )
        self.point(
            metric,
            series,
            x,
            mean,
            n=len(values),
            reference=reference,
            low=None if radius is None else mean - radius,
            high=None if radius is None else mean + radius,
            **details,
        )

    def proportion(
        self,
        metric: str,
        series: str,
        x: Cell,
        successes: int,
        trials: int,
        *,
        reference: float | None = None,
        **details: Cell,
    ) -> None:
        """Report k/n with an exact two-sided Clopper–Pearson interval."""
        low, high = clopper_pearson(successes, trials)
        self.point(
            metric,
            series,
            x,
            successes / trials,
            low=low,
            high=high,
            n=trials,
            reference=reference,
            successes=successes,
            **details,
        )

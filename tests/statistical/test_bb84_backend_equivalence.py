"""Compare independent 2,000-pulse sessions and analytic binomial oracles."""

import math
from dataclasses import replace

import numpy as np
import pytest
from scipy.stats import fisher_exact

from qkdsim.config import AttackConfig, BB84Config, ChannelConfig, SessionConfig
from qkdsim.postprocess.sifting import sift
from qkdsim.rng import SimRNG
from qkdsim.simulation import simulate_bb84

pytestmark = pytest.mark.statistical


@pytest.mark.parametrize(
    ("attack", "channel", "expected_qber"),
    [
        pytest.param(AttackConfig(), ChannelConfig(e_misalign=0), 0, id="noiseless"),
        pytest.param(
            AttackConfig(kind="ir", p=1),
            ChannelConfig(e_misalign=0),
            0.25,
            id="full-ir",
        ),
        pytest.param(
            AttackConfig(),
            ChannelConfig(e_misalign=0, depol=0.2),
            0.10,
            id="depolarizing",
        ),
    ],
)
def test_backends_agree(
    attack: AttackConfig, channel: ChannelConfig, expected_qber: float
) -> None:
    config = SessionConfig(
        bb84=BB84Config(n_pulses=2_000), attack=attack, channel=channel
    )
    qiskit = replace(
        config, seed=config.seed + 1, bb84=replace(config.bb84, backend="qiskit")
    )
    qber_table = []
    sift_table = []
    for settings in (config, qiskit):
        observed, _ = simulate_bb84(settings, SimRNG(settings.seed).generator)
        key = sift(observed)
        errors = int(np.count_nonzero(key.alice_bits != key.bob_bits))
        qber_table.append([errors, key.sifted - errors])
        sift_table.append([key.sifted, key.sent - key.sifted])
        assert key.detected == key.sent
        assert abs(key.sifted - key.sent / 2) <= 4 * math.sqrt(key.sent / 4)
        expected_errors = key.sifted * expected_qber
        assert abs(errors - expected_errors) <= 4 * math.sqrt(
            expected_errors * (1 - expected_qber)
        )

    # Fisher's exact test handles the all-zero error column in the ideal case.
    assert fisher_exact(qber_table, alternative="two-sided").pvalue > 0.001
    assert fisher_exact(sift_table, alternative="two-sided").pvalue > 0.001

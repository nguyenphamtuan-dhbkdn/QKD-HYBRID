import numpy as np
import pytest

from qkdsim.analysis.chsh import chsh_mask, estimate_chsh
from qkdsim.protocols.e91 import E91Transmission, sift_e91


def test_chsh_signs_standard_error_and_sifting() -> None:
    a = np.array([0] * 8 + [2] * 8 + [1, 2, 0], dtype=np.uint8)
    b = np.array(([0] * 4 + [2] * 4) * 2 + [0, 1, 0], dtype=np.uint8)
    bits = np.array(
        [1, 0, 0, 0, 0, 1, 1, 1] + [1, 0, 0, 0] * 2 + [1, 1, 1], dtype=np.uint8
    )
    alice_clicks = np.ones(a.size, dtype=np.bool_)
    bob_clicks = alice_clicks.copy()
    bob_clicks[-1] = False
    observed = E91Transmission(a, b, np.zeros_like(a), bits, alice_clicks, bob_clicks)
    result = estimate_chsh(observed)
    assert result.counts == (4, 4, 4, 4)
    assert result.correlations == (0.5, -0.5, 0.5, 0.5)
    assert result.s == 2
    assert result.standard_error == pytest.approx(1)
    assert result.lower_bound(5) == pytest.approx(-3)
    np.testing.assert_array_equal(np.flatnonzero(chsh_mask(observed)), np.arange(16))
    np.testing.assert_array_equal(sift_e91(observed).pulse_indices, [16, 17])


@pytest.mark.parametrize("last_click", [False, True])
def test_chsh_needs_two_samples_per_group_for_standard_error(last_click: bool) -> None:
    a = np.array([0, 0, 2, 2], dtype=np.uint8)
    b = np.array([0, 2, 0, 2], dtype=np.uint8)
    detected = np.ones(4, dtype=np.bool_)
    clicks = np.array([True, True, True, last_click])
    stats = estimate_chsh(E91Transmission(a, b, a & 1, b & 1, detected, clicks))
    assert stats.counts == (1, 1, 1, int(last_click))
    assert stats.s == (2 if last_click else None)
    assert stats.standard_error is None
    assert stats.lower_bound(0) is None

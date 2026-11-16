"""Finite and asymptotic BB84 key length estimates."""

import math

from qkdsim.analysis.theory import asymptotic_key_fraction, h2


def secret_key_length(
    n_key: int,
    q_ub: float,
    leak_ec: int,
    leak_verify: int,
    eps_sec: float,
    eps_cor: float,
) -> int:
    """Floor n_key*(1-h2(Q_ub)) - leak_ec - leak_verify + 2*log2(eps_sec).

    This simplified composable-style bound assumes an ideal single-photon
    source and a Shor–Preskill-style phase-error entropy term
    (arXiv:quant-ph/0003004). A full finite-key proof against general attacks
    requires tighter assumptions and accounting (Tomamichel et al.,
    arXiv:1103.4130). Use eps_PA = eps_sec and budget eps_cor separately in
    verification. For Q_ub >= 1/2, the worst-case entropy is one bit.
    """
    if min(n_key, leak_ec, leak_verify) < 0:
        raise ValueError("key length and leakage counts must be nonnegative")
    if not 0 < eps_sec < 1 or not 0 < eps_cor < 1:
        raise ValueError("eps_sec and eps_cor must be in (0, 1)")
    if not 0 <= q_ub <= 1:
        raise ValueError("q_ub must be in [0, 1]")
    available = n_key * (1 - h2(min(q_ub, 0.5)))
    return math.floor(available - leak_ec - leak_verify + 2 * math.log2(eps_sec))


def asymptotic_key_length(n_key: int, qber: float, f_ec: float = 1.0) -> float:
    """Return the unclipped asymptotic length n_key*(1-(1+f_ec)*h2(Q))."""
    if n_key < 0:
        raise ValueError("n_key must be nonnegative")
    return n_key * asymptotic_key_fraction(qber, f_ec)

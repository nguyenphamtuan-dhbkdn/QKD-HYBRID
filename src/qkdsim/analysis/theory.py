"""Closed-form expectations in the idealized QKD models."""

import math

from scipy.optimize import brentq  # type: ignore[import-untyped]

from qkdsim.config import BasisMode
from qkdsim.physics.channel import combine_errors


def qber_ir(
    p: float, e_ch: float = 0.0, *, p_z: float = 0.5, basis_mode: BasisMode = "random"
) -> float:
    """Combine channel noise with p * P(Eve basis differs | sifted) / 2.

    For fixed Z Eve the conditional mismatch probability is
    (1-p_z)**2 / (p_z**2 + (1-p_z)**2). For fixed X the numerator is p_z**2.
    """
    if not (0 <= p <= 1 and 0 <= e_ch <= 1 and 0 <= p_z <= 1):
        raise ValueError("p, e_ch, and p_z must be probabilities")
    sift_z = p_z**2
    sift_x = (1 - p_z) ** 2
    match basis_mode:
        case "random":
            mismatch = 0.5
        case "fixed_z":
            mismatch = sift_x / (sift_z + sift_x)
        case "fixed_x":
            mismatch = sift_z / (sift_z + sift_x)
    return combine_errors(p * mismatch / 2, e_ch)


def p_detect_ir(k: int, p: float = 1.0) -> float:
    """Return 1 - (1-p/4)**k, the chance of any error in k ideal test bits."""
    if k < 0:
        raise ValueError("k must be nonnegative")
    error = qber_ir(p)
    return -math.expm1(k * math.log1p(-error))


def chsh_werner(visibility: float) -> float:
    """Return the ideal Werner-state CHSH statistic S = 2*sqrt(2)*V."""
    if not 0 <= visibility <= 1:
        raise ValueError("visibility must be in [0, 1]")
    return 2 * math.sqrt(2) * visibility


def h2(x: float) -> float:
    """Compute binary entropy -x*log2(x) - (1-x)*log2(1-x), with 0*log(0)=0."""
    if not 0 <= x <= 1:
        raise ValueError("x must be in [0, 1]")
    if x in (0, 1):
        return 0.0
    return -x * math.log2(x) - (1 - x) * math.log1p(-x) / math.log(2)


def asymptotic_key_fraction(qber: float, f_ec: float = 1.0) -> float:
    """Return the unclipped asymptotic BB84 fraction 1-(1+f_ec)*h2(Q)."""
    if not math.isfinite(f_ec) or f_ec < 1:
        raise ValueError("f_ec must be finite and >= 1")
    return 1 - (1 + f_ec) * h2(qber)


def qber_threshold_bb84() -> float:
    """Find the root of 1-2*h2(Q) in [0, 1/2] for ideal reconciliation."""
    return float(brentq(asymptotic_key_fraction, 0.0, 0.5))


def visibility_threshold_chsh() -> float:
    """Return the visibility 1/sqrt(2) where the Werner state reaches S=2."""
    return 1 / math.sqrt(2)


def grover_effective_bits(key_bits: int) -> float:
    """Return k/2 query-model bits from O(sqrt(2**k)) Grover queries."""
    if key_bits < 0:
        raise ValueError("key_bits must be nonnegative")
    return key_bits / 2


def decoy_bounds(
    mu: float,
    nu: float,
    eta: float,
    dark: float,
    misalignment: float,
) -> tuple[float, float, float, float]:
    """Return Q_mu, E_mu, Y1 lower, e1 upper (Ma et al., Eqs. 10–11, 34, 37)."""
    if not 0 < nu < mu:
        raise ValueError("expected 0 < nu < mu")
    s_mu, s_nu = -math.expm1(-eta * mu), -math.expm1(-eta * nu)
    q_mu, q_nu = dark + s_mu, dark + s_nu
    error_mu = (0.5 * dark + misalignment * s_mu) / q_mu if q_mu else 0.5
    y1 = max(
        0.0,
        (mu / (mu * nu - nu**2))
        * (
            q_nu * math.exp(nu)
            - q_mu * math.exp(mu) * (nu / mu) ** 2
            - (1 - (nu / mu) ** 2) * dark
        ),
    )
    numerator = (0.5 * dark + misalignment * s_nu) * math.exp(nu) - 0.5 * dark
    e1 = min(0.5, numerator / (y1 * nu)) if y1 else 0.5
    return q_mu, error_mu, y1, e1

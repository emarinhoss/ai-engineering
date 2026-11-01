"""Oblique and normal shock relations for a calorically perfect gas (NACA 1135).

Scalar inputs, pure Python/numpy. Angles in radians.
"""
import math

from physics.constants import GAMMA as G

NAN = float("nan")


def _theta_of_beta(M, beta):
    """theta-beta-M relation (NACA 1135 eq. 138):
    tan(theta) = 2 cot(beta) (M^2 sin^2(beta) - 1) / (M^2 (g + cos 2 beta) + 2).
    """
    num = 2.0 / math.tan(beta) * (M * M * math.sin(beta) ** 2 - 1.0)
    den = M * M * (G + math.cos(2.0 * beta)) + 2.0
    return math.atan(num / den)


def _beta_at_max(M):
    """Wave angle where theta(beta) peaks, by golden-section search on (mu, pi/2).

    theta is zero at the Mach angle mu = asin(1/M) and at 90 deg and has one maximum between.
    """
    lo, hi = math.asin(1.0 / M), math.pi / 2
    r = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = hi - r * (hi - lo), lo + r * (hi - lo)
    f1, f2 = _theta_of_beta(M, x1), _theta_of_beta(M, x2)
    while hi - lo > 1e-12:
        if f1 < f2:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + r * (hi - lo)
            f2 = _theta_of_beta(M, x2)
        else:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - r * (hi - lo)
            f1 = _theta_of_beta(M, x1)
    return 0.5 * (lo + hi)


def theta_max(M):
    """Maximum flow deflection [rad] for an attached oblique shock: max over beta of the
    theta-beta-M relation (NACA 1135 eq. 138). Requires M > 1.
    """
    if M <= 1.0:
        raise ValueError("theta_max needs M > 1")
    return _theta_of_beta(M, _beta_at_max(M))


def _jump(M, Mn1, sin_turn):
    """Rankine-Hugoniot jump for normal Mach Mn1 (NACA 1135 eqs. 93, 94, 96, 99, 100).

    p2/p1 = 1 + 2g/(g+1) (Mn1^2 - 1)
    rho2/rho1 = (g+1) Mn1^2 / ((g-1) Mn1^2 + 2),   T2/T1 = (p2/p1)/(rho2/rho1)
    Mn2^2 = ((g-1) Mn1^2 + 2) / (2 g Mn1^2 - (g-1)),   M2 = Mn2 / sin_turn
    p02/p01 = [(g+1) Mn1^2 / ((g-1) Mn1^2 + 2)]^(g/(g-1)) * [(g+1) / (2 g Mn1^2 - (g-1))]^(1/(g-1))
    sin_turn is sin(beta - theta) (oblique) or 1 (normal shock).
    """
    if Mn1 <= 1.0:
        return {"p_ratio": 1.0, "rho_ratio": 1.0, "T_ratio": 1.0, "M2": M, "p0_ratio": 1.0}
    m2 = Mn1 * Mn1
    p = 1.0 + 2.0 * G / (G + 1.0) * (m2 - 1.0)
    rho = (G + 1.0) * m2 / ((G - 1.0) * m2 + 2.0)
    Mn2 = math.sqrt(((G - 1.0) * m2 + 2.0) / (2.0 * G * m2 - (G - 1.0)))
    p0 = (rho ** (G / (G - 1.0))) * (((G + 1.0) / (2.0 * G * m2 - (G - 1.0))) ** (1.0 / (G - 1.0)))
    M2 = Mn2 / sin_turn
    return {"p_ratio": p, "rho_ratio": rho, "T_ratio": p / rho, "M2": M2, "p0_ratio": p0}


def normal(M):
    """Normal shock: _jump with Mn1 = M. For M <= 1 there is no shock and all ratios are 1."""
    out = _jump(M, M, 1.0)
    return {k: out[k] for k in ("p_ratio", "rho_ratio", "T_ratio", "M2", "p0_ratio")}


def oblique(M, theta_rad):
    """Weak-solution oblique shock for flow deflection theta_rad at Mach M.

    Solves the theta-beta-M relation for beta by bisection between the Mach angle and the
    beta at theta_max (theta is monotone increasing there), then applies _jump with
    Mn1 = M sin(beta) and M2 = Mn2 / sin(beta - theta).
    Returns beta = nan and all ratios nan if theta_rad > theta_max(M).
    """
    keys = ("beta", "p_ratio", "rho_ratio", "T_ratio", "M2", "p0_ratio")
    b_hi = _beta_at_max(M)
    if theta_rad > _theta_of_beta(M, b_hi):
        return dict.fromkeys(keys, NAN)
    lo, hi = math.asin(1.0 / M), b_hi
    while hi - lo > 1e-12:
        mid = 0.5 * (lo + hi)
        if _theta_of_beta(M, mid) < theta_rad:
            lo = mid
        else:
            hi = mid
    beta = 0.5 * (lo + hi)
    out = _jump(M, M * math.sin(beta), math.sin(beta - theta_rad))
    return {"beta": beta, **out}

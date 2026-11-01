"""Synthetic pool for tests of the replay harness. NOT a physics result.

For (theta1, theta2) in the design box (same Sobol points as designs/pool_sobol96.csv):
  recovery_total = p0 ratio of two oblique shocks (Mach 4) x normal-shock p0 ratio at the inviscid
                   throat Mach x (1 - 0.02)
  q_peak_W_m2    = Eckert flat-plate heating (physics.heating) at the post-shock edge state of
                   ramp 2, 0.1 m from the start, rescaled to 3e4 W/m^2 at theta1 = theta2 = 8.
Then a tiny seeded multiplicative noise (1e-4 relative). The shapes are smooth and the ranges
realistic; the exact values mean nothing.
"""
import math

import numpy as np

from designs.make_pool import points
from physics.constants import ATMOSPHERE_TABLE
from physics.heating import eckert_flat_plate
from physics.shock import normal, oblique

MACH = 4.0
T_INF, P_INF = ATMOSPHERE_TABLE[30]["T"], ATMOSPHERE_TABLE[30]["p"]
T_WALL, X_PROBE = 300.0, 0.1       # K, m
Q_AT_DESIGN = 3.0e4                # W/m^2 at 8/8
NOISE_REL = 1e-4


def _raw(theta1_deg, theta2_deg):
    """(recovery_total, unscaled heat flux) for one design."""
    s1 = oblique(MACH, math.radians(theta1_deg))
    s2 = oblique(s1["M2"], math.radians(theta2_deg))
    m_throat = s2["M2"]
    recovery = s1["p0_ratio"] * s2["p0_ratio"] * normal(m_throat)["p0_ratio"] * (1.0 - 0.02)
    T_e = T_INF * s1["T_ratio"] * s2["T_ratio"]
    p_e = P_INF * s1["p_ratio"] * s2["p_ratio"]
    return recovery, float(eckert_flat_plate(m_throat, T_e, p_e, T_WALL, X_PROBE))


def make_pool(n=96, seed=0):
    """Dict of numpy arrays: index, theta1_deg, theta2_deg, recovery_total, q_peak_W_m2."""
    theta = points(n)                                    # (n, 2) Sobol points in the box
    raw = np.array([_raw(t1, t2) for t1, t2 in theta])
    scale = Q_AT_DESIGN / _raw(8.0, 8.0)[1]
    rng = np.random.default_rng(seed)
    noise = 1.0 + NOISE_REL * rng.standard_normal((n, 2))
    out = raw * [1.0, scale] * noise
    if not np.isfinite(out).all():
        raise ValueError("a design in the box has a detached shock; synthetic pool is invalid")
    return {"index": np.arange(n), "theta1_deg": theta[:, 0], "theta2_deg": theta[:, 1],
            "recovery_total": out[:, 0], "q_peak_W_m2": out[:, 1]}

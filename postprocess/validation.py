"""Validation checks against analytic solutions. V1: Euler wedge vs the oblique shock relations."""
import math
from pathlib import Path

import numpy as np

from physics.constants import ATMOSPHERE_TABLE
from postprocess.history import load

P_INF = ATMOSPHERE_TABLE[30]["p"]  # Pa, freestream pressure at 30 km (single source)


def _column(cols, name):
    """Exact (case-insensitive) column lookup; SU2 volume files also have e.g. Pressure_Coefficient."""
    for c in cols:
        if c.lower() == name.lower():
            return cols[c]
    raise KeyError(f"no column {name!r}; available: {list(cols)}")


def _band(x, xs):
    """Indices of nodes within 0.6 mm of x = xs; 1.5 mm if that gives fewer than 20 nodes."""
    for half in (0.6e-3, 1.5e-3):
        idx = np.where(np.abs(x - xs) <= half)[0]
        if len(idx) >= 20:
            break
    return idx


def _plateau(y, p, lo, hi):
    """Median pressure for lo <= y <= hi and the index of those nodes."""
    sel = np.where((y >= lo) & (y <= hi))[0]
    if len(sel) == 0:
        raise ValueError(f"no nodes between y = {lo:.5f} and {hi:.5f} m")
    return float(np.median(p[sel])), sel


def _shock_y(y, p, level):
    """y where p first reaches `level` scanning from the top down (linear interpolation)."""
    for j in range(len(y) - 2, -1, -1):
        if p[j + 1] < level <= p[j]:
            return float(y[j] + (level - p[j]) / (p[j + 1] - p[j]) * (y[j + 1] - y[j]))
    raise ValueError("pressure never crosses the midpoint level")


def _station(x, y, p, mach_field, xs, theta, beta_guess, p_inf):
    """Plateau, shock position and plateau Mach at one x station (two passes, as in V1)."""
    idx = _band(x, xs)
    order = np.argsort(y[idx])
    ys, ps, ms = y[idx][order], p[idx][order], mach_field[idx][order]
    y_wall = xs * math.tan(theta)
    y_shock = xs * math.tan(beta_guess)           # first pass: analytic shock
    for _ in range(2):                              # second pass: measured shock
        plateau, sel = _plateau(ys, ps, y_wall + 1e-3, y_shock - 3e-3)
        y_shock = _shock_y(ys, ps, 0.5 * (p_inf + plateau))
    plateau, sel = _plateau(ys, ps, y_wall + 1e-3, y_shock - 3e-3)
    return {"plateau": plateau, "y_shock": y_shock, "M2": float(np.median(ms[sel])),
            "n_nodes": len(idx)}


def oblique_shock_check(case_dir, theta_deg, mach=4.0, stations=(0.04, 0.08),
                        tol_beta_deg=0.5, tol_ratio=0.02, p_inf=P_INF):
    """V1: compare beta, p2/p1 and M2 from case_dir/flow.csv with the oblique shock relations."""
    from physics.shock import oblique  # imported here so this module loads without physics/

    theta = math.radians(theta_deg)
    ref = oblique(mach, theta)
    beta_ref = math.degrees(ref["beta"])
    out = {"beta_ref_deg": beta_ref, "p_ratio_ref": ref["p_ratio"], "M2_ref": ref["M2"]}

    cols = load(Path(case_dir) / "flow.csv")
    x, y = _column(cols, "x"), _column(cols, "y")
    p, mach_field = _column(cols, "Pressure"), _column(cols, "Mach")
    try:
        s1, s2 = (_station(x, y, p, mach_field, xs, theta, ref["beta"], p_inf) for xs in stations)
    except ValueError as err:
        return {"pass": False, "beta_deg": math.nan, "p_ratio": math.nan, "M2": math.nan,
                **out, "details": {"error": str(err)}}
    beta = math.degrees(math.atan2(s2["y_shock"] - s1["y_shock"], stations[1] - stations[0]))
    p_ratio, m2 = s2["plateau"] / p_inf, s2["M2"]

    errors = {"beta_deg": beta - beta_ref, "p_ratio_rel": p_ratio / ref["p_ratio"] - 1,
              "M2_rel": m2 / ref["M2"] - 1}
    ok = (abs(errors["beta_deg"]) <= tol_beta_deg and abs(errors["p_ratio_rel"]) <= tol_ratio
          and abs(errors["M2_rel"]) <= tol_ratio)
    return {"pass": bool(ok), "beta_deg": beta, "p_ratio": p_ratio, "M2": m2, **out,
            "details": {"errors": errors, "stations": list(stations), "s1": s1, "s2": s2,
                        "tol_beta_deg": tol_beta_deg, "tol_ratio": tol_ratio}}

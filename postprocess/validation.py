"""Validation checks against analytic solutions (00_decisions.md section 4).

V1 oblique_shock_check, V2b eckert_check, V3 fay_riddell_check, V4e/V4v inlet_check, and
grid_study for the mesh-convergence tables. Each check returns a dict with "pass" (True, False,
or None with an "error" string when an input file is missing or unusable).
"""
import functools
import json
import math
from pathlib import Path

import numpy as np

from physics.constants import ATMOSPHERE_TABLE, GAMMA
from physics.heating import billig_standoff, eckert_flat_plate, fay_riddell_cylinder
from physics.shock import oblique
from postprocess import metrics, surface
from postprocess.tecplot import read_tecplot_ascii

P_INF = ATMOSPHERE_TABLE[30]["p"]  # Pa, freestream pressure at 30 km (single source)


def _column(cols, name):
    """Exact (case-insensitive) column lookup; SU2 volume files also have e.g. Pressure_Coefficient."""
    for c in cols:
        if c.lower() == name.lower():
            return cols[c]
    raise KeyError(f"no column {name!r}; available: {list(cols)}")


def _pressure_and_mach(cols, gamma=GAMMA):
    """Pressure and Mach from the file if present, else from the conservative variables:
    p = (gamma - 1) (E - 0.5 rho |u|^2),  M = |u| / sqrt(gamma p / rho)."""
    lower = {c.lower() for c in cols}
    if {"pressure", "mach"} <= lower:
        return _column(cols, "Pressure"), _column(cols, "Mach")
    rho, E = _column(cols, "Density"), _column(cols, "Energy")
    u = _column(cols, "Momentum_x") / rho
    v = _column(cols, "Momentum_y") / rho
    speed2 = u**2 + v**2
    p = (gamma - 1.0) * (E - 0.5 * rho * speed2)
    return p, np.sqrt(speed2 / (gamma * p / rho))


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
    """V1: compare beta, p2/p1 and M2 from case_dir/flow.dat (Tecplot) with the oblique shock relations."""
    theta = math.radians(theta_deg)
    ref = oblique(mach, theta)
    beta_ref = math.degrees(ref["beta"])
    out = {"beta_ref_deg": beta_ref, "p_ratio_ref": ref["p_ratio"], "M2_ref": ref["M2"]}

    cols = read_tecplot_ascii(Path(case_dir) / "flow.dat")["data"]
    x, y = _column(cols, "x"), _column(cols, "y")
    p, mach_field = _pressure_and_mach(cols)
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


GRID_TOL = {"recovery_total": 0.02, "q_peak_W_m2": 0.05}    # V4m, medium to fine, relative


def _never_raises(check):
    """A check that cannot read its inputs returns {"pass": None, "error": ...} instead of raising."""
    @functools.wraps(check)
    def wrapper(*args, **kwargs):
        try:
            return check(*args, **kwargs)
        except (OSError, KeyError, ValueError, IndexError) as err:
            return {"pass": None, "error": f"{type(err).__name__}: {err}"}
    return wrapper


@_never_raises
def eckert_check(case_dir, theta_deg, window=(0.3, 0.9), tol_mean=0.10, tol_max=0.15):
    """V2b: wall heat flux of the laminar wedge against the Eckert flat plate with the oblique-shock
    edge state. x is the distance along the surface from the leading edge; the window is
    window[0] <= x/X_w <= window[1] with X_w = geometry.json["X_w"]. Pass: mean |q/q_Eckert - 1|
    <= tol_mean and every point <= tol_max."""
    params, geometry, fs = surface.inputs(case_dir)
    body = surface.load(case_dir)["body"]
    if "q" not in body:
        raise ValueError("surface_flow.dat has no Heat_Flux (Euler run?)")
    edge = oblique(fs["M"], math.radians(theta_deg))
    Te, pe = fs["T"] * edge["T_ratio"], fs["p"] * edge["p_ratio"]
    inside = (body["s"] / geometry["X_w"] >= window[0]) & (body["s"] / geometry["X_w"] <= window[1])
    x, q_cfd = body["s"][inside], body["q"][inside]
    q_ref = eckert_flat_plate(edge["M2"], Te, pe, float(params.get("T_wall_K", 300.0)), x)
    rel = q_cfd / q_ref - 1.0
    mean_abs, max_abs = float(np.abs(rel).mean()), float(np.abs(rel).max())
    return {"pass": bool(mean_abs <= tol_mean and max_abs <= tol_max),
            "mean_abs_rel": mean_abs, "max_abs_rel": max_abs, "n": int(inside.sum()),
            "tol_mean": tol_mean, "tol_max": tol_max, "window": list(window),
            "edge": {"M": edge["M2"], "T": Te, "p": pe},
            "profile": [{"x": float(a), "q_cfd": float(b), "q_eckert": float(c), "rel": float(d)}
                        for a, b, c, d in zip(x, q_cfd, q_ref, rel)]}


def edge_velocity_gradient(case_dir, R, standoff_over_R, max_deg=5.0, line_fraction=0.1):
    """du_e/dx at the stagnation point of a cylinder from flow.dat.

    For every wall node with 0 < phi <= max_deg (phi from the stagnation point) take the
    wall-normal (radial) line of volume nodes out to line_fraction x the stand-off; the boundary-layer
    edge is the first node of that line whose Mach is within 1 percent of the largest Mach on it;
    u_e is the velocity there along the wall tangent. du_e/dx is the least-squares slope through
    the origin of u_e against the arc length R phi. Returns dict(dudx, phi_deg, u_e, edge_height_m).
    The line is cut short because the Mach number keeps rising from the boundary layer to the shock;
    with the whole line the edge would land at the shock."""
    case = Path(case_dir)
    vol = read_tecplot_ascii(case / "flow.dat")["data"]
    st = surface.state(vol)
    phi_node = np.arctan2(vol["y"], -vol["x"])
    r_node = np.hypot(vol["x"], vol["y"])
    wall = surface.load(case)["wall"]
    phi_wall = np.arctan2(wall["y"], -wall["x"])
    s_list, u_list, h_list, phi_list = [], [], [], []
    for phi in phi_wall[(phi_wall > 1e-6) & (phi_wall <= math.radians(max_deg) + 1e-6)]:
        on_line = np.where((np.abs(phi_node - phi) < 1e-5)
                           & (r_node >= R * (1 - 1e-6))
                           & (r_node <= R * (1.0 + line_fraction * standoff_over_R)))[0]
        on_line = on_line[np.argsort(r_node[on_line])]
        if len(on_line) < 3:
            continue
        mach = st["M"][on_line]
        edge = on_line[int(np.argmax(mach >= 0.99 * mach.max()))]
        s_list.append(R * phi)
        u_list.append(float(st["u"][edge] * math.sin(phi) + st["v"][edge] * math.cos(phi)))
        h_list.append(float(r_node[edge] - R))
        phi_list.append(math.degrees(phi))
    if not s_list:
        raise ValueError("no wall-normal lines found in flow.dat for the first 5 degrees")
    s, u = np.array(s_list), np.array(u_list)
    return {"dudx": float(np.sum(s * u) / np.sum(s * s)), "phi_deg": phi_list, "u_e": u_list,
            "edge_height_m": h_list}


@_never_raises
def fay_riddell_check(case_dir, tol=0.15, tol_standoff=0.15):
    """V3: stagnation-point heat flux of the cylinder against Fay-Riddell (hard, tol 15 percent).

    Also reported: q_FR recomputed with du_e/dx from the CFD edge velocity (edge_velocity_gradient)
    and the shock stand-off against Billig (report, tol_standoff). The last two need flow.dat and
    are None without it; "pass" depends on q_stag only."""
    params, geometry, fs = surface.inputs(case_dir)
    R = float(params.get("radius_m", geometry.get("radius_m", 0.010)))
    Tw = float(params.get("T_wall_K", 300.0))
    found = metrics.compute(case_dir)
    if found["q_stag_W_m2"] is None:
        raise ValueError("no stagnation heat flux: " + "; ".join(found["notes"]))
    ref = fay_riddell_cylinder(fs["M"], fs["T"], fs["p"], Tw, R)
    rel = found["q_stag_W_m2"] / ref["q"] - 1.0
    out = {"pass": bool(abs(rel) <= tol), "tol": tol, "q_stag": found["q_stag_W_m2"],
           "q_FR": ref["q"], "rel_error": rel, "dudx_newtonian": ref["dudx"],
           "dudx_cfd": None, "q_FR_cfd_gradient": None, "rel_error_cfd_gradient": None,
           "standoff_over_R": found["standoff_over_R"], "standoff_billig": billig_standoff(fs["M"]),
           "standoff_rel_error": None, "standoff_within_tol": None, "notes": list(found["notes"])}
    if found["standoff_over_R"] is not None:
        out["standoff_rel_error"] = found["standoff_over_R"] / out["standoff_billig"] - 1.0
        out["standoff_within_tol"] = bool(abs(out["standoff_rel_error"]) <= tol_standoff)
    if (Path(case_dir) / "flow.dat").exists():
        standoff = found["standoff_over_R"] or out["standoff_billig"]
        try:
            grad = edge_velocity_gradient(case_dir, R, standoff)
        except ValueError as err:
            out["notes"].append(f"CFD velocity gradient not computed: {err}")
        else:
            out["dudx_cfd"] = grad["dudx"]
            out["q_FR_cfd_gradient"] = ref["q"] * math.sqrt(grad["dudx"] / ref["dudx"])
            out["rel_error_cfd_gradient"] = found["q_stag_W_m2"] / out["q_FR_cfd_gradient"] - 1.0
            out["edge_height_m"] = grad["edge_height_m"]
    return out


def _average(f, s, lo=0.0, hi=1.0):
    """Mean of the piecewise-linear f(s) over the fractions lo..hi of the plane length."""
    a, b = s[0] + lo * (s[-1] - s[0]), s[0] + hi * (s[-1] - s[0])
    grid = np.concatenate(([a], s[(s > a) & (s < b)], [b]))
    return surface.trapezoid(np.interp(grid, s, f), grid) / (b - a)


@_never_raises
def inlet_check(case_dir):
    """V4e (EULER, hard, 2 percent) and V4v (NAVIER_STOKES, soft, 5 percent) on the throat plane.

    Area averages (plain length weights, not mass flux) of p0/p0_inf and Mach over the whole throat
    and of p0/p0_inf over the middle 50 percent of its height, against geometry.json's
    recovery_2shock_inviscid and M2_inviscid. EULER passes if the whole-throat p0 ratio and Mach are
    both within 2 percent; NAVIER_STOKES passes if the core p0 ratio is within 5 percent. The
    mass-weighted metrics (the objective) are reported next to them."""
    params, geometry, fs = surface.inputs(case_dir)
    euler = params.get("solver", "NAVIER_STOKES") == "EULER"
    t = metrics.throat_profile(surface.load(case_dir), geometry)
    ratio = t["p0"] / fs["p0"]
    got = {"p0_ratio_area": _average(ratio, t["s"]), "mach_area": _average(t["M"], t["s"]),
           "p0_ratio_core": _average(ratio, t["s"], 0.25, 0.75)}
    ref = {"p0_ratio": geometry["recovery_2shock_inviscid"], "mach": geometry["M2_inviscid"]}
    err = {"p0_ratio_area": got["p0_ratio_area"] / ref["p0_ratio"] - 1.0,
           "mach_area": got["mach_area"] / ref["mach"] - 1.0,
           "p0_ratio_core": got["p0_ratio_core"] / ref["p0_ratio"] - 1.0}
    tol = 0.02 if euler else 0.05
    checked = ("p0_ratio_area", "mach_area") if euler else ("p0_ratio_core",)
    out = {"pass": bool(all(abs(err[k]) <= tol for k in checked)),
           "type": "V4e hard" if euler else "V4v soft", "tol": tol, "checked": list(checked),
           "values": got, "reference": ref, "rel_error": err}
    try:
        found = metrics.compute(case_dir)
        out["mass_weighted"] = {k: found[k] for k in ("recovery_throat", "recovery_total",
                                                       "mach_throat_massavg")}
    except (OSError, KeyError, ValueError) as exc:
        out["mass_weighted"] = {"error": str(exc)}
    return out


def _metrics_of(item):
    """A metrics dict, or the "metrics" block of case_dir/result.json, or metrics.compute(case_dir)."""
    if isinstance(item, dict):
        return item
    result = Path(item) / "result.json"
    if result.exists():
        return json.loads(result.read_text())["metrics"]
    return metrics.compute(item)


@_never_raises
def grid_study(case_dirs, keys=("recovery_total", "q_peak_W_m2"), ratio=1.4, tol=None):
    """Mesh-convergence table. case_dirs are ordered coarse -> fine (a case directory or a metrics dict).

    For each key: values per level, relative change of each level from the previous one, the
    medium-to-fine change against `tol` and, with three or more levels, the Richardson estimate from
    the last three (constant refinement ratio): p = ln((f2 - f1) / (f3 - f2)) / ln(ratio),
    f_extrapolated = f3 + (f3 - f2) / (ratio^p - 1). If the changes are not monotone (opposite signs
    or growing) the order is reported as undefined and there is no extrapolated value. "pass" is
    True when every key that has a tolerance (default: V4m, 2 percent recovery_total and 5 percent
    q_peak) changed by less than it from medium to fine, None if no key has one."""
    tol = GRID_TOL if tol is None else tol
    found = [_metrics_of(c) for c in case_dirs]
    table = {}
    for key in keys:
        f = [m[key] for m in found]
        row = {"values": f, "rel_change": [None] + [f[i] / f[i - 1] - 1.0 for i in range(1, len(f))],
               "order": None, "extrapolated": None, "note": None}
        if len(f) >= 2 and key in tol:
            row["within_tol"] = bool(abs(row["rel_change"][-1]) <= tol[key])
        if len(f) < 3:
            row["note"] = "Richardson estimate needs three levels"
        else:
            d12, d23 = f[-2] - f[-3], f[-1] - f[-2]
            if d12 * d23 > 0 and abs(d12) > abs(d23):
                row["order"] = math.log(d12 / d23) / math.log(ratio)
                row["extrapolated"] = f[-1] + d23 / (ratio ** row["order"] - 1.0)
            else:
                row["note"] = "order undefined (changes not monotone and decreasing)"
        table[key] = row
    checks = [row["within_tol"] for row in table.values() if "within_tol" in row]
    return {"pass": all(checks) if checks else None, "ratio": ratio, "levels": len(found),
            "table": table}

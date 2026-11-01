"""Load SU2's surface_flow.dat as ordered arrays per mesh marker (units: SI, q positive into the wall).

load(case_dir) returns {marker: {x, y, s, rho, u, v, p, T, M, [q]}} for every marker of
mesh_markers.json that SU2 wrote to the surface file. For the inlet the "body" is also split at
x = X1 into body_ramp1 / body_ramp2 and the "cowl" into cowl_inner / cowl_outer (inner = on the
line lip P -> E_cowl). Checks that fail with ValueError: pressure or Mach rebuilt from the
conservative variables differs from SU2's own columns (a unit mistake), or the heat flux of a
cold body has the wrong sign.
"""
import json
from pathlib import Path

import numpy as np

from physics import atmosphere
from physics.constants import GAMMA, R_AIR
from postprocess.tecplot import read_su2_points, read_tecplot_ascii, surface_nodes_for_marker

CROSS_CHECK_TOL = 1e-3     # relative, pressure and Mach against SU2's own columns
ON_SURFACE_TOL = 1e-7      # m, same tolerance as surface_nodes_for_marker
LINE_TOL = 1e-6            # m, "on the line P -> E_cowl"
WALL_MARKERS = ("body", "wall")   # markers that carry the cold-wall heat-flux sign check


def read_json(case_dir, name):
    """Parsed case_dir/name, or {} if the file does not exist."""
    path = Path(case_dir) / name
    return json.loads(path.read_text()) if path.exists() else {}


def freestream(params):
    """Freestream state of a case: M, T, p, rho, a, U, T0, p0 (p0 = p (1 + 0.2 M^2)^3.5)."""
    st = atmosphere.state(params.get("altitude_km", 30))
    M = float(params.get("mach", 4.0))
    ratio = 1.0 + (GAMMA - 1.0) / 2.0 * M**2
    return {"M": M, "T": st["T"], "p": st["p"], "rho": st["rho"], "a": st["a"], "U": M * st["a"],
            "T0": st["T"] * ratio, "p0": st["p"] * ratio ** (GAMMA / (GAMMA - 1.0))}


def inputs(case_dir):
    """(params, geometry, freestream) of a case directory; missing json files give {}."""
    params = read_json(case_dir, "params.json")
    return params, read_json(case_dir, "geometry.json"), freestream(params)


def trapezoid(y, x):
    """Integral of y over x by the trapezoid rule."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x)))


def stagnation_pressure(p, M):
    """Isentropic total pressure p (1 + 0.2 M^2)^3.5 (gamma = 1.4)."""
    return p * (1.0 + (GAMMA - 1.0) / 2.0 * M**2) ** (GAMMA / (GAMMA - 1.0))


def state(cols):
    """rho, u, v, p, T, M from the columns of a Tecplot file (surface or volume).

    u, v from Velocity_x/Velocity_y if present, else Momentum/Density; p = (gamma-1)(E - rho |V|^2/2);
    T = p/(rho R); M = |V|/sqrt(gamma p/rho).
    """
    rho = cols["Density"]
    if "Velocity_x" in cols:
        u, v = cols["Velocity_x"], cols["Velocity_y"]
    else:
        u, v = cols["Momentum_x"] / rho, cols["Momentum_y"] / rho
    speed2 = u**2 + v**2
    p = (GAMMA - 1.0) * (cols["Energy"] - 0.5 * rho * speed2)
    with np.errstate(all="ignore"):                  # a bad p or rho gives nan; load() rejects it
        return {"rho": rho, "u": u, "v": v, "p": p, "T": p / (rho * R_AIR),
                "M": np.sqrt(speed2 / (GAMMA * p / rho))}


def _cross_check(mine, theirs, name, marker):
    """Raise if `mine` and SU2's column differ by more than 1e-3 relative on any node.
    A floor of 1e-6 of the largest value keeps Mach = 1e-14 at a wall from failing."""
    bad = np.abs(mine - theirs) > CROSS_CHECK_TOL * np.abs(theirs) + 1e-6 * np.abs(theirs).max()
    if bad.any():
        k = int(np.argmax(np.abs(mine - theirs) / (np.abs(theirs) + 1e-30) * bad))
        raise ValueError(f"marker {marker}: {name} from the conservative variables differs from "
                         f"SU2's column by more than {CROSS_CHECK_TOL:g} relative at node {k} "
                         f"({mine[k]:.6g} against {theirs[k]:.6g}); check the units")


def _arc_length(x, y):
    return np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))))


def _subset(marker, keep):
    """The nodes of a marker where `keep` is true (same order), with s measured from the first one."""
    out = {k: v[keep] for k, v in marker.items()}
    out["s"] = _arc_length(out["x"], out["y"])
    return out


def _mostly_on_surface(points, data, tol=ON_SURFACE_TOL):
    """True if at least half of the marker's mesh points have a surface row (the marker is plotted).
    A few shared corner nodes (symmetry and body meet at the leading edge) do not count."""
    xy = np.column_stack([data["data"]["x"], data["data"]["y"]])
    dist = np.hypot(points[:, None, 0] - xy[None, :, 0], points[:, None, 1] - xy[None, :, 1])
    return bool((dist.min(axis=1) <= tol).mean() >= 0.5)


def _split_inlet(out, geometry):
    """body -> body_ramp1 / body_ramp2 at x = X1; cowl -> cowl_inner / cowl_outer, both from the lip."""
    X1 = geometry["X1"]
    if "body" in out:
        x = out["body"]["x"]
        out["body_ramp1"] = _subset(out["body"], x < X1 - 1e-9)
        out["body_ramp2"] = _subset(out["body"], x >= X1 - 1e-9)
    if "cowl" in out:
        P, E = np.array(geometry["P"]), np.array(geometry["E_cowl"])
        axis = (E - P) / np.linalg.norm(E - P)
        rel = np.column_stack([out["cowl"]["x"], out["cowl"]["y"]]) - P
        off_line = np.abs(rel[:, 0] * axis[1] - rel[:, 1] * axis[0])
        for name, keep in (("cowl_inner", off_line <= LINE_TOL), ("cowl_outer", off_line > LINE_TOL)):
            part = _subset(out["cowl"], keep)
            if np.hypot(part["x"][0] - P[0], part["y"][0] - P[1]) > np.hypot(
                    part["x"][-1] - P[0], part["y"][-1] - P[1]):
                part = _subset(part, np.arange(len(part["x"]))[::-1])      # start at the lip
            out[name] = part


def _check_heat_flux_sign(out, params, fs):
    """A cold body must take heat in: the integral of q over s on the body is positive."""
    wall_T = float(params.get("T_wall_K", 300.0))
    for name in WALL_MARKERS:
        if name in out and "q" in out[name] and wall_T < fs["T0"]:
            total = trapezoid(out[name]["q"], out[name]["s"])
            if not total > 0.0:
                raise ValueError(f"heat flux sign: the integral of q over the {name} is {total:.6g} "
                                 f"W/m for T_wall = {wall_T:g} K below T0 = {fs['T0']:.1f} K; "
                                 "SU2's Heat_Flux should be positive into a cold wall")


def load(case_dir):
    """Per-marker arrays from case_dir/surface_flow.dat (see the module docstring)."""
    case = Path(case_dir)
    params, geometry, fs = inputs(case)
    markers = json.loads((case / "mesh_markers.json").read_text())
    data = read_tecplot_ascii(case / "surface_flow.dat")
    cols = data["data"]
    mine = state(cols)
    points = read_su2_points(case / "mesh.su2")

    out = {}
    for name, ids in markers.items():
        if not isinstance(ids, list) or not _mostly_on_surface(points[ids], data):
            continue                                    # "nodes", "cells", "level", unplotted markers
        rows = surface_nodes_for_marker(data, case / "mesh_markers.json", name)
        if "Pressure" in cols:
            _cross_check(mine["p"][rows], cols["Pressure"][rows], "pressure", name)
        if "Mach" in cols:
            _cross_check(mine["M"][rows], cols["Mach"][rows], "Mach", name)
        marker = {"x": cols["x"][rows], "y": cols["y"][rows]}
        marker["s"] = _arc_length(marker["x"], marker["y"])
        marker.update({k: v[rows] for k, v in mine.items()})
        if not (np.all(marker["rho"] > 0.0) and np.all(marker["p"] > 0.0)):
            raise ValueError(f"marker {name}: density or pressure is not positive on some node")
        if "Heat_Flux" in cols:
            marker["q"] = cols["Heat_Flux"][rows]
        out[name] = marker

    _check_heat_flux_sign(out, params, fs)
    if "X1" in geometry and "P" in geometry and "E_cowl" in geometry:
        _split_inlet(out, geometry)
    return out


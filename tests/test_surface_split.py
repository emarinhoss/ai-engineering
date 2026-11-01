"""postprocess.surface on hand-made cases: marker split and order, cross-checks, heat-flux sign."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from physics.constants import GAMMA, R_AIR
from postprocess import surface

VARIABLES = ["x", "y", "Density", "Momentum_x", "Momentum_y", "Energy", "Pressure", "Temperature",
             "Mach", "Velocity_x", "Velocity_y", "Heat_Flux"]


def marker(x, y, rho=0.05, u=1000.0, v=0.0, p=5000.0, q=None):
    """Node data of one marker, in order along it. Scalars are broadcast to all nodes."""
    n = len(x)
    one = lambda a: np.broadcast_to(np.asarray(a, float), (n,)).copy()
    return {"x": np.asarray(x, float), "y": np.asarray(y, float), "rho": one(rho), "u": one(u),
            "v": one(v), "p": one(p), "q": None if q is None else one(q)}


def write_case(path, markers, unplotted=None, params=None, geometry=None, scale=None, seed=0):
    """Write mesh.su2, mesh_markers.json, surface_flow.dat (rows shuffled) and the json inputs.

    markers: {name: marker(...)} in the surface file; unplotted: {name: (x, y)} only in the mesh.
    scale: {column: factor} multiplies a Tecplot column (to fake a unit mistake)."""
    ids, nodes = {}, []                                         # coordinates -> node id

    def node_id(xv, yv):
        key = (round(float(xv), 12), round(float(yv), 12))
        if key not in ids:
            ids[key] = len(nodes)
            nodes.append(key)
        return ids[key]

    mesh_markers, rows, links = {}, {}, []
    for name, m in markers.items():
        mesh_markers[name] = [node_id(a, b) for a, b in zip(m["x"], m["y"])]
        for k, i in enumerate(mesh_markers[name]):
            rows[i] = {key: (m[key][k] if m[key] is not None else 0.0) for key in m
                       if key not in ("x", "y")}              # a node shared by two markers: last wins
        links += list(zip(mesh_markers[name][:-1], mesh_markers[name][1:]))
    for name, (xs, ys) in (unplotted or {}).items():
        mesh_markers[name] = [node_id(a, b) for a, b in zip(xs, ys)]

    (path / "mesh.su2").write_text(f"NDIME= 2\nNPOIN= {len(nodes)}\n" + "".join(
        f"{a:.16e} {b:.16e} {i}\n" for i, (a, b) in enumerate(nodes)))
    (path / "mesh_markers.json").write_text(json.dumps(
        {**mesh_markers, "nodes": len(nodes), "cells": 0, "level": "medium"}))
    (path / "params.json").write_text(json.dumps(params or {"family": "inlet2r", "tag": "test"}))
    if geometry is not None:
        (path / "geometry.json").write_text(json.dumps(geometry))

    keys = sorted(rows)
    arr = lambda name: np.array([rows[i][name] for i in keys])
    write_tecplot(path / "surface_flow.dat", [nodes[i][0] for i in keys], [nodes[i][1] for i in keys],
                  arr("rho"), arr("u"), arr("v"), arr("p"), arr("q"),
                  [(keys.index(a), keys.index(b)) for a, b in links], scale=scale, seed=seed)


def write_tecplot(path, x, y, rho, u, v, p, q=None, links=(), scale=None, seed=0):
    """Tecplot ASCII, one FELINESEG zone, SU2's column names, rows in random order.
    links: pairs of 0-based node indices (into x, y); scale: {column: factor} (fake unit mistakes)."""
    x, y, rho, u, v, p = (np.asarray(a, float) for a in (x, y, rho, u, v, p))
    q = np.zeros(len(x)) if q is None else np.asarray(q, float)
    speed2 = u**2 + v**2
    table = {"x": x, "y": y, "Density": rho, "Momentum_x": rho * u, "Momentum_y": rho * v,
             "Energy": p / (GAMMA - 1) + 0.5 * rho * speed2, "Pressure": p,
             "Temperature": p / (rho * R_AIR), "Mach": np.sqrt(speed2 / (GAMMA * p / rho)),
             "Velocity_x": u, "Velocity_y": v, "Heat_Flux": q}
    for key, factor in (scale or {}).items():
        table[key] = table[key] * factor
    order = np.random.default_rng(seed).permutation(len(x))
    row_of = np.empty(len(x), dtype=int)
    row_of[order] = np.arange(len(x)) + 1                       # 1-based row in the file
    lines = [" ".join(f"{table[v_][i]:.15e}" for v_ in VARIABLES) for i in order]
    text = ('TITLE = "synthetic"\nVARIABLES = ' + ",".join(f'"{v_}"' for v_ in VARIABLES) + "\n"
            f"ZONE NODES= {len(x)}, ELEMENTS= {len(links)}, DATAPACKING=POINT, ZONETYPE=FELINESEG\n"
            + "\n".join(lines) + "\n" + "".join(f"{row_of[a]} {row_of[b]}\n" for a, b in links))
    Path(path).write_text(text)


X1 = 0.1
LIP = np.array([0.2, 0.075])
AXIS = np.array([math.cos(math.radians(16)), math.sin(math.radians(16))])
E_COWL = LIP + 0.05 * AXIS
GEOMETRY = {"X1": X1, "P": LIP.tolist(), "E_cowl": E_COWL.tolist()}


def two_markers(q_body=1.0e4):
    """A body (ramp 1 to x = 0.1, then ramp 2) and a cowl (E_cowl -> lip -> outer end)."""
    xb = np.linspace(0.0, 0.15, 16)                             # x = 0.1 is a node (index 10)
    yb = np.where(xb <= X1, xb * 0.14, X1 * 0.14 + (xb - X1) * 0.29)
    t_in = np.linspace(0.05, 0.0, 6)                            # inner: E_cowl down to the lip
    inner = LIP[:, None] + AXIS[:, None] * t_in
    t_out = np.linspace(0.004, 0.02, 5)                         # outer: leaves the lip at 22 degrees
    outer = LIP[:, None] + np.array([[math.cos(math.radians(22))], [math.sin(math.radians(22))]]) * t_out
    xc, yc = np.concatenate([inner[0], outer[0]]), np.concatenate([inner[1], outer[1]])
    return {"body": marker(xb, yb, q=q_body * (1.0 + xb)),
            "cowl": marker(xc, yc, rho=0.04, q=5.0e3 * (1.0 + xc))}


def test_markers_are_split_and_ordered(tmp_path):
    write_case(tmp_path, two_markers(), unplotted={"symmetry": ([-0.03, -0.01, 0.0], [0.0, 0.0, 0.0])},
               geometry=GEOMETRY)
    out = surface.load(tmp_path)
    assert set(out) == {"body", "cowl", "body_ramp1", "body_ramp2", "cowl_inner", "cowl_outer"}
    body = out["body"]
    assert (np.diff(body["x"]) > 0).all() and len(body["x"]) == 16
    assert body["s"][0] == 0.0 and (np.diff(body["s"]) > 0).all()
    assert body["s"][-1] == pytest.approx(np.hypot(np.diff(body["x"]), np.diff(body["y"])).sum())
    assert (out["body_ramp1"]["x"] < X1 - 1e-9).all() and len(out["body_ramp1"]["x"]) == 10
    assert (out["body_ramp2"]["x"] >= X1 - 1e-9).all() and len(out["body_ramp2"]["x"]) == 6
    assert out["body_ramp2"]["s"][0] == 0.0
    # values travel with the nodes (q was written as 1e4 (1 + x)), whatever the row order
    for part in ("body_ramp1", "body_ramp2"):
        assert out[part]["q"] == pytest.approx(1.0e4 * (1.0 + out[part]["x"]))
    assert out["body"]["u"] == pytest.approx(1000.0) and out["body"]["p"] == pytest.approx(5000.0)
    assert out["body"]["M"] == pytest.approx(1000.0 / math.sqrt(GAMMA * 5000.0 / 0.05))
    assert out["body"]["T"] == pytest.approx(5000.0 / (0.05 * R_AIR))

    inner, outer = out["cowl_inner"], out["cowl_outer"]
    assert len(inner["x"]) == 6 and len(outer["x"]) == 5 and len(out["cowl"]["x"]) == 11
    # inner is on the line lip -> E_cowl and starts at the lip; outer leaves it and starts next to the lip
    assert inner["x"][0] == pytest.approx(LIP[0]) and inner["y"][0] == pytest.approx(LIP[1])
    rel = np.column_stack([inner["x"], inner["y"]]) - LIP
    assert np.abs(rel[:, 0] * AXIS[1] - rel[:, 1] * AXIS[0]).max() < 1e-9
    assert (np.diff(inner["s"]) > 0).all() and inner["s"][-1] == pytest.approx(0.05)
    dist = np.hypot(outer["x"] - LIP[0], outer["y"] - LIP[1])
    assert dist == pytest.approx(np.linspace(0.004, 0.02, 5)) and outer["s"][0] == 0.0
    assert inner["rho"] == pytest.approx(0.04) and outer["q"] == pytest.approx(5.0e3 * (1 + outer["x"]))


def test_euler_file_without_heat_flux_loads_without_q(tmp_path):
    m = two_markers()
    write_case(tmp_path, m, params={"family": "inlet2r", "solver": "EULER", "tag": "test"},
               geometry=GEOMETRY)
    text = (tmp_path / "surface_flow.dat").read_text().replace(',"Heat_Flux"', "")
    lines = text.splitlines()
    n = int(lines[2].split("NODES=")[1].split(",")[0])
    lines[3:3 + n] = [" ".join(row.split()[:-1]) for row in lines[3:3 + n]]
    (tmp_path / "surface_flow.dat").write_text("\n".join(lines) + "\n")
    out = surface.load(tmp_path)
    assert "q" not in out["body"] and "q" not in out["cowl_inner"]


def test_pressure_unit_mistake_raises(tmp_path):
    write_case(tmp_path, two_markers(), geometry=GEOMETRY, scale={"Pressure": 1.0e-3})   # kPa column
    with pytest.raises(ValueError, match="pressure.*differs"):
        surface.load(tmp_path)


def test_mach_mismatch_raises_but_zero_mach_wall_is_fine(tmp_path):
    m = two_markers()
    m["body"]["u"][0] = 0.0                                      # a wall node with M = 0 exactly
    write_case(tmp_path, m, geometry=GEOMETRY)
    assert surface.load(tmp_path)["body"]["M"][0] == 0.0
    write_case(tmp_path, m, geometry=GEOMETRY, scale={"Mach": 1.01})
    with pytest.raises(ValueError, match="Mach.*differs"):
        surface.load(tmp_path)


def test_negative_heat_flux_integral_on_a_cold_wall_raises(tmp_path):
    write_case(tmp_path, two_markers(q_body=-1.0e4), geometry=GEOMETRY)      # T_wall 300 K default
    with pytest.raises(ValueError, match="heat flux sign"):
        surface.load(tmp_path)


def test_negative_heat_flux_is_allowed_on_a_hot_wall(tmp_path):
    params = {"family": "inlet2r", "T_wall_K": 2000.0, "tag": "test"}       # above T0 = 951 K
    write_case(tmp_path, two_markers(q_body=-1.0e4), geometry=GEOMETRY, params=params)
    assert surface.load(tmp_path)["body"]["q"].max() < 0


def test_marker_missing_from_the_surface_file_is_skipped_not_an_error(tmp_path):
    write_case(tmp_path, {"body": two_markers()["body"]}, unplotted={"inlet": ([-0.03] * 3, [0, 1, 2])})
    assert set(surface.load(tmp_path)) == {"body"}

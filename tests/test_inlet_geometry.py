import math

import numpy as np
import pytest

from geometry.inlet import build, design_points
from geometry.structured import read_su2_counts
from physics import gates

DESIGN = {"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "mesh_level": "medium"}
GRID = [(t1, t2) for t1 in np.linspace(5, 12, 7) for t2 in np.linspace(5, 14, 7)]
KEYS = {"X1", "L_d", "x_in", "y_top", "delta_ext_deg", "theta_t_deg", "C", "P", "E_body", "E_cowl",
        "G", "h_duct", "beta1_deg", "beta2_abs_deg", "M1", "M2_inviscid", "p_th_over_p_inf_inviscid",
        "recovery_2shock_inviscid", "body_length", "level", "nodes", "cells"}


def test_design_point_numbers():
    geo, _ = build(DESIGN)
    assert KEYS <= set(geo)
    expect = {"h_duct": 0.0309, "M2_inviscid": 2.962, "recovery_2shock_inviscid": 0.9316,
              "p_th_over_p_inf_inviscid": 4.08, "beta1_deg": 20.472, "beta2_abs_deg": 31.002,
              "theta_t_deg": 16.0}
    for k, v in expect.items():
        assert geo[k] == pytest.approx(v, rel=1e-3), k
    assert geo["P"] == pytest.approx([0.2023, 0.0755], rel=1e-3)
    assert geo["body_length"] == geo["E_body"][0]


def test_lip_on_both_shock_lines_and_throat_normal_to_ramp2():
    geo, mesh = build(DESIGN)
    x, y = geo["P"]
    b1, b2 = math.radians(geo["beta1_deg"]), math.radians(geo["beta2_abs_deg"])
    xc, yc = geo["C"]
    assert abs(x * math.sin(b1) - y * math.cos(b1)) < 1e-9                      # line through O
    assert abs((x - xc) * math.sin(b2) - (y - yc) * math.cos(b2)) < 1e-9        # line through C
    tt = math.radians(geo["theta_t_deg"])
    t2 = np.array([math.cos(tt), math.sin(tt)])
    Eb, Ec, P = (np.array(geo[k]) for k in ("E_body", "E_cowl", "P"))
    assert abs((Ec - Eb) @ t2) < 1e-9                                           # throat normal to ramp 2
    assert abs((Eb - np.array(geo["C"])) @ [-t2[1], t2[0]]) < 1e-9              # E_body on ramp 2
    assert abs((Ec - P) @ [-t2[1], t2[0]]) < 1e-9 and np.linalg.norm(Ec - P) == pytest.approx(0.05)
    assert np.linalg.norm(Ec - Eb) == pytest.approx(geo["h_duct"], abs=1e-12)
    # the same from the mesh: every outlet_duct node lies on the throat line
    ids = sorted({k for line in mesh.markers["outlet_duct"] for k in line})
    assert np.ptp(mesh.coords[ids] @ t2) < 1e-9
    assert mesh.coords[ids] @ t2 == pytest.approx(Eb @ t2, abs=1e-9)


def test_cowl_outer_end_is_above_the_duct_exit():
    geo, _ = build(DESIGN)
    G, Ec, P = geo["G"], geo["E_cowl"], geo["P"]
    assert G[0] == pytest.approx(Ec[0], abs=1e-12)
    angle = math.degrees(math.atan2(G[1] - P[1], G[0] - P[0]))
    assert angle == pytest.approx(geo["theta_t_deg"] + geo["delta_ext_deg"], abs=1e-9)


def test_markers_and_wall_flags():
    geo, mesh = build(DESIGN)
    assert set(mesh.markers) == {"body", "cowl", "symmetry", "inlet", "top", "outlet_duct", "outlet_ext"}
    assert sorted(mesh.walls) == ["body", "cowl"]
    body = mesh.coords[sorted({k for line in mesh.markers["body"] for k in line})]
    assert body[:, 0].min() == 0.0 and body[:, 0].max() == pytest.approx(geo["body_length"])
    top = mesh.coords[sorted({k for line in mesh.markers["top"] for k in line})]
    assert np.allclose(top[:, 1], 0.2) and top[:, 0].min() == -0.03     # continuous, x_in to x_G
    assert top[:, 0].max() == pytest.approx(geo["G"][0])
    ext = mesh.coords[sorted({k for line in mesh.markers["outlet_ext"] for k in line})]
    assert np.allclose(ext[:, 0], geo["G"][0]) and ext[:, 1].min() == pytest.approx(geo["G"][1])


def _boundary_edges(mesh):
    """Edges used by exactly one cell, as a set of sorted id pairs."""
    c = mesh.cells
    e = np.sort(np.concatenate([c[:, [k, (k + 1) % 4]] for k in range(4)]), axis=1)
    uniq, counts = np.unique(e, axis=0, return_counts=True)
    assert counts.max() <= 2                                         # no edge shared by 3 cells
    return {tuple(p) for p in uniq[counts == 1]}


@pytest.mark.parametrize("t1, t2", [(8.0, 8.0), (5.0, 14.0), (12.0, 5.0)])
def test_markers_close_the_boundary(t1, t2):
    _, mesh = build({**DESIGN, "theta1_deg": t1, "theta2_deg": t2})
    boundary = _boundary_edges(mesh)
    lines = [tuple(sorted(map(int, ab))) for seg in mesh.markers.values() for ab in seg]
    assert len(lines) == len(set(lines)), "a boundary line appears in two markers or twice"
    assert set(lines) == boundary
    print(f"closure {t1}/{t2}: {len(boundary)} boundary edges, {len(lines)} marker lines")


def test_every_node_is_used_and_no_inverted_cells():
    _, mesh = build(DESIGN)
    assert mesh.n_inverted == 0
    assert set(np.unique(mesh.cells)) == set(range(len(mesh.coords)))


def test_quality_gate_over_the_design_box():
    """7 x 7 grid: mesh quality gate (00_decisions.md section 6) and physics gates."""
    cells, min_angles, growth = [], [], []
    for t1, t2 in GRID:
        params = {**DESIGN, "theta1_deg": float(t1), "theta2_deg": float(t2)}
        geo, mesh = build(params)
        q = mesh.quality()
        where = f"theta1={t1:.3f} theta2={t2:.3f}"
        assert q["n_inverted"] == 0, where
        assert q["min_angle_deg"] >= 40, (where, q["min_angle_deg"])
        for wall in ("body", "cowl"):
            assert abs(q["first_cell_height"][wall] - 20e-6) <= 2e-6, (where, wall, q["first_cell_height"])
        assert q["max_growth"] <= 1.25, (where, q["max_growth"])
        assert q["max_aspect_ratio"] <= 5000, where
        assert 15_000 <= geo["cells"] <= 45_000, (where, geo["cells"])   # 40.2k at 5/5 medium
        # The corner (12, 14) has p_th/p_inf = 8.1 and a wall-cell Reynolds number of 42.4,
        # inside gate 5's limit of 50 (the grid study covers this corner explicitly).
        assert gates.check(params) == [], (where, gates.check(params))
        cells.append(geo["cells"])
        min_angles.append(q["min_angle_deg"])
        growth.append(q["max_growth"])
    print(f"medium cells over the grid: min {min(cells)}, max {max(cells)}; "
          f"min angle {min(min_angles):.2f} deg; max growth {max(growth):.3f}")


def test_medium_cells_at_design_point():
    geo, mesh = build(DESIGN)
    print(f"design point 8/8 medium: nodes {geo['nodes']}, cells {geo['cells']}, quality {mesh.quality()}")
    assert 15_000 <= geo["cells"] <= 40_000
    assert geo["nodes"] == len(mesh.coords) and geo["cells"] == len(mesh.cells)


def test_write_files_are_byte_identical_on_repeat(tmp_path):
    out = []
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        _, mesh = build(DESIGN)
        mesh.write_su2(d / "mesh.su2")
        mesh.write_markers(d / "mesh_markers.json")
        out.append(d)
    for f in ("mesh.su2", "mesh_markers.json"):
        assert (out[0] / f).read_bytes() == (out[1] / f).read_bytes()
    c = read_su2_counts(out[0] / "mesh.su2")
    assert set(c["markers"]) == {"body", "cowl", "symmetry", "inlet", "top", "outlet_duct", "outlet_ext"}


def test_levels_scale_the_mesh():
    n = {lvl: build({**DESIGN, "mesh_level": lvl})[0]["cells"] for lvl in ("coarse", "medium", "fine")}
    assert 1.4 < n["medium"] / n["coarse"] < 2.6 and 1.4 < n["fine"] / n["medium"] < 2.6
    _, fine = build({**DESIGN, "mesh_level": "fine"})
    assert fine.n_inverted == 0 and fine.quality()["min_angle_deg"] >= 40
    with pytest.raises(ValueError):
        build({**DESIGN, "mesh_level": "huge"})


def test_builder_refuses_bad_geometry():
    with pytest.raises(ValueError, match="x_P - X1"):
        build({**DESIGN, "theta1_deg": 18.0, "theta2_deg": 22.0, "mach": 3.0})
    with pytest.raises(ValueError, match="detached"):
        build({**DESIGN, "theta1_deg": 40.0})


def test_design_points_matches_build():
    geo, _ = build(DESIGN)
    g = design_points(8.0, 8.0)
    assert list(g["P"]) == geo["P"] and g["h"] == geo["h_duct"]


def test_stretch_two_sided_smooth():
    from geometry.structured import stretch_two_sided_smooth
    x, info = stretch_two_sided_smooth(0.0309, 61, 20.8e-6, 20.8e-6)
    d = np.diff(x)
    assert x[0] == 0 and x[-1] == 0.0309 and np.all(d > 0)
    assert d[0] == pytest.approx(20.8e-6) and d[-1] == pytest.approx(20.8e-6)
    assert np.max(np.maximum(d[1:] / d[:-1], d[:-1] / d[1:])) <= info["ratio"] * (1 + 1e-9)
    assert info["max_growth"] == pytest.approx(info["ratio"], rel=1e-6)
    print(f"duct line h=0.0309, 61 nodes: ratio {info['ratio']:.4f}, max spacing {info['max_spacing']:.3e}")
    x, info = stretch_two_sided_smooth(0.1, 200, 0.3e-3, 0.3e-3, dmax=1.0e-3)       # capped
    assert np.diff(x).max() <= 1.0e-3 * (1 + 1e-12) and x[-1] == 0.1
    x, _ = stretch_two_sided_smooth(0.05, 80, 0.2e-3, 0.4e-3)                       # unequal ends
    assert np.diff(x)[0] == pytest.approx(0.2e-3) and np.diff(x)[-1] == pytest.approx(0.4e-3)
    with pytest.raises(ValueError):
        stretch_two_sided_smooth(0.001, 61, 20e-6, 20e-6)

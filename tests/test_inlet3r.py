import json
import math

import numpy as np
import pytest

from geometry import inlet
from geometry.inlet3r import build, design_points, sizes
from geometry.structured import mesh_fingerprint
from worker.make_case import quality_failures

MARKERS = {"body", "cowl", "symmetry", "inlet", "top", "outlet_duct", "outlet_ext"}
# (10, 10, 7) and (9, 9, 9) are 27 deg corners. They failed the 40 deg minimum-angle gate (36.8 and
# 38.9 deg at medium) until the upper line at X2 became a blend of the X1 and x_P lines; now 52.8 and
# 56.1 deg. A scan of {3, 4.5, 6, 7.5, 9, 10}^3 at 27 deg or less: 200 sets pass at every level,
# 6 (all with theta1 = theta2 = 3) are refused because the lip is too high.
ANGLES = [(7, 7, 7), (3, 3, 3), (10, 10, 7), (9, 9, 9), (10, 3, 10), (3, 10, 10), (5, 9, 10)]


def _dist_to_line(P, origin, angle):
    return abs((P[0] - origin[0]) * math.sin(angle) - (P[1] - origin[1]) * math.cos(angle))


@pytest.mark.parametrize("angles", [(7, 7, 7), (4, 6, 8), (10, 5, 9), (5, 9, 10)])
def test_three_shocks_pass_through_the_lip(angles):
    g = design_points(*angles)
    P = g["P"]
    assert _dist_to_line(P, (0.0, 0.0), g["beta1"]) < 1e-9
    assert _dist_to_line(P, g["C1"], g["beta2_abs"]) < 1e-9
    assert _dist_to_line(P, g["C2"], g["beta3_abs"]) < 1e-9
    t12 = math.radians(angles[0] + angles[1])                   # C2 lies on ramp 2
    assert _dist_to_line(g["C2"], g["C1"], t12) < 1e-12
    assert g["C1"][0] < g["C2"][0] < P[0]
    assert g["recovery"] < 1 and g["M3"] < g["M2"] < g["M1"] < 4.0


@pytest.mark.parametrize("t1, t2", [(7, 7), (4, 9), (10, 5)])
def test_theta3_to_zero_recovers_two_ramp_lip(t1, t2):
    P3 = design_points(t1, t2, 1e-6)["P"]
    P2 = inlet.design_points(t1, t2)["P"]
    assert np.max(np.abs(P3 - P2)) < 1e-9


def test_flight_mach_does_not_change_the_geometry(tmp_path):
    prints, pts = [], []
    for mach in (4.0, 3.5, 4.5):
        geo, mesh = build({"theta1_deg": 7, "theta2_deg": 7, "theta3_deg": 7, "mach": mach})
        f = tmp_path / f"m{mach}.su2"
        mesh.write_su2(f)
        prints.append(mesh_fingerprint(f))
        pts.append([geo[k] for k in ("C", "C2", "P", "E_body", "E_cowl", "G", "h_duct")])
    assert prints[0] == prints[1] == prints[2]
    assert pts[0] == pts[1] == pts[2]


@pytest.mark.parametrize("level", ["coarse", "medium", "fine"])
@pytest.mark.parametrize("angles", ANGLES)
def test_mesh_quality_gate(angles, level):
    params = dict(zip(("theta1_deg", "theta2_deg", "theta3_deg"), map(float, angles)), mesh_level=level)
    d0 = sizes(level)["d0"]
    try:
        geo, mesh = build(params)
    except ValueError as e:                                      # a length check refuses the corner
        assert "m is below" in str(e) or "above" in str(e) or "does not exist" in str(e)
        print(f"REFUSED {angles} {level}: {e}")
        return
    assert quality_failures(mesh.quality(), {"body": d0, "cowl": d0}) == [], (angles, level)
    assert mesh.n_inverted == 0
    assert set(np.unique(mesh.cells)) == set(range(len(mesh.coords)))


def test_geometry_keys_and_counts():
    geo, mesh = build({"theta1_deg": 7, "theta2_deg": 7, "theta3_deg": 7})
    need = {"X1", "X2", "L_d", "x_in", "y_top", "delta_ext_deg", "theta_t_deg", "C", "C2", "P",
            "E_body", "E_cowl", "G", "h_duct", "beta1_deg", "beta2_abs_deg", "M1", "M2_inviscid",
            "M3", "theta3_deg", "p_th_over_p_inf_inviscid", "recovery_2shock_inviscid",
            "body_length", "level", "nodes", "cells"}
    assert need <= set(geo)
    assert geo["theta_t_deg"] == pytest.approx(21.0) and geo["X2"] == geo["C2"][0]
    assert geo["nodes"] == len(mesh.coords) and geo["cells"] == len(mesh.cells)
    print(f"7/7/7 medium: nodes {geo['nodes']}, cells {geo['cells']}")


def test_markers(tmp_path):
    geo, mesh = build({"theta1_deg": 7, "theta2_deg": 7, "theta3_deg": 7})
    assert set(mesh.markers) == MARKERS and sorted(mesh.walls) == ["body", "cowl"]
    mesh.write_markers(tmp_path / "m.json")
    d = json.loads((tmp_path / "m.json").read_text())
    assert MARKERS <= set(d)
    body = mesh.coords[sorted({k for line in mesh.markers["body"] for k in line})]
    assert body[:, 0].min() == 0.0 and body[:, 0].max() == pytest.approx(geo["body_length"])
    # body nodes sit on the three ramp lines and the duct wall, with corners at C1 and C2
    for p in (geo["C"], geo["C2"], geo["E_body"]):
        assert np.min(np.hypot(*(body - p).T)) < 1e-9
    top = mesh.coords[sorted({k for line in mesh.markers["top"] for k in line})]
    assert np.allclose(top[:, 1], 0.2) and top[:, 0].min() == -0.03
    assert top[:, 0].max() == pytest.approx(geo["G"][0])
    # markers close the boundary: lines used by exactly one cell equal the marker lines
    c = mesh.cells
    e = np.sort(np.concatenate([c[:, [k, (k + 1) % 4]] for k in range(4)]), axis=1)
    uniq, counts = np.unique(e, axis=0, return_counts=True)
    boundary = {tuple(p) for p in uniq[counts == 1]}
    lines = [tuple(sorted(map(int, ab))) for seg in mesh.markers.values() for ab in seg]
    assert len(lines) == len(set(lines)) and set(lines) == boundary


def test_construction_refusals():
    with pytest.raises(ValueError, match="detached"):
        design_points(40, 5, 5)
    with pytest.raises(ValueError, match="lip height"):
        build({"theta1_deg": 3, "theta2_deg": 3, "theta3_deg": 3})

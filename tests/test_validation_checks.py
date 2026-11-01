"""postprocess.validation: Eckert (V2b), Fay-Riddell (V3), inlet (V4e/V4v) and grid_study."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from geometry import cylinder
from physics.heating import billig_standoff, eckert_flat_plate, fay_riddell_cylinder
from physics.shock import oblique
from postprocess import validation
from tests.test_metrics import M_CORE, P0_INF, P_CORE, write_inlet
from tests.test_surface_split import marker, write_case, write_tecplot

SCRATCH = Path("/tmp/claude-0/-home-user-ai-engineering/4e62754b-8c8b-5b87-a61c-cb95358da47b/scratchpad")
REAL_LAM = SCRATCH / "lam"
REAL_EULER = SCRATCH / "inlet" / "inlet88_euler"
REAL_NS = SCRATCH / "inlet" / "inlet88_navier_stokes"
T_INF, P_INF, M_INF = 226.509, 1197.03, 4.0


# ---- V2b Eckert -----------------------------------------------------------------------------

@pytest.mark.skipif(not (REAL_LAM / "surface_flow.dat").exists(), reason="real laminar wedge not available")
def test_eckert_on_the_real_laminar_wedge():
    res = validation.eckert_check(REAL_LAM, 10.0)
    assert res["pass"] is True
    assert res["mean_abs_rel"] < 0.03 and res["max_abs_rel"] < 0.05     # measured 0.74 and 1.1 percent
    assert res["n"] == len(res["profile"]) and res["n"] > 50
    assert all(0.3 <= row["x"] / 0.15 <= 0.9 for row in res["profile"])
    first = res["profile"][0]
    assert first["q_cfd"] / first["q_eckert"] - 1 == pytest.approx(first["rel"])


def synthetic_wedge(tmp_path, factor, outlier=1.0):
    """Wedge body (10 deg, X_w = 0.15) whose heat flux is `factor` x the Eckert value."""
    theta = math.radians(10.0)
    edge = oblique(M_INF, theta)
    s = np.linspace(0.0, 0.15 / math.cos(theta), 91)
    q = np.zeros(len(s))
    q[1:] = factor * eckert_flat_plate(edge["M2"], T_INF * edge["T_ratio"], P_INF * edge["p_ratio"],
                                       300.0, s[1:])
    q[40] *= outlier
    body = marker(s * math.cos(theta), s * math.sin(theta), q=q)
    write_case(tmp_path, {"body": body}, geometry={"X_w": 0.15},
               params={"family": "wedge", "theta1_deg": 10.0, "tag": "test"})


def test_eckert_check_passes_within_tolerance(tmp_path):
    synthetic_wedge(tmp_path, 1.06)
    res = validation.eckert_check(tmp_path, 10.0)
    assert res["pass"] is True and res["mean_abs_rel"] == pytest.approx(0.06, abs=1e-6)


def test_eckert_check_fails_on_mean_and_on_a_single_point(tmp_path):
    synthetic_wedge(tmp_path, 1.12)
    assert validation.eckert_check(tmp_path, 10.0)["pass"] is False          # mean 12 percent
    synthetic_wedge(tmp_path, 1.0, outlier=1.2)                              # one point 20 percent off
    res = validation.eckert_check(tmp_path, 10.0)
    assert res["mean_abs_rel"] < 0.01 and res["max_abs_rel"] == pytest.approx(0.2) and res["pass"] is False


def test_checks_return_pass_none_instead_of_raising(tmp_path):
    for res in (validation.eckert_check(tmp_path, 10.0), validation.fay_riddell_check(tmp_path),
                validation.inlet_check(tmp_path), validation.grid_study([tmp_path, tmp_path])):
        assert res["pass"] is None and "error" in res


# ---- V4e / V4v inlet --------------------------------------------------------------------------

@pytest.mark.skipif(not (REAL_EULER / "surface_flow.dat").exists(), reason="real Euler inlet not available")
def test_inlet_check_on_the_real_euler_run():
    res = validation.inlet_check(REAL_EULER)
    assert res["pass"] is True and res["tol"] == 0.02 and "V4e" in res["type"]
    assert abs(res["rel_error"]["p0_ratio_area"]) < 0.01 and abs(res["rel_error"]["mach_area"]) < 0.01
    assert res["values"]["p0_ratio_core"] == pytest.approx(res["values"]["p0_ratio_area"], abs=0.01)


@pytest.mark.skipif(not (REAL_NS / "surface_flow.dat").exists(), reason="real laminar inlet not available")
def test_inlet_check_on_the_real_laminar_run_is_soft_on_the_core():
    res = validation.inlet_check(REAL_NS)
    assert "V4v" in res["type"] and res["tol"] == 0.05 and res["checked"] == ["p0_ratio_core"]
    assert res["pass"] is True
    # boundary layers pull the whole-throat average below the core one
    assert res["values"]["p0_ratio_area"] < res["values"]["p0_ratio_core"]


def test_inlet_check_synthetic_uniform_profile_misses_the_inviscid_value(tmp_path):
    write_inlet(tmp_path, uniform=True, solver="EULER")      # uniform M 2.9: p0/p0_inf is about 0.85, not 0.93
    res = validation.inlet_check(tmp_path)
    assert res["pass"] is False and res["rel_error"]["p0_ratio_area"] < -0.05
    # uniform profile: area average, core average and the per-node value all agree
    assert res["values"]["p0_ratio_area"] == pytest.approx(res["values"]["p0_ratio_core"], rel=1e-9)
    assert res["values"]["mach_area"] == pytest.approx(2.9, abs=1e-9)


def test_core_average_ignores_the_wall_deficits(tmp_path):
    write_inlet(tmp_path)                                    # parabolic deficits within 12 percent of each wall
    res = validation.inlet_check(tmp_path)
    assert res["values"]["p0_ratio_core"] > res["values"]["p0_ratio_area"] + 0.05
    uniform_value = P_CORE * (1 + 0.2 * M_CORE**2) ** 3.5 / P0_INF        # the core is uniform
    assert res["values"]["p0_ratio_core"] == pytest.approx(uniform_value, rel=1e-9)


# ---- grid_study ----------------------------------------------------------------------------------

def second_order(h):
    return 0.30 + 0.01 * np.asarray(h) ** 2


def test_grid_study_richardson_for_a_second_order_sequence():
    h = [1.4**2, 1.4, 1.0]                                   # coarse, medium, fine
    values = second_order(h)
    study = validation.grid_study([{"recovery_total": v, "q_peak_W_m2": 2.0 * v} for v in values])
    row = study["table"]["recovery_total"]
    assert row["order"] == pytest.approx(2.0, abs=1e-9)
    assert row["extrapolated"] == pytest.approx(0.30, abs=1e-12)
    assert row["rel_change"][0] is None
    assert row["rel_change"][2] == pytest.approx(values[2] / values[1] - 1)
    assert row["note"] is None and study["levels"] == 3
    # medium to fine changes by 0.0096/0.3 ... 3 percent: over the 2 percent tolerance of V4m
    assert row["within_tol"] is False and study["pass"] is False
    assert study["table"]["q_peak_W_m2"]["order"] == pytest.approx(2.0, abs=1e-9)
    assert study["table"]["q_peak_W_m2"]["extrapolated"] == pytest.approx(0.60, abs=1e-12)


def test_grid_study_non_monotone_sequence_has_undefined_order():
    study = validation.grid_study([{"recovery_total": v} for v in (0.30, 0.32, 0.31)],
                                  keys=("recovery_total",))
    row = study["table"]["recovery_total"]
    assert row["order"] is None and row["extrapolated"] is None
    assert "order undefined" in row["note"]
    diverging = validation.grid_study([{"recovery_total": v} for v in (0.30, 0.31, 0.33)],
                                      keys=("recovery_total",))
    assert "order undefined" in diverging["table"]["recovery_total"]["note"]


def test_grid_study_two_levels_and_case_directories(tmp_path):
    dirs = []
    for k, value in enumerate((0.300, 0.304)):
        d = tmp_path / f"level{k}"
        d.mkdir()
        (d / "result.json").write_text(json.dumps({"metrics": {"recovery_total": value}}))
        dirs.append(d)
    study = validation.grid_study(dirs, keys=("recovery_total",))
    row = study["table"]["recovery_total"]
    assert row["values"] == [0.300, 0.304] and row["order"] is None and "three levels" in row["note"]
    assert row["rel_change"][1] == pytest.approx(0.304 / 0.300 - 1) and study["pass"] is True


# ---- V3 Fay-Riddell on a synthetic cylinder ---------------------------------------------------------

R = 0.010
G_TRUE = 6.5e4              # the "CFD" velocity gradient, 1/s (Newtonian: 7.2e4)
BL = 5e-5                   # boundary-layer thickness of the fake tangential velocity profile, m
FR = fay_riddell_cylinder(M_INF, T_INF, P_INF, 300.0, R)


def synthetic_cylinder(tmp_path, q_factor=1.0, volume=True):
    """Coarse cylinder mesh; wall heat flux q_factor x Fay-Riddell at the stagnation node; flow.dat with
    pressure ramping from p_inf to 21 p_inf across r = R (1 + 0.517) and u_t = G R phi (1 - exp(-y/BL))."""
    geometry, mesh = cylinder.build({"radius_m": R, "mesh_level": "coarse"})
    mesh.write_su2(tmp_path / "mesh.su2")
    mesh.write_markers(tmp_path / "mesh_markers.json")
    (tmp_path / "geometry.json").write_text(json.dumps(geometry))
    (tmp_path / "params.json").write_text(json.dumps(
        {"family": "cylinder", "radius_m": R, "mesh_level": "coarse", "tag": "test"}))
    wall_ids = json.loads((tmp_path / "mesh_markers.json").read_text())["wall"]
    wall = mesh.coords[wall_ids]
    phi = np.arctan2(wall[:, 1], -wall[:, 0])
    n = len(wall)
    write_tecplot(tmp_path / "surface_flow.dat", wall[:, 0], wall[:, 1], np.full(n, 0.2), np.zeros(n),
                  np.zeros(n), np.full(n, 25000.0), q=q_factor * FR["q"] * np.cos(phi),
                  links=[(k, k + 1) for k in range(n - 1)], seed=3)
    if not volume:
        return
    x, y = mesh.coords[:, 0], mesh.coords[:, 1]
    r, ph = np.hypot(x, y), np.arctan2(y, -x)
    ramp = np.clip((R * 1.517 - r) / 2e-3 + 0.5, 0.0, 1.0)
    p = P_INF + (21.0 * P_INF - P_INF) * ramp
    u_t = G_TRUE * R * ph * (1.0 - np.exp(-(r - R) / BL))
    write_tecplot(tmp_path / "flow.dat", x, y, np.full(len(x), 0.05), u_t * np.sin(ph),
                  u_t * np.cos(ph), p, links=[(k, k + 1) for k in range(len(x) - 1)], seed=4)


def test_fay_riddell_check_passes_on_the_reference_value(tmp_path):
    synthetic_cylinder(tmp_path)
    res = validation.fay_riddell_check(tmp_path)
    assert res["pass"] is True
    assert res["q_stag"] == pytest.approx(FR["q"], rel=1e-6) and res["q_FR"] == pytest.approx(FR["q"])
    assert res["rel_error"] == pytest.approx(0.0, abs=1e-6)
    # stand-off from the pressure ramp: 0.517 R, Billig 0.5168
    assert res["standoff_over_R"] == pytest.approx(0.517, abs=2e-3)
    assert res["standoff_billig"] == pytest.approx(billig_standoff(M_INF))
    assert res["standoff_within_tol"] is True
    # velocity gradient from the fake edge velocity: 6.5e4 within the 1 percent the edge rule allows
    assert res["dudx_cfd"] == pytest.approx(G_TRUE, rel=0.012)
    assert res["q_FR_cfd_gradient"] == pytest.approx(FR["q"] * math.sqrt(res["dudx_cfd"] / FR["dudx"]))
    assert res["rel_error_cfd_gradient"] == pytest.approx(
        res["q_stag"] / res["q_FR_cfd_gradient"] - 1.0)
    assert max(res["edge_height_m"]) < 6 * BL


def test_fay_riddell_check_fails_outside_15_percent(tmp_path):
    synthetic_cylinder(tmp_path, q_factor=1.2)
    res = validation.fay_riddell_check(tmp_path)
    assert res["pass"] is False and res["rel_error"] == pytest.approx(0.2, abs=1e-6)
    synthetic_cylinder(tmp_path, q_factor=0.9)
    assert validation.fay_riddell_check(tmp_path)["pass"] is True


def test_fay_riddell_check_without_volume_file_still_checks_q(tmp_path):
    synthetic_cylinder(tmp_path, volume=False)
    res = validation.fay_riddell_check(tmp_path)
    assert res["pass"] is True and res["standoff_over_R"] is None and res["dudx_cfd"] is None
    assert any("flow.dat" in n for n in res["notes"])


def test_cylinder_metrics_pick_the_stagnation_node(tmp_path):
    synthetic_cylinder(tmp_path)
    from postprocess.metrics import compute
    got = compute(tmp_path)
    assert got["q_stag_W_m2"] == pytest.approx(FR["q"], rel=1e-6)    # cos(0) = 1 at the nearest node
    assert got["standoff_over_R"] == pytest.approx(0.517, abs=2e-3) and got["notes"] == []

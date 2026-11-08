"""T10.8b/8c contract: V6e (SU2 against the E387 tunnel polars) and V6f (low-fidelity closed forms
against the same data), plus the two helpers they need: a polar aggregator that keeps runs SU2
stopped on its own Cauchy criterion, and the camber and thickness measured off a coordinate file.

Rules fixed here, before any SU2 E387 result exists:
- the SU2 cases are run AT the tunnel's own angles, so every comparison is point to point and no
  value is interpolated in alpha; records at other angles are refused;
- cl_alpha is the least-squares slope over the SAME alphas on both sides;
- the drag ratio is the mean of |cd_su2 / cd_tunnel - 1| over the matched points whose tunnel cl
  lies in [0.3, 0.9];
- cl_max is reported only when the SU2 polar actually peaks (its angles stop at 7.23 deg).
"""
import copy

import numpy as np
import pytest
import yaml

from analysis import drone_polar, drone_validation
from drone import naca
from geometry import airfoils

with open("data/validation/e387_uiuc.yaml") as _f:
    E387_POLARS = yaml.safe_load(_f)["polars"]
RUN_213 = next(p for p in E387_POLARS if p["run"] == 213)        # Re 203,800
RUN_215 = next(p for p in E387_POLARS if p["run"] == 215)        # Re 305,200
ANGLES = {203800.0: (1.27, 2.67, 4.23, 5.59, 7.23), 305200.0: (1.04, 2.53, 4.07, 5.93, 6.93)}


def tunnel_point(run, alpha):
    i = run["alpha_deg"].index(alpha)
    return run["cl"][i], run["cd"][i]


def su2_record(re, alpha, cl, cd, status="not_converged", iterations=4500, max_iter=6000,
               cl_drift=1.5, cd_drift=4.0):
    return {"case_id": f"airfoil2d-{abs(hash((re, alpha))) % 10**10:010d}",
            "params": {"family": "airfoil2d", "airfoil": "e387", "alpha_deg": alpha, "reynolds": re,
                       "transition": "BCM", "mesh_level": "medium", "max_iter": max_iter, "tag": "e387"},
            "metrics": {"cl": cl, "cd": cd, "cm": 0.08, "cl_drift_pct": cl_drift, "cd_drift_pct": cd_drift},
            "convergence": {"status": status, "iterations": iterations, "residual_column": "rms[P]",
                            "drift_pct": {"cl": cl_drift, "cd": cd_drift}},
            "run": {"exit_code": 0, "timeout": False, "iterations": iterations, "wall_time_s": 1300.0}}


def synthetic_su2(run, re, cl_factor, cd_factor, **kw):
    """SU2 records that reproduce the tunnel polar at its own angles, scaled by known factors."""
    out = []
    for a in ANGLES[re]:
        cl, cd = tunnel_point(run, a)
        out.append(su2_record(re, a, cl * cl_factor, cd * cd_factor, **kw))
    return out


# ---- the aggregator keeps Cauchy-stopped runs and knows the airfoil key ----

def test_polar_keeps_runs_that_su2_stopped_on_its_own_criterion():
    recs = synthetic_su2(RUN_213, 203800.0, 1.0, 1.0)
    s = drone_polar.polar(recs)
    assert s.cl_alpha_per_deg > 0.09 and "not_peaked" in s.flags
    assert "cauchy_stopped" in s.flags
    assert any(f.startswith("cd_drift_max_pct=4.0") for f in s.flags)
    assert "missing_angles" not in s.flags
    assert "e387" in s.source


def test_polar_drops_a_run_that_merely_exhausted_its_budget():
    recs = synthetic_su2(RUN_213, 203800.0, 1.0, 1.0)
    recs[2]["convergence"]["iterations"] = recs[2]["run"]["iterations"] = 6000     # == max_iter
    s = drone_polar.polar(recs)
    assert "missing_angles" in s.flags
    recs[3]["run"]["timeout"] = True
    recs[3]["convergence"]["iterations"] = recs[3]["run"]["iterations"] = 5000
    assert "missing_angles" in drone_polar.polar(recs).flags


def test_polar_refuses_to_mix_a_file_section_with_a_naca_one():
    recs = synthetic_su2(RUN_213, 203800.0, 1.0, 1.0)
    recs[1]["params"] = {**recs[1]["params"], "camber_pct": 4.0, "thickness_pct": 12.0}
    del recs[1]["params"]["airfoil"]
    with pytest.raises(ValueError):
        drone_polar.polar(recs)


# ---- camber and thickness off a coordinate file ----

def test_camber_and_thickness_of_a_naca_4412_loop_are_its_digits():
    x, y = naca.coordinates(4.0, 12.0, n=801)
    c = airfoils.camber_thickness(x, y)
    assert c["max_camber"] == pytest.approx(0.04, abs=1e-3)
    assert c["camber_position"] == pytest.approx(0.40, abs=0.01)
    assert c["max_thickness"] == pytest.approx(0.12, abs=1e-3)


def test_e387_is_a_nine_percent_section():
    x, y, _ = airfoils.load("e387")
    c = airfoils.camber_thickness(*airfoils.dense_loop(x, y, 801))
    assert c["max_thickness"] == pytest.approx(0.0907, abs=0.002)
    assert 0.02 < c["max_camber"] < 0.06 and 0.2 < c["camber_position"] < 0.7


# ---- V6e ----

def test_v6e_passes_on_a_polar_three_percent_high_in_lift_and_ten_in_drag():
    rows = []
    su2 = {203800.0: synthetic_su2(RUN_213, 203800.0, 1.03, 1.10),
           305200.0: synthetic_su2(RUN_215, 305200.0, 1.03, 1.10)}
    drone_validation.v6e(rows, E387_POLARS, su2)
    by = {r["name"]: r for r in rows}
    for re in ("203800", "305200"):
        a = by[f"V6e cl_alpha Re {re}"]
        assert a["verdict"] == "pass" and a["deviation"] == pytest.approx(0.03, abs=1e-6)
        d = by[f"V6e cd ratio Re {re}"]
        assert d["verdict"] == "pass" and d["measured"] == pytest.approx(0.10, abs=1e-6)
        m = by[f"V6e cl_max Re {re}"]
        assert m["verdict"] == "report" and "stall" in m["note"]
    assert all(r["tolerance"] in (0.05, 0.20, None) for r in rows)


def test_v6e_fails_on_thirty_percent_drag_and_six_percent_lift_slope():
    rows = []
    drone_validation.v6e(rows, E387_POLARS, {203800.0: synthetic_su2(RUN_213, 203800.0, 1.06, 1.30)})
    by = {r["name"]: r for r in rows}
    assert by["V6e cl_alpha Re 203800"]["verdict"] == "fail"
    assert by["V6e cd ratio Re 203800"]["verdict"] == "fail"
    assert "305200" not in " ".join(by)                     # only the Reynolds numbers given


def test_v6e_drag_ratio_uses_only_points_with_tunnel_cl_between_0_3_and_0_9():
    rows = []
    recs = synthetic_su2(RUN_213, 203800.0, 1.0, 1.0)
    # 7.23 deg has tunnel cl 1.042, outside [0.3, 0.9]: a wild drag there must not count
    recs[-1]["metrics"]["cd"] *= 5.0
    drone_validation.v6e(rows, E387_POLARS, {203800.0: recs})
    d = next(r for r in rows if r["name"] == "V6e cd ratio Re 203800")
    assert d["measured"] == pytest.approx(0.0, abs=1e-9)
    assert "4 points" in d["note"]


def test_v6e_refuses_records_off_the_tunnel_angles():
    recs = synthetic_su2(RUN_213, 203800.0, 1.0, 1.0)
    recs[0]["params"]["alpha_deg"] = 1.5
    with pytest.raises(ValueError, match="angle"):
        drone_validation.v6e([], E387_POLARS, {203800.0: recs})


def test_v6e_mesh_check_compares_cd_at_cl_0_6():
    rows = []
    medium = synthetic_su2(RUN_213, 203800.0, 1.0, 1.0)
    fine = synthetic_su2(RUN_213, 203800.0, 1.0, 1.03)
    drone_validation.v6e_mesh(rows, medium, fine)
    r = rows[0]
    assert r["name"].startswith("V6e mesh") and r["tolerance"] == 0.05
    assert r["deviation"] == pytest.approx(0.03, abs=1e-6) and r["verdict"] == "pass"


# ---- V6f ----

def test_v6f_reports_the_closed_forms_against_each_nominal_reynolds(fixed):
    rows = []
    drone_validation.v6f(rows, E387_POLARS, fixed)
    names = [r["name"] for r in rows]
    for re in ("101800", "203800", "305200"):
        for what in ("cl_alpha", "alpha_L0", "cd ratio", "cl_max"):
            assert f"V6f {what} Re {re}" in names
    assert all(r["verdict"] == "report" and r["tolerance"] is None for r in rows)
    assert all(np.isfinite(r["measured"]) and np.isfinite(r["reference"]) for r in rows)
    a = next(r for r in rows if r["name"] == "V6f cl_alpha Re 203800")
    # the tunnel slope over its linear points (cl below 0.85 cl_max, from_polar's rule): 0.1017/deg
    assert a["reference"] == pytest.approx(0.1017, abs=0.002)
    assert 0.05 < a["measured"] < 0.12                           # k_eff 2 pi per radian, in per degree
    assert "camber" in a["note"] and "thickness" in a["note"]


def test_v6f_and_v6e_are_pure_in_their_inputs():
    polars = copy.deepcopy(E387_POLARS)
    drone_validation.v6f([], polars, drone_validation.ledger.load_all())
    assert polars == E387_POLARS

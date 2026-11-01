"""postprocess.metrics on synthetic inlets (independent references) and on a real Euler run."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from geometry.inlet import design_points
from physics.atmosphere import state as atmosphere
from physics.constants import GAMMA
from physics.shock import normal
from postprocess.metrics import compute
from tests.test_surface_split import marker, write_case
from worker import run_case

SCRATCH = Path("/tmp/claude-0/-home-user-ai-engineering/4e62754b-8c8b-5b87-a61c-cb95358da47b/scratchpad")
REAL_EULER = SCRATCH / "inlet" / "inlet88_euler"
REAL_LAM = SCRATCH / "lam"

trapezoid = getattr(np, "trapezoid", None) or np.trapz
G = design_points(8.0, 8.0)
THETA_T = G["theta_t"]
AXIS = np.array([math.cos(THETA_T), math.sin(THETA_T)])
NORMAL = np.array([-AXIS[1], AXIS[0]])
GEOMETRY = {"X1": 0.1, "theta_t_deg": math.degrees(THETA_T), "C": G["C"].tolist(),
            "P": G["P"].tolist(), "E_body": G["E_body"].tolist(), "E_cowl": G["E_cowl"].tolist(),
            "recovery_2shock_inviscid": G["recovery"], "M2_inviscid": G["M2"]}
FREE = atmosphere(30)
P0_INF = FREE["p"] * (1 + 0.2 * 4.0**2) ** 3.5
RHO, P_CORE, M_CORE = 0.05, 4900.0, 2.9
A_CORE = math.sqrt(GAMMA * P_CORE / RHO)


def mach_profile(t, uniform=False):
    """M across the throat (t in 0..1): uniform core, parabolic deficit to 0.1 M_core at each wall."""
    if uniform:
        return np.full_like(t, M_CORE)
    d = np.minimum(t, 1.0 - t)                                   # distance to the nearest wall
    delta = 0.12
    deficit = np.where(d < delta, 0.9 * (1.0 - d / delta) ** 2, 0.0)
    return M_CORE * (1.0 - deficit)


def throat_marker(uniform=False, tilt_deg=3.0):
    """Nodes on the inclined throat segment E_body -> E_cowl (uneven spacing) and the flow there,
    directed tilt_deg away from the duct axis so that the n . V projection matters."""
    t = 0.5 * (1 - np.cos(np.linspace(0.0, np.pi, 45)))         # clustered at both walls
    pts = G["E_body"][:, None] + (G["E_cowl"] - G["E_body"])[:, None] * t
    M = mach_profile(t, uniform)
    angle = THETA_T + math.radians(tilt_deg)
    speed = M * A_CORE
    m = marker(pts[0], pts[1], rho=RHO, p=P_CORE, u=speed * math.cos(angle), v=speed * math.sin(angle),
               q=0.0)
    return m, t, M, tilt_deg


def body_marker(q_ramp1, t_arc, q_ramp2):
    """Body nodes: ramp 1 (11 nodes) then ramp 2 at arc lengths t_arc from the corner."""
    x1 = np.linspace(0.0, 0.1, 11)[:-1]
    ramp1 = np.column_stack([x1, x1 * math.tan(math.radians(8))])
    ramp2 = G["C"][None, :] + t_arc[:, None] * AXIS[None, :]
    xy = np.vstack([ramp1, ramp2])
    return marker(xy[:, 0], xy[:, 1], q=np.concatenate([np.full(len(x1), q_ramp1), q_ramp2]))


def cowl_marker(dist, q_inner):
    """Cowl: inner nodes at distances `dist` from the lip (listed far to near), then 4 outer nodes."""
    inner = G["P"][:, None] + AXIS[:, None] * dist[::-1]
    out_dir = np.array([math.cos(THETA_T + math.radians(6)), math.sin(THETA_T + math.radians(6))])
    outer = G["P"][:, None] + out_dir[:, None] * np.array([0.003, 0.006, 0.009, 0.012])
    xy = np.hstack([inner, outer])
    return marker(xy[0], xy[1], rho=0.04, q=np.concatenate([q_inner[::-1], np.full(4, 9.9e5)]))


def write_inlet(tmp_path, uniform=False, solver="NAVIER_STOKES", q_ramp1=1.0e5, history_scale=None,
                tilt_deg=3.0):
    """A synthetic inlet case. Returns the expected ramp-2 / cowl numbers."""
    throat, t, M, _ = throat_marker(uniform, tilt_deg)
    L = float(np.linalg.norm(G["E_body"] - G["C"]))
    t_arc = np.concatenate([np.linspace(0.0, L - 0.012, 40), [L - 0.003, L - 0.001, L]])
    centre = 20                                                  # q peaks at this node, 30 kW/m^2
    q2 = 1.0e4 + 2.0e4 * np.exp(-(((t_arc - t_arc[centre]) / 0.02) ** 2))
    q2[-2:] = 1.0e6                                              # within 2 mm of the throat: excluded
    dist = np.array([0.0, 0.0005, 0.0015, 0.0025, 0.004, 0.008, 0.02, 0.04, 0.05])
    q_in = np.array([8.0e5, 4.0e5, 2.0e5, 6.0e4, 5.0e4, 4.0e4, 3.0e4, 2.0e4, 1.0e4])
    markers = {"body": body_marker(q_ramp1, t_arc, q2), "cowl": cowl_marker(dist, q_in),
               "outlet_duct": throat}
    params = {"family": "inlet2r", "solver": solver, "theta1_deg": 8.0, "theta2_deg": 8.0,
              "tag": "test"}
    write_case(tmp_path, markers, params=params, geometry=GEOMETRY)
    if solver == "EULER":                                        # SU2 Euler files have no Heat_Flux
        text = (tmp_path / "surface_flow.dat").read_text().replace(',"Heat_Flux"', "")
        lines = text.splitlines()
        n = int(lines[2].split("NODES=")[1].split(",")[0])
        lines[3:3 + n] = [" ".join(row.split()[:-1]) for row in lines[3:3 + n]]
        (tmp_path / "surface_flow.dat").write_text("\n".join(lines) + "\n")
    expected = {"q_peak": float(q2[centre]), "x_q_peak": float(G["C"][0] + t_arc[centre] * AXIS[0]),
                "heat_load": float(trapezoid(q2[:-2], t_arc[:-2])), "q_cowl": 6.0e4}
    if history_scale is not None:
        ref = throat_reference(t, M, tilt_deg)["recovery_throat"]
        (tmp_path / "history.csv").write_text(
            f'"Inner_Iter","Avg_TotalPress"\n0, 1.0\n1, {history_scale * ref * P0_INF:.10e}\n')
    return expected


def throat_reference(t, M, tilt_deg):
    """Mass-flux-weighted throat numbers computed directly with np.trapezoid and physics.shock.normal."""
    s = t * float(np.linalg.norm(G["E_cowl"] - G["E_body"]))
    phi = RHO * M * A_CORE * math.cos(math.radians(tilt_deg))     # rho |V| cos(angle to n)
    p0 = P_CORE * (1 + 0.2 * M**2) ** 3.5
    pi = np.array([normal(max(m, 1.0))["p0_ratio"] for m in M])
    flow = trapezoid(phi, s)
    mass_avg = lambda f: trapezoid(phi * f, s) / flow
    rec = mass_avg(p0) / P0_INF
    return {"recovery_throat": rec, "recovery_total": mass_avg(p0 * pi) / P0_INF,
            "mach": mass_avg(M), "flow": flow,
            "bulk": rec * normal(max(mass_avg(M), 1.0))["p0_ratio"]}


def test_nonuniform_throat_matches_independent_reference(tmp_path):
    expected = write_inlet(tmp_path, history_scale=1.002)
    _, t, M, tilt = throat_marker()
    ref = throat_reference(t, M, tilt)
    got = compute(tmp_path)
    assert (M < 1.0).any() and (M > 2.5).any()                  # the profile covers subsonic and core
    assert got["recovery_throat"] == pytest.approx(ref["recovery_throat"], rel=1e-6)
    assert got["recovery_total"] == pytest.approx(ref["recovery_total"], rel=1e-6)
    assert got["recovery_total_bulk"] == pytest.approx(ref["bulk"], rel=1e-6)
    assert got["mach_throat_massavg"] == pytest.approx(ref["mach"], rel=1e-6)
    assert got["capture_ratio"] == pytest.approx(ref["flow"] / (FREE["rho"] * 4.0 * FREE["a"] * G["P"][1]),
                                                 rel=1e-6)
    assert got["recovery_total"] < got["recovery_throat"] * 0.5       # terminal shock costs a lot
    assert got["p0_inf_Pa"] == pytest.approx(P0_INF, rel=1e-12)
    assert got["su2_avg_totalpress_Pa"] is not None and got["su2_crosscheck_pass"] is True
    assert got["q_peak_W_m2"] == pytest.approx(expected["q_peak"], rel=1e-9)
    assert got["notes"] == []


def test_su2_crosscheck_flag_fails_beyond_half_a_percent(tmp_path):
    write_inlet(tmp_path, history_scale=1.01)
    assert compute(tmp_path)["su2_crosscheck_pass"] is False


def test_no_history_means_no_crosscheck(tmp_path):
    write_inlet(tmp_path)
    got = compute(tmp_path)
    assert got["su2_avg_totalpress_Pa"] is None and got["su2_crosscheck_pass"] is None


def test_uniform_profile_bulk_equals_total(tmp_path):
    write_inlet(tmp_path, uniform=True)
    got = compute(tmp_path)
    assert got["recovery_total_bulk"] == pytest.approx(got["recovery_total"], rel=0, abs=1e-9)
    assert got["mach_throat_massavg"] == pytest.approx(M_CORE, abs=1e-9)
    _, t, M, tilt = throat_marker(uniform=True)
    assert got["recovery_throat"] == pytest.approx(throat_reference(t, M, tilt)["recovery_throat"],
                                                   rel=1e-9)


def test_heat_flux_peak_is_on_ramp_2_and_the_throat_is_excluded(tmp_path):
    expected = write_inlet(tmp_path, q_ramp1=1.0e5)             # ramp 1 is 3x the ramp-2 maximum
    got = compute(tmp_path)
    assert got["q_peak_W_m2"] == pytest.approx(30000.0, rel=1e-9)   # not 1e5 (ramp 1), not 1e6 (throat)
    assert got["x_q_peak_m"] == pytest.approx(expected["x_q_peak"], abs=1e-9)
    assert got["heat_load_body_W_per_m"] == pytest.approx(expected["heat_load"], rel=1e-9)
    # cowl: 8e5, 4e5, 2e5 are within 2 mm of the lip; the 2.5 mm node (6e4) is the largest left
    assert got["q_peak_cowl_W_m2"] == pytest.approx(expected["q_cowl"], rel=1e-9)


def test_euler_case_has_no_heat_flux_fields(tmp_path):
    write_inlet(tmp_path, solver="EULER")
    got = compute(tmp_path)
    for key in ("q_peak_W_m2", "x_q_peak_m", "q_peak_cowl_W_m2", "heat_load_body_W_per_m"):
        assert got[key] is None
    assert got["recovery_total"] > 0 and any("EULER" in n for n in got["notes"])


def test_negative_body_heat_flux_raises(tmp_path):
    write_inlet(tmp_path, q_ramp1=-1.0e5)
    # ramp 2 stays positive but the whole-body integral is negative on the cold wall
    with pytest.raises(ValueError, match="heat flux sign"):
        compute(tmp_path)


def test_flow_into_the_inlet_raises(tmp_path):
    write_inlet(tmp_path, tilt_deg=180.0)
    with pytest.raises(ValueError, match="no net mass flow"):
        compute(tmp_path)


# ---- run_case wiring ------------------------------------------------------------------------

FAKE = f"{sys.executable} {Path(__file__).parent / 'fake_su2.py'}"
WEDGE = {"family": "wedge", "theta1_deg": 10.0, "solver": "NAVIER_STOKES", "mesh_level": "coarse",
         "tag": "test", "max_iter": 300}


def test_run_case_records_metrics_error_and_no_result_json(tmp_path):
    from worker.make_case import make
    make(WEDGE, tmp_path)
    result = run_case.run(tmp_path, FAKE)                        # the fake surface is not on the mesh
    assert "metrics" not in result and "no node of marker" in result["metrics_error"]
    assert (tmp_path / "result_partial.json").exists() and not (tmp_path / "result.json").exists()


def test_run_case_writes_result_json_when_metrics_succeed(tmp_path, monkeypatch):
    from worker.make_case import make
    make(WEDGE, tmp_path)
    monkeypatch.setattr(run_case, "compute", lambda case_dir: {"recovery_total": 0.3})
    result = run_case.run(tmp_path, FAKE)
    assert result["metrics"] == {"recovery_total": 0.3} and "metrics_error" not in result
    assert json.loads((tmp_path / "result.json").read_text()) == result
    assert json.loads((tmp_path / "result_partial.json").read_text()) == result


def test_run_case_skips_metrics_after_a_failed_run(tmp_path, monkeypatch):
    from worker.make_case import make
    make(WEDGE, tmp_path)
    monkeypatch.setenv("FAKE_SU2_EXIT", "3")
    monkeypatch.setattr(run_case, "compute", lambda case_dir: pytest.fail("must not be called"))
    result = run_case.run(tmp_path, FAKE)
    assert "metrics" not in result and "metrics_error" not in result


# ---- real SU2 output ------------------------------------------------------------------------

@pytest.mark.skipif(not (REAL_EULER / "surface_flow.dat").exists(), reason="real Euler inlet not available")
def test_real_euler_inlet_design_point():
    got = compute(REAL_EULER)
    geometry = json.loads((REAL_EULER / "geometry.json").read_text())
    assert got["recovery_throat"] == pytest.approx(geometry["recovery_2shock_inviscid"], rel=0.02)
    assert got["su2_crosscheck_pass"] is True
    assert got["q_peak_W_m2"] is None
    assert 0.95 < got["capture_ratio"] <= 1.01
    assert got["recovery_total_bulk"] == pytest.approx(got["recovery_total"], rel=0.01)


@pytest.mark.skipif(not (REAL_LAM / "surface_flow.dat").exists(), reason="real wedge not available")
def test_real_wedge_reports_only_what_applies():
    got = compute(REAL_LAM)
    assert got["recovery_total"] is None and got["capture_ratio"] is None
    # runs/dev README: +4573 W per metre depth integrated over x; over the surface length it is 1/cos(10 deg) more
    assert got["heat_load_body_W_per_m"] == pytest.approx(4573.0 / math.cos(math.radians(10)), rel=0.002)
    assert any("wedge" in n for n in got["notes"])

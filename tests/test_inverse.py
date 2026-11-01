"""Inverse query and confirmation reporting on the synthetic pool (NOT a physics result)."""
import json

import numpy as np
import pytest

from analysis.confirm import run as confirm_run
from analysis.inverse import run as inverse_run
from analysis.pareto import make_grid
from physics.gates import check
from surrogate.synthetic import _raw
from tests.test_pareto import pool_rows

GRID = 61


@pytest.fixture(scope="module")
def rows():
    return pool_rows()


def true_constrained_optimum(q_cap):
    """Best true recovery on the feasible grid among points with true q <= q_cap (synthetic).

    The synthetic q is rescaled so that q = 3e4 at 8/8, as in make_pool."""
    t1, t2, feas = make_grid(GRID)
    scale = 3.0e4 / _raw(8.0, 8.0)[1]
    best = (-np.inf, None)
    for a, b in zip(t1[feas], t2[feas]):
        rec, q = _raw(a, b)
        if q * scale <= q_cap and rec > best[0]:
            best = (rec, (a, b))
    return best[1]


def test_inverse_lands_near_true_optimum(rows, tmp_path):
    q_obs = np.array([float(r["q_peak_W_m2"]) for r in rows])
    q_cap = float(np.quantile(q_obs, 0.5))
    res = inverse_run(rows, q_cap, tmp_path, grid=GRID)
    assert res["feasible"] and res["p_q_le_cap"] >= 0.9
    t1, t2 = true_constrained_optimum(q_cap)
    assert abs(res["theta1_deg"] - t1) <= 0.5 and abs(res["theta2_deg"] - t2) <= 0.5
    rec = res["recovery_total"]
    assert rec["lo90"] <= rec["mean"] <= rec["hi90"]
    q = res["q_peak_W_m2"]
    assert q["lo90"] <= q["median"] <= q["hi90"]


def test_params_json_passes_gates_and_schema(rows, tmp_path):
    q_cap = float(np.quantile([float(r["q_peak_W_m2"]) for r in rows], 0.4))
    res = inverse_run(rows, q_cap, tmp_path, grid=GRID)
    params = json.loads((tmp_path / "params.json").read_text())
    assert params == {"family": "inlet2r", "theta1_deg": round(res["theta1_deg"], 4),
                      "theta2_deg": round(res["theta2_deg"], 4), "mesh_level": "medium",
                      "tag": "confirm", "save_volume": False}
    assert check(params) == []
    assert res["case_id"].startswith("inlet2r-")


def test_unattainable_cap_is_reported_infeasible(rows, tmp_path):
    q_min = min(float(r["q_peak_W_m2"]) for r in rows)
    res = inverse_run(rows, 0.5 * q_min, tmp_path, grid=GRID)
    assert res["feasible"] is False and "no feasible design" in res["reason"]
    assert (tmp_path / "result.json").exists() and not (tmp_path / "params.json").exists()
    assert json.loads((tmp_path / "result.json").read_text())["feasible"] is False


def test_confirm_reports_pass_and_shrinkage(rows, tmp_path):
    """Hold out a 'confirmation' design: use the true synthetic value as the simulated result."""
    q_cap = float(np.quantile([float(r["q_peak_W_m2"]) for r in rows], 0.5))
    res = inverse_run(rows, q_cap, tmp_path, grid=GRID)
    scale = 3.0e4 / _raw(8.0, 8.0)[1]
    rec, q = _raw(res["theta1_deg"], res["theta2_deg"])
    conf = [{"case_id": res["case_id"], "theta1_deg": str(res["theta1_deg"]),
             "theta2_deg": str(res["theta2_deg"]), "recovery_total": str(rec),
             "q_peak_W_m2": str(q * scale), "status": "converged"}]
    out = confirm_run(rows, res, conf, tmp_path)
    assert (tmp_path / "confirm.json").exists()
    assert out["recovery_total"]["inside"] and out["q_peak_W_m2"]["inside"] and out["c2_pass"]
    assert out["refit"]["row_added"]
    assert out["refit"]["log_q_std"]["after"] <= out["refit"]["log_q_std"]["before"] * 1.05
    # a clearly wrong simulated value is reported as a miss with its direction
    conf[0]["recovery_total"] = str(rec * 0.5)
    miss = confirm_run(rows, res, conf, tmp_path)
    assert miss["c2_pass"] is False and miss["recovery_total"]["position"] == "below"

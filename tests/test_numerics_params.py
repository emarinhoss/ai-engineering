"""Optional airfoil2d solver settings for experiment S1/S2: unset changes nothing, set changes one line."""
import json
from pathlib import Path

from mcp_server.schemas import to_params, validate
from worker.make_case import case_id, make

REPO = Path(__file__).resolve().parent.parent
BASE = {"family": "airfoil2d", "airfoil": "e387", "reynolds": 203800.0, "alpha_deg": 4.23,
        "mesh_level": "coarse", "tag": "s1"}


def test_recorded_params_id_and_config_sha_unchanged(tmp_path):
    recorded = json.loads((REPO / "runs/e387/airfoil2d-7de8a51345/params.json").read_text())
    model, errors, _ = validate(recorded)
    assert errors == [] and to_params(model) == recorded
    assert case_id(recorded) == "airfoil2d-7de8a51345"
    job = json.loads((REPO / "su2queue_local/batches/e387_fine.batch.json").read_text())["jobs"][0]
    assert make(job["params"], tmp_path)["config_sha256"] == job["config_sha256"]


def _cfg(params, tmp_path):
    model, errors, _ = validate(params)
    assert errors == []
    make(to_params(model), tmp_path)
    return (tmp_path / "case.cfg").read_text()


def test_each_setting_changes_only_its_own_line(tmp_path):
    base = _cfg(BASE, tmp_path / "b")
    assert "CFL_ADAPT_PARAM= ( 0.5, 1.05, 1.0, 20.0 )" in base and "LINEAR_SOLVER_ERROR= 1E-6" in base
    assert "CONV_CAUCHY_ELEMS= 200" in base and "CONV_CAUCHY_EPS= 1E-5" in base
    for i, (extra, line) in enumerate((({"cfl_max": 100.0}, "CFL_ADAPT_PARAM= ( 0.5, 1.05, 1.0, 100.0 )"),
                                       ({"linear_tol": 1e-4}, "LINEAR_SOLVER_ERROR= 0.0001"),
                                       ({"cauchy_elems": 500, "cauchy_eps": 1e-7}, "CONV_CAUCHY_EPS= 1e-07"))):
        text = _cfg({**BASE, **extra}, tmp_path / str(i))
        assert line in text
        body = lambda t: [x for x in t.splitlines() if not x.startswith("%")]
        changed = [a for a, b in zip(body(base), body(text), strict=True) if a != b]
        assert len(changed) == len(extra)


def test_bounds_and_family():
    assert validate({**BASE, "cfl_max": 5000.0})[1] and validate({**BASE, "linear_tol": 0.5})[1]
    _, errors, _ = validate({"family": "wedge", "theta1_deg": 10.0, "tag": "x", "cfl_max": 50.0})
    assert any("cfl_max" in e for e in errors)

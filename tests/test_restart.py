"""Warm start for airfoil2d (experiment E0): schema, config, map_restart, queue donor gates."""
import json
from pathlib import Path

import numpy as np
import pytest

from cases.config import _output_files, _restart_lines
from mcp_server import queue
from mcp_server.schemas import to_params, validate
from worker.make_case import case_id, make
from worker.restart import map_restart, read_su2_coords
from worker.run_worker import write_warm_start

REPO = Path(__file__).resolve().parent.parent
BASE = {"family": "airfoil2d", "airfoil": "e387", "reynolds": 203800.0, "alpha_deg": 4.23,
        "mesh_level": "coarse", "tag": "e0"}
DONOR_ID = "airfoil2d-0123456789"


def test_old_params_and_case_id_unchanged():
    recorded = json.loads((REPO / "runs/e387/airfoil2d-7de8a51345/params.json").read_text())
    model, errors, _ = validate(recorded)
    assert errors == []
    assert to_params(model) == recorded               # no new key leaks into the params
    assert case_id(recorded) == "airfoil2d-7de8a51345"


def test_recorded_batch_config_sha_still_reproduces(tmp_path):
    batch = json.loads((REPO / "su2queue_local/batches/e387_fine.batch.json").read_text())
    job = batch["jobs"][0]
    made = make(job["params"], tmp_path)
    assert made["case_id"] == job["case_id"]
    assert made["config_sha256"] == job["config_sha256"]
    text = (tmp_path / "case.cfg").read_text()
    assert "RESTART_SOL" not in text and "READ_BINARY_RESTART" not in text
    assert "OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII )\n" in text


def test_schema_accepts_and_rejects():
    model, errors, _ = validate({**BASE, "save_restart": True, "restart_from": DONOR_ID})
    assert errors == [] and to_params(model)["restart_from"] == DONOR_ID
    for bad in ({"restart_from": "inlet2r-0123456789"}, {"restart_from": "airfoil2d-XYZ"},
                {"save_restart": "yes"}):
        assert validate({**BASE, **bad})[1]
    other = {"family": "wedge", "theta1_deg": 10.0, "tag": "t"}
    assert validate({**other, "save_restart": True})[1]
    assert validate({**other, "restart_from": DONOR_ID})[1]


def test_config_lines():
    assert _output_files({"save_restart": True}) == "( SURFACE_TECPLOT_ASCII, RESTART_ASCII )"
    assert _output_files({"save_restart": True, "save_volume": True}) == \
        "( SURFACE_TECPLOT_ASCII, TECPLOT_ASCII, RESTART_ASCII )"
    assert _output_files({}) == "( SURFACE_TECPLOT_ASCII )"
    assert _restart_lines({}) == ""
    params = to_params(validate({**BASE, "save_restart": True, "restart_from": DONOR_ID})[0])
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        make(params, tmp)
        text = (Path(tmp) / "case.cfg").read_text()
    assert "OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII, RESTART_ASCII )" in text
    assert "RESTART_SOL= YES\nREAD_BINARY_RESTART= NO\n" in text
    assert text.endswith("SOLUTION_FILENAME= solution_flow\nRESTART_SOL= YES\nREAD_BINARY_RESTART= NO\n")


HEADER = '"PointID","x","y","Pressure","Velocity_x"'


def donor_text(points):
    rows = [f"{k},{float(x)!r},{float(y)!r},{float(10 * x + y)!r},{float(x - y)!r}"
            for k, (x, y) in enumerate(points)]
    return "\n".join([HEADER, *rows]) + "\n"


def test_map_restart_identity():
    pts = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 2.0], [0.5, 0.25]])
    text, dmax = map_restart(donor_text(pts), pts)
    assert text == donor_text(pts) and dmax == 0.0


def test_map_restart_permuted_donor_gets_new_point_ids():
    pts = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 2.0]])
    perm = pts[[2, 0, 1]]
    text, dmax = map_restart(donor_text(perm), pts)
    assert text == donor_text(pts) and dmax == 0.0   # PointID rewritten to the new node order


def test_map_restart_coarser_donor_uses_nearest_row():
    donor = np.array([[0.0, 0.0], [1.0, 0.0]])
    mesh = np.array([[0.1, 0.0], [0.9, 0.1], [0.4, 0.0]])
    text, dmax = map_restart(donor_text(donor), mesh)
    head, *rows = text.splitlines()
    assert head == HEADER                              # header and column order preserved
    got = [[float(v) for v in r.split(",")] for r in rows]
    assert [g[0] for g in got] == [0, 1, 2]
    assert [g[1:3] for g in got] == mesh.tolist()      # x, y are this mesh's
    assert [g[3] for g in got] == [0.0, 10.0, 0.0]     # Pressure copied from nodes 0, 1, 0
    assert dmax == pytest.approx(0.4)                  # node (0.4, 0) to donor (0, 0)


def test_map_restart_rejects_bad_header():
    with pytest.raises(ValueError):
        map_restart('"a","b"\n1,2\n', np.zeros((1, 2)))


def test_read_su2_coords_matches_mesh_node_order(tmp_path):
    make({**BASE}, tmp_path)
    coords = read_su2_coords(tmp_path / "mesh.su2")
    nodes = json.loads((tmp_path / "mesh_markers.json").read_text())["nodes"]
    assert coords.shape == (nodes, 2)


def test_write_warm_start_and_donor_missing(tmp_path):
    queue_root, run_dir = tmp_path / "q", tmp_path / "q" / "runs" / "airfoil2d-aaaaaaaaaa"
    run_dir.mkdir(parents=True)
    make(BASE, run_dir)
    coords = read_su2_coords(run_dir / "mesh.su2")
    params = {**BASE, "restart_from": DONOR_ID}
    with pytest.raises(FileNotFoundError):
        write_warm_start(queue_root, run_dir, params)
    donor_dir = queue_root / "runs" / DONOR_ID
    donor_dir.mkdir(parents=True)
    (donor_dir / "restart_flow.csv").write_text(donor_text(coords + 1e-4))
    info = write_warm_start(queue_root, run_dir, params)
    assert info["restart_from"] == DONOR_ID and len(info["donor_restart_sha256"]) == 64
    assert info["max_nn_distance_m"] == pytest.approx(np.hypot(1e-4, 1e-4), rel=1e-3)
    assert (run_dir / "solution_flow.csv").read_text().splitlines()[0] == HEADER


# ---------------------------------------------------------------- queue.create donor gates

def stage_donor(root, **changes):
    params = to_params(validate({**BASE, "save_restart": True, **changes})[0])   # defaults filled in
    d = root / "jobs" / DONOR_ID
    d.mkdir(parents=True)
    (d / "params.json").write_text(json.dumps(params))


def errors_for(**changes):
    res = queue.validate_only({**BASE, "restart_from": DONOR_ID, **changes})
    return res["stage"], res["errors"]


@pytest.fixture
def qdir(tmp_path, monkeypatch):
    monkeypatch.setenv("SU2_QUEUE_DIR", str(tmp_path))
    return tmp_path


def test_donor_unknown(qdir):
    stage, errors = errors_for()
    assert stage == "donor" and "not a staged job" in errors[0]


def test_donor_without_save_restart(qdir):
    stage_donor(qdir, save_restart=False)
    stage, errors = errors_for()
    assert stage == "donor" and "save_restart" in errors[0]


def test_donor_other_family(qdir):
    d = qdir / "jobs" / DONOR_ID
    d.mkdir(parents=True)
    (d / "params.json").write_text(json.dumps({"family": "wedge", "save_restart": True}))
    assert any("not an airfoil2d" in e for e in errors_for()[1])


@pytest.mark.parametrize("change", [{"airfoil": "naca2412"}, {"reynolds": 150000.0},
                                    {"transition": "NONE"}])
def test_donor_different_section_reynolds_or_transition(qdir, change):
    stage_donor(qdir)
    stage, errors = errors_for(**change)
    assert stage == "donor" and len(errors) >= 1


def test_donor_other_alpha_and_mesh_allowed(qdir):
    stage_donor(qdir, alpha_deg=1.0, mesh_level="medium")
    res = queue.create({**BASE, "restart_from": DONOR_ID})
    assert res["ok"], res

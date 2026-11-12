"""Start files for experiment W1 (task W1.1): reader, scaling, writer, schema, config, worker copy."""
import json
from pathlib import Path

import numpy as np
import pytest

from cases.config import _restart_lines
from mcp_server.schemas import to_params, validate
from worker import startfile as sf
from worker.make_case import make
from worker.restart import read_su2_coords
from worker.run_worker import copy_start_file

REPO = Path(__file__).resolve().parent.parent
BASE = {"family": "airfoil2d", "camber_pct": 3.549782, "thickness_pct": 9.848634, "reynolds": 170203.9,
        "alpha_deg": 6.0, "mesh_level": "coarse", "transition": "BCM", "max_iter": 6000, "tag": "w1_cold_a"}
SU2_TEXT = ('"PointID","x","y","Pressure","Velocity_x","Velocity_y","Nu_Tilde"\n'
            "0, 3.100000000000000e+01, 0.000000000000000e+00, -1.481553829981706e-05, "
            "9.947481830629099e-01, 1.030479467358879e-01, 8.819317012604870e-08\n"
            "1, 2.690574084195795e+01, 0.000000000000000e+00, 1.927899333387252e-04, "
            "9.948794489786821e-01, 1.014192697395788e-01, 8.818075021236141e-08\n")


def test_su2_text_reads_and_writes_back_unchanged():
    header, data = sf.read_restart(SU2_TEXT)
    assert header[3:] == list(sf.FIELDS)
    assert sf.write_solution(data[:, 1:3], sf.fields(header, data)) == SU2_TEXT


def test_scale_then_unscale_returns_the_fields_and_clips_negative_nu_tilde():
    f = sf.fields(*sf.read_restart(SU2_TEXT))
    assert np.allclose(sf.unscale(sf.scale(f, 170203.9), 170203.9), f, rtol=1e-15)
    assert sf.scale(f, 2.0)[0, 3] == 2.0 * f[0, 3] and np.array_equal(sf.scale(f, 2.0)[:, :3], f[:, :3])
    g = f.copy()
    g[1, 3] = -1.0
    assert sf.unscale(g, 1.0)[1, 3] == 0.0


def test_reader_and_writer_refuse_bad_input():
    with pytest.raises(ValueError):
        sf.read_restart(SU2_TEXT.replace("\n1, ", "\n7, "))
    with pytest.raises(ValueError):
        sf.write_solution(np.zeros((3, 2)), np.zeros((2, 4)))


def test_schema_and_config():
    params = to_params(validate({**BASE, "start_file": "w1_x.csv"})[0])
    assert params["start_file"] == "w1_x.csv"
    assert _restart_lines(params) == "RESTART_SOL= YES\nREAD_BINARY_RESTART= NO\n"
    assert validate({**BASE, "start_file": "../x.csv"})[1]
    assert validate({**BASE, "start_file": "a.csv", "restart_from": "airfoil2d-0123456789"})[1]
    assert validate({"family": "wedge", "theta1_deg": 10.0, "tag": "t", "start_file": "a.csv"})[1]


def test_config_without_start_file_is_unchanged():
    """The cold runs of W1 must render the config of every recorded case: no restart lines."""
    recorded = json.loads((REPO / "runs/e0/airfoil2d-32d362298f/params.json").read_text())
    assert _restart_lines(to_params(validate(recorded)[0])) == ""


def test_copy_start_file(tmp_path):
    queue_root = tmp_path / "q"
    run_dir = queue_root / "runs" / "airfoil2d-aaaaaaaaaa"
    run_dir.mkdir(parents=True)
    make(BASE, run_dir)
    params = {**BASE, "start_file": "w1_a.csv"}
    with pytest.raises(FileNotFoundError):
        copy_start_file(queue_root, run_dir, params)
    coords = read_su2_coords(run_dir / "mesh.su2")
    (queue_root / "starts").mkdir()
    text = sf.write_solution(coords, np.ones((len(coords), 4)))
    (queue_root / "starts" / "w1_a.csv").write_text(text)
    info = copy_start_file(queue_root, run_dir, params)
    assert (run_dir / "solution_flow.csv").read_text() == text
    assert info["start_file"] == "w1_a.csv" and len(info["start_sha256"]) == 64
    (queue_root / "starts" / "w1_a.csv").write_text(sf.write_solution(coords[:-1], np.ones((len(coords) - 1, 4))))
    with pytest.raises(ValueError):
        copy_start_file(queue_root, run_dir, params)

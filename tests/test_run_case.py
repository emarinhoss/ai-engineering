import json
import sys
from pathlib import Path

import pytest

from worker.make_case import make
from worker.run_case import main, parse_n_cores, run, run_first_working

FAKE = f"{sys.executable} {Path(__file__).parent / 'fake_su2.py'}"
PARAMS = {"family": "wedge", "theta1_deg": 10.0, "solver": "NAVIER_STOKES",
          "mesh_level": "coarse", "tag": "test", "max_iter": 300}


@pytest.fixture
def case_dir(tmp_path):
    make(PARAMS, tmp_path)
    return tmp_path


def test_normal_run(case_dir):
    result = run(case_dir, FAKE)
    assert result["run"]["exit_code"] == 0 and result["run"]["timeout"] is False
    assert result["run"]["iterations"] == 300
    assert result["run"]["wall_time_s"] > 0
    assert result["history_summary"]["status"] == "converged"
    assert result["solver"]["version"].startswith("SU2 vFAKE")
    assert result["solver"]["n_cores"] == 1
    assert len(result["solver"]["config_sha256"]) == 64
    assert (case_dir / "solver_version.txt").read_text().startswith("SU2 vFAKE")
    assert "fake_su2" in (case_dir / "log.txt").read_text()
    assert json.loads((case_dir / "result_partial.json").read_text()) == result
    assert (case_dir / "surface_flow.csv").exists()


def test_exit_code_is_recorded(case_dir, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_EXIT", "3")
    result = run(case_dir, FAKE)
    assert result["run"]["exit_code"] == 3
    assert result["history_summary"]["status"] == "error"


def test_timeout_kills_and_records(case_dir, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_SLEEP", "5")
    result = run(case_dir, FAKE, timeout_s=1)
    assert result["run"]["timeout"] is True and result["run"]["exit_code"] is None
    assert result["run"]["wall_time_s"] < 4
    assert "history_summary" not in result


def test_nan_residual_is_diverged(case_dir, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_NAN", "1")
    assert run(case_dir, FAKE)["history_summary"]["status"] == "diverged"


def test_stale_outputs_are_removed(case_dir, monkeypatch):
    run(case_dir, FAKE)
    monkeypatch.setenv("FAKE_SU2_SLEEP", "5")
    result = run(case_dir, FAKE, timeout_s=1)
    assert not (case_dir / "history.csv").exists()
    assert result["run"]["iterations"] == 0


def test_parse_n_cores():
    assert parse_n_cores(["mpirun", "-n", "2", "--allow-run-as-root", "SU2_CFD"]) == 2
    assert parse_n_cores(["SU2_CFD"]) == 1


def test_fallback_when_first_command_cannot_start(case_dir):
    result = run_first_working(case_dir, ["no_such_binary_xyz", FAKE])
    assert result["run"]["exit_code"] == 0
    assert result["solver"]["fallback_from"] == ["no_such_binary_xyz"]
    assert json.loads((case_dir / "result_partial.json").read_text()) == result


def test_command_line(case_dir, capsys):
    main([str(case_dir), "--su2-cmd", FAKE, "--timeout", "60"])
    assert json.loads(capsys.readouterr().out)["run"]["iterations"] == 300

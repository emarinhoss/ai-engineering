import json
import sys
from pathlib import Path

import pytest

from postprocess.tecplot import read_tecplot_ascii
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
    assert (case_dir / "surface_flow.dat").exists()
    assert not (case_dir / "surface_flow.csv").exists()
    surface = read_tecplot_ascii(case_dir / "surface_flow.dat")
    assert surface["zonetype"] == ["FELINESEG"] and (surface["data"]["Heat_Flux"] > 0).all()
    assert not (case_dir / "flow.dat").exists()          # save_volume is off in PARAMS


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


def test_volume_output_only_when_requested(tmp_path):
    make({**PARAMS, "save_volume": True}, tmp_path)
    run(tmp_path, FAKE)
    volume = read_tecplot_ascii(tmp_path / "flow.dat")
    assert volume["zonetype"] == ["FEQUADRILATERAL"] and len(volume["data"]["x"]) == 25


def test_stale_outputs_are_removed(case_dir, monkeypatch):
    run(case_dir, FAKE)
    for stale in ("flow.dat", "restart_flow.dat", "restart_flow.csv", "surface_flow.dat"):
        (case_dir / stale).write_text("old\n")
    monkeypatch.setenv("FAKE_SU2_SLEEP", "5")
    result = run(case_dir, FAKE, timeout_s=1)
    assert not (case_dir / "history.csv").exists()
    for stale in ("flow.dat", "restart_flow.dat", "restart_flow.csv", "surface_flow.dat"):
        assert not (case_dir / stale).exists()
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


# ---- local work directory (flow.dat rewritten in place on a Drive mount came back corrupt) ----

def test_local_work_dir_runs_there_and_copies_every_output_back(tmp_path, monkeypatch):
    import worker.run_case as rc
    case = tmp_path / "case"
    make({**PARAMS, "save_volume": True}, case)
    work = tmp_path / "local" / "w"
    seen = {}
    real = rc._execute

    def spy(tokens, cwd, log_path, timeout_s):
        seen["cwd"], seen["log"] = Path(cwd), Path(log_path)
        seen["case_files_during_run"] = sorted(p.name for p in case.iterdir())
        return real(tokens, cwd, log_path, timeout_s)

    monkeypatch.setattr(rc, "_execute", spy)
    result = run(case, FAKE, work_dir=work)
    assert seen["cwd"] == work and seen["log"].parent == work
    assert "history.csv" not in seen["case_files_during_run"]     # nothing written to case/ mid-run
    assert not work.exists()                                       # local copy removed afterwards
    for name in ("history.csv", "surface_flow.dat", "flow.dat", "log.txt", "solver_version.txt",
                 "result_partial.json", "result.json"):
        assert (case / name).exists(), name
    assert not list(case.glob("*.part"))
    volume = read_tecplot_ascii(case / "flow.dat")
    assert volume["zonetype"] == ["FEQUADRILATERAL"] and len(volume["data"]["x"]) == 25
    assert result["run"]["iterations"] == 300 and result["history_summary"]["status"] == "converged"
    assert "metrics" in result


def test_local_work_dir_gives_the_same_record_as_running_in_place(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    make(PARAMS, a)
    make(PARAMS, b)
    ra = run(a, FAKE)
    rb = run(b, FAKE, work_dir=tmp_path / "w")
    for block in ("history_summary", "metrics"):
        assert ra[block] == rb[block], block
    assert ra["run"]["iterations"] == rb["run"]["iterations"]
    assert ra["solver"]["config_sha256"] == rb["solver"]["config_sha256"]


def test_local_work_dir_leaves_untouched_inputs_alone(tmp_path):
    case = tmp_path / "case"
    make(PARAMS, case)
    mesh = case / "mesh.su2"
    before = mesh.stat().st_mtime_ns
    run(case, FAKE, work_dir=tmp_path / "w")
    assert mesh.stat().st_mtime_ns == before


def test_local_work_dir_copies_back_after_a_timeout(tmp_path, monkeypatch):
    case = tmp_path / "case"
    make(PARAMS, case)
    monkeypatch.setenv("FAKE_SU2_SLEEP", "5")
    result = run(case, FAKE, timeout_s=1, work_dir=tmp_path / "w")
    assert result["run"]["timeout"] is True
    assert (case / "log.txt").exists() and not (tmp_path / "w").exists()

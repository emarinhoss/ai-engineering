"""Guards added after the real-SU2 faults of 2026-11-03 (docs/specs/task6b_real_su2_faults.md):
R9, the worker re-checks the physics gates; R5, the worker stops a solver left in the run folder."""
import json
import subprocess
import sys
import time
from pathlib import Path

from tests.test_worker_end_to_end import PARAMS, flags, stage_job, worker
from worker.make_case import make


def test_hand_made_job_that_fails_a_gate_is_refused_before_su2(tmp_path):
    queue = tmp_path / "queue"
    params = {"family": "inlet2r", "theta1_deg": 12.0, "theta2_deg": 14.0, "solver": "NAVIER_STOKES",
              "mesh_level": "coarse", "max_iter": 300, "tag": "test"}
    job = make(params, tmp_path / "staging")               # not create_case: no gate has run
    (queue / "jobs").mkdir(parents=True)
    (queue / "jobs" / f"{job['case_id']}.json").write_text(json.dumps(job))
    assert worker(queue, "--once") == 0
    run_dir = queue / "runs" / job["case_id"]
    assert flags(queue, job["case_id"]) == ["0-seen", "2-failed"]
    error = json.loads((run_dir / "error.json").read_text())
    assert error["reason"] == "gates" and "gate 4" in error["detail"][0]
    assert not (run_dir / "log.txt").exists() and not (run_dir / "mesh.su2").exists()


def test_leftover_solver_in_the_run_folder_is_stopped(tmp_path, capsys):
    queue = tmp_path / "queue"
    job = stage_job(queue, PARAMS)
    run_dir = queue / "runs" / job["case_id"]
    run_dir.mkdir(parents=True)
    leftover = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], cwd=run_dir)
    try:
        time.sleep(0.3)
        assert worker(queue, "--once") == 0
        assert "stopped 1 leftover solver process" in capsys.readouterr().out
        assert leftover.wait(timeout=10) != 0               # killed, not finished
        assert flags(queue, job["case_id"]) == ["0-seen", "1-running", "2-done"]
    finally:
        leftover.kill()

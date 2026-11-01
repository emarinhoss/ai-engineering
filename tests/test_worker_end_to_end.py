"""The queue worker with the fake SU2: one job from jobs/<case_id>.json to 2-done."""
import json
import sys
from pathlib import Path

from worker.make_case import make
from worker.run_worker import main

TESTS, REPO = Path(__file__).parent, Path(__file__).resolve().parent.parent

# The command that stands in for SU2. WRAPPER is normally None: the worker runs tests/fake_su2.py
# directly. A test can set it to the text of a python script to run instead (see
# test_worker_failures.test_missing_surface_file_is_a_postprocess_error).
WRAPPER = None


def fake_command(directory):
    """Command line of the fake SU2: tests/fake_su2.py, or the script text in WRAPPER if set."""
    if WRAPPER is None:
        return f"{sys.executable} {TESTS / 'fake_su2.py'}"
    script = Path(directory) / "fake_su2_replacement.py"
    script.write_text(WRAPPER)
    return f"{sys.executable} {script}"


PARAMS = {"family": "wedge", "theta1_deg": 10.0, "solver": "NAVIER_STOKES",
          "mesh_level": "coarse", "tag": "test", "max_iter": 300}


def stage_job(queue, params=PARAMS, created_at=None):
    """Build the case in a scratch folder and upload its job.json to <queue>/jobs/<case_id>.json."""
    scratch = Path(queue).parent / "scratch" / f"{params['theta1_deg']}"
    job = make(params, scratch)
    job["created_at"] = created_at or job["created_at"]
    (Path(queue) / "jobs").mkdir(parents=True, exist_ok=True)
    (Path(queue) / "jobs" / f"{job['case_id']}.json").write_text(json.dumps(job, indent=1))
    return job


def worker(queue, *extra):
    """Run the worker in this process against the fake SU2; return its exit code."""
    return main(["--queue", str(queue), "--su2-cmd", fake_command(Path(queue).parent), "--poll", "1",
                 "--worker-id", "test-worker", *extra])


def flags(queue, cid):
    return sorted(p.name for p in (Path(queue) / "runs" / cid / "status").iterdir())


def test_once_finishes_one_job_and_second_run_does_nothing(tmp_path, capsys):
    queue = tmp_path / "queue"
    job = stage_job(queue)
    cid, run_dir = job["case_id"], queue / "runs" / job["case_id"]

    assert worker(queue, "--once") == 0
    assert flags(queue, cid) == ["0-seen", "1-running", "2-done"]

    result = json.loads((run_dir / "result.json").read_text())
    assert result["case_id"] == cid and result["params"] == PARAMS
    for block in ("geometry", "mesh", "solver", "run", "convergence", "metrics", "code", "files"):
        assert isinstance(result[block], dict), block
    assert result["job"] == {k: job[k] for k in ("mesh_fingerprint", "config_sha256", "code_commit")}
    assert result["mesh"]["nodes"] > 0 and result["mesh"]["quality"]["pass"] is True
    assert result["run"]["exit_code"] == 0 and result["run"]["worker_id"] == "test-worker"
    assert result["run"]["iterations"] == 300
    assert result["convergence"]["status"] == "converged"
    assert "heat_load_body_W_per_m" in result["metrics"]
    assert result["solver"]["config_sha256"] == job["config_sha256"]

    assert (queue / "runs" / f"{cid}.result.json").read_text() == (run_dir / "result.json").read_text()
    assert (run_dir / "solver_version.txt").read_text().startswith("SU2 vFAKE")
    assert json.loads((run_dir / "job.json").read_text()) == job      # the uploaded job, unchanged
    assert not list(run_dir.glob("**/.tmp-*"))                        # atomic writes left no litter

    beat = json.loads((run_dir / "heartbeat.json").read_text())
    assert beat["worker_id"] == "test-worker" and beat["current_case"] == cid
    assert beat["iterations"] == 300 and beat["started_at"] <= beat["last_seen"]
    assert json.loads((queue / "worker" / "heartbeat.json").read_text())["worker_id"] == "test-worker"

    before = {p: p.stat().st_mtime_ns for p in queue.rglob("*") if p.is_file() and "worker" not in p.parts}
    capsys.readouterr()
    assert worker(queue, "--once") == 0
    assert "nothing to do" in capsys.readouterr().out
    after = {p: p.stat().st_mtime_ns for p in queue.rglob("*") if p.is_file() and "worker" not in p.parts}
    assert after == before                                            # nothing touched, nothing new


def test_oldest_job_first(tmp_path):
    queue = tmp_path / "queue"
    newer = stage_job(queue, {**PARAMS, "theta1_deg": 9.0}, created_at="2026-11-01T10:00:00+00:00")
    older = stage_job(queue, {**PARAMS, "theta1_deg": 11.0}, created_at="2026-11-01T09:00:00+00:00")
    assert worker(queue, "--once") == 0
    assert flags(queue, older["case_id"])[-1] == "2-done"
    assert not (queue / "runs" / newer["case_id"]).exists()


def write_batch(queue, jobs, name="batch0123456"):
    path = Path(queue) / "jobs" / f"{name}.batch.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"batch_id": name, "jobs": jobs}, indent=1))
    return path


def test_batch_file_jobs_run_in_created_at_order(tmp_path, capsys):
    queue = tmp_path / "queue"
    scratch = tmp_path / "jobs_src"
    newer = make({**PARAMS, "theta1_deg": 9.0}, scratch / "a")
    older = make({**PARAMS, "theta1_deg": 11.0}, scratch / "b")
    newer["created_at"], older["created_at"] = "2026-11-01T10:00:00+00:00", "2026-11-01T09:00:00+00:00"
    path = write_batch(queue, [newer, older])                  # listed newest first on purpose
    text = path.read_text()

    assert worker(queue, "--once") == 0
    assert flags(queue, older["case_id"])[-1] == "2-done"
    assert not (queue / "runs" / newer["case_id"]).exists()
    assert worker(queue, "--once") == 0
    assert flags(queue, newer["case_id"]) == ["0-seen", "1-running", "2-done"]
    assert flags(queue, older["case_id"]) == ["0-seen", "1-running", "2-done"]

    capsys.readouterr()
    assert worker(queue, "--once") == 0
    assert "nothing to do" in capsys.readouterr().out
    assert path.read_text() == text                            # the worker never rewrites the batch


def test_batch_with_a_finished_entry_runs_only_the_pending_one(tmp_path):
    queue = tmp_path / "queue"
    scratch = tmp_path / "jobs_src"
    done = make({**PARAMS, "theta1_deg": 9.0}, scratch / "a")
    todo = make({**PARAMS, "theta1_deg": 11.0}, scratch / "b")
    done["created_at"], todo["created_at"] = "2026-11-01T09:00:00+00:00", "2026-11-01T10:00:00+00:00"
    write_batch(queue, [done, todo])
    finished = queue / "runs" / done["case_id"] / "status"
    finished.mkdir(parents=True)
    (finished / "2-done").write_text("x\n")

    assert worker(queue, "--once") == 0
    assert flags(queue, todo["case_id"])[-1] == "2-done"
    assert sorted(p.name for p in finished.iterdir()) == ["2-done"]      # untouched
    assert not (queue / "runs" / done["case_id"] / "log.txt").exists()

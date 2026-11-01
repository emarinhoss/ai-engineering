"""Fault injection (docs/specs/task6_agent_eval.md): every bad input is stopped before SU2 runs and
every solver failure is recorded with a reason. One test per fault; each asserts which layer caught it
and what the user sees, and appends a row to MATRIX. The last test writes docs/faults/fault_matrix.md.

No SU2 is needed: the solver is tests/fake_su2.py. F8 (kill -9) lives in tests/test_worker_resume.py.
"""
import inspect
import json
import os
import re
import shutil
import signal
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cases.config
from geometry import structured
from mcp_server import queue
from tests import test_worker_resume
from tests.test_worker_end_to_end import flags, stage_job, worker

REPO = Path(__file__).resolve().parent.parent
MATRIX_FILE = REPO / "docs" / "faults" / "fault_matrix.md"
MATRIX = []        # rows (fault id, injected how, caught by, user-visible message), filled by the tests
FAULT_IDS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10a", "F10b"]
MESSAGE_LIMIT = 120

INLET = {"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "mesh_level": "coarse", "tag": "test"}
WEDGE = {"family": "wedge", "theta1_deg": 8.0, "mesh_level": "coarse", "tag": "test", "max_iter": 300}


def record(fault, injected, caught_by, message):
    """Add a row to the matrix. Hashes are shortened to 8 digits; the message is cut at 120 characters."""
    text = re.sub(r"[0-9a-f]{64}", lambda m: m.group(0)[:8] + "...", " ".join(str(message).split()))
    MATRIX.append((fault, injected, caught_by, text[:MESSAGE_LIMIT]))


@pytest.fixture
def staging(tmp_path, monkeypatch):
    """A staging queue ($SU2_QUEUE_DIR) and a repo folder for runs/ that are both empty."""
    monkeypatch.setenv("SU2_QUEUE_DIR", str(tmp_path / "staging"))
    monkeypatch.setattr(queue, "REPO", tmp_path / "repo")
    return tmp_path


def nothing_staged(tmp_path):
    """No job directory, no file left in the temporary build folder, nothing under runs/."""
    root = tmp_path / "staging"
    assert not (root / "jobs").exists()
    assert not (root / "tmp").exists() or list((root / "tmp").iterdir()) == []
    assert not (tmp_path / "repo").exists()


# ---------------------------------------------------------------- before submit: the gates

def test_f1_schema_theta2_above_bound(staging):
    results = [call({**INLET, "theta2_deg": 20.0}) for call in (queue.validate_only, queue.create)]
    for res in results:
        assert res["ok"] is False and res["stage"] == "schema"
        assert any("theta2_deg" in e and "[5, 14]" in e for e in res["errors"])
    nothing_staged(staging)
    record("F1", "theta2_deg = 20 (bound is 14)", "validate_config / create_case: stage schema",
           results[0]["errors"][0])


def test_f2_physics_gate_total_turning(staging):
    params = {**INLET, "theta1_deg": 12.0, "theta2_deg": 14.0}      # 26 deg total turning
    results = [call(params) for call in (queue.validate_only, queue.create)]
    for res in results:
        assert res["ok"] is False and res["stage"] == "gates"
        assert "gate 4" in res["errors"][0] and "24 deg" in res["errors"][0]    # gate 5 may also fire
    nothing_staged(staging)
    record("F2", "theta1 = 12, theta2 = 14 (total turning 26 deg; the run in runs/dev diverged)",
           "validate_config / create_case: stage gates (physics.gates, gate 4)", results[0]["errors"][0])


def test_f3_inverted_cell(staging, monkeypatch):
    real = structured.Mesh.quality
    monkeypatch.setattr(structured.Mesh, "quality", lambda self: {**real(self), "n_inverted": 1})
    results = [call(WEDGE) for call in (queue.validate_only, queue.create)]
    for res in results:
        assert res["ok"] is False and res["stage"] == "mesh_quality"
        assert any("n_inverted = 1" in e for e in res["errors"])
    nothing_staged(staging)
    record("F3", "mesh quality reports n_inverted = 1 (monkeypatched)",
           "validate_config / create_case: stage mesh_quality (worker.make_case)", results[0]["errors"][0])


def test_f4_unknown_su2_key_in_template(staging, monkeypatch):
    templates = staging / "templates"
    shutil.copytree(cases.config.TEMPLATES, templates)
    with open(templates / "navier_stokes.cfg", "a") as f:
        f.write("\nBOGUS_SU2_KEY= 1\n")
    monkeypatch.setattr(cases.config, "TEMPLATES", templates)
    results = [call(WEDGE) for call in (queue.validate_only, queue.create)]
    for res in results:
        assert res["ok"] is False and res["stage"] == "config_keys"
        assert res["errors"] == ["key not in the SU2 config template: BOGUS_SU2_KEY"]
    nothing_staged(staging)
    record("F4", "config template with the key BOGUS_SU2_KEY (not in SU2 v8.2.0)",
           "validate_config / create_case: stage config_keys (cases.check_keys)", results[0]["errors"][0])


# ---------------------------------------------------------------- in the worker: solver failures

def error_of(queue_dir, job):
    """error.json of a job that the worker flagged 2-failed, with no result to download."""
    seen = flags(queue_dir, job["case_id"])
    assert seen[-1] == "2-failed" and "2-done" not in seen
    assert not (queue_dir / "runs" / f"{job['case_id']}.result.json").exists()
    return json.loads((queue_dir / "runs" / job["case_id"] / "error.json").read_text())


def test_f5_solver_divergence(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_NAN", "1")
    queue_dir = tmp_path / "queue"
    job = stage_job(queue_dir)
    assert worker(queue_dir, "--once") == 0
    err = error_of(queue_dir, job)
    run_dir = queue_dir / "runs" / job["case_id"]
    assert err["reason"] == "nan"
    partial = json.loads((run_dir / "result_partial.json").read_text())
    assert partial["convergence"]["status"] == "diverged" and partial["run"]["exit_code"] == 0
    assert (run_dir / "history.csv").is_file() and partial["run"]["iterations"] > 0     # history kept
    record("F5", "fake SU2 writes NaN residuals (FAKE_SU2_NAN)",
           "worker: history check, reason nan, convergence.status diverged", f"{err['reason']}: {err['detail']}")


def test_f6_solver_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_EXIT", "3")
    queue_dir = tmp_path / "queue"
    job = stage_job(queue_dir)
    assert worker(queue_dir, "--once") == 0
    err = error_of(queue_dir, job)
    assert err["reason"] == "nonzero_exit" and err["detail"]["exit_code"] == 3
    tail = err["detail"]["log_tail"]
    assert tail and any("fake_su2" in line for line in tail)
    assert (queue_dir / "runs" / job["case_id"] / "log.txt").is_file()
    record("F6", "fake SU2 exits with code 3 (FAKE_SU2_EXIT)", "worker: exit-code check, reason nonzero_exit",
           f"{err['reason']}: exit code {err['detail']['exit_code']}; log tail: {tail[-1]}")


def processes_in(directory):
    """pids of the processes whose working directory is `directory` (Linux /proc)."""
    pids = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if Path(os.readlink(proc / "cwd")) == directory.resolve():
                pids.append(int(proc.name))
        except OSError:
            pass
    return pids


@pytest.mark.skipif(not Path("/proc/self/cwd").exists(), reason="needs /proc (Linux)")
def test_f7_timeout_kills_the_process_group(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_SLEEP", "30")
    queue_dir = tmp_path / "queue"
    job = stage_job(queue_dir)
    run_dir = queue_dir / "runs" / job["case_id"]
    try:
        assert worker(queue_dir, "--once", "--timeout", "1") == 0
        left = processes_in(run_dir)
    finally:
        for pid in processes_in(run_dir):           # do not leave a 30 s sleeper behind if the test fails
            os.kill(pid, signal.SIGKILL)
    err = error_of(queue_dir, job)
    assert err["reason"] == "timeout" and "1 s" in err["detail"]
    assert json.loads((run_dir / "result_partial.json").read_text())["run"]["timeout"] is True
    assert left == []                                # SU2 (here the fake) did not outlive the worker's kill
    record("F7", "fake SU2 sleeps 30 s, worker timeout 1 s (FAKE_SU2_SLEEP)",
           "worker: timeout, process group killed, reason timeout", f"{err['reason']}: {err['detail']}")


def test_f8_killed_worker_is_covered_by_the_resume_test():
    """kill -9 in the middle of a job is tested in tests/test_worker_resume.py; not repeated here (it
    starts a subprocess and takes ten seconds). This test only checks that the test exists and still
    asserts the message that the matrix quotes."""
    name = "test_killed_worker_job_is_rerun_once_and_done_job_is_untouched"
    source = inspect.getsource(getattr(test_worker_resume, name))
    assert "kill" in source and "--stale-minutes" in source and "crash victim" in source
    record("F8", "kill -9 of the worker mid-run, restart with a stale heartbeat "
                 "(tests/test_worker_resume.py, not run here)",
           "worker: heartbeat check, job re-run once, finished jobs untouched",
           "crash victim (1-running, stale heartbeat), will be re-run")


def test_f9_tampered_job_never_starts_su2(tmp_path):
    queue_dir = tmp_path / "queue"
    job = stage_job(queue_dir)
    path = queue_dir / "jobs" / f"{job['case_id']}.json"
    path.write_text(json.dumps({**job, "mesh_fingerprint": "0" * 64}))
    assert worker(queue_dir, "--once") == 0
    err = error_of(queue_dir, job)
    run_dir = queue_dir / "runs" / job["case_id"]
    assert err["reason"] == "mesh_mismatch"
    assert err["detail"]["job_mesh_fingerprint"] == "0" * 64
    assert err["detail"]["our_mesh_fingerprint"] == job["mesh_fingerprint"]
    assert "1-running" not in flags(queue_dir, job["case_id"])                       # SU2 never started
    assert not (run_dir / "history.csv").exists() and not (run_dir / "log.txt").exists()
    record("F9", "job file with an edited mesh_fingerprint", "worker: regenerated-mesh check, reason mesh_mismatch",
           f"{err['reason']}: job mesh_fingerprint {'0' * 64} differs from the mesh the worker regenerated; "
           "SU2 not started")


# ---------------------------------------------------------------- results coming back

def run_and_get_result(tmp_path):
    """Stage and upload a wedge job, run the worker on the drive folder, return (case_id, record)."""
    cid = queue.create(WEDGE)["case_id"]
    assert queue.submit(cid)["ok"]
    drive = tmp_path / "drive"
    (drive / "jobs").mkdir(parents=True)
    shutil.copyfile(queue.queue_dir() / "jobs" / cid / "job.json", drive / "jobs" / f"{cid}.json")
    assert worker(drive, "--once") == 0
    return cid, json.loads((drive / "runs" / f"{cid}.result.json").read_text())


def refused_and_unchanged(tmp_path, cid, tampered, case=None):
    """ingest_result must refuse; no result.json, status still pending, nothing under runs/."""
    res = queue.ingest_result(case or cid, json.dumps(tampered))
    staged = queue.queue_dir() / "jobs" / cid
    assert res["ok"] is False and res["errors"], res
    assert not (staged / "result.json").exists()
    assert queue.status(cid)[0]["status"] == "pending"
    assert not (tmp_path / "repo").exists()
    return res


def test_f10a_result_with_the_wrong_case_id(staging):
    cid, rec = run_and_get_result(staging)
    res = refused_and_unchanged(staging, cid, {**rec, "case_id": "wedge-0000000000"})
    assert res["stage"] == "record" and "case_id" in res["errors"][0]
    record("F10a", "result.json whose case_id belongs to another job", "ingest_result: stage record (check_record)",
           res["errors"][0])


def test_f10b_result_with_the_wrong_mesh_fingerprint(staging):
    cid, rec = run_and_get_result(staging)
    res = refused_and_unchanged(staging, cid, {**rec, "job": {**rec["job"], "mesh_fingerprint": "f" * 64}})
    assert res["stage"] == "record" and "job.mesh_fingerprint" in res["errors"][0]
    record("F10b", "result.json whose job.mesh_fingerprint differs from the staged job",
           "ingest_result: stage record (check_record)", res["errors"][0])


# ---------------------------------------------------------------- the matrix (must stay the last test)

def test_zz_write_matrix():
    missing = [f for f in FAULT_IDS if f not in {row[0] for row in MATRIX}]
    if missing:
        pytest.skip(f"no row for {missing}: run the whole file to regenerate {MATRIX_FILE.name}")
    rows = sorted(MATRIX, key=lambda row: FAULT_IDS.index(row[0]))
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [
        (f"<!-- Generated by tests/test_faults.py on {today}; do not edit by hand. "
         "Re-run: python -m pytest -q tests/test_faults.py -->"),
        "# Fault matrix",
        "",
        (f"Generated by `tests/test_faults.py` on {today}. Every row comes from a test that ran without "
         "SU2 (the solver is `tests/fake_su2.py`). F8 is run by `tests/test_worker_resume.py`. "
         "Messages are cut at 120 characters; hashes show 8 digits."),
        "",
        "| Fault | Injected how | Caught by | User sees |",
        "|---|---|---|---|",
    ]
    lines += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    MATRIX_FILE.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_FILE.write_text("\n".join(lines) + "\n")
    assert len(rows) == len(FAULT_IDS)

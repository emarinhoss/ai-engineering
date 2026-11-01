"""Kill the worker (kill -9) in the middle of a job; a restart re-runs that job once."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.test_worker_end_to_end import PARAMS, REPO, fake_command, flags, stage_job, worker

pytestmark = pytest.mark.skipif(not Path("/proc/self/cwd").exists(), reason="needs /proc (Linux)")


def wait_for(predicate, what, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


def kill_solver_in(run_dir):
    """The fake SU2 runs in its own session, so killing the worker's group leaves it behind; end it,
    as the end of a Colab runtime would."""
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if Path(os.readlink(proc / "cwd")) == run_dir.resolve():
                os.kill(int(proc.name), signal.SIGKILL)
        except OSError:
            pass


def test_killed_worker_job_is_rerun_once_and_done_job_is_untouched(tmp_path, capsys):
    queue = tmp_path / "queue"
    first = stage_job(queue, {**PARAMS, "theta1_deg": 9.0}, created_at="2026-11-01T09:00:00+00:00")
    second = stage_job(queue, {**PARAMS, "theta1_deg": 11.0}, created_at="2026-11-01T10:00:00+00:00")
    assert worker(queue, "--once") == 0                       # the older job is done before the crash
    done_dir = queue / "runs" / first["case_id"]
    result_mtime = (done_dir / "result.json").stat().st_mtime_ns
    victim = queue / "runs" / second["case_id"]

    proc = subprocess.Popen(
        [sys.executable, "-m", "worker.run_worker", "--queue", str(queue), "--su2-cmd",
         fake_command(tmp_path), "--poll", "1", "--worker-id", "doomed"],
        cwd=REPO, env={**os.environ, "FAKE_SU2_SLEEP": "8"}, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for(lambda: (victim / "status" / "1-running").exists()
                 and (victim / "heartbeat.json").exists(), "1-running and a heartbeat")
        os.killpg(proc.pid, signal.SIGKILL)
    finally:
        proc.kill()
        proc.wait()
        kill_solver_in(victim)
    assert flags(queue, second["case_id"]) == ["0-seen", "1-running"]
    assert not (victim / "result.json").exists()

    capsys.readouterr()
    assert worker(queue, "--once") == 0                       # heartbeat is fresh: not a crash victim
    assert "nothing to do" in capsys.readouterr().out
    assert flags(queue, second["case_id"]) == ["0-seen", "1-running"]

    assert worker(queue, "--once", "--stale-minutes", "0") == 0
    out = capsys.readouterr().out
    assert out.count("crash victim") == 1                     # reported at start
    assert out.count(f"{second['case_id']}: running") == 1    # and run exactly once
    assert flags(queue, second["case_id"]) == ["0-seen", "1-running", "2-done"]
    result = json.loads((victim / "result.json").read_text())
    assert result["run"]["worker_id"] == "test-worker" and result["run"]["iterations"] == 300
    assert json.loads((victim / "heartbeat.json").read_text())["iterations"] == 300
    assert (queue / "runs" / f"{second['case_id']}.result.json").is_file()

    assert (done_dir / "result.json").stat().st_mtime_ns == result_mtime
    assert flags(queue, first["case_id"]) == ["0-seen", "1-running", "2-done"]
    assert worker(queue, "--once", "--stale-minutes", "0") == 0       # nothing left to run
    assert "nothing to do" in capsys.readouterr().out


def test_ctrl_c_flags_nothing_and_stops_the_solver(tmp_path):
    queue = tmp_path / "queue"
    job = stage_job(queue)
    run_dir = queue / "runs" / job["case_id"]
    proc = subprocess.Popen(
        [sys.executable, "-m", "worker.run_worker", "--queue", str(queue), "--su2-cmd",
         fake_command(tmp_path), "--poll", "1"],
        cwd=REPO, env={**os.environ, "FAKE_SU2_SLEEP": "30"}, stdout=subprocess.PIPE, text=True)
    try:
        wait_for(lambda: (run_dir / "heartbeat.json").exists(), "the first heartbeat")
        time.sleep(1)                                         # SU2 has started
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=20)
        time.sleep(0.5)
        left = [p for p in Path("/proc").glob("[0-9]*") if _cwd(p) == run_dir.resolve()]
    finally:
        proc.kill()
        kill_solver_in(run_dir)
    assert proc.returncode == 0 and "interrupted" in out
    assert flags(queue, job["case_id"]) == ["0-seen", "1-running"]
    assert left == []                                         # the solver did not outlive the worker


def _cwd(proc):
    try:
        return Path(os.readlink(proc / "cwd"))
    except OSError:
        return None

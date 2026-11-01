"""Colab queue worker: pick pending jobs from a Drive queue folder, run SU2, write results.

    python -m worker.run_worker --queue DIR --su2-cmd "mpirun -n 2 SU2_CFD" --poll 20 --timeout 2400

DIR holds jobs/<case_id>.json (the job.json that worker.make_case wrote, uploaded by Claude),
jobs/<batch_id>.batch.json (many jobs in one file, each entry handled like a job file) and
runs/<case_id>/ (written here). Layout and flags: docs/specs/01_interfaces.md, "Job directory".
Pending = a job file with no status/2-done and no status/2-failed flag in its run directory. A job
flagged 1-running whose heartbeat is older than --stale-minutes is a crash victim and is re-run.
The worker never deletes or moves anything; re-running a job overwrites its outputs.
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from geometry.structured import mesh_bbox, mesh_fingerprint
from worker.make_case import REPO, StageError, case_id, config_sha256, git_commit, make, sha256_file
from worker.run_case import run

JOB_KEYS = ("case_id", "params", "created_at", "mesh_fingerprint", "config_sha256", "code_commit")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def say(message):
    print(f"[{now()}] {message}", flush=True)


# ---------------------------------------------------------------- small file helpers

def write_json(path, obj):
    """Atomic: write a temporary file next to the target, then rename it."""
    path = Path(path)
    tmp = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, path)


def set_flag(run_dir, name):
    """Create status/<name> (for example 2-done) atomically."""
    status = Path(run_dir) / "status"
    status.mkdir(parents=True, exist_ok=True)
    tmp = status / f".tmp-{os.getpid()}-{name}"
    tmp.write_text(now() + "\n")
    os.replace(tmp, status / name)


def flags(run_dir):
    status = Path(run_dir) / "status"
    return {p.name for p in status.iterdir() if not p.name.startswith(".")} if status.is_dir() else set()


def read_json(path):
    return json.loads(Path(path).read_text())


def count_iterations(history):
    """Rows of history.csv written so far (lines minus the header); 0 if there is no file."""
    try:
        with open(history) as f:
            return max(0, sum(1 for line in f if line.strip()) - 1)
    except OSError:
        return 0


# ---------------------------------------------------------------- which jobs to run

def heartbeat_age_s(run_dir):
    """Seconds since last_seen in runs/<id>/heartbeat.json; infinite if missing or unreadable."""
    try:
        last = datetime.fromisoformat(read_json(Path(run_dir) / "heartbeat.json")["last_seen"])
        return (datetime.now(timezone.utc) - last).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return float("inf")


def job_state(run_dir, stale_s):
    """finished (2-done or 2-failed) | new | running (fresh heartbeat) | crashed (stale heartbeat)."""
    seen = flags(run_dir)
    if "2-done" in seen or "2-failed" in seen:
        return "finished"
    if "1-running" not in seen:
        return "new"
    return "crashed" if heartbeat_age_s(run_dir) >= stale_s else "running"


def check_job(job, label, expected_id=None):
    """`job` if it has all JOB_KEYS (and, when given, case_id == expected_id), else None."""
    try:
        missing = [k for k in JOB_KEYS if k not in job]
    except TypeError:
        missing = list(JOB_KEYS)
    if missing or (expected_id is not None and job["case_id"] != expected_id):
        say(f"skipping {label}: missing keys {missing} or case_id differs from file name")
        return None
    return job


def read_job(path):
    """The job dict, or None (with a message) if the file is unreadable or incomplete.
    A file still being synced by Drive is simply tried again at the next poll."""
    try:
        job = read_json(path)
    except (OSError, ValueError) as err:
        say(f"skipping {Path(path).name}: {err}")
        return None
    return check_job(job, Path(path).name, Path(path).stem)


def read_batch(path):
    """The valid jobs of a jobs/<batch_id>.batch.json (each checked like a single job file).
    The batch file itself is never rewritten."""
    try:
        entries = read_json(path)["jobs"]
        if not isinstance(entries, list):
            raise TypeError("'jobs' is not a list")
    except (OSError, ValueError, KeyError, TypeError) as err:
        say(f"skipping {Path(path).name}: {err}")
        return []
    jobs = (check_job(e, f"{Path(path).name} entry {i}") for i, e in enumerate(entries))
    return [j for j in jobs if j]


def jobs_in_state(queue, states, stale_s):
    """Jobs (single files jobs/<case_id>.json and entries of jobs/*.batch.json) whose state is in
    `states`, oldest created_at first. A case_id listed twice is taken once."""
    jobs_dir = Path(queue) / "jobs"
    found, seen = [], set()
    candidates = [read_job(p) for p in sorted(jobs_dir.glob("*.json")) if not p.name.endswith(".batch.json")]
    for path in sorted(jobs_dir.glob("*.batch.json")):
        candidates += read_batch(path)
    for job in candidates:
        if job and job["case_id"] not in seen:
            seen.add(job["case_id"])
            if job_state(Path(queue) / "runs" / job["case_id"], stale_s) in states:
                found.append(job)
    return sorted(found, key=lambda j: (j["created_at"], j["case_id"]))


# ---------------------------------------------------------------- one job

def check_regenerated(job, run_dir):
    """Rebuild mesh and config from the job's params into run_dir and compare with the job file.
    Returns None if they agree, else (reason, detail) for error.json."""
    try:
        if case_id(job["params"]) != job["case_id"]:
            return "bad_job", "case_id does not match the sha256 of the params in the job file"
        make(job["params"], run_dir)
    except (StageError, ValueError, NotImplementedError) as err:
        return "make_error", str(err)
    write_json(run_dir / "job.json", job)             # make() wrote a new job.json; keep the uploaded one
    ours = mesh_fingerprint(run_dir / "mesh.su2")
    if ours != job["mesh_fingerprint"]:
        detail = {"job_mesh_fingerprint": job["mesh_fingerprint"], "our_mesh_fingerprint": ours,
                  "job_code_commit": job["code_commit"], "our_code_commit": git_commit()}
        if "mesh_bbox" in job:                        # how far apart are the two meshes?
            mine = mesh_bbox(run_dir / "mesh.su2")
            detail.update(job_mesh_bbox=job["mesh_bbox"], our_mesh_bbox=mine,
                          max_bbox_diff_m=max(abs(a - b) for a, b in zip(job["mesh_bbox"], mine)))
        return "mesh_mismatch", detail
    ours = config_sha256(run_dir / "case.cfg")
    # Job files written before 2026-11-01 evening hash the whole file, comments included.
    if job["config_sha256"] not in (ours, sha256_file(run_dir / "case.cfg")):
        return "config_mismatch", {"job_config_sha256": job["config_sha256"],
                                   "our_config_sha256": ours, "job_code_commit": job["code_commit"],
                                   "our_code_commit": git_commit()}
    return None


def tail(path, n=8):
    try:
        return Path(path).read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def failure_of(result, run_dir, timeout_s):
    """None if the run is good, else (reason, detail)."""
    run_info, summary = result["run"], result.get("history_summary", {})
    if run_info["timeout"]:
        return "timeout", f"SU2 killed after {timeout_s:g} s"
    if run_info["exit_code"] != 0 and summary.get("status") != "diverged":
        return "nonzero_exit", {"exit_code": run_info["exit_code"], "log_tail": tail(run_dir / "log.txt")}
    if summary.get("status") == "diverged":
        return "nan", "non-finite residual in history.csv (convergence.status = diverged)"
    if "metrics" not in result or "history_summary" not in result or summary.get("status") == "error":
        return "postprocess_error", (result.get("metrics_error") or summary.get("error")
                                     or "no history.csv or no metrics after the run")
    return None


def git_dirty():
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True,
                             text=True, check=True)
        return bool(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def run_record(job, run_dir, result, worker_id):
    """The run record of 01_interfaces.md: run_case's result plus params, geometry, mesh, code, job."""
    record = {k: v for k, v in result.items() if k != "history_summary"}
    record["run"]["worker_id"] = worker_id
    markers = read_json(run_dir / "mesh_markers.json")
    record.update(
        case_id=job["case_id"], params=job["params"], geometry=read_json(run_dir / "geometry.json"),
        mesh={"level": markers["level"], "nodes": markers["nodes"], "cells": markers["cells"],
              "quality": read_json(run_dir / "mesh_quality.json")},
        convergence=result.get("history_summary"),
        code={"git_commit": git_commit(), "dirty": git_dirty()},
        files={"history": "history.csv", "surface": "surface_flow.dat", "log": "log.txt"},
        job={k: job[k] for k in ("mesh_fingerprint", "config_sha256", "code_commit")})
    return record


def fail(queue, run_dir, job, reason, detail):
    write_json(run_dir / "error.json", {"case_id": job["case_id"], "reason": reason,
                                        "detail": detail, "at": now()})
    set_flag(run_dir, "2-failed")
    os.sync()
    say(f"{job['case_id']}: FAILED ({reason})")


def run_with_heartbeat(run_dir, job, args):
    """Call worker.run_case.run in a thread; write heartbeat.json every args.heartbeat seconds."""
    timeout_s = min(args.timeout, job.get("timeout_s", args.timeout))
    box = {}

    def target():
        try:
            box["result"] = run(run_dir, args.su2_cmd, timeout_s)
        except Exception as err:  # noqa: BLE001  (reported as a failed job, not a dead worker)
            box["error"] = f"{type(err).__name__}: {err}"

    started = now()
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    while True:
        beat = {"worker_id": args.worker_id, "started_at": started, "last_seen": now(),
                "current_case": job["case_id"], "iterations": count_iterations(run_dir / "history.csv")}
        write_json(run_dir / "heartbeat.json", beat)
        write_worker_heartbeat(args, job["case_id"])
        if not thread.is_alive():
            return box, timeout_s
        thread.join(args.heartbeat)


def process(job, args):
    """Steps 2 to 4 of the spec for one job."""
    queue, cid = Path(args.queue), job["case_id"]
    run_dir = queue / "runs" / cid
    run_dir.mkdir(parents=True, exist_ok=True)
    set_flag(run_dir, "0-seen")
    say(f"{cid}: regenerating mesh and config at commit {git_commit()[:10]}")
    problem = check_regenerated(job, run_dir)
    if problem:
        return fail(queue, run_dir, job, *problem)

    set_flag(run_dir, "1-running")
    say(f"{cid}: running {args.su2_cmd}")
    box, timeout_s = run_with_heartbeat(run_dir, job, args)
    if "error" in box:
        return fail(queue, run_dir, job, "postprocess_error", box["error"])
    result = box["result"]
    record = run_record(job, run_dir, result, args.worker_id)
    write_json(run_dir / "result_partial.json", record)
    if "metrics" in record:
        write_json(run_dir / "result.json", record)
    problem = failure_of(result, run_dir, timeout_s)
    if problem:
        return fail(queue, run_dir, job, *problem)
    write_json(queue / "runs" / f"{cid}.result.json", record)
    set_flag(run_dir, "2-done")
    os.sync()
    say(f"{cid}: done, convergence {record['convergence']['status']}")


# ---------------------------------------------------------------- the loop

def write_worker_heartbeat(args, current_case=None):
    folder = Path(args.queue) / "worker"
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / "heartbeat.json", {"worker_id": args.worker_id, "last_seen": now(),
                                           "current_case": current_case, "pid": os.getpid()})


def stop_solver():
    """Ctrl-C: SU2 runs in its own session (see run_case), so end it explicitly."""
    try:
        for children in Path(f"/proc/{os.getpid()}/task").glob("*/children"):
            for pid in children.read_text().split():
                os.killpg(int(pid), signal.SIGKILL)
    except OSError:
        pass


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--queue", required=True, help="folder with jobs/ and runs/")
    ap.add_argument("--su2-cmd", default="SU2_CFD")
    ap.add_argument("--poll", type=float, default=20, help="seconds between scans of jobs/")
    ap.add_argument("--timeout", type=float, default=2400,
                    help="seconds per SU2 run (the smaller of this and the job's timeout_s)")
    ap.add_argument("--once", action="store_true", help="process at most one job, then exit")
    ap.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    ap.add_argument("--stale-minutes", type=float, default=10,
                    help="a 1-running job with an older heartbeat is a crash victim")
    ap.add_argument("--heartbeat", type=float, default=30, help="seconds between heartbeats")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    queue, stale_s = Path(args.queue), args.stale_minutes * 60
    for sub in ("jobs", "runs", "worker"):
        (queue / sub).mkdir(parents=True, exist_ok=True)
    write_worker_heartbeat(args)
    say(f"worker {args.worker_id} on {queue}, SU2 command: {args.su2_cmd}")
    for job in jobs_in_state(queue, {"crashed"}, stale_s):
        say(f"{job['case_id']}: crash victim (1-running, stale heartbeat), will be re-run")
    try:
        while True:
            write_worker_heartbeat(args)
            todo = jobs_in_state(queue, {"new", "crashed"}, stale_s)
            if todo:
                try:
                    process(todo[0], args)
                except Exception:  # noqa: BLE001  (keep serving; the job is retried once stale)
                    traceback.print_exc()
                    if args.once:
                        return 1
                    time.sleep(args.poll)
            elif args.once:
                say("nothing to do")
            else:
                time.sleep(args.poll)
            if args.once:
                return 0
    except KeyboardInterrupt:
        stop_solver()
        say("interrupted; a running job keeps 1-running and is re-run once its heartbeat is stale")
        return 0


if __name__ == "__main__":
    sys.exit(main())

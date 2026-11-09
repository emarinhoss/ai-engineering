"""Colab queue worker: pick pending jobs from a Drive queue folder, run SU2, write results.

    python -m worker.run_worker --queue DIR --su2-cmd "mpirun -n 2 SU2_CFD" --poll 20 --timeout 2400

DIR holds jobs/<case_id>.json (the job.json that worker.make_case wrote, uploaded by Claude),
jobs/<batch_id>.batch.json (many jobs in one file, each entry handled like a job file) and
runs/<case_id>/ (written here). Layout and flags: docs/specs/01_interfaces.md, "Job directory".
Pending = a job file with no status/2-done and no status/2-failed flag in its run directory. A job
flagged 1-running whose heartbeat is older than --stale-minutes is a crash victim and is re-run.
The regenerated mesh is compared by fingerprint (1 um rounding); a job file staged before
2026-11-08 evening carries the old 1 nm digest, which the worker also accepts.
Before a job runs, the worker checks the physics gates again (a job file not made by create_case
has not been checked) and stops any process still running in its run folder (an SU2 left behind
by a worker that died alone).
Several workers may serve one queue only if they are SHARDED (--shard K/N): a worker takes the jobs
whose case_id hash is congruent to K modulo N, so the shards are disjoint and no claim race exists.
Without a shard flag the worker takes every job, and two such workers on one queue would both start
the same job (the 1-running flag is written only after the mesh is regenerated, and Drive sync adds
tens of seconds on top), so never run two unsharded workers on one queue.
The worker never deletes or moves anything; re-running a job overwrites its outputs. The one
exception is `--retry-reason R`: at start-up, a job flagged 2-failed whose error.json has reason R
gets its 2-failed and 1-running flags removed (error.json is kept as error.retried.json), so it is
pending again. Next to every `runs/<id>.result.json` the worker writes `runs/<id>.result.sha256`,
and next to every failure `runs/<id>.error.sha256` (digest of `runs/<id>/error.json`), so that a
copy that crossed Drive through a transcription can be checked byte for byte at ingest.
"""
import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from geometry.structured import mesh_bbox, mesh_fingerprint, mesh_fingerprint_nm
from physics import gates
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


def write_digest(target, digest_path):
    """Write the sha256 of the bytes of `target` to `digest_path` (64 hex digits and a newline)."""
    Path(digest_path).write_text(sha256_file(target) + "\n")


def backfill_digests(queue):
    """Digest files for results and failures written before digests existed."""
    runs = Path(queue) / "runs"
    for result in runs.glob("*.result.json"):
        digest = result.with_name(result.name[: -len(".json")] + ".sha256")
        if not digest.exists():
            write_digest(result, digest)
    for error in runs.glob("*/error.json"):
        digest = runs / f"{error.parent.name}.error.sha256"
        if not digest.exists():
            write_digest(error, digest)


def clear_flag(run_dir, name):
    try:
        (Path(run_dir) / "status" / name).unlink()
    except FileNotFoundError:
        pass


def retry_failed(queue, reasons):
    """Make jobs flagged 2-failed with error.json reason in `reasons` pending again. Returns the
    case ids. error.json becomes error.retried.json and its digest file is removed."""
    runs, retried = Path(queue) / "runs", []
    for error in sorted(runs.glob("*/error.json")):
        run_dir = error.parent
        if "2-failed" not in flags(run_dir):
            continue
        try:
            reason = read_json(error).get("reason")
        except (OSError, ValueError):
            continue
        if reason not in reasons:
            continue
        os.replace(error, run_dir / "error.retried.json")
        (runs / f"{run_dir.name}.error.sha256").unlink(missing_ok=True)
        clear_flag(run_dir, "2-failed")
        clear_flag(run_dir, "1-running")
        retried.append(run_dir.name)
        say(f"{run_dir.name}: 2-failed ({reason}) cleared by --retry-reason, will be re-run")
    os.sync()
    return retried


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


def parse_shard(text):
    """"K/N" -> (K, N) with 0 <= K < N; the default "0/1" is every job."""
    m = re.fullmatch(r"(\d+)/(\d+)", text.strip())
    if not m or int(m.group(2)) < 1 or int(m.group(1)) >= int(m.group(2)):
        raise ValueError(f"--shard must be K/N with 0 <= K < N, got {text!r}")
    return int(m.group(1)), int(m.group(2))


def in_shard(case_id, shard):
    """True if this worker's shard owns case_id: the hex digest after the family prefix, as an
    integer, modulo N equals K. Every case_id lands in exactly one of the N shards."""
    k, n = shard
    return int(case_id.rsplit("-", 1)[1], 16) % n == k


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


def jobs_in_state(queue, states, stale_s, shard=(0, 1)):
    """Jobs (single files jobs/<case_id>.json and entries of jobs/*.batch.json) whose state is in
    `states` and whose case_id is in `shard`, oldest created_at first. A case_id listed twice is
    taken once."""
    jobs_dir = Path(queue) / "jobs"
    found, seen = [], set()
    candidates = [read_job(p) for p in sorted(jobs_dir.glob("*.json")) if not p.name.endswith(".batch.json")]
    for path in sorted(jobs_dir.glob("*.batch.json")):
        candidates += read_batch(path)
    for job in candidates:
        if job and job["case_id"] not in seen and in_shard(job["case_id"], shard):
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
        # The MCP layer checks the gates before staging; a job file made any other way has not been
        # checked (real-SU2 fault R9, 2026-11-03: a hand-made 12/14 job reached SU2). Check again here.
        errors = gates.check(job["params"])
        if errors:
            return "gates", errors
        make(job["params"], run_dir)
    except (StageError, ValueError, NotImplementedError) as err:
        return "make_error", str(err)
    write_json(run_dir / "job.json", job)             # make() wrote a new job.json; keep the uploaded one
    ours = mesh_fingerprint(run_dir / "mesh.su2")
    ours_nm = mesh_fingerprint_nm(run_dir / "mesh.su2")   # job files staged before 2026-11-08 evening
    if job["mesh_fingerprint"] not in (ours, ours_nm):
        detail = {"job_mesh_fingerprint": job["mesh_fingerprint"], "our_mesh_fingerprint": ours,
                  "our_mesh_fingerprint_nm": ours_nm,
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
    write_digest(run_dir / "error.json", Path(queue) / "runs" / f"{job['case_id']}.error.sha256")
    set_flag(run_dir, "2-failed")
    os.sync()
    say(f"{job['case_id']}: FAILED ({reason})")


def run_with_heartbeat(run_dir, job, args):
    """Call worker.run_case.run in a thread; write heartbeat.json every args.heartbeat seconds."""
    timeout_s = min(args.timeout, job.get("timeout_s", args.timeout))
    box = {}
    # SU2 runs on local disk and its outputs are copied to the Drive run folder once at the end
    # (run_case docstring: in-place rewrites of flow.dat on the Drive mount corrupted it).
    work_dir = Path(args.work_root) / job["case_id"] if args.work_root else None
    progress = (work_dir or run_dir) / "history.csv"

    def target():
        try:
            box["result"] = run(run_dir, args.su2_cmd, timeout_s, work_dir=work_dir)
        except Exception as err:  # noqa: BLE001  (reported as a failed job, not a dead worker)
            box["error"] = f"{type(err).__name__}: {err}"

    started = now()
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    while True:
        beat = {"worker_id": args.worker_id, "started_at": started, "last_seen": now(),
                "current_case": job["case_id"],
                "iterations": count_iterations(progress if progress.exists() else run_dir / "history.csv")}
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

    left = stop_leftover_solvers(run_dir)
    if left:
        say(f"{cid}: stopped {left} leftover solver process(es) still running in the run folder")
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
    write_digest(queue / "runs" / f"{cid}.result.json", queue / "runs" / f"{cid}.result.sha256")
    set_flag(run_dir, "2-done")
    os.sync()
    say(f"{cid}: done, convergence {record['convergence']['status']}")


# ---------------------------------------------------------------- the loop

def stop_leftover_solvers(run_dir):
    """Kill processes still running in run_dir (an SU2 left behind by a worker that died alone;
    real-SU2 fault R5, 2026-11-03: two solvers wrote in one folder). Returns how many were stopped.
    Linux only: without /proc nothing is found."""
    stopped = 0
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if int(proc.name) != os.getpid() and Path(os.readlink(proc / "cwd")) == Path(run_dir).resolve():
                os.kill(int(proc.name), signal.SIGKILL)
                stopped += 1
        except (OSError, ValueError):
            pass
    return stopped


def write_worker_heartbeat(args, current_case=None):
    folder = Path(args.queue) / "worker"
    folder.mkdir(parents=True, exist_ok=True)
    k, n = args.shard
    name = "heartbeat.json" if n == 1 else f"heartbeat.{k}of{n}.json"
    write_json(folder / name, {"worker_id": args.worker_id, "last_seen": now(),
                               "current_case": current_case, "pid": os.getpid(),
                               "shard": f"{k}/{n}"})


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
    ap.add_argument("--work-root", default=str(Path(tempfile.gettempdir()) / "su2work"),
                    help="local directory SU2 runs in (one subfolder per case); outputs are copied "
                         "to the run folder once at the end. Empty: run in the run folder itself")
    ap.add_argument("--shard", type=parse_shard, default="0/1", metavar="K/N",
                    help="serve only the jobs whose case_id hash is K modulo N (default 0/1 = all); "
                         "the only safe way to run N workers on one queue")
    ap.add_argument("--retry-reason", action="append", default=[], metavar="REASON",
                    help="at start-up, make 2-failed jobs with this error.json reason pending again "
                         "(repeatable), e.g. config_mismatch after a worker-side fix")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    queue, stale_s = Path(args.queue), args.stale_minutes * 60
    for sub in ("jobs", "runs", "worker"):
        (queue / sub).mkdir(parents=True, exist_ok=True)
    write_worker_heartbeat(args)
    say(f"worker {args.worker_id} on {queue}, shard {args.shard[0]}/{args.shard[1]}, "
        f"SU2 command: {args.su2_cmd}")
    backfill_digests(queue)
    if args.retry_reason:
        retried = retry_failed(queue, set(args.retry_reason))
        say(f"{len(retried)} failed job(s) made pending again ({', '.join(args.retry_reason)})")
    for job in jobs_in_state(queue, {"crashed"}, stale_s, args.shard):
        say(f"{job['case_id']}: crash victim (1-running, stale heartbeat), will be re-run")
    try:
        while True:
            write_worker_heartbeat(args)
            todo = jobs_in_state(queue, {"new", "crashed"}, stale_s, args.shard)
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

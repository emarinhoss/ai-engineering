"""Run SU2 on a case directory made by worker.make_case and record how it went.

    python -m worker.run_case CASE_DIR --su2-cmd "mpirun -n 2 SU2_CFD" --timeout 2400

With work_dir set, SU2 runs in that local directory (a copy of the case's files) and its outputs are
copied back into CASE_DIR once, after it exits: SU2 rewrites its output files every OUTPUT_WRT_FREQ
iterations, and on a Google Drive mount those in-place rewrites of a large flow.dat overlapped into
a corrupt file (viz case airfoil2d-731806baea, 2026-11-09). One copy at the end is one write.

Writes log.txt, solver_version.txt and result_partial.json (the "run" and "solver" blocks of the
run record in 01_interfaces.md plus a convergence summary). After a run that exited with code 0,
postprocess.metrics.compute adds the "metrics" block and the same record is also written to
result.json; if compute fails the exception text is kept under "metrics_error" and there is no
result.json.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from postprocess.history import summarize
from postprocess.metrics import compute
from worker.make_case import config_sha256

MPI_LAUNCHERS = ("mpirun", "mpiexec")
MISSING_LIBRARY_HINTS = ("shared librar", "cannot open shared object", "no such file",
                         "not found", "unable to find")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_n_cores(tokens):
    """N from "-n N" / "-np N" in an mpirun command, else 1."""
    for flag in ("-n", "-np", "--np"):
        if flag in tokens[:-1]:
            return int(tokens[tokens.index(flag) + 1])
    return 1


def ram_gb():
    """Total RAM in GB from /proc/meminfo, None if unavailable."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 2)
    except (OSError, ValueError):
        pass
    return None


def solver_version(tokens, cwd, log_path=None):
    """First non-empty line of `<SU2_CFD> --help`, or a banner line from the run log, or "unknown".

    Behind an MPI launcher only the last token (the binary) is called; otherwise the whole
    command, so that "python fake_su2.py" works as a stand-in.
    """
    cmd = [tokens[-1]] if Path(tokens[0]).name in MPI_LAUNCHERS else list(tokens)
    try:
        out = subprocess.run(cmd + ["--help"], cwd=cwd, capture_output=True, text=True, timeout=60,
                             check=False)
        for line in (out.stdout + out.stderr).splitlines():
            if line.strip():
                return line.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    if log_path and Path(log_path).exists():          # SU2 prints "SU2 v8.2.0 ..." in its banner
        m = re.search(r"SU2 v\d\S*.*", Path(log_path).read_text(errors="replace"))
        if m:
            return m.group(0).strip(" |")
    return "unknown"


def _count_rows(path):
    with open(path) as f:
        return max(0, sum(1 for line in f if line.strip()) - 1)


def _execute(tokens, case_dir, log_path, timeout_s):
    """Run the command, stdout and stderr to log_path. Returns (exit_code, timed_out)."""
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(tokens + ["case.cfg"], cwd=case_dir, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as err:
            log.write(f"failed to start {tokens[0]}: {err}\n".encode())
            return 127, False
        try:
            return proc.wait(timeout=timeout_s), False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)       # the whole group: mpirun and its ranks
            proc.wait()
            return None, True


def _stage_local(case_dir, work_dir):
    """Fresh work_dir holding a copy of every file (not directory) in case_dir; returns the names."""
    work_dir = Path(work_dir)
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True)
    names = set()
    for f in Path(case_dir).iterdir():
        if f.is_file():
            shutil.copy2(f, work_dir / f.name)
            names.add(f.name)
    return names


def _copy_back(work_dir, case_dir, inputs):
    """Copy every file SU2 wrote or changed in work_dir into case_dir (one write each), then
    remove work_dir. A file is copied when it is new or differs in size or mtime from its input."""
    work_dir, case_dir = Path(work_dir), Path(case_dir)
    for f in sorted(work_dir.iterdir()):
        if not f.is_file():
            continue
        dest = case_dir / f.name
        if f.name in inputs and dest.exists():
            a, b = f.stat(), dest.stat()
            if a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime):
                continue                              # an input SU2 did not touch
        tmp = dest.with_name(dest.name + ".part")
        shutil.copyfile(f, tmp)
        os.replace(tmp, dest)
    shutil.rmtree(work_dir, ignore_errors=True)


def run(case_dir, su2_cmd="SU2_CFD", timeout_s=2400, log_name="log.txt", work_dir=None):
    """Run `<su2_cmd> case.cfg` in case_dir (or in a local copy at work_dir, outputs copied back
    once at the end); return and save the run/solver/history blocks."""
    case_dir = Path(case_dir)
    tokens = shlex.split(su2_cmd)
    log_path = case_dir / log_name
    history = case_dir / "history.csv"
    for stale in ("history.csv", "surface_flow.dat", "flow.dat", "restart_flow.dat",
                  "restart_flow.csv", "result_partial.json", "result.json"):
        (case_dir / stale).unlink(missing_ok=True)    # never mistake an old run for this one

    version = solver_version(tokens, case_dir)
    started_at, t0 = _now(), time.monotonic()
    if work_dir is None:
        exit_code, timed_out = _execute(tokens, case_dir, log_path, timeout_s)
    else:
        inputs = _stage_local(case_dir, work_dir)
        try:
            exit_code, timed_out = _execute(tokens, Path(work_dir), Path(work_dir) / log_name,
                                            timeout_s)
        finally:
            _copy_back(work_dir, case_dir, inputs)
    wall = time.monotonic() - t0
    finished_at = _now()
    if version == "unknown":
        version = solver_version(tokens, case_dir, log_path)
    (case_dir / "solver_version.txt").write_text(version + "\n")

    result = {
        "run": {"started_at": started_at, "finished_at": finished_at, "wall_time_s": wall,
                "iterations": _count_rows(history) if history.exists() else 0,
                "exit_code": exit_code, "timeout": timed_out,
                "runtime": {"nproc": os.cpu_count(), "ram_gb": ram_gb()}},
        "solver": {"name": "SU2_CFD", "version": version, "command": f"{su2_cmd} case.cfg",
                   "n_cores": parse_n_cores(tokens), "config_sha256": config_sha256(case_dir / "case.cfg")},
    }
    job = case_dir / "job.json"
    if job.exists():
        result["case_id"] = json.loads(job.read_text())["case_id"]
    if history.exists():
        params_file = case_dir / "params.json"
        params = json.loads(params_file.read_text()) if params_file.exists() else None
        try:
            summary = summarize(history, params)
        except (ValueError, KeyError) as err:         # empty or odd history file
            summary = {"status": "error", "error": str(err)}
        if timed_out:
            summary["status"] = "timeout"             # the worker decides timeout and error
        elif exit_code != 0 and summary["status"] != "diverged":
            summary["status"] = "error"
        result["history_summary"] = summary
    if exit_code == 0 and not timed_out:
        try:
            result["metrics"] = compute(case_dir)
        except Exception as err:  # noqa: BLE001  (any failure must not lose the run record)
            result["metrics_error"] = f"{type(err).__name__}: {err}"
    _save(case_dir, result)
    return result


def _save(case_dir, result):
    """result_partial.json always; result.json too once the metrics block exists."""
    text = json.dumps(result, indent=1) + "\n"
    (Path(case_dir) / "result_partial.json").write_text(text)
    if "metrics" in result:
        (Path(case_dir) / "result.json").write_text(text)


def run_first_working(case_dir, su2_cmds, timeout_s=2400, fast_fail_s=20):
    """Try the commands in order. A command that exits non-zero within fast_fail_s seconds and
    whose log mentions a missing library or file counts as "did not start"; the next one is
    tried and the skipped commands are listed in solver["fallback_from"]."""
    skipped = []
    for i, cmd in enumerate(su2_cmds):
        result = run(case_dir, cmd, timeout_s)
        log = (Path(case_dir) / "log.txt").read_text(errors="replace").lower()
        failed_to_start = (result["run"]["exit_code"] not in (0, None)
                           and result["run"]["wall_time_s"] < fast_fail_s
                           and any(h in log for h in MISSING_LIBRARY_HINTS))
        if not failed_to_start or i == len(su2_cmds) - 1:
            break
        skipped.append(cmd)
    if skipped:
        result["solver"]["fallback_from"] = skipped
        _save(case_dir, result)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("case_dir")
    ap.add_argument("--su2-cmd", default="SU2_CFD")
    ap.add_argument("--timeout", type=float, default=2400)
    args = ap.parse_args(argv)
    print(json.dumps(run(args.case_dir, args.su2_cmd, args.timeout), indent=1))


if __name__ == "__main__":
    sys.exit(main())

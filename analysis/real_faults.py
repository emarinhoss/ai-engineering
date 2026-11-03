"""Task 6b: fault injection through the real SU2 binary (spec: docs/specs/task6b_real_su2_faults.md).

    python -m analysis.real_faults --su2-cmd /path/to/SU2_CFD --work SCRATCH [--only R0 R1 ...]
    python -m analysis.real_faults --matrix          # rebuild docs/faults/real_fault_matrix.md

Each fault runs the real worker (worker.run_worker) on a local queue folder, the way the Colab worker
sees the Drive folder, except R6 and R7, which bypass a gate on purpose and call worker.run_case.run.
Each writes runs/faults/2026-11-03/<id>/ (the run folder's small files, gzipped logs and
observed.json). The matrix is generated from the observed.json files, not typed.
"""
import argparse
import gzip
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import cases.config
from cases.check_keys import DEFAULT_TEMPLATE, unknown_keys
from worker.make_case import make
from worker.run_case import run
from worker.run_worker import main as worker_main

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "runs" / "faults" / "2026-11-03"
MATRIX = REPO / "docs" / "faults" / "real_fault_matrix.md"
PARAMS = {"family": "wedge", "theta1_deg": 10.0, "solver": "NAVIER_STOKES", "mesh_level": "coarse",
          "max_iter": 3000, "tag": "fault"}
KEEP = ("log.txt", "history.csv", "error.json", "result.json", "result_partial.json", "heartbeat.json",
        "job.json", "case.cfg", "solver_version.txt")


# ---------------------------------------------------------------- small helpers
def stage(queue, params=PARAMS):
    """Build the case in a scratch folder and put its job file in <queue>/jobs/, as create_case does."""
    job = make(params, Path(queue).parent / "staging" / Path(queue).name)
    (Path(queue) / "jobs").mkdir(parents=True, exist_ok=True)
    (Path(queue) / "jobs" / f"{job['case_id']}.json").write_text(json.dumps(job, indent=1))
    return job


def worker_args(queue, su2_cmd, *extra):
    return ["--queue", str(queue), "--su2-cmd", su2_cmd, "--poll", "1", "--heartbeat", "2",
            "--worker-id", "fault-harness", *extra]


def start_worker(queue, su2_cmd, *extra):
    """The worker as a subprocess in its own session, so it can be killed like a dying runtime."""
    return subprocess.Popen([sys.executable, "-m", "worker.run_worker", *worker_args(queue, su2_cmd, *extra)],
                            cwd=REPO, start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def solvers_in(folder):
    """PIDs of processes whose working directory is `folder` (SU2 runs with cwd = the run folder)."""
    pids = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if Path(os.readlink(proc / "cwd")) == Path(folder).resolve():
                pids.append(int(proc.name))
        except OSError:
            pass
    return pids


def history_rows(run_dir):
    path = Path(run_dir) / "history.csv"
    try:
        return max(0, sum(1 for line in open(path) if line.strip()) - 1)
    except OSError:
        return 0


def wait_until(predicate, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        if predicate():
            return
        time.sleep(0.2)
    raise RuntimeError(f"timed out after {seconds} s waiting for {what}")


def flags(run_dir):
    status = Path(run_dir) / "status"
    return sorted(p.name for p in status.iterdir()) if status.exists() else []


def keep(run_dir, fault, observed):
    """Copy the small files of run_dir to runs/faults/<date>/<fault>/ (logs gzipped); write observed.json."""
    dest = OUT / fault
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in KEEP:
        src = Path(run_dir) / name
        if not src.exists():
            continue
        if name in ("log.txt", "history.csv"):
            with open(src, "rb") as f, gzip.open(dest / f"{name}.gz", "wb") as g:
                shutil.copyfileobj(f, g)
        else:
            shutil.copy(src, dest / name)
    observed = {"fault": fault, "flags": flags(run_dir), **observed}
    (dest / "observed.json").write_text(json.dumps(observed, indent=1) + "\n")
    return observed


def error_of(run_dir):
    path = Path(run_dir) / "error.json"
    return json.loads(path.read_text()) if path.exists() else None


def metrics_of(run_dir):
    path = Path(run_dir) / "result.json"
    return json.loads(path.read_text()).get("metrics") if path.exists() else None


def log_tail(run_dir, n=6):
    path = Path(run_dir) / "log.txt"
    if not path.exists():
        return None
    lines = [line for line in path.read_text(errors="replace").splitlines() if line.strip()]
    return lines[-n:]


# ---------------------------------------------------------------- the faults
def r0(work, su2_cmd):
    queue = work / "R0" / "queue"
    job = stage(queue)
    t0 = time.monotonic()
    code = worker_main(worker_args(queue, su2_cmd, "--once"))
    run_dir = queue / "runs" / job["case_id"]
    return keep(run_dir, "R0", {
        "injected": "none: the clean control case (wedge, coarse mesh, laminar)",
        "case_id": job["case_id"], "worker_exit": code, "wall_s": round(time.monotonic() - t0, 1),
        "iterations": history_rows(run_dir), "metrics": metrics_of(run_dir), "error": error_of(run_dir)})


def r1(work, su2_cmd):
    """A bad template edit that both staging and the worker see: the hashes agree, the job is accepted."""
    queue = work / "R1" / "queue"
    bad = work / "R1" / "templates"
    shutil.copytree(cases.config.TEMPLATES, bad, dirs_exist_ok=True)
    cfg = bad / "navier_stokes.cfg"
    text = cfg.read_text().replace("CFL_NUMBER= 1.0", "CFL_NUMBER= 10000.0").replace("CFL_ADAPT= YES", "CFL_ADAPT= NO")
    cfg.write_text(text)
    saved, cases.config.TEMPLATES = cases.config.TEMPLATES, bad
    try:
        job = stage(queue)
        code = worker_main(worker_args(queue, su2_cmd, "--once"))
    finally:
        cases.config.TEMPLATES = saved
    run_dir = queue / "runs" / job["case_id"]
    return keep(run_dir, "R1", {
        "injected": "template edit seen by staging and worker: CFL_NUMBER 1e4, CFL_ADAPT NO",
        "case_id": job["case_id"], "worker_exit": code, "iterations": history_rows(run_dir),
        "error": error_of(run_dir), "log_tail": log_tail(run_dir)})


def r2(work, su2_cmd, rows=50):
    """SIGKILL to the solver only, as an out-of-memory kill would do."""
    queue = work / "R2" / "queue"
    job = stage(queue)
    run_dir = queue / "runs" / job["case_id"]
    proc = start_worker(queue, su2_cmd, "--once")
    wait_until(lambda: history_rows(run_dir) >= rows, 600, f"{rows} history rows")
    killed = solvers_in(run_dir)
    for pid in killed:
        os.kill(pid, signal.SIGKILL)
    out, _ = proc.communicate(timeout=300)
    return keep(run_dir, "R2", {
        "injected": f"SIGKILL to the SU2 process only after {rows} history rows",
        "case_id": job["case_id"], "solver_pids_killed": len(killed), "worker_exit": proc.returncode,
        "iterations": history_rows(run_dir), "error": error_of(run_dir), "worker_output": out.splitlines()[-4:]})


def r3(work, su2_cmd):
    queue = work / "R3" / "queue"
    job = stage(queue)
    run_dir = queue / "runs" / job["case_id"]
    code = worker_main(worker_args(queue, su2_cmd, "--once", "--timeout", "10"))
    time.sleep(1)
    return keep(run_dir, "R3", {
        "injected": "worker timeout 10 s on a run that needs longer",
        "case_id": job["case_id"], "worker_exit": code, "iterations": history_rows(run_dir),
        "solver_processes_left": len(solvers_in(run_dir)), "error": error_of(run_dir)})


def r4(work, su2_cmd, reference, rows=50):
    """Runtime restart: the worker and the solver both die; the restarted worker re-runs the job."""
    queue = work / "R4" / "queue"
    job = stage(queue)
    run_dir = queue / "runs" / job["case_id"]
    proc = start_worker(queue, su2_cmd, "--once")
    wait_until(lambda: history_rows(run_dir) >= rows, 600, f"{rows} history rows")
    os.killpg(proc.pid, signal.SIGKILL)
    for pid in solvers_in(run_dir):
        os.kill(pid, signal.SIGKILL)
    proc.wait()
    flags_after_kill = flags(run_dir)
    code = worker_main(worker_args(queue, su2_cmd, "--once", "--stale-minutes", "0"))
    m = metrics_of(run_dir)
    same = m is not None and reference is not None and all(m.get(k) == v for k, v in reference.items())
    return keep(run_dir, "R4", {
        "injected": f"worker and SU2 both killed after {rows} history rows; worker restarted with --stale-minutes 0",
        "case_id": job["case_id"], "flags_after_kill": flags_after_kill, "worker_exit": code,
        "iterations": history_rows(run_dir), "metrics_equal_R0": same, "error": error_of(run_dir)})


def r5(work, su2_cmd, reference, rows=50, label="R5"):
    """The worker dies alone; its SU2 keeps running; a new worker starts on the same job.
    R5g is the same fault after the leftover-solver guard was added to the worker."""
    queue = work / label / "queue"
    job = stage(queue)
    run_dir = queue / "runs" / job["case_id"]
    first = start_worker(queue, su2_cmd, "--once")
    wait_until(lambda: history_rows(run_dir) >= rows, 600, f"{rows} history rows")
    orphans = solvers_in(run_dir)
    os.kill(first.pid, signal.SIGKILL)                   # the worker only; SU2 is in its own session
    first.wait()
    second = start_worker(queue, su2_cmd, "--once", "--stale-minutes", "0")
    most, samples = 0, 0
    while second.poll() is None or any(Path(f"/proc/{p}").exists() for p in orphans):
        most = max(most, len(solvers_in(run_dir)))
        samples += 1
        time.sleep(0.5)
    out, _ = second.communicate()
    m = metrics_of(run_dir)
    same = m is not None and reference is not None and all(m.get(k) == v for k, v in reference.items())
    return keep(run_dir, label, {
        "injected": f"worker killed alone after {rows} history rows (SU2 left running); new worker with --stale-minutes 0",
        "case_id": job["case_id"], "orphan_solvers": len(orphans), "max_solvers_in_folder_at_once": most,
        "samples": samples, "worker_exit": second.returncode, "iterations": history_rows(run_dir),
        "metrics_equal_R0": same, "error": error_of(run_dir), "worker_output": out.splitlines()[-4:]})


def r6(work, su2_cmd):
    """Gate F4 bypassed: an unknown key reaches SU2."""
    case = work / "R6" / "case"
    make(PARAMS, case)
    cfg = case / "case.cfg"
    cfg.write_text(cfg.read_text() + "BOGUS_SU2_KEY= 1\n")
    gate_says = unknown_keys(cfg.read_text(), DEFAULT_TEMPLATE.read_text())
    result = run(case, su2_cmd, timeout_s=300)
    return keep(case, "R6", {
        "injected": "BOGUS_SU2_KEY= 1 appended to case.cfg after staging; run_case.run called directly",
        "gate_F4_would_say": gate_says, "exit_code": result["run"]["exit_code"],
        "wall_s": round(result["run"]["wall_time_s"], 2), "iterations": result["run"]["iterations"],
        "metrics": "metrics" in result, "log_tail": log_tail(case)})


def r7(work, su2_cmd):
    """Gate F3 bypassed: one quad of the mesh with its node order reversed (negative area)."""
    case = work / "R7" / "case"
    make(PARAMS, case)
    mesh = case / "mesh.su2"
    lines = mesh.read_text().splitlines()
    i = next(k for k, line in enumerate(lines) if line.startswith("NELEM")) + 1
    kind, a, b, c, d, eid = lines[i].split()
    lines[i] = " ".join([kind, a, d, c, b, eid])         # 9 = quad: a b c d -> a d c b flips orientation
    mesh.write_text("\n".join(lines) + "\n")
    result = run(case, su2_cmd, timeout_s=900)
    m = result.get("metrics", {})
    return keep(case, "R7", {
        "injected": f"element 0 node order reversed in mesh.su2 ({kind} {a} {b} {c} {d} -> {a} {d} {c} {b})",
        "exit_code": result["run"]["exit_code"], "iterations": result["run"]["iterations"],
        "convergence": result.get("history_summary", {}).get("status"),
        "heat_load_body_W_per_m": m.get("heat_load_body_W_per_m"),
        "su2_mesh_messages": [line.strip() for line in (case / "log.txt").read_text(errors="replace").splitlines()
                              if "orientation" in line][:4],
        "metrics_error": result.get("metrics_error"), "log_tail": log_tail(case)})


def r7b(work, su2_cmd):
    """Added after R7 (SU2 re-oriented the reversed element): a tangled cell that re-ordering cannot fix.
    One interior node is moved across the opposite corner of one of its cells."""
    case = work / "R7b" / "case"
    make(PARAMS, case)
    mesh = case / "mesh.su2"
    lines = mesh.read_text().splitlines()
    e0 = next(k for k, line in enumerate(lines) if line.startswith("NELEM"))
    p0 = next(k for k, line in enumerate(lines) if line.startswith("NPOIN"))
    n_elem = int(lines[e0].split("=")[1])
    _, a, b, c, d, _ = lines[e0 + 1 + n_elem // 2].split()        # a cell in the middle of the list
    xa, ya = map(float, lines[p0 + 1 + int(a)].split()[:2])
    xc, yc = map(float, lines[p0 + 1 + int(c)].split()[:2])
    moved = (xa + 2 * (xc - xa), ya + 2 * (yc - ya))             # node a jumps past the opposite corner c
    rest = lines[p0 + 1 + int(a)].split()[2:]
    lines[p0 + 1 + int(a)] = " ".join([repr(moved[0]), repr(moved[1]), *rest])
    mesh.write_text("\n".join(lines) + "\n")
    result = run(case, su2_cmd, timeout_s=900)
    log = (case / "log.txt").read_text(errors="replace").splitlines()
    m = result.get("metrics", {})
    return keep(case, "R7b", {
        "injected": f"node {a} moved from ({xa:.5f}, {ya:.5f}) to ({moved[0]:.5f}, {moved[1]:.5f}) m, past the opposite corner {c} of its cell",
        "exit_code": result["run"]["exit_code"], "iterations": result["run"]["iterations"],
        "convergence": result.get("history_summary", {}).get("status"),
        "heat_load_body_W_per_m": m.get("heat_load_body_W_per_m"), "metrics_error": result.get("metrics_error"),
        "su2_mesh_messages": [line.strip() for line in log if "orientation" in line or "Minimum" in line or "egative" in line][:6],
        "log_tail": log_tail(case)})


INLET_12_14 = {"family": "inlet2r", "theta1_deg": 12.0, "theta2_deg": 14.0, "mach": 4.0, "T_wall_K": 300.0,
               "solver": "NAVIER_STOKES", "mesh_level": "medium", "save_volume": False, "tag": "task2-dev",
               "max_iter": 8000}                                 # params of runs/dev/.../12_14_medium


def r9(work, su2_cmd, label="R9"):
    """Added after R1 (CFL 1e4 converged): a job file made without create_case, so the physics gates
    never ran, for the 12/14 inlet that diverged in runs/dev. The worker regenerates mesh and config
    and compares hashes; the question is whether anything stops it before SU2."""
    queue = work / label / "queue"
    job = stage(queue, INLET_12_14)
    record = REPO / "runs/dev/2026-11-01_inlet_grid_study_ef03/12_14_medium/case.cfg"
    from worker.make_case import config_sha256
    same_cfg = config_sha256(record) == job["config_sha256"]
    t0 = time.monotonic()
    code = worker_main(worker_args(queue, su2_cmd, "--once"))
    run_dir = queue / "runs" / job["case_id"]
    return keep(run_dir, label, {
        "injected": "job file for theta1 = 12, theta2 = 14 (gate 4 limit 24 deg) written with worker.make_case.make, not create_case",
        "case_id": job["case_id"], "config_equals_runs_dev_record": same_cfg, "worker_exit": code,
        "wall_s": round(time.monotonic() - t0, 1), "solver_started": (run_dir / "log.txt").exists(),
        "iterations": history_rows(run_dir), "error": error_of(run_dir), "log_tail": log_tail(run_dir)})


def r8(work, su2_cmd):
    queue = work / "R8" / "queue"
    job = stage(queue)
    path = queue / "jobs" / f"{job['case_id']}.json"
    edited = {**job, "mesh_fingerprint": "0" * 64}
    path.write_text(json.dumps(edited, indent=1))
    code = worker_main(worker_args(queue, su2_cmd, "--once"))
    run_dir = queue / "runs" / job["case_id"]
    return keep(run_dir, "R8", {
        "injected": "job file with mesh_fingerprint edited to 64 zeros",
        "case_id": job["case_id"], "worker_exit": code, "solver_started": (run_dir / "log.txt").exists(),
        "error": error_of(run_dir)})


# ---------------------------------------------------------------- the matrix
def caught_by(o):
    err = o.get("error") or {}
    if err:
        return f"worker: 2-failed, reason {err['reason']}"
    if o["fault"] in ("R6", "R7", "R7b"):
        return "nothing after the gate (bypassed on purpose)"
    return "no failure record: the worker flagged 2-done" if "2-done" in o.get("flags", []) else "nothing"


def write_matrix():
    rows = []
    for path in sorted(OUT.glob("R*/observed.json")):
        o = json.loads(path.read_text())
        hidden = ("fault", "injected", "case_id", "flags", "error", "log_tail", "worker_output", "samples", "metrics")
        shown = {k: v for k, v in o.items() if k not in hidden}
        if isinstance(o.get("metrics"), dict):
            shown["heat_load_body_W_per_m"] = o["metrics"].get("heat_load_body_W_per_m")
        err = o.get("error")
        detail = err.get("detail") if err else None
        if isinstance(detail, dict) and "log_tail" in detail:
            detail = {"exit_code": detail.get("exit_code"), "log_tail": [x for x in detail["log_tail"] if x.strip()][-2:]}
        sees = json.dumps(detail)[:200] if detail else ""
        rows.append(f"| {o['fault']} | {o['injected']} | {caught_by(o)} | {sees} | "
                    f"flags {', '.join(o.get('flags', [])) or '-'}; " + "; ".join(f"{k} = {json.dumps(v)[:120]}" for k, v in shown.items()) + " |")
    MATRIX.write_text(
        "<!-- Generated by python -m analysis.real_faults --matrix from runs/faults/2026-11-03/*/observed.json; do not edit by hand. -->\n"
        "# Fault matrix with the real SU2 v8.2.0 binary\n\n"
        "Spec: `docs/specs/task6b_real_su2_faults.md`. Every row comes from the run folder under "
        "`runs/faults/2026-11-03/<fault>/`. R6, R7 and R7b bypass a gate on purpose to show what SU2 does without it. "
        "R5g and R9g repeat R5 and R9 after the guards of 2026-11-03 were added to the worker. Full detail, including "
        "log tails and worker messages, is in each `observed.json`.\n\n"
        "| Fault | Injected how | Caught by | User sees (error.json detail) | Observed |\n|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n")
    return MATRIX


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--su2-cmd")
    ap.add_argument("--work", help="scratch folder for queues and cases")
    ap.add_argument("--only", nargs="*", default=["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"])
    ap.add_argument("--matrix", action="store_true")
    a = ap.parse_args()
    if a.su2_cmd:
        work = Path(a.work)
        reference = None
        r0_file = OUT / "R0" / "observed.json"
        for fault in a.only:
            shutil.rmtree(work / fault, ignore_errors=True)
            if r0_file.exists():
                m = json.loads(r0_file.read_text())["metrics"] or {}
                reference = {k: m[k] for k in m if isinstance(m[k], (int, float))}
            fn = globals().get(fault.lower())
            if fault in ("R5g", "R9g"):
                out = globals()[fault[:-1].lower()](work, a.su2_cmd, *((reference,) if fault == "R5g" else ()), label=fault)
            else:
                args = (work, a.su2_cmd, reference) if fault in ("R4", "R5") else (work, a.su2_cmd)
                out = fn(*args)
            print(fault, json.dumps(out)[:400], flush=True)
    print(write_matrix())


if __name__ == "__main__":
    main()

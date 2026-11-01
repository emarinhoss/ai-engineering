"""Local staging queue: build, check and stage SU2 jobs. This module never runs SU2.

Layout under $SU2_QUEUE_DIR (default ./su2queue_local):
  jobs/<case_id>/   the job directory of 01_interfaces.md plus status/ flag files
  mcp_log.jsonl     audit log, one JSON line per tool call
Status flags are empty files named "<n>-<name>" written atomically; 0-created, 1-pending here.
The highest number is the current status. Claude uploads job.json to Drive by hand (the
connector), the Colab worker does the rest.

Pipeline for validate / create, stopping at the first failing stage:
schema -> gates -> geometry -> mesh_quality -> config -> config_keys.
"""
import csv
import functools
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cases.check_keys import DEFAULT_TEMPLATE, unknown_keys
from cases.config import render
from geometry import cylinder, inlet, wedge
from mcp_server.schemas import to_params, validate
from physics import gates
from worker.make_case import case_id, git_commit, quality_failures, sha256_file

MODULES = {"inlet2r": inlet, "wedge": wedge, "cylinder": cylinder}
CASE_ID_RE = re.compile(r"^(inlet2r|wedge|cylinder)-[0-9a-f]{10}$")


def queue_dir():
    return Path(os.environ.get("SU2_QUEUE_DIR", "./su2queue_local"))


# ---------------------------------------------------------------- audit log

def _log(tool, args, ok, cid=None, **extra):
    """Append one line {time, tool, args_sha256, ok, case_id?} to mcp_log.jsonl."""
    digest = hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()
    line = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": tool,
            "args_sha256": digest, "ok": ok, **({"case_id": cid} if cid else {}), **extra}
    queue_dir().mkdir(parents=True, exist_ok=True)
    with open(queue_dir() / "mcp_log.jsonl", "a") as f:
        f.write(json.dumps(line) + "\n")


def audited(fn):
    """Log every call of a public function (also when it raises)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        argd = {"args": args, "kwargs": kwargs}
        try:
            out = fn(*args, **kwargs)
        except Exception:
            _log(fn.__name__, argd, False)
            raise
        d = out if isinstance(out, dict) else {}
        cid = d.get("case_id") or (args[0] if args and isinstance(args[0], str) else None)
        _log(fn.__name__, argd, d.get("ok", True), cid if cid and CASE_ID_RE.match(cid) else None)
        return out
    return wrapper


# ---------------------------------------------------------------- building a case

class StageError(Exception):
    def __init__(self, stage, errors):
        super().__init__(stage)
        self.stage, self.errors = stage, errors


def _dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def _requested_first_cell(params):
    """{wall marker: first-cell height (m) the mesh was asked for}, per family."""
    level, fam = params["mesh_level"], params["family"]
    if fam == "wedge":
        return {"body": wedge.sizes(level)["d0"]}
    if fam == "inlet2r":
        d0 = inlet.sizes(level)["d0"]
        return {"body": d0, "cowl": d0}
    return {"wall": cylinder.LEVELS[level][0]}


def build_case(params, staging_dir):
    """Write the job directory for complete `params` into `staging_dir`; return the job dict.

    TEMPORARY SHIM: same files as worker.make_case.make, which only knows the wedge.
    TODO: fold into worker.make_case in the worker half of Task 3 and delete this function.
    Raises StageError("geometry" | "mesh_quality" | "config") and writes nothing on the first two.
    """
    try:
        geometry, mesh = MODULES[params["family"]].build(params)
    except (ValueError, NotImplementedError) as exc:
        raise StageError("geometry", [str(exc)]) from exc
    quality, wanted = mesh.quality(), _requested_first_cell(params)
    failures = quality_failures(quality, wanted)
    if failures:
        raise StageError("mesh_quality", failures)

    out = Path(staging_dir)
    out.mkdir(parents=True, exist_ok=True)
    mesh.write_su2(out / "mesh.su2")
    mesh.write_markers(out / "mesh_markers.json")
    _dump(out / "geometry.json", geometry)
    _dump(out / "mesh_quality.json", {**quality, "pass": True, "failures": [],
                                      "requested_first_cell_m": wanted})
    _dump(out / "params.json", params)
    try:
        text = render(params, geometry, json.loads((out / "mesh_markers.json").read_text()))
    except ValueError as exc:
        raise StageError("config", [str(exc)]) from exc
    (out / "case.cfg").write_text(text)
    job = {"case_id": case_id(params), "params": params,
           "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "mesh_sha256": sha256_file(out / "mesh.su2"), "config_sha256": sha256_file(out / "case.cfg"),
           "code_commit": git_commit(), "timeout_s": 2400, "max_cores": 2}
    _dump(out / "job.json", job)
    return job


def _fail(stage, errors, warnings=()):
    return {"ok": False, "stage": stage, "errors": list(errors), "warnings": list(warnings)}


def _pipeline(raw, out_dir):
    """All stages, building into out_dir. Returns a result dict; on success it holds the job."""
    model, errors, warnings = validate(raw)
    if errors:
        return _fail("schema", errors)
    params = to_params(model)
    errors = gates.check(params)
    if errors:
        return _fail("gates", errors, warnings)
    try:
        job = build_case(params, out_dir)
    except StageError as exc:
        return _fail(exc.stage, exc.errors, warnings)
    bad = unknown_keys((Path(out_dir) / "case.cfg").read_text(), DEFAULT_TEMPLATE.read_text())
    if bad:
        return _fail("config_keys", [f"key not in the SU2 config template: {k}" for k in bad], warnings)
    return {"ok": True, "stage": "done", "errors": [], "warnings": warnings,
            "case_id": job["case_id"], "job": job}


def _read(path):
    return json.loads(Path(path).read_text())


@audited
def validate_only(params):
    """Run the whole pipeline in a temporary directory; nothing is staged."""
    with tempfile.TemporaryDirectory() as tmp:
        res = _pipeline(params, Path(tmp) / "case")
        if res["ok"]:
            res.pop("job")
            res["geometry"] = _read(Path(tmp) / "case" / "geometry.json")
            res["mesh_quality"] = _read(Path(tmp) / "case" / "mesh_quality.json")
    return res


# ---------------------------------------------------------------- status flags

def _job_dir(cid):
    if not isinstance(cid, str) or not CASE_ID_RE.match(cid):
        raise ValueError(f"bad case_id {cid!r}")
    return queue_dir() / "jobs" / cid


def _flags(case_dir):
    d = case_dir / "status"
    return sorted(p.name for p in d.iterdir() if not p.name.startswith(".")) if d.is_dir() else []


def _status_of(case_dir):
    flags = _flags(case_dir)
    return flags[-1].split("-", 1)[1] if flags else "unknown"


def _set_flag(case_dir, name):
    """Atomic: write a temporary file, then rename it."""
    d = case_dir / "status"
    d.mkdir(exist_ok=True)
    tmp = d / f".tmp-{os.getpid()}-{name}"
    tmp.write_text(datetime.now(timezone.utc).isoformat() + "\n")
    os.replace(tmp, d / name)


# ---------------------------------------------------------------- public functions

@audited
def create(params, force=False):
    """Pipeline, then stage jobs/<case_id>/ with status 0-created. Nothing is written on failure."""
    tmp_root = queue_dir() / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp:
        built = Path(tmp) / "case"
        res = _pipeline(params, built)
        if not res["ok"]:
            return res
        cid = res["case_id"]
        dest = queue_dir() / "jobs" / cid
        if dest.exists():
            now = _status_of(dest)
            if not force or now not in ("created", "failed"):
                msg = (f"{cid} already exists with status {now}; "
                       "force=true replaces it only if created or failed")
                return {**_fail("exists", [msg], res["warnings"]), "case_id": cid}
            shutil.rmtree(dest)
        _set_flag(built, "0-created")
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(built, dest)
    return {"ok": True, "case_id": cid, "path": str(dest), "job_json": str(dest / "job.json"),
            "mesh_quality": _read(dest / "mesh_quality.json"), "warnings": res["warnings"]}


@audited
def submit(case_id, force=False):
    """0-created -> 1-pending. Submitting a pending job again needs force=True."""
    try:
        d = _job_dir(case_id)
    except ValueError as exc:
        return _fail("case_id", [str(exc)])
    if not d.is_dir():
        return {**_fail("unknown_case", [f"no staged job {case_id}"]), "case_id": case_id}
    now = _status_of(d)
    if now != "created" and not (force and now == "pending"):
        return {**_fail("status", [f"status is {now}; only a created job can be submitted"]),
                "case_id": case_id}
    _set_flag(d, "1-pending")
    return {"ok": True, "case_id": case_id, "status": "pending", "job_json": str(d / "job.json")}


def _rows(case_id=None):
    """Status rows (oldest first) for one case or all staged jobs."""
    root = queue_dir() / "jobs"
    if case_id is not None:
        try:
            ids = [_job_dir(case_id).name]
        except ValueError:
            return [{"case_id": case_id, "status": "unknown"}]
    elif root.is_dir():
        def created(c):
            flag = root / c / "status" / "0-created"
            return (flag.stat().st_mtime_ns if flag.exists() else 0, c)
        ids = sorted((p.name for p in root.iterdir() if p.is_dir()), key=created)
    else:
        ids = []
    rows = []
    for cid in ids:
        d = root / cid
        params = _read(d / "params.json") if (d / "params.json").exists() else {}
        rows.append({"case_id": cid, "status": _status_of(d) if d.is_dir() else "unknown",
                     "tag": params.get("tag"), "iterations": None, "elapsed_s": None,
                     "last_rms_rho": None})
    return rows


@audited
def status(case_id=None):
    """List of {case_id, status, tag, ...} from flag files, oldest first.

    TODO (worker half): iterations, elapsed_s and last_rms_rho from heartbeat.json and history.csv.
    """
    return _rows(case_id)


@audited
def list_results(tag=None, status=None):
    """One row per staged job; metrics come from result.json when it exists, else null."""
    out = []
    for row in _rows():
        if (tag and row["tag"] != tag) or (status and row["status"] != status):
            continue
        d = queue_dir() / "jobs" / row["case_id"]
        res = _read(d / "result.json") if (d / "result.json").exists() else {}
        params = _read(d / "params.json")
        out.append({"case_id": row["case_id"], "tag": row["tag"], "status": row["status"],
                    "theta1_deg": params.get("theta1_deg"), "theta2_deg": params.get("theta2_deg"),
                    "convergence": res.get("convergence", {}).get("status"),
                    "recovery_total": res.get("metrics", {}).get("recovery_total"),
                    "q_peak_W_m2": res.get("metrics", {}).get("q_peak_W_m2"),
                    "wall_time_s": res.get("run", {}).get("wall_time_s")})
    return out


@audited
def queue_batch(csv_path, tag, mesh_level="medium", family="inlet2r"):
    """create + submit every row (theta1_deg, theta2_deg) of a design CSV, in order.

    Stops at the first failing row. A row whose job already exists is not an error: it is
    submitted if still only created, so an interrupted batch can be run again.
    """
    out = {"ok": True, "case_ids": [], "failed": None}
    try:
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        points = [(float(r["theta1_deg"]), float(r["theta2_deg"])) for r in rows]
    except (OSError, KeyError, ValueError) as exc:
        return {**out, "ok": False, "failed": {"row": None, "stage": "csv", "errors": [repr(exc)]}}
    for i, (t1, t2) in enumerate(points):
        params = {"family": family, "theta1_deg": t1, "mesh_level": mesh_level, "tag": tag}
        if family == "inlet2r":
            params["theta2_deg"] = t2
        res = create(params)
        if not res["ok"] and res["stage"] == "exists":
            res = {"ok": True, "case_id": res["case_id"]}
        if res["ok"] and _status_of(_job_dir(res["case_id"])) == "created":
            res = submit(res["case_id"])
        if not res["ok"]:
            return {**out, "ok": False, "failed": {"row": i, "stage": res["stage"],
                                                   "errors": res["errors"], "theta1_deg": t1,
                                                   "theta2_deg": t2}}
        out["case_ids"].append(res["case_id"])
    return out


def record_transfer(case_id, direction, drive_file_id, sha256):
    """Log a Drive upload/download that Claude did through the connector."""
    errors = []
    if not isinstance(case_id, str) or not CASE_ID_RE.match(case_id):
        errors.append(f"bad case_id {case_id!r}")
    if direction not in ("upload", "download"):
        errors.append("direction must be 'upload' or 'download'")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        errors.append("sha256 must be 64 lowercase hex digits")
    if not isinstance(drive_file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{5,128}", drive_file_id):
        errors.append("drive_file_id must be a Drive file id")
    if errors:
        _log("record_transfer", {"case_id": str(case_id)}, False)
        return _fail("schema", errors)
    _log("record_transfer", {"case_id": case_id, "direction": direction}, True, case_id,
         direction=direction, drive_file_id=drive_file_id, sha256=sha256)
    return {"ok": True, "case_id": case_id, "direction": direction}

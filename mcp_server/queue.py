"""Local staging queue: build, check and stage SU2 jobs. This module never runs SU2.

Layout under $SU2_QUEUE_DIR (default ./su2queue_local):
  jobs/<case_id>/   the job directory of 01_interfaces.md plus status/ flag files
  mcp_log.jsonl     audit log, one JSON line per tool call
Status flags are empty files named "<n>-<name>" written atomically; 0-created, 1-pending here,
then 2-done (result ingested) or 2-failed (error.json ingested).
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
from mcp_server.schemas import to_params, validate
from physics import gates
from postprocess.metrics import compute
from worker.make_case import StageError, config_sha256, git_commit, make, sha256_file

CASE_ID_RE = re.compile(r"^(inlet2r|inlet3r|wedge|cylinder|airfoil2d|drone)-[0-9a-f]{10}$")
TAG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
REPO = Path(__file__).resolve().parent.parent           # runs/<tag>/<case_id>/ is written here
RUN_BLOCKS = ("params", "mesh", "solver", "run", "convergence", "metrics")
NOT_A_RESULT = ("diverged", "timeout", "error")         # these are reported with ingest_error
COMMITTED = ("params.json", "geometry.json", "case.cfg", "result.json", "mesh_quality.json",
             "solver_version.txt")


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

def build_case(params, staging_dir):
    """Write the job directory for complete `params` into `staging_dir`; return the job dict.

    Raises StageError("geometry" | "mesh_quality" | "config"); nothing is written on the first two.
    """
    return make(params, staging_dir)


DONOR_SAME = ("airfoil", "camber_pct", "thickness_pct", "reynolds", "transition")


def donor_errors(params):
    """Why params["restart_from"] is not a usable donor in the local queue (empty list if usable).
    The donor must be a staged airfoil2d job with save_restart true, of the same section, Reynolds
    number and transition setting. Angle of attack and mesh level may differ."""
    donor_id = params.get("restart_from")
    if donor_id is None:
        return []
    path = queue_dir() / "jobs" / donor_id / "params.json"
    if not path.exists():
        return [f"restart_from: donor {donor_id} is not a staged job in the local queue"]
    donor = _read(path)
    errors = []
    if donor.get("family") != "airfoil2d":
        errors.append(f"restart_from: donor {donor_id} is not an airfoil2d job")
    if not donor.get("save_restart"):
        errors.append(f"restart_from: donor {donor_id} was not made with save_restart true")
    for key in DONOR_SAME:
        if donor.get(key) != params.get(key):
            errors.append(f"restart_from: {key} differs from the donor ({params.get(key)!r} against "
                          f"{donor.get(key)!r})")
    return errors


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
    errors = donor_errors(params)
    if errors:
        return _fail("donor", errors, warnings)
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
def queue_batch(csv_path, tag, mesh_level="medium", family="inlet2r", skip_gated=True):
    """create + submit every row (theta1_deg, theta2_deg) of a design CSV, in order.

    With skip_gated, a row that fails at stage "gates" or "schema" is recorded under "skipped" and
    the loop goes on; a failure at a later stage (geometry, mesh_quality, config) stops the batch.
    A row whose job already exists is not an error: it is submitted if still only created, so an
    interrupted batch can be run again. The row's "index" column (if any) is returned in
    "pool_index" (parallel to "case_ids") and written to jobs/<case_id>/pool_index.txt; it is not
    part of the params.
    """
    out = {"ok": True, "case_ids": [], "pool_index": [], "skipped": [], "failed": None}
    try:
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        points = [(float(r["theta1_deg"]), float(r["theta2_deg"])) for r in rows]
    except (OSError, KeyError, ValueError) as exc:
        return {**out, "ok": False, "failed": {"row": None, "stage": "csv", "errors": [repr(exc)]}}
    for i, (t1, t2) in enumerate(points):
        index = rows[i].get("index", str(i))
        params = {"family": family, "theta1_deg": t1, "mesh_level": mesh_level, "tag": tag}
        if family == "inlet2r":
            params["theta2_deg"] = t2
        res = create(params)
        if not res["ok"] and res["stage"] == "exists":
            res = {"ok": True, "case_id": res["case_id"]}
        if res["ok"] and _status_of(_job_dir(res["case_id"])) == "created":
            res = submit(res["case_id"])
        if not res["ok"] and skip_gated and res["stage"] in ("gates", "schema"):
            out["skipped"].append({"row": i, "index": index, "theta1_deg": t1, "theta2_deg": t2,
                                   "stage": res["stage"], "errors": res["errors"]})
            continue
        if not res["ok"]:
            return {**out, "ok": False, "failed": {"row": i, "stage": res["stage"],
                                                   "errors": res["errors"], "theta1_deg": t1,
                                                   "theta2_deg": t2}}
        _write_text(_job_dir(res["case_id"]) / "pool_index.txt", f"{index}\n")
        out["case_ids"].append(res["case_id"])
        out["pool_index"].append(index)
    return out


@audited
def export_batch(case_ids, path=None):
    """Bundle the job.json of staged jobs into one JSON text {batch_id, created_at, code_commit,
    jobs}, jobs in the given order, so one file can be uploaded to Drive instead of many.

    batch_id is the first 10 hex digits of the sha256 of the sorted case ids. With path=None the
    text is also written to $SU2_QUEUE_DIR/batches/<batch_id>.batch.json. Never runs SU2.
    """
    jobs = []
    for cid in case_ids:
        d, bad = _staged(cid)
        if bad:
            raise ValueError(f"cannot export {cid!r}: {bad['errors'][0]}")
        jobs.append(_read(d / "job.json"))
    batch_id = hashlib.sha256(",".join(sorted(case_ids)).encode()).hexdigest()[:10]
    text = json.dumps({"batch_id": batch_id,
                       "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "code_commit": git_commit(), "jobs": jobs}, indent=1, sort_keys=True) + "\n"
    target = Path(path) if path else queue_dir() / "batches" / f"{batch_id}.batch.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_text(target, text)
    return text


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


# ---------------------------------------------------------------- results coming back from Drive

def _write_text(path, text):
    """Atomic: temporary file, then rename."""
    tmp = path.with_name(f".tmp-{os.getpid()}-{path.name}")
    tmp.write_text(text)
    os.replace(tmp, path)


def _set_final(d, name):
    """Flag 2-done or 2-failed and remove the other one (the highest flag is the status)."""
    (d / "status" / ("2-failed" if name == "2-done" else "2-done")).unlink(missing_ok=True)
    _set_flag(d, name)


def _staged(case_id):
    """(job dir, None) if the job was staged here, else (None, failure dict)."""
    try:
        d = _job_dir(case_id)
    except ValueError as exc:
        return None, _fail("case_id", [str(exc)])
    if not (d / "job.json").is_file():
        return None, {**_fail("unknown_case", [f"no staged job {case_id}"]), "case_id": case_id}
    return d, None


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_record(rec, d, case_id):
    """Errors (list of strings) for a result.json against the run record and the staged job."""
    if not isinstance(rec, dict):
        return ["the result must be a JSON object"]
    staged = _read(d / "job.json")
    errors = []
    if rec.get("case_id") != case_id:
        errors.append(f"case_id is {rec.get('case_id')!r}, expected {case_id!r}")
    errors += [f"block {b!r} is missing or not an object" for b in RUN_BLOCKS
               if not isinstance(rec.get(b), dict)]
    echo = rec.get("job")
    if not isinstance(echo, dict):
        errors.append("block 'job' (echo of mesh_fingerprint, config_sha256) is missing")
    else:
        errors += [f"job.{k} is {echo.get(k)!r}, the staged job has {staged[k]!r}"
                   for k in ("mesh_fingerprint", "config_sha256") if echo.get(k) != staged[k]]
    if errors:
        return errors
    if rec["params"] != _read(d / "params.json"):
        errors.append("params differ from the staged params.json")
    # The config SU2 ran must be the staged one: its hash over the lines SU2 reads, or (jobs staged
    # before the comment lines were left out of the hash) over the whole file.
    cfg = d / "case.cfg"
    accepted = {staged["config_sha256"]}
    if cfg.is_file():
        accepted |= {config_sha256(cfg), sha256_file(cfg)}
    if rec["solver"].get("config_sha256") not in accepted:
        errors.append("solver.config_sha256 differs from the staged config_sha256")
    if not isinstance(rec["solver"].get("version"), str):
        errors.append("solver.version must be a string")
    for key in ("wall_time_s", "iterations", "exit_code"):
        if not _is_number(rec["run"].get(key)):
            errors.append(f"run.{key} must be a number")
    status = rec["convergence"].get("status")
    if not isinstance(status, str):
        errors.append("convergence.status must be a string")
    elif status in NOT_A_RESULT:
        errors.append(f"convergence.status is {status!r}: report a failed run with ingest_error")
    return errors


def _commit_to_repo(d, rec=None):
    """Copy the committed subset of a staged job to REPO/runs/<tag>/<case_id>/. `rec` is the
    result record (its solver version is written when the worker's file is not staged); a failed
    job has none and its record is error.json."""
    dest = REPO / "runs" / _read(d / "params.json")["tag"] / d.name
    dest.mkdir(parents=True, exist_ok=True)
    names = COMMITTED if rec is not None else COMMITTED + ("error.json",)
    for name in names:
        if (d / name).is_file():
            shutil.copyfile(d / name, dest / name)
    if rec is not None:
        (dest / "error.json").unlink(missing_ok=True)       # a retried job that now succeeded
        if not (d / "solver_version.txt").is_file():         # the worker's file stays on Drive
            (dest / "solver_version.txt").write_text(rec["solver"]["version"] + "\n")
    return dest


def _digest_mismatch(case_id, text, sha256):
    """A refusal when the text's sha256 differs from the digest the worker wrote next to the file
    (runs/<id>.result.sha256 or runs/<id>.error.sha256); None when it matches or none is given."""
    if not sha256:
        return None
    got = hashlib.sha256(text.encode()).hexdigest()
    if got != sha256.strip().lower():
        why = (f"sha256 of the text is {got[:12]}..., the worker's digest is {sha256.strip()[:12]}...: "
               "the copy is not the file on Drive")
        return {**_fail("digest", [why]), "case_id": case_id}
    return None


@audited
def ingest_result(case_id, result_json_text, sha256=""):
    """Check a downloaded result.json against the staged job, store it, flag 2-done, and copy the
    committed subset to runs/<tag>/<case_id>/. Nothing is stored or flagged if a check fails.
    `sha256` (optional) is the worker's digest of the file (runs/<id>.result.sha256); the text must
    match it, which catches a copy altered on its way through Drive and a transcription."""
    d, bad = _staged(case_id)
    if bad:
        return bad
    bad = _digest_mismatch(case_id, result_json_text, sha256)
    if bad:
        return bad
    try:
        rec = json.loads(result_json_text)
    except (TypeError, ValueError) as exc:
        return {**_fail("json", [f"result is not valid JSON: {exc}"]), "case_id": case_id}
    errors = check_record(rec, d, case_id)
    if not errors and not TAG_RE.match(str(_read(d / "params.json").get("tag"))):
        errors.append("staged params.json has a bad tag")
    if errors:
        return {**_fail("record", errors), "case_id": case_id}
    _write_text(d / "result.json", result_json_text)
    _set_final(d, "2-done")
    dest = _commit_to_repo(d, rec)
    return {"ok": True, "case_id": case_id, "status": "done", "committed_to": str(dest),
            "files": sorted(p.name for p in dest.iterdir())}


@audited
def ingest_error(case_id, error_json_text, sha256=""):
    """Store a downloaded error.json ({reason, detail}) for a staged job, flag it 2-failed and copy
    the record (params, geometry, config, mesh quality, error.json) to runs/<tag>/<case_id>/.
    `sha256` (optional) is the worker's digest of the file (runs/<id>.error.sha256)."""
    d, bad = _staged(case_id)
    if bad:
        return bad
    bad = _digest_mismatch(case_id, error_json_text, sha256)
    if bad:
        return bad
    try:
        err = json.loads(error_json_text)
    except (TypeError, ValueError) as exc:
        return {**_fail("json", [f"error.json is not valid JSON: {exc}"]), "case_id": case_id}
    if not isinstance(err, dict) or not isinstance(err.get("reason"), str) or "detail" not in err:
        return {**_fail("record", ["error.json needs a string 'reason' and a 'detail'"]),
                "case_id": case_id}
    if err.get("case_id", case_id) != case_id:
        return {**_fail("record", [f"case_id is {err['case_id']!r}, expected {case_id!r}"]),
                "case_id": case_id}
    _write_text(d / "error.json", error_json_text)
    _set_final(d, "2-failed")
    dest = _commit_to_repo(d)        # a failure is a run record too: params, config, error.json
    return {"ok": True, "case_id": case_id, "status": "failed", "reason": err["reason"],
            "committed_to": str(dest)}


@audited
def postprocess(case_id, recompute=False):
    """The metrics block of a staged job: from its result.json, or recomputed with
    postprocess.metrics.compute when asked (or when result.json is missing but surface_flow.dat
    is staged). Writes nothing."""
    d, bad = _staged(case_id)
    if bad:
        return bad
    if (d / "result.json").is_file() and not recompute:
        return {"ok": True, "case_id": case_id, "source": "result.json",
                "metrics": _read(d / "result.json")["metrics"]}
    if not (d / "surface_flow.dat").is_file():
        why = "no result.json and no surface_flow.dat" if not recompute else \
            "recompute needs surface_flow.dat in the staged job directory"
        return {**_fail("no_result", [why]), "case_id": case_id}
    try:
        return {"ok": True, "case_id": case_id, "source": "recomputed", "metrics": compute(d)}
    except Exception as exc:  # noqa: BLE001  (compute raises ValueError, KeyError, OSError ...)
        return {**_fail("postprocess", [f"{type(exc).__name__}: {exc}"]), "case_id": case_id}

"""Validation report for run records (00_decisions.md sections 4 and 5).

    python -m postprocess.report --out docs/validation --date 2026-11-01 --cases CASE_DIR [CASE_DIR ...]

Writes <out>/<date>_report.md and one PNG per figure, <out>/<date>_<name>.png.

Pure reporting: every number comes from a check dictionary (postprocess.validation), from
metrics.compute, from history.summarize or from a file of the case. Each case directory is copied
into a temporary directory (gzip files are unpacked there) and the checks run on the copy, so the
case directories are not modified. A check that cannot run (missing file, missing mesh, an error
inside the check) gives a row with the verdict "not run" and its error text.
"""

import argparse
import datetime
import gzip
import hashlib
import json
import math
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from geometry.structured import mesh_fingerprint
from postprocess import history, metrics, surface, validation
from postprocess.tecplot import read_tecplot_ascii
from worker.make_case import make as make_case

# What a check, a metric or a plot raises on bad or missing input; anything else is a bug and is raised.
EXPECTED_ERRORS = (
    ArithmeticError,
    IndexError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)
REPO = Path(__file__).resolve().parents[1]
TASK1_DIR = REPO / "runs" / "task1"  # Colab JSON reports (V1, V2a) written by the Task 1 notebook
MESH_FILES = ("mesh.su2", "mesh_markers.json")
RECORD_COPIES_KEPT = ("geometry.json", "case.cfg", "mesh_quality.json")
LEVELS = ("coarse", "medium", "fine")
DESIGN_THETA = (8.0, 8.0)  # V4 rows are scoped to the 8/8 inlet of the decisions table
CYLINDER_GRID_TOL = {"q_stag_W_m2": 0.05}  # V3 grid study: medium to fine, 5 percent

ID_ORDER = ("V1", "V2a", "V2b", "V3", "V3 grid", "V3 stand-off", "V4e", "V4v", "V4m", "X1")
TOLERANCE = {  # (tolerance, type) as in 00_decisions.md section 5
    "V1": ("beta +-0.5 deg; p2/p1 and M2 2 percent", "hard"),
    "V2a": ("plateau p vs inviscid +0 to +6 percent", "report"),
    "V2b": ("mean 10 percent, max 15 percent", "hard"),
    "V3": ("15 percent (fine mesh)", "hard"),
    "V3 grid": ("5 percent, medium to fine", "hard"),
    "V3 stand-off": ("15 percent vs Billig", "report"),
    "V4e": ("2 percent", "hard"),
    "V4v": ("5 percent (mid 50 percent core)", "soft"),
    "V4m": ("recovery_total 2 percent; q_peak 5 percent, medium to fine", "hard"),
    "X1": ("0.5 percent", "hard"),
}
DEFAULT_QUANTITY = {
    "V1": "beta, p2/p1, M2 (Euler wedge)",
    "V2a": "plateau p vs inviscid (laminar wedge)",
    "V2b": "q_w vs Eckert flat plate (Navier-Stokes wedge)",
    "V3": "q_stag vs Fay-Riddell (cylinder)",
    "V3 grid": "q_stag, medium to fine (cylinder levels)",
    "V3 stand-off": "stand-off / R vs Billig (cylinder)",
    "V4e": "throat area average p0/p0_inf and Mach (Euler inlet)",
    "V4v": "core p0/p0_inf (Navier-Stokes inlet)",
    "V4m": "recovery_total and q_peak, medium to fine (inlet levels)",
    "X1": "SU2 AVG_TOTALPRESS vs mass average (inlet)",
}
NOT_APPLICABLE = {
    "V1": "no Euler wedge with flow.dat in the inputs",
    "V2a": "no check in postprocess/validation.py; needs flow.dat of a laminar wedge",
    "V2b": "no Navier-Stokes wedge with surface_flow.dat in the inputs",
    "V3": "no cylinder case with surface_flow.dat in the inputs",
    "V3 grid": "no cylinder levels with equal numerics (medium and fine)",
    "V3 stand-off": "no cylinder case with flow.dat in the inputs",
    "V4e": "no Euler inlet with surface_flow.dat in the inputs",
    "V4v": "no Navier-Stokes inlet with surface_flow.dat in the inputs",
    "V4m": "no inlet levels with equal numerics (medium and fine)",
    "X1": "no inlet case in the inputs (the throat plane is needed)",
}


@dataclass
class Case:
    case_id: str
    source: Path
    staged: Path | None = None
    params: dict = field(default_factory=dict)
    geometry: dict = field(default_factory=dict)
    fs: dict = field(default_factory=dict)
    summary: dict | None = None
    notes: list = field(default_factory=list)
    mesh: str = "-"
    fingerprint: str = "-"
    results: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)

    @property
    def family(self):
        return self.params.get("family")

    @property
    def level(self):
        return self.params.get("mesh_level")

    @property
    def solver(self):
        return self.params.get("solver")

    def has(self, name):
        return self.staged is not None and (self.staged / name).exists()


def case_id(case_dir):
    """Parent directory name and case directory name, e.g. 2026-11-01_numerics/wedge-381c48d17f."""
    path = Path(case_dir).resolve()
    return f"{path.parent.name}/{path.name}"


def clean(text, case=None):
    """Error text without the staging path (so the report is the same on every run), one line, no pipes."""
    text = str(text)
    if case is not None and case.staged is not None:
        text = text.replace(str(case.staged), case.case_id)
    return " ".join(text.replace("|", "/").split())


def stage(source, dest):
    """Copy the files of a case directory to dest, unpacking *.gz. Only reads the source."""
    dest.mkdir(parents=True)
    for src in sorted(Path(source).iterdir()):
        if not src.is_file():
            continue
        if src.suffix == ".gz":
            with gzip.open(src, "rb") as f_in, (dest / src.stem).open("wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copyfile(src, dest / src.name)


def materialise(case_dir, tmp_dir):
    """Copy a run record into tmp_dir and make sure its mesh is there. The record is only read.

    gzip files are unpacked. If mesh.su2 or mesh_markers.json is missing (the run records do not
    always keep them) the mesh is regenerated from params.json with worker.make_case.make; the
    record's own geometry.json, case.cfg and mesh_quality.json are kept. If job.json records a
    mesh_fingerprint it is compared with the fingerprint of the mesh in tmp_dir. The worker's
    job.json carries only mesh_sha256 (a byte hash, which differs between machines), so for a
    regenerated mesh the byte comparison is reported as a note and the fingerprint stays "not recorded".
    Returns {"mesh": "record" | "regenerated" | "missing", "fingerprint": "match" | "mismatch" |
    "not recorded" | "not compared", "notes": [...]}. It does not raise for a bad record.
    """
    source, tmp = Path(case_dir), Path(tmp_dir)
    stage(source, tmp)
    info = {"mesh": "record", "fingerprint": "not recorded", "notes": []}
    if not all((tmp / name).exists() for name in MESH_FILES):
        info["mesh"] = "regenerated"
        regen = tmp / "_regenerated"
        try:
            make_case(json.loads((tmp / "params.json").read_text()), regen)
        except EXPECTED_ERRORS as err:
            info["mesh"] = "missing"
            info["notes"].append(f"mesh regeneration failed: {type(err).__name__}: {err}")
            return info
        for name in MESH_FILES:
            shutil.copyfile(regen / name, tmp / name)
        for name in RECORD_COPIES_KEPT:
            if not (tmp / name).exists() and (regen / name).exists():
                shutil.copyfile(regen / name, tmp / name)
        shutil.rmtree(regen)

    recorded = {}
    if (source / "job.json").exists():
        try:
            recorded = json.loads((source / "job.json").read_text())
        except (OSError, ValueError):
            info["notes"].append("job.json unreadable")
    mesh_path = tmp / "mesh.su2"
    if mesh_path.exists() and "mesh_fingerprint" in recorded:
        try:
            same = mesh_fingerprint(mesh_path) == recorded["mesh_fingerprint"]
            info["fingerprint"] = "match" if same else "mismatch"
        except EXPECTED_ERRORS as err:
            info["fingerprint"] = "not compared"
            info["notes"].append(f"fingerprint not compared: {type(err).__name__}: {err}")
    elif mesh_path.exists() and info["mesh"] == "regenerated" and "mesh_sha256" in recorded:
        digest = hashlib.sha256(mesh_path.read_bytes()).hexdigest()
        bytes_equal = "equal" if digest == recorded["mesh_sha256"] else "differ"
        info["notes"].append(f"job.json has only mesh_sha256; regenerated mesh bytes {bytes_equal}")
    return info


def load_case(source, dest):
    """A Case: materialised record (see materialise), params, geometry, freestream and summary."""
    case = Case(case_id=case_id(source), source=Path(source))
    try:
        info = materialise(source, dest)
    except OSError as err:
        case.notes.append(f"case directory unreadable: {err}")
        return case
    case.staged = dest
    case.mesh, case.fingerprint = info["mesh"], info["fingerprint"]
    case.notes += [clean(note, case) for note in info["notes"]]
    if not case.has("params.json"):
        case.notes.append("params.json missing")
    try:
        case.params, case.geometry, case.fs = surface.inputs(dest)
    except ValueError as err:
        case.notes.append(f"params or geometry unreadable: {clean(err, case)}")
    if case.has("history.csv"):
        try:
            case.summary = history.summarize(dest / "history.csv")
        except EXPECTED_ERRORS as err:  # reported in the case table, the report goes on
            case.notes.append(
                f"history not summarised: {clean(f'{type(err).__name__}: {err}', case)}"
            )
    return case


def run_check(case, fn, *args, **kwargs):
    """fn(staged case directory, ...) or {"pass": None, "error": ...} if it cannot run."""
    try:
        result = fn(case.staged, *args, **kwargs)
    except EXPECTED_ERRORS as err:  # a check that cannot run becomes a "not run" row
        return {"pass": None, "error": clean(f"{type(err).__name__}: {err}", case)}
    if "error" in result:
        result["error"] = clean(result["error"], case)
    return result


def case_metrics(case):
    """metrics.compute of the staged case, cached; {"error": ...} if it cannot be computed."""
    if "metrics" not in case.cache:
        try:
            case.cache["metrics"] = metrics.compute(case.staged)
        except EXPECTED_ERRORS as err:
            case.cache["metrics"] = {"error": clean(f"{type(err).__name__}: {err}", case)}
    return case.cache["metrics"]


def load_surface(case):
    """surface.load of the staged case, cached. Raises ValueError with the reason if it cannot be read."""
    if "surface" not in case.cache:
        try:
            case.cache["surface"] = {"surface": surface.load(case.staged)}
        except EXPECTED_ERRORS as err:
            case.cache["surface"] = {"error": clean(f"{type(err).__name__}: {err}", case)}
    result = case.cache["surface"]
    if "error" in result:
        raise ValueError(result["error"])
    return result["surface"]


def row(item, quantity, measured, verdict, tol=None, kind=None):
    default_tol, default_kind = TOLERANCE[item]
    return {
        "id": item,
        "quantity": quantity,
        "tol": tol or default_tol,
        "type": kind or default_kind,
        "measured": measured,
        "verdict": verdict,
    }


def not_run(item, quantity, reason):
    return row(item, quantity, f"not run: {reason}", "not run")


def verdict_of(ok, kind="hard"):
    if ok is None:
        return "not run"
    if kind == "report":
        return "REPORT"
    return "PASS" if ok else "FAIL"


def _shown(path):
    """Path relative to the repository when it lies inside it (for the report text)."""
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def _oblique_rows(res, where, stored_in=None):
    """V1 rows: beta, p2/p1 and M2 against the oblique shock relations (res is a check dictionary)."""
    quantity = "{} of the Euler wedge (" + where + ")"
    if res.get("pass") is None:
        return [not_run("V1", quantity.format("beta, p2/p1, M2"), res.get("error", "no result"))]
    details = res.get("details", {})
    errors = details.get("errors")
    suffix = f" (stored in {stored_in})" if stored_in else ""
    if errors is None:  # the check ran but found no plateau or shock
        message = clean(details.get("error", ""))
        return [row("V1", quantity.format("beta, p2/p1, M2"), f"no result: {message}", "FAIL")]
    tol_beta, tol_ratio = details["tol_beta_deg"], details["tol_ratio"]
    return [
        row(
            "V1",
            quantity.format("beta"),
            f"{errors['beta_deg']:+.3f} deg{suffix}",
            verdict_of(abs(errors["beta_deg"]) <= tol_beta),
            tol=f"+-{tol_beta:g} deg",
        ),
        row(
            "V1",
            quantity.format("p2/p1 vs oblique shock"),
            f"{errors['p_ratio_rel']:+.2%}{suffix}",
            verdict_of(abs(errors["p_ratio_rel"]) <= tol_ratio),
            tol=f"{tol_ratio:.0%}",
        ),
        row(
            "V1",
            quantity.format("M2 vs oblique shock"),
            f"{errors['M2_rel']:+.2%}{suffix}",
            verdict_of(abs(errors["M2_rel"]) <= tol_ratio),
            tol=f"{tol_ratio:.0%}",
        ),
    ]


def oblique_rows(case, res):
    return _oblique_rows(res, case.case_id)


def stored_rows(task1_dir):
    """V1 and V2a rows from the JSON reports the Colab notebook wrote (runs/task1), if they exist."""
    rows = []
    v1 = Path(task1_dir) / "v1_oblique_shock.json"
    if v1.exists():
        try:
            rows += _oblique_rows(json.loads(v1.read_text()), "Colab run", _shown(v1))
        except (OSError, ValueError, KeyError) as err:
            rows.append(not_run("V1", "stored V1 report", f"{_shown(v1)}: {err}"))
    v2a = Path(task1_dir) / "v2a.json"
    if v2a.exists():
        try:
            record = json.loads(v2a.read_text())
            pct = float(record["plateau_pct_vs_inviscid"])
            check_p = record["check"]["details"]["errors"]["p_ratio_rel"]
            band = "inside" if 0.0 <= pct <= 6.0 else "outside"
            measured = (
                f"{pct:+.2f} percent, {band} the +0 to +6 percent band (stored in {_shown(v2a)}; "
                f"its check block gives p2/p1 {check_p:+.2%})"
            )
            rows.append(
                row(
                    "V2a",
                    "plateau p vs inviscid, laminar wedge 10 deg (Colab run)",
                    measured,
                    "REPORT",
                )
            )
        except (OSError, ValueError, KeyError) as err:
            rows.append(not_run("V2a", "stored V2a report", f"{_shown(v2a)}: {err}"))
    return rows


def wedge_rows(case):
    theta = case.params.get("theta1_deg")
    if case.solver == "EULER":
        if not case.has("flow.dat"):
            return [not_run("V1", f"beta, p2/p1, M2 ({case.case_id})", "flow.dat absent")]
        return oblique_rows(
            case, run_check(case, validation.oblique_shock_check, theta, mach=case.fs["M"])
        )
    quantity = f"q_w vs Eckert flat plate, 0.3 <= x/X_w <= 0.9 ({case.case_id})"
    if not case.has("surface_flow.dat"):
        return [not_run("V2b", quantity, "surface_flow.dat absent")]
    res = run_check(case, validation.eckert_check, theta)
    case.results["eckert"] = res
    if res.get("pass") is None:
        return [not_run("V2b", quantity, res.get("error", "no result"))]
    measured = f"mean {res['mean_abs_rel']:.2%}, max {res['max_abs_rel']:.2%} ({res['n']} nodes)"
    return [row("V2b", quantity, measured, verdict_of(res["pass"]))]


def cylinder_rows(case):
    q_name = f"q_stag vs Fay-Riddell ({case.case_id})"
    s_name = f"stand-off / R vs Billig ({case.case_id})"
    if not case.has("surface_flow.dat"):
        return [
            not_run("V3", q_name, "surface_flow.dat absent"),
            not_run("V3 stand-off", s_name, "surface_flow.dat absent"),
        ]
    res = run_check(case, validation.fay_riddell_check)
    case.results["fay"] = res
    if res.get("pass") is None:
        return [
            not_run("V3", q_name, res.get("error", "no result")),
            not_run("V3 stand-off", s_name, "check did not run"),
        ]
    fine = case.level == "fine"
    measured = (
        f"q_stag {res['q_stag']:.4g} W/m^2, Fay-Riddell {res['q_FR']:.4g} W/m^2, "
        f"error {res['rel_error']:+.2%}"
    )
    if not fine:
        measured += f"; level {case.level}, the tolerance applies to the fine mesh"
    rows = [row("V3", q_name, measured, verdict_of(res["pass"]) if fine else "REPORT")]
    if res.get("standoff_rel_error") is None:
        reason = "; ".join(res.get("notes", [])) or "no flow.dat"
        rows.append(not_run("V3 stand-off", s_name, reason))
    else:
        measured = (
            f"stand-off/R {res['standoff_over_R']:.4g} vs Billig "
            f"{res['standoff_billig']:.4g}, error {res['standoff_rel_error']:+.2%}"
        )
        rows.append(row("V3 stand-off", s_name, measured, "REPORT"))
    return rows


def x1_row(case):
    """X1: SU2 AVG_TOTALPRESS against the mass-averaged throat p0 (every run with a throat)."""
    quantity = f"SU2 AVG_TOTALPRESS vs mass average ({case.case_id})"
    m = case_metrics(case)
    if "error" in m:
        return not_run("X1", quantity, m["error"])
    if m["su2_crosscheck_pass"] is None:
        return not_run("X1", quantity, "no AVG_TOTALPRESS column in history")
    rel = m["su2_avg_totalpress_Pa"] / (m["recovery_throat"] * m["p0_inf_Pa"]) - 1.0
    return row("X1", quantity, f"{rel:+.3%}", verdict_of(m["su2_crosscheck_pass"]))


def inlet_rows(case):
    res = run_check(case, validation.inlet_check)
    case.results["inlet"] = res
    design = (case.params.get("theta1_deg"), case.params.get("theta2_deg")) == DESIGN_THETA
    scope = "" if design else " (outside the 8/8 design: REPORT only)"
    if case.solver == "EULER":
        item, rows = "V4e", []
        quantity = f"{{}} ({case.case_id}){scope}"
        if res.get("pass") is None:
            rows.append(
                not_run(
                    item,
                    quantity.format("throat area average p0/p0_inf"),
                    res.get("error", "no result"),
                )
            )
        else:
            for key, label in (
                ("p0_ratio_area", "throat area average p0/p0_inf"),
                ("mach_area", "throat area average Mach"),
            ):
                err = res["rel_error"][key]
                rows.append(
                    row(
                        item,
                        quantity.format(label),
                        f"{err:+.2%}",
                        verdict_of(abs(err) <= res["tol"]) if design else "REPORT",
                    )
                )
    else:
        item = "V4v"
        quantity = f"core (mid 50 percent) p0/p0_inf ({case.case_id}){scope}"
        if res.get("pass") is None:
            rows = [not_run(item, quantity, res.get("error", "no result"))]
        else:
            err = res["rel_error"]["p0_ratio_core"]
            rows = [
                row(
                    item,
                    quantity,
                    f"{err:+.2%}",
                    verdict_of(abs(err) <= res["tol"], "soft") if design else "REPORT",
                )
            ]
    return rows + [x1_row(case)]


def case_rows(case):
    """Verdict rows for one case; which checks apply follows from params.json."""
    if case.family == "wedge":
        return wedge_rows(case)
    if case.family == "cylinder":
        return cylinder_rows(case)
    if case.family == "inlet2r":
        return inlet_rows(case)
    case.notes.append("no check applies (params.json has no known family)")
    return []


def numerics_key(case):
    """Short hash of the discretisation lines of case.cfg. Iteration count, output and file names
    are left out so that runs with the same numerics but different output settings group together."""
    if not case.has("case.cfg"):
        return None
    lines = []
    for raw in (case.staged / "case.cfg").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("%") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key == "ITER" or any(word in key for word in ("OUTPUT", "FILENAME", "SCREEN")):
            continue
        lines.append(" ".join(line.split()))
    return hashlib.sha1("\n".join(sorted(lines)).encode()).hexdigest()[:10]


def grid_entries(cases):
    """One grid study per group of cases with the same family, theta, solver and numerics that has
    a medium and a fine level (two or three levels, coarse to fine order)."""
    groups = {}
    for case in cases:
        if case.family not in ("cylinder", "inlet2r") or case.level not in LEVELS:
            continue
        numerics = numerics_key(case)
        if numerics is None:
            continue
        key = (
            case.family,
            case.params.get("theta1_deg"),
            case.params.get("theta2_deg"),
            case.solver,
            numerics,
        )
        groups.setdefault(key, []).append(case)
    entries = []
    for key in sorted(groups, key=str):
        family, theta1, theta2, solver, numerics = key
        by_level = {}
        for case in groups[key]:
            by_level.setdefault(case.level, []).append(case)
        if "medium" not in by_level or "fine" not in by_level:
            continue
        parts = [family] + ([f"theta {theta1:g}/{theta2:g} deg"] if theta1 is not None else [])
        label = ", ".join(parts + [str(solver), f"numerics {numerics}"])
        entry = {
            "label": label,
            "family": family,
            "tol": CYLINDER_GRID_TOL if family == "cylinder" else validation.GRID_TOL,
            "levels": [],
            "result": None,
        }
        entry["levels"] = [(lvl, by_level[lvl][0].case_id) for lvl in LEVELS if lvl in by_level]
        duplicates = [lvl for lvl, cases_at in by_level.items() if len(cases_at) > 1]
        if duplicates:
            entry["result"] = {"error": f"more than one case at level {', '.join(duplicates)}"}
        else:
            ordered = [by_level[lvl][0] for lvl in LEVELS if lvl in by_level]
            try:
                entry["result"] = validation.grid_study(
                    [c.staged for c in ordered], keys=tuple(entry["tol"]), tol=entry["tol"]
                )
            except EXPECTED_ERRORS as err:
                entry["result"] = {"error": f"{type(err).__name__}: {err}"}
            if (
                "error" in entry["result"]
            ):  # grid_study reports the staged paths; name the cases instead
                for case in ordered:
                    entry["result"]["error"] = clean(entry["result"]["error"], case)
        entries.append(entry)
    return entries


def grid_rows(entry):
    item = "V3 grid" if entry["family"] == "cylinder" else "V4m"
    res = entry["result"]
    levels = "; ".join(f"{lvl} {cid}" for lvl, cid in entry["levels"])
    if "table" not in res:
        return [not_run(item, f"medium to fine, {entry['label']}", res.get("error", "no result"))]
    rows = []
    for key, tol in entry["tol"].items():
        table_row = res["table"][key]
        rel = table_row["rel_change"][-1]
        rows.append(
            row(
                item,
                f"{key} medium to fine, {entry['label']}",
                f"{rel:+.2%} (levels: {levels})",
                verdict_of(table_row.get("within_tol")),
                tol=f"{tol:.0%}",
            )
        )
    return rows


def residual_series(cases):
    series = []
    for case in cases:
        if not case.has("history.csv"):
            continue
        try:
            cols = history.load(case.staged / "history.csv")
            residual = cols[history.find_column(cols, "rms[rho]")]
            # SU2 steady runs write Time_Iter = 0 on every row, so the iteration is the row index
            # (the same count history.summarize reports as "iterations").
            series.append((case.case_id, np.arange(len(residual)), residual))
        except (OSError, KeyError, ValueError) as err:
            case.notes.append(f"residual history not read: {clean(err, case)}")
    return series


def wedge_series(cases):
    """Heat flux along the wedge wall from surface_flow.dat (the wall is the straight ramp y = x tan theta)."""
    series, eckert = [], []
    for case in cases:
        if case.family != "wedge" or case.solver == "EULER" or not case.has("surface_flow.dat"):
            continue
        try:
            data = read_tecplot_ascii(case.staged / "surface_flow.dat")["data"]
            theta = math.radians(case.params["theta1_deg"])
            if "Heat_Flux" not in data:
                raise ValueError("no Heat_Flux column")
            if np.max(np.abs(data["y"] - data["x"] * math.tan(theta))) > 1e-6:
                raise ValueError("surface file has nodes off the wedge wall")
            order = np.argsort(data["x"])
            x, y = data["x"][order], data["y"][order]
            s = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))))
            series.append((case.case_id, s, data["Heat_Flux"][order], case.geometry["X_w"]))
            profile = case.results.get("eckert", {}).get("profile")
            if profile:
                eckert.append(
                    (
                        f"Eckert {case.case_id}",
                        np.array([p["x"] for p in profile]),
                        np.array([p["q_eckert"] for p in profile]),
                    )
                )
        except (OSError, KeyError, ValueError) as err:
            case.notes.append(f"wedge heat flux not plotted: {clean(err, case)}")
    return series, eckert


def cylinder_series(cases):
    """Heat flux against phi from surface_flow.dat; the cylinder file holds only wall nodes (checked)."""
    series, fr_points = [], []
    for case in cases:
        if case.family != "cylinder" or not case.has("surface_flow.dat"):
            continue
        try:
            data = read_tecplot_ascii(case.staged / "surface_flow.dat")["data"]
            radius = float(case.params["radius_m"])
            if "Heat_Flux" not in data:
                raise ValueError("no Heat_Flux column")
            if np.max(np.abs(np.hypot(data["x"], data["y"]) - radius)) > 1e-6:
                raise ValueError("surface file has nodes off the cylinder wall")
            phi = np.degrees(np.arctan2(data["y"], -data["x"]))
            order = np.argsort(phi)
            series.append((case.case_id, phi[order], data["Heat_Flux"][order]))
            if "q_FR" in case.results.get("fay", {}):
                fr_points.append(case.results["fay"]["q_FR"])
        except (OSError, KeyError, ValueError) as err:
            case.notes.append(f"cylinder heat flux not plotted: {clean(err, case)}")
    return series, (fr_points[0] if fr_points else None)


def throat_series(cases):
    series, ref = [], None
    for case in cases:
        if case.family != "inlet2r" or not case.has("surface_flow.dat"):
            continue
        try:
            throat = metrics.throat_profile(load_surface(case), case.geometry)
            series.append((case.case_id, throat["s"], throat["p0"] / case.fs["p0"]))
            ref = ref if ref is not None else case.geometry["recovery_2shock_inviscid"]
        except (KeyError, ValueError) as err:
            case.notes.append(f"throat profile not plotted: {clean(err, case)}")
    return series, ref


def inlet_heat_series(cases):
    series, peaks, x1 = [], [], None
    for case in cases:
        if case.family != "inlet2r" or case.solver == "EULER" or not case.has("surface_flow.dat"):
            continue
        try:
            body = load_surface(case)["body"]
            if "q" not in body:
                raise ValueError("no Heat_Flux column")
            series.append((case.case_id, body["x"], body["q"]))
            x1 = x1 if x1 is not None else case.geometry["X1"]
            m = case_metrics(case)
            if "q_peak_W_m2" in m and m["q_peak_W_m2"] is not None:
                peaks.append((case.case_id, m["x_q_peak_m"], m["q_peak_W_m2"]))
        except (KeyError, ValueError) as err:
            case.notes.append(f"inlet heat flux not plotted: {clean(err, case)}")
    return series, peaks, x1


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_residuals(series, path):
    if not series:
        raise ValueError("no case has a readable history")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for label, iterations, residual in series:
        ax.plot(iterations, residual, lw=1.0, label=label)
    ax.set_xlabel("iteration (row of history.csv)")
    ax.set_ylabel("log10 rms[Rho] (density residual)")
    ax.set_title("Residual history")
    ax.legend(fontsize=6)
    return _save(fig, path)


def plot_wedge(series, eckert, path):
    if not series:
        raise ValueError("no wedge with a readable surface_flow.dat")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x_w = series[0][3]
    ax.axvspan(0.3 * x_w, 0.9 * x_w, color="0.9", label="window 0.3 to 0.9 X_w")
    for label, s, q, _ in series:
        ax.plot(s, q, "o-", ms=2, lw=1.0, label=f"CFD {label}")
    for label, s, q in eckert:
        ax.plot(s, q, "-", lw=1.5, label=label)
    ax.set_xlabel("s, distance along the wall from the leading edge (m)")
    ax.set_ylabel("wall heat flux q_w (W/m^2)")
    ax.set_title("Laminar wedge heat flux")
    ax.legend(fontsize=6)
    return _save(fig, path)


def plot_cylinder(series, fr_q, path):
    if not series:
        raise ValueError("no cylinder with a readable surface_flow.dat")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for label, phi, q in series:
        ax.plot(phi, q, "o-", ms=2, lw=1.0, label=label)
    if fr_q is not None:
        ax.plot([0.0], [fr_q], "k*", ms=10, label="Fay-Riddell q_FR (phi = 0)")
    ax.set_xlabel("phi, angle from the stagnation point (deg)")
    ax.set_ylabel("wall heat flux q_w (W/m^2)")
    ax.set_title("Cylinder heat flux by mesh level")
    ax.legend(fontsize=6)
    return _save(fig, path)


def plot_throat(series, ref, path):
    if not series:
        raise ValueError("no inlet with a readable throat plane")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for label, s, ratio in series:
        ax.plot(s, ratio, "o-", ms=2, lw=1.0, label=label)
    ax.axhline(ref, color="k", ls="--", lw=1.0, label="two-shock value (geometry.json)")
    ax.set_xlabel("distance along the throat plane from its first node (m)")
    ax.set_ylabel("p0 / p0_inf (-)")
    ax.set_title("Throat total pressure profile")
    ax.legend(fontsize=6)
    return _save(fig, path)


def plot_inlet_heat(series, peaks, x1, path):
    if not series:
        raise ValueError("no inlet with a readable body surface")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for label, x, q in series:
        ax.plot(x, q, "o-", ms=2, lw=1.0, label=label)
    if x1 is not None:
        ax.axvline(x1, color="0.5", ls=":", lw=1.0, label="X1 (ramp 1 to ramp 2)")
    for label, x_peak, q_peak in peaks:
        ax.plot([x_peak], [q_peak], "r^", ms=8, label=f"ramp-2 peak {label}")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("wall heat flux q_w (W/m^2)")
    ax.set_title("Inlet body heat flux")
    ax.legend(fontsize=6)
    return _save(fig, path)


def plot_grid(entries, path):
    panels = []
    for entry in entries:
        res = entry["result"]
        if "table" not in res:
            continue
        labels = [lvl for lvl, _ in entry["levels"]]
        for key in entry["tol"]:
            values = res["table"][key]["values"]
            unit = "W/m^2" if key.endswith("W_m2") else "-"
            panels.append((entry["label"], key, unit, labels, values))
    if not panels:
        raise ValueError("no grid study with a medium and a fine level ran")
    fig, axes = plt.subplots(1, len(panels), figsize=(3.4 * len(panels), 3.8), squeeze=False)
    for ax, (title, key, unit, labels, values) in zip(axes[0], panels):
        bars = ax.bar(labels, values, color="0.6")
        ax.bar_label(bars, fmt="%.4g", fontsize=6)
        ax.set_title(f"{key}\n{title}", fontsize=6)
        ax.set_xlabel("mesh level")
        ax.set_ylabel(f"{key} ({unit})", fontsize=7)
    return _save(fig, path)


def build_figures(cases, entries, out, date):
    """Figures that can be drawn; the rest are listed with the reason. Returns (figures, not_produced)."""
    figures, not_produced = [], []

    def add(name, title, make):
        path = Path(out) / f"{date}_{name}.png"
        try:
            case_ids, note = make(path)
        except EXPECTED_ERRORS as err:  # a figure that cannot be drawn is listed with the reason
            not_produced.append(f"{title}: {type(err).__name__}: {err}")
            return
        figures.append({"file": path.name, "title": title, "cases": case_ids, "note": note})

    def residual(path):
        series = residual_series(cases)
        plot_residuals(series, path)
        return [s[0] for s in series], "All cases with a history.csv"

    add("residual_history", "Residual history", residual)

    def wedge(path):
        series, eckert = wedge_series(cases)
        note = (
            "Eckert curve from eckert_check drawn"
            if eckert
            else "Eckert curve not drawn: eckert_check produced no profile (see the verdict table)"
        )
        plot_wedge(series, eckert, path)
        return [s[0] for s in series], note

    add("wedge_heat_flux", "Laminar wedge heat flux q(x)", wedge)

    def cylinder(path):
        series, fr_q = cylinder_series(cases)
        note = (
            "Fay-Riddell point drawn"
            if fr_q is not None
            else "Fay-Riddell point not drawn: fay_riddell_check produced no result"
        )
        plot_cylinder(series, fr_q, path)
        return [s[0] for s in series], note

    add("cylinder_heat_flux", "Cylinder heat flux q(phi) by mesh level", cylinder)

    def throat(path):
        series, ref = throat_series(cases)
        plot_throat(series, ref, path)
        return [s[0] for s in series], "Two-shock value from geometry.json"

    add("inlet_throat_p0", "Inlet throat total pressure profile", throat)

    def inlet_heat(path):
        series, peaks, x1 = inlet_heat_series(cases)
        plot_inlet_heat(series, peaks, x1, path)
        note = "Ramp-2 peak from metrics.compute marked" if peaks else "No metrics peak marked"
        return [s[0] for s in series], note

    add("inlet_heat_flux", "Inlet body heat flux q(x)", inlet_heat)

    def grid(path):
        plot_grid(entries, path)
        ids = [cid for entry in entries if "table" in entry["result"] for _, cid in entry["levels"]]
        return ids, "Grid study bars for medium and fine, with coarse where present"

    add("grid_study", "Grid study", grid)
    return figures, not_produced


def _fmt_values(values):
    return " / ".join("nan" if v is None or not np.isfinite(v) else f"{v:.6g}" for v in values)


def render_markdown(date, command, cases, rows, entries, figures, not_produced):
    lines = [
        f"# Validation report, {date}",
        "",
        f"Generated by `{command}`.",
        "",
        (
            "Verdicts: PASS and FAIL are checked against the tolerance; REPORT is reported without a "
            "gate; `not run` means the check could not run, and the Measured column gives the reason."
        ),
        "",
        "## Cases",
        "",
        "| Case id | Family | Level | Solver | Mesh | Status | Iterations | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        status = case.summary["status"] if case.summary else "no history"
        iterations = case.summary["iterations"] if case.summary else "-"
        notes = "; ".join(clean(n) for n in case.notes) or "-"
        lines.append(
            f"| {case.case_id} | {case.family or '-'} | {case.level or '-'} | "
            f"{case.solver or '-'} | {case.mesh}, fingerprint {case.fingerprint} | {status} | "
            f"{iterations} | {notes} |"
        )

    lines += [
        "",
        "## Tolerance table (00_decisions.md section 5)",
        "",
        "| Id | Quantity | Tolerance | Type | Measured | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for item in ID_ORDER:
        for r in rows.get(item) or [not_run(item, DEFAULT_QUANTITY[item], NOT_APPLICABLE[item])]:
            lines.append(
                f"| {item} | {clean(r['quantity'])} | {clean(r['tol'])} | {r['type']} | "
                f"{clean(r['measured'])} | {r['verdict']} |"
            )

    lines += ["", "## Grid studies", ""]
    if not entries:
        lines.append("No group of cases has a medium and a fine level with equal numerics.")
        lines.append("")
    for entry in entries:
        lines += [
            f"### {entry['label']}",
            "",
            "Levels: " + "; ".join(f"{lvl} `{cid}`" for lvl, cid in entry["levels"]),
            "",
        ]
        res = entry["result"]
        if "table" not in res:
            lines += [f"not run: {clean(res.get('error', 'no result'))}", ""]
            continue
        labels = ", ".join(lvl for lvl, _ in entry["levels"])
        lines += [
            f"| Quantity | Values ({labels}) | Medium to fine | Order | Extrapolated | Note |",
            "|---|---|---|---|---|---|",
        ]
        for key in entry["tol"]:
            t = res["table"][key]
            order = "-" if t["order"] is None else f"{t['order']:.3g}"
            extrap = "-" if t["extrapolated"] is None else f"{t['extrapolated']:.6g}"
            lines.append(
                f"| {key} | {_fmt_values(t['values'])} | {t['rel_change'][-1]:+.2%} | "
                f"{order} | {extrap} | {clean(t['note'] or '-')} |"
            )
        lines.append("")

    lines += ["## Figures", ""]
    if not figures:
        lines += ["No figure could be drawn.", ""]
    for fig in figures:
        lines += [
            f"### {fig['title']}",
            "",
            f"![{fig['title']}]({fig['file']})",
            "",
            f"Caption: {fig['title']}. Cases: {', '.join(fig['cases']) or 'none'}. {fig['note']}.",
            "",
        ]
    if not_produced:
        lines += ["### Figures not produced", ""] + [f"- {clean(p)}" for p in not_produced] + [""]
    return "\n".join(lines)


def write_report(
    case_dirs, out_dir, date, command="python -m postprocess.report", task1_dir=TASK1_DIR
):
    """Run the checks on the case directories and write the markdown and the figures to out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="validation_report_") as tmp:
        cases = [load_case(src, Path(tmp) / f"case_{i:02d}") for i, src in enumerate(case_dirs)]
        rows = {}
        for r in stored_rows(task1_dir):
            rows.setdefault(r["id"], []).append(r)
        for case in cases:
            for r in case_rows(case):
                rows.setdefault(r["id"], []).append(r)
        entries = grid_entries(cases)
        for entry in entries:
            for r in grid_rows(entry):
                rows.setdefault(r["id"], []).append(r)
        figures, not_produced = build_figures(cases, entries, out_dir, date)
        text = render_markdown(date, command, cases, rows, entries, figures, not_produced)
    md_path = out_dir / f"{date}_report.md"
    md_path.write_text(text)
    return md_path, [out_dir / f["file"] for f in figures]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(description="Validation report for run records.")
    parser.add_argument("--out", default="docs/validation", help="output directory")
    parser.add_argument("--date", required=True, help="date stamp for the file names, YYYY-MM-DD")
    parser.add_argument(
        "--cases",
        nargs="*",
        default=[],
        metavar="CASE_DIR",
        help="case directories, each with a params.json",
    )
    parser.add_argument(
        "--task1-dir",
        default=str(TASK1_DIR),
        help="directory with the Colab JSON reports v1_oblique_shock.json and v2a.json",
    )
    args = parser.parse_args(argv)
    datetime.date.fromisoformat(args.date)
    command = " ".join(["python -m postprocess.report", *argv])
    md_path, figure_paths = write_report(
        args.cases, args.out, args.date, command, task1_dir=args.task1_dir
    )
    print(md_path)
    for path in figure_paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

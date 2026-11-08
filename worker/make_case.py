"""Build a case directory (mesh, markers, config, job.json) from a parameter dict.

Layout and file contents are described in docs/specs/01_interfaces.md ("Job directory").
Everything is a pure function of `params` except the file writes, the timestamp and the git commit.

The mesh is identified by `mesh_fingerprint` (geometry/structured.py), not by the sha256 of
mesh.su2: the bytes of the file differ between machines (the last digit of a coordinate depends on
the numpy build and platform; Colab and the staging container disagreed), while the coordinates
agree to far better than 1 nm. The fingerprint hashes coordinates rounded to 1 nm, the cells and the
marker node ids. `mesh_bbox` in job.json is a debugging aid for a mismatch. config_sha256 is a
hash of the text of case.cfg, which is platform independent.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cases.config import render
from geometry import airfoil2d, cylinder, inlet, inlet3r, wedge
from geometry.structured import mesh_bbox, mesh_fingerprint

REPO = Path(__file__).resolve().parent.parent

# Mesh-quality gate, 00_decisions.md section 6.
MIN_ANGLE_DEG = 40.0
FIRST_CELL_TOL = 0.10
MAX_GROWTH = 1.25
MAX_ASPECT = 5000.0

BUILDERS = {"wedge": wedge.build, "inlet2r": inlet.build, "inlet3r": inlet3r.build, "cylinder": cylinder.build,
            "airfoil2d": airfoil2d.build}


class StageError(ValueError):
    """A stage of make() failed: stage is "geometry", "mesh_quality" or "config"; errors is a list
    of strings. It is a ValueError so that callers that do not care which stage can catch that."""

    def __init__(self, stage, errors, message=None):
        super().__init__(message or f"{stage} failed: " + "; ".join(errors))
        self.stage, self.errors = stage, list(errors)


def canonical_json(params):
    """Sorted keys, no spaces; floats are written with Python's repr."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def case_id(params):
    """family-<first 10 hex digits of sha256 of the canonical params>."""
    digest = hashlib.sha256(canonical_json(params).encode()).hexdigest()
    return f"{params['family']}-{digest[:10]}"


def requested_first_cell(params):
    """{wall marker: first-cell height (m) that the mesh was asked for}, per family."""
    family, level = params["family"], params.get("mesh_level", "medium")
    if family == "wedge":
        return {"body": wedge.sizes(level)["d0"]}
    if family in ("inlet2r", "inlet3r"):
        # inlet3r: d0 x 0.6 (gate 5 over the Task 9 envelope)
        d0 = (inlet3r if family == "inlet3r" else inlet).sizes(level)["d0"]
        return {"body": d0, "cowl": d0}
    if family == "cylinder":
        return {"wall": cylinder.LEVELS[level][0]}
    if family == "airfoil2d":
        # y+ = 0.5 at the chord Reynolds number (task10_drone_sizing.md, gate 5)
        return {"airfoil": airfoil2d.first_cell(params["reynolds"], level)}
    raise NotImplementedError(f"geometry family {family!r}")


def quality_failures(quality, requested):
    """List of strings, one per violated gate; empty when the mesh passes."""
    fails = []
    if quality["n_inverted"] != 0:
        fails.append(f"n_inverted = {quality['n_inverted']} (must be 0)")
    if not quality["min_angle_deg"] >= MIN_ANGLE_DEG:      # written so that NaN fails
        fails.append(f"min_angle_deg = {quality['min_angle_deg']:.2f} (must be >= {MIN_ANGLE_DEG})")
    for wall, want in requested.items():
        got = quality["first_cell_height"].get(wall)
        if got is None or not abs(got - want) <= FIRST_CELL_TOL * want:
            fails.append(f"first_cell_height[{wall}] = {got} m, requested {want} m "
                         f"(tolerance {FIRST_CELL_TOL:.0%})")
    growth = quality["max_growth"]
    if growth is not None and not growth <= MAX_GROWTH:
        fails.append(f"max_growth = {growth:.3f} (must be <= {MAX_GROWTH})")
    if not quality["max_aspect_ratio"] <= MAX_ASPECT:
        fails.append(f"max_aspect_ratio = {quality['max_aspect_ratio']:.0f} (must be <= {MAX_ASPECT:.0f})")
    return fails


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def config_sha256(path):
    """sha256 of the lines of case.cfg that SU2 reads: comment lines (starting with %) and blank
    lines are left out. The comment lines carry the geometry summary at full float precision, and
    its last digit can differ between machines (h_duct differed by 3e-18 between the container and
    Colab, pool job inlet2r-db92dcf68d), which is not a different case."""
    lines = (line.rstrip() for line in Path(path).read_text().splitlines())
    text = "\n".join(line for line in lines if line and not line.lstrip().startswith("%"))
    return hashlib.sha256(text.encode()).hexdigest()


def git_commit():
    """HEAD commit of this repository, or "unknown" when git is not available."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                             text=True, check=True)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def make(params, out_dir):
    """Write the case directory `out_dir` for `params` and return the job.json dict.

    Raises NotImplementedError for an unknown geometry family and StageError (a ValueError that
    names the stage and lists every failure) if the geometry, the mesh-quality gate or the config
    fails. Nothing is written when the geometry or the mesh-quality gate fails.
    """
    if "family" not in params:
        raise ValueError("params need a 'family'")
    family = params["family"]
    if family not in BUILDERS:
        raise NotImplementedError(f"geometry family {family!r} is not implemented "
                                  f"(available: {sorted(BUILDERS)})")
    try:
        geometry, mesh = BUILDERS[family](params)
    except (ValueError, NotImplementedError, FileNotFoundError) as exc:
        raise StageError("geometry", [str(exc)]) from exc

    quality = mesh.quality()
    wanted = requested_first_cell(params)
    failures = quality_failures(quality, wanted)
    if failures:
        raise StageError("mesh_quality", failures,
                         "mesh quality gate failed: " + "; ".join(failures))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mesh.write_su2(out / "mesh.su2")
    mesh.write_markers(out / "mesh_markers.json")
    _dump(out / "geometry.json", geometry)
    _dump(out / "mesh_quality.json", {**quality, "pass": True, "failures": [],
                                      "requested_first_cell_m": wanted})
    _dump(out / "params.json", params)

    markers = json.loads((out / "mesh_markers.json").read_text())
    try:
        text = render(params, geometry, markers)
    except ValueError as exc:
        raise StageError("config", [str(exc)]) from exc
    (out / "case.cfg").write_text(text)

    job = {
        "case_id": case_id(params),
        "params": params,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mesh_fingerprint": mesh_fingerprint(out / "mesh.su2"),
        "mesh_bbox": mesh_bbox(out / "mesh.su2"),
        "config_sha256": config_sha256(out / "case.cfg"),
        "code_commit": git_commit(),
        "timeout_s": 2400,
        "max_cores": 2,
    }
    _dump(out / "job.json", job)
    return job

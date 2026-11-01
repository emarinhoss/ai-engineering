"""Build a case directory (mesh, markers, config, job.json) from a parameter dict.

Layout and file contents are described in docs/specs/01_interfaces.md ("Job directory").
Everything is a pure function of `params` except the file writes, the timestamp and the git commit.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cases.config import render
from geometry import wedge

REPO = Path(__file__).resolve().parent.parent

# Mesh-quality gate, 00_decisions.md section 6.
MIN_ANGLE_DEG = 40.0
FIRST_CELL_TOL = 0.10
MAX_GROWTH = 1.25
MAX_ASPECT = 5000.0

BUILDERS = {"wedge": wedge.build}


def canonical_json(params):
    """Sorted keys, no spaces; floats are written with Python's repr."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def case_id(params):
    """family-<first 10 hex digits of sha256 of the canonical params>."""
    digest = hashlib.sha256(canonical_json(params).encode()).hexdigest()
    return f"{params['family']}-{digest[:10]}"


def requested_first_cell(params):
    """{wall marker: first-cell height (m) that the mesh was asked for}."""
    if params["family"] == "wedge":
        return {"body": wedge.sizes(params.get("mesh_level", "medium"))["d0"]}
    raise NotImplementedError(f"geometry family {params['family']!r}")


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

    Raises NotImplementedError for a geometry family that does not exist yet and ValueError
    (listing every failure) if the mesh does not pass the quality gate. Nothing is written
    when the gate fails.
    """
    if "family" not in params:
        raise ValueError("params need a 'family'")
    family = params["family"]
    if family not in BUILDERS:
        raise NotImplementedError(f"geometry family {family!r} is not implemented "
                                  f"(available: {sorted(BUILDERS)})")
    geometry, mesh = BUILDERS[family](params)

    quality = mesh.quality()
    failures = quality_failures(quality, requested_first_cell(params))
    if failures:
        raise ValueError("mesh quality gate failed: " + "; ".join(failures))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mesh.write_su2(out / "mesh.su2")
    mesh.write_markers(out / "mesh_markers.json")
    _dump(out / "geometry.json", geometry)
    _dump(out / "mesh_quality.json", {**quality, "pass": True, "failures": [],
                                      "requested_first_cell_m": requested_first_cell(params)})
    _dump(out / "params.json", params)

    markers = json.loads((out / "mesh_markers.json").read_text())
    (out / "case.cfg").write_text(render(params, geometry, markers))

    job = {
        "case_id": case_id(params),
        "params": params,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mesh_sha256": sha256_file(out / "mesh.su2"),
        "config_sha256": sha256_file(out / "case.cfg"),
        "code_commit": git_commit(),
        "timeout_s": 2400,
        "max_cores": 2,
    }
    _dump(out / "job.json", job)
    return job

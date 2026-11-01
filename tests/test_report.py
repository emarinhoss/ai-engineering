"""Tests for postprocess/report.py.

The CLI and materialise tests run on run records committed in runs/dev and are skipped if one is
missing. The figure test uses synthetic arrays only.
"""

import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from postprocess import report, validation

REPO = Path(__file__).resolve().parents[1]
DATE = "2026-11-01"
RECORDS = [
    REPO / "runs/dev/2026-11-01_cylinder_v3_attempt3/cyl_coarse_ef03_cfl20",
    REPO / "runs/dev/2026-11-01_inlet_design_point/inlet88_navier_stokes",
    REPO / "runs/dev/2026-11-01_numerics/wedge-381c48d17f-tecplot",
]
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def run_cli(out, cases, task1_dir=None):
    cmd = [
        sys.executable,
        "-m",
        "postprocess.report",
        "--out",
        str(out),
        "--date",
        DATE,
        "--cases",
        *map(str, cases),
    ]
    if task1_dir is not None:
        cmd += ["--task1-dir", str(task1_dir)]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=False)


def verdicts(text):
    """Verdict cell of every row of the tolerance table (the legend line is not a table row)."""
    out = []
    for line in text.splitlines():
        if line.startswith("| ") and line.endswith(" |"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 6:
                out.append(cells[-1])
    return out


def test_cli_on_run_records(tmp_path):
    missing = [str(c) for c in RECORDS if not (c / "params.json").exists()]
    if missing:
        pytest.skip(f"run records not in the repository: {missing}")
    empty_task1 = tmp_path / "no_stored_reports"  # so that a PASS must come from the record checks
    empty_task1.mkdir()
    out = tmp_path / "out"
    proc = run_cli(out, RECORDS, task1_dir=empty_task1)
    assert proc.returncode == 0, proc.stderr
    md = out / f"{DATE}_report.md"
    assert md.exists()
    text = md.read_text()
    for token in ("V3", "V2b"):
        assert token in text
    assert "PASS" in verdicts(text), "no table row has the verdict PASS"
    assert len(list(out.glob(f"{DATE}_*.png"))) >= 3
    # every figure the markdown links to was written
    linked = re.findall(r"!\[[^\]]*\]\(([^)]+\.png)\)", text)
    assert linked
    assert all((out / name).exists() for name in linked)


def test_materialise_regenerates_mesh_and_keeps_the_record(tmp_path):
    record = RECORDS[0]
    if not (record / "params.json").exists():
        pytest.skip(f"run record not in the repository: {record}")
    before = sorted(p.name for p in record.iterdir())
    dest = tmp_path / "staged"
    info = report.materialise(record, dest)
    assert info["mesh"] == "regenerated"
    assert (dest / "mesh.su2").exists() and (dest / "mesh_markers.json").exists()
    assert (dest / "history.csv").exists()  # gzip unpacked
    assert sorted(p.name for p in record.iterdir()) == before  # the record is only read
    for name in report.RECORD_COPIES_KEPT:
        if (record / name).exists():
            assert (dest / name).read_bytes() == (record / name).read_bytes()


def test_stored_colab_reports_fill_v1_and_v2a(tmp_path):
    task1 = REPO / "runs/task1"
    if not (task1 / "v1_oblique_shock.json").exists():
        pytest.skip("runs/task1 JSON reports not in the repository")
    rows = report.stored_rows(task1)
    by_id = {}
    for r in rows:
        by_id.setdefault(r["id"], []).append(r)
    assert [r["verdict"] for r in by_id["V1"]] == ["PASS", "PASS", "PASS"]
    assert by_id["V2a"][0]["verdict"] == "REPORT"
    assert "runs/task1/v2a.json" in by_id["V2a"][0]["measured"]


def test_empty_case_directory(tmp_path):
    empty = tmp_path / "empty_case"
    empty.mkdir()
    out = tmp_path / "out"
    proc = run_cli(out, [empty])
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    text = (out / f"{DATE}_report.md").read_text()
    assert "not run" in text


def test_figures_from_synthetic_data(tmp_path):
    levels = [
        {"recovery_total": 0.900, "q_peak_W_m2": 3.00e5},
        {"recovery_total": 0.915, "q_peak_W_m2": 3.10e5},
        {"recovery_total": 0.9155, "q_peak_W_m2": 3.12e5},
    ]
    result = validation.grid_study(levels, keys=("recovery_total", "q_peak_W_m2"))
    entries = [
        {
            "label": "synthetic",
            "family": "inlet2r",
            "tol": validation.GRID_TOL,
            "levels": [("coarse", "c"), ("medium", "m"), ("fine", "f")],
            "result": result,
        }
    ]
    report.plot_grid(entries, tmp_path / "grid.png")

    s = np.linspace(0.0, 1.0, 50)
    ratio = 0.93 - 0.02 * np.exp(-(((s - 0.5) / 0.2) ** 2))
    report.plot_throat([("synthetic", s, ratio)], 0.9316, tmp_path / "throat.png")

    x = np.linspace(0.1, 0.2, 40)
    q = 1e5 * np.exp(-(((x - 0.17) / 0.01) ** 2))
    report.plot_inlet_heat(
        [("synthetic", x, q)], [("synthetic", 0.17, 1e5)], 0.1, tmp_path / "heat.png"
    )
    for name in ("grid.png", "throat.png", "heat.png"):
        assert (tmp_path / name).read_bytes()[:8] == PNG_MAGIC

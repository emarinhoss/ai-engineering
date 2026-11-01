"""Validation and budget summary of the Colab run records (runs/val, runs/pool) from their result.json.

The large files of a Colab run (surface_flow.dat, history.csv, log.txt) stay on Drive; the record
in the repo holds params, geometry, config, mesh quality and result.json with the metrics that
postprocess.metrics.compute produced on Colab. This script reads only those records and writes a
Markdown report. Checks that need the surface file (V1, V2a, V2b, the V4e area average) are not
redone here; they are in the Task 1 README and in the development report.

    python -m postprocess.colab_summary --out docs/validation/2026-11-01_colab_records.md
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from physics.atmosphere import state
from physics.heating import fay_riddell_cylinder
from postprocess.validation import GRID_TOL, grid_study

REPO = Path(__file__).resolve().parent.parent
TOL = {"V3": 0.15, "V3 grid": 0.05, "V4e": 0.02, "X1": 0.005}
LEVELS = ("coarse", "medium", "fine")


def load(root):
    """[(case directory, result.json dict)] for every record below root that has a result.json."""
    out = []
    for result in sorted(Path(root).glob("*/result.json")):
        out.append((result.parent, json.loads(result.read_text())))
    return out


def errors(root):
    """[(case directory, error.json dict)] for the failed jobs below root."""
    return [(p.parent, json.loads(p.read_text())) for p in sorted(Path(root).glob("*/error.json"))]


def verdict(ok):
    return "PASS" if ok else "FAIL"


def pct(x):
    return f"{x:+.2%}"


def by_level(records, family, solver="NAVIER_STOKES"):
    """{mesh_level: result} for one family and solver, keeping the first record per level."""
    out = {}
    for _, r in records:
        p = r["params"]
        if p["family"] == family and p["solver"] == solver:
            out.setdefault(p["mesh_level"], r)
    return out


def v3_rows(val):
    cyl = by_level(val, "cylinder")
    if not cyl:
        return ["No cylinder record."]
    lines = ["| level | cells | q_stag [W/m^2] | Fay-Riddell [W/m^2] | error | verdict |", "|---|---|---|---|---|---|"]
    q = {}
    for level in LEVELS:
        if level not in cyl:
            continue
        r, p = cyl[level], cyl[level]["params"]
        fs = state(p["altitude_km"])
        fr = fay_riddell_cylinder(p["mach"], fs["T"], fs["p"], p["T_wall_K"], p["radius_m"])["q"]
        q[level] = r["metrics"]["q_stag_W_m2"]
        err = q[level] / fr - 1.0
        v = verdict(abs(err) <= TOL["V3"]) if level == "fine" else "REPORT"
        lines.append(f"| {level} | {r['mesh']['cells']} | {q[level]:.4g} | {fr:.4g} | {pct(err)} | {v} |")
    if "medium" in q and "fine" in q:
        change = q["fine"] / q["medium"] - 1.0
        lines.append("")
        lines.append(f"Grid change medium -> fine: {pct(change)} (tolerance {TOL['V3 grid']:.0%}): "
                     f"{verdict(abs(change) <= TOL['V3 grid'])}.")
    lines.append("")
    lines.append("The stand-off distance (Billig) is not in these records: the Colab flow.dat zone could not "
                 "be parsed (note kept in result.json); stand-off is report-only in the spec.")
    return lines


def v4m_rows(val):
    inlet = by_level(val, "inlet2r")
    levels = [lv for lv in LEVELS if lv in inlet]
    if len(levels) < 2:
        return ["Fewer than two laminar inlet levels recorded."]
    study = grid_study([inlet[lv]["metrics"] for lv in levels])
    if "error" in study:
        return [f"grid_study failed: {study['error']}"]
    lines = ["| quantity | " + " | ".join(f"{lv} ({inlet[lv]['mesh']['cells']} cells)" for lv in levels)
             + " | medium -> fine | tolerance | verdict |", "|---|" + "---|" * (len(levels) + 3)]
    for key, row in study["table"].items():
        vals = " | ".join(f"{v:.5g}" for v in row["values"])
        change = row["rel_change"][-1]
        lines.append(f"| {key} | {vals} | {pct(change)} | {GRID_TOL[key]:.0%} | {verdict(row['within_tol'])} |")
        if row["order"] is not None:
            lines.append(f"| {key}: observed order, Richardson extrapolation | "
                         + " | ".join("" for _ in levels) + f" {row['order']:.2f}, {row['extrapolated']:.5g} | | |")
    return lines


def v4e_rows(val):
    lines = []
    for d, r in val:
        p = r["params"]
        if p["family"] != "inlet2r" or p["solver"] != "EULER":
            continue
        got, ref = r["metrics"]["recovery_throat"], r["geometry"]["recovery_2shock_inviscid"]
        err = got / ref - 1.0
        lines.append(f"| {d.name} | {p['theta1_deg']:g}/{p['theta2_deg']:g} {p['mesh_level']} | {got:.4f} | {ref:.4f} "
                     f"| {pct(err)} | {TOL['V4e']:.0%} | {verdict(abs(err) <= TOL['V4e'])} |")
    if not lines:
        return ["No Euler inlet record."]
    note = ("This is the mass-flux-weighted throat recovery of result.json against the inviscid two-shock "
            "value. The spec's V4e row (area average, validation.inlet_check) needs the surface file and is "
            "in the development report.")
    header = ["| case | design, mesh | mass-flux p0/p0_inf at the throat | two-shock inviscid | error | tolerance | verdict |",
              "|---|---|---|---|---|---|---|"]
    return header + lines + ["", note]


def x1_rows(records):
    lines = []
    for d, r in records:
        m = r["metrics"]
        if m.get("su2_crosscheck_pass") is None:
            continue
        rel = m["su2_avg_totalpress_Pa"] / (m["recovery_throat"] * m["p0_inf_Pa"]) - 1.0
        lines.append(f"| {d.name} | {rel:+.2e} | {verdict(bool(m['su2_crosscheck_pass']))} |")
    if not lines:
        return ["No record with an AVG_TOTALPRESS cross-check."]
    return ["| case | SU2 AVG_TOTALPRESS vs mass average | verdict (tolerance 0.5%) |", "|---|---|---|"] + lines


def budget_rows(records, failed):
    lines = ["| case | family | design | mesh | cells | iterations | status | wall time [s] | ranks |",
             "|---|---|---|---|---|---|---|---|---|"]
    for d, r in records:
        p, run = r["params"], r["run"]
        design = f"{p.get('theta1_deg', '-')}/{p.get('theta2_deg', '-')}" if "theta1_deg" in p else "-"
        lines.append(f"| {d.name} | {p['family']} | {design} | {p['mesh_level']} | {r['mesh']['cells']} | "
                     f"{run['iterations']} | {r['convergence']['status']} | {run['wall_time_s']:.0f} | "
                     f"{r['solver']['n_cores']} |")
    for d, e in failed:
        p = json.loads((d / "params.json").read_text()) if (d / "params.json").exists() else {}
        g = json.loads((d / "geometry.json").read_text()) if (d / "geometry.json").exists() else {}
        design = f"{p.get('theta1_deg', '-')}/{p.get('theta2_deg', '-')}" if "theta1_deg" in p else "-"
        lines.append(f"| {d.name} | {p.get('family', '-')} | {design} | {p.get('mesh_level', '-')} | "
                     f"{g.get('cells', '-')} | - | failed: {e['reason']} | - | - |")
    return lines


def pool_section(pool, failed):
    n = len(pool)
    lines = [f"{n} pool results recorded, {len(failed)} failures recorded."]
    if n:
        walls = [r["run"]["wall_time_s"] for _, r in pool]
        conv = sum(r["convergence"]["status"] == "converged" for _, r in pool)
        lines.append(f"{conv} of {n} converged to the residual target; wall time per case "
                     f"{min(walls):.0f} to {max(walls):.0f} s, mean {sum(walls) / n:.0f} s on 4 MPI ranks.")
    return lines


def build(val_dir, pool_dir, today):
    val, pool = load(val_dir), load(pool_dir)
    failed = errors(val_dir) + errors(pool_dir)
    intro = (f"Generated by `python -m postprocess.colab_summary` from `{val_dir.relative_to(REPO) if val_dir.is_relative_to(REPO) else val_dir}` and `{pool_dir.relative_to(REPO) if pool_dir.is_relative_to(REPO) else pool_dir}` "
             "(result.json written by the Colab worker, metrics from postprocess.metrics.compute on Colab). "
             "Every number below is read from a committed record; nothing is recomputed from flow fields.")
    parts = [f"# Colab run records, {today}", "", intro, "",
             "## V3: stagnation heat flux on the R = 10 mm cylinder against Fay-Riddell", ""] + v3_rows(val) + [
             "", "## V4m: grid study of the 8/8 laminar inlet", ""] + v4m_rows(val) + [
             "", "## V4e (metrics form): Euler inlet throat recovery against the two-shock value", ""] + v4e_rows(val) + [
             "", "## X1: SU2's own AVG_TOTALPRESS against the mass-averaged throat total pressure", ""] + x1_rows(val + pool) + [
             "", "## Pool", ""] + pool_section(pool, failed) + [
             "", "## Runs and budget", ""] + budget_rows(val + pool, failed)
    return "\n".join(parts) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--val", default=REPO / "runs" / "val")
    ap.add_argument("--pool", default=REPO / "runs" / "pool")
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    args = ap.parse_args(argv)
    text = build(Path(args.val), Path(args.pool), args.date)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()

"""Full info-gap study of other cells of the robust re-size (owner ruling B-2b), next to its winner.

    python -m measurement.bands_cells --out runs/task12/stage3/2026-11-26/m250_bands_cells --cells "13,8;13,9"
    python -m measurement.bands_cells --out ... --report docs/validation/2026-11-26_task12_m250_bands_cells.md --report-only

The re-size (measurement/robust_sizing.py --curve-targets, SOURCE below) wrote the design record of its winner
only; of every other candidate it kept the row (W/S, A, the converged L_sized, W0, fuel, ...). A cell named here
is sized again by the same function at the row's L_sized (no new bisection), and the result must equal the row;
then it gets what the winner got: the endurance and cliff mode scans (robust_sizing.mode_study), the mode
searches at the target (mode_worst_at) and the full measurement.info_gap.study. The winner is read from its record.
Nothing is tuned and no cell is recommended.
"""
# ruff: noqa: ISC004  (the report text is a list of adjacent string pieces, as in info_gap)
import argparse
import json
import sys
import time
from pathlib import Path

from conceptual import uav
from measurement import info_gap
from measurement import robust_sizing as rs

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "runs/task12/stage3/2026-11-26/m250_bands_resize"
POWER, H_T = 450.0, 1.05
WINNER = SOURCE / "P450" / "h1.05"
MATCH_REL = 1e-9                  # the re-sized W0 and fuel against the recorded row


def source_row(ws, a, curve=None):
    """The candidate row of cell (W/S, A) in the last iteration of the re-size; it must be a compliant design."""
    curve = curve or json.loads((SOURCE / "curve.json").read_text())
    cell = curve["per_P"][f"{POWER:g}"][f"{H_T:.2f}"]
    rows = [r for r in cell["iterations"][-1]["candidates"] if r["W_S"] == ws and r["A"] == a]
    if len(rows) != 1:
        raise ValueError(f"W/S {ws:g} A {a:g}: {len(rows)} rows in the last iteration of the re-size, expected 1")
    row = rows[0]
    if not row["ok"] or row["failed"]:
        raise ValueError(f"W/S {ws:g} A {a:g} is not a compliant design in the re-size: {row['status'] or row['failed']}")
    return row


def size_cell(row):
    """The design record of the row, sized again at its L_sized; raises if W0 or fuel differ from the row."""
    L = row["L_sized_h"]
    _, _, rec = rs.sized_aircraft_guess(row["P_hp"], row["W_S"], row["A"], L, rs.first_guess(row["P_hp"], L), rs.VC_RULE)
    for k in ("W0_lb", "fuel_lb"):
        if abs(rec[k] - row[k]) > MATCH_REL * row[k]:
            raise ValueError(f"re-sized {k} {rec[k]!r} is not the recorded row's {row[k]!r}")
    return rec


def cell_name(ws, a):
    return f"ws{ws:g}_a{a:g}"


def run_cell(out, ws, a, processes, log=print):
    t0 = time.time()
    row = source_row(ws, a)
    rec = size_cell(row)
    folder = Path(out) / cell_name(ws, a)
    path = rs.write_record_rec(row, folder, rec)
    need = uav.load_ledger()[0]["r5_robust_hours"]
    modes = rs.mode_study(path, need)[0]
    worst = rs.mode_worst_at(path, need, H_T)
    ig = info_gap.study(str(path), processes=processes)
    ig["inputs"] = rs.inputs_block("full info_gap.study of a cell of the re-size; worst-case search is the corrected one")
    (folder / "info_gap.json").write_text(json.dumps(info_gap._json_safe(ig), indent=1, default=float))
    result = {"inputs": rs.inputs_block("cell of the re-size, sized again at the recorded L_sized"),
              "source": str(SOURCE.relative_to(REPO)), "source_curve_sha256": rs.sha256(SOURCE / "curve.json"),
              "h_T": H_T, "need_h": need, "design": rs.summary_of(row), "modes": modes, "worst_at_target": worst,
              "command": "python -m measurement.bands_cells " + " ".join(sys.argv[1:]), "runtime_s": time.time() - t0}
    (folder / "cell_result.json").write_text(json.dumps(info_gap._json_safe(result), indent=1, default=float))
    hh = ig["h_hat"]
    log(f"W/S {ws:g} A {a:g}: R5 guarantee {hh['R5_guarantee']['h_hat']:.4f} (endurance {modes['endurance']['h_hat']:.4f}, "
        f"cliff {modes['cliff']['h_hat']:.4f}) R7 {hh['R7']['h_hat']:.4f} ({time.time() - t0:.0f} s)", flush=True)


def summarise(folder):
    """The table values of one cell from its record folder (a cell of this tool, or the re-size winner)."""
    folder = Path(folder)
    d = json.loads((folder / "design_pusher.json").read_text())
    row = json.loads((folder / "robust_candidate.json").read_text())
    ig = json.loads((folder / "info_gap.json").read_text())
    res = json.loads((folder / ("cell_result.json" if (folder / "cell_result.json").exists() else "target_result.json")).read_text())
    hh = {k: v["h_hat"] for k, v in ig["h_hat"].items()}
    at1 = next(c for c in ig["worst_case_curve"] if c["h"] == 1.0)
    modes, worst = res["modes"], res["worst_at_target"]
    return {"folder": str(folder.relative_to(REPO)), "commit": ig["inputs"]["commit"],
            "W_S": row["W_S"], "A": row["A"], "W0_lb": row["W0_lb"], "fuel_lb": row["fuel_lb"], "We_lb": row["We_lb"],
            "L_sized_h": row["L_sized_h"], "span_ft": row["span_ft"], "power_margin": row["power_margin"],
            "vc_kt": d["V_c_eas_kt"]["sea_level"], "h_hat": hh,
            "R7_binding": "take-off" if hh["TO"] <= hh["LD"] else "landing",
            "mode_endurance": modes["endurance"]["h_hat"], "mode_cliff": modes["cliff"]["h_hat"],
            "binding_mode": modes["binding_mode"], "target_holds": hh["R5_guarantee"] >= H_T,
            "nominal": ig["nominal"], "w0_check_lb": ig["w0_check"]["difference_lb"],
            "at_h1": {"R5_hours": at1["R5"]["hours"], "takeoff_ft": at1["TO"]["takeoff_ft"], "landing_ft": at1["LD"]["landing_ft"],
                      "cliff_ratio": modes["cliff"]["worst_at_h1"]["transit_ratio"]},
            "at_target": {"endurance_hours": worst["endurance"]["hours"], "cliff_ratio": worst["cliff"]["transit_ratio"]},
            "worst_moved_h1": {"endurance": modes["endurance"]["worst_at_h1"]["moved"],
                               "cliff": modes["cliff"]["worst_at_h1"]["moved"],
                               "TO": at1["TO"]["moved"], "LD": at1["LD"]["moved"]}}


def parse_cells(text):
    return [tuple(float(x) for x in c.split(",")) for c in text.split(";")]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cells", help='cells to run, "W/S,A;W/S,A"')
    ap.add_argument("--processes", type=int, default=2, help="processes of info_gap.study (the re-size used 2)")
    ap.add_argument("--report")
    ap.add_argument("--report-only", action="store_true",
                    help="write OUT/summary.json and the report from the cell folders in OUT and the winner's record")
    a = ap.parse_args(argv)
    out = (REPO / a.out).resolve()
    if not a.report_only:
        code_dirty = info_gap.git_dirty()
        if code_dirty:
            raise SystemExit(f"uncommitted changes in conceptual, measurement or data: {code_dirty}")
        rs.use_engine_as_is(True)
        out.mkdir(parents=True, exist_ok=True)
        for ws, a_ in parse_cells(a.cells):
            run_cell(out, ws, a_, a.processes)
        return
    cells = {"winner": summarise(WINNER)}
    for folder in sorted(p for p in out.iterdir() if (p / "cell_result.json").exists()):
        cells[folder.name] = summarise(folder)
    res = {"source": str(SOURCE.relative_to(REPO)), "h_T": H_T, "cells": cells}
    (out / "summary.json").write_text(json.dumps(info_gap._json_safe(res), indent=1, default=float))
    if a.report:
        Path(a.report).write_text(report_text(res, str(out.relative_to(REPO))))


# ---- the note ----------------------------------------------------------------------------------------
def _moved(m):
    return ", ".join(f"`{k}` {v:.4g}" for k, v in m.items())


def report_text(res, folder):
    cells = list(res["cells"].values())
    head = [f"W/S {c['W_S']:g}, A {c['A']:g}" for c in cells]
    head[0] += " (re-size winner)"

    def line(label, f):
        return f"| {label} | " + " | ".join(f(c) for c in cells) + " |"

    hT = res["h_T"]
    lines = [
        "# Task 12: the re-sized cell and two alternatives under both bands (ruling B-2b)", "",
        f"Every number is read from `{folder}/summary.json`, which is extracted from the record folders named in the "
        "table (`info_gap.json`, `cell_result.json` or `target_result.json`, `robust_candidate.json`, `design_pusher.json`). "
        "Generated by `python -m measurement.bands_cells --report-only`. No cell is recommended here; the owner chooses.", "",
        "## What was run", "",
        f"- The re-size `{res['source']}` (target h_T {hT:g}, composite band `saving` and empty-weight band acting, 450 shp "
        "M250-B17F as is) recorded the design of its lightest cell only. The other cells here are compliant candidates of "
        "its last iteration: each is sized again by the same function at the L_sized the re-size converged to (no new "
        "bisection) and the result is checked against the recorded row (W0 and fuel equal to 1e-9).",
        "- Each then gets what the winner got: the endurance and transit-cliff mode scans, the mode searches at h_T and the "
        "full `measurement.info_gap.study` (seed and sample count in each `info_gap.json`). The winner's column is its own "
        "record, not re-run.",
        "- The corner sets of the re-size were grown from the worst points of the designs it selected (W/S 17 A 7, then "
        "W/S 14 A 8). An alternative's L_sized was bisected against those sets, not against its own mode searches; "
        "whether its guarantee reaches the target is therefore a result below, not a construction.", "",
        "## Side by side", "",
        "| | " + " | ".join(head) + " |", "|---|" + "---|" * len(cells),
        line("record", lambda c: f"`{c['folder']}`"),
        line("commit of the study", lambda c: f"`{c['commit'][:7]}`"),
        line("W0 (lb)", lambda c: f"{c['W0_lb']:.0f}"),
        line("fuel (lb)", lambda c: f"{c['fuel_lb']:.0f}"),
        line("empty weight (lb)", lambda c: f"{c['We_lb']:.0f}"),
        line("L_sized (h)", lambda c: f"{c['L_sized_h']:.2f}"),
        line("span (ft)", lambda c: f"{c['span_ft']:.1f}"),
        line("V_C (kt EAS)", lambda c: f"{c['vc_kt']:g}"),
        line("power margin", lambda c: f"{100 * c['power_margin']:.1f} %"),
        line("R5 guarantee horizon (full study)", lambda c: f"**{c['h_hat']['R5_guarantee']:.4f}**"),
        line(f"h_T {hT:g} holds", lambda c: "yes" if c["target_holds"] else "**NO**"),
        line("endurance mode horizon", lambda c: f"{c['mode_endurance']:.4f}"),
        line("cliff mode horizon", lambda c: f"{c['mode_cliff']:.4f}"),
        line("R7 horizon", lambda c: f"{c['h_hat']['R7']:.4f}"),
        line("R7 binding leg (take-off / landing horizon)",
             lambda c: f"{c['R7_binding']} ({c['h_hat']['TO']:.4f} / {c['h_hat']['LD']:.4f})"),
        line("worst endurance at h = 1 (h)", lambda c: f"{c['at_h1']['R5_hours']:.3f}"),
        line(f"worst endurance at h_T {hT:g} (h)", lambda c: f"{c['at_target']['endurance_hours']:.3f}"),
        line("worst cliff ratio at h = 1", lambda c: f"{c['at_h1']['cliff_ratio']:.4f}"),
        line(f"worst cliff ratio at h_T {hT:g}", lambda c: f"{c['at_target']['cliff_ratio']:.4f}"),
        line("worst take-off / landing at h = 1 (ft)", lambda c: f"{c['at_h1']['takeoff_ft']:.0f} / {c['at_h1']['landing_ft']:.0f}"),
        line("nominal take-off / landing (ft)", lambda c: f"{c['nominal']['takeoff_ft']:.0f} / {c['nominal']['landing_ft']:.0f}"),
        line("nominal 8 h horizon (R5)", lambda c: f"{c['h_hat']['R5']:.4f}"),
        line("nominal hours on station", lambda c: f"{c['nominal']['R5_hours']:.3f}"),
        "",
        "R5 guarantee: largest h at which every member of U(h) still gives 3.5 h on station (a member that cannot fly counts "
        "as 0 h). Endurance and cliff: the two failure modes of that guarantee. Cliff ratio: shaft power needed over power "
        "available on the worst transit sub-step (above 1: the mission cannot be flown). R7: the smaller of the take-off and "
        "landing horizons against 2,500 ft. Nominal 8 h horizon: largest h at which every member still gives the full 8 h.", "",
        "## Differences from the winner (same records)", ""]
    w = cells[0]
    for c, h in zip(cells[1:], head[1:]):
        lines.append(f"- {h}: W0 {c['W0_lb'] - w['W0_lb']:+.0f} lb, fuel {c['fuel_lb'] - w['fuel_lb']:+.0f} lb, span "
                     f"{c['span_ft'] - w['span_ft']:+.1f} ft, R5 guarantee {c['h_hat']['R5_guarantee'] - w['h_hat']['R5_guarantee']:+.4f}, "
                     f"cliff horizon {c['mode_cliff'] - w['mode_cliff']:+.4f}, R7 horizon {c['h_hat']['R7'] - w['h_hat']['R7']:+.4f}, "
                     f"worst endurance at h = 1 {c['at_h1']['R5_hours'] - w['at_h1']['R5_hours']:+.3f} h.")
    lines += ["", "## Worst points at h = 1 (moved variables)", ""]
    for c, h in zip(cells, head):
        lines.append(f"**{h}**")
        lines.append("")
        for key, label in (("endurance", "endurance"), ("cliff", "cliff"), ("TO", "take-off"), ("LD", "landing")):
            lines.append(f"- {label}: {_moved(c['worst_moved_h1'][key])}.")
        lines.append("")
    lines += ["## What this does not cover", "",
              "- Only these cells have a full study. The grid of the re-size is 1 lb/ft^2 in W/S and 1 in A; cells between "
              "the levels were not sized.",
              "- The exclusions of the info-gap study apply (listed in each `info_gap.json`).",
              "- Stage 3, VSPAERO, V-n and the compliance table have not been run on any of these designs.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()

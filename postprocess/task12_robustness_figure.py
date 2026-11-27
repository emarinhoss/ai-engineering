"""Robustness curves of the Task 12 baseline (spec 7.3, review item GB-7), plotted from the committed records.

Only stored points are plotted; nothing is interpolated or recomputed. Straight lines join the stored
points and say nothing about values between them.
    python -m postprocess.task12_robustness_figure --out-dir runs/task12/stage3/2026-11-27/robustness_figure_ws13a8

Stored in info_gap.json: the worst points at the R5, take-off and landing horizons, and `worst_case_curve` (8 horizons, 0 to 3; worst hours on station, take-off and landing
over 50 ft at each) and `h_hat.R5_guarantee.worst_at_h_hat` (the worst case at the horizon of the R5 guarantee).
Stored in cell_result.json: the transit-cliff ratio at three horizons only (h = 1, h_T, and its own horizon).
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8"
INFO_GAP = BASE / "info_gap.json"
CELL = BASE / "cell_result.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_data(info_gap_path=INFO_GAP, cell_path=CELL):
    """The points that the figure plots, read from the two records."""
    ig = json.loads(Path(info_gap_path).read_text())
    cell = json.loads(Path(cell_path).read_text())
    curve = ig["worst_case_curve"]
    r5_flyable = [[p["h"], p["R5"]["hours"]] for p in curve if p["R5"]["not_flyable"] is None]
    r5_not_flyable = [p["h"] for p in curve if p["R5"]["not_flyable"] is not None]
    g = ig["h_hat"]["R5_guarantee"]["worst_at_h_hat"]
    r5_flyable.append([g["h"], g["hours"]])
    r5_flyable.sort()
    takeoff = [[p["h"], p["TO"]["takeoff_ft"]] for p in curve if math.isfinite(float(p["TO"]["takeoff_ft"]))]
    landing = [[p["h"], p["LD"]["landing_ft"]] for p in curve if math.isfinite(float(p["LD"]["landing_ft"]))]
    # the worst points stored at the R7 horizons, so the lines do not cut the limit early between h = 1 and 1.5
    to_hat = ig["h_hat"]["TO"]["worst_at_h_hat"]
    ld_hat = ig["h_hat"]["LD"]["worst_at_h_hat"]
    takeoff = sorted(takeoff + [[to_hat["h"], to_hat["takeoff_ft"]]])
    landing = sorted(landing + [[ld_hat["h"], ld_hat["landing_ft"]]])
    modes = cell["modes"]["cliff"]
    cliff = [[1.0, modes["worst_at_h1"]["transit_ratio"]],
             [cell["h_T"], cell["worst_at_target"]["cliff"]["transit_ratio"]],
             [modes["h_hat"], modes["worst_at_h_hat"]["transit_ratio"]]]
    return {
        "r5_hours_flyable": r5_flyable,
        "r5_not_flyable_h": r5_not_flyable,
        "takeoff_ft": takeoff,
        "takeoff_unbounded_h": [p["h"] for p in curve if not math.isfinite(float(p["TO"]["takeoff_ft"]))],
        "landing_ft": landing,
        "landing_unbounded_h": [p["h"] for p in curve if not math.isfinite(float(p["LD"]["landing_ft"]))],
        "cliff_ratio": cliff,
        "requirement_hours": cell["need_h"],
        "h_T": cell["h_T"],
        "field_length_limit_ft": ig["h_hat"]["TO"]["limit"],
    }


def plot(d, path):
    fig, ax = plt.subplots(1, 3, figsize=(14, 5))
    a = ax[0]
    a.plot(*zip(*d["r5_hours_flyable"]), "o-", color="tab:blue", label="worst-case endurance (stored points)")
    a.axhline(d["requirement_hours"], color="tab:red", ls="--", label=f"requirement {d['requirement_hours']} h")
    a.axvline(d["h_T"], color="tab:green", ls=":", label=f"target h_T {d['h_T']}")
    a.set_xlabel("horizon of uncertainty h")
    a.set_ylabel("worst hours on station (R5)")
    a.set_title("R5 endurance")
    if d["r5_not_flyable_h"]:
        a.set_xlabel("horizon of uncertainty h\nnot flyable (stored as 0 h) at h = "
                     + ", ".join(f"{h:g}" for h in d["r5_not_flyable_h"]) + " (off the axis)")
    a.legend(fontsize=8)
    b = ax[1]
    b.plot(*zip(*d["cliff_ratio"]), "s", color="tab:purple", label="transit ratio (3 stored points)")
    b.axhline(1.0, color="tab:red", ls="--", label="limit 1.0")
    b.axvline(d["h_T"], color="tab:green", ls=":", label=f"target h_T {d['h_T']}")
    b.set_xlabel("horizon of uncertainty h")
    b.set_ylabel("worst transit-cliff ratio (R5)")
    b.set_title("Transit cliff: three stored points only")
    b.legend(fontsize=8)
    c = ax[2]
    c.plot(*zip(*d["takeoff_ft"]), "o-", color="tab:orange", label="take-off over 50 ft")
    c.plot(*zip(*d["landing_ft"]), "^-", color="tab:brown", label="landing over 50 ft")
    c.axhline(d["field_length_limit_ft"], color="tab:red", ls="--", label=f"limit {d['field_length_limit_ft']:g} ft")
    c.set_xlabel("horizon of uncertainty h")
    c.set_ylabel("worst field length (ft)")
    c.set_title("R7 take-off and landing")
    unb = [("take-off", d["takeoff_unbounded_h"]), ("landing", d["landing_unbounded_h"])]
    txt = "; ".join(f"{n} unbounded at h = " + ", ".join(f"{h:g}" for h in hs) for n, hs in unb if hs)
    if txt:
        c.set_xlabel("horizon of uncertainty h\n" + txt + "\n(not plotted)")
    c.legend(fontsize=8)
    fig.suptitle("W/S 13, A 8 baseline: worst case against horizon (lines join stored points only)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", required=True)
    out = Path(p.parse_args().out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d = build_data()
    plot(d, out / "robustness.png")
    meta = {"figure": "robustness.png", "sources": {str(f.relative_to(ROOT)): sha256(f) for f in (INFO_GAP, CELL)},
            "note": "Only stored points; cliff ratio is stored at three horizons, not as a curve.", "data": d}
    (out / "plotted_data.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()

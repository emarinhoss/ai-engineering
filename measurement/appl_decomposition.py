"""Decomposition of the App. L baseline's +43 lb take-off weight against the flat-propeller baseline (review S3A-1).

    python -m measurement.appl_decomposition \
        --old runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05 \
        --new runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05 \
        --out runs/task12/stage3/2026-11-26/appl_decomposition/decomposition.json

Reads the two records (design_pusher.json and target_result.json in each folder) and rebuilds each design with
measurement.info_gap.Built, the code that produced the worst case. It reports:
  1. the split of W0, fuel, empty weight and sized loiter between the two records (read from target_result.json);
  2. at each design's worst endurance point (the record's own moved values, loiter time as the record's hours),
     the fuel burned in each mission segment, the mean propeller efficiency of each leg and the climb inputs,
     with the propeller as in the record and with the other propeller swapped in (the new design with the old
     flat efficiency low end, the old design with the disk);
  3. the same at nominal for the new design, loiter at its sized time.
Nothing is tuned. The efficiencies and climb inputs are read by wrapping the sizing functions that receive them,
so they are the numbers the mission code used."""
import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

from conceptual import sizing, uav
from conceptual.units import KT
from measurement import info_gap as ig
from measurement import stage3_perf as sp

REPO = Path(__file__).resolve().parents[1]


def case(built, theta, loiter_h):
    """One build of `built` at theta with loiter_h: hours on station at theta, W0, segment fuel (weight lost, lb,
    before the reserve factor), fuel with reserve, mean propeller efficiency of each leg, and the climb inputs."""
    seen = {"cruise": [], "loiter": [], "climb": {}}
    orig = (sizing.cruise_fraction_prop, sizing.loiter_fraction_prop, sizing.climb_fraction_energy, sizing.equivalent_tsfc)

    def cruise(dist, cbhp, eta, LD):
        seen["cruise"].append(eta)
        return orig[0](dist, cbhp, eta, LD)

    def loiter(t, V, cbhp, eta, LD):
        seen["loiter"].append(eta)
        return orig[1](t, V, cbhp, eta, LD)

    def climb(C, dhe, V, d_t):
        f = orig[2](C, dhe, V, d_t)
        seen["climb"].update(climb_speed_kt=V / KT, drag_over_thrust=d_t, climb_fraction=f)
        return f

    def tsfc(c, V, eta):
        seen["climb"].update(eta_mid_altitude=eta, cbhp_climb=c)
        return orig[3](c, V, eta)

    sizing.cruise_fraction_prop, sizing.loiter_fraction_prop = cruise, loiter
    sizing.climb_fraction_energy, sizing.equivalent_tsfc = climb, tsfc
    try:
        b, _ = built.build(theta, loiter_h)
    finally:
        sizing.cruise_fraction_prop, sizing.loiter_fraction_prop, sizing.climb_fraction_energy, sizing.equivalent_tsfc = orig
    n = len(seen["cruise"]) // 2
    mean = lambda xs: sum(xs) / len(xs)
    return {"loiter_h": loiter_h, "W0_lb": built.w0_for(theta), "fuel_with_reserve_lb": b["fuel"],
            "segment_fuel_lb": {r[0]: r[1] - r[2] for r in b["mission"] if r[0] not in ("landing",)},
            "mean_eta": {"cruise_out": mean(seen["cruise"][:n]), "loiter": mean(seen["loiter"]),
                         "cruise_back": mean(seen["cruise"][n:])},
            "climb": dict(seen["climb"])}


def read(folder):
    folder = Path(folder)
    return (json.loads((folder / "design_pusher.json").read_text()),
            json.loads((folder / "target_result.json").read_text()))


def split(rec_old, rec_new):
    keys = ("W0_lb", "fuel_lb", "We_lb", "L_sized_h", "W0_at_8h_lb")
    out = {}
    for k in keys:
        o, n = rec_old["design_row"][k], rec_new["design_row"][k]
        out[k] = {"old": o, "new": n, "change": n - o}
    for tag, r in (("old", rec_old), ("new", rec_new)):
        row = r["design_row"]
        out.setdefault("W0_minus_fuel_minus_We_lb", {})[tag] = row["W0_lb"] - row["fuel_lb"] - row["We_lb"]
    return out


def run(old_dir, new_dir):
    d_old, t_old = read(old_dir)
    d_new, t_new = read(new_dir)
    b_old, b_new = ig.Built(Path(old_dir) / "design_pusher.json"), ig.Built(Path(new_dir) / "design_pusher.json")
    w_old, w_new = (t["worst_at_target"]["endurance"] for t in (t_old, t_new))
    th_old, th_new = dict(w_old["moved"]), dict(w_new["moved"])
    eta_low = th_old["eta_p"]                       # the old record's flat efficiency at its worst endurance point
    f_low = th_new["prop_real_to_ideal"]            # the new record's disk factor at its worst endurance point
    new_flat = {k: v for k, v in th_new.items() if k != "prop_real_to_ideal"}
    new_flat.update(propeller_model="flat", eta_p=eta_low)
    old_disk = {k: v for k, v in th_old.items() if k != "eta_p"}
    old_disk.update(propeller_model="app_l", prop_real_to_ideal=f_low)
    nominal_flat = {"propeller_model": "flat"}      # the ledger's flat eta_p
    L_sized = t_new["design_row"]["L_sized_h"]
    cases = {
        "new_worst_disk": case(b_new, th_new, w_new["hours"]),
        "new_worst_flat_eta_low": case(b_new, new_flat, w_new["hours"]),
        "old_worst_flat_eta_low": case(b_old, th_old, w_old["hours"]),
        "old_worst_disk": case(b_old, old_disk, w_old["hours"]),
        "new_nominal_disk": case(b_new, {}, L_sized),
        "new_nominal_flat": case(b_new, nominal_flat, L_sized),
    }
    hours = {"new_worst_disk": w_new["hours"], "old_worst_flat_eta_low": w_old["hours"],
             "new_worst_flat_eta_low": b_new.hours_detail(new_flat)[0], "old_worst_disk": b_old.hours_detail(old_disk)[0]}
    return {"split": split(t_old, t_new), "cases": cases, "hours_on_station": hours,
            "swapped_values": {"flat_eta_p_low_end_old_record": eta_low, "disk_factor_low_end_new_record": f_low,
                               "flat_eta_p_ledger_nominal": b_new.L["eta_p"], "disk_factor_nominal": b_new.L["prop_real_to_ideal"]},
            "records": {tag: {"folder": str(d), "design_sha256": sp.sha256(Path(d) / "design_pusher.json"),
                              "target_result_sha256": sp.sha256(Path(d) / "target_result.json")}
                        for tag, d in (("old", old_dir), ("new", new_dir))}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    dirty = sp.git_dirty_files()
    res = run(a.old, a.new)
    res["inputs"] = {"git_commit": sp.git_commit(), "git_dirty": bool(dirty), "git_dirty_files": dirty,
                     "python": platform.python_version(), "seed": None,
                     "command": "python -m measurement.appl_decomposition " + " ".join(sys.argv[1:] if argv is None else argv)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    for k, v in res["cases"].items():
        print(k, round(v["W0_lb"], 1), round(v["fuel_with_reserve_lb"], 1), {s: round(x, 1) for s, x in v["segment_fuel_lb"].items()})


if __name__ == "__main__":
    main()

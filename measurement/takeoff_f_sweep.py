"""Take-off distance against the propeller real-to-ideal factor f on the App. L baseline record (review APL-5,
owner ruling G-9).

    python -m measurement.takeoff_f_sweep \
        --record runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05 \
        --out runs/task12/stage1/2026-11-26/takeoff_f_sweep/sweep.json

The record is rebuilt with the ledger as recorded (measurement.stage3_perf.rebuild, which checks that the rebuild
reproduces the record). The design is then held fixed: weight, wing, drag, CL_max, engine power and propeller
diameter are the rebuilt ones. Only `prop_real_to_ideal` in a copy of the ledger values changes, and Stage 1's own
functions (conceptual.uav._takeoff, the thrust function and perf.landing_distance, as in uav.performance) are
called again. This is not a re-size: weight and fuel do not move with f."""
import argparse
import json
import platform
import sys
from pathlib import Path

from conceptual import raymer_performance as perf
from conceptual import uav
from conceptual.units import isa
from measurement import stage3_perf as sp

REPO = Path(__file__).resolve().parents[1]
F_VALUES = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


def at_f(d, L, b, f):
    """Take-off and landing at factor f, everything else as in the record. Thrust is read at V = 0 (the code
    holds V at 1 ft/s), at 0.707 V_TO (where the ground roll takes it, Raymer 17.8) and at 1.15 V_stall
    (where the transition takes it)."""
    Lf = dict(L, prop_real_to_ideal=f)
    W0, S, K = d["W0_lb"], b["geom"]["S"], d["K"]
    to = uav._takeoff(W0, S, b["CD0_takeoff"], K, b["clmax"]["takeoff"], Lf, b["bhp"], b["D_prop"])
    thrust = uav._thrust_fn(b["bhp"], Lf, b["D_prop"])
    ld = perf.landing_distance(W0, S, isa(0.0)["rho"], b["CD0_landing"], K, b["clmax"]["landing"],
                               mu_brake=Lf["braking_mu"], free_roll_s=Lf["free_roll_s"])
    V_tr = 1.15 * to["V_stall"]
    return {"f": f,
            "thrust_static_lb": thrust(0.0), "thrust_0707_VTO_lb": thrust(0.707 * to["V_TO"]),
            "thrust_transition_lb": thrust(V_tr),
            "V_TO_ft_s": to["V_TO"], "speed_at_0707_VTO_ft_s": 0.707 * to["V_TO"],
            "ground_roll_ft": to["ground_roll"], "rotation_ft": to["rotation"],
            "transition_ft": to["transition"], "climb_ft": to["climb"],
            "takeoff_over_50ft_ft": to["total"], "landing_over_50ft_ft": ld["total"]}


def run(record_dir, f_values=F_VALUES):
    record_dir = Path(record_dir)
    d, L, b, ledger_path, check = sp.rebuild(record_dir / "design_pusher.json")
    return {"record_takeoff_ft": d["performance"]["takeoff_ft"], "record_landing_ft": d["performance"]["landing_ft"],
            "record_f": L["prop_real_to_ideal"], "propeller_diameter_ft": b["D_prop"], "bhp": b["bhp"],
            "W0_lb": d["W0_lb"], "field_length_ft": L["field_length_ft"],
            "sweep": [at_f(d, L, b, f) for f in f_values],
            "inputs": {"record": str(record_dir.relative_to(REPO) if record_dir.is_absolute() else record_dir),
                       "design_sha256": sp.sha256(record_dir / "design_pusher.json"),
                       "ledger_sha256": sp.sha256(ledger_path)}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    dirty = sp.git_dirty_files()
    res = run(a.record)
    res["inputs"].update(git_commit=sp.git_commit(), git_dirty=bool(dirty), git_dirty_files=dirty,
                         python=platform.python_version(), seed=None,
                         command="python -m measurement.takeoff_f_sweep " + " ".join(sys.argv[1:] if argv is None else argv))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    for r in res["sweep"]:
        print(f"f {r['f']:.2f}  T0 {r['thrust_static_lb']:.0f}  roll {r['ground_roll_ft']:.0f}  "
              f"TO {r['takeoff_over_50ft_ft']:.0f}  LD {r['landing_over_50ft_ft']:.0f}")


if __name__ == "__main__":
    main()

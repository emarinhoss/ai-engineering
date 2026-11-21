"""Spec 7.1b item 1: the change in mission fuel and W0 at the frozen Stage 1 point when the TP100
table built with the constant-cp burner (the record's own table) is replaced by the one built with
Mattingly's MSH burner and the widened cycle family (data/task12/tp100_table.json).

    python -m measurement.engine_change --run runs/task12/stage1/2026-11-21d --out <json>

Two numbers at the record's W/S, A and tail size: mission fuel at the record's W0 (no re-size),
and W0 re-sized with the new table. Also the share of mission sub-steps where App. K's
choked-turbine assumption fails, and the turbine pressure ratios at the rating.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from conceptual import stage1, uav
from conceptual.engine_model import TP100_TABLE, TableEngine, table_for_run


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    run = Path(a.run)
    d = json.loads((run / "design_pusher.json").read_text())
    L, _ = uav.load_ledger(run / "ledger.yaml")
    L = dict(L, ht_volume_scale=d["ht_volume_scale"])
    base = dict(stage1.engine_options()[0][stage1.CHOSEN_ENGINE])
    old, new = TableEngine(table_for_run(run)), TableEngine(TP100_TABLE)
    out = {"record": str(run), "W0_record_lb": d["W0_lb"], "fuel_record_lb": d["fuel_lb"]}
    for tag, m in (("old_table", old), ("new_table", new)):
        e = dict(base, model=m)
        b = uav._build(d["W0_lb"], d["concept"], d["W_S"], d["A"], L, d["fuel_lb"], e)
        r = uav.evaluate(d["concept"], d["W_S"], d["A"], L, W0_guess=d["W0_lb"], engine=e)
        out[tag] = {"fuel_at_record_W0_lb": b["fuel"], "W0_resized_lb": r["W0"], "fuel_resized_lb": r["fuel"],
                    "power_ok": r["power_ok"], "power_required_hp": max(r["power_req"].values()),
                    "unchoked_share": {m_[0]: m_[6] for m_ in r["mission"] if m_[3] > 0},
                    "lp_ratio_rated": float(m.lp_ratio[0, 2, -1]), "hp_ratio": m.hp_ratio,
                    "critical_ratio": m.crit, "meta": m.meta}
    o, n = out["old_table"], out["new_table"]
    out["fuel_change_at_record_W0"] = n["fuel_at_record_W0_lb"] / o["fuel_at_record_W0_lb"] - 1.0
    out["W0_change_resized"] = n["W0_resized_lb"] / o["W0_resized_lb"] - 1.0
    out["inputs"] = {"commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                              check=False).stdout.strip(),
                     "new_table_sha256": hashlib.sha256(TP100_TABLE.read_bytes()).hexdigest()}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: out[k] for k in ("fuel_change_at_record_W0", "W0_change_resized")}),
          o["W0_resized_lb"], n["W0_resized_lb"], n["power_ok"], n["unchoked_share"], n["lp_ratio_rated"], n["hp_ratio"])


if __name__ == "__main__":
    main()

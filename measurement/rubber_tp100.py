"""Photo-scaled TP100 sweep (owner request 2026-11-22): what rated shaft power would let the Task 12
pusher pass Gate B robustness, R5's guarantee (at least 3.5 h at info-gap horizon 1) and R7.

    python -m measurement.rubber_tp100 --out runs/task12/stage3/2026-11-22/rubber

For each rated power P the engine is the TP100's App. K table scaled in power by P/241 (same lapse
and part-power SFC curve, same 5 % SFC allowance) and in weight by Raymer's rubber-engine law,
W = W_TP100 (P/241)^0.803 (Table 10.3, p. 224, turboprop; `geometry_sizing.turboprop_scaled`).
No such engine is known to exist: the sweep finds the power class to look for. Each engine is
sized with the current ledger and selection rules (Stage 1 carpet and first_compliant, pusher),
written as a record, and its robustness found with measurement/info_gap.py (empty weight banded).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from conceptual import constraints, stage1, uav
from conceptual.engine_model import TP100_TABLE, TableEngine
from conceptual.geometry_sizing import turboprop_scaled
from conceptual.units import KT, RHO0
from measurement import info_gap

POWERS = (260.0, 280.0, 300.0, 330.0, 360.0)


def scaled_engine(P, L):
    base = stage1.engine_options()[0][stage1.CHOSEN_ENGINE]
    w = turboprop_scaled({"weight_lb": base["weight_lb"], "length_in": 0.0, "diameter_in": 0.0},
                         base["bhp"], P)["weight_lb"]
    model = TableEngine(TP100_TABLE).scaled(sfc=L.get("engine_sfc_allowance", 1.0), power=P / base["bhp"],
                                            rerate=True)
    return dict(base, name=f"TP100 scaled to {P:g} hp", bhp=P, weight_lb=w, model=model)


def size(P, out):
    """Stage 1 selection with the scaled engine; writes a record folder; returns a summary."""
    L, _ = uav.load_ledger()
    eng = scaled_engine(P, L)
    raw = stage1.engine_options()[1][stage1.CHOSEN_ENGINE]
    rows = stage1.carpet("pusher", L, eng, eng["name"])
    ws = constraints.ws_stall(RHO0, L["stall_speed_kt"] * KT, uav._cl_max(L)["clean"])
    a, comp, tried = stage1.first_compliant("pusher", rows, ws, L, eng, raw)
    rec = out / f"P{P:g}"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "design_pusher.json").write_text(json.dumps(stage1.design_record(a, L, raw), indent=1, default=float))
    shutil.copyfile(uav.LEDGER, rec / "ledger.yaml")
    shutil.copyfile(TP100_TABLE, rec / "tp100_table.json")
    (rec / "selection_pusher.json").write_text(json.dumps(tried, indent=1, default=float))
    d = a["design"]
    return {"P_hp": P, "engine_weight_lb": eng["weight_lb"], "W_S": d["W_S"], "A": d["A"], "W0_lb": d["W0"],
            "fuel_lb": d["fuel"], "span_ft": d["geom"]["wing"].span,
            "power_margin": 1.0 - max(d["power_req"].values()) / P,
            "failed": [c["requirement"] for c in comp if c["met"] is False], "record": str(rec)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    res = []
    for P in POWERS:
        s = size(P, out)
        ig = info_gap.study(str(Path(s["record"]) / "design_pusher.json"))
        s["h_hat"] = {k: v["h_hat"] for k, v in ig["h_hat"].items()}
        (Path(s["record"]) / "info_gap.json").write_text(json.dumps(info_gap._json_safe(ig), indent=1, default=float))
        res.append(s)
        print(json.dumps({k: s[k] for k in ("P_hp", "W0_lb", "W_S", "A", "power_margin", "failed", "h_hat")},
                         default=float), flush=True)
    meta = {"commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                     check=False).stdout.strip(),
            "ledger_sha256": hashlib.sha256(uav.LEDGER.read_bytes()).hexdigest(),
            "table_sha256": hashlib.sha256(TP100_TABLE.read_bytes()).hexdigest(),
            "weight_law": "W = 135.8 (P/241)^0.803, Raymer Table 10.3 p. 224", "runtime_s": time.time() - t0}
    (out / "sweep.json").write_text(json.dumps({"inputs": meta, "results": res}, indent=1, default=float))


if __name__ == "__main__":
    main()

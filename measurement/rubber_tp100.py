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
import re
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
TP100 = "PBS_TP100"
# The ledger now holds the M250's values (ruling R-b 1.02, TCDS rpm 2,030) and the App. L propeller (ruling G-4);
# the TP100 sweeps used these
TP100_LEDGER = {"engine_sfc_allowance": 1.05, "propeller_rpm": 2158.0, "propeller_model": "flat"}


def tp100_ledger_values():
    """The current ledger's values with the three the TP100 records were sized with (TP100_LEDGER)."""
    return dict(uav.load_ledger()[0], **TP100_LEDGER)


TP100_LEDGER_LINES = {      # the ledger lines as the TP100 records had them (git show 1b11d3b:data/task12/ledger.yaml);
                            # those records have no propeller_model line, which reads as flat
    "engine_sfc_allowance": '  engine_sfc_allowance:  {value: 1.05, units: "-", confidence: requirement, source: "Gate A round 5 ruling 2 (Eder 2026-11-21): every SFC from the TP100 App. K table multiplied by 1.05 in sizing, covering the model\'s part-power optimism against the book (MSH reads 5-9 % low, calibration absorbs the design-point part)"}',
    "propeller_rpm": '  propeller_rpm:         {value: 2158.0, units: rpm, confidence: datasheet, source: "PBS TP100 output shaft speed 2,158 RPM, maker\'s brochure p. 12 (Gate A round 4, R4-10); was an assumed 2,000 rpm"}',
    "propeller_model": '  propeller_model:       {value: flat, units: "-", confidence: requirement, source: "TP100 records: flat eta_p, as sized before owner ruling G-4"}',
}


def tp100_ledger_text(text):
    """Ledger text with the TP100's lines (TP100_LEDGER_LINES) in place of the M250's."""
    for key, line in TP100_LEDGER_LINES.items():
        text, n = re.subn(rf"^\s*{key}:.*$", lambda m, line=line: line, text, flags=re.MULTILINE)
        if n != 1:
            raise ValueError(f"{key} line not found in the ledger")
    return text


def scaled_engine(P, L):
    base = stage1.engine_options(TP100)[0][TP100]
    w = turboprop_scaled({"weight_lb": base["weight_lb"], "length_in": 0.0, "diameter_in": 0.0},
                         base["bhp"], P)["weight_lb"]
    model = TableEngine(TP100_TABLE).scaled(sfc=L.get("engine_sfc_allowance", 1.0), power=P / base["bhp"],
                                            rerate=True)
    return dict(base, name=f"TP100 scaled to {P:g} hp", bhp=P, weight_lb=w, model=model)


def size(P, out):
    """Stage 1 selection with the scaled engine; writes a record folder; returns a summary."""
    L = tp100_ledger_values()
    eng = scaled_engine(P, L)
    raw = stage1.engine_options(TP100)[1][TP100]
    rows = stage1.carpet("pusher", L, eng, eng["name"])
    ws = constraints.ws_stall(RHO0, L["stall_speed_kt"] * KT, uav._cl_max(L)["clean"])
    a, comp, tried = stage1.first_compliant("pusher", rows, ws, L, eng, raw)
    rec = out / f"P{P:g}"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "design_pusher.json").write_text(json.dumps(stage1.design_record(a, L, raw), indent=1, default=float))
    (rec / "ledger.yaml").write_text(tp100_ledger_text(uav.LEDGER.read_text()))   # TP100 values, see TP100_LEDGER
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

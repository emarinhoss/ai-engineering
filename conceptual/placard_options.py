"""Gate A round 4, ruling 8 record (re-check RC-3): the lightest compliant pusher for each V_C
placard option, with the round-4 margins as they stood when the ruling was asked (power 5 %,
ceiling 500 ft, negative gust 0.1 g), and how many single band-end trades break a requirement.

    python -m conceptual.placard_options --out runs/task12/stage1/<date>_placard_options
"""
import argparse
import hashlib
import json
import subprocess
from multiprocessing import Pool
from pathlib import Path

from conceptual import constraints, stage1, uav
from conceptual.units import KT, RHO0

OPTIONS = (100.0, 105.0, 110.0, 120.0)


def run(vc):
    L, _ = uav.load_ledger()
    L = dict(L, vc_placard_kt_eas=vc, margin_power_fraction=0.05)
    engs, raw = stage1.engine_options()
    e = engs[stage1.CHOSEN_ENGINE]
    rows = stage1.carpet("pusher", L, e, stage1.CHOSEN_ENGINE)
    ws = constraints.ws_stall(RHO0, L["stall_speed_kt"] * KT, uav._cl_max(L)["clean"])
    a, comp, tried = stage1.first_compliant("pusher", rows, ws, L, e, raw[stage1.CHOSEN_ENGINE])
    d = a["design"]
    tr = stage1.trades("pusher", d["W_S"], d["A"], L, e, raw[stage1.CHOSEN_ENGINE])
    bands = [t for t in tr if t["case"].endswith(("(lo)", "(hi)")) or t["case"].startswith("engine table")]
    return {"vc_kt_eas": vc, "W_S": d["W_S"], "A": d["A"], "W0_lb": d["W0"], "span_ft": d["geom"]["wing"].span,
            "power_margin": 1 - max(d["power_req"].values()) / d["bhp"],
            "failed_at_chosen": [c["requirement"] for c in comp if c["met"] is False],
            "n_gust": d["n_gust"], "n_negative_gust": d["n_negative_gust"], "band_ends": len(bands),
            "band_ends_breaking_a_requirement": [t["case"] for t in bands if t.get("failed_without_margins")],
            "candidates_tried": len(tried)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    repo = stage1.REPO
    with Pool(3) as p:
        res = p.map(run, OPTIONS)
    meta = {"commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                     check=False, cwd=repo).stdout.strip(),
            "ledger_sha256": hashlib.sha256(uav.LEDGER.read_bytes()).hexdigest(),
            "overrides": {"margin_power_fraction": 0.05, "vc_placard_kt_eas": list(OPTIONS)},
            "note": "Re-run of the option probe the owner saw before ruling 8, with the code of this commit "
                    "(which also evaluates the gust lift slope at the V_C Mach, re-check RC-6); numbers may "
                    "differ slightly from the probe quoted in the ruling question."}
    (out / "options.json").write_text(json.dumps({"inputs": meta, "options": res}, indent=1, default=float))
    for r in res:
        print(r["vc_kt_eas"], r["W_S"], r["A"], round(r["W0_lb"]), r["failed_at_chosen"],
              len(r["band_ends_breaking_a_requirement"]), "/", r["band_ends"])


if __name__ == "__main__":
    main()

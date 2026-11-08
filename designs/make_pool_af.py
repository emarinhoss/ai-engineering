"""Stage the high-fidelity (SU2) design pool, T10.9c: python -m designs.make_pool_af

For the first N gate-passing designs of designs/pool_drone96.csv (seed 0, in file order), the
section is the design's own NACA four-digit section at the design's cruise Reynolds number from
the low-fidelity model (drone.evaluate, re_cruise), at the spec's five angles of attack
(-2, 2, 6, 10, 14 deg), one airfoil2d case each, on the `coarse` mesh (decision 7, 2026-11-08:
the coarse drag is within 1.1 percent of the fine mesh on the smoke case, inside every drift
band, at 2.8x less cost). A bias pair, the first B designs at 2, 6 and 10 deg on the `medium`
mesh, is staged beside it (tag pool_af_bias) as the recorded coarse-against-medium check.

Writes designs/pool_af_cases.csv (design index, case_id, tag, mesh level, Re, alpha) and two
batch files under $SU2_QUEUE_DIR/batches/ through mcp_server.queue.export_batch. Never chooses a
design: the designs are the committed Sobol pool and the angles are the spec's.
"""
import argparse
import csv
from pathlib import Path

from drone import evaluate, ledger
from mcp_server import queue

INPUTS = ("span_m", "aspect_ratio", "taper_ratio", "battery_fraction", "camber_pct", "thickness_pct")
ANGLES = (-2.0, 2.0, 6.0, 10.0, 14.0)
BIAS_ANGLES = (2.0, 6.0, 10.0)
HERE = Path(__file__).parent


def stage(design, alpha, level, tag, re_cruise):
    params = {"family": "airfoil2d", "camber_pct": design["camber_pct"], "thickness_pct": design["thickness_pct"],
              "reynolds": round(re_cruise, 1), "alpha_deg": alpha, "transition": "BCM",
              "mesh_level": level, "max_iter": 6000, "tag": tag}
    res = queue.create(params)
    if not res["ok"] and res.get("stage") == "exists":
        res = {"ok": True, "case_id": res["case_id"]}
    if not res["ok"]:
        raise SystemExit(f"design {design['index']} alpha {alpha} {level}: {res}")
    sub = queue.submit(res["case_id"])
    if not sub["ok"] and "only a created job" not in " ".join(sub.get("errors", [])):
        raise SystemExit(f"submit {res['case_id']}: {sub}")
    return res["case_id"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--designs", type=int, default=32)
    ap.add_argument("--bias-designs", type=int, default=4)
    ap.add_argument("--pool", default=str(HERE / "pool_drone96.csv"))
    ap.add_argument("--out", default=str(HERE / "pool_af_cases.csv"))
    a = ap.parse_args(argv)
    fixed = ledger.load_all()
    with open(a.pool, newline="") as f:
        designs = [{"index": int(r["index"]), **{k: float(r[k]) for k in INPUTS}} for r in csv.DictReader(f)]
    rows, pool_ids, bias_ids = [], [], []
    for k, d in enumerate(designs[: a.designs]):
        out = evaluate.evaluate({key: d[key] for key in INPUTS}, fixed)
        if out["gates"]:
            raise SystemExit(f"design {d['index']} is gated: {out['gates']}")
        re = out["re_cruise"]
        for alpha in ANGLES:
            cid = stage(d, alpha, "coarse", "pool_af", re)
            pool_ids.append(cid)
            rows.append({"index": d["index"], "case_id": cid, "tag": "pool_af", "mesh_level": "coarse",
                         "reynolds": round(re, 1), "alpha_deg": alpha})
        if k < a.bias_designs:
            for alpha in BIAS_ANGLES:
                cid = stage(d, alpha, "medium", "pool_af_bias", re)
                bias_ids.append(cid)
                rows.append({"index": d["index"], "case_id": cid, "tag": "pool_af_bias", "mesh_level": "medium",
                             "reynolds": round(re, 1), "alpha_deg": alpha})
        print(f"design {d['index']}: Re {re:.0f}, {len(ANGLES)} coarse cases" + (f" + {len(BIAS_ANGLES)} medium" if k < a.bias_designs else ""))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("index", "case_id", "tag", "mesh_level", "reynolds", "alpha_deg"))
        w.writeheader()
        w.writerows(rows)
    for ids, name in ((pool_ids, "pool_af"), (bias_ids, "pool_af_bias")):
        text = queue.export_batch(ids, path=str(queue.queue_dir() / "batches" / f"{name}.batch.json"))
        print(name, len(ids), "cases, batch bytes", len(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

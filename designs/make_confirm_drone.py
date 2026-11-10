"""Stage the confirmation run of the high-fidelity inverse query (T10.10a, spec section 10.4).

    python -m designs.make_confirm_drone [--params runs/drone_inverse_hf/2026-11-09/confirm_params.json]

The design is the one analysis.inverse --family drone wrote to confirm_params.json; this script
never chooses it. Exactly as designs.make_pool_af stages a pool design: the section is the
design's own NACA four-digit section at the design's cruise Reynolds number from the low-fidelity
model (drone.evaluate, re_cruise), at the spec's five angles (-2, 2, 6, 10, 14 deg), one airfoil2d
case each on the `coarse` mesh, max_iter 6000, BCM transition, tag `confirm`. Each case goes
through mcp_server.queue.create and submit (schema, gates, mesh quality), and the five jobs are
bundled with mcp_server.queue.export_batch. Writes designs/confirm_drone_cases.csv.
"""
import argparse
import csv
import json
from pathlib import Path

from designs.make_pool_af import ANGLES, INPUTS
from drone import evaluate, ledger
from mcp_server import queue

HERE = Path(__file__).parent
DEFAULT_PARAMS = "runs/drone_inverse_hf/2026-11-09/confirm_params.json"


def stage(design, alpha, re_cruise):
    params = {"family": "airfoil2d", "camber_pct": design["camber_pct"],
              "thickness_pct": design["thickness_pct"], "reynolds": round(re_cruise, 1),
              "alpha_deg": alpha, "transition": "BCM", "mesh_level": "coarse", "max_iter": 6000,
              "tag": "confirm"}
    res = queue.create(params)
    if not res["ok"] and res.get("stage") == "exists":
        res = {"ok": True, "case_id": res["case_id"]}
    if not res["ok"]:
        raise SystemExit(f"alpha {alpha}: {res}")
    sub = queue.submit(res["case_id"])
    if not sub["ok"] and "only a created job" not in " ".join(sub.get("errors", [])):
        raise SystemExit(f"submit {res['case_id']}: {sub}")
    return res["case_id"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--params", default=DEFAULT_PARAMS)
    ap.add_argument("--out", default=str(HERE / "confirm_drone_cases.csv"))
    a = ap.parse_args(argv)
    p = json.loads(Path(a.params).read_text())
    design = {k: float(p[k]) for k in INPUTS}
    out = evaluate.evaluate(design, ledger.load_all())
    if out["gates"]:
        raise SystemExit(f"the confirmation design is gated: {out['gates']}")
    re = out["re_cruise"]
    rows, ids = [], []
    for alpha in ANGLES:
        cid = stage(design, alpha, re)
        ids.append(cid)
        rows.append({"case_id": cid, "tag": "confirm", "mesh_level": "coarse",
                     "reynolds": round(re, 1), "alpha_deg": alpha, **design})
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    text = queue.export_batch(ids, path=str(queue.queue_dir() / "batches" / "confirm_drone.batch.json"))
    print(f"design {design}: Re {re:.0f}, {len(ids)} coarse cases; batch bytes {len(text)}")
    for r in rows:
        print(r["case_id"], r["alpha_deg"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

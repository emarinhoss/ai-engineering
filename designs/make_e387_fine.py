"""Stage the fine-mesh E387 cases for the V6e medium-against-fine row (decision 11, 2026-11-10).

    python -m designs.make_e387_fine [--max-iter 12000]

The angles and Reynolds numbers are read from the recorded medium-mesh E387 cases under runs/e387/
(five angles at Re 203,800 and five at Re 305,200), never typed here. Each fine case is the same
case as its medium one except mesh_level `fine` and the iteration budget: the one earlier fine case
(runs/mesh/, NACA section, 6 deg) used its whole 6,000 iterations, so these get 12,000 by decision
11. Each case goes through mcp_server.queue.create and submit (schema, gates, mesh quality), and the
ten jobs are bundled with mcp_server.queue.export_batch. Writes designs/e387_fine_cases.csv.

    python -m designs.make_e387_fine --medium-rerun

stages the like-for-like partner (decision 11, second ruling): the five medium cases at Re 203,800
again on the current (smoothed) mesher, same budget as the originals (6,000), tag `e387_smooth` so
they get their own case ids and record folder. Writes designs/e387_medium_smooth_cases.csv.
"""
import argparse
import csv
import json
from pathlib import Path

from mcp_server import queue

HERE = Path(__file__).parent
ROOT = HERE.parent


def medium_cases():
    """The params of every recorded medium E387 case, sorted by Reynolds number and angle."""
    out = []
    for f in sorted((ROOT / "runs" / "e387").glob("airfoil2d-*/params.json")):
        p = json.loads(f.read_text())
        if p.get("airfoil") == "e387" and p.get("mesh_level") == "medium":
            out.append(p)
    return sorted(out, key=lambda p: (p["reynolds"], p["alpha_deg"]))


def stage(params):
    res = queue.create(params)
    if not res["ok"] and res.get("stage") == "exists":
        res = {"ok": True, "case_id": res["case_id"]}
    if not res["ok"]:
        raise SystemExit(f"{params['reynolds']:g}, {params['alpha_deg']:g} deg: {res}")
    sub = queue.submit(res["case_id"])
    if not sub["ok"] and "only a created job" not in " ".join(sub.get("errors", [])):
        raise SystemExit(f"submit {res['case_id']}: {sub}")
    return res["case_id"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--medium-rerun", action="store_true",
                    help="stage the Re 203,800 medium cases on the smoothed mesher instead")
    ap.add_argument("--max-iter", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--batch-name", default=None)
    a = ap.parse_args(argv)
    if a.medium_rerun:
        level, tag, n_expected = "medium", "e387_smooth", 5
        a.max_iter = a.max_iter or 6000
        a.out = a.out or str(HERE / "e387_medium_smooth_cases.csv")
        a.batch_name = a.batch_name or "e387_medium_smooth"
        cases = [m for m in medium_cases() if m["reynolds"] == 203800.0]
    else:
        level, tag, n_expected = "fine", None, 10
        a.max_iter = a.max_iter or 12000
        a.out = a.out or str(HERE / "e387_fine_cases.csv")
        a.batch_name = a.batch_name or "e387_fine"
        cases = medium_cases()
    rows, ids = [], []
    for m in cases:
        p = {k: m[k] for k in ("family", "airfoil", "reynolds", "alpha_deg", "transition", "tag")}
        p.update(mesh_level=level, max_iter=a.max_iter, tag=tag or m["tag"])
        cid = stage(p)
        ids.append(cid)
        rows.append({"case_id": cid, "tag": p["tag"], "mesh_level": level, "reynolds": p["reynolds"],
                     "alpha_deg": p["alpha_deg"], "max_iter": a.max_iter})
    if len(rows) != n_expected:
        raise SystemExit(f"expected {n_expected} cases, found {len(rows)}")
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    text = queue.export_batch(ids, path=str(queue.queue_dir() / "batches" / f"{a.batch_name}.batch.json"))
    print(f"{len(ids)} {level} E387 cases, max_iter {a.max_iter}; batch bytes {len(text)}")
    for r in rows:
        print(r["case_id"], r["reynolds"], r["alpha_deg"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

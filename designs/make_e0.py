"""Stage experiment E0 (docs/specs/task11_fno_exploration.md, section 4): what a warm start saves.

    python -m designs.make_e0

Section and Reynolds number are read from the recorded pool design 1 (designs/pool_af_cases.csv and
its run record), never typed. Twelve airfoil2d cases, tag `e0`, budget 6,000, in two batches:

  e0_cold  coarse at 2, 6, 10 deg writing a restart file (the donors, and the cold twins of the
           angle-step cases); medium at 2, 6, 10 deg (the cold twins of the mesh-step cases)
  e0_warm  angle step: coarse 6 from coarse 2, coarse 10 from coarse 6, coarse 2 from coarse 6;
           mesh step: medium at 2, 6, 10 deg from the coarse solution at the same angle

A warm case differs from its cold twin by `restart_from` (and, for the coarse twins, by the twin
writing a restart file). The warm batch must reach the workers only after the three donors are
done: a warm job whose donor has no restart file fails as `donor_missing`. Each case goes through
mcp_server.queue.create and submit. Writes designs/e0_cases.csv.
"""
import csv
import json
from pathlib import Path

from mcp_server import queue

HERE = Path(__file__).parent
ROOT = HERE.parent
DESIGN = 1
ANGLES = (2.0, 6.0, 10.0)
ANGLE_STEPS = ((6.0, 2.0), (10.0, 6.0), (2.0, 6.0))      # (this angle, donor angle)


def section():
    """camber, thickness, Reynolds number and transition of pool design DESIGN, from its record."""
    with open(HERE / "pool_af_cases.csv", newline="") as f:
        row = next(r for r in csv.DictReader(f) if int(r["index"]) == DESIGN and r["tag"] == "pool_af")
    p = json.loads((ROOT / "runs" / "pool_af" / row["case_id"] / "params.json").read_text())
    return {k: p[k] for k in ("family", "camber_pct", "thickness_pct", "reynolds", "transition")}


def stage(params):
    res = queue.create(params)
    if not res["ok"] and res.get("stage") == "exists":
        res = {"ok": True, "case_id": res["case_id"]}
    if not res["ok"]:
        raise SystemExit(f"{params}: {res}")
    sub = queue.submit(res["case_id"])
    if not sub["ok"] and "only a created job" not in " ".join(sub.get("errors", [])):
        raise SystemExit(f"submit {res['case_id']}: {sub}")
    return res["case_id"]


def main():
    base = {**section(), "tag": "e0", "max_iter": 6000}
    rows, donor = [], {}

    def add(batch, kind, level, alpha, twin="", **extra):
        cid = stage({**base, "mesh_level": level, "alpha_deg": alpha, **extra})
        rows.append({"case_id": cid, "batch": batch, "kind": kind, "mesh_level": level,
                     "alpha_deg": alpha, "restart_from": extra.get("restart_from", ""),
                     "cold_twin": twin})
        return cid

    medium = {}
    for a in ANGLES:
        donor[a] = add("e0_cold", "cold", "coarse", a, save_restart=True)
    for a in ANGLES:
        medium[a] = add("e0_cold", "cold", "medium", a)
    for a, d in ANGLE_STEPS:
        add("e0_warm", "angle_step", "coarse", a, twin=donor[a], restart_from=donor[d])
    for a in ANGLES:
        add("e0_warm", "mesh_step", "medium", a, twin=medium[a], restart_from=donor[a])
    with open(HERE / "e0_cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for batch in ("e0_cold", "e0_warm"):
        ids = [r["case_id"] for r in rows if r["batch"] == batch]
        text = queue.export_batch(ids, path=str(queue.queue_dir() / "batches" / f"{batch}.batch.json"))
        print(f"{batch}: {len(ids)} cases, batch bytes {len(text)}")
    for r in rows:
        print(r["case_id"], r["kind"], r["mesh_level"], r["alpha_deg"], r["restart_from"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Stage experiment S2R (docs/specs/task11_fno_exploration.md): linear tolerance 1E-2 on one machine.

    python -m designs.make_s2r

Seven cases, fixed by the approved rule: the five S1/S2 cases plus pool design 1 coarse at 4 and
8 deg. The two new angles first get a reference (tag s2r_ref, the S1/S2 reference settings). Then
each case gets four runs, staged in the order baseline, 1E-2, 1E-2, baseline:

  s2r_base_a   today's numerics (linear tolerance 1E-6), budget 6,000
  s2r_tol_a    linear tolerance 1E-2
  s2r_tol_b    linear tolerance 1E-2 (repeat)
  s2r_base_b   today's numerics (repeat)

The worker takes jobs oldest created_at first, and created_at has one-second resolution, so the
script waits just over a second between stagings: the staging order is then the run order. The
references of the five old cases are the valid S1/S2 ones and are not staged again.
Writes designs/s2r_cases.csv (rows in staging order) and one batch file.
"""
import csv
import time
from pathlib import Path

from designs.make_e0 import section, stage
from designs.make_s12 import REFERENCE
from designs.make_s12 import cases as s12_cases
from mcp_server import queue

HERE = Path(__file__).parent
TOL = 1e-2
NEW_ANGLES = (4.0, 8.0)
ORDER = (("s2r_base_a", "baseline"), ("s2r_tol_a", "tol"), ("s2r_tol_b", "tol"), ("s2r_base_b", "baseline"))


def cases():
    """{name: params without tag, budget or numerics}: the five S1/S2 cases, then the two new ones."""
    out = s12_cases()
    pool = section()
    for a in NEW_ANGLES:
        out[f"pool1_coarse_{a:g}"] = {**pool, "mesh_level": "coarse", "alpha_deg": a}
    return out


def main():
    rows = []

    def add(case, base, tag, setting, **extra):
        cid = stage({**base, "tag": tag, "max_iter": 6000, **extra})
        rows.append({"case_id": cid, "set": tag, "case": case, "setting": setting})
        time.sleep(1.1)                      # distinct created_at, so staging order = run order

    all_cases = cases()
    for a in NEW_ANGLES:
        name = f"pool1_coarse_{a:g}"
        add(name, all_cases[name], "s2r_ref", "reference", **REFERENCE)
    for case, base in all_cases.items():
        for tag, setting in ORDER:
            add(case, base, tag, setting, **({"linear_tol": TOL} if setting == "tol" else {}))
    with open(HERE / "s2r_cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ids = [r["case_id"] for r in rows]
    text = queue.export_batch(ids, path=str(queue.queue_dir() / "batches" / "s2r.batch.json"))
    print(f"s2r: {len(ids)} cases, batch bytes {len(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Stage experiment S1/S2 (docs/specs/task11_fno_exploration.md): CFL ceiling and linear tolerance.

    python -m designs.make_s12

Five cases, fixed by the approved rule: pool design 1 (section and Reynolds number read from its
record, as designs.make_e0 does) on the coarse mesh at 2, 6 and 10 deg and on the medium mesh at
6 deg; the E387 at Re 203,800 and 4.23 deg on the medium mesh (params read from its recorded case).
Forty runs in five sets, each set with its own tag so that equal params get their own case id:

  s12_ref    today's numerics, budget 20,000, Cauchy window 500 at 1E-7 (the reference)
  s12_base1  today's numerics and stop, budget 6,000 (baseline, first repeat)
  s12_base2  the same again (second repeat: the noise of the wall-time measurement)
  s12_s1     CFL ceiling 50, 100, 250
  s12_s2     linear tolerance 1E-4, 1E-2

Each case goes through mcp_server.queue.create and submit. Writes designs/s12_cases.csv and one
batch file per set.
"""
import csv
import json
from pathlib import Path

from designs.make_e0 import section, stage
from mcp_server import queue

HERE = Path(__file__).parent
ROOT = HERE.parent
E387_CASE = "airfoil2d-7de8a51345"          # recorded medium E387, Re 203,800, 4.23 deg
REFERENCE = {"max_iter": 20000, "cauchy_elems": 500, "cauchy_eps": 1e-7}
CFL_CEILINGS = (50.0, 100.0, 250.0)
LINEAR_TOLS = (1e-4, 1e-2)


def cases():
    """{name: params without tag, budget or numerics} for the five cases of the rule."""
    pool = section()
    out = {f"pool1_coarse_{a:g}": {**pool, "mesh_level": "coarse", "alpha_deg": a} for a in (2.0, 6.0, 10.0)}
    out["pool1_medium_6"] = {**pool, "mesh_level": "medium", "alpha_deg": 6.0}
    p = json.loads((ROOT / "runs" / "e387" / E387_CASE / "params.json").read_text())
    out["e387_medium_4.23"] = {k: p[k] for k in ("family", "airfoil", "reynolds", "alpha_deg",
                                                  "transition", "mesh_level")}
    return out


def main():
    rows = []

    def add(case, base, tag, setting, **extra):
        cid = stage({**base, "tag": tag, "max_iter": 6000, **extra})
        rows.append({"case_id": cid, "set": tag, "case": case, "setting": setting})

    for case, base in cases().items():
        add(case, base, "s12_ref", "reference", **REFERENCE)
        add(case, base, "s12_base1", "baseline")
        add(case, base, "s12_base2", "baseline")
        for c in CFL_CEILINGS:
            add(case, base, "s12_s1", f"cfl_max={c:g}", cfl_max=c)
        for t in LINEAR_TOLS:
            add(case, base, "s12_s2", f"linear_tol={t:g}", linear_tol=t)
    with open(HERE / "s12_cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for tag in sorted({r["set"] for r in rows}):
        ids = [r["case_id"] for r in rows if r["set"] == tag]
        text = queue.export_batch(ids, path=str(queue.queue_dir() / "batches" / f"{tag}.batch.json"))
        print(f"{tag}: {len(ids)} cases, batch bytes {len(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

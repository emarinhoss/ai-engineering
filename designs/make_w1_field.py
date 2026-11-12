"""Stage the W1 field campaign (docs/specs/task11_fno_exploration.md, experiment W1; task W1.3).

    python -m designs.make_w1_field

Training set: the pool designs of designs/pool_af_cases.csv other than the two test sections
(designs 1 and 4), each at -2, 2, 6 and 10 deg, coarse mesh, budget 6,000, writing a restart file
(tag w1_field). Also the three references of test design 4 at 2, 6 and 10 deg with the S1/S2
reference settings (tag w1_ref). Each section is read from its recorded pool_af run, never typed.
Writes designs/w1_field_cases.csv and one batch file. Chooses nothing: the designs are the
committed pool and the angles and settings are the rule's.
"""
import csv
import json
from pathlib import Path

from designs.make_e0 import stage
from designs.make_s12 import REFERENCE
from mcp_server import queue

HERE = Path(__file__).parent
ROOT = HERE.parent
TEST_DESIGNS = (1, 4)
FIELD_ANGLES = (-2.0, 2.0, 6.0, 10.0)
REF_DESIGN, REF_ANGLES = 4, (2.0, 6.0, 10.0)
KEYS = ("family", "camber_pct", "thickness_pct", "reynolds", "transition")


def sections():
    """{design index: section params} from each design's recorded pool_af run (its first angle)."""
    out = {}
    with open(HERE / "pool_af_cases.csv", newline="") as f:
        for r in csv.DictReader(f):
            i = int(r["index"])
            if r["tag"] == "pool_af" and i not in out:
                p = json.loads((ROOT / "runs" / "pool_af" / r["case_id"] / "params.json").read_text())
                out[i] = {k: p[k] for k in KEYS}
    return out


def plan():
    """[(design, tag, params)] in staging order: the field runs, then the design 4 references."""
    secs = sections()
    rows = []
    for i in sorted(secs):
        if i in TEST_DESIGNS:
            continue
        for a in FIELD_ANGLES:
            rows.append((i, "w1_field", {**secs[i], "mesh_level": "coarse", "alpha_deg": a,
                                         "max_iter": 6000, "save_restart": True, "tag": "w1_field"}))
    for a in REF_ANGLES:
        rows.append((REF_DESIGN, "w1_ref", {**secs[REF_DESIGN], "mesh_level": "coarse", "alpha_deg": a,
                                            "tag": "w1_ref", **REFERENCE}))
    return rows


def main():
    rows = []
    for design, tag, params in plan():
        cid = stage(params)
        rows.append({"case_id": cid, "set": tag, "design": design, "alpha_deg": params["alpha_deg"],
                     "reynolds": params["reynolds"]})
    with open(HERE / "w1_field_cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ids = [r["case_id"] for r in rows]
    text = queue.export_batch(ids, path=str(queue.queue_dir() / "batches" / "w1_field.batch.json"))
    print(f"w1_field: {len(ids)} cases, batch bytes {len(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

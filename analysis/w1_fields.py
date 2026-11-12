"""Field store of experiment W1 (docs/specs/task11_fno_exploration.md; task W1.5).

    python -m analysis.w1_fields --queue /content/drive/MyDrive/su2queue_w1 --out <dir>

Runs where the queue is (a Colab runtime with Drive mounted). For each w1_field run of
designs/w1_field_cases.csv: it enters the training set only if it is done, exited 0 and stopped on
the Cauchy rule inside its budget (the rule's condition); its restart_flow.csv is read with
worker/startfile.py and scaled. Writes <out>/fields.npz (case ids, design index, inputs
camber %, thickness %, log10 Re, angle deg, and the (B, n, 4) scaled fields) and
<out>/fields.json (counts, every excluded run with its reason, the sha256 of fields.npz).
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from worker import startfile as sf

ROOT = Path(__file__).resolve().parents[1]
MIN_FIELDS = 90


def entry(run_dir):
    """(inputs, scaled fields) of one finished run, or (None, reason) if it does not enter."""
    if not (run_dir / "status" / "2-done").exists():
        return None, "not done"
    r = json.loads((run_dir / "result.json").read_text())
    if r["run"]["exit_code"] != 0 or r["convergence"]["iterations"] >= r["params"]["max_iter"]:
        return None, f"exit {r['run']['exit_code']}, {r['convergence']['iterations']} iterations"
    p = r["params"]
    header, data = sf.read_restart((run_dir / "restart_flow.csv").read_text())
    x = [p["camber_pct"], p["thickness_pct"], math.log10(p["reynolds"]), p["alpha_deg"]]
    return x, sf.scale(sf.fields(header, data), p["reynolds"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--queue", required=True)
    ap.add_argument("--cases", default=str(ROOT / "designs" / "w1_field_cases.csv"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.cases, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["set"] == "w1_field"]
    ids, designs, X, F, excluded = [], [], [], [], {}
    for r in rows:
        x, f = entry(Path(a.queue) / "runs" / r["case_id"])
        if x is None:
            excluded[r["case_id"]] = f
            continue
        if F and f.shape != F[0].shape:
            raise ValueError(f"{r['case_id']}: field shape {f.shape} differs from {F[0].shape}")
        ids.append(r["case_id"])
        designs.append(int(r["design"]))
        X.append(x)
        F.append(f)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "fields.npz", case_ids=np.array(ids), designs=np.array(designs),
                        X=np.array(X), F=np.array(F))
    digest = hashlib.sha256((out / "fields.npz").read_bytes()).hexdigest()
    summary = {"training_fields": len(ids), "planned": len(rows), "gate_b_min": MIN_FIELDS,
               "gate_b_fields_ok": len(ids) >= MIN_FIELDS, "nodes": int(F[0].shape[0]) if F else 0,
               "excluded": excluded, "fields_npz_sha256": digest}
    (out / "fields.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "excluded"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare the confirmation run with the prediction and report how much the GP shrank (C2).

    python -m analysis.confirm --results RESULTS.csv --prediction DIR/result.json \
        --confirmed CONFIRMED.csv --out DIR

CONFIRMED.csv has the columns of RESULTS.csv and holds the confirmation run's row. Writes
DIR/confirm.json: simulated and predicted values, inside/outside the 90 percent interval (with
the direction of a miss), and the predictive std at that design before and after refitting the
GPs with the new row added. Pure reporting: nothing is tuned.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from analysis.pareto import fit_gps, load_rows, predict
from surrogate.replay import CONVERGED


def where(value, lo, hi):
    return "inside" if lo <= value <= hi else ("below" if value < lo else "above")


def run(results_rows, prediction, confirmed_rows, out_dir):
    """Returns the confirm.json dict (also written)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not prediction.get("feasible"):
        raise ValueError("the prediction file has no design (feasible is false)")
    t1, t2 = prediction["theta1_deg"], prediction["theta2_deg"]
    hits = [r for r in confirmed_rows if r.get("case_id") == prediction.get("case_id")]
    hits = hits or [r for r in confirmed_rows
                    if abs(float(r["theta1_deg"]) - t1) < 1e-3
                    and abs(float(r["theta2_deg"]) - t2) < 1e-3]
    if len(hits) != 1:
        raise ValueError(f"expected one confirmed row for the design ({t1}, {t2}), found {len(hits)}")
    row = hits[0]
    result = {"case_id": row.get("case_id"), "predicted_case_id": prediction.get("case_id"),
              "theta1_deg": t1, "theta2_deg": t2, "status": row["status"]}
    if row["status"] not in CONVERGED:
        result.update(c2_pass=None, note="confirmation run is not converged/stationary; no "
                      "comparison and no refit")
        (out_dir / "confirm.json").write_text(json.dumps(result, indent=2))
        return result

    rec_sim, q_sim = float(row["recovery_total"]), float(row["q_peak_W_m2"])
    rec, q = prediction["recovery_total"], prediction["q_peak_W_m2"]
    rec_where = where(rec_sim, rec["lo90"], rec["hi90"])
    q_where = where(q_sim, q["lo90"], q["hi90"])
    result["recovery_total"] = {"predicted_mean": rec["mean"], "lo90": rec["lo90"],
                                "hi90": rec["hi90"], "simulated": rec_sim, "position": rec_where,
                                "inside": rec_where == "inside",
                                "z": (rec_sim - rec["mean"]) / rec["std"]}
    result["q_peak_W_m2"] = {"predicted_median": q["median"], "lo90": q["lo90"],
                             "hi90": q["hi90"], "simulated": q_sim, "position": q_where,
                             "inside": q_where == "inside",
                             "z_log": (np.log(q_sim) - np.log(q["median"])) / q["log_std"]}
    result["q_cap_W_m2"] = prediction["q_cap_W_m2"]
    result["q_below_cap"] = q_sim <= prediction["q_cap_W_m2"]
    result["c2_pass"] = rec_where == "inside" and q_where == "inside"

    # refit with the new row (not twice if the results table already holds it)
    old_ids = {r.get("case_id") for r in results_rows}
    extra = [] if row.get("case_id") in old_ids else [row]
    th = np.array([[t1, t2]])
    before = predict(fit_gps(results_rows)[0], th, noise=True)
    after = predict(fit_gps(list(results_rows) + extra)[0], th, noise=True)
    result["refit"] = {
        "row_added": bool(extra),
        "recovery_total_std": {"before": float(before[1][0]), "after": float(after[1][0]),
                               "ratio": float(after[1][0] / before[1][0])},
        "log_q_std": {"before": float(before[3][0]), "after": float(after[3][0]),
                      "ratio": float(after[3][0] / before[3][0])},
        "recovery_total_mean": {"before": float(before[0][0]), "after": float(after[0][0])},
        "q_median_W_m2": {"before": float(np.exp(before[2][0])), "after": float(np.exp(after[2][0]))},
        "interval": "predictive std at the design, includes fitted noise"}
    (out_dir / "confirm.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--results", required=True)
    ap.add_argument("--prediction", required=True)
    ap.add_argument("--confirmed", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = run(load_rows(a.results), json.loads(Path(a.prediction).read_text()),
              load_rows(a.confirmed), a.out)
    print(f"C2 pass: {res['c2_pass']}")
    if res["c2_pass"] is not None:
        print(f"  recovery {res['recovery_total']['position']}, q {res['q_peak_W_m2']['position']}")


if __name__ == "__main__":
    main()

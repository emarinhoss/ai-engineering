"""Compare the confirmation run with the prediction and report how much the GP shrank (C2).

    python -m analysis.confirm --results RESULTS.csv --prediction DIR/result.json \
        --confirmed CONFIRMED.csv --out DIR

CONFIRMED.csv has the columns of RESULTS.csv and holds the confirmation run's row. Writes
DIR/confirm.json: simulated and predicted values, inside/outside the 90 percent interval (with
the direction of a miss), and the predictive std at that design before and after refitting the
GPs with the new row added. Pure reporting: nothing is tuned.

--family drone (Task 10): compare one high-fidelity design record against the inverse query's
inverse.json (analysis.inverse --family drone):

    python -m analysis.confirm --family drone --prediction DIR/inverse.json \
        --design-result RECORD/result.json --out DIR [--results RESULTS.csv]

RECORD/result.json is the analysis.drone_design output (params, section, result). Pass when
endurance_h and mtow_kg are BOTH inside their 90 percent intervals (C2). With --results the GPs
are also refitted with the confirmed design added and the predictive std before and after is
reported. The record's gates and section flags (the V6e bias flags of decision 8) are copied into
confirm.json. Writes DIR/confirm.json.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from analysis.pareto import DRONE_INPUTS, fit_gps, load_rows, predict
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


def run_drone(prediction, record, out_dir, results_rows=None):
    """Drone C2 check. prediction: inverse.json dict; record: drone_design result.json dict."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not prediction.get("feasible"):
        raise ValueError("the prediction file has no design (feasible is false)")
    design = prediction["design"]
    params = record["params"]
    off = [k for k in DRONE_INPUTS if abs(float(params[k]) - design[k]) > 1e-6]
    if off:
        raise ValueError(f"the record is not the predicted design: inputs differ in {off}")
    res = record["result"]
    end_sim, mtow_sim = float(res["endurance_h"]), float(res["mtow_kg"])
    end, mtow = prediction["endurance_h"], prediction["mtow_kg"]
    end_where = where(end_sim, end["lo90"], end["hi90"])
    mtow_where = where(mtow_sim, mtow["lo90"], mtow["hi90"])
    result = {"family": "drone", "design": design, "gates": list(res.get("gates", [])),
              "section_flags": list(record.get("section", {}).get("flags", [])),
              "endurance_h": {"predicted_mean": end["mean"], "lo90": end["lo90"],
                              "hi90": end["hi90"], "simulated": end_sim, "position": end_where,
                              "inside": end_where == "inside",
                              "z": (end_sim - end["mean"]) / end["std"]},
              "mtow_kg": {"predicted_median": mtow["median"], "lo90": mtow["lo90"],
                          "hi90": mtow["hi90"], "simulated": mtow_sim, "position": mtow_where,
                          "inside": mtow_where == "inside",
                          "z_log": (np.log(mtow_sim) - np.log(mtow["median"])) / mtow["log_std"]},
              "mtow_cap_kg": prediction["mtow_cap_kg"],
              "mtow_below_cap": mtow_sim <= prediction["mtow_cap_kg"],
              "c2_pass": end_where == "inside" and mtow_where == "inside"}
    if results_rows is not None:
        x = np.array([[float(params[k]) for k in DRONE_INPUTS]])
        new = {**{k: params[k] for k in DRONE_INPUTS}, "index": "confirm", "gates": "",
               "error": "", "endurance_h": end_sim, "mtow_kg": mtow_sim}
        before = predict(fit_gps(results_rows, "drone")[0], x, noise=True, family="drone")
        after = predict(fit_gps(list(results_rows) + [new], "drone")[0], x, noise=True,
                        family="drone")
        result["refit"] = {
            "endurance_std": {"before": float(before[1][0]), "after": float(after[1][0]),
                              "ratio": float(after[1][0] / before[1][0])},
            "log_mtow_std": {"before": float(before[3][0]), "after": float(after[3][0]),
                             "ratio": float(after[3][0] / before[3][0])},
            "interval": "predictive std at the design, includes fitted noise"}
    (out_dir / "confirm.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--family", choices=("inlet", "drone"), default="inlet")
    ap.add_argument("--results", help="required for inlet; optional for drone (refit)")
    ap.add_argument("--prediction", required=True)
    ap.add_argument("--confirmed", help="inlet: the confirmation run's row, CSV")
    ap.add_argument("--design-result", help="drone: analysis.drone_design result.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.family == "drone":
        if not a.design_result:
            ap.error("--design-result is required for --family drone")
        res = run_drone(json.loads(Path(a.prediction).read_text()),
                        json.loads(Path(a.design_result).read_text()), a.out,
                        load_rows(a.results) if a.results else None)
        print(f"C2 pass: {res['c2_pass']}")
        print(f"  endurance {res['endurance_h']['position']}, mtow {res['mtow_kg']['position']}")
        return
    if not (a.results and a.confirmed):
        ap.error("--results and --confirmed are required for --family inlet")
    res = run(load_rows(a.results), json.loads(Path(a.prediction).read_text()),
              load_rows(a.confirmed), a.out)
    print(f"C2 pass: {res['c2_pass']}")
    if res["c2_pass"] is not None:
        print(f"  recovery {res['recovery_total']['position']}, q {res['q_peak_W_m2']['position']}")


if __name__ == "__main__":
    main()

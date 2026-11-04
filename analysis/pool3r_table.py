"""Task 9: one table of the inlet3r pools, built only from the committed run records.

One row per Sobol point (set "hf": 160 points, seed 0; set "lf": 160 more, seed 1) that passed the
gates. Columns: the six inputs, total turning, and per fidelity the status and objectives:
  ns_status, ns_recovery_total, ns_q_peak_W_m2   laminar Navier-Stokes (hf set only)
  lf_status, lf_recovery_total, lf_q_peak_W_m2   Euler recovery, Eckert q_peak on the Euler wall state
Where the records are:
  NS on the container:  runs/pool3r/ns/<case_id>/result_partial.json
  NS from Colab (queue): runs/pool3r/<case_id>/result.json or error.json
  Euler (container):     runs/pool3r/euler/<case_id>/result_partial.json
The design case lists (designs/pool3r_ns_cases.json, 159 cases; designs/pool3r_euler_cases.json, 316)
tie a case_id to its set and index. Status is "converged" or the failure kind (error, diverged, timeout, ...); "missing" if no record.

One NS point has two records: inlet3r-f52ab49df3 timed out on Colab (worker limit 2400 s); every other
NS pool run had the container limit of 7200 s, so the container rerun under that limit gives its label
(ns_record says which record was used; the Colab record stays in runs/pool3r/).

    python -m analysis.pool3r_table --out runs/pool3r/pool3r_table.csv
"""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path("runs/pool3r")
INPUTS = ("theta1_deg", "theta2_deg", "theta3_deg", "mach", "altitude_km", "T_wall_K")
COLUMNS = ("set", "index") + INPUTS + ("theta_total_deg", "ns_case_id", "ns_record", "ns_status",
                                       "ns_recovery_total", "ns_q_peak_W_m2", "ns_iterations",
                                       "lf_case_id", "lf_status", "lf_recovery_total", "lf_q_peak_W_m2")


def read_record(case_id, folder):
    """(status, metrics, iterations, record path) for one case, or ("missing", {}, None, None)."""
    container = ROOT / folder / case_id / "result_partial.json"
    if container.exists():
        r = json.loads(container.read_text())
        return r["history_summary"]["status"], r.get("metrics") or {}, r["run"]["iterations"], str(container)
    if folder == "ns":                                            # Colab records, via the queue
        result, error = ROOT / case_id / "result.json", ROOT / case_id / "error.json"
        if result.exists():
            r = json.loads(result.read_text())
            return r["convergence"]["status"], r.get("metrics") or {}, r["run"]["iterations"], str(result)
        if error.exists():
            return json.loads(error.read_text())["reason"], {}, None, str(error)
    return "missing", {}, None, None


def build():
    ns = {(c["set"], c["index"]): c for c in json.loads(Path("designs/pool3r_ns_cases.json").read_text())}
    lf = {(c["set"], c["index"]): c for c in json.loads(Path("designs/pool3r_euler_cases.json").read_text())}
    rows = []
    for key in sorted(lf, key=lambda k: (k[0] != "hf", k[1])):     # every gate-passing point has an Euler run
        p = lf[key]["params"]
        row = {"set": key[0], "index": key[1], **{k: p[k] for k in INPUTS}}
        row["theta_total_deg"] = sum(p[f"theta{i}_deg"] for i in (1, 2, 3))
        st, m, _, _ = read_record(lf[key]["name"], "euler")
        row.update(lf_case_id=lf[key]["name"], lf_status=st,
                   lf_recovery_total=m.get("recovery_total"), lf_q_peak_W_m2=m.get("q_peak_lf_W_m2"))
        if key in ns:
            st, m, it, path = read_record(ns[key]["name"], "ns")
            assert all(abs(ns[key]["params"][k] - p[k]) < 1e-9 for k in INPUTS), key
            row.update(ns_case_id=ns[key]["name"], ns_record=path, ns_status=st, ns_iterations=it,
                       ns_recovery_total=m.get("recovery_total"), ns_q_peak_W_m2=m.get("q_peak_W_m2"))
        rows.append(row)
    return rows


def write(rows, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def load(path="runs/pool3r/pool3r_table.csv"):
    """Rows as dicts with numbers converted (None for empty cells)."""
    def num(v):
        try:
            return float(v)
        except ValueError:
            return None if v == "" else v
    with open(path) as f:
        return [{k: (num(v) if k not in ("set", "ns_case_id", "ns_record", "ns_status", "lf_case_id",
                                         "lf_status") else v) for k, v in r.items()} for r in csv.DictReader(f)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="runs/pool3r/pool3r_table.csv")
    a = ap.parse_args()
    rows = build()
    write(rows, a.out)
    from collections import Counter
    print(len(rows), "rows;", "NS:", dict(Counter(r.get("ns_status") for r in rows if r["set"] == "hf")),
          "Euler:", dict(Counter(r["lf_status"] for r in rows)))


if __name__ == "__main__":
    main()

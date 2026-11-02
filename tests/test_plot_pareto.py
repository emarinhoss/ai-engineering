"""Pareto plot on a hand-made pareto.csv and inverse result: the PNG file is written."""
import csv
import json

import pytest

from analysis.plot_pareto import plot_pareto

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FIELDS = ["kind", "case_id", "theta1_deg", "theta2_deg", "recovery_total", "q_peak_W_m2",
          "rec_p05", "rec_p50", "rec_p95"]
INVERSE = {"theta1_deg": 12.0, "theta2_deg": 7.07,
           "recovery_total": {"mean": 0.3449, "lo90": 0.3448, "hi90": 0.3450},
           "q_peak_W_m2": {"median": 31400.0, "lo90": 31380.0, "hi90": 31420.0},
           "q_cap_W_m2": 31450.0}


def write_pareto(path):
    observed = [(0.40, 46000.0), (0.39, 44000.0), (0.41, 50000.0)]
    predicted = [(0.38 + 0.01 * k, 40000.0 + 2000.0 * k) for k in range(5)]
    band = [(42000.0, 0.39), (46000.0, 0.40), (50000.0, 0.41)]
    rows = [{"kind": "observed", "case_id": f"c{i}", "theta1_deg": 10 + i, "theta2_deg": 12 - i,
             "recovery_total": r, "q_peak_W_m2": q} for i, (r, q) in enumerate(observed)]
    rows += [{"kind": "predicted", "theta1_deg": 10.0, "theta2_deg": 10.0 + k,
              "recovery_total": r, "q_peak_W_m2": q} for k, (r, q) in enumerate(predicted)]
    rows += [{"kind": "band", "q_peak_W_m2": q, "rec_p05": r - 0.001, "rec_p50": r,
              "rec_p95": r + 0.001} for q, r in band]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


@pytest.mark.parametrize("feasible", [None, True, False])
def test_plot_pareto_writes_png(tmp_path, feasible):
    csv_path = tmp_path / "pareto.csv"
    write_pareto(csv_path)
    inverse = None
    if feasible is not None:
        inverse = tmp_path / "result.json"
        inverse.write_text(json.dumps({**INVERSE, "feasible": feasible}))
    out = tmp_path / "pareto.png"
    assert plot_pareto(csv_path, out, 0.09, 1.68, inverse) == 3
    assert out.read_bytes()[:8] == PNG_MAGIC

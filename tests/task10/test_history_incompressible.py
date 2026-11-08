"""summarize and the airfoil2d metrics on a history with the incompressible solver's columns."""
import numpy as np

from postprocess import metrics
from postprocess.history import summarize

COLUMNS = ["Time_Iter", "Outer_Iter", "Inner_Iter", "rms[P]", "rms[U]", "rms[V]", "rms[nu]",
           "max[P]", "max[U]", "max[V]", "max[nu]", "LinSolIter", "LinSolRes", "LinSolIterTurb",
           "LinSolResTurb", "Min DT", "Max DT", "Min CFL", "Max CFL", "Avg CFL", "RefForce", "CD",
           "CL", "CSF", "CMx", "CMy", "CMz", "CFx", "CFy", "CFz", "CEff"]


def write(path, cd_wiggle=0.0, n=400):
    i = np.arange(n)
    rmsp = -3.0 - 6.0 * i / (n - 1)
    cl = 0.8 + 0.2 * np.exp(-i / (0.05 * n))
    cd = 0.02 + 0.01 * np.exp(-i / (0.05 * n))
    cd = cd * (1 + cd_wiggle * np.where(i >= int(0.7 * n), np.sin(i), 0.0))
    with open(path, "w") as f:
        f.write(",".join(f'"{c}"' for c in COLUMNS) + "\n")
        for k in range(n):
            row = {c: 0.0 for c in COLUMNS}
            row.update({"Inner_Iter": k, "rms[P]": rmsp[k], "rms[U]": rmsp[k] - 1,
                        "rms[V]": rmsp[k] - 1, "rms[nu]": rmsp[k] - 2, "CD": cd[k], "CL": cl[k],
                        "CMz": -0.05, "Avg CFL": 10.0})
            f.write(",".join(repr(float(row[c])) for c in COLUMNS) + "\n")
    return path


def test_converged_on_rms_p(tmp_path):
    s = summarize(write(tmp_path / "history.csv"))
    assert s["residual_column"] == "rms[P]"
    assert s["status"] == "converged"
    assert s["drop_orders"] >= 5
    assert s["drift_pct"]["cl"] is not None and s["drift_pct"]["cd"] is not None
    assert s["drift_pct"]["recovery_total"] is None


def test_oscillating_cd_is_not_converged(tmp_path):
    s = summarize(write(tmp_path / "history.csv", cd_wiggle=0.1))
    assert s["residual_column"] == "rms[P]"
    assert s["drift_pct"]["cd"] > 15
    assert s["status"] == "not_converged"


def test_airfoil2d_metrics_on_these_columns(tmp_path):
    write(tmp_path / "history.csv")
    out = metrics._airfoil2d(tmp_path, {"alpha_deg": 2.0})
    assert abs(out["cl"] - 0.8) < 0.01 and abs(out["cd"] - 0.02) < 0.001
    assert out["cm"] == -0.05 and out["alpha_deg"] == 2.0

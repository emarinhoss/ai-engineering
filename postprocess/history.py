"""Read SU2's history.csv and classify convergence (00_decisions.md section 6)."""
import csv
import math

import numpy as np

DROP_MIN = 5.0     # orders of magnitude of density residual for "converged"
DRIFT_MAX = 0.2    # percent, over the last 20 percent of iterations


def load(history_csv):
    """Return {column name: float array}. Header quotes and spaces are stripped."""
    with open(history_csv, newline="") as f:
        rows = list(csv.reader(f))
    names = [h.strip().strip('"').strip() for h in rows[0]]
    data = [[_to_float(v) for v in r] for r in rows[1:] if r]
    arr = np.array(data, dtype=float).reshape(len(data), len(names))
    return {name: arr[:, i] for i, name in enumerate(names)}


def _to_float(text):
    try:
        return float(text.strip().strip('"'))
    except ValueError:
        return math.nan


def find_column(cols, *substrings):
    """The one column whose name contains all substrings (case-insensitive)."""
    wanted = [s.lower() for s in substrings]
    hits = [c for c in cols if all(s in c.lower() for s in wanted)]
    if len(hits) != 1:
        raise KeyError(f"{len(hits)} columns match {substrings}; available: {list(cols)}")
    return hits[0]


def _try_find(cols, *alternatives):
    """First alternative substring that matches exactly one column, else None."""
    for sub in alternatives:
        try:
            return find_column(cols, sub)
        except KeyError:
            continue
    return None


def drift_pct(values, tail=0.2):
    """(max - min) over the last `tail` of the series, divided by the final |value|, in percent."""
    n = len(values)
    window = values[-max(2, math.ceil(tail * n)):]
    final = abs(values[-1])
    if final == 0 or not np.all(np.isfinite(window)):
        return None
    return float((window.max() - window.min()) / final * 100.0)


def summarize(history_csv, params=None):
    """The "convergence" block of result.json. `params` is accepted for the interface contract.

    Drift of recovery_total is taken from the Avg_TotalPress column (the objective itself needs
    the surface data) and drift of q_peak from the maximum heat flux column; absent columns
    give None. Status: diverged (non-finite residual), converged (drop >= 5 and every available
    drift < 0.2), stationary (at least one drift available, all < 0.2, drop < 5), else
    not_converged. Timeout and error are decided by the worker, not here.
    """
    cols = load(history_csv)
    res = cols[find_column(cols, "rms[rho]")]
    if len(res) == 0:
        raise ValueError(f"{history_csv} has no rows")

    finite = res[np.isfinite(res)]
    start = float(np.max(res[:50][np.isfinite(res[:50])])) if np.any(np.isfinite(res[:50])) else None
    end = float(res[-1]) if np.isfinite(res[-1]) else None
    drop = start - end if start is not None and end is not None else None

    drifts = {"recovery_total": None, "q_peak": None}
    col = _try_find(cols, "totalpress")
    if col:
        drifts["recovery_total"] = drift_pct(cols[col])
    col = _try_find(cols, "maxhf", "maximum_heatflux")
    if col:
        drifts["q_peak"] = drift_pct(cols[col])
    available = [d for d in drifts.values() if d is not None]
    steady = all(d < DRIFT_MAX for d in available)

    if len(finite) < len(res):
        status = "diverged"
    elif steady and drop >= DROP_MIN:
        status = "converged"
    elif steady and available:
        status = "stationary"
    else:
        status = "not_converged"

    return {"rms_rho_log10_start": start, "rms_rho_log10_end": end, "drop_orders": drop,
            "drift_pct": drifts, "status": status, "iterations": len(res)}

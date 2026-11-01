import numpy as np
import pytest

from postprocess.history import find_column, load, summarize

HEADER = ('"Time_Iter","Outer_Iter","Inner_Iter",   "rms[Rho]",   "rms[RhoU]",'
          '   "Avg_TotalPress",   "Total_HeatFlux",   "MaxHF"')


def write(path, rho, p0=None, maxhf=None, header=HEADER):
    n = len(rho)
    p0 = np.full(n, 1.8e5) if p0 is None else p0
    maxhf = np.full(n, 3.0e4) if maxhf is None else maxhf
    with open(path, "w") as f:
        f.write(header + "\n")
        f.writelines(f"0, 0, {i}, {float(rho[i])!r}, {float(rho[i]) - 0.3!r}, "
                     f"{float(p0[i])!r}, 1.0, {float(maxhf[i])!r}\n" for i in range(n))
    return path


def decay(n=1000, orders=8.0, floor=None):
    rho = -2.0 - orders * np.arange(n) / (n - 1)
    return rho if floor is None else np.maximum(rho, floor)


def settle(n, amp=0.05, tau=0.1):
    """Quantity that approaches 1 and wiggles with relative size `amp` percent at the end."""
    i = np.arange(n)
    return 1.0 + 0.5 * np.exp(-i / (tau * n)) + amp / 100 * 0.5 * np.sin(i)


def test_load_and_find_column(tmp_path):
    cols = load(write(tmp_path / "h.csv", decay(10)))
    assert "rms[Rho]" in cols and "MaxHF" in cols and "Inner_Iter" in cols
    assert find_column(cols, "totalpress") == "Avg_TotalPress"
    assert find_column(cols, "RMS[RHO]") == "rms[Rho]"
    with pytest.raises(KeyError, match="available"):
        find_column(cols, "nothere")
    with pytest.raises(KeyError):
        find_column(cols, "rms")  # ambiguous


def test_converged(tmp_path):
    n = 1000
    out = summarize(write(tmp_path / "h.csv", decay(n), settle(n) * 1.8e5, settle(n) * 3e4), {})
    assert out["status"] == "converged"
    assert out["iterations"] == n
    assert out["drop_orders"] == pytest.approx(8.0, abs=0.05)
    assert out["rms_rho_log10_start"] == pytest.approx(-2.0)
    assert out["rms_rho_log10_end"] == pytest.approx(-10.0)
    assert out["drift_pct"]["recovery_total"] < 0.2 and out["drift_pct"]["q_peak"] < 0.2


def test_stationary(tmp_path):
    n = 1000
    out = summarize(write(tmp_path / "h.csv", decay(n, 3.0), settle(n) * 1.8e5, settle(n) * 3e4), {})
    assert out["status"] == "stationary"
    assert out["drop_orders"] == pytest.approx(3.0, abs=0.05)


def test_not_converged_when_objective_drifts(tmp_path):
    n = 1000
    drifting = 3e4 * (1 + 0.05 * np.sin(np.arange(n) / 30))  # about 10 percent swing
    out = summarize(write(tmp_path / "h.csv", decay(n), maxhf=drifting), {})
    assert out["status"] == "not_converged"
    assert out["drift_pct"]["q_peak"] > 0.2


def test_diverged(tmp_path):
    rho = decay(500, 4.0)
    rho[300:] = np.nan
    out = summarize(write(tmp_path / "h.csv", rho), {})
    assert out["status"] == "diverged"
    assert out["rms_rho_log10_end"] is None and out["drop_orders"] is None
    rho = decay(500, 4.0)
    rho[400] = np.inf
    assert summarize(write(tmp_path / "h2.csv", rho), {})["status"] == "diverged"


def test_missing_columns_are_null(tmp_path):
    n = 600
    header = '"Inner_Iter","rms[Rho]"'
    path = tmp_path / "h.csv"
    path.write_text(header + "\n" + "\n".join(f"{i}, {float(r)!r}" for i, r in enumerate(decay(n))) + "\n")
    out = summarize(path, {})
    assert out["drift_pct"] == {"recovery_total": None, "q_peak": None}
    assert out["status"] == "converged"           # nothing to disagree with a 8 order drop
    flat = tmp_path / "flat.csv"
    flat.write_text(header + "\n" + "\n".join(f"{i}, {float(r)!r}" for i, r in enumerate(decay(n, 3.0))) + "\n")
    assert summarize(flat, {})["status"] == "not_converged"   # no drift data, residual stalled

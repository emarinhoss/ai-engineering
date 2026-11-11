"""analysis.history_cost: settle iteration and the recorded smoke2 run."""
import numpy as np

from analysis import history_cost as hc


def test_last_outside_counts_iterations_before_the_band_holds():
    x = np.array([2.0, 1.2, 0.9, 1.004, 1.0])
    assert hc.last_outside(x, 0.05) == 3 and hc.last_outside(x, 0.5) == 1
    assert hc.last_outside(np.ones(4), 0.01) == 0


def test_recorded_smoke2_run():
    r = hc.analyse(hc.Path(hc.__file__).resolve().parents[1] / "runs/smoke2/airfoil2d-51d551f2cc")
    assert r["iterations"] == 4867 and r["linear"]["share_at_cap"] == 0.0
    assert r["cfl"]["first_iter_at_ceiling"] < 100 and r["cfl"]["ceiling"] == 20.0

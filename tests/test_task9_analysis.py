"""Small checks of the Task 9 analysis helpers (no pool data needed)."""
import numpy as np

from analysis.feas3r import folds, rank_auc
from analysis.inverse3r import ENVELOPE, params_for
from physics.gates import check


def test_folds_are_stratified():
    y = np.array([0] * 8 + [1] * 151)
    f = folds(y, k=5, seed=0)
    for k in range(5):
        assert (y[f == k] == 0).sum() in (1, 2)          # 8 failures over 5 folds
        assert abs((f == k).sum() - 159 / 5) < 2


def test_rank_auc():
    y = np.array([1, 1, 0, 0])
    assert rank_auc(np.array([0.9, 0.8, 0.1, 0.2]), y) == 1.0
    assert rank_auc(np.array([0.1, 0.2, 0.9, 0.8]), y) == 0.0
    assert rank_auc(np.array([0.5, 0.5, 0.5, 0.5]), y) == 0.5


def test_envelope_grid_and_params():
    assert len(ENVELOPE) == 125
    p = params_for([7.0, 7.0, 7.0], (4.0, 30.0, 300.0))
    assert p["family"] == "inlet3r" and p["tag"] == "confirm3r" and p["max_iter"] == 8000
    assert check(p) == []                                  # the nominal point passes every gate

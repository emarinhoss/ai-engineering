"""Hypervolume, Pareto front and EHVI on hand-computable cases (minimisation)."""
import numpy as np
import torch

from surrogate.acquisition import (
    DT,
    argmax_ties,
    ehvi_mc,
    hvi_2d,
    hypervolume_2d,
    max_variance,
    pareto_front,
    ref_point,
)

FRONT = np.array([[1.0, 4.0], [2.0, 2.0], [4.0, 1.0]])
REF = np.array([5.0, 5.0])
# union of boxes: 4 (from (1,4)) + 6 (adds [2,5]x[2,4]) + 1 (adds [4,5]x[1,2]) = 11
HV = 11.0


def test_hypervolume_hand_value():
    assert hypervolume_2d(FRONT, REF) == HV
    assert hypervolume_2d(FRONT[::-1], REF) == HV      # order does not matter


def test_dominated_and_outside_points_change_nothing():
    extra = np.array([[3.0, 4.0], [2.5, 3.0], [4.5, 4.5], [6.0, 0.0], [0.0, 6.0]])
    assert hypervolume_2d(np.vstack([FRONT, extra]), REF) == HV


def test_pareto_front_indices():
    F = np.vstack([FRONT, [[3.0, 4.0], [2.0, 2.0]]])   # one dominated, one duplicate
    assert set(pareto_front(F)) == {0, 1, 2, 4}


def test_ref_point():
    F = np.array([[0.0, 10.0], [2.0, 20.0]])
    assert np.allclose(ref_point(F, 0.1), [2.2, 21.0])


def test_hvi_equals_difference_of_hypervolumes():
    rng = np.random.default_rng(0)
    pts = rng.uniform(0, 6, size=(50, 2))
    got = hvi_2d(torch.tensor(pts, dtype=DT), FRONT, REF).numpy()
    want = [hypervolume_2d(np.vstack([FRONT, p]), REF) - HV for p in pts]
    assert np.allclose(got, want, atol=1e-12)


def test_ehvi_dominated_is_zero_and_beyond_front_is_large():
    mean1 = [4.5, 0.0, 3.0]
    mean2 = [4.5, 0.0, 1.5]
    var = [1e-6] * 3
    e = ehvi_mc(mean1, var, mean2, var, FRONT, REF, n_samples=64, seed=0)
    assert e[0] < 1e-3                       # deep inside the dominated region
    assert abs(e[1] - (25.0 - HV)) < 0.01    # (0, 0) dominates the whole box: 25 - 11
    # (3, 1.5): staircase height is 2 on [3, 4) -> gain 1 x 0.5; on [4, 5) it is 1 < 1.5 -> 0
    assert abs(e[2] - 0.5) < 0.01


def test_ehvi_is_seeded():
    a = ehvi_mc([1.0, 3.0], [0.5, 0.5], [1.0, 3.0], [0.5, 0.5], FRONT, REF, seed=7)
    b = ehvi_mc([1.0, 3.0], [0.5, 0.5], [1.0, 3.0], [0.5, 0.5], FRONT, REF, seed=7)
    assert (a == b).all()


def test_max_variance_and_ties():
    assert np.allclose(max_variance([1, 2], [0.5, 0.25]), [1.5, 2.25])
    assert argmax_ties([0.0, 0.0, 0.0], [1.0, 3.0, 2.0]) == 1      # all tied: larger variance
    assert argmax_ties([0.0, 2.0, 1.0], [9.0, 1.0, 1.0]) == 1      # clear winner ignores tiebreak

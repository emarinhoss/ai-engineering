"""Two-objective acquisition functions. All objectives are in minimisation form (see
surrogate.replay.to_objectives): f1 = -recovery_total, f2 = log(q_peak_W_m2)."""
import numpy as np
import torch

DT = torch.float64


def pareto_front(F):
    """Indices of the non-dominated rows of F (n, 2), minimisation.

    Row j dominates row i if F[j] <= F[i] in both objectives and < in at least one.
    """
    F = np.asarray(F, dtype=float)
    le = (F[:, None, :] <= F[None, :, :]).all(-1)   # le[j, i]: j no worse than i everywhere
    lt = (F[:, None, :] < F[None, :, :]).any(-1)    # lt[j, i]: j strictly better somewhere
    dominated = (le & lt).any(0)
    return np.flatnonzero(~dominated)


def ref_point(F, margin=0.1):
    """Reference point = nadir + margin * range, per objective.

    "Nadir" here is the componentwise worst value over all rows of F (not only over its
    Pareto front), so every row of F lies inside the reference box.
    """
    F = np.asarray(F, dtype=float)
    worst, best = F.max(0), F.min(0)
    return worst + margin * (worst - best)


def _staircase(front, ref):
    """Non-dominated rows of `front` inside the reference box, sorted by f1 ascending."""
    front = np.asarray(front, dtype=float).reshape(-1, 2)
    front = front[(front < np.asarray(ref)).all(1)]
    if len(front):
        front = front[pareto_front(front)]
        front = front[np.argsort(front[:, 0])]
    return front


def hypervolume_2d(F, ref):
    """Area dominated by the rows of F and bounded by ref (minimisation), exact.

    Sort by f1; sweep left to right keeping the lowest f2 seen so far. A point adds a strip
    of width (ref1 - f1) and height (best f2 so far - its f2) if it lowers the f2 level;
    dominated points add nothing.
    """
    F = np.asarray(F, dtype=float).reshape(-1, 2)
    F = F[(F < np.asarray(ref)).all(1)]
    F = F[np.argsort(F[:, 0], kind="stable")]
    hv, level = 0.0, float(ref[1])
    for f1, f2 in F:
        if f2 < level:
            hv += (ref[0] - f1) * (level - f2)
            level = f2
    return hv


def hvi_2d(points, front, ref):
    """Hypervolume improvement of each point in `points` (P, 2) over `front` (torch, exact).

    The front is a staircase: for x in segment k its height is h_k (f2 of the last front point
    with f1 <= x; ref2 before the first). A new point (a, b) adds, over every segment, the
    overlap width of [a, ref1] with the segment times max(h_k - b, 0).
    """
    s = _staircase(front, ref)
    left = torch.tensor(np.r_[-np.inf, s[:, 0]], dtype=DT)
    right = torch.tensor(np.r_[s[:, 0], ref[0]], dtype=DT)
    height = torch.tensor(np.r_[ref[1], s[:, 1]], dtype=DT)
    a, b = points[:, :1], points[:, 1:]
    width = (right - torch.maximum(left, a)).clamp(min=0)
    return (width * (height - b).clamp(min=0)).sum(1)


def ehvi_mc(mean1, var1, mean2, var2, front, ref, n_samples=128, seed=0):
    """Monte-Carlo expected hypervolume improvement of each candidate.

    mean/var are the posterior mean and variance of f1 and f2 at the candidates (independent
    Gaussians). `front` is the observed objective array (n_obs, 2); its non-dominated part is
    used. Draws n_samples (f1, f2) per candidate with a seeded generator and averages the
    exact hypervolume improvement. Returns a numpy array, one value per candidate.
    """
    mean = torch.stack([torch.as_tensor(mean1, dtype=DT), torch.as_tensor(mean2, dtype=DT)], -1)
    std = torch.sqrt(torch.stack([torch.as_tensor(var1, dtype=DT),
                                  torch.as_tensor(var2, dtype=DT)], -1))
    gen = torch.Generator().manual_seed(seed)
    z = torch.randn(mean.shape[0], n_samples, 2, generator=gen, dtype=DT)
    samples = mean[:, None, :] + std[:, None, :] * z               # (candidates, samples, 2)
    hvi = hvi_2d(samples.reshape(-1, 2), front, ref)
    return hvi.reshape(mean.shape[0], n_samples).mean(1).numpy()


def max_variance(var1, var2):
    """Pure exploration score: sum of the two posterior variances. The caller passes them in
    standardised units so the two outputs count equally."""
    return np.asarray(var1, dtype=float) + np.asarray(var2, dtype=float)


def argmax_ties(score, tiebreak, tol=1e-12):
    """Index of the largest score; among scores within tol of the largest, the largest tiebreak."""
    score, tiebreak = np.asarray(score), np.asarray(tiebreak)
    tied = np.flatnonzero(score >= score.max() - tol)
    return int(tied[np.argmax(tiebreak[tied])])

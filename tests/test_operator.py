"""Task 4c: profile extraction, FNO and PCA + GP on synthetic profiles, the comparison end to end."""
import csv
import json

import numpy as np
import torch

from analysis import operator_compare
from analysis.profiles import extract
from surrogate.fno import FNOEnsemble, SpectralConv1d
from surrogate.pca_gp import PCAGP

RUN = "runs/dev/2026-11-01_inlet_grid_study_ef03/8_8_medium"


def family(X, n=128):
    """A smooth family of profiles: a bump whose position and height follow the two inputs."""
    s = torch.linspace(0, 1, n, dtype=torch.float64)
    X = torch.as_tensor(X, dtype=torch.float64)
    return torch.exp(-((s - 0.2 - 0.5 * X[:, :1]) ** 2) / 0.02) * (1 + X[:, 1:]) + 0.3 * s + 1.0


def test_profile_reproduces_recorded_peak():
    params = json.load(open(f"{RUN}/params.json"))
    q_peak = json.load(open(f"{RUN}/metrics.json"))["q_peak_W_m2"]
    p = extract(params, f"{RUN}/surface_flow.dat.gz")
    assert p["q_peak_nodes"] == q_peak                      # same nodes as the objective
    assert 0.995 * q_peak <= p["q"].max() <= q_peak         # interpolation can only lower the peak
    assert p["q"].shape == (128,) and np.all(p["q"] > 0)
    assert p["x_start"] == 0.1                              # ramp 2 starts at the corner X1


def test_spectral_layer_keeps_only_low_modes():
    torch.manual_seed(0)
    layer = SpectralConv1d(width=2, modes=4)
    h = torch.randn(1, 2, 64)
    out_hat = torch.fft.rfft(layer(h))
    assert torch.allclose(out_hat[..., 4:], torch.zeros_like(out_hat[..., 4:]), atol=1e-5)


def test_pca_gp_and_fno_fit_a_smooth_family():
    g = torch.Generator().manual_seed(0)
    X, Xt = torch.rand((40, 2), generator=g, dtype=torch.float64), torch.rand((10, 2), generator=g, dtype=torch.float64)
    Y, Yt = torch.log(family(X)), torch.log(family(Xt))
    mu, sd = Y.mean(0), (Y - Y.mean(0)).std()
    for model in (PCAGP(), FNOEnsemble(members=2, steps=600)):
        mean, var = model.fit(X, (Y - mu) / sd).predict(Xt)
        err = ((mu + sd * mean - Yt) ** 2).mean().sqrt().item()
        assert err < 0.25 * Yt.std().item(), type(model).__name__
        assert (var > 0).all()


def test_comparison_runs_end_to_end(tmp_path, monkeypatch):
    g = torch.Generator().manual_seed(1)
    theta = torch.stack([5 + 7 * torch.rand(30, generator=g, dtype=torch.float64),
                         5 + 9 * torch.rand(30, generator=g, dtype=torch.float64)], 1)
    X = (theta - torch.tensor([5.0, 5.0], dtype=torch.float64)) / torch.tensor([7.0, 9.0], dtype=torch.float64)
    Q = 1e4 * family(X)
    path = tmp_path / "profiles.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "theta1_deg", "theta2_deg", "x_start_m", "x_end_m"] + [f"q_{i}" for i in range(128)])
        for i in range(30):
            w.writerow([f"c{i:02d}", *theta[i].tolist(), 0.1, 0.25] + Q[i].tolist())
    monkeypatch.setattr(operator_compare, "SMALL_N", 12)
    monkeypatch.setattr(operator_compare, "REPEATS", 1)
    monkeypatch.setattr(operator_compare, "FOLDS", 2)
    monkeypatch.setitem(operator_compare.MODELS, "fno", lambda: FNOEnsemble(members=2, steps=150))
    operator_compare.compare(path, tmp_path, jobs=2)
    rows = list(csv.DictReader(open(tmp_path / "operator_compare.csv")))
    assert {r["model"] for r in rows} == {"pca_gp", "fno", "scalar_gp"}
    assert {r["regime"] for r in rows} == {"A", "B"}
    held_A = {r["case_id"] for r in rows if r["regime"] == "A" and r["metric"] == "rel_l2" and r["model"] == "fno"}
    assert len(held_A) == 30                                # every design predicted once in regime A
    png = operator_compare.report(tmp_path, tmp_path, "op", path)
    assert png.stat().st_size > 20_000 and (tmp_path / "op_summary.md").exists()

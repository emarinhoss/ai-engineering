"""MLP ensemble (surrogate/mlp.py): fit quality, determinism, uncertainty, replay integration."""
import csv

import numpy as np
import torch

from surrogate.gp import DT, Standardizer
from surrogate.mlp import MLPEnsemble
from surrogate.replay import COLUMNS, STRATEGIES, run
from surrogate.synthetic import make_pool


def smooth(X):
    """A smooth, mildly curved function of two unit-square inputs."""
    return torch.sin(2.0 * X[:, 0]) + 0.5 * X[:, 1] ** 2


def training_set(n=30, seed=0):
    g = torch.Generator().manual_seed(seed)
    X = torch.rand((n, 2), generator=g, dtype=DT)
    return X, smooth(X)


def test_fits_a_smooth_function():
    X, y = training_set()
    st = Standardizer().fit(y)
    ens = MLPEnsemble().fit(X, st.transform(y))
    Xt, yt = training_set(n=200, seed=1)
    mean, var = ens.predict(Xt)
    rmse = torch.sqrt(((st.inverse(mean) - yt) ** 2).mean()).item()
    assert rmse < 0.02 * (yt.max() - yt.min()).item()            # within 2 percent of the range
    assert (var > 0).all()


def test_deterministic_given_data():
    X, y = training_set(n=12)
    a = MLPEnsemble(steps=200).fit(X, y).predict(X[:3])
    b = MLPEnsemble(steps=200).fit(X, y).predict(X[:3])
    assert torch.equal(a[0], b[0]) and torch.equal(a[1], b[1])


def test_noise_adds_training_mse():
    X, y = training_set(n=12)
    ens = MLPEnsemble(steps=200).fit(X, y)
    _, v = ens.predict(X[:4])
    _, vn = ens.predict(X[:4], noise=True)
    assert torch.allclose(vn - v, ens.noise_var().expand(4))


def test_spread_grows_away_from_the_data():
    g = torch.Generator().manual_seed(2)
    X = 0.5 * torch.rand((20, 2), generator=g, dtype=DT)        # data only in the lower-left quarter
    ens = MLPEnsemble().fit(X, smooth(X))
    _, v_in = ens.predict(torch.tensor([[0.25, 0.25]], dtype=DT))
    _, v_out = ens.predict(torch.tensor([[0.95, 0.95]], dtype=DT))
    assert v_out.item() > 10 * v_in.item()


def test_replay_runs_with_mlp(tmp_path):
    out = tmp_path / "replay_mlp.csv"
    rows = run(make_pool(), strategies=("random", "al_ehvi"), seeds=range(1), n_max=12,
               out_csv=out, model="mlp")
    with open(out) as f:
        read = list(csv.DictReader(f))
    assert tuple(read[0].keys()) == COLUMNS and len(read) == len(rows)
    assert {r["strategy"] for r in read} == {"random", "al_ehvi"}
    assert {int(r["n"]) for r in read} == {8, 12}
    assert any(r["metric"] == "hyp_recovery_members" for r in read)
    values = {r["metric"]: float(r["value"]) for r in read if r["strategy"] == "al_ehvi" and r["n"] == "12"}
    assert np.isfinite(values["rmse_recovery"]) and 0.0 <= values["cov90_q"] <= 1.0
    assert set(STRATEGIES) >= {r["strategy"] for r in read}

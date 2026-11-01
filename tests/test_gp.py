"""GP checks: accuracy on a smooth function, agreement with a numpy reference, gradients."""
import math

import numpy as np
import torch

from surrogate.gp import DT, GP, JITTER, Standardizer, scale_inputs


def matern52(A, B, ls, sf2):
    d = np.sqrt((((A[:, None, :] - B[None, :, :]) / ls) ** 2).sum(-1))
    return sf2 * (1 + math.sqrt(5) * d + 5.0 / 3.0 * d**2) * np.exp(-math.sqrt(5) * d)


# fixed 6-point 2D dataset and 5 test points
X6 = np.array([[0.1, 0.2], [0.8, 0.1], [0.4, 0.5], [0.9, 0.9], [0.2, 0.8], [0.6, 0.35]])
Y6 = np.array([0.3, -1.1, 0.4, 1.4, -0.2, -0.6])
XS5 = np.array([[0.15, 0.25], [0.5, 0.5], [0.7, 0.2], [0.3, 0.9], [0.95, 0.6]])


def test_sine_rmse():
    # (a) 20 noiseless points of one sine period; RMSE at 200 interior points
    x = torch.linspace(0, 1, 20, dtype=DT)[:, None]
    y = torch.sin(2 * math.pi * x[:, 0])
    st = Standardizer().fit(y)
    gp = GP().fit(x, st.transform(y))
    xs = torch.linspace(0.025, 0.975, 200, dtype=DT)[:, None]
    mean, _ = gp.predict(xs)
    rmse = torch.sqrt(((st.inverse(mean) - torch.sin(2 * math.pi * xs[:, 0])) ** 2).mean())
    assert rmse < 1e-2


def test_matches_numpy_reference():
    # (b) with the fitted hyperparameters, posterior mean/variance equal a plain numpy solve
    gp = GP().fit(X6, Y6)
    mean, var = gp.predict(XS5)
    th = gp.theta.numpy()
    ls, sf2, c = np.exp(th[:2]), np.exp(th[2]), th[4]
    s2 = 1e-6 + np.exp(th[3]) + JITTER
    K = matern52(X6, X6, ls, sf2) + s2 * np.eye(6)
    Ks = matern52(XS5, X6, ls, sf2)
    ref_mean = c + Ks @ np.linalg.solve(K, Y6 - c)
    ref_var = sf2 - np.einsum("ij,ji->i", Ks, np.linalg.solve(K, Ks.T))
    assert np.abs(mean.numpy() - ref_mean).max() < 1e-8
    assert np.abs(var.numpy() - ref_var).max() < 1e-8


def test_lml_gradient_matches_finite_differences():
    # (c) autograd gradient of the LML w.r.t. all hyperparameters vs central differences
    gp = GP()
    gp.X, gp.y = torch.tensor(X6, dtype=DT), torch.tensor(Y6, dtype=DT)
    theta = torch.tensor([-0.7, 0.4, 0.3, -4.0, 0.2], dtype=DT, requires_grad=True)
    gp.log_marginal_likelihood(theta).backward()
    eps = 1e-6
    for i in range(5):
        e = torch.zeros(5, dtype=DT)
        e[i] = eps
        with torch.no_grad():
            up, down = gp.log_marginal_likelihood(theta + e), gp.log_marginal_likelihood(theta - e)
        fd = (up - down) / (2 * eps)
        g = theta.grad[i]
        assert abs(g - fd) <= 1e-5 * max(1.0, abs(g)), (i, g.item(), fd.item())


def test_training_variance_below_noise():
    # (d) at a training point the posterior variance of f cannot exceed the noise variance
    rng = np.random.default_rng(3)
    x = rng.random((15, 1))
    y = np.sin(6 * x[:, 0]) + 0.1 * rng.standard_normal(15)
    gp = GP().fit(x, y)
    _, var = gp.predict(x)
    assert (var <= gp.noise_var() + 1e-6).all()


def test_standardizer_round_trip():
    # (e) mean and variance transform back exactly
    y = torch.tensor([3.0, 5.0, 4.0, 9.0], dtype=DT)
    st = Standardizer().fit(y)
    z = st.transform(y)
    assert abs(z.mean()) < 1e-12 and abs(z.std(unbiased=False) - 1) < 1e-12
    assert torch.allclose(st.inverse(z), y, atol=1e-12)
    v = torch.tensor([0.5, 2.0], dtype=DT)
    assert torch.allclose(st.inverse_var(v / st.std**2), v, atol=1e-12)


def test_scale_inputs():
    s = scale_inputs([[5.0, 5.0], [12.0, 14.0], [8.5, 9.5]], [(5, 12), (5, 14)])
    assert torch.allclose(s, torch.tensor([[0, 0], [1, 1], [0.5, 0.5]], dtype=DT))

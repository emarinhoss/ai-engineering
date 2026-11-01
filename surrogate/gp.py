"""Exact Gaussian process regression in pure torch (float64).

Model: y = c + f(x) + noise, f ~ GP(0, k), k = Matern-5/2 with ARD lengthscales and signal
variance. Inputs must already be scaled to [0, 1]^d (scale_inputs); outputs should be
standardised (Standardizer). Hyperparameters live in one vector in log space:
theta = [log lengthscale_1..d, log signal variance, log noise variance, mean c].
Kernel and likelihood also accept a batch theta of shape (B, d+3): fit() uses that to run its
3 restarts together (same arithmetic as 3 separate runs, 3x fewer torch calls).
"""
import math

import torch

torch.set_num_threads(1)   # matrices are tiny; with 4 threads torch was 30x slower here

DT = torch.float64
NOISE_FLOOR = 1e-6   # added to the noise variance, in standardised units
JITTER = 1e-8        # added to the diagonal before every Cholesky
SQRT5 = math.sqrt(5.0)


def scale_inputs(X, bounds):
    """Map X (n, d) to [0, 1]^d. bounds = [(lo_1, hi_1), ..., (lo_d, hi_d)]."""
    X = torch.as_tensor(X, dtype=DT)
    b = torch.as_tensor(bounds, dtype=DT)
    return (X - b[:, 0]) / (b[:, 1] - b[:, 0])


class Standardizer:
    """z = (y - mean) / std, with the matching inverse for means and for variances."""

    def fit(self, y):
        y = torch.as_tensor(y, dtype=DT)
        self.mean = y.mean()
        std = y.std(unbiased=False)
        self.std = std if std > 0 else torch.ones((), dtype=DT)   # constant data: keep scale 1
        return self

    def transform(self, y):
        return (torch.as_tensor(y, dtype=DT) - self.mean) / self.std

    def inverse(self, z):          # standardised mean -> original units
        return z * self.std + self.mean

    def inverse_var(self, v):      # standardised variance -> original units (scale only)
        return v * self.std**2


class GP:
    def __init__(self, restarts=(-1.0, 0.0, 1.0), steps=300, lr=0.05):
        self.restarts, self.steps, self.lr = restarts, steps, lr

    def kernel(self, A, B, theta):
        """Matern-5/2: sf2 (1 + sqrt5 r + 5 r^2 / 3) exp(-sqrt5 r), r = ARD-scaled distance."""
        d = A.shape[1]
        diff = (A[:, None, :] - B[None, :, :]) / torch.exp(theta[..., None, None, :d])
        r = torch.sqrt((diff**2).sum(-1).clamp(min=1e-12))   # clamp: sqrt has no gradient at 0
        sf2 = torch.exp(theta[..., d, None, None])
        return sf2 * (1 + SQRT5 * r + 5.0 / 3.0 * r**2) * torch.exp(-SQRT5 * r)

    def noise_var(self, theta=None):
        theta = self.theta if theta is None else theta
        return NOISE_FLOOR + torch.exp(theta[..., -2])

    def _cholesky(self, theta):
        K = self.kernel(self.X, self.X, theta)
        eye = torch.eye(self.X.shape[0], dtype=DT)
        s2 = self.noise_var(theta)[..., None, None] + JITTER
        return torch.linalg.cholesky(K + s2 * eye)   # K + s2 I = L L^T

    def log_marginal_likelihood(self, theta=None):
        """log p(y | X, theta) = -1/2 r^T (K+s2 I)^-1 r - 1/2 log|K+s2 I| - n/2 log 2 pi."""
        theta = self.theta if theta is None else theta
        L = self._cholesky(theta)
        r = (self.y - theta[..., -1, None])[..., None]   # residual y - c as a column
        alpha = torch.cholesky_solve(r, L)
        logdet_half = torch.log(torch.diagonal(L, dim1=-2, dim2=-1)).sum(-1)   # 1/2 log|K+s2 I|
        n = self.y.shape[0]
        return -0.5 * (r * alpha).sum((-2, -1)) - logdet_half - 0.5 * n * math.log(2 * math.pi)

    def fit(self, X, y):
        """Adam on -LML from each restart (run as one batch); keep the best LML."""
        self.X, self.y = torch.as_tensor(X, dtype=DT), torch.as_tensor(y, dtype=DT)
        d = self.X.shape[1]
        # one row per restart: lengthscale e^init, signal var 1, noise 1e-3, mean 0
        init = [[log_ls] * d + [0.0, math.log(1e-3), 0.0] for log_ls in self.restarts]
        theta = torch.tensor(init, dtype=DT, requires_grad=True)
        opt = torch.optim.Adam([theta], lr=self.lr)
        for _ in range(self.steps):
            opt.zero_grad()
            (-self.log_marginal_likelihood(theta).sum()).backward()   # rows are independent
            opt.step()
        with torch.no_grad():
            lml = self.log_marginal_likelihood(theta)
        self.theta = theta[lml.argmax()].detach().clone()
        self.L = self._cholesky(self.theta)
        self.alpha = torch.cholesky_solve((self.y - self.theta[-1]).unsqueeze(1), self.L)
        return self

    def predict(self, Xs, noise=False):
        """Posterior mean and variance of f at Xs (add the noise variance with noise=True)."""
        Xs = torch.as_tensor(Xs, dtype=DT)
        d = self.X.shape[1]
        with torch.no_grad():
            Ks = self.kernel(Xs, self.X, self.theta)                 # (m, n)
            mean = self.theta[-1] + (Ks @ self.alpha).squeeze(1)     # c + k*^T (K+s2 I)^-1 (y-c)
            V = torch.linalg.solve_triangular(self.L, Ks.T, upper=False)   # L^-1 k*
            var = (torch.exp(self.theta[d]) - (V**2).sum(0)).clamp(min=1e-12)   # k** - |V|^2
            if noise:
                var = var + self.noise_var()
        return mean, var

    def hypers(self):
        """Fitted hyperparameters as plain floats (for the replay CSV)."""
        d = self.X.shape[1]
        out = {f"log_ls{i + 1}": self.theta[i].item() for i in range(d)}
        out.update(log_sf2=self.theta[d].item(), noise_var=self.noise_var().item(),
                   mean=self.theta[-1].item(), lml=self.log_marginal_likelihood().item())
        return out

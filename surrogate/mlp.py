"""Deep ensemble of small neural networks with the same interface as surrogate.gp.GP.

Spec: docs/specs/task4b_mlp_ensemble.md. Five multilayer perceptrons 2 -> 64 -> 64 -> 1 (tanh),
trained on the same data from different random initial weights. The ensemble mean is the
prediction and the spread between members is the uncertainty (Lakshminarayanan et al. 2017,
without variance heads). Inputs must be scaled to [0, 1]^d (surrogate.gp.scale_inputs); outputs
should be standardised (surrogate.gp.Standardizer), exactly as for the GP.

The five members are stored as one tensor per layer with the member index first, e.g.
W1 has shape (5, d, 64). One batched training step then updates all five networks at once; Adam and
the weight decay act element by element, so this is the same arithmetic as five separate trainings.
"""
import math

import torch

from surrogate.gp import DT, NOISE_FLOOR

MEMBERS = 5
WIDTH = 64
STEPS = 2000
LR = 1e-2
WEIGHT_DECAY = 1e-4


def _uniform(gen, shape, fan_in):
    """PyTorch nn.Linear default: uniform(-1/sqrt(fan_in), 1/sqrt(fan_in))."""
    bound = 1.0 / math.sqrt(fan_in)
    return (torch.rand(shape, generator=gen, dtype=DT) * 2.0 - 1.0) * bound


class MLPEnsemble:
    def __init__(self, members=MEMBERS, width=WIDTH, steps=STEPS, lr=LR, weight_decay=WEIGHT_DECAY, seed=0):
        self.members, self.width, self.steps = members, width, steps
        self.lr, self.weight_decay, self.seed = lr, weight_decay, seed

    def _forward(self, X):
        """X (n, d) in [0, 1] -> member predictions (members, n)."""
        x = (2.0 * torch.as_tensor(X, dtype=DT) - 1.0).unsqueeze(0)       # [-1, 1], (1, n, d)
        W1, b1, W2, b2, W3, b3 = self.params
        h = torch.tanh(x @ W1 + b1)                                        # (K, n, width)
        h = torch.tanh(h @ W2 + b2)                                        # (K, n, width)
        return (h @ W3 + b3).squeeze(-1)                                   # (K, n)

    def fit(self, X, y):
        """Train every member on (X, y) by full-batch mean squared error."""
        X, y = torch.as_tensor(X, dtype=DT), torch.as_tensor(y, dtype=DT)
        K, d, H = self.members, X.shape[1], self.width
        gen = torch.Generator().manual_seed(self.seed)
        self.params = [_uniform(gen, (K, d, H), d), _uniform(gen, (K, 1, H), d),
                       _uniform(gen, (K, H, H), H), _uniform(gen, (K, 1, H), H),
                       _uniform(gen, (K, H, 1), H), _uniform(gen, (K, 1, 1), H)]
        for p in self.params:
            p.requires_grad_(True)
        opt = torch.optim.AdamW(self.params, lr=self.lr, weight_decay=self.weight_decay)
        for _ in range(self.steps):
            opt.zero_grad()
            mse = ((self._forward(X) - y) ** 2).mean(1)                    # one MSE per member
            mse.sum().backward()                                           # members are independent
            opt.step()
        with torch.no_grad():
            self.train_mse = ((self._forward(X) - y) ** 2).mean(1)         # (K,)
        return self

    def noise_var(self):
        """Mean training MSE over the members, plus the GP's noise floor (standardised units)."""
        return self.train_mse.mean() + NOISE_FLOOR

    def predict(self, Xs, noise=False):
        """Ensemble mean and variance between members at Xs (add noise_var() with noise=True)."""
        with torch.no_grad():
            P = self._forward(Xs)                                          # (K, m)
            mean = P.mean(0)
            var = P.var(0, unbiased=True).clamp(min=1e-12)
            if noise:
                var = var + self.noise_var()
        return mean, var

    def hypers(self):
        """Plain floats for the replay CSV (the hyp_* columns)."""
        return {"members": float(self.members), "noise_var": self.noise_var().item(),
                "train_mse_max": self.train_mse.max().item()}

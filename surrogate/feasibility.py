"""Learned feasibility (Task 9): probability that SU2 converges at a point.

Logistic regression on the scaled inputs plus one extra feature (total turning for inlet3r),
fitted by plain gradient descent on the mean log loss with a small L2 penalty:

    p(x) = 1 / (1 + exp(-(w . f(x) + b)))
    loss = -mean(y log p + (1 - y) log(1 - p)) + LAM |w|^2 / 2

y = 1 for a converged run, 0 for a run that diverged, timed out or exited with an error. The
classifier never picks a point; the acquisition multiplies EHVI by p(x).
"""
import torch

from surrogate.gp import DT

LAM, STEPS, LR = 1e-3, 5000, 0.5


class Feasibility:
    def fit(self, F, y):
        """F (n, k) features already scaled to about [0, 1]; y (n,) of 0 and 1."""
        F, y = torch.as_tensor(F, dtype=DT), torch.as_tensor(y, dtype=DT)
        self.mu, self.sd = F.mean(0), F.std(0).clamp(min=1e-9)      # centre the features
        Z = (F - self.mu) / self.sd
        w = torch.zeros(Z.shape[1], dtype=DT, requires_grad=True)
        b = torch.zeros((), dtype=DT, requires_grad=True)
        opt = torch.optim.SGD([w, b], lr=LR)
        for _ in range(STEPS):
            opt.zero_grad()
            logit = Z @ w + b
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logit, y) + LAM * (w @ w) / 2
            loss.backward()
            opt.step()
        self.w, self.b = w.detach(), b.detach()
        return self

    def predict(self, F):
        """Probability of convergence at each row of F."""
        Z = (torch.as_tensor(F, dtype=DT) - self.mu) / self.sd
        return torch.sigmoid(Z @ self.w + self.b)

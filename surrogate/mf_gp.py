"""Two-level (multi-fidelity) GP, linear autoregressive form (Kennedy and O'Hagan 2000). Task 9.

    y_H(x) = rho * y_L(x) + d(x)

y_L is the cheap model (Euler + Eckert), y_H the expensive one (laminar Navier-Stokes). One GP is
fitted to all low-fidelity runs; a second GP is fitted to the discrepancy d at the high-fidelity
runs. The design is nested: every high-fidelity point also has a low-fidelity run, so y_L at the
high-fidelity points is observed, not predicted.

rho in two steps, both plain least squares:
  1. ordinary least squares of y_H on (y_L, 1) at the high-fidelity points; fit the GP to d;
  2. generalized least squares with that GP's covariance K: [rho, c] = (A' K^-1 A)^-1 A' K^-1 y_H,
     A = [y_L, 1]; refit the GP to the new d.
Both levels are standardized with one scale, that of the low-fidelity data, so rho is near 1 when
the two agree and the low-level GP does not depend on which high-fidelity runs are used.

Prediction at new points: mean rho m_L + m_d, variance rho^2 v_L + v_d (independent levels), plus the
discrepancy GP's noise variance when predicting a new run (noise=True).
"""
import torch

from surrogate.gp import DT, GP, Standardizer


class TwoLevelGP:
    def fit(self, XL, yL, XH, yH, yL_at_H, low=None):
        """XL, yL: all low-fidelity runs. XH, yH: high-fidelity runs. yL_at_H: the low-fidelity
        value at each high-fidelity point (nested design). low: optionally the .low GP of an earlier
        TwoLevelGP fitted with the same XL, yL (it is the same fit; saves refitting the large level)."""
        XL, XH = torch.as_tensor(XL, dtype=DT), torch.as_tensor(XH, dtype=DT)
        self.st = Standardizer().fit(yL)                       # one scale for both levels
        zL, zH, zLH = self.st.transform(yL), self.st.transform(yH), self.st.transform(yL_at_H)
        self.low = low if low is not None else GP().fit(XL, zL)

        A = torch.stack([zLH, torch.ones_like(zLH)], 1)       # columns: y_L, constant
        beta = torch.linalg.lstsq(A, zH.unsqueeze(1)).solution.squeeze(1)     # step 1: OLS
        self.d = GP().fit(XH, zH - beta[0] * zLH)
        L = self.d.L                                           # Cholesky of the GP's K (noise included)
        KiA = torch.cholesky_solve(A, L)
        beta = torch.linalg.solve(A.T @ KiA, KiA.T @ zH)       # step 2: GLS
        self.rho = float(beta[0])
        self.d = GP().fit(XH, zH - self.rho * zLH)
        return self

    def predict(self, Xs, noise=False):
        """Mean and variance of y_H at Xs, in original units (noise=True adds the discrepancy GP's
        fitted noise variance: the spread of a new high-fidelity run, as GP.predict(noise=True))."""
        mL, vL = self.low.predict(Xs)
        md, vd = self.d.predict(Xs, noise=noise)
        return self.st.inverse(self.rho * mL + md), self.st.inverse_var(self.rho**2 * vL + vd)

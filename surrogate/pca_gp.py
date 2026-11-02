"""Principal components plus one GP per coefficient (Task 4c baseline, docs/specs/task4c_operator_profiles.md).

Targets Y (B, n) must already be centred by the training mean profile and scaled. Keep the fewest
components that explain 99.9 percent of the training variance (at most 8); fit surrogate.gp.GP to
each standardised coefficient over the unit-square inputs; predict the profile from the predicted
coefficients, with variance sum_j var_j * v_j(s)^2 (components treated as independent).
"""
import torch

from surrogate.gp import DT, GP, Standardizer

VARIANCE_KEPT, MAX_COMPONENTS = 0.999, 8


class PCAGP:
    def fit(self, X, Y):
        X, Y = torch.as_tensor(X, dtype=DT), torch.as_tensor(Y, dtype=DT)
        _, S, Vt = torch.linalg.svd(Y, full_matrices=False)
        frac = torch.cumsum(S**2, 0) / (S**2).sum()
        self.k = min(MAX_COMPONENTS, int((frac < VARIANCE_KEPT).sum()) + 1)
        self.V = Vt[:self.k]                                            # (k, n) components
        C = Y @ self.V.T                                                # (B, k) coefficients
        self.models = []
        for j in range(self.k):
            st = Standardizer().fit(C[:, j])
            self.models.append((GP().fit(X, st.transform(C[:, j])), st))
        self.explained = float(frac[self.k - 1])
        return self

    def predict(self, Xs):
        """-> mean (m, n), variance (m, n) of the scaled target (latent, no noise)."""
        means, variances = [], []
        for gp, st in self.models:
            m, v = gp.predict(Xs)
            means.append(st.inverse(m))
            variances.append(st.inverse_var(v))
        M, Vc = torch.stack(means, 1), torch.stack(variances, 1)       # (m, k)
        return M @ self.V, Vc @ (self.V**2)

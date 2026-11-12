"""Field model of experiment W1 (docs/specs/task11_fno_exploration.md; task W1.6).

Maps x = (camber %, thickness %, log10 Reynolds, angle deg) to the four scaled fields of a coarse
airfoil2d solution, one value per mesh node: pressure, two velocity components, nu_tilde * Re
(worker/startfile.py). Steps:
  1. inputs scaled to [0, 1] by the training range (surrogate.gp.scale_inputs);
  2. each field centred by its training mean (per node) and divided by one number, its training
     standard deviation, so that the four fields weigh alike;
  3. principal components of the stacked fields, keeping k;
  4. one GP (surrogate.gp.GP) per component coefficient, standardised.
The prediction is the mean of each GP put back through steps 3 and 2. Same method as
surrogate/pca_gp.py, for a field instead of a profile.
"""
import numpy as np
import torch

from surrogate.gp import DT, GP, Standardizer, scale_inputs


class FieldPCAGP:
    def fit(self, X, F, k):
        """X (B, 4) raw inputs, F (B, n, 4) scaled fields, k components."""
        X, F = np.asarray(X, dtype=float), np.asarray(F, dtype=float)
        self.bounds = np.stack([X.min(0), X.max(0)], 1)
        self.mean = F.mean(0)                                            # (n, 4)
        self.block = (F - self.mean).reshape(-1, 4).std(0)               # (4,)
        Y = torch.as_tensor(((F - self.mean) / self.block).reshape(len(F), -1), dtype=DT)
        _, S, Vt = torch.linalg.svd(Y, full_matrices=False)
        self.k = int(k)
        self.V = Vt[:self.k]                                             # (k, n * 4)
        self.explained = float((S[:self.k] ** 2).sum() / (S ** 2).sum())
        C = Y @ self.V.T                                                 # (B, k)
        Xs = scale_inputs(X, self.bounds)
        self.models = []
        for j in range(self.k):
            st = Standardizer().fit(C[:, j])
            self.models.append((GP().fit(Xs, st.transform(C[:, j])), st))
        return self

    def predict(self, x, k=None):
        """x (4,) raw inputs -> (n, 4) predicted scaled fields, from the first k components (all by
        default). The components and their GPs do not depend on k, so one fit serves every k."""
        k = self.k if k is None else k
        xs = scale_inputs(np.asarray(x, dtype=float)[None, :], self.bounds)
        c = torch.stack([st.inverse(gp.predict(xs)[0][0]) for gp, st in self.models[:k]])
        flat = (c @ self.V[:k]).numpy()
        return flat.reshape(self.mean.shape) * self.block + self.mean

    def save(self, path):
        """Everything predict needs, in one .npz (GP training data, hyperparameters, components)."""
        np.savez_compressed(
            path, bounds=self.bounds, mean=self.mean, block=self.block, V=self.V.numpy(),
            explained=self.explained, X=self.models[0][0].X.numpy(),
            y=np.stack([gp.y.numpy() for gp, _ in self.models]),
            theta=np.stack([gp.theta.numpy() for gp, _ in self.models]),
            st=np.array([[st.mean.item(), st.std.item()] for _, st in self.models]))

    @classmethod
    def load(cls, path):
        z = np.load(path)
        self = cls()
        self.bounds, self.mean, self.block = z["bounds"], z["mean"], z["block"]
        self.V, self.explained = torch.as_tensor(z["V"], dtype=DT), float(z["explained"])
        self.k = len(self.V)
        self.models = []
        for y, theta, (m, s) in zip(z["y"], z["theta"], z["st"]):
            gp = GP()
            gp.X, gp.y, gp.theta = (torch.as_tensor(a, dtype=DT) for a in (z["X"], y, theta))
            gp.L = gp._cholesky(gp.theta)
            gp.alpha = torch.cholesky_solve((gp.y - gp.theta[-1]).unsqueeze(1), gp.L)
            st = Standardizer()
            st.mean, st.std = torch.tensor(m, dtype=DT), torch.tensor(s, dtype=DT)
            self.models.append((gp, st))
        return self

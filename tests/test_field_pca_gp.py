"""surrogate.field_pca_gp: the W1 field model (task W1.6)."""
import numpy as np

from surrogate.field_pca_gp import FieldPCAGP


def family(n=200, B=30, seed=0):
    """Fields built from two smooth modes whose weights are smooth functions of the four inputs."""
    rng = np.random.default_rng(seed)
    X = np.column_stack([rng.uniform(0, 6, B), rng.uniform(8, 15, B), rng.uniform(4.9, 5.4, B),
                         rng.uniform(-2, 10, B)])
    s = np.linspace(0, 1, n)
    m1 = np.stack([np.sin(np.pi * s), np.cos(np.pi * s), s, 50 * s ** 2], 1)
    m2 = np.stack([s ** 2, np.sin(2 * np.pi * s), 1 - s, 30 * np.sin(np.pi * s)], 1)
    w1 = 0.1 * X[:, 3] + 0.05 * X[:, 0]
    w2 = 0.02 * X[:, 1] * X[:, 2]
    return X, w1[:, None, None] * m1 + w2[:, None, None] * m2


def test_two_mode_family_is_reproduced_and_saved_exactly(tmp_path):
    X, F = family()
    model = FieldPCAGP().fit(X[:-3], F[:-3], k=2)
    assert model.explained > 0.999999
    for i in (-3, -2, -1):                                     # held-out inputs
        err = np.abs(model.predict(X[i]) - F[i]).max() / np.abs(F[i]).max()
        assert err < 0.02
    model.save(tmp_path / "m.npz")
    again = FieldPCAGP.load(tmp_path / "m.npz")
    assert np.allclose(again.predict(X[-1]), model.predict(X[-1]), rtol=1e-12, atol=1e-12)

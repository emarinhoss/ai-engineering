"""Task 9: the two-level GP on a synthetic pair of fidelities, and the feasibility classifier."""
import torch

from surrogate.feasibility import Feasibility
from surrogate.gp import DT, GP, Standardizer
from surrogate.mf_gp import TwoLevelGP


def high(X):
    return torch.sin(6 * X[:, 0]) + X[:, 1] ** 2 + 0.3 * X[:, 0] * X[:, 1]


def low(X):                                  # a biased, scaled version of high: rho = 1 / 0.8
    return 0.8 * high(X) - 0.2 * X[:, 1] + 0.1


def test_two_level_beats_high_only_with_few_high_runs():
    g = torch.Generator().manual_seed(0)
    XL = torch.rand((120, 2), generator=g, dtype=DT)
    XH = XL[:10]                                                  # nested: high runs are low runs too
    Xt = torch.rand((200, 2), generator=g, dtype=DT)
    mf = TwoLevelGP().fit(XL, low(XL), XH, high(XH), low(XH))
    m_mf, v_mf = mf.predict(Xt)
    st = Standardizer().fit(high(XH))
    m_h, _ = GP().fit(XH, st.transform(high(XH))).predict(Xt)
    err_mf = (m_mf - high(Xt)).pow(2).mean().sqrt()
    err_h = (st.inverse(m_h) - high(Xt)).pow(2).mean().sqrt()
    assert err_mf < 0.5 * err_h
    assert 1.0 < mf.rho < 1.5                                     # true value 1.25
    assert (v_mf > 0).all()


def test_feasibility_learns_a_linear_boundary():
    g = torch.Generator().manual_seed(1)
    F = torch.rand((300, 3), generator=g, dtype=DT)
    y = (F[:, 0] + 0.5 * F[:, 2] < 0.9).to(DT)                    # converges below a plane
    p = Feasibility().fit(F, y).predict(F)
    assert ((p > 0.5).to(DT) == y).to(DT).mean() > 0.93
    assert p[(F[:, 0] > 0.95) & (F[:, 2] > 0.8)].max() < 0.2      # far inside the failing side

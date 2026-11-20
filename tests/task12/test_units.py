"""ISA in fps units against Mattingly App. B (p. 511): at 20 kft delta = 0.4599, theta = 0.8626."""
import pytest

from conceptual.units import P0, RHO0, T0_R, isa


def test_sea_level():
    s = isa(0.0)
    assert s["rho"] == pytest.approx(RHO0, rel=1e-4)
    assert s["a"] == pytest.approx(1116.45, rel=1e-3)
    assert s["mu"] == pytest.approx(3.737e-7, rel=1e-2)


@pytest.mark.parametrize("h_kft, delta, theta", [(20, 0.4599, 0.8626), (25, None, None)])
def test_mattingly_appendix_b(h_kft, delta, theta):
    s = isa(h_kft * 1000.0)
    if delta is not None:
        assert s["p"] / P0 == pytest.approx(delta, abs=6e-5)
        assert s["T"] / T0_R == pytest.approx(theta, abs=6e-5)

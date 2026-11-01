import pytest

from physics.atmosphere import state


def test_30km():
    s = state(30)
    assert s["T"] == pytest.approx(226.509, rel=1e-4)
    assert s["p"] == pytest.approx(1197.03, rel=1e-4)
    assert s["rho"] == pytest.approx(0.018410, rel=1e-4)
    assert s["mu"] == pytest.approx(1.4752e-5, rel=1e-3)
    assert s["a"] == pytest.approx(301.71, rel=1e-3)


def test_unknown_altitude():
    with pytest.raises(KeyError, match="not tabulated"):
        state(25)

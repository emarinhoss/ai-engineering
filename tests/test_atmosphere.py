import pytest

from physics.atmosphere import state


def test_30km():
    s = state(30)
    assert s["T"] == pytest.approx(226.509, rel=1e-4)
    assert s["p"] == pytest.approx(1197.03, rel=1e-4)
    assert s["rho"] == pytest.approx(0.018410, rel=1e-4)
    assert s["mu"] == pytest.approx(1.4752e-5, rel=1e-3)
    assert s["a"] == pytest.approx(301.71, rel=1e-3)


def test_untabulated_altitude_uses_the_1976_formula_and_out_of_range_raises():
    # Task 9: altitudes other than the table's come from the 1976 formula (20 to 47 km).
    s = state(25)
    assert s["T"] == pytest.approx(221.552, rel=1e-4) and s["p"] == pytest.approx(2549.2, rel=1e-4)   # USSA 1976 table, 25 km geometric
    with pytest.raises(ValueError, match="outside the 20 to 47 km"):
        state(50)

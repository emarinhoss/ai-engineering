"""Unit tests for the MSH gas properties and burner option (no validation asserts)."""
import pytest

from conceptual.units import isa
from measurement import gas_props as gp
from measurement import turboprop_cycle as tc

AIR = {"N2": 0.78084, "O2": 0.20946, "AR": 0.00934, "CO2": 0.00036}


def _gas():
    ct = pytest.importorskip("cantera")
    g = ct.Solution("gri30.yaml")
    return ct, g


@pytest.mark.parametrize("T_R", [540.0, 1800.0])
def test_cp_air_vs_cantera(T_R):
    _, g = _gas()
    g.TPX = T_R / 1.8, 101325.0, AIR
    cp_btu = g.cp_mass / 2326.0 / 1.8          # J/(kg K) to Btu/(lbm R)
    assert gp.cp_air(T_R) == pytest.approx(cp_btu, rel=0.005)
    # independent anchor: standard air cp near room temperature is about 0.240 Btu/(lbm R)
    if T_R == 540.0:
        assert gp.cp_air(T_R) == pytest.approx(0.240, abs=0.002)


def test_reference_enthalpy_is_zero():
    assert gp.h_air(536.67) == pytest.approx(0.0, abs=1e-3)


@pytest.mark.parametrize("T_R", [800.0, 2200.0])
def test_products_with_no_fuel_equal_air(T_R):
    assert gp.h_products(T_R, 0.0) == pytest.approx(gp.h_air(T_R), rel=1e-12)


def test_products_vs_cantera_mixture():
    _, g = _gas()
    f, T_R = 0.02, 2200.0
    moles = gp._products_moles(f)
    names = {"N2": "N2", "O2": "O2", "Ar": "AR", "CO2": "CO2", "H2O": "H2O"}
    g.TPX = 298.15, 101325.0, {names[s]: n for s, n in moles.items()}
    h_ref = g.enthalpy_mass
    g.TPX = T_R / 1.8, 101325.0, {names[s]: n for s, n in moles.items()}
    assert gp.h_products(T_R, f) == pytest.approx((g.enthalpy_mass - h_ref) / 2326.0, rel=0.005)


def test_rich_mixture_rejected():
    with pytest.raises(ValueError):
        gp.h_products(2000.0, 0.2)


def test_msh_fuel_air_is_sensible():
    f = gp.fuel_air_msh(1000.0, 2200.0, 0.98, 18400.0)
    assert 0.01 < f < 0.03
    assert gp.h_products(2200.0, f) * (1 + f) - gp.h_air(1000.0) == pytest.approx(0.98 * f * 18400.0, rel=1e-9)


def test_csh_default_unchanged_and_msh_changes_f():
    a = isa(25000.0)
    base = tc.design_point(0.8, a["T"], a["p"], 20, 0.5, tc.BOOK_EXAMPLE)
    explicit = tc.design_point(0.8, a["T"], a["p"], 20, 0.5, dict(tc.BOOK_EXAMPLE, burner="csh"))
    assert base == explicit
    msh = tc.design_point(0.8, a["T"], a["p"], 20, 0.5, dict(tc.BOOK_EXAMPLE, burner="msh"))
    assert msh["f"] != base["f"] and 0.005 < msh["f"] < 0.05


def test_fuel_air_msh_anchor_without_cantera():
    # Value cross-checked by the reviewer against Cantera frozen products and a hand mean-cp
    # calculation (not computed with Cantera here), so this test needs no Cantera install.
    assert gp.fuel_air_msh(1000.0, 2200.0, 0.98, 18400.0) == pytest.approx(0.01884, abs=2e-5)


def test_gas_props_gates():
    with pytest.raises(ValueError):
        gp.h_air(300.0)
    with pytest.raises(ValueError):
        gp.cp_air(7000.0)
    with pytest.raises(ValueError):
        gp.h_products(100.0, 0.02)
    with pytest.raises(ValueError):
        gp.fuel_air_msh(2000.0, 1500.0, 0.98, 18400.0)

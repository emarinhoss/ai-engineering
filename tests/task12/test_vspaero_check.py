"""Pure-Python parts of conceptual/vspaero_check.py (no OpenVSP needed)."""
import math

import pytest

from conceptual import vspaero_check as v


def test_line_fit_recovers_a_line():
    a, b, res = v.line_fit([0.0, 1.0, 2.0, 5.0], [1.0, 3.0, 5.0, 11.0])
    assert (a, b) == pytest.approx((1.0, 2.0))
    assert res == pytest.approx(0.0, abs=1e-12)


def test_lift_curve_slope_per_radian_and_zero_lift_angle():
    alpha = [-2.0, 0.0, 2.0, 4.0]
    cl = [0.25 + 0.1 * a for a in alpha]            # 0.1 per degree, CL0 0.25
    cla, cl0, a0, res = v.lift_curve(alpha, cl)
    assert cla == pytest.approx(0.1 * 180.0 / math.pi)
    assert cl0 == pytest.approx(0.25)
    assert a0 == pytest.approx(-2.5)                # CL = 0 at alpha = -CL0 / slope
    assert res == pytest.approx(0.0, abs=1e-12)


def test_induced_drag_fit_gives_back_e():
    A, e = 7.0, 0.9
    cl = [0.1, 0.3, 0.5, 0.8, 1.0]
    cdi = [0.0005 + c * c / (math.pi * A * e) for c in cl]
    k, cdi0, e_fit, res = v.induced_drag_fit(cl, cdi, A)
    assert e_fit == pytest.approx(e)
    assert cdi0 == pytest.approx(0.0005)
    assert k == pytest.approx(1.0 / (math.pi * A * e))
    assert res == pytest.approx(0.0, abs=1e-12)


def test_neutral_point_from_cm_alpha():
    # Cm_alpha = -CL_alpha (x_np - x_cg)/c: x_np 12 ft, x_cg 11 ft, c 5 ft, CL_alpha 5 -> -1 per rad
    cma = -5.0 * (12.0 - 11.0) / 5.0
    assert v.neutral_point_from_cm(11.0, cma, 5.0, 5.0) == pytest.approx(12.0)


POLAR = """
   Surface Integration Forces and Moments -->
      Beta             Mach             AoA              CLtot            CDi          CMytot
  0.0   0.15   -2.0   0.02   0.001  0.13
  0.0   0.15    2.0   0.44   0.012  0.06
  0.0   0.22   -2.0   0.03   0.001  0.12
"""


def test_parse_polar_reads_named_columns():
    rows = v.parse_polar(POLAR)
    assert len(rows) == 3
    assert rows[1]["AoA"] == 2.0 and rows[1]["CLtot"] == 0.44 and rows[2]["Mach"] == 0.22


def test_derivatives_at_mach_selects_one_mach_and_fits():
    alpha = [-2.0, 0.0, 2.0, 4.0]
    rows = []
    for a in alpha:
        cl = 0.2 + 0.1 * a
        rows.append({"Mach": 0.15, "AoA": a, "CLtot": cl, "CMytot": -0.5 * cl, "CDi": cl * cl / 20.0,
                     "CDiw": cl * cl / 25.0})
        rows.append({"Mach": 0.22, "AoA": a, "CLtot": 9.0, "CMytot": 9.0, "CDi": 9.0, "CDiw": 9.0})
    d = v.derivatives_at_mach(rows, 0.15, 5.0, 4.0, 10.0)
    assert d["CL_alpha_per_rad"] == pytest.approx(0.1 * 180.0 / math.pi)
    assert d["CL0"] == pytest.approx(0.2)
    assert d["K_trefftz"] == pytest.approx(1.0 / 25.0)
    assert d["K_surface"] == pytest.approx(1.0 / 20.0)
    assert d["e_trefftz"] == pytest.approx(25.0 / (math.pi * 5.0))
    # Cm = -0.5 CL: Cm_alpha = -0.5 CL_alpha, so x_np = x_cg + 0.5 c
    assert d["x_np_ft"] == pytest.approx(10.0 + 0.5 * 4.0)


def test_ledger_value():
    text = "  tail_eta_h:  {value: 0.9, units: \"-\"}\n  mission_altitude_ft: {value: 20000.0, units: ft}\n"
    assert v.ledger_value(text, "tail_eta_h") == 0.9
    assert v.ledger_value(text, "mission_altitude_ft") == 20000.0
    with pytest.raises(KeyError):
        v.ledger_value(text, "nothing")


def test_relative_change():
    assert v.relative_change(5.0, 5.5) == pytest.approx(0.1)


def test_valid_polar_gate():
    assert v.valid_polar(4.7, 0.001, [0.001, 0.01])[0]
    assert not v.valid_polar(2.0, 0.001, [0.001, 0.01])[0]        # slope too low
    assert not v.valid_polar(37.0, 0.001, [0.001, 0.01])[0]       # slope absurd
    assert not v.valid_polar(4.7, 0.5, [0.001, 0.01])[0]          # not a line
    assert not v.valid_polar(4.7, 0.001, [0.001, -0.01])[0]       # negative induced drag


def test_vspaero_version():
    assert v.vspaero_version("VSPAERO v.7.2.2 --- Compiled on: Nov 24 2026") == "VSPAERO v.7.2.2"
    assert v.vspaero_version("nothing here") is None

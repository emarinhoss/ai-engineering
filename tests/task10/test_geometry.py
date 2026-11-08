"""T10.2b: planform, tail and fuselage geometry."""
import math

import pytest
from drone import geometry


def test_tapered_wing_area_and_chords():
    p = geometry.tapered(span=2.0, aspect_ratio=10.0, taper_ratio=0.5)
    w = geometry.wing_dict(p)
    assert w["S"] == pytest.approx(0.4)
    assert w["b"] == pytest.approx(2.0) and w["AR"] == pytest.approx(10.0)
    # S = b (c_root + c_tip) / 2 with c_tip = 0.5 c_root  ->  c_root = 2 S / (1.5 b)
    assert w["c_root"] == pytest.approx(0.8 / 1.5 * 0.5)
    assert w["c_tip"] == pytest.approx(w["c_root"] * 0.5)
    assert w["c_mean"] == pytest.approx(0.2)
    # MAC of a trapezoid: 2/3 c_root (1 + l + l^2) / (1 + l)
    lam = 0.5
    assert w["c_mac"] == pytest.approx(2.0 / 3.0 * w["c_root"] * (1 + lam + lam * lam) / (1 + lam))


def test_rectangular_wing_mac_equals_chord():
    w = geometry.wing_dict(geometry.tapered(1.5, 6.0, 1.0))
    assert w["c_mac"] == pytest.approx(w["c_root"]) and w["c_root"] == pytest.approx(0.25)


def test_elliptic_planform_has_the_requested_area_and_root_chord():
    p = geometry.elliptic(span=2.0, aspect_ratio=8.0, n_nodes=201)
    w = geometry.wing_dict(p)
    assert w["S"] == pytest.approx(0.5, rel=1e-3)
    # c(eta) = c0 sqrt(1 - eta^2), S = pi/4 b c0  ->  c0 = 4 S / (pi b)
    assert p.chord[0] == pytest.approx(4 * 0.5 / (math.pi * 2.0), rel=1e-6)
    assert p.chord[-1] == pytest.approx(0.0, abs=1e-9)


def test_sweep_moves_the_leading_edge_back():
    p = geometry.tapered(2.0, 8.0, 0.5, sweep_le_rad=math.radians(30.0))
    assert p.x_le[-1] - p.x_le[0] == pytest.approx(1.0 * math.tan(math.radians(30.0)))


def test_fuselage_holds_the_requested_volume_at_the_fineness_ratio():
    f = geometry.fuselage(volume_m3=0.004, fineness=6.0)
    assert f["volume"] == pytest.approx(0.004, rel=1e-6)
    assert f["length"] / f["diameter"] == pytest.approx(6.0)
    assert f["wetted_area"] > 0.0


def test_build_returns_every_component_and_positive_wetted_areas(nominal, fixed):
    g = geometry.build(nominal, fixed)
    for key in ("wing", "tail", "fuselage", "wetted_areas"):
        assert key in g
    assert all(v > 0 for v in g["wetted_areas"].values())
    assert set(g["wetted_areas"]) >= {"wing", "htail", "vtail", "fuselage"}

"""T10.4a: section data at low fidelity and from a polar."""
import numpy as np
import pytest

from drone import section


def test_low_fidelity_section_is_sane_at_the_nominal_point(fixed):
    s = section.low_fidelity(camber_pct=4.0, thickness_pct=12.0, reynolds=2e5, fixed=fixed)
    assert 0.9 < s.cl_max < 1.8
    assert -0.12 < s.alpha_L0 < 0.0
    cd = [s.cd_of_cl(c) for c in (0.2, 0.5, 0.8)]
    assert all(0.004 < c < 0.05 for c in cd)
    assert cd[2] >= cd[1] >= cd[0] * 0.999          # profile drag does not fall with lift


def test_more_camber_gives_more_cl_max_and_more_negative_alpha_l0(fixed):
    a = section.low_fidelity(0.0, 12.0, 2e5, fixed)
    b = section.low_fidelity(6.0, 12.0, 2e5, fixed)
    assert b.cl_max > a.cl_max and b.alpha_L0 < a.alpha_L0


def test_lower_reynolds_gives_more_profile_drag(fixed):
    lo = section.low_fidelity(4.0, 12.0, 1e5, fixed)
    hi = section.low_fidelity(4.0, 12.0, 4e5, fixed)
    assert lo.cd_of_cl(0.5) > hi.cd_of_cl(0.5)


def test_from_polar_interpolates_and_flags_an_unpeaked_polar():
    alpha = np.array([-2.0, 2.0, 6.0, 10.0, 14.0])
    cl = np.array([0.20, 0.62, 1.02, 1.30, 1.22])
    cd = np.array([0.012, 0.011, 0.016, 0.030, 0.060])
    s = section.from_polar(alpha, cl, cd, source="synthetic")
    assert s.cl_max == pytest.approx(1.30)
    assert abs(s.cd_of_cl(0.82) - 0.0135) < 1e-9        # linear in cl between the two middle points
    assert not s.flags
    mono = section.from_polar(alpha, np.linspace(0.2, 1.4, 5), cd, source="synthetic")
    assert "not_peaked" in mono.flags

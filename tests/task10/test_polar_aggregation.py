"""T10.7c and 7d: five case records become one section polar."""
import pytest

from analysis.drone_polar import polar


def record(alpha, cl, cd, status="converged"):
    return {"params": {"family": "airfoil2d", "alpha_deg": alpha, "reynolds": 2e5, "camber_pct": 4.0,
                       "thickness_pct": 12.0, "transition": "BCM"},
            "metrics": {"cl": cl, "cd": cd, "cm": -0.05}, "convergence": {"status": status},
            "case_id": f"airfoil2d-{int(alpha + 10):010d}"}


ALPHA = [-2.0, 2.0, 6.0, 10.0, 14.0]
CL = [0.20, 0.62, 1.02, 1.30, 1.22]
CD = [0.012, 0.011, 0.016, 0.030, 0.060]


def test_polar_from_five_converged_records():
    s = polar([record(a, c, d) for a, c, d in zip(ALPHA, CL, CD)])
    assert s.cl_max == pytest.approx(1.30)
    # the linear fit uses the angles with cl below 0.85 cl_max = 1.105: -2, 2, 6 deg
    slope = (1.02 - 0.20) / 8.0
    assert abs(s.cl_alpha_per_deg - slope) < 0.01
    # decision 8: a converged polar carries NO drift flags, but every SU2 polar carries the
    # recorded V6e bias and the ruling that accepted the high level with it
    assert all(f.startswith("v6e") for f in s.flags) and "v6e_ruling=decision8_accepted_with_bias" in s.flags
    assert s.source.startswith("airfoil2d")


def test_records_may_come_in_any_order():
    recs = [record(a, c, d) for a, c, d in zip(ALPHA, CL, CD)]
    assert polar(recs[::-1]).cl_max == polar(recs).cl_max


def test_a_failed_angle_is_flagged_and_the_polar_still_forms_if_three_remain():
    recs = [record(a, c, d) for a, c, d in zip(ALPHA, CL, CD)]
    recs[4]["convergence"]["status"] = "diverged"
    s = polar(recs)
    assert "missing_angles" in s.flags and "not_peaked" in s.flags
    assert s.cl_max == pytest.approx(1.30)


def test_fewer_than_three_converged_angles_is_an_error():
    recs = [record(a, c, d, status="diverged") for a, c, d in zip(ALPHA, CL, CD)]
    recs[0]["convergence"]["status"] = recs[1]["convergence"]["status"] = "converged"
    with pytest.raises(ValueError):
        polar(recs)


def test_mixed_designs_are_refused():
    recs = [record(a, c, d) for a, c, d in zip(ALPHA, CL, CD)]
    recs[2]["params"]["camber_pct"] = 2.0
    with pytest.raises(ValueError):
        polar(recs)

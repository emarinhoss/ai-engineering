"""T10.5b: the nominal design lands in a plausible place, and the diagnostics are all present."""
from drone import evaluate

KEYS = ("endurance_h", "mtow_kg", "range_km", "v_cruise", "v_stall", "wing_loading", "re_cruise",
        "throttle_cruise", "static_margin", "cl_max", "e_span", "cd0", "masses", "closure_iterations",
        "closure_residual", "gates", "diagnostics")


def test_every_recorded_key_is_present(nominal, fixed):
    out = evaluate.evaluate(nominal, fixed)
    for k in KEYS:
        assert k in out, k


def test_nominal_design_is_a_plausible_small_drone(nominal, fixed):
    out = evaluate.evaluate(nominal, fixed)
    assert 1.0 < out["mtow_kg"] < 8.0
    assert 0.5 < out["endurance_h"] < 12.0
    assert 8.0 < out["v_cruise"] < 30.0
    assert 20.0 < out["wing_loading"] < 150.0
    assert 8e4 <= out["re_cruise"] <= 5e5
    assert 0.0 < out["throttle_cruise"] <= 0.5 + 1e-9        # installed power at least twice the cruise power
    assert 0.8 < out["e_span"] <= 1.0


def test_high_fidelity_section_is_used_when_given(nominal, fixed):
    import numpy as np
    from drone import section
    alpha = np.array([-2.0, 2.0, 6.0, 10.0, 14.0])
    s = section.from_polar(alpha, np.array([0.1, 0.55, 0.95, 1.25, 1.15]),
                           np.array([0.015, 0.013, 0.018, 0.035, 0.07]), source="synthetic")
    low = evaluate.evaluate(nominal, fixed)
    high = evaluate.evaluate({**nominal, "fidelity": "high"}, fixed, section=s)
    assert high["cl_max"] == 1.25 and high["cl_max"] != low["cl_max"]
    assert high["diagnostics"]["section_source"] == "synthetic"

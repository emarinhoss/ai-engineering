"""T10.3: the vortex-lattice method against analytic wings and the Warren-12 benchmark (V6a to V6c)."""
import math

import pytest
import yaml

from drone import geometry, vlm
from tests.task10.conftest import helmbold, lifting_line

WARREN = "data/validation/warren12.yaml"


def test_elliptic_wing_has_unit_span_efficiency_and_helmbold_slope():
    p = geometry.elliptic(span=4.0, aspect_ratio=8.0, n_nodes=41)
    d = vlm.derivatives(p, level="fine")
    assert abs(d["CL_alpha"] / helmbold(8.0) - 1.0) < 0.02
    r = vlm.solve(p, math.radians(4.0), level="fine")
    assert abs(r["e"] - 1.0) < 0.01
    assert abs(r["CDi"] - r["CL"] ** 2 / (math.pi * 8.0 * r["e"])) < 1e-9


def test_high_aspect_ratio_rectangular_wing_tends_to_lifting_line():
    p = geometry.tapered(span=100.0, aspect_ratio=100.0, taper_ratio=1.0)
    d = vlm.derivatives(p, level="fine")
    assert abs(d["CL_alpha"] / lifting_line(100.0) - 1.0) < 0.01


def test_flat_wing_has_zero_lift_at_zero_alpha():
    p = geometry.tapered(2.0, 8.0, 0.5)
    r = vlm.solve(p, 0.0)
    assert abs(r["CL"]) < 1e-12 and abs(r["CDi"]) < 1e-12
    assert abs(vlm.derivatives(p)["alpha_L0"]) < 1e-12


def test_camber_shifts_the_zero_lift_angle_the_right_way():
    from drone import naca
    p = geometry.tapered(2.0, 8.0, 0.5)

    def cam(x):                                     # dy_c/dx of a 4-percent camber line
        return naca.camber_line(x, 0.04, 0.4)[1]
    d = vlm.derivatives(p, camber=cam)
    assert d["alpha_L0"] < -math.radians(2.0)          # cambered: lift at zero alpha, negative alpha_L0
    assert vlm.solve(p, 0.0, camber=cam)["CL"] > 0.2


def test_warren_12_lift_and_moment_slopes():
    """CL_alpha 2.743 /rad and Cm_alpha -3.10 /rad about the reference point of the YAML (2 percent)."""
    with open(WARREN) as f:
        w = yaml.safe_load(f)["warren12"]
    if w.get("moment_reference_x") == "pending":
        pytest.skip("Warren-12 moment reference not yet established from a retrievable source (retrieval pending)")
    p = geometry.Planform(span=2.0 * w["semispan"], eta=[0.0, 1.0],
                          chord=[w["root_chord"], w["tip_chord"]],
                          x_le=[0.0, w["semispan"] * math.tan(math.radians(w["sweep_le_deg"]))],
                          x_ref=w["moment_reference_x"])
    d = vlm.derivatives(p, level="fine")
    assert abs(d["CL_alpha"] / w["CL_alpha_per_rad"] - 1.0) < 0.02
    # the benchmark normalises the moment by its reference chord (1.0), the solver by the MAC
    c_mac = geometry.wing_dict(p)["c_mac"]
    cm_alpha = d["Cm_alpha"] * c_mac / w["reference_chord"]
    assert abs(cm_alpha / w["Cm_alpha_per_rad"] - 1.0) < 0.02


def test_lattice_convergence_medium_to_fine(nominal):
    p = geometry.tapered(nominal["span_m"], nominal["aspect_ratio"], nominal["taper_ratio"])
    med, fine = (vlm.derivatives(p, level=lv) for lv in ("medium", "fine"))
    assert abs(med["CL_alpha"] / fine["CL_alpha"] - 1.0) < 0.01
    e_med = vlm.solve(p, math.radians(4.0), "medium")["e"]
    e_fine = vlm.solve(p, math.radians(4.0), "fine")["e"]
    assert abs(e_med / e_fine - 1.0) < 0.01


def test_section_lift_distribution_is_root_to_tip_and_vanishes_at_the_tip():
    p = geometry.tapered(2.0, 10.0, 0.6)
    r = vlm.solve(p, math.radians(5.0), "medium")
    assert len(r["eta"]) == len(r["cl"]) == vlm.LEVELS["medium"][1]
    assert all(0.0 < a < b < 1.0 for a, b in zip(r["eta"][:-1], r["eta"][1:]))
    assert r["cl"][-1] < 0.5 * r["cl"][0]
    # the strip loads integrate to the wing CL: sum(cl_i c_i d_eta_i) b/2 / S
    import numpy as np
    chord = np.interp(r["eta"], p.eta, p.chord)
    d_eta = np.gradient(np.asarray(r["eta"]))
    cl_wing = float(np.sum(np.asarray(r["cl"]) * chord * d_eta) * (p.span / 2) * 2 / (0.4))
    assert abs(cl_wing / r["CL"] - 1.0) < 0.05

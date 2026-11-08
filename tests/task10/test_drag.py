"""T10.4b: the drag build-up."""
import math

from drone import drag, geometry, section, vlm


def test_skin_friction_laws_match_the_textbook_values():
    assert abs(drag.cf_turbulent(1e6) / (0.074 * 1e6 ** -0.2) - 1.0) < 1e-9     # Prandtl-Schlichting
    assert abs(drag.cf_laminar(1e5) / (1.328 / math.sqrt(1e5)) - 1.0) < 1e-9    # Blasius
    assert drag.cf(4.9e5) == drag.cf_laminar(4.9e5) and drag.cf(5.1e5) == drag.cf_turbulent(5.1e5)


def test_parasite_drag_lists_every_component_and_sums_to_total(nominal, fixed):
    g = geometry.build(nominal, fixed)
    d = drag.parasite(g, V=15.0, fixed=fixed)
    parts = {k: v for k, v in d.items() if k != "total"}
    assert set(parts) >= {"fuselage", "htail", "vtail"}
    assert abs(sum(parts.values()) - d["total"]) < 1e-12
    assert 0.003 < d["total"] < 0.03


def test_total_drag_is_induced_plus_profile_plus_parasite(nominal, fixed):
    g = geometry.build(nominal, fixed)
    p = geometry.tapered(nominal["span_m"], nominal["aspect_ratio"], nominal["taper_ratio"])
    r = vlm.solve(p, math.radians(4.0))
    s = section.low_fidelity(4.0, 12.0, 2e5, fixed)
    t = drag.total(g, s, r, CL=r["CL"], V=15.0, fixed=fixed)
    assert abs(t["CD"] - (t["CD_induced"] + t["CD_profile"] + t["CD_parasite"])) < 1e-12
    assert abs(t["CD_induced"] - r["CL"] ** 2 / (math.pi * nominal["aspect_ratio"] * r["e"])) < 1e-9
    assert 0.015 < t["CD"] < 0.08

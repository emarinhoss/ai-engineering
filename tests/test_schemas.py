import copy

import pytest

from mcp_server.schemas import to_params, validate
from worker.make_case import case_id

BASE = {
    "inlet2r": {"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "tag": "test"},
    "wedge": {"family": "wedge", "theta1_deg": 8.0, "tag": "test"},
    "cylinder": {"family": "cylinder", "tag": "test"},
}

# (family, field, low, high): inclusive bounds of the table in 01_interfaces.md.
BOUNDS = [
    ("inlet2r", "theta1_deg", 5.0, 12.0),
    ("wedge", "theta1_deg", 2.0, 20.0),
    ("inlet2r", "theta2_deg", 5.0, 14.0),
    ("cylinder", "radius_m", 0.002, 0.05),
    ("wedge", "mach", 3.0, 5.0),
    ("wedge", "T_wall_K", 250.0, 1200.0),
    ("wedge", "max_iter", 100, 20000),
]


def with_value(family, field, value):
    p = copy.deepcopy(BASE[family])
    p[field] = value
    return p


@pytest.mark.parametrize("family,field,low,high", BOUNDS)
def test_bounds_accepted_at_the_bound_and_rejected_outside(family, field, low, high):
    eps = {"max_iter": 1, "radius_m": 1e-9}.get(field, 1e-6)
    for ok in (low, high):
        model, errors, _ = validate(with_value(family, field, ok))
        assert model is not None and errors == [], (field, ok, errors)
    for bad in (low - eps, high + eps):
        model, errors, _ = validate(with_value(family, field, bad))
        assert model is None and errors, (field, bad)
        assert any(field in e for e in errors)


def test_defaults_and_warning():
    model, errors, warnings = validate(BASE["cylinder"])
    p = to_params(model)
    assert errors == [] and warnings == []
    assert p["radius_m"] == 0.010 and p["mach"] == 4.0 and p["T_wall_K"] == 300.0
    assert p["solver"] == "NAVIER_STOKES" and p["mesh_level"] == "medium"
    assert p["save_volume"] is False and p["max_iter"] == 6000 and p["altitude_km"] == 30
    _, _, warnings = validate({**BASE["wedge"], "mach": 4.5})
    assert len(warnings) == 1 and "4.0" in warnings[0]


def test_required_and_forbidden_fields():
    assert validate({k: v for k, v in BASE["inlet2r"].items() if k != "theta2_deg"})[0] is None
    assert validate({k: v for k, v in BASE["wedge"].items() if k != "theta1_deg"})[0] is None
    assert validate({k: v for k, v in BASE["wedge"].items() if k != "tag"})[0] is None
    model, errors, _ = validate({**BASE["wedge"], "theta2_deg": 8.0})
    assert model is None and any("theta2_deg" in e and "not allowed" in e for e in errors)
    assert validate({**BASE["wedge"], "radius_m": 0.01})[0] is None
    assert validate({**BASE["cylinder"], "theta1_deg": 8.0})[0] is None


def test_unknown_field_and_bad_literals_rejected():
    for extra in ({"colour": "red"}, {"altitude_km": 25}, {"solver": "LES"},
                  {"mesh_level": "ultra"}, {"tag": "Has Space"}, {"tag": "x" * 33},
                  {"family": "sphere"}, {"mach": float("nan")}, {"save_volume": "yes"}):
        model, errors, _ = validate({**BASE["wedge"], **extra})
        assert model is None and errors, extra


def test_validate_never_raises():
    for junk in (None, [], "text", 3, {"family": {"a": 1}}, {}):
        model, errors, _ = validate(junk)
        assert model is None and errors


def test_case_id_stable_across_key_order_and_matches_make_case():
    raw = BASE["inlet2r"]
    reordered = dict(reversed(list(raw.items())))
    p1, p2 = to_params(validate(raw)[0]), to_params(validate(reordered)[0])
    assert p1 == p2 and case_id(p1) == case_id(p2)
    assert case_id(p1).startswith("inlet2r-")
    # An int and the equal float give the same id because the model converts to float.
    p3 = to_params(validate({**raw, "theta1_deg": 8})[0])
    assert case_id(p3) == case_id(p1)
    # Spelling out a default gives the same id; changing it does not.
    assert case_id(to_params(validate({**raw, "mach": 4.0})[0])) == case_id(p1)
    assert case_id(to_params(validate({**raw, "mach": 4.5})[0])) != case_id(p1)


def test_rans_sa_solver_accepted():
    model, errors, _ = validate({**BASE["inlet2r"], "solver": "RANS_SA"})
    assert errors == [] and model is not None and model.solver == "RANS_SA"

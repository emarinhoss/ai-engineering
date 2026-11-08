"""T10.6: the two schemas, the drone gates and the committed pool designs."""
import csv
import os

import pytest

from mcp_server.schemas import to_params, validate
from physics.gates import check


def test_schema_accepts_the_nominal_drone_and_fills_defaults(nominal):
    model, errors, _ = validate(nominal)
    assert errors == [] and model is not None
    p = to_params(model)
    assert p["fidelity"] == "low" and p["family"] == "drone"


@pytest.mark.parametrize("field, value, bound", [
    ("span_m", 3.5, "[1.2, 3]"), ("aspect_ratio", 20.0, "[6, 16]"), ("taper_ratio", 0.2, "[0.3, 1]"),
    ("battery_fraction", 0.5, "[0.2, 0.45]"), ("camber_pct", 7.0, "[0, 6]"), ("thickness_pct", 20.0, "[8, 15]"),
])
def test_schema_names_the_field_and_the_bound(nominal, field, value, bound):
    _, errors, _ = validate({**nominal, field: value})
    assert any(e.startswith(field) and bound in e for e in errors), errors


def test_schema_refuses_unknown_fields_and_inlet_fields(nominal):
    assert validate({**nominal, "theta1_deg": 8.0})[1]
    assert validate({**nominal, "wingspan": 2.0})[1]


def test_airfoil2d_schema_bounds():
    base = {"family": "airfoil2d", "camber_pct": 4.0, "thickness_pct": 12.0, "reynolds": 2e5,
            "alpha_deg": 6.0, "transition": "BCM", "tag": "test"}
    model, errors, _ = validate(base)
    assert errors == [] and to_params(model)["mesh_level"] == "medium"
    assert validate({**base, "reynolds": 7e5})[1]
    assert validate({**base, "alpha_deg": 20.0})[1]
    assert validate({**base, "transition": "GAMMA"})[1]
    assert validate({**base, "span_m": 2.0})[1]


def test_gates_pass_at_the_nominal_design(nominal):
    assert check(nominal) == []


def test_gate_messages_are_in_the_inlet_form(nominal):
    bad = check({**nominal, "span_m": 1.2, "aspect_ratio": 16.0, "taper_ratio": 0.3, "battery_fraction": 0.45})
    assert bad, "this corner must trip at least one gate (tip chord 0.08 m floor or Reynolds range)"
    for m in bad:
        assert m.startswith("gate ") and "(" in m and ")" in m, m


def test_reynolds_gate_fires_on_a_tiny_slow_wing(nominal):
    msgs = check({**nominal, "span_m": 1.2, "aspect_ratio": 16.0, "battery_fraction": 0.2})
    assert any(m.startswith("gate 1 (reynolds range)") for m in msgs), msgs


def test_tip_chord_floor(nominal):
    msgs = check({**nominal, "span_m": 1.2, "aspect_ratio": 16.0, "taper_ratio": 0.3})
    assert any(m.startswith("gate 4") and "tip chord" in m for m in msgs), msgs


def test_gates_are_pure_and_deterministic(nominal):
    assert check(nominal) == check(dict(nominal))


@pytest.mark.parametrize("path, n", [("designs/pool_drone96.csv", 96), ("designs/pool_drone_lf192.csv", 192)])
def test_committed_pools_are_gate_checked(path, n):
    assert os.path.exists(path), path
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == n
    from designs.make_pool_drone import HIGH, INPUTS, LOW
    for r in rows:
        p = {"family": "drone", "fidelity": "low", "tag": "pool", **{k: float(r[k]) for k in INPUTS}}
        assert all(lo <= p[k] <= hi for k, lo, hi in zip(INPUTS, LOW, HIGH))
        assert check(p) == [], (r, check(p))

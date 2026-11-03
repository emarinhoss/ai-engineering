"""Task 9 inputs: the continuous atmosphere (V5e), the inlet3r schema, and configs at other altitudes."""
import json
import math

import pytest

from cases.config import render
from mcp_server.schemas import to_params, validate
from physics.atmosphere import state, ussa1976
from physics.constants import ATMOSPHERE_TABLE
from worker.make_case import make, sha256_file

POOL = "runs/pool/inlet2r-029b302750"


def test_v5e_formula_equals_the_table_and_the_decisions_file():
    for z, row in ATMOSPHERE_TABLE.items():
        T, p = ussa1976(float(z))
        assert abs(T / row["T"] - 1) < 1e-4 and abs(p / row["p"] - 1) < 1e-4
    s = state(30)                                     # 00_decisions.md section 1
    assert (s["T"], s["p"]) == (226.509, 1197.03)
    assert math.isclose(s["rho"], 0.018410, rel_tol=1e-4)
    assert math.isclose(s["mu"], 1.4752e-5, rel_tol=1e-4)


def test_atmosphere_is_continuous_across_the_32_km_layer_boundary():
    below, above = ussa1976(32.16 - 1e-6), ussa1976(32.16 + 1e-6)   # 32 km geopotential is 32.16 km geometric
    assert abs(below[0] - above[0]) < 1e-3 and abs(below[1] / above[1] - 1) < 1e-5
    with pytest.raises(ValueError):
        ussa1976(50.0)


def test_inlet3r_schema_takes_the_envelope_and_old_families_stay_at_30_km():
    m, err, _ = validate({"family": "inlet3r", "theta1_deg": 7.0, "theta2_deg": 7.0, "theta3_deg": 7.0,
                          "mach": 4.5, "altitude_km": 28.0, "T_wall_K": 600.0, "tag": "t"})
    assert not err and to_params(m)["theta3_deg"] == 7.0
    _, err, _ = validate({"family": "inlet3r", "theta1_deg": 7.0, "theta2_deg": 7.0, "theta3_deg": 7.0,
                          "mach": 3.4, "altitude_km": 25, "tag": "t"})
    assert err == ["altitude_km: 25 outside [28, 35] for family inlet3r", "mach: 3.4 outside [3.5, 4.5] for family inlet3r"]
    _, err, _ = validate({"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "altitude_km": 31, "tag": "t"})
    assert err == ["altitude_km: 31 not allowed for family inlet2r (30 km only)"]
    m, _, _ = validate({"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "altitude_km": 30, "tag": "t"})
    assert to_params(m)["altitude_km"] == 30 and isinstance(to_params(m)["altitude_km"], int)   # case_id unchanged


def test_config_freestream_follows_altitude_and_30_km_text_is_unchanged(tmp_path):
    params = json.load(open(f"{POOL}/params.json"))
    recorded = json.load(open(f"{POOL}/result.json"))["solver"]["config_sha256"]
    job = make(params, tmp_path)                      # the template now reads T and p from the atmosphere
    assert recorded in (job["config_sha256"], sha256_file(tmp_path / "case.cfg"))
    markers = {m: [] for m in ("body", "cowl", "symmetry", "inlet", "top", "outlet_duct", "outlet_ext")}
    text = render({**params, "family": "inlet3r", "theta3_deg": 7.0, "altitude_km": 31.5}, {}, markers)
    T, p = ussa1976(31.5)
    assert f"FREESTREAM_TEMPERATURE= {T!r}" in text and f"FREESTREAM_PRESSURE= {p!r}" in text


def test_inlet3r_viscous_duct_outlet_imposes_the_three_shock_pressure_only_where_subsonic():
    markers = {m: [] for m in ("body", "cowl", "symmetry", "inlet", "top", "outlet_duct", "outlet_ext")}
    base = {"family": "inlet3r", "theta1_deg": 7.0, "theta2_deg": 7.0, "theta3_deg": 7.0, "mach": 4.0,
            "altitude_km": 30, "T_wall_K": 300.0, "solver": "NAVIER_STOKES"}
    lines = [l for l in render(base, {}, markers).splitlines() if "OUTLET" in l]
    p_back = 1197.03 * 1.9397633839844466 * (3.4949 / 1.9397633839844466) * (5.9227 / 3.4949)   # chain ratios (V5a)
    assert lines[0] == "MARKER_SUPERSONIC_OUTLET= ( outlet_ext )"
    assert lines[1].startswith("MARKER_OUTLET= ( outlet_duct, ") and abs(float(lines[1].split(",")[1].strip(" )")) / p_back - 1) < 1e-4
    euler = [l for l in render({**base, "solver": "EULER"}, {}, markers).splitlines() if "OUTLET" in l]
    assert euler == ["MARKER_SUPERSONIC_OUTLET= ( outlet_duct, outlet_ext )"]            # Euler: unchanged
    two = {"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "solver": "NAVIER_STOKES"}
    assert [l for l in render(two, {}, markers).splitlines() if "OUTLET" in l] == \
        ["MARKER_SUPERSONIC_OUTLET= ( outlet_duct, outlet_ext )"]                          # inlet2r: unchanged

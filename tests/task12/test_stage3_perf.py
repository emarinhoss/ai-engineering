"""Stage 3 performance runner on the frozen 2026-11-21d pusher record."""
import math
from pathlib import Path

import pytest

from conceptual import raymer_performance as perf
from conceptual.units import KT, RHO0, isa
from measurement import stage3_perf

DESIGN = Path(__file__).resolve().parents[2] / "runs/task12/stage1/2026-11-21d/design_pusher.json"
KEYS = {"id", "quantity", "unit", "stage1", "stage1_source", "stage3", "source", "deviation",
        "deviation_kind", "tolerance", "verdict", "note"}


@pytest.fixture(scope="module")
def result():
    return stage3_perf.compute(DESIGN)


def by_id(result, rid):
    return next(r for r in result["rows"] if r["id"] == rid)


def test_every_row_has_the_required_keys(result):
    assert len({r["id"] for r in result["rows"]}) == len(result["rows"])
    for r in result["rows"]:
        assert KEYS <= set(r), r["id"]
        assert r["verdict"] in ("within", "outside", "not judged", "not computed")
        assert r["note"] and r["source"]


def test_verdicts_agree_with_deviation_and_tolerance(result):
    for r in result["rows"]:
        if r["verdict"] in ("within", "outside"):
            assert (abs(r["deviation"]) <= r["tolerance"]) == (r["verdict"] == "within"), r["id"]
        elif r["verdict"] == "not computed":
            assert r["stage3"] is None and r["deviation"] is None
        else:
            assert r["tolerance"] is None


def test_rebuild_reproduces_the_record(result):
    for k, v in result["rebuild_check"].items():
        assert v["rebuilt"] == pytest.approx(v["record"], rel=1e-6), k


def test_best_range_speed_by_hand(result):
    """(L/D)max speed by hand from the record: V = sqrt(2 (W/S)/(rho CL)), CL = sqrt(CD0/K)."""
    import json
    d = json.loads(DESIGN.read_text())
    rho = isa(20000.0)["rho"]
    CL = math.sqrt(d["CD0"]["mission_altitude"] / d["K"])
    V = math.sqrt(2.0 * d["W_S"] / (rho * CL)) / KT
    r = by_id(result, "v_best_range")
    assert r["stage3"] == pytest.approx(V, rel=1e-9)
    assert r["deviation"] == pytest.approx(r["stage3"] / r["stage1"] - 1.0)
    assert r["stage1"] == pytest.approx(perf.speed_max_ld(d["W_S"], rho, d["CD0"]["mission_altitude"],
                                                          d["K"])[0] / KT)


def test_corner_speed_by_hand(result):
    import json
    d = json.loads(DESIGN.read_text())
    V = math.sqrt(2.0 * d["n_limit"] * d["W_S"] / (RHO0 * d["CL_max"]["clean"])) / KT
    assert by_id(result, "v_corner")["stage3"] == pytest.approx(V, rel=1e-9)


def test_anderson_w0_closes_with_historical_empty_fraction(result):
    aw = result["anderson_w0"]
    # (8.4): W0 = W_fixed/(1 - Wf/W0 - 0.62)
    assert aw["W0"] == pytest.approx(500.0 / (1.0 - aw["fuel_fraction"] - 0.62), rel=1e-6)


def test_field_rows_by_hand(result):
    """Take-off and landing rows are Anderson's relations at the rebuilt Stage 1 inputs; the sum of the
    parts quoted in each note's relation equals the row value (checked from a fresh call)."""
    import json

    from conceptual import uav
    from measurement import anderson as A
    d, L, b, _, _ = stage3_perf.rebuild(DESIGN)
    S, K = b["geom"]["S"], d["K"]
    thrust = uav._thrust_fn(b["bhp"], L, b["D_prop"])
    V_lo = 1.1 * A.stall_speed(d["W0_lb"] / S, RHO0, b["clmax"]["takeoff"])
    to = A.takeoff_distance(d["W0_lb"], S, RHO0, b["CD0_takeoff"], K, b["clmax"]["takeoff"],
                            thrust(0.7 * V_lo), L["rolling_mu"], L["cl_ground"])
    r = by_id(result, "takeoff_distance")
    assert r["stage3"] == pytest.approx(to["ground_roll"] + to["airborne"])
    assert r["verdict"] in ("within", "outside")
    assert r["tolerance"] == 0.15
    assert by_id(result, "landing_distance")["stage3"] > 0.0
    assert json.loads(DESIGN.read_text())["performance"]["takeoff_ft"] == r["stage1"]


def test_takeoff_power_row_meets_the_field_length(result):
    """The Mattingly take-off power, put back into the same route, gives the field length."""
    from conceptual import uav
    from measurement import mattingly as M
    d, L, b, _, _ = stage3_perf.rebuild(DESIGN)
    r = by_id(result, "power_takeoff")
    assert r["tolerance"] == 0.05 and r["stage3"] is not None
    s = M.takeoff_distance(d["W0_lb"], b["geom"]["S"], RHO0, b["CD0_takeoff"], d["K"],
                           b["clmax"]["takeoff"], uav._thrust_fn(r["stage3"], L, b["D_prop"]),
                           L["rolling_mu"], L["cl_ground"])["total"]
    assert s == pytest.approx(L["field_length_ft"], abs=1.0)


def test_gust_row_stays_not_computed_with_reason(result):
    r = by_id(result, "gust_n")
    assert r["verdict"] == "not computed" and r["stage3"] is None
    assert "no gust load factor relation" in r["note"] and "Raymer" in r["note"]

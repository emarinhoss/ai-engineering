"""Preliminary design P9 (closing re-record r1): tests of the findings list, of what r1 adds to Stage 1 and to the
info-gap rebuild, of the r1 ledger and of the loft measurements, written before any P9 record. No test asks r1 to pass
a row: acceptance is judged on the record (test_p9_record.py) and a failed row is reported. What is tested is that
each new piece does what its docstring says, that without the r1 entries every r0 number is unchanged, and that the
new Stage 1 terms equal the routes of the packages they come from (P0's climb, P4b's weights, P1's +10 % CD0).
"""
import json
import math

import numpy as np
import pytest
import yaml

from conceptual import raymer_weights as wts
from conceptual import uav
from measurement import info_gap
from prelim import p0_baseline as p0
from prelim import p4_methods as m
from prelim import p9_r1 as p9

R0_DESIGN = p9.R0 / "design_pusher.json"
P4B = json.loads(p9.P4B_RECORD.read_text())
BS = P4B["candidates"][P4B["selection"]["chosen"]]


@pytest.fixture(scope="module")
def built():
    return info_gap.Built(R0_DESIGN)


@pytest.fixture(scope="module")
def state(built):
    """r0 rebuilt at its record's take-off weight (the weights P4b's ratios start from)."""
    return built.build({}, 11.0, W0=built.d["W0_lb"])


# ---- the findings list --------------------------------------------------------------------------------------------
def test_every_finding_value_is_the_value_at_its_record_and_key():
    for f in p9.findings():
        rec = json.loads((p9.REPO / f["record"]).read_text())
        assert p9.pick(rec, f["key"]) == f["value"], f["id"]
        for prop in f.get("proposals", []):
            assert p9.pick(rec, prop["key"]) == prop["value"], (f["id"], prop["entry"])


def test_every_finding_says_applied_or_not_with_a_reason_and_an_applied_one_names_its_entry():
    ids = [f["id"] for f in p9.findings()]
    assert len(ids) == len(set(ids))
    for f in p9.findings():
        assert isinstance(f["applied"], bool) and f["reason"].strip(), f["id"]
        if f["applied"]:
            assert f["entry"] in set(p9.fixed_entries()) | set(p9.MEASURED) | {"airfoil_cl_max", "airfoil_cm0"}, f["id"]


def test_the_brief_s_not_applied_items_are_not_applied():
    by = {f["id"]: f for f in p9.findings()}
    for fid in ("P1-3", "P1-4", "P2-4", "P6-1", "P7-1", "P5-1", "P4b-9"):
        assert by[fid]["applied"] is False, fid
    assert by["P1-4"]["value"] == 5 and len(by["P1-4"]["proposals"]) == 5


# ---- Stage 1 without the r1 entries is r0 ---------------------------------------------------------------------------
def test_r0_rebuilds_with_the_new_code_to_its_record(built):
    assert built.check["fuel_lb"]["rebuilt"] == pytest.approx(built.check["fuel_lb"]["record"], rel=1e-12)
    assert built.hours_detail({})[0] == pytest.approx(11.0, abs=2e-5)


def test_drag_areas_are_stage1_s_without_factors_and_scale_with_them(state):
    b, L = state
    g = b["geom"]
    plain = uav.drag_areas(g, L)
    assert plain == {"wing": g["s_wet_wing"], "fuselage": g["s_wet_fus"], "horizontal_tail": g["s_wet_ht"],
                     "vertical_tail": g["s_wet_vt"], "sponsons": g["s_wet_sponsons"]}
    scaled = uav.drag_areas(g, dict(L, loft_wetted_factor_fuselage=0.9))
    assert scaled["fuselage"] == pytest.approx(0.9 * g["s_wet_fus"], rel=1e-15) and scaled["wing"] == g["s_wet_wing"]


def test_a_record_without_r1_entries_carries_no_r1_fields(state):
    from conceptual import stage1
    b, L = state
    assert stage1.preliminary_design_fields(b, L) == {}


# ---- the integrated climb (P1-1) --------------------------------------------------------------------------------------
def test_integrated_climb_equals_p0_s_integration_on_r0(built, state):
    b, L = state
    S = built.S_record
    row = next(r for r in b["mission"] if r[0] == "climb")
    alt = uav.isa(L["mission_altitude_ft"])
    V_cr = uav._cruise_speed(row[1], S, alt["rho"], b["CD0_alt"], b["K"], b["clmax"]["clean"], L, "range")[0]
    ref = p0.integrate_climb(p0.climb_point_fn(b, L, S), row[1], np.arange(0.0, 20500.0, 1000.0).tolist(), V_end=V_cr)
    mine = uav.integrated_climb(row[1], b["geom"], b["K"], b["bhp"], b["D_prop"], b["clmax"], L, b["engine_model"], V_cr)
    assert mine["fuel_lb"] == pytest.approx(ref["fuel_lb"], rel=1e-12)
    assert mine["time_s"] == pytest.approx(ref["time_s"], rel=1e-12)


def test_the_mission_flies_the_integrated_climb_when_the_ledger_says_so(built, state):
    b, L = state
    b2, _ = built.build({"climb_model": "integrated"}, 11.0, W0=built.d["W0_lb"])
    two = next(r for r in b["mission"] if r[0] == "climb")
    one = next(r for r in b2["mission"] if r[0] == "climb")
    assert two[1] == one[1]
    # P0's record: the integrated climb and Stage 1's two-point climb at nominal values (its section 7.2)
    rec = json.loads((p9.REPO / "runs/task12/pd/2026-11-27/p0/p0.json").read_text())["climb"]
    assert one[1] - one[2] == pytest.approx(rec["integrated"]["fuel_lb"], rel=1e-12)
    assert two[1] - two[2] == pytest.approx(rec["stage1_two_point_fuel_lb"], rel=1e-12)


def test_the_integrated_climb_without_power_cannot_be_flown_and_the_study_knows_the_message(built):
    assert any("cannot climb to the mission altitude" in u for u in info_gap.UNFLYABLE)
    f, reason = built.fuel_at({"climb_model": "integrated", "engine_power_mult": 0.05}, 1.0)
    assert math.isinf(f) and reason


# ---- P4b's route in Stage 1 (P4b-1 to P4b-4) --------------------------------------------------------------------------
def _r0_weights_inputs(state):
    b, L = state
    d = json.loads(R0_DESIGN.read_text())
    f = wts.composite_fudge(L["composite_factor"], L.get("composite_model"))
    return b, L, d, f


def test_fuselage_weight_with_the_extension_is_p4b_s_route(state):
    b, L, d, f = _r0_weights_inputs(state)
    ext = BS["layout"]["extension"]
    L1 = dict(L, fuselage_added_skin_ft2=ext["added_skin_ft2"], shaft_lb_per_ft=ext["shaft_lb_per_ft"])
    g = dict(b["geom"], extension=ext["length_ft"])
    total, added = uav.fuselage_weight(g, L1, b["Nz"], d["W0_lb"], b["q_design"], f["fuselage"])
    assert total == pytest.approx(BS["layout"]["weights"]["fuselage"], rel=1e-9)
    assert added == pytest.approx(BS["measures"]["weight_changes_lb"]["fuselage"], rel=1e-9)
    base, zero = uav.fuselage_weight(b["geom"], L, b["Nz"], d["W0_lb"], b["q_design"], f["fuselage"])
    assert base == pytest.approx(d["components_lb"]["fuselage"], rel=1e-12) and zero == 0.0


def test_flight_controls_and_tailplane_with_the_r1_entries_are_p4b_s(state):
    b, L, d, f = _r0_weights_inputs(state)
    ext = BS["layout"]["extension"]
    fc = wts.flight_controls(b["geom"]["L_f"] + ext["length_ft"], b["geom"]["wing"].span, b["Nz"], d["W0_lb"])
    assert fc == pytest.approx(BS["layout"]["weights"]["flight_controls"], rel=1e-9)
    L1 = dict(L, tail_trailing_edges="straight")
    ht = f["tails"] * wts.horizontal_tail(b["Nz"], d["W0_lb"], b["q_design"], d["horizontal_tail"]["area"], L["tail_t_c"],
                                          L["ht_aspect_ratio"], uav.tail_sweep(L1, "quarter_chord"), L["ht_taper"])
    assert ht == pytest.approx(BS["layout"]["weights"]["horizontal_tail"], rel=1e-9)


def test_tail_slopes_and_sweeps_are_p4_s(state):
    _, L = state
    L1 = dict(L, tail_trailing_edges="straight")
    for which in ("horizontal", "vertical"):
        assert uav.tail_le_slope(L1, which) == pytest.approx(m.tail_le_slope(L, which), rel=1e-15)
        assert uav.tail_le_slope(L, which) == 0.0
    lay = {"tail_te_straight": True}
    assert uav.tail_sweep(L1, "max_thickness") == pytest.approx(math.atan(0.7 * m.tail_le_slope(L, "horizontal")), rel=1e-15)
    from conceptual import raymer_aero as aero
    assert aero.lift_slope(L["ht_aspect_ratio"], 0.0, L["airfoil_efficiency"], uav.tail_sweep(L1, "max_thickness")) == \
        pytest.approx(m.tail_lift_slope(L, lay), rel=1e-15)


# ---- the info-gap rebuild with held values (PD-26 item 9) --------------------------------------------------------------
def test_built_overrides_give_p1_s_plus_10_percent_cd0_hours():
    b = info_gap.Built(R0_DESIGN, overrides={"leakage_fraction": 0.155})
    # P1's band audit, leakage_fraction 0.155 on the built r0: 10.418227431235366 h (p1.json ledger.audit.rows.30.points.2)
    assert b.hours_detail({})[0] == pytest.approx(10.418227431235366, rel=1e-9)
    assert info_gap.Built(R0_DESIGN).overrides == {}


# ---- the r1 ledger ------------------------------------------------------------------------------------------------
def test_the_r1_ledger_text_changes_two_values_and_adds_unbanded_entries(tmp_path):
    inputs = {k: 1.0 for k in p9.MEASURED}
    path = tmp_path / "ledger_r1.yaml"
    path.write_text(p9.ledger_r1_text(inputs, tmp_path / "inputs.json"))
    L, entries = uav.load_ledger(path)
    L0, entries0 = uav.load_ledger(p9.LEDGER_GATE_B)
    assert L["airfoil_cl_max"] == 1.41777 and L["airfoil_cm0"] == -0.0911291
    assert entries["airfoil_cl_max"]["band"] == entries0["airfoil_cl_max"]["band"]
    assert entries["airfoil_cm0"]["band"] == entries0["airfoil_cm0"]["band"]
    new = set(L) - set(L0)
    assert new == set(p9.fixed_entries()) | set(p9.MEASURED)
    assert all("band" not in entries[k] for k in new)
    assert {k for k in L0 if L0[k] != L[k]} == {"airfoil_cl_max", "airfoil_cm0"}
    banded = lambda e: sorted(k for k, q in e.items() if "band" in q)
    assert banded(entries) == banded(entries0)


def test_the_committed_r1_ledger_is_what_the_code_writes_from_its_inputs_record():
    if not p9.LEDGER_R1.exists():
        pytest.skip("no r1 ledger committed yet")
    head = p9.LEDGER_R1.read_text().splitlines()[2]
    src = head.split("measurement ")[1].split(".")[0] + ".json"
    values = json.loads((p9.REPO / src).read_text())["values"]
    assert p9.LEDGER_R1.read_text() == p9.ledger_r1_text(values, p9.REPO / src)


def test_ledger_in_use_switches_the_sizing_s_ledger_and_restores_it(tmp_path):
    from measurement import robust_sizing as rs
    path = tmp_path / "ledger.yaml"
    path.write_text(p9.ledger_r1_text({k: 1.0 for k in p9.MEASURED}, tmp_path / "inputs.json"))
    before = uav.LEDGER
    with p9.ledger_in_use(path):
        assert rs.ledger_values()["airfoil_cl_max"] == 1.41777
        assert dict(rs._nominal_tuple())["airfoil_cl_max"] == 1.41777
    assert uav.LEDGER == before and rs.ledger_values()["airfoil_cl_max"] == 1.5


# ---- the loft measurements -----------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def reference():
    A = yaml.safe_load(p9.ARRANGEMENT.read_text())
    d, L0, ext, mult, src = p9.reference_record()
    return d, dict(L0, **{k: v["value"] for k, v in p9.fixed_entries().items()}), A, ext, mult


def test_the_reference_is_p4b_s_chosen_layout_on_r0(reference):
    d, L, A, ext, mult = reference
    assert d["layout"]["x_le"] == BS["layout"]["x_le"] and d["layout"]["x_main"] == BS["layout"]["x_main"]
    assert d["horizontal_tail"]["area"] == BS["layout"]["ht_area"] and "le_slope" in d["horizontal_tail"]
    assert ext == BS["measures"]["extension_ft"]
    assert mult == pytest.approx(BS["evaluation"]["neutral_point"]["Cma_fus_multhopp_per_rad"] / 0.10143039814429375, rel=1e-9)


def test_the_loft_of_the_reference_has_the_longer_body_and_the_propeller_behind_it(reference):
    d, L, A, ext, _ = reference
    model = p9.loft(d, L, A, ext)
    assert model["fuselage"].length == pytest.approx(BS["measures"]["fuselage_length_ft"], rel=1e-12)
    assert model["propeller"]["x"] == pytest.approx(BS["measures"]["propeller_plane_x_ft"], rel=1e-12)
    assert p9.added_skin(d, L, A, ext) == pytest.approx(BS["measures"]["added_wetted_ft2"]["fuselage"], rel=1e-9)


def test_r0_s_sponson_does_not_hold_the_gear_and_the_scaled_one_just_does(reference):
    d, L, A, ext, _ = reference
    need = A["arrangement"]["box_clearance_in"]["value"]
    assert p9.gear_clearance_in(d, L, A, ext) < need             # P3 finding 7
    s = p9.sponson_scale(d, L, A, ext)
    k = s["scale"]
    assert s["clearance_in"] >= need - 1e-9
    assert p9.gear_clearance_in(p9.with_sponson(d, k - p9.SPONSON_TOL), L, A, ext) < need
    assert s["bracket"][1] - s["bracket"][0] <= p9.SPONSON_TOL


def test_the_area_factors_are_the_loft_s_areas_over_stage1_s(reference):
    d, L, A, ext, _ = reference
    f, parts = p9.area_and_tank_factors(d, L, A, ext)
    for k in p9.COMPONENTS:
        r = parts["gate3"]["components"][k]
        assert f["loft_wetted_factor_" + k] == pytest.approx(r["loft_wetted_ft2"] / r["stage1_ft2"], rel=1e-15)
    # without the extension, r0's own loft gives P3's recorded tank volume over Stage 1's claim
    d0 = json.loads(R0_DESIGN.read_text())
    L0 = uav.load_ledger(p9.R0 / "ledger.yaml")[0]
    f0, _ = p9.area_and_tank_factors(d0, L0, A, 0.0)
    assert f0["tank_volume_factor"] == pytest.approx(68.24154001010257 / 73.1687706763378, rel=1e-9)
    assert f0["loft_wetted_factor_sponsons"] == pytest.approx(47.03290253869907 / 63.65994590948411, rel=1e-9)


def test_compare_inputs_uses_the_stated_tolerances():
    used = {k: 1.0 for k in p9.MEASURED}
    rows, ok = p9.compare_inputs(used, dict(used))
    assert ok
    rows, ok = p9.compare_inputs(used, dict(used, fuselage_extension_ft=1.0 + 1.5 * p9.TOL_LENGTH_FT))
    assert not ok and not rows["fuselage_extension_ft"]["within"]
    rows, ok = p9.compare_inputs(used, dict(used, sponson_size_factor=1.0 + 0.5 * p9.TOL_RATIO))
    assert ok

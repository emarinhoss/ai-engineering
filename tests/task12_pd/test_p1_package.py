"""Preliminary design P1 (docs/specs/task12_preliminary_design.md, "P1. Stage 1 package for r0"): the acceptance
tests of the package, written before prelim/p1_package.py.

The spec's acceptance rows are tested here on the baseline record r0 itself and on the judgement file; the
tests of the committed P1 record are in test_p1_record.py. Tolerances are the spec's (0.1 lb on the weight
statement, 1e-6 on the V-n points) or are fixed here before any run; a test may not loosen one.
"""
import json
import math
import re

import pytest
import yaml

from conceptual import stage1, uav
from prelim import p1_package as p1

R0_DESIGN = json.loads((p1.R0 / "design_pusher.json").read_text())
JUDGE = yaml.safe_load(p1.JUDGEMENTS.read_text())
PACKAGE_2026_11_25 = p1.REPO / "docs/validation/2026-11-25_task12_conceptual_m250_appl.md"


@pytest.fixture(scope="module")
def rebuilt():
    """r0 sized again by the function that sized it (a few seconds); every test of a computed part reads this."""
    return p1.rebuild_r0()


# ---- the numbers fixed before the run ------------------------------------------------------------------
def test_tolerances_and_inputs_are_the_ones_fixed_in_the_spec():
    assert (p1.TOL_WEIGHT_LB, p1.TOL_VN, p1.TOL_REPRODUCE) == (0.1, 1e-6, 1e-9)
    assert p1.TOL_CLIMB_FUEL == 0.01                     # the P0 row-5 threshold, used again at the corner
    assert p1.PAYLOAD_DENSITY_LB_FT3 == 30.0             # PD-12
    assert p1.R0 == p1.REPO / "runs/task12/pd/2026-11-27/p0/r0"
    assert p1.CURVE == p1.REPO / "runs/task12/stage3/2026-11-26/m250_bands_resize/curve.json"
    assert (p1.W_S, p1.ASPECT) == (13.0, 8.0) == (R0_DESIGN["W_S"], R0_DESIGN["A"])


# ---- "every number is read from r0": the rebuild is r0 ---------------------------------------------------
def test_rebuild_is_r0_field_by_field(rebuilt):
    c = rebuilt["reproduction"]
    assert c["n_compared"] > 300 and not c["different"] and not c["added"] and not c["removed"]
    assert c["max_relative_difference"] <= p1.TOL_REPRODUCE


def test_lookup_reads_a_record_by_path():
    assert p1.lookup(R0_DESIGN, "W0_lb") == R0_DESIGN["W0_lb"]
    assert p1.lookup(R0_DESIGN, "layout.nose_load.full") == R0_DESIGN["layout"]["nose_load"]["full"]
    assert p1.lookup({"rows": [{"id": "a", "v": 1}, {"id": "b", "v": 2}]}, "rows[id=b].v") == 2
    with pytest.raises(KeyError):
        p1.lookup(R0_DESIGN, "layout.no_such_field")


# ---- compliance matrix: no blank row ----------------------------------------------------------------------
def test_compliance_matrix_has_every_requirement_and_no_blank_cell(rebuilt):
    info_gap = json.loads((p1.R0 / "info_gap.json").read_text())
    rows = p1.compliance_matrix(rebuilt["compliance_rows"], R0_DESIGN, info_gap, rubber_bhp=180.0)
    named = {r for row in rows for r in row["requirement_id"].split("/")}
    assert {f"R{i}" for i in range(1, 20)} <= named
    assert p1.blank_cells(rows) == []
    for row in rows:
        assert row["verdict"] in ("pass", "fail") or row["verdict"].startswith("not tested: ")
        assert row["evidence_class"] and row["step"]
    # a row with a numeric rule carries a numeric margin with the sign of its verdict
    for row in rows:
        if isinstance(row["margin"], float):
            assert (row["margin"] >= -1e-9) == (row["verdict"] == "pass"), row
    assert not [r for r in rows if r["verdict"] == "fail"]            # r0 is the Gate B aircraft


def test_blank_cells_finds_an_empty_cell():
    row = {"requirement_id": "R1", "requirement": "x", "value": "", "limit": 1.0, "margin": None, "units": "-",
           "rule": "<=", "verdict": "pass", "evidence_class": "c", "step": "s"}
    assert p1.blank_cells([row]) == [("R1", "value"), ("R1", "margin")]


# ---- weight statement: sums to the record's empty weight within 0.1 lb ---------------------------------------
def test_weight_statement_sums_to_the_empty_weight():
    w = p1.weight_statement(R0_DESIGN)
    assert len(w["rows"]) == len(R0_DESIGN["components_lb"]) == 13
    assert abs(w["sum_components_lb"] - R0_DESIGN["We_lb"]) <= p1.TOL_WEIGHT_LB
    assert w["within_tolerance"] is True
    assert abs(w["We_lb"] + w["payload_lb"] + w["fuel_lb"] - R0_DESIGN["W0_lb"]) <= p1.TOL_WEIGHT_LB
    for row in w["rows"]:
        assert row["weight_lb"] == R0_DESIGN["components_lb"][row["item"]]
        assert row["x_ft"] == R0_DESIGN["stations"][row["item"]]["x"]
    # the centre of gravity from the stations is the record's, empty of fuel and full
    assert w["cg_empty_from_stations_ft"] == pytest.approx(R0_DESIGN["layout"]["cg_empty"], rel=1e-9)
    assert w["cg_full_from_stations_ft"] == pytest.approx(R0_DESIGN["layout"]["cg_full"], rel=1e-9)


# ---- V-n points equal r0's vn entries to 1e-6 ---------------------------------------------------------------
def test_vn_points_are_the_record_entries():
    pts = p1.vn_points(R0_DESIGN)
    assert len(pts) == 1 + 4 * 4
    vn = R0_DESIGN["vn"]
    assert pts[0] == {"case": "manoeuvre", "point": "corner", "V_eas_kt": vn["V_corner_eas_kt"], "n": R0_DESIGN["n_limit"]}
    for p in pts[1:]:
        g = vn["gust_" + p["case"]]
        speed = g["V_cruise_eas_kt"] if p["point"].startswith("V_C") else g["V_dive_eas_kt"]
        key = {"V_C up": "n_cruise", "V_C down": "n_cruise_neg", "V_D up": "n_dive", "V_D down": "n_dive_neg"}[p["point"]]
        assert abs(p["V_eas_kt"] - speed) <= p1.TOL_VN and abs(p["n"] - g[key]) <= p1.TOL_VN
    assert {p["case"] for p in pts[1:]} == {k[5:] for k in vn if k.startswith("gust_")}


# ---- out-of-calibration list ------------------------------------------------------------------------------------
def flagged_bullets():
    """The bullets under "Used outside its calibration" in the 2026-11-25 package."""
    text = PACKAGE_2026_11_25.read_text()
    block = text.split("Used outside its calibration", 1)[1].split("\n## ", 1)[0]
    return [ln[2:] for ln in block.splitlines() if ln.startswith("- ")]


def test_every_correlation_flagged_on_2026_11_25_is_in_the_list_or_has_a_reason():
    bullets = flagged_bullets()
    assert len(bullets) == len(p1.FLAGGED_2026_11_25) == 8
    for tag, bullet in zip(p1.FLAGGED_2026_11_25, bullets):
        assert tag in bullet, (tag, bullet)                           # the tags are the document's, in its order
    entries = JUDGE["out_of_calibration"]
    assert entries, "the out-of-calibration list is empty"
    for tag in p1.FLAGGED_2026_11_25:
        mine = [e for e in entries if e["flagged_2026_11_25"] == tag]
        assert len(mine) == 1, f"{tag}: flagged on 2026-11-25 and {'missing' if not mine else 'listed twice'}"
        e = mine[0]
        assert e["status"] in p1.OC_STATUS
        if e["status"] != "applies":
            assert len(e["used_here"]) > 20, f"{tag}: no stated reason"       # the reason it no longer applies to r0
    assert p1.check_out_of_calibration(entries) == []


def test_out_of_calibration_check_refuses_a_missing_flag():
    entries = [e for e in JUDGE["out_of_calibration"] if e["flagged_2026_11_25"] != "(13.9)"]
    assert any("(13.9)" in problem for problem in p1.check_out_of_calibration(entries))


# ---- risk list -----------------------------------------------------------------------------------------------------
def test_every_risk_names_its_package_or_the_ruling_that_carries_it():
    risks = JUDGE["risks"]
    assert risks, "the risk list is empty"
    assert p1.check_risks(risks) == []
    for r in risks:
        assert set(r["measured_by"]) <= set(p1.PACKAGES)
        assert r["measured_by"] or r.get("carried_under"), r["id"]
        assert r["how"] and r["effect"]
    # the named risk of ruling B-9g (item 8) is there, with the package that sizes the wing from the bottom up
    weight = [r for r in risks if 8 in r["items"]]
    assert len(weight) == 1 and "P7" in weight[0]["measured_by"]
    # every entry item of the Gate B report (items 1 to 8) is some risk; item 5 is this package itself
    assert set(range(1, 9)) - {5} <= {i for r in risks for i in r["items"]}


def test_risk_check_refuses_a_risk_without_package_or_ruling():
    bad = [{"id": "K-x", "risk": "r", "effect": "e", "how": "h", "items": [], "measured_by": []}]
    assert p1.check_risks(bad) and "K-x" in p1.check_risks(bad)[0]
    bad[0]["measured_by"] = ["P11"]
    assert p1.check_risks(bad)


def test_every_evidence_path_of_the_judgement_file_exists():
    files = p1.evidence_files()
    for group in ("risks", "out_of_calibration"):
        for entry in JUDGE[group]:
            for ev in entry.get("evidence", []):
                if ev["file"] != "p1":                                # p1 paths are checked on the record
                    assert isinstance(p1.lookup(files[ev["file"]], ev["path"]), (int, float, bool)), ev


# ---- band audit ------------------------------------------------------------------------------------------------------
def test_band_audit_covers_exactly_the_58_entries_without_a_band():
    _, entries = uav.load_ledger(p1.R0 / "ledger.yaml")
    unbanded = [k for k, q in entries.items() if "band" not in q]
    assert len(entries) == 111 and len(unbanded) == 58
    audit = JUDGE["band_audit"]
    assert sorted(audit) == sorted(unbanded)
    assert p1.check_band_audit(audit, entries) == []
    for name, a in audit.items():
        assert a["class"] in p1.BAND_CLASSES and a["reason"]
        if a["class"] == "needs a band":
            if a["proposed_band"] is None:
                assert a["why_no_proposal"]
            else:
                lo, hi = a["proposed_band"]
                assert lo <= entries[name]["value"] <= hi and a["basis"]        # a proposal contains the value
            assert "measured_by" in a and set(a["measured_by"]) <= set(p1.PACKAGES)
        else:
            assert "proposed_band" not in a
    # the 19 entries of the ledger's requirements group are requirements or definitions, never "needs a band"
    raw = yaml.safe_load((p1.R0 / "ledger.yaml").read_text())
    assert all(audit[k]["class"] != "needs a band" for k in raw["requirements"] if k in audit)


def test_band_audit_proposals_are_not_in_the_ledger():
    """A proposed band is listed for Gate C and not applied: the ledger of the repository still has no band there."""
    _, entries = uav.load_ledger()
    for name in JUDGE["band_audit"]:
        assert "band" not in entries[name], name


# ---- empty weight, component by component ------------------------------------------------------------------------
def test_table_15_2_groups_sum_to_the_record_value(rebuilt):
    e = p1.empty_weight_explanation(R0_DESIGN, rebuilt["s_exposed_ft2"], rebuilt["ledger"])
    groups = e["table_15_2"]["groups"]
    W0 = R0_DESIGN["W0_lb"]
    assert sum(g["table_15_2_lb"] for g in groups) == pytest.approx(
        R0_DESIGN["empty_fraction_comparison"]["table_15_2_approximate"] * W0, rel=1e-9)
    assert sum(g["build_up_lb"] for g in groups) == pytest.approx(R0_DESIGN["We_lb"], abs=p1.TOL_WEIGHT_LB)
    assert sorted(i for g in groups for i in g["items"]) == sorted(R0_DESIGN["components_lb"])
    # the metal build-up of the groups is the record's metal fraction
    assert sum(g["build_up_metal_lb"] for g in groups) == pytest.approx(
        R0_DESIGN["empty_fraction_comparison"]["build_up_metal"] * W0, rel=1e-9)


def test_fit_to_build_up_steps_close_exactly(rebuilt):
    e = p1.empty_weight_explanation(R0_DESIGN, rebuilt["s_exposed_ft2"], rebuilt["ledger"])
    c = R0_DESIGN["empty_fraction_comparison"]
    steps = e["table_3_1"]["steps"]
    assert steps[0]["fraction"] == c["table_3_1"] and steps[-1]["fraction"] == c["build_up"]
    assert sum(s["change"] for s in steps[1:]) == pytest.approx(c["build_up"] - c["table_3_1"], abs=1e-12)
    like = e["table_3_1"]["like_for_like"]
    assert like["gap_lb"] == pytest.approx((c["build_up_metal_with_crew_items"] - c["table_3_1_metal"]) * R0_DESIGN["W0_lb"])
    assert like["gap_lb"] == pytest.approx(sum(f["metal_lb"] for f in like["features"]) + like["remainder_lb"], abs=1e-9)


def test_scale_by_exponent():
    assert p1.scaled_weight(100.0, 2.0, 1.0) == 200.0
    assert p1.scaled_weight(100.0, 4.0, 0.5) == pytest.approx(200.0)
    assert p1.scaled_weight(100.0, 1.0, 0.896) == 100.0


# ---- payload bay, first check ---------------------------------------------------------------------------------------
def test_fuselage_volume_is_raymer_7_13():
    assert p1.fuselage_volume(10.0, 8.0, 5.0) == pytest.approx(3.4 * 10.0 * 8.0 / (4.0 * 5.0))
    # the Stage 1 body: both projected areas are fill x length x diameter
    fill, L, d = 0.8, 28.0, 3.5
    assert p1.fuselage_volume(fill * L * d, fill * L * d, L) == pytest.approx(0.85 * fill ** 2 * L * d ** 2)


def test_drawn_body_has_the_ledger_fill_inside_its_band():
    L, d = R0_DESIGN["fuselage"]["length"], R0_DESIGN["fuselage"]["diameter"]
    assert p1.body_radius(0.0, L, d) == 0.0
    assert p1.body_radius(0.4 * L, L, d) == pytest.approx(0.5 * d)
    assert p1.body_radius(L, L, d) == pytest.approx(0.15 * 0.5 * d)
    lo, hi = uav.load_ledger(p1.R0 / "ledger.yaml")[1]["fuselage_fill"]["band"]
    assert lo <= p1.drawn_body_fill(L, d) <= hi
    # volume of a slice of the cylindrical part is the cylinder's
    assert p1.drawn_body_volume(0.3 * L, 0.5 * L, L, d) == pytest.approx(math.pi / 4 * d ** 2 * 0.2 * L, rel=1e-6)


def test_payload_bay_first_check_reads_pd_12(rebuilt):
    b = p1.payload_bay(R0_DESIGN, rebuilt["ledger"])
    assert b["payload_volume_ft3"] == pytest.approx(R0_DESIGN["payload_lb"] / 30.0)
    L, d = R0_DESIGN["fuselage"]["length"], R0_DESIGN["fuselage"]["diameter"]
    assert b["body_volume_ft3"] == pytest.approx(0.85 * rebuilt["ledger"]["fuselage_fill"] ** 2 * L * d ** 2)
    assert b["free_volume_ft3"] == pytest.approx(b["body_volume_ft3"] - sum(i["volume_ft3"] for i in b["deducted"]))
    assert b["fits_in_free_volume"] == (b["payload_volume_ft3"] <= b["free_volume_ft3"])
    assert b["not_deducted"]                                          # what the record gives no size for is said
    # the local reading: a bay centred on the payload station that holds the PD-12 volume at full cross-section
    n = b["nose"]
    assert p1.drawn_body_volume(n["bay_from_ft"], n["bay_to_ft"], L, d) == pytest.approx(b["payload_volume_ft3"], rel=1e-6)
    assert 0.5 * (n["bay_from_ft"] + n["bay_to_ft"]) == pytest.approx(R0_DESIGN["stations"]["payload"]["x"])


# ---- trades and concepts ---------------------------------------------------------------------------------------------
def test_hours_for_fuel_inverts_a_fuel_curve():
    assert p1.hours_for_fuel(lambda h: 100.0 + 50.0 * h, 400.0) == pytest.approx(6.0, abs=1e-6)
    assert p1.hours_for_fuel(lambda h: 100.0 + 50.0 * h + 0.5 * h ** 2, 400.0) == pytest.approx(
        (-50.0 + math.sqrt(2500.0 + 600.0)), abs=1e-3)
    assert p1.hours_for_fuel(lambda h: 500.0 + h, 400.0) == 0.0       # the fuel is gone before any loiter
    assert p1.hours_for_fuel(lambda h: math.inf, 400.0) == 0.0        # not flyable


def test_resized_nominal_trade_is_r0(rebuilt):
    row = p1.resized(rebuilt["ledger_sizing"], {})
    assert row["W0_lb"] == pytest.approx(R0_DESIGN["W0_lb"], rel=p1.TOL_REPRODUCE)
    assert row["fuel_lb"] == pytest.approx(R0_DESIGN["fuel_lb"], rel=p1.TOL_REPRODUCE)
    assert row["failed"] == []


def test_score_break_even_ratio():
    """The pusher-over-tractor weight ratio at which the two weighted scores are equal, from the round-1 weights."""
    r = p1.break_even_weight_ratio(stage1.ROUND1_WEIGHTS)
    w0_weight = stage1.ROUND1_WEIGHTS[0][1]
    tractor = w0_weight * 5.0 + sum(w * gt for _, w, gt, gp in stage1.ROUND1_WEIGHTS[1:])
    pusher = w0_weight * 5.0 / r + sum(w * gp for _, w, gt, gp in stage1.ROUND1_WEIGHTS[1:])
    assert pusher == pytest.approx(tractor) and r > 1.0


def test_carpet_rows_are_the_committed_grid():
    rows = p1.carpet_rows(json.loads(p1.CURVE.read_text()))
    mine = [r for r in rows if (r["W_S"], r["A"]) == (13.0, 8.0)]
    assert len(mine) == 1 and mine[0]["W0_lb"] == R0_DESIGN["W0_lb"] and mine[0]["ok"]
    assert len(rows) == 20 and sum(r["ok"] for r in rows) == 7
    assert all(r["ok"] or r["status"] for r in rows)                  # a cell without a design says why


# ---- climb speed against the stall at the top of the climb (item 18) ---------------------------------------------
def test_stall_margin_of_a_climb_speed():
    rho = 0.0012673                                                    # 20,000 ft ISA, slug/ft^3 (conceptual/units.py)
    m = p1.climb_speed_margin(V_kt=90.0, W_lb=3000.0, S_ft2=250.0, rho=rho, clmax=1.2, floor=1.2)
    v_stall = math.sqrt(2.0 * 3000.0 / 250.0 / (rho * 1.2)) / 1.68781
    assert m["V_stall_kt"] == pytest.approx(v_stall, rel=1e-4)
    assert m["over_stall"] == pytest.approx(90.0 / v_stall, rel=1e-4)
    assert m["above_stall"] == (90.0 >= v_stall) and m["above_floor"] == (90.0 >= 1.2 * v_stall)


def test_no_number_of_the_aircraft_is_typed_in_the_judgement_file():
    """The judgement file may carry bands, item numbers and ruling names, not results: no number with a decimal
    point outside the band audit's proposed bands and extra values."""
    text = p1.JUDGEMENTS.read_text()
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    risks = re.sub(r"\(\d+\.\d+\)", "", body.split("\nrisks:", 1)[1])        # equation tags such as (16.22) are not results
    assert not re.findall(r"\d+\.\d+", risks), "a decimal number is typed in the risk list"


def test_weight_exponents_are_the_ones_of_the_group_equations():
    """The what-if scalings of the empty-weight explanation use the exponents of (15.46), (15.47) and (15.50)."""
    from conceptual import raymer_weights as wts
    assert wts.main_gear(4.5, 3000.0, 60.0) / wts.main_gear(4.5, 3000.0, 30.0) == pytest.approx(2.0 ** p1.EXP_MAIN_GEAR_LENGTH)
    a = wts.horizontal_tail(5.7, 3500.0, 40.0, 140.0, 0.12, 4.0, 0.0, 0.5)
    b = wts.horizontal_tail(5.7, 3500.0, 40.0, 70.0, 0.12, 4.0, 0.0, 0.5)
    assert a / b == pytest.approx(2.0 ** p1.EXP_HT_AREA)
    a = wts.wing(300.0, 500.0, 8.0, 0.0, 40.0, 0.45, 0.15, 5.7, 3500.0)
    b = wts.wing(150.0, 500.0, 8.0, 0.0, 40.0, 0.45, 0.15, 5.7, 3500.0)
    assert a / b == pytest.approx(2.0 ** p1.EXP_WING_AREA)

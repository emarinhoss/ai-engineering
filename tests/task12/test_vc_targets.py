"""Tests of the per-design V_C placard (owner ruling 2026-11-23), the fixed-h targets of the robustness curve
and the review items RC2-5 and RC2-6."""
import pytest
import yaml

from conceptual import stage1, uav
from conceptual.units import KT, isa
from measurement import info_gap
from measurement import robust_sizing as rs


# ---- the per-design V_C rule ---------------------------------------------------------------------------------
@pytest.mark.parametrize("fastest,expected", [
    (0.0, 110.0), (80.0, 110.0), (100.0, 110.0),            # 1.1 x 100 = 110: the 110 kt floor
    (100.2, 115.0),                                         # 110.22 rounds UP to 115, not to 110
    (104.0, 115.0), (104.5, 115.0),                         # 114.95
    (104.6, 120.0),                                         # 115.06 rounds up to 120
    (118.0, 130.0),                                         # 129.8
])
def test_per_design_vc_rounds_up_to_5_kt_and_never_below_110(fastest, expected):
    assert uav.per_design_vc_kt(fastest) == expected


@pytest.fixture(scope="module")
def fast_design():
    """480 hp, W/S 15, A 8: fastest sub-step 105 kt EAS, so V_C goes above the 110 kt floor."""
    return rs.sized_aircraft_guess(480.0, 15.0, 8.0, 8.0, rs.first_guess(480.0, 8.0), "per_design")


def test_per_design_vc_follows_the_fastest_step_and_r18_holds(fast_design):
    a, L, rec = fast_design
    d = a["design"]
    fastest = max(m[7] * (isa(L["mission_altitude_ft"])["sigma"]) ** 0.5 for m in d["mission"]) / KT
    assert rec["fastest_step_eas_kt"] == pytest.approx(fastest, rel=1e-12)
    vc = uav.per_design_vc_kt(fastest)
    assert vc > 110.0 and rec["V_c_rule"] == "per_design"
    assert all(v == pytest.approx(vc * KT) for v in d["V_c_eas"].values())       # the same at every altitude
    assert d["q_design"] == pytest.approx(0.5 * 0.0023769 * (vc * KT) ** 2, rel=1e-3)
    comp = stage1.compliance(d, d["ledger_used"], a["layout"], a["performance"], *a["fuel_volume"], rs._raw())
    r18 = next(c for c in comp if c["requirement"].startswith("R18"))
    assert r18["met"] is True


def test_built_aircraft_ledger_fixes_the_chosen_vc_and_drops_the_rule(fast_design):
    _, L, rec = fast_design
    assert "vc_placard_rule" not in L
    assert L["vc_placard_kt_eas"] == pytest.approx(rec["V_c_eas_kt"]["sea_level"])
    text = yaml.safe_load(rs.ledger_text(9.0, L["vc_placard_kt_eas"]))
    flat = {**text["requirements"], **text["assumptions"]}
    assert "vc_placard_rule" not in flat
    assert flat["vc_placard_kt_eas"]["value"] == pytest.approx(L["vc_placard_kt_eas"])
    assert text["requirements"]["loiter_h"]["value"] == 9.0
    # a rebuild with the built ledger keeps V_C: the weight at the nominal member is the record's
    from conceptual.engine_model import TP100_TABLE
    built = info_gap.Built("in memory", True, record=(rec, L, TP100_TABLE))
    nominal = info_gap.nominal_theta(info_gap.uncertain_variables(uav.load_ledger()[1]))
    assert built.w0_for(nominal) == pytest.approx(rec["W0_lb"], abs=0.1)


def test_fixed_rule_is_the_round4_placard_and_unchanged():
    """With the rule set to fixed (the round-4 behaviour), sizing equals stage1.analyse without the rule."""
    L0, _ = uav.load_ledger()
    assert L0["vc_placard_rule"] == "per_design"            # owner ruling 2026-11-23
    _, _, rec = rs.sized_aircraft_guess(400.0, 13.0, 8.0, 8.0, rs.first_guess(400.0, 8.0), vc_rule="fixed")
    ref = stage1.analyse("pusher", 13.0, 8.0, {k: v for k, v in dict(L0, loiter_h=8.0).items() if k != "vc_placard_rule"},
                         rs._engine(400.0), W0_guess=rs.first_guess(400.0, 8.0))
    assert rec["W0_lb"] == pytest.approx(ref["design"]["W0"], rel=1e-12)
    assert rec["fuel_lb"] == pytest.approx(ref["design"]["fuel"], rel=1e-12)
    assert rec["V_c_eas_kt"]["sea_level"] == pytest.approx(110.0) and rec["V_c_rule"] == "fixed"


def test_ledger_text_without_vc_keeps_the_ledgers_rule():
    text = yaml.safe_load(rs.ledger_text(9.0))
    L0, _ = uav.load_ledger()
    assert {**text["requirements"], **text["assumptions"]}["vc_placard_rule"]["value"] == L0["vc_placard_rule"]


# ---- scaled corners at the target h ----------------------------------------------------------------------------
def test_scaled_corner_at_h1_is_the_seed_and_moves_further_out_at_larger_h():
    E, C = rs.seed_sets()
    nom = dict(rs._nominal_tuple())
    for c in E + C:
        s1 = rs.scaled_corner(c["moved"], 1.0)
        assert set(s1) == set(c["moved"])
        assert all(s1[k] == pytest.approx(c["moved"][k], rel=1e-9) for k in s1)
        s105, s110 = rs.scaled_corner(c["moved"], 1.05), rs.scaled_corner(c["moved"], 1.10)
        assert set(s105) == set(c["moved"]) == set(s110)
        for k in s105:       # same direction, further from the nominal value
            sign = 1 if c["moved"][k] > nom[k] else -1
            assert sign * (s105[k] - nom[k]) > sign * (s1[k] - nom[k]) > 0.0
            assert sign * (s110[k] - nom[k]) > sign * (s105[k] - nom[k])


def test_scaled_corner_is_the_u_of_h_corner_in_the_same_directions():
    E, _ = rs.seed_sets()
    nom = dict(rs._nominal_tuple())
    dirs = {v["name"]: (0 if k not in E[0]["moved"] else 1 if E[0]["moved"][k] > nom[k] else -1)
            for v in rs._variables() for k in [v["name"]]}
    expect = rs.moved_of(info_gap.corner_theta(rs._variables(), 1.05, dirs))
    assert rs.scaled_corner(E[0]["moved"], 1.05) == expect


def test_scaled_sets_are_labelled_with_their_target():
    E, C = rs.scaled_sets(1.05)
    assert E and C and all("1.05" in c["label"] for c in E + C)


# ---- RC2-6: the speed grid of the cliff ratio is the grid of uav._leg_speed ---------------------------------------
def test_transit_ratio_speed_grid_matches_uav_leg_speed():
    """info_gap.leg_power_ratio is the minimum over the grid uav._leg_speed searches: at the engine power that
    makes it exactly 1, _leg_speed must find a speed; a hair below it must raise 'no speed on the leg'. If either
    grid (start, step or number of points) changes alone, one side fails."""
    a, L, _ = rs.sized_aircraft(400.0, 13.0, 8.0, 8.0)
    d = a["design"]
    S = d["geom"]["S"]
    alt = isa(L["mission_altitude_ft"])
    model = d["engine_model"]
    for W in (0.92 * d["W0"], 0.8 * d["W0"]):
        for mode in ("loiter", "range"):
            L_t = dict(L, headwind_kt=0.0)
            r = info_gap.leg_power_ratio(W, S, alt, L["mission_altitude_ft"], d["CD0_alt"], d["K"], d["clmax"]["clean"],
                                         L_t, model, d["bhp"])
            args = (W, S, alt, L["mission_altitude_ft"], d["CD0_alt"], d["K"], d["clmax"]["clean"], L_t, mode, model)
            uav._leg_speed(*args, d["bhp"] * r * (1.0 + 1e-6))
            with pytest.raises(ValueError, match="no speed on the leg"):
                uav._leg_speed(*args, d["bhp"] * r * (1.0 - 1e-6))


# ---- RC2-6: no retry on 'did not converge'; status text -----------------------------------------------------------
def test_did_not_converge_is_not_retried():
    calls = []

    def run(g):
        calls.append(g)
        raise ValueError("take-off weight iteration did not converge (fractions may sum near 1)")
    res, info = rs.close_with_retry(run, 4000.0)
    assert res is None and calls == [4000.0] and info["no_retry"] and not info["retried"]
    assert "did not converge" in rs.closure_status(info, 8.0) and "not retried" in rs.closure_status(info, 8.0)


def test_status_text_says_no_l_on_the_lattice():
    L, status = rs.bisect_two_corner(lambda L: "heavy" if L > 9.0 else "small")
    assert L is None and "no L satisfies both on the lattice" in status


# ---- RC2-5: report helpers --------------------------------------------------------------------------------------
def test_reason_labels_keep_their_digits_and_name_the_row():
    comp = {"ok": True, "failed": ["R9 negative gust within the negative limit, with the round-4 margin"], "status": "bisected"}
    assert rs.reason_label(comp) == "meets both corners but fails Stage 1 row: R9 negative gust within the negative limit"
    heavy = {"ok": False, "failed": [], "status": "too heavy already at 8 h (last heavy point: cliff corner not flyable: x)"}
    assert "cliff corner not flyable" in rs.reason_label(heavy) and "#" not in rs.reason_label(heavy)
    lattice = {"ok": False, "failed": [], "status": "no L satisfies both on the lattice (bisection grid of 1/32 h): too few"}
    assert rs.reason_label(lattice).startswith("no L on the lattice satisfies both corners")


def test_dirty_note_separates_untracked_outputs_from_modified_code():
    note = rs.dirty_note(["?? runs/x/", " M measurement/robust_sizing.py"])
    assert "1 tracked file(s) modified" in note and "1 untracked path(s)" in note and "not the commit alone" in note
    assert "clean" in rs.dirty_note([])


# ---- review fixes: V_C outside the weight loop, unresolved cells, built ledger only ---------------------------------
def test_limit_cycle_case_converges_and_vc_satisfies_the_rule():
    """420 hp, W/S 12.5, A 8, 8.5 h: V_C inside the weight iteration cycled between 110 and 115 kt (did not converge)."""
    a, L, rec = rs.sized_aircraft_guess(420.0, 12.5, 8.0, 8.5, rs.first_guess(420.0, 8.0), "per_design")
    vc = rec["V_c_eas_kt"]["sea_level"]
    info = rec["vc_placard"]
    assert vc >= uav.per_design_vc_kt(rec["fastest_step_eas_kt"])
    assert info["used_kt"] == vc and info["rule_kt"] == uav.per_design_vc_kt(rec["fastest_step_eas_kt"])
    assert info["exact"] == (vc == info["rule_kt"]) and info["steps"][-1]["vc_kt"] == vc


def test_vc_loop_steps_up_until_the_placard_holds_and_keeps_a_safe_value():
    """Fake sizer: the fastest step is 104 kt at V_C 110 (rule 115), 100 kt at 115 (rule would be 110)."""
    def size(Ls):
        return {"fastest_step_eas_kt": 104.0 if Ls["vc_placard_kt_eas"] < 115.0 else 100.0}
    d = uav.size_with_vc_rule({"vc_placard_rule": "per_design"}, size)
    assert d["vc_placard"]["used_kt"] == 115.0 and d["vc_placard"]["rule_kt"] == 110.0
    assert d["vc_placard"]["exact"] is False and [s["vc_kt"] for s in d["vc_placard"]["steps"]] == [110.0, 115.0]
    fixed = uav.size_with_vc_rule({"vc_placard_rule": "fixed"}, lambda Ls: {"fastest_step_eas_kt": 104.0})
    assert "vc_placard" not in fixed


def test_did_not_converge_is_unresolved_not_heavy():
    """close_with_retry gives None for 'did not converge'; classify must not call that 'heavy'."""
    def never(Lh):
        raise ValueError("take-off weight iteration did not converge (fractions may sum near 1)")
    orig = rs.sized_aircraft_guess
    rs.sized_aircraft_guess = lambda P, W_S, A, Lh, g, vc_rule=None: never(Lh)
    try:
        row = rs.evaluate_candidate_sets(400.0, 13.0, 8.0, [], [], 3.5, {}, vc_rule="per_design")
    finally:
        rs.sized_aircraft_guess = orig
    assert row["ok"] is False and row["unresolved"] is True and "did not converge" in row["status"]
    assert [t["class"] for t in row["trace"]] == ["unresolved"]
    assert rs.reason_label(row).startswith("unresolved")


def test_bisection_stops_at_unresolved():
    seen = []

    def classify(L):
        seen.append(L)
        return "unresolved" if L > 9.0 else "small"
    L, status = rs.bisect_two_corner(classify)
    assert L is None and status.startswith("unresolved") and len(seen) < 8


def test_built_refuses_a_per_design_ledger_and_sized_aircraft_drops_the_rule():
    from conceptual.engine_model import TP100_TABLE
    a, L, rec = rs.sized_aircraft(400.0, 13.0, 8.0, 8.0)
    assert "vc_placard_rule" not in L and L["vc_placard_kt_eas"] == pytest.approx(rec["V_c_eas_kt"]["sea_level"])
    with pytest.raises(ValueError, match="per_design"):
        info_gap.Built("in memory", True, record=(rec, dict(L, vc_placard_rule="per_design"), TP100_TABLE))
    info_gap.Built("in memory", True, record=(rec, L, TP100_TABLE))

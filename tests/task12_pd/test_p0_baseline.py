"""Preliminary design P0 (docs/specs/task12_preliminary_design.md): the engine table to 35,000 ft, the
re-sized baseline against the Gate B record, the climb integration, and the record-hygiene items.

The tolerances are the spec's (P0, "Acceptance, fixed now") and are read from prelim.p0_baseline, which copies
them; a test here may not loosen one. The tests of the committed r0 record are in test_p0_record.py.
"""
import json

import numpy as np
import pytest

from conceptual import uav
from conceptual.engine_model import M250_TABLE, TP100_TABLE, TableEngine
from measurement import bands_cells
from measurement import m250_engine as m250
from measurement import robust_sizing as rs
from measurement import stage3_perf as sp
from measurement import tp100_engine as tp
from prelim import p0_baseline as p0
from prelim import record

GATE_B_TABLE = p0.GATE_B / "m250_table.json"


def test_spec_tolerances_are_the_ones_fixed_in_the_spec():
    assert (p0.TOL_TABLE, p0.TOL_FIELDS, p0.TOL_CEILING_FT, p0.TOL_MISSION_FUEL, p0.TOL_HORIZON) == (
        1e-12, 1e-9, 1000.0, 0.01, 1e-4)
    assert p0.STEP_FT == 1000.0 and p0.OLD_TOP_FT == 30000.0


# ---- acceptance row 1: the table -----------------------------------------------------------------------
def test_m250_grid_keeps_every_old_altitude_and_reaches_35000_ft():
    assert m250.TABLE_H[:len(tp.TABLE_H)] == tp.TABLE_H
    assert m250.TABLE_H[-1] == 35000.0 and m250.TABLE_H == sorted(m250.TABLE_H)
    assert tp.TABLE_H[-1] == 30000.0 and len(tp.TABLE_H) == 13          # the TP100 grid is not touched
    assert json.loads(TP100_TABLE.read_text())["h_ft"] == tp.TABLE_H


def test_committed_table_equals_the_gate_b_table_at_or_below_30000_ft():
    c = p0.compare_tables(json.loads(GATE_B_TABLE.read_text()), json.loads(M250_TABLE.read_text()))
    assert c["passed"] and c["every_old_altitude_kept"] and c["new_top_ft"] == 35000.0
    for a in c["arrays_at_or_below_old_top"].values():
        assert a["max_relative_difference"] <= p0.TOL_TABLE
    assert all(c["other_keys_equal"].values())
    assert [r["h_ft"] for r in c["new_rows"]] == [32500.0, 35000.0]


def test_new_rows_carry_the_choked_flag_and_power_keeps_falling():
    t = json.loads(M250_TABLE.read_text())
    lp = np.array(t["lp_turbine_pressure_ratio"])
    assert lp.shape == (15, 11, 19) and np.isfinite(lp).all() and np.isfinite(np.array(t["bsfc"])).all()
    c = p0.compare_tables(json.loads(GATE_B_TABLE.read_text()), t)
    for r in c["new_rows"]:
        assert r["all_finite"] and 0 < r["choked_cells"] < r["cells"] and r["power_below_row_beneath_at_every_speed"]
    e = TableEngine(M250_TABLE)
    choked_full, ratio = e.turbine_choked(35000.0, 110.0, e.power_available(35000.0, 110.0))
    assert choked_full and ratio >= e.crit                     # full throttle is choked, as at every altitude
    assert not e.turbine_choked(35000.0, 110.0, 0.1 * e.power_available(35000.0, 110.0))[0]


def test_one_table_row_from_the_generator_is_the_committed_row():
    """tp.table computes each altitude row on its own: the 35,000 ft row made alone equals the committed one."""
    t = json.loads(M250_TABLE.read_text())
    one = tp.table(m250.calibrate(**m250.NOMINAL), rated_shp=m250.RATED_SHP, calibration_bsfc=m250.BSFC_TAKEOFF,
                   altitudes=[35000.0])
    assert one["h_ft"] == [35000.0]
    assert one["full_throttle_shp"][0] == t["full_throttle_shp"][-1]
    assert one["bsfc"][0] == t["bsfc"][-1]


def test_compare_tables_catches_a_changed_cell_and_a_dropped_altitude():
    old = json.loads(GATE_B_TABLE.read_text())
    new = json.loads(M250_TABLE.read_text())
    bad = json.loads(json.dumps(new))
    bad["bsfc"][3][4][5] *= 1.0 + 1e-9
    assert not p0.compare_tables(old, bad)["passed"]
    bad = json.loads(json.dumps(new))
    bad["h_ft"][5] += 1.0
    assert not p0.compare_tables(old, bad)["passed"]
    assert not p0.compare_tables(old, old)["passed"]            # no new row: not the extension


def test_lookup_is_unchanged_up_to_30000_ft_and_no_longer_held_above_it():
    old, new = TableEngine(GATE_B_TABLE), TableEngine(M250_TABLE)
    rng = np.random.default_rng(20261127)
    for h, v, f in zip(rng.uniform(0.0, 30000.0, 200), rng.uniform(30.0, 230.0, 200), rng.uniform(0.1, 1.0, 200)):
        assert new.power_available(h, v) == old.power_available(h, v)
        shp = f * new.power_available(h, v)
        assert new.bsfc(h, v, shp) == old.bsfc(h, v, shp)
        assert new.turbine_choked(h, v, shp) == old.turbine_choked(h, v, shp)
    assert new.power_available(30000.0, 95.0) == old.power_available(30000.0, 95.0)
    assert old.power_available(32500.0, 95.0) == old.power_available(30000.0, 95.0)       # the old clamp
    assert new.power_available(35000.0, 95.0) < new.power_available(32500.0, 95.0) < new.power_available(30000.0, 95.0)
    assert new.power_available(40000.0, 95.0) == new.power_available(35000.0, 95.0)       # still clamped at the new top


# ---- acceptance rows 2 to 4: the design ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def resized(tmp_path_factory):
    """W/S 13, A 8 sized again as P0 does it, written to a temporary record folder."""
    was = rs.ENGINE_AS_IS
    rs.use_engine_as_is(True)
    try:
        row = bands_cells.source_row(p0.W_S, p0.ASPECT)
        rec, reads = p0.table_reads_above_top(lambda: bands_cells.size_cell(row))
        design = rs.write_record_rec(row, tmp_path_factory.mktemp("r0"), rec)
    finally:
        rs.use_engine_as_is(was)
    return design, json.loads(design.read_text()), reads


def test_resized_design_equals_gate_b_in_every_field_but_the_ceiling(resized):
    _, rec, _ = resized
    old = json.loads((p0.GATE_B / "design_pusher.json").read_text())
    c = p0.compare_fields(old, rec, p0.TOL_FIELDS, skip=(p0.CEILING_FIELD,))
    assert c["different"] == [] and c["removed"] == [] and c["n_compared"] > 300
    assert [s["path"] for s in c["skipped"]] == [p0.CEILING_FIELD]
    # the two B-9c fields are the only additions: the Gate B record was made before commit 5bb3f81 stored them
    assert sorted(a["path"] for a in c["added"]) == ["performance.engine_table_top_ft",
                                                     "performance.service_ceiling_above_table_top"]


def test_ceiling_flag_is_stored_false_and_the_ceiling_is_lower_than_the_clamped_one(resized):
    _, rec, reads = resized
    per = rec["performance"]
    old = json.loads((p0.GATE_B / "design_pusher.json").read_text())["performance"]["service_ceiling_ft"]
    assert per["service_ceiling_above_table_top"] is False and per["engine_table_top_ft"] == 35000.0
    assert p0.OLD_TOP_FT < per["service_ceiling_ft"] < old
    # what is still read above the top: the first two probes of uav.ceiling's bisection from 60,000 ft, nothing else
    assert reads == [37500.0, 45000.0]


def test_ceiling_is_inside_the_spec_tolerance_of_the_engine_cycle_value_and_r12_holds(resized):
    design = resized[0]
    c = p0.ceiling_study(design, m250.calibrate(**m250.NOMINAL))
    assert c["within"] and max(abs(x) for x in c["deviation_ft"]) <= p0.TOL_CEILING_FT
    assert c["independent_of_reads_above_top"]
    assert c["r12_required_ft"] == 23500.0 and c["r12_met_by_both"]
    band = c["engine_cycle_family_ft"]
    assert band["min"] <= c["engine_cycle_nominal_member_ft"] <= band["max"]       # the table's member is in its family
    assert abs(c["table_minus_nominal_cycle_ft"]) < 100.0                           # what linear interpolation leaves


def test_ceiling_refactor_kept_the_function_the_bisection_uses(resized):
    design, rec, _ = resized
    d, L, b, _, _ = sp.rebuild(design)
    bd = dict(b, W0=d["W0_lb"], W_S=d["W_S"])
    assert uav.ceiling(bd, L) == rec["performance"]["service_ceiling_ft"]
    rate, _ = uav.climb_rate_at(bd, L, rec["performance"]["service_ceiling_ft"], uav.climb_power_default(bd, L))
    assert 60.0 * rate == pytest.approx(L["ceiling_rate_fpm"], abs=1e-3)           # 100 ft/min at the ceiling


# ---- acceptance row 5: the climb -----------------------------------------------------------------------------
def test_integrate_climb_closed_forms():
    """Constant rate r and fuel flow f: time H/r and fuel f H/r ((17.44), (17.45)); with a speed change the time is
    the energy-height change over the rate ((17.88))."""
    r, f, H = 20.0, 0.05, 20000.0
    alts = np.arange(0.0, H + 1.0, 1000.0).tolist()
    out = p0.integrate_climb(lambda h, W: (r, 150.0, f), 3500.0, alts)
    assert out["time_s"] == pytest.approx(H / r, rel=1e-12)
    assert out["fuel_lb"] == pytest.approx(f * H / r, rel=1e-12)
    assert out["distance_ft"] == pytest.approx(150.0 * H / r, rel=1e-12)
    assert out["W_end"] == pytest.approx(3500.0 - f * H / r, rel=1e-12) and len(out["steps"]) == 20
    fast = p0.integrate_climb(lambda h, W: (r, 150.0, f), 3500.0, alts, V_end=200.0)
    dhe = H + (200.0 ** 2 - 150.0 ** 2) / (2.0 * 32.174)
    assert fast["time_s"] == pytest.approx(dhe / r, rel=1e-12)
    flat = p0.integrate_climb(lambda h, W: (r, 150.0, f), 3500.0, alts, V_end=200.0, with_speed_change=False)
    assert flat["time_s"] == pytest.approx(H / r, rel=1e-12)


def test_integrate_climb_with_a_linear_rate_is_the_trapezoid_of_one_over_rate():
    """Rate falling linearly with altitude: the exact time is (1/a) ln(r0/r1), Raymer (17.48); the stepwise sum
    with the mean rate of each step agrees to second order in the step."""
    r0, a, H = 30.0, 1.0e-3, 20000.0
    exact = np.log(r0 / (r0 - a * H)) / a
    coarse = p0.integrate_climb(lambda h, W: (r0 - a * h, 150.0, 0.0), 1.0, np.arange(0.0, H + 1.0, 1000.0).tolist())
    fine = p0.integrate_climb(lambda h, W: (r0 - a * h, 150.0, 0.0), 1.0, np.arange(0.0, H + 1.0, 500.0).tolist())
    assert coarse["time_s"] == pytest.approx(exact, rel=2e-3)
    assert abs(fine["time_s"] - exact) < 0.3 * abs(coarse["time_s"] - exact)


def test_climb_study_on_the_resized_design(resized):
    design, rec, _ = resized
    c = p0.climb_study(design)
    row = next(r for r in rec["mission"] if r["segment"] == "climb")
    assert c["stage1_two_point_fuel_lb"] == pytest.approx(row["burned_lb"], rel=1e-12)
    assert len(c["steps"]) == 20 and c["steps"][0]["h_from_ft"] == 0.0 and c["steps"][-1]["h_to_ft"] == 20000.0
    assert c["integrated"]["fuel_lb"] == pytest.approx(sum(s["fuel_lb"] for s in c["steps"]), rel=1e-12)
    assert c["mission_fuel_change_bound"] == pytest.approx(
        1.06 * abs(c["integrated"]["fuel_lb"] - row["burned_lb"]) / rec["fuel_lb"], rel=1e-12)
    assert c["finding_for_r1"] == (c["mission_fuel_change_bound"] > p0.TOL_MISSION_FUEL)
    prof = c["profile_at_takeoff_weight"]
    assert [r["h_ft"] for r in prof[:3]] == [0.0, 1000.0, 2000.0]
    assert prof[-1]["h_ft"] == rec["performance"]["service_ceiling_ft"]
    assert prof[-1]["rate_fpm"] == pytest.approx(100.0, abs=1e-3)
    rates = [r["rate_fpm"] for r in prof]
    assert rates == sorted(rates, reverse=True) and len(set(rates)) == len(rates)   # falls with altitude all the way


# ---- comparing records ------------------------------------------------------------------------------------------
def test_compare_fields_reports_differences_additions_removals_and_skips():
    old = {"a": 1.0, "b": {"c": [1.0, 2.0], "d": "x"}, "gone": 3, "skip": 5.0, "flag": True}
    new = {"a": 1.0 + 1e-12, "b": {"c": [1.0, 2.1], "d": "y"}, "new": 4, "skip": 6.0, "flag": True}
    c = p0.compare_fields(old, new, 1e-9, skip=("skip",))
    assert [d["path"] for d in c["different"]] == ["b.c.1", "b.d"]
    assert c["different"][0]["relative_difference"] == pytest.approx(0.1 / 2.1)
    assert [a["path"] for a in c["added"]] == ["new"] and [r["path"] for r in c["removed"]] == ["gone"]
    assert c["skipped"] == [{"path": "skip", "old": 5.0, "new": 6.0}]
    assert c["n_compared"] == 5                                  # a, b.c.0, b.c.1, b.d, flag
    assert p0.compare_fields({"a": [1, 2]}, {"a": [1, 2, 3]}, 1e-9)["different"][0]["path"] == "a"   # a list that grew
    assert p0.relative_difference(0.0, 0.0) == 0.0 and p0.relative_difference(1.0, -1.0) == 2.0


def test_table_reads_above_top_restores_the_method_even_after_an_error():
    original = TableEngine._full_throttle
    e = TableEngine(M250_TABLE)
    _, reads = p0.table_reads_above_top(lambda: (e.lapse(36000.0, 100.0), e.bsfc(20000.0, 100.0, 50.0),
                                                 e.turbine_choked(41000.0, 100.0, 50.0)))
    assert reads == [36000.0, 41000.0] and TableEngine._full_throttle is original
    with pytest.raises(ZeroDivisionError):
        p0.table_reads_above_top(lambda: 1 / 0)
    assert TableEngine._full_throttle is original


# ---- hygiene ----------------------------------------------------------------------------------------------------
def test_tree_state_lists_dirty_files_and_leaves_out_only_the_runs_own_folder():
    lines = ["?? runs/task12/pd/2026-11-27/p0/r0/info_gap.json", " M conceptual/uav.py", "",
             "?? runs/task12/pd/2026-11-27/p0x/a.json", 'R  old.py -> "runs/task12/pd/2026-11-27/p0/new.py"']
    assert record.dirty_files(lines, "runs/task12/pd/2026-11-27/p0") == [" M conceptual/uav.py",
                                                                         "?? runs/task12/pd/2026-11-27/p0x/a.json"]
    assert record.dirty_files(lines) == [ln for ln in lines if ln]
    s = record.tree_state("runs/task12/pd/2026-11-27/p0")
    assert set(s) == {"commit", "git_dirty", "git_dirty_files", "excluded"} and len(s["commit"]) == 40
    assert s["git_dirty"] == bool(s["git_dirty_files"]) and s["excluded"] == "runs/task12/pd/2026-11-27/p0"


def test_item_20_closed_form_climb_rows_of_an_app_l_record_carry_their_own_class():
    res = sp.compute(p0.GATE_B / "design_pusher.json")
    rows = {r["id"]: r for r in res["rows"]}
    for rid in ("roc_sl", "v_best_climb"):
        assert rows[rid]["class"] == sp.CLOSED_FORM_NA and rows[rid]["verdict"] == "not judged"
    assert rows["roc_sl_excess_power"]["class"] == sp.CODING and rows["roc_sl_excess_power"]["verdict"] == "within"
    assert sp.CLOSED_FORM_NA in sp.CLASSES and all(r["class"] in sp.CLASSES for r in res["rows"])


def test_item_22_both_propeller_fixed_points_raise_when_they_do_not_converge(monkeypatch):
    """stage3_perf._prop_eta_fixed_point raises since commit 9302606; conceptual ActuatorDisk always did."""
    from conceptual import raymer_propulsion as rp
    from measurement import mattingly as M
    flip = iter(range(10 ** 6))
    monkeypatch.setattr(M, "real_propeller_efficiency", lambda *a, **k: 0.5 + 0.1 * (next(flip) % 2))
    with pytest.raises(ValueError, match="did not converge"):
        sp._prop_eta_fixed_point(450.0, 100.0, 0.002377, 6.9)
    disk = rp.ActuatorDisk(0.002377, 6.9, 0.85)
    monkeypatch.setattr(disk, "efficiency_for_thrust", lambda T, V: 0.5 + 0.1 * (next(flip) % 2))
    with pytest.raises(ValueError, match="did not converge"):
        disk.efficiency_and_thrust(450.0, 100.0)

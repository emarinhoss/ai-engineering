"""Preliminary design package P0: the baseline record r0 (docs/specs/task12_preliminary_design.md, P0, PD-7).

    python -m prelim.p0_baseline --out runs/task12/pd/2026-11-27/p0
    python -m prelim.p0_baseline --out runs/task12/pd/2026-11-27/p0 --report-only \
        --report docs/validation/2026-11-27_task12_pd_p0.md

What it does, in order:
 1. refuses to start from a tree that differs from its commit (prelim/record.py);
 2. regenerates the M250 engine table (measurement/m250_engine.py, now to 35,000 ft, ruling B-9c) and
    compares it with the committed file and, cell by cell, with the table of the Gate B record;
 3. sizes W/S 13, A 8 again at the Gate B record's L_sized with the same ledger values (the same call as
    measurement/bands_cells.py) and compares every field with the Gate B design record;
 4. records the rate of climb against altitude in 1,000 ft steps and the climb leg integrated over those
    steps, next to Stage 1's two-point estimate (Gate B report item 23);
 5. runs the mode scans and the full info-gap study on r0 (seed 20261122) and compares the horizons.
Gate B records are read, never written. Nothing is tuned: each acceptance row of the spec is evaluated with
the tolerance the spec fixed, and a failed row is written down as failed.

Output: OUT/r0/ (the baseline record, same file names as the Gate B record so that the existing tools read
it), OUT/p0.json (checks and acceptance rows) and OUT/run.log.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from conceptual import raymer_performance as perf
from conceptual import sizing, uav
from conceptual.engine_model import TableEngine
from conceptual.units import KT, G, isa
from measurement import appk_validation, bands_cells, info_gap
from measurement import m250_engine as m250
from measurement import robust_sizing as rs
from measurement import stage3_perf as sp
from measurement import tp100_engine as tp
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
GATE_B = REPO / "runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8"
GATE_B_ENGINE = REPO / "runs/task12/stage3/2026-11-27/m250_ws13a8_measure/engine.json"
W_S, ASPECT = 13.0, 8.0
OLD_TOP_FT = 30000.0             # top of the engine table of the Gate B record
STEP_FT = 1000.0                 # altitude step of the climb profile and of the integrated climb (spec P0)
# tolerances of spec P0, "Acceptance, fixed now", rows 1 to 6
TOL_TABLE = 1e-12                # 1: table cells at or below 30,000 ft, relative
TOL_FIELDS = 1e-9                # 2: every field of the design record but the ceiling, relative
TOL_CEILING_FT = 1000.0          # 4: Stage 1 ceiling against the engine-cycle value (spec 7.1a)
TOL_MISSION_FUEL = 0.01          # 5: change of total mission fuel that makes the integrated climb a finding
TOL_HORIZON = 1e-4               # 6: info-gap horizons against Gate B, absolute
CEILING_FIELD = "performance.service_ceiling_ft"
EVIDENCE_CLASS = "coding check (same model, extended range)"
# keys of info_gap.json and cell_result.json that describe the run, not the aircraft
RUN_KEYS = ("inputs", "runtime_s", "record", "command", "source_curve_sha256")
TABLE_ARRAYS = ("full_throttle_shp", "bsfc", "lp_turbine_pressure_ratio")


# ---- comparing two records ---------------------------------------------------------------------------
def relative_difference(a, b):
    """|b - a| over the larger magnitude; 0 for two zeros."""
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0.0 else abs(b - a) / scale


def compare_fields(old, new, tol, skip=()):
    """Every field of two JSON records, by path ("performance.takeoff_ft", list items by index). Numbers are
    compared by relative_difference against tol, everything else by equality. Paths in `skip` (and all below
    them) are listed under "skipped" and not judged. Returns the differing, added, removed and skipped fields."""
    out = {"n_compared": 0, "max_relative_difference": 0.0, "different": [], "added": [], "removed": [], "skipped": []}

    def walk(a, b, path):
        if path in skip:
            out["skipped"].append({"path": path, "old": a, "new": b})
        elif isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                p = f"{path}.{k}" if path else k
                if k not in a:
                    out["added"].append({"path": p, "new": b[k]})
                elif k not in b:
                    out["removed"].append({"path": p, "old": a[k]})
                else:
                    walk(a[k], b[k], p)
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}.{i}")
        elif _is_number(a) and _is_number(b):
            rel = relative_difference(a, b)
            out["n_compared"] += 1
            out["max_relative_difference"] = max(out["max_relative_difference"], rel)
            if rel > tol:
                out["different"].append({"path": path, "old": a, "new": b, "relative_difference": rel})
        else:
            out["n_compared"] += 1
            if a != b:
                out["different"].append({"path": path, "old": a, "new": b, "relative_difference": None})
    walk(old, new, "")
    return out


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ---- the engine table -----------------------------------------------------------------------------------
def compare_tables(old, new, old_top=OLD_TOP_FT):
    """Acceptance row 1. old, new: table dicts (m250_table.json). Every altitude of the old table must be in
    the new one at the same index, with every cell equal to TOL_TABLE; the other keys must be equal. For each
    added altitude: the full-throttle power range over speed and how many of its cells (speed x power fraction)
    are choked (LP turbine pressure ratio at or above the critical ratio, as TableEngine.turbine_choked)."""
    n = len(old["h_ft"])
    kept = list(new["h_ft"][:n]) == list(old["h_ft"])
    arrays = {}
    for k in TABLE_ARRAYS:
        a, b = np.array(old[k]), np.array(new[k])[:n]
        arrays[k] = {"cells": int(a.size), "max_relative_difference": float(np.abs(b / a - 1.0).max()),
                     "bit_identical": bool((a == b).all())}
    other = {k: old[k] == new.get(k) for k in old if k not in TABLE_ARRAYS and k != "h_ft"}
    lp, crit = np.array(new["lp_turbine_pressure_ratio"]), new["critical_pressure_ratio"]
    p, s = np.array(new["full_throttle_shp"]), np.array(new["bsfc"])
    rows = []
    for i in range(n, len(new["h_ft"])):
        rows.append({"h_ft": new["h_ft"][i], "full_throttle_shp_min": float(p[i].min()),
                     "full_throttle_shp_max": float(p[i].max()), "cells": int(lp[i].size),
                     "choked_cells": int((lp[i] >= crit).sum()), "all_finite": bool(np.isfinite(lp[i]).all()
                                                                                     and np.isfinite(s[i]).all()),
                     "power_below_row_beneath_at_every_speed": bool((p[i] < p[i - 1]).all())})
    ok = (kept and all(a["max_relative_difference"] <= TOL_TABLE for a in arrays.values()) and all(other.values())
          and bool(rows) and all(r["all_finite"] for r in rows))
    return {"old_altitudes_ft": old["h_ft"], "new_altitudes_ft": new["h_ft"], "old_top_ft": old_top,
            "new_top_ft": max(new["h_ft"]), "every_old_altitude_kept": kept, "arrays_at_or_below_old_top": arrays,
            "other_keys_equal": other, "new_rows": rows, "tolerance": TOL_TABLE, "passed": ok}


def extension_facts(member, table_path, speed_kt=m250.LAPSE_V_KT):
    """What can be said about the rows above 30,000 ft, which no printed value covers (Mattingly's Fig. K.7
    ends at 30,000 ft and the brochure has no altitude data). At speed_kt:
    - the cycle's full-throttle state at the four top altitudes (which control limit acts: pi_c at its ceiling
      or below it), from m250_engine.altitude_lapse;
    - the error of the table's linear interpolation half way between its rows, against the cycle itself: between
      the two new rows, across the old top, and between two old rows for comparison."""
    engine = TableEngine(table_path)
    state = []
    for h in (27500.0, 30000.0, 32500.0, 35000.0):
        r = m250.altitude_lapse(member, h, speed_kt)["pi_c_ceiling"]
        state.append({"h_ft": h, "shp": r["shp"], "lapse": r["lapse"], "pi_c": r["pi_c"],
                      "pi_c_over_rated": r["pi_c"] / member["ref"]["pi_c"], "mgt_c": r["mgt_c"]})
    midpoints = []
    for h in (28750.0, 31250.0, 33750.0):     # the first is between two rows of the old table, for comparison
        cycle, table = tp.power_available(member, h, speed_kt), engine.power_available(h, speed_kt)
        midpoints.append({"h_ft": h, "cycle_shp": cycle, "table_shp": table, "table_over_cycle": table / cycle})
    return {"speed_kt": speed_kt, "full_throttle_state": state, "interpolation_at_midpoints": midpoints}


def book_validation():
    """The App. K example against Mattingly's figure readings (measurement/appk_validation.py, burner msh), run
    again at this commit. The lapse rows (Fig. K.7) are the ones that bear on the altitude grid."""
    rows = appk_validation.run("msh")
    lapse = [r for r in rows if r["group"] == "lapse"]
    return {"burner": "msh", "n_rows": len(rows), "n_pass": sum(r["verdict"] == "PASS" for r in rows),
            "failed": [r for r in rows if r["verdict"] != "PASS"], "lapse_rows": lapse,
            "lapse_highest_altitude_case": lapse[-1]["case"]}


# ---- which altitudes the table is read at ----------------------------------------------------------------------
def table_reads_above_top(run):
    """run() with every engine-table lookup watched. Returns (what run returned, the sorted altitudes above the
    table's top altitude that were looked up). Every lookup of TableEngine (power_available, lapse, bsfc,
    turbine_choked) goes through _full_throttle, so that one method is wrapped for the duration of run."""
    seen = set()
    original = TableEngine._full_throttle

    def watched(self, h_ft, V_kt):
        if h_ft > self.h[-1]:
            seen.add(float(h_ft))
        return original(self, h_ft, V_kt)
    TableEngine._full_throttle = watched
    try:
        result = run()
    finally:
        TableEngine._full_throttle = original
    return result, sorted(seen)


# ---- climb -------------------------------------------------------------------------------------------------
def integrate_climb(point, W_start, altitudes, V_end=None, with_speed_change=True):
    """Climb at full throttle through the altitudes (ft, rising), step by step.

    point(h, W) -> (best rate of climb ft/s, its speed ft/s, fuel flow lb/s) at altitude h and weight W.
    Per step, with the weight at the start of the step used at both of its ends:
      energy height gained  dhe = dh + (V_b^2 - V_a^2)/(2 g)        Raymer (19.9), p. 523
      time                  dt  = dhe / mean rate of the two ends   Raymer (17.88), (17.90), p. 479-482
      fuel                  dW  = mean fuel flow x dt                Raymer (17.45), p. 466
    The best rate of climb is the specific excess power at that speed ((17.86), p. 476), so dt = dhe/P_s is
    (17.44), dt = dh/V_v, when the speed does not change. V_end replaces the speed at the last altitude (the
    cruise speed at the top of the climb, as in Stage 1's energy-height change). with_speed_change False
    drops the speed term (dhe = dh).
    Returns {"time_s", "fuel_lb", "distance_ft", "W_end", "steps": [...]}."""
    W, t, dist, steps = W_start, 0.0, 0.0, []
    for i, (h_a, h_b) in enumerate(zip(altitudes[:-1], altitudes[1:])):      # noqa: RUF007 (plain pairs)
        r_a, V_a, f_a = point(h_a, W)
        r_b, V_b, f_b = point(h_b, W)
        if V_end is not None and i == len(altitudes) - 2:
            V_b = V_end
        dhe = (h_b - h_a) + ((V_b ** 2 - V_a ** 2) / (2.0 * G) if with_speed_change else 0.0)
        dt = dhe / (0.5 * (r_a + r_b))
        fuel = 0.5 * (f_a + f_b) * dt
        steps.append({"h_from_ft": h_a, "h_to_ft": h_b, "W_lb": W, "rate_from_fpm": 60.0 * r_a, "rate_to_fpm": 60.0 * r_b,
                      "V_from_kt": V_a / KT, "V_to_kt": V_b / KT, "energy_height_ft": dhe, "time_s": dt, "fuel_lb": fuel})
        W, t, dist = W - fuel, t + dt, dist + 0.5 * (V_a + V_b) * dt
    return {"time_s": t, "fuel_lb": W_start - W, "distance_ft": dist, "W_end": W, "steps": steps}


def climb_point_fn(b, L, S):
    """point(h, W) for integrate_climb from the rebuilt Stage 1 state b: the best rate of climb and its speed by
    uav.climb_rate_at (the function the service ceiling bisects on) at weight W, and the full-throttle fuel flow
    c P / 3600 with power and SFC both read from the engine table at the climb-speed floor, the speed at which
    uav.ceiling takes the power."""
    model = b["engine_model"]

    def point(h, W):
        d = dict(b, W0=W, W_S=W / S)
        power_at = uav.climb_power_default(d, L)
        rate, V = uav.climb_rate_at(d, L, h, power_at)
        V_floor = L["climb_speed_over_stall"] * perf.stall_speed(W / S, isa(h)["rho"], b["clmax"]["clean"])
        shp = power_at(h)
        return rate, V, model.bsfc(h, V_floor / KT, shp) * shp / 3600.0
    return point


def climb_profile(b, L, d, ceiling_ft, step=STEP_FT):
    """Rate of climb at take-off weight against altitude: every `step` ft from sea level up to the ceiling,
    and at the ceiling itself (where it is the ceiling_rate_fpm of the ledger by construction)."""
    bd = dict(b, W0=d["W0_lb"], W_S=d["W_S"])
    power_at = uav.climb_power_default(bd, L)
    rows = []
    for h in [*np.arange(0.0, ceiling_ft, step).tolist(), ceiling_ft]:
        rate, V = uav.climb_rate_at(bd, L, h, power_at)
        rows.append({"h_ft": h, "rate_fpm": 60.0 * rate, "V_kt": V / KT, "shaft_hp_available": power_at(h)})
    return rows


def climb_study(design_path):
    """Item 23: the climb leg of the record's mission (sea level to the mission altitude, from the weight after
    take-off) integrated in STEP_FT steps, next to Stage 1's two-point estimate (the record's `climb` row), and the
    rate of climb against altitude at take-off weight. The effect on the total mission fuel is bounded, not
    re-flown: the later legs start lighter by what the climb burns more, so the total changes by less than
    RESERVE_FACTOR x the difference in climb fuel."""
    d, L, b, _, _ = sp.rebuild(design_path)
    S = d["wing"]["area"]
    row = next(r for r in d["mission"] if r["segment"] == "climb")
    h_top = L["mission_altitude_ft"]
    altitudes = np.arange(0.0, h_top + 0.5 * STEP_FT, STEP_FT).tolist()
    alt = isa(h_top)
    V_cruise = uav._cruise_speed(row["W_start"], S, alt["rho"], b["CD0_alt"], b["K"], b["clmax"]["clean"], L, "range")[0]
    point = climb_point_fn(b, L, S)
    energy = integrate_climb(point, row["W_start"], altitudes, V_end=V_cruise)
    height = integrate_climb(point, row["W_start"], altitudes, with_speed_change=False)
    two_point = row["W_start"] - row["W_end"]
    bound = sizing.RESERVE_FACTOR * abs(energy["fuel_lb"] - two_point) / d["fuel_lb"]
    return {"mission_altitude_ft": h_top, "step_ft": STEP_FT, "W_start_lb": row["W_start"],
            "V_cruise_top_of_climb_kt": V_cruise / KT, "stage1_two_point_fuel_lb": two_point,
            "integrated": {k: energy[k] for k in ("time_s", "fuel_lb", "distance_ft", "W_end")},
            "integrated_height_only": {k: height[k] for k in ("time_s", "fuel_lb", "distance_ft", "W_end")},
            "steps": energy["steps"], "fuel_difference_lb": energy["fuel_lb"] - two_point,
            "fuel_difference_relative": energy["fuel_lb"] / two_point - 1.0, "mission_fuel_lb": d["fuel_lb"],
            "reserve_factor": sizing.RESERVE_FACTOR, "mission_fuel_change_bound": bound, "tolerance": TOL_MISSION_FUEL,
            "finding_for_r1": bound > TOL_MISSION_FUEL,
            "profile_at_takeoff_weight": climb_profile(b, L, d, d["performance"]["service_ceiling_ft"])}


# ---- the service ceiling ---------------------------------------------------------------------------------
def ceiling_study(design_path, member, gate_b_engine=GATE_B_ENGINE):
    """Acceptance rows 3 and 4. The record's Stage 1 ceiling (now on the table to 35,000 ft) against the
    engine-cycle value of the Gate B engine record (the App. K family in Stage 1's own bisection, min to max),
    and against the same bisection run here with the cycle of the table's own member, which leaves only the
    table's interpolation as the difference. Also the bisection with the power set to zero above the table top:
    uav.ceiling probes 45,000 and 37,500 ft on its way down, and the result must not depend on those reads."""
    d, L, b, _, _ = sp.rebuild(design_path)
    bd = dict(b, W0=d["W0_lb"], W_S=d["W_S"])
    per = d["performance"]
    top = per["engine_table_top_ft"]
    default = uav.climb_power_default(bd, L)
    no_power_above_top = uav.ceiling(bd, L, power_at=lambda h: default(h) if h <= top else 0.0)

    def cycle_power(h):                      # the member's own cycle at the speed uav.ceiling takes the power
        a = isa(h)
        V = L["climb_speed_over_stall"] * perf.stall_speed(d["W_S"], a["rho"], b["clmax"]["clean"])
        return tp.power_available(member, h, V / KT)
    cycle_nominal = uav.ceiling(bd, L, power_at=cycle_power)
    band = next(r for r in json.loads(Path(gate_b_engine).read_text())["rows"] if r["id"] == "ceiling")["stage3"]
    need = L["ceiling_ft"] + L.get("margin_ceiling_ft", 0.0)
    dev = [per["service_ceiling_ft"] - band["min"], per["service_ceiling_ft"] - band["max"]]
    return {"stage1_ft": per["service_ceiling_ft"], "above_table_top": per["service_ceiling_above_table_top"],
            "table_top_ft": top, "ceiling_with_no_power_above_table_top_ft": no_power_above_top,
            "independent_of_reads_above_top": no_power_above_top == per["service_ceiling_ft"],
            "gate_b_engine_record": str(Path(gate_b_engine).relative_to(REPO)),
            "engine_cycle_family_ft": {"min": band["min"], "max": band["max"]}, "deviation_ft": dev,
            "tolerance_ft": TOL_CEILING_FT, "within": all(abs(x) <= TOL_CEILING_FT for x in dev),
            "engine_cycle_nominal_member_ft": cycle_nominal,
            "table_minus_nominal_cycle_ft": per["service_ceiling_ft"] - cycle_nominal,
            "r12_required_ft": need, "r12_margin_stage1_ft": per["service_ceiling_ft"] - need,
            "r12_margin_engine_cycle_min_ft": band["min"] - need,
            "r12_met_by_both": per["service_ceiling_ft"] >= need and band["min"] >= need}


# ---- the run -------------------------------------------------------------------------------------------------
def ledger_values_equal(path_a, path_b, ignore=("loiter_h",)):
    """Whether two ledger files carry the same values and bands (labels and source text may differ)."""
    def values(path):
        L, entries = uav.load_ledger(path)
        bands = {v["name"]: [v["band_lo"], v["band_hi"]] for v in info_gap.uncertain_variables(entries)}
        return {k: v for k, v in L.items() if k not in ignore}, bands
    a, b = values(path_a), values(path_b)
    return {"values_equal": a[0] == b[0], "bands_equal": a[1] == b[1], "n_values": len(a[0]), "n_bands": len(a[1]),
            "ignored": list(ignore)}


def acceptance_rows(res):
    """The six rows of spec P0, each with its numbers and a verdict: pass, fail or (row 5) finding."""
    t, f, c, cl = res["table"], res["design_fields"], res["ceiling"], res["climb"]
    rows = [
        {"row": 1, "what": "table cells at or below 30,000 ft equal the Gate B record's table; new rows carry the choked flag",
         "value": max(a["max_relative_difference"] for a in t["arrays_at_or_below_old_top"].values()),
         "tolerance": TOL_TABLE, "verdict": "pass" if t["passed"] and res["table_regenerated"]["equals_committed"] else "fail"},
        {"row": 2, "what": f"every field of r0's design record other than {CEILING_FIELD} equals the Gate B record",
         "value": f["max_relative_difference"], "tolerance": TOL_FIELDS, "n_compared": f["n_compared"],
         "n_different": len(f["different"]), "n_added": len(f["added"]), "n_removed": len(f["removed"]),
         "verdict": "pass" if not f["different"] and not f["removed"] else "fail"},
        {"row": 3, "what": "no ceiling above the table top: the B-9c flag is stored and false",
         "value": c["above_table_top"], "reads_above_top": res["table_reads_above_top"],
         "verdict": "pass" if c["above_table_top"] is False and c["independent_of_reads_above_top"] else "fail"},
        {"row": 4, "what": "service ceiling: Stage 1 on the extended table against the engine-cycle value; R12 under both",
         "value": c["stage1_ft"], "reference": c["engine_cycle_family_ft"], "deviation": c["deviation_ft"],
         "tolerance": TOL_CEILING_FT, "verdict": "pass" if c["within"] and c["r12_met_by_both"] else "fail"},
        {"row": 5, "what": "integrated climb fuel against the two-point estimate: change of total mission fuel",
         "value": cl["mission_fuel_change_bound"], "tolerance": TOL_MISSION_FUEL,
         "verdict": "finding for r1" if cl["finding_for_r1"] else "pass (no finding)"}]
    if "info_gap" in res:
        g = res["info_gap"]["horizons"]
        rows.append({"row": 6, "what": "info-gap horizons of r0 (seed 20261122) against Gate B: R5 guarantee and R7",
                     "value": {k: g[k]["r0"] for k in ("R5_guarantee", "R7")},
                     "reference": {k: g[k]["gate_b"] for k in ("R5_guarantee", "R7")},
                     "deviation": {k: g[k]["difference"] for k in ("R5_guarantee", "R7")}, "tolerance": TOL_HORIZON,
                     "verdict": "pass" if all(abs(g[k]["difference"]) <= TOL_HORIZON for k in ("R5_guarantee", "R7")) else "fail"})
    return rows


def run(out, processes, log):
    """The whole package; returns the result dict (also written to OUT/p0.json)."""
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P0 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    rs.use_engine_as_is(True)
    r0 = out / "r0"
    r0.mkdir(parents=True, exist_ok=True)
    inputs = dict(rs.inputs_block("preliminary design P0, baseline record r0"), **tree)
    res = {"inputs": dict(inputs, command="python -m prelim.p0_baseline " + " ".join(sys.argv[1:]), processes=processes),
           "gate_b_record": str(GATE_B.relative_to(REPO)), "evidence_class": EVIDENCE_CLASS}
    log(f"commit {tree['commit']}, clean tree; engine table {inputs['table_sha256']}")

    # 1. the table: made again by the committed code, compared with the committed file and with Gate B's
    study = m250.study("450")
    member = next(m for m in study["_members"] if (m["e_c"], m["e_t"]) == (m250.NOMINAL["e_c"], m250.NOMINAL["e_t"]))
    regenerated = json.dumps(m250.table(member), indent=1)
    res["table_regenerated"] = {"equals_committed": regenerated == rs.engine_table().read_text(),
                                "committed": str(rs.engine_table().relative_to(REPO)), "sha256": inputs["table_sha256"]}
    res["table"] = compare_tables(json.loads((GATE_B / "m250_table.json").read_text()), json.loads(regenerated))
    res["table"]["unchoked_cells"] = m250.unchoked_cells(json.loads(regenerated))
    res["table"]["unchoked_cells_gate_b"] = m250.unchoked_cells(json.loads((GATE_B / "m250_table.json").read_text()))
    res["table_extension"] = extension_facts(member, rs.engine_table())
    res["book_validation"] = book_validation()
    res["brochure_validation"] = {"n_members": len(study["members"]),
                                  "n_pass": sum(m["validation"]["passed"] for m in study["members"]),
                                  "range": "sea level, 70 to 100 % power (measurement/m250_engine.py)"}
    log(f"table regenerated: equals the committed file {res['table_regenerated']['equals_committed']}; "
        f"cells at or below 30,000 ft against Gate B: {'pass' if res['table']['passed'] else 'FAIL'}")

    # 2. the design, sized again at the recorded L_sized, with every table lookup watched
    row = bands_cells.source_row(W_S, ASPECT)
    rec, reads = table_reads_above_top(lambda: bands_cells.size_cell(row))
    design = rs.write_record_rec(row, r0, rec)
    rec = json.loads(design.read_text())
    old = json.loads((GATE_B / "design_pusher.json").read_text())
    res["design_fields"] = compare_fields(old, rec, TOL_FIELDS, skip=(CEILING_FIELD,))
    res["ledger"] = ledger_values_equal(GATE_B / "ledger.yaml", r0 / "ledger.yaml", ignore=())
    res["power_margin"] = {"r0": 1.0 - max(rec["power_required_hp"].values()) / rec["bhp_sl"],
                           "gate_b_row": json.loads((GATE_B / "robust_candidate.json").read_text())["power_margin"]}
    res["unchoked_fuel_share"] = {"r0": rec["unchoked_fuel_share"], "gate_b": old["unchoked_fuel_share"]}
    res["table_reads_above_top"] = {"stage1_sizing_and_performance_ft": reads}
    log(f"r0 sized: W0 {rec['W0_lb']:.3f} lb, fuel {rec['fuel_lb']:.3f} lb, ceiling {rec['performance']['service_ceiling_ft']:.1f} ft; "
        f"{len(res['design_fields']['different'])} fields differ from Gate B beyond {TOL_FIELDS:g} (ceiling apart)")

    # 3. ceiling and climb
    res["ceiling"] = ceiling_study(design, member)
    res["climb"] = climb_study(design)
    log(f"ceiling {res['ceiling']['stage1_ft']:.1f} ft against the engine cycle {res['ceiling']['engine_cycle_family_ft']['min']:.1f} to "
        f"{res['ceiling']['engine_cycle_family_ft']['max']:.1f} ft; integrated climb {res['climb']['integrated']['fuel_lb']:.2f} lb "
        f"against {res['climb']['stage1_two_point_fuel_lb']:.2f} lb")

    res["acceptance"] = acceptance_rows(res)
    if res["acceptance"][1]["verdict"] != "pass":
        # spec P0 row 2: a field that differs stops the package and is reported
        res["stopped"] = "acceptance row 2 failed: a field of r0 differs from the Gate B record; no info-gap study was run"
        _write(out, res, t0, own)
        raise SystemExit(res["stopped"])

    # 4. robustness of r0: the mode scans and the full study, as measurement/bands_cells.run_cell
    need = uav.load_ledger()[0]["r5_robust_hours"]
    (modes, worst), reads = table_reads_above_top(
        lambda: (rs.mode_study(design, need)[0], rs.mode_worst_at(design, need, bands_cells.H_T)))
    res["table_reads_above_top"]["mode_scans_ft"] = reads
    log(f"mode scans: endurance {modes['endurance']['h_hat']:.4f}, cliff {modes['cliff']['h_hat']:.4f}")
    ig = info_gap.study(str(design), processes=processes)
    ig["inputs"] = dict(inputs, note="full info_gap.study of the preliminary-design baseline r0")
    (r0 / "info_gap.json").write_text(json.dumps(info_gap._json_safe(ig), indent=1, default=float))
    cell = {"inputs": dict(inputs, note="r0: W/S 13, A 8 sized again at the recorded L_sized"),
            "source": str(bands_cells.SOURCE.relative_to(REPO)), "source_curve_sha256": rs.sha256(bands_cells.SOURCE / "curve.json"),
            "h_T": bands_cells.H_T, "need_h": need, "design": rs.summary_of(row), "modes": modes, "worst_at_target": worst,
            "command": res["inputs"]["command"], "runtime_s": time.time() - t0}
    (r0 / "cell_result.json").write_text(json.dumps(info_gap._json_safe(cell), indent=1, default=float))
    res["info_gap"] = compare_info_gap(r0)
    res["acceptance"] = acceptance_rows(res)
    _write(out, res, t0, own)
    hh = res["info_gap"]["horizons"]
    log(f"info-gap: R5 guarantee {hh['R5_guarantee']['r0']:.4f}, R7 {hh['R7']['r0']:.4f}; "
        + ", ".join(f"row {a['row']} {a['verdict']}" for a in res["acceptance"]) + f" ({time.time() - t0:.0f} s)")
    return res


def compare_info_gap(r0, gate_b=GATE_B):
    """Acceptance row 6 and more: the horizons of r0 against the Gate B record, and a field-by-field comparison of
    info_gap.json and cell_result.json (the keys that describe the run, RUN_KEYS, are skipped)."""
    new_ig, old_ig = (json.loads((p / "info_gap.json").read_text()) for p in (r0, gate_b))
    new_c, old_c = (json.loads((p / "cell_result.json").read_text()) for p in (r0, gate_b))
    horizons = {k: {"r0": new_ig["h_hat"][k]["h_hat"], "gate_b": old_ig["h_hat"][k]["h_hat"],
                    "difference": new_ig["h_hat"][k]["h_hat"] - old_ig["h_hat"][k]["h_hat"]} for k in old_ig["h_hat"]}
    for k in ("endurance", "cliff"):
        horizons["mode_" + k] = {"r0": new_c["modes"][k]["h_hat"], "gate_b": old_c["modes"][k]["h_hat"],
                                 "difference": new_c["modes"][k]["h_hat"] - old_c["modes"][k]["h_hat"]}
    files = {}
    for name, a, b in (("info_gap.json", old_ig, new_ig), ("cell_result.json", old_c, new_c)):
        cmp_ = compare_fields(a, b, TOL_FIELDS, skip=RUN_KEYS)
        files[name] = {k: cmp_[k] for k in ("n_compared", "max_relative_difference", "different", "added", "removed")}
        files[name]["skipped"] = [s["path"] for s in cmp_["skipped"]]
    return {"seed": new_ig["inputs"]["seed"], "n_samples": new_ig["inputs"]["n_samples"], "horizons": horizons,
            "nominal": {"r0": new_ig["nominal"], "gate_b": old_ig["nominal"]}, "tolerance": TOL_HORIZON, "files": files,
            "runtime_s": new_ig["runtime_s"]}


def _write(out, res, t0, own):
    """OUT/p0.json, with the state of the tree at the end of the run next to the one at its start."""
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == res["inputs"]["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p0.json").write_text(json.dumps(info_gap._json_safe(res), indent=1, default=float))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--processes", type=int, default=2, help="processes of info_gap.study (Gate B used 2)")
    ap.add_argument("--report")
    ap.add_argument("--report-only", action="store_true", help="write the report from OUT/p0.json and OUT/r0")
    a = ap.parse_args(argv)
    out = (REPO / a.out).resolve()
    if not a.report_only:
        t0 = time.time()
        lines = []

        def log(msg):
            lines.append(f"[{time.time() - t0:7.0f} s] {msg}")
            print(lines[-1], flush=True)
            if out.exists():
                (out / "run.log").write_text("\n".join(lines) + "\n")
        run(out, a.processes, log)
    if a.report:
        from prelim.p0_report import report_text
        Path(a.report).write_text(report_text(out))


if __name__ == "__main__":
    main()

"""Preliminary design P9: the summary record and the report (spec P9; rulings PD-22, PD-25; decisions PD-26, PD-27).

Not yet Fable-reviewed (rulings PD-22 and PD-25).

    python -m prelim.p9_report summary --out runs/task12/pd/2026-11-28/p9/summary
    python -m prelim.p9_report report --out runs/task12/pd/2026-11-28/p9/summary --report docs/validation/2026-11-28_task12_pd_p9.md

`summary` reads the P9 records (pass 0, pass 1 and, if r1 has no design, the diagnosis), computes what the acceptance
rows need that the records do not hold yet (each finding alone on r0 as built; the labelled sensitivities of CD0 and of
the faired-peak C_L,max on the climb at the failing corner; P4's route on the lightest design), judges the four
acceptance rows by the spec's rules and writes summary.json. `report` writes the report from summary.json and the
records it names; every number in it is read from them.
"""
import argparse
import copy
import json
import math
import sys
import time
from pathlib import Path

import yaml

from conceptual import uav
from measurement import info_gap
from measurement import robust_sizing as rs
from prelim import p9_r1 as p9
from prelim import p9_study as st

REPO = p9.REPO
P9 = REPO / "runs/task12/pd/2026-11-28/p9"
PASS0, PASS1, DIAG = P9 / "pass0/inputs.json", P9 / "pass1/pass.json", P9 / "diagnose/diagnose.json"
R0_INFO, R0_CELL = p9.R0 / "info_gap.json", p9.R0 / "cell_result.json"
REL = 1e-6                                   # a field "changes" with a finding group if it moves by more than this


def rel(path):
    return str(Path(path).relative_to(REPO))


# ---- sensitivities on the climb at the failing corner --------------------------------------------------------------
def member_with_nominal(moved, h, ledger, nominal, overrides):
    """A member of U(h) along a corner's directions with the nominal of banded entries moved (the bands stay):
    each moved variable at its harmful end of U(h) about the new nominal (DMDU (10.7) as info_gap.bounds)."""
    _, entries = uav.load_ledger(ledger)
    base = {v["name"]: v["nominal"] for v in info_gap.uncertain_variables(entries)}
    entries = copy.deepcopy(entries)
    for k, v in nominal.items():
        entries[k]["value"] = v
    variables = info_gap.uncertain_variables(entries)
    dirs = {n: (0 if moved.get(n, base[n]) == base[n] else 1 if moved[n] > base[n] else -1) for n in base}
    return dict(overrides, **info_gap.corner_theta(variables, h, dirs))


def climb_limit(built, moved, ledger, nominal, overrides, h_hi=1.5, tol=1e-3):
    ok = lambda h: st.climb_at(built, member_with_nominal(moved, h, ledger, nominal, overrides))["rate_at_mission_altitude_fpm"] > 0.0
    if ok(h_hi):
        return h_hi
    lo, hi = 0.0, h_hi
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def sensitivities(diag, pass0, log):
    """Labelled sensitivities, not bands, on the climb at the corner that fails (the largest h along its directions at
    which the aircraft still climbs to 20,000 ft) and on the nominal hours: CD0 +-10 % (P1's route, leakage_fraction),
    the faired-peak section C_L,max 1.43 (P2), and the sponson placed 0.4 of its length ahead of the main wheel
    (PD-27 keeps P3's 0.3), on r0 as built with every finding and on the lightest design."""
    corner = next(c for c in diag["cliff_corners"] if c["label"] == diag["attribution_corner"])
    L1 = uav.load_ledger(p9.LEDGER_R1)[0]
    ent = st.r1_entries(L1)
    b0 = info_gap.Built(p9.R0 / "design_pusher.json")
    b8 = info_gap.Built(REPO / diag["lightest_8h"]["record"])
    leak = L1["leakage_fraction"]
    k04 = pass0["detail"]["sponson_position_sensitivity"]["0.4"]
    cases = {"as recorded": ({}, {}),
             "CD0 +10 %": ({}, {"leakage_fraction": (1 + p9.CD0_STEP) * (1 + leak) - 1}),
             "CD0 -10 %": ({}, {"leakage_fraction": (1 - p9.CD0_STEP) * (1 + leak) - 1}),
             "section C_L,max 1.43 (faired peak)": ({"airfoil_cl_max": p9.FAIRED_SECTION_CL_MAX}, {}),
             "sponson centre 0.4 of its length ahead of the wheel": ({}, {"sponson_size_factor": k04})}
    out = {"corner": corner["label"], "cases": {}}
    for name, (nominal, extra) in cases.items():
        row = {}
        for tag, built, ov in (("r0_with_every_finding", b0, dict(ent, **extra)), ("lightest_8h", b8, extra)):
            if tag == "lightest_8h" and "sponson_size_factor" in extra:
                row[tag] = None                   # the lightest design's weights were sized with PD-27's sponson
                continue
            th0 = dict(ov, **nominal)
            row[tag] = {"climb_limit_h": climb_limit(built, corner["moved"], p9.LEDGER_R1, nominal, ov),
                        "nominal_hours": built.hours_detail(th0)[0], "W0_lb": built.w0_for(th0)}
        out["cases"][name] = dict(row, nominal=nominal, held=extra)
        log(f"sensitivity {name}: climb limit h r0+findings {row['r0_with_every_finding']['climb_limit_h']:.3f}"
            + (f", lightest {row['lightest_8h']['climb_limit_h']:.3f}" if row["lightest_8h"] else ""))
    return out


# ---- the r1-minus-r0 table ---------------------------------------------------------------------------------------
FIELDS = (("W0_lb", "take-off weight W0", "lb"), ("We_lb", "empty weight", "lb"),
          ("fuel_needed_at_record_loiter_lb", "mission fuel at the record's sized loiter", "lb"),
          ("hours_on_station", "hours on station on the record's fuel", "h"), ("takeoff_ft", "take-off over 50 ft", "ft"),
          ("landing_ft", "landing over 50 ft", "ft"), ("V_stall_clean_kt", "clean stall speed, sea level", "kt"),
          ("service_ceiling_ft", "service ceiling", "ft"), ("power_margin", "power margin", "-"),
          ("gear_length_in", "main gear length", "in"), ("n_limit", "limit load factor used", "-"),
          ("CD0.mission_altitude", "CD0 at 20,000 ft", "-"), ("CD0.sea_level", "CD0 at sea level", "-"),
          ("CL_max.clean", "wing C_L,max clean", "-"), ("CL_max.takeoff", "wing C_L,max take-off", "-"),
          ("CL_max.landing", "wing C_L,max landing", "-"), ("layout.x_le", "wing leading edge (Stage 1's layout)", "ft"),
          ("layout.x_main", "main wheels (Stage 1's layout)", "ft"), ("layout.sm_full", "static margin, full fuel (Stage 1's layout)", "MAC"),
          ("layout.sm_empty", "static margin, empty fuel (Stage 1's layout)", "MAC"),
          ("layout.prop_clearance_in", "propeller clearance at rotation", "in"),
          ("rotation_tail_cl", "tail lift coefficient at rotation", "-"))
COMPONENTS = ("wing", "horizontal_tail", "vertical_tail", "fuselage", "main_gear", "nose_gear", "installed_engine", "sponsons",
              "fuel_system", "flight_controls", "hydraulics", "avionics", "electrical")


def one_at_a_time(log):
    """Each finding group alone on r0 as built (PD-26 item 8): the values of p9_study.built_values."""
    L1 = uav.load_ledger(p9.LEDGER_R1)[0]
    ent = st.r1_entries(L1)
    b0 = info_gap.Built(p9.R0 / "design_pusher.json")
    out = {}
    for name, keys in st.GROUPS.items():
        out[name] = st.built_values(b0, {k: ent[k] for k in keys})
        log(f"{name}: W0 {out[name]['W0_lb']:.1f} lb, hours {out[name]['hours_on_station']:.3f} h")
    return out


def table(diag, oat):
    """Field by field: r0 as built (its record rebuilt), r0 as built with every finding, the lightest W/S 13, A 8 design
    with r1's ledger (Stage 1 at 8 h; the re-size found no design). The cause of a change at r0's sizes is every
    finding group that alone moves the field by more than REL; the lightest design adds the re-size to 8 h."""
    base, allf, light = diag["r0_built"], diag["r0_built_with_findings"], diag["lightest_8h"]["nominal"]
    rows = []
    fields = list(FIELDS) + [(f"components_lb.{k}", f"weight: {k.replace('_', ' ')}", "lb") for k in COMPONENTS]
    for key, label, unit in fields:
        v0, v1, v8 = p9.pick(base, key), p9.pick(allf, key), p9.pick(light, key)
        causes = [g for g, o in oat.items() if abs(p9.pick(o, key) - v0) > REL * max(1.0, abs(v0))]
        rows.append({"field": key, "label": label, "unit": unit, "r0": v0, "r0_with_findings": v1, "lightest_8h": v8,
                     "findings_change": v1 - v0, "resize_change": v8 - v1, "caused_by": causes})
    return rows


# ---- acceptance ---------------------------------------------------------------------------------------------------
def acceptance(pass1, diag, tbl):
    has_r1 = pass1["sizing"]["design"] is not None
    ig = diag["info_gap_lightest_8h"]["h_hat"] if diag else None
    rows = []
    if has_r1:
        raise NotImplementedError("r1 exists: the acceptance rows are judged on its robustness and re-run records")
    trace = pass1["sizing"]["iterations"][0]["candidates"][0]
    rows.append({"row": 1, "what": "R5 guarantee horizon and R7 horizon each at least 1 on r1 (spec 7.4)",
                 "verdict": "fail",
                 "value": {"r1": "no design: " + trace["status"], "lightest_8h_R5_guarantee": ig["R5_guarantee"],
                           "lightest_8h_R7": ig["R7"],
                           "climb_limit_h_lightest_8h": min(r["climb_limit_h"] for r in diag["corners"]["lightest_8h"] if "climb_limit_h" in r),
                           "climb_limit_h_r0_with_findings": min(r["climb_limit_h"] for r in diag["corners"]["r0_with_every_finding"] if "climb_limit_h" in r)},
                 "threshold": 1.0})
    failed8 = diag["lightest_8h"]["failed"]
    rows.append({"row": 2, "what": "no compliance row fails", "verdict": "not judged (no r1)",
                 "value": {"lightest_8h_stage1_rows_failed": failed8, "lightest_8h_stage1_rows": len(diag["lightest_8h"]["compliance"])}})
    rows.append({"row": 3, "what": "r1 minus r0 field by field with the finding that caused each change",
                 "verdict": "tabulated without r1", "value": {"fields": len(tbl)}})
    rows.append({"row": 4, "what": "step doubling changes W0 by less than 0.5 %", "verdict": "not run (no r1)", "value": None,
                 "threshold": p9.TOL_STEP_W0})
    return rows


def cmd_summary(out, log):
    t0 = time.time()
    own, inputs = p9.start(out, "summary")
    rs.use_engine_as_is(True)
    pass0, pass1 = p9.load(PASS0), p9.load(PASS1)
    diag = p9.load(DIAG) if DIAG.exists() else None
    res = {"inputs": dict(inputs, records={k: rel(v) for k, v in (("pass0", PASS0), ("pass1", PASS1), ("diagnose", DIAG))
                                            if Path(v).exists()}), "review": p9.REVIEW}
    log("each finding group alone on r0 as built")
    res["one_at_a_time"] = one_at_a_time(log)
    res["table"] = table(diag, res["one_at_a_time"])
    log("labelled sensitivities on the climb at the failing corner")
    res["sensitivities"] = sensitivities(diag, pass0, log)
    log("P4's route on the lightest design (not r1; for the operating limit and the static margins)")
    d8 = REPO / diag["lightest_8h"]["record"]
    with p9.ledger_in_use(p9.LEDGER_R1):
        d, L = p9.load(d8), uav.load_ledger(d8.parent / "ledger.yaml")[0]
        A = yaml.safe_load(p9.ARRANGEMENT.read_text())
        r4 = st.p4_on_r1(d, L, A, log)
    res["p4_lightest_8h"] = {k: r4[k] for k in ("x_le_stage1_ft", "x_le_p4_ft", "wing_p4_minus_stage1_ft", "x_main_p4_ft",
                                                 "static_margin", "stage1_static_margin", "neutral_point_difference_mac",
                                                 "rows", "extension_needed_ft", "extension_used_ft", "multhopp_over_16_22")}
    res["p4_lightest_8h"]["ballast_lb"] = r4["ballast"]["ballast_every_loading_lb"]
    res["p4_lightest_8h"]["rotation_used_of_limit"] = r4["rotation"]["used_of_limit"]
    res["acceptance"] = acceptance(pass1, diag, res["table"])
    res["stopped"] = any(a["row"] in (1, 2) and a["verdict"] == "fail" for a in res["acceptance"])
    p9.finish(out, own, res, "summary.json", t0)
    log("acceptance: " + "; ".join(f"{a['row']} {a['verdict']}" for a in res["acceptance"]) + f" ({time.time() - t0:.0f} s)")


# ---- the report ---------------------------------------------------------------------------------------------------
def f(x, fmt=".4g"):
    if x is None:
        return "-"
    if isinstance(x, str):
        return x
    return format(x, fmt)


def report_text(summary_path):
    s = p9.load(summary_path)
    pass0, pass1 = p9.load(REPO / s["inputs"]["records"]["pass0"]), p9.load(REPO / s["inputs"]["records"]["pass1"])
    diag = p9.load(REPO / s["inputs"]["records"]["diagnose"])
    r0d = p9.load(p9.R0 / "design_pusher.json")
    r0ig, r0cell = p9.load(R0_INFO), p9.load(R0_CELL)
    ig8 = diag["info_gap_lightest_8h"]["h_hat"]
    acc = {a["row"]: a for a in s["acceptance"]}
    v0 = pass0["values"]
    trace = pass1["sizing"]["iterations"][0]["candidates"][0]
    W = []
    w = W.append
    w("# Task 12 preliminary design P9: closing re-record r1 and robustness")
    w("")
    w(f"**{p9.REVIEW}.** Run on Opus 5.5 under owner ruling PD-25 (`docs/specs/00_decisions.md` section 9), ahead of Fable's "
      "review of P5, P7 and P8; Fable reviews P5, P7, P8 and P9 together before P10 and Gate C.")
    w("")
    w(f"Generated by `python -m prelim.p9_report report` from `{rel(summary_path)}` and the records it names: "
      + ", ".join(f"`{v}`" for v in s["inputs"]["records"].values()) + ". Every number below is read from them. "
      "Spec: `docs/specs/task12_preliminary_design.md`, P9. Findings list: `data/task12/pd_p9_findings.yaml`; decisions "
      "PD-26 (how the findings enter r1) and PD-27 (the sponson). Nothing was tuned; a failed row is reported.")
    w("")
    w("## In short")
    w("")
    w(f"- **Acceptance 1 fails. There is no r1.** The closing re-record, sized as r0 was (ruling B-2b: W/S 13, A 8, 450 shp, "
      f"guarantee target h_T {p9.H_T:g}, robust_sizing's procedure, seed {info_gap.SEED}, {info_gap.N_SAMPLES} samples), "
      f"finds no sized loiter in 8 to 16 h: {trace['status']}.")
    a1 = acc[1]["value"]
    w(f"- The lightest W/S 13, A 8 aircraft with every applied finding (Stage 1 at L_sized 8 h, the bisection's lower end; "
      f"W0 {f(diag['lightest_8h']['W0_lb'], ',.1f')} lb) has an R5 guarantee horizon of **{f(ig8['R5_guarantee'])}** and an R7 "
      f"horizon of **{f(ig8['R7'])}** (full info-gap study; threshold 1). Along the failing cliff corner it climbs to 20,000 ft "
      f"only up to h = {f(a1['climb_limit_h_lightest_8h'], '.3f')}; r0 as built with every finding, up to h = "
      f"{f(a1['climb_limit_h_r0_with_findings'], '.3f')}. A heavier sizing (more loiter) climbs worse, so no re-size of this cell reaches 1.")
    att = diag["attribution"]
    sp_name = "PD-27 sponson"
    w(f"- What breaks it is the climb to the mission altitude, which Stage 1's two-point climb never tested (P1-1). Of the "
      f"findings, the resized sponson of PD-27 (scale {f(v0['sponson_size_factor'], '.3f')}) is the one that, with the integrated "
      f"climb, takes the rate of climb at 20,000 ft below zero at h = 1 ({f(att[sp_name]['rate_at_mission_altitude_fpm'], '.1f')} "
      f"ft/min; with the integrated climb alone {f(att['P1 integrated climb']['rate_at_mission_altitude_fpm'], '.1f')} ft/min).")
    w("- Acceptance 2 and 4 are not judged and the re-runs of P3 to P8 on r1 were not made: there is no r1. Acceptance 3 is "
      "tabulated with r0 as built with the findings and the lightest design in place of r1 (section 6).")
    w("- **The design stops here (brief, and spec P9 'If 1 or 2 fails').** No other cell was sized and nothing was chosen. "
      "The spec's next step is a return to Stage 1 with the full study of W/S 13, A 7 (PD-4); the owner decides.")
    w("")
    w("## 1. Acceptance rows (spec P9)")
    w("")
    w("| # | Row | Result | Verdict |")
    w("|---|---|---|---|")
    w(f"| 1 | {acc[1]['what']} | no r1 ({trace['status']}); lightest design: R5 guarantee {f(ig8['R5_guarantee'])}, R7 {f(ig8['R7'])} | **fail** |")
    w(f"| 2 | {acc[2]['what']} | not judged; the lightest design's Stage 1 rows: {len(acc[2]['value']['lightest_8h_stage1_rows_failed'])} of "
      f"{acc[2]['value']['lightest_8h_stage1_rows']} fail | **not judged (no r1)** |")
    w(f"| 3 | {acc[3]['what']} | {acc[3]['value']['fields']} fields, r0 against r0 as built with the findings and the lightest design (section 6) | **tabulated without r1** |")
    w(f"| 4 | {acc[4]['what']} | - | **not run (no r1)** |")
    w("")
    w("## 2. The findings and what entered r1")
    w("")
    w("| Id | Finding | Value at its record and key | Applied | Ledger entry | Reason |")
    w("|---|---|---|---|---|---|")
    for x in p9.findings():
        w(f"| {x['id']} | {x['what']} | {f(x['value'], '.6g') if not isinstance(x['value'], str) else x['value']} (`{x['record']}` `{x['key']}`) | "
          f"{'yes' if x['applied'] else 'no'} | {('`' + x['entry'] + '`') if x.get('entry') else '-'} | {x['reason']} |")
    w("")
    w(f"P1's five band proposals (finding P1-4) are not applied and are listed for Gate C: "
      + "; ".join(f"`{p['entry']}` {p['value']}" for p in next(x for x in p9.findings() if x['id'] == 'P1-4')['proposals']) + ".")
    w("")
    w("## 3. r1's inputs measured on the loft (pass 0: r0's sizes with the PD-21 layout)")
    w("")
    w(f"Record `{s['inputs']['records']['pass0']}` (commit `{pass0['inputs']['commit'][:7]}`, clean tree: {not pass0['inputs']['git_dirty']}). "
      "These values are the measured entries of `data/task12/ledger_r1.yaml`.")
    w("")
    w("| Entry | Value | What |")
    w("|---|---|---|")
    for k in p9.MEASURED:
        w(f"| `{k}` | {f(v0[k], '.5g')} | {p9.measured_entry(k, 0, '').get('source').split(': ', 1)[1].split('; measured')[0]} |")
    sp0 = pass0["detail"]["sponson"]
    w("")
    w(f"- **PD-27, the sponson.** r0's sponson ({f(sp0['stage1_sponson_ft']['length'], '.3f')} ft long, "
      f"{f(sp0['stage1_sponson_ft']['depth'], '.3f')} ft deep) does not hold the main gear (P3 finding 7). The least scale of the "
      f"same ellipsoid, placed as P3 places it, at which P3's three gear boxes per side keep P3's {f(sp0['required_in'], 'g')} in "
      f"clearance is **{f(sp0['scale'], '.4f')}** (bisection bracket {f(sp0['bracket'][0], '.4f')} to {f(sp0['bracket'][1], '.4f')}; "
      f"least clearance there {f(sp0['clearance_in'], '.2f')} in): {f(sp0['scale'] * sp0['stage1_sponson_ft']['length'], '.2f')} ft by "
      f"{f(sp0['scale'] * sp0['stage1_sponson_ft']['depth'], '.2f')} ft.")
    pos = pass0["detail"]["sponson_position_sensitivity"]
    w(f"- Sensitivity, not the choice: with the sponson's centre placed 0.2 or 0.4 of its length ahead of the main wheel "
      f"(P3: 0.3) the least scale is {f(pos['0.2'], '.4f')} and {f(pos['0.4'], '.4f')}.")
    w("")
    w("## 4. Pass 1: the sizing of r1")
    w("")
    w(f"Record `{s['inputs']['records']['pass1']}` (commit `{pass1['inputs']['commit'][:7]}`, ledger sha256 "
      f"`{pass1['inputs']['ledger_sha256'][:12]}`). Corner sets: the final sets of the Gate B re-size (450 shp, h_T 1.05), "
      f"re-scaled to h_T in r1's ledger: {len(pass1['sizing']['corner_sets']['endurance'])} endurance, "
      f"{len(pass1['sizing']['corner_sets']['cliff'])} cliff corners.")
    w("")
    for t in trace["trace"]:
        w(f"- L_sized {f(t['L_h'], 'g')} h: {t['class']}; {t.get('why', '')}")
    w(f"- Result: {trace['status']}. The loft inputs were not measured again on r1 (there is no r1).")
    w("")
    w("## 5. Why: the climb to 20,000 ft at the cliff corners")
    w("")
    w(f"Record `{s['inputs']['records']['diagnose']}`. For each case and each cliff corner of the sizing: the member of U(h) along "
      "the corner's directions, its rate of climb at 20,000 ft and its absolute ceiling at the weight after take-off, the "
      "transit power ratio (above 1, or not flyable, is the cliff), and the largest h at which it still climbs to 20,000 ft. "
      "Members of r0 as recorded are taken in the Gate B ledger, the others in r1's.")
    w("")
    w("| Case | Corner | h | Rate at 20,000 ft (ft/min) | Absolute ceiling (ft) | Transit ratio or reason |")
    w("|---|---|---|---|---|---|")
    lims = []
    for case, rows in diag["corners"].items():
        for r in rows:
            if "climb_limit_h" in r:
                lims.append((case, r["corner"], r["climb_limit_h"]))
                continue
            if r["h"] in (1.0, 1.05):
                tr = r["reason"] if r["reason"] else f(r["transit_ratio"], ".4f")
                w(f"| {case} | {r['corner']} | {f(r['h'], 'g')} | {f(r['rate_at_mission_altitude_fpm'], '.1f')} | "
                  f"{f(r['absolute_ceiling_ft'], ',.0f')} | {tr} |")
    w("")
    w("| Case | Corner | Largest h at which it climbs to 20,000 ft |")
    w("|---|---|---|")
    for case, c, h in lims:
        w(f"| {case} | {c} | {f(h, '.3f')} |")
    w("")
    w(f"Each finding group with the integrated climb, at corner {diag['attribution_corner']}, h = 1 (r0 as built):")
    w("")
    w("| Group | Rate at 20,000 ft (ft/min) | Absolute ceiling (ft) | Largest h that climbs |")
    w("|---|---|---|---|")
    for g, r in att.items():
        w(f"| {g} | {f(r['rate_at_mission_altitude_fpm'], '.1f')} | {f(r['absolute_ceiling_ft'], ',.0f')} | {f(r['climb_limit_h'], '.3f')} |")
    w("")
    w("- The two-point climb of Stage 1 never fails at a corner: it evaluates the drag at two altitudes and has no rate of "
      "climb in it. The integrated climb flies each altitude; at the cliff corners the aircraft is close to its absolute ceiling "
      "at 20,000 ft, and the larger sponson's weight and drag take it below.")
    w(f"- The full info-gap study of the lightest design: " + ", ".join(f"{k} {f(v)}" for k, v in ig8.items())
      + f" (r0: " + ", ".join(f"{k} {f(v['h_hat'])}" for k, v in r0ig["h_hat"].items()) + ").")
    w("")
    w("## 6. r1 minus r0, field by field (acceptance 3, without r1)")
    w("")
    w("Columns: r0 as built (its record rebuilt), r0 as built with every finding (no re-size, PD-26 item 8), and the lightest "
      "W/S 13, A 8 design with r1's ledger (Stage 1 at 8 h). 'Caused by': every finding group that alone moves the field on "
      "r0 as built by more than a part in a million (section 7 has each group's numbers; a field that follows W0 moves with "
      "every group that moves W0, however little); the last column adds Stage 1's re-size to 8 h.")
    w("")
    w("| Field | Unit | r0 | r0 with findings | change by the findings | lightest design | change by the re-size | caused by |")
    w("|---|---|---|---|---|---|---|---|")
    for r in s["table"]:
        w(f"| {r['label']} | {r['unit']} | {f(r['r0'], '.5g')} | {f(r['r0_with_findings'], '.5g')} | {f(r['findings_change'], '+.4g')} | "
          f"{f(r['lightest_8h'], '.5g')} | {f(r['resize_change'], '+.4g')} | {', '.join(r['caused_by']) or 'none'} |")
    w("")
    w("Main numbers (no r1; r0 against the lightest design with the findings):")
    w("")
    l8, p4l = diag["lightest_8h"], s["p4_lightest_8h"]
    r0row = p9.load(p9.R0 / "robust_candidate.json")
    diag_L8 = p9.load((REPO / l8["record"]).parent / "robust_candidate.json")["L_sized_h"]
    p4r0 = p9.load(REPO / "runs/task12/pd/2026-11-27/p4/p4.json")["as_arranged"]["row1"]["gear_up/empty_weight_x1"]
    p4b = p9.load(p9.P4B_RECORD)
    bal0 = p4b["candidates"][p4b["selection"]["chosen"]]["measures"]["payload_off"]["ballast_every_loading_lb"]
    w("| | r0 | lightest design with the findings (not r1) |")
    w("|---|---|---|")
    w(f"| W0 (lb) | {f(r0d['W0_lb'], ',.1f')} | {f(l8['W0_lb'], ',.1f')} |")
    w(f"| fuel (lb) | {f(r0d['fuel_lb'], ',.1f')} | {f(l8['fuel_lb'], ',.1f')} |")
    w(f"| L_sized (h) | {f(r0row['L_sized_h'], '.3f')} | {f(diag_L8, '.3f')} (the bisection's lower end; no L satisfies the corners) |")
    w(f"| span (ft) | {f(r0d['wing']['span'], '.2f')} | {f(l8['span_ft'], '.2f')} |")
    w(f"| R5 guarantee / R7 horizon | {f(r0ig['h_hat']['R5_guarantee']['h_hat'])} / {f(r0ig['h_hat']['R7']['h_hat'])} | {f(ig8['R5_guarantee'])} / {f(ig8['R7'])} |")
    w(f"| power margin | {f(1 - max(r0d['power_required_hp'].values()) / r0d['bhp_sl'], '.4f')} | {f(l8['nominal']['power_margin'], '.4f')} |")
    w(f"| service ceiling (ft) | {f(r0d['performance']['service_ceiling_ft'], ',.0f')} | {f(l8['nominal']['service_ceiling_ft'], ',.0f')} |")
    w(f"| static margin full / empty, Stage 1's layout | {f(r0d['layout']['sm_full'], '.4f')} / {f(r0d['layout']['sm_empty'], '.4f')} | "
      f"{f(p4l['stage1_static_margin']['full'], '.4f')} / {f(p4l['stage1_static_margin']['empty'], '.4f')} |")
    w(f"| static margin full / empty, P4's route | {f(p4r0['sm_full'], '.4f')} / {f(p4r0['sm_empty'], '.4f')} (P4, r0 as arranged) | "
      f"{f(p4l['static_margin']['full'], '.4f')} / {f(p4l['static_margin']['empty'], '.4f')} |")
    w(f"| payload-off ballast (lb), P4b's rule | {f(bal0, '.0f')} (P4b, PD-21 layout at r0's sizes) | {f(p4l['ballast_lb'], '.0f')} |")
    w("")
    w("The P4 row of the static margin for r0 is P4's recorded value on r0 as P3 arranged it (`runs/task12/pd/2026-11-27/p4/p4.json`); "
      "the 474 lb is P4b's (`runs/task12/pd/2026-11-28/p4b/p4b.json`).")
    w("")
    w(f"P4's route on the lightest design (labelled: not r1): wing leading edge {f(p4l['x_le_p4_ft'], '.3f')} ft against Stage 1's "
      f"{f(p4l['x_le_stage1_ft'], '.3f')} ft; extension the tails need {f(p4l['extension_needed_ft'], '.3f')} ft against "
      f"{f(p4l['extension_used_ft'], '.3f')} ft used; Multhopp over (16.22) {f(p4l['multhopp_over_16_22'], '.4f')}; rotation "
      f"{f(p4l['rotation_used_of_limit'], '.3f')} of the tail limit; rows: " + ", ".join(f"{k} {v}" for k, v in p4l["rows"].items()) + ".")
    w("")
    w("## 7. Each finding group alone on r0 as built")
    w("")
    w("| Group | W0 (lb) | empty (lb) | hours on station | take-off (ft) | landing (ft) | CD0 at 20,000 ft | ceiling (ft) |")
    w("|---|---|---|---|---|---|---|---|")
    b = diag["r0_built"]
    w(f"| none (r0 rebuilt) | {f(b['W0_lb'], ',.1f')} | {f(b['We_lb'], ',.1f')} | {f(b['hours_on_station'], '.3f')} | {f(b['takeoff_ft'], ',.0f')} | "
      f"{f(b['landing_ft'], ',.0f')} | {f(b['CD0']['mission_altitude'], '.5f')} | {f(b['service_ceiling_ft'], ',.0f')} |")
    for g, o in list(s["one_at_a_time"].items()) + [("every finding", diag["r0_built_with_findings"])]:
        w(f"| {g} | {f(o['W0_lb'], ',.1f')} | {f(o['We_lb'], ',.1f')} | {f(o['hours_on_station'], '.3f')} | {f(o['takeoff_ft'], ',.0f')} | "
          f"{f(o['landing_ft'], ',.0f')} | {f(o['CD0']['mission_altitude'], '.5f')} | {f(o['service_ceiling_ft'], ',.0f')} |")
    w("")
    w("## 8. Sensitivities (labelled; not bands, not applied)")
    w("")
    sens = s["sensitivities"]
    w(f"On the climb at corner {sens['corner']} (largest h at which the aircraft still climbs to 20,000 ft) and on the nominal "
      "hours on station on the record's fuel. CD0 +-10 % is P1's route (leakage_fraction); the faired peak is P2's section 1.43 by "
      "eye (wing about 1.29); the sponson row uses the least scale with the centre 0.4 of its length ahead of the wheel.")
    w("")
    w("| Case | r0 with findings: climb limit h | its hours | lightest design: climb limit h | its hours |")
    w("|---|---|---|---|---|")
    for name, c in sens["cases"].items():
        a, l = c["r0_with_every_finding"], c["lightest_8h"]
        w(f"| {name} | {f(a['climb_limit_h'], '.3f')} | {f(a['nominal_hours'], '.3f')} | {f(l['climb_limit_h'], '.3f') if l else '-'} | "
          f"{f(l['nominal_hours'], '.3f') if l else '-'} |")
    w("")
    w("The full info-gap studies with CD0 +-10 % (PD-26 item 9) were not run: they are defined on r1, which does not exist. The "
      "climb limit above bounds the R5 guarantee from above along that corner.")
    w("")
    w("## 9. Re-runs on r1")
    w("")
    w("None. P3, P4, P5, P7 and P8 were to be re-run on r1, and the compliance table, the Gate A re-check, the V-n check, the "
      "Stage 3 rows, the full info-gap study and the step-doubling check (NR-13) repeated on it. With no r1 they were not run "
      "(the brief: stop and report). The code for them is in `prelim/p9_study.py` (commands reruns, robustness, built, cd0, p8) "
      "and runs on r1 once one exists.")
    w("")
    w("## 10. Decisions and assumptions")
    w("")
    w("- PD-25 (owner ruling): P9 on Opus 5.5 before Fable's review. PD-26: how the findings enter r1. PD-27: the sponson.")
    w("- The integrated climb is P0's integration (prelim/p0_baseline.integrate_climb) coded in conceptual/uav.py; a test shows "
      "they agree to 1e-12 on r0. A member of U(h) that has no rate of climb at some altitude cannot fly the mission (info_gap.UNFLYABLE).")
    w("- Stage 1 without the r1 entries reproduces every r0 number (the full test suite passes on the new code).")
    w(f"- The info-gap study uses {p9.STUDY_PROCESSES} processes (Gate B used 2): each job carries its own seed, so the result does not depend on it.")
    w("- 'The lightest design' is Stage 1 at the bisection's lower end (8 h, the nominal R5 requirement) with r1's ledger. It is "
      "not chosen and is not r1; it is recorded so that the failure has numbers.")
    w("- The diagnosis's climb check is the integrated climb's own test (rate of climb at each altitude above zero) evaluated at "
      "the weight after take-off; a test shows it agrees with the mission on whether a member can be flown.")
    w("")
    w("## 11. What this does not show")
    w("")
    w("- Whether another sponson, gear or cell closes: nothing was re-sized or chosen. The owner decides (spec P9; PD-4).")
    w("- No re-run of P3 to P8 on r1, no Gate A re-check, no Stage 3 rows on r1: there is no r1.")
    w(f"- {p9.REVIEW}.")
    return "\n".join(W) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("summary", "report"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    out = (REPO / a.out).resolve()
    if a.command == "report":
        (REPO / a.report).write_text(report_text(out / "summary.json"))
        return
    t0, lines = time.time(), []

    def log(msg, **_):
        lines.append(f"[{time.time() - t0:7.0f} s] {msg}")
        print(lines[-1], flush=True)
        if out.exists():
            (out / "summary.log").write_text("\n".join(lines) + "\n")
    cmd_summary(out, log)


if __name__ == "__main__":
    main()

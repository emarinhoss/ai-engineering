"""Report and figures of preliminary design P1 (prelim/p1_package.py), from the record alone.

report_text(out) returns the Markdown of docs/validation/<date>_task12_pd_p1.md; write_figures(out, folder) draws
the figures it links. Both read OUT/p1.json, OUT/design_tractor.json and the baseline record r0. No number is
typed here: each is formatted from a record field, and a sentence that states a finding is chosen by the
record's own flags.
"""
import json
from pathlib import Path

from conceptual import uav
from conceptual.units import isa
from prelim import p1_package as p1

REPO = p1.REPO
STATE_NAMES = {"nominal": "nominal, sized loiter", "corner_h1": "worst endurance point at h = 1",
               "corner_target": "worst endurance point at the target h_T"}
SEGMENTS = ("takeoff", "climb", "cruise_out", "loiter", "cruise_back")


def n(x, nd=1):
    """A number with thousands separators and nd decimals; text and None pass through."""
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        return f"{x:,.{nd}f}"
    return str(x)


def cell(x):
    """A table cell for a value of mixed kind (the compliance matrix): 4 significant figures for a number."""
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        return f"{x:,.0f}" if abs(x) >= 1e4 else f"{x:.4g}"
    return str(x)


def cap(text):
    """The text with its first letter in upper case and the rest as it is."""
    return text[0].upper() + text[1:]


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows] + [""]


def rel(path):
    return str(Path(path).relative_to(REPO))


def read(out):
    out = Path(out)
    return (p1.load(out / "p1.json"), p1.load(p1.R0 / "design_pusher.json"), p1.load(p1.R0 / "info_gap.json"),
            uav.load_ledger(p1.R0 / "ledger.yaml"))


# ---- figures ------------------------------------------------------------------------------------------------
def write_figures(out, folder):
    """The figures of the report, drawn from the records (matplotlib only, PD-2), and figures.json beside them
    saying what each was drawn from. They are sketches of the sizing records: geometry only, no flow solution."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from conceptual import report as stage1_report
    out, folder = Path(out), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    res, d, _, (L, _) = read(out)
    tractor = p1.load(out / "design_tractor.json")
    stage1_report.three_view(d, folder / "three_view_pusher.png")
    stage1_report.three_view(tractor, folder / "three_view_tractor.png")
    stage1_report.weights_plot(d, folder / "weights.png")
    stage1_report.polar_plot(d, isa(L["mission_altitude_ft"])["rho"], folder / "polar.png")
    stage1_report.constraint_plot(res["constraint"]["rows"], res["constraint"]["limits"], d,
                                  folder / "constraint_diagram.png", ceiling_ft=L["ceiling_ft"])
    stage1_report.vn_plot(d, folder / "vn.png")

    # internal layout: the drawn body in side view with the stations of the record and the bay of the first check
    bay = res["payload_bay"]["nose"]
    L_f, D_f = d["fuselage"]["length"], d["fuselage"]["diameter"]
    xs = [i * L_f / 200 for i in range(201)]
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(xs, [p1.body_radius(x, L_f, D_f) for x in xs], "k")
    ax.plot(xs, [-p1.body_radius(x, L_f, D_f) for x in xs], "k")
    ax.axvspan(bay["bay_from_ft"], bay["bay_to_ft"], ymin=0.05, ymax=0.45, color="tab:orange", alpha=0.35,
               label="payload bay of the first check (full cross-section)")
    ax.plot([bay["nose_gear_station_ft"], bay["retracted_aft_reaches_ft"]], [-0.35 * D_f] * 2, color="tab:red", lw=3,
            label="nose-gear leg retracted aft (record's gear length)")
    at = {}                                             # items within half a foot of each other get one label
    for name, st in d["stations"].items():
        ax.plot(st["x"], 0.0, "o", color="tab:blue", ms=4)
        at.setdefault(round(2.0 * st["x"]) / 2.0, []).append(name.replace("installed_", "").replace("_", " "))
    for x, names in at.items():
        ax.annotate(", ".join(names), (x, 0.0), xytext=(x, 0.65 * D_f), rotation=50, fontsize=7, ha="left", va="bottom",
                    arrowprops={"arrowstyle": "-", "color": "0.6", "lw": 0.6})
    ax.axvline(d["layout"]["x_np"], ymin=0.05, ymax=0.45, color="m", ls="--", lw=1, label="neutral point")
    ax.axvspan(min(d["layout"]["cg_full"], d["layout"]["cg_empty"]), max(d["layout"]["cg_full"], d["layout"]["cg_empty"]),
               ymin=0.05, ymax=0.45, color="tab:green", alpha=0.5, label="CG range, full to empty fuel")
    ax.set_aspect("equal")
    ax.set_ylim(-0.75 * D_f, 2.6 * D_f)
    ax.set_yticks([])
    ax.set_xlabel("ft from nose")
    ax.set_title("Internal layout: stations of the record on the drawn body of revolution (a sketch, not a loft)", fontsize=9)
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(folder / "layout.png", dpi=130)
    plt.close(fig)

    # carpet: the committed re-size grid
    rows = res["carpet"]["rows"]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    good, none = [r for r in rows if r["ok"]], [r for r in rows if not r["ok"]]
    ax.plot([r["W_S"] for r in none], [r["A"] for r in none], "x", color="0.5", label="no robust design in this cell")
    ax.plot([r["W_S"] for r in good], [r["A"] for r in good], "o", color="tab:blue", label="robust design, with its W0 (lb)")
    for r in good:
        ax.annotate(f"{r['W0_lb']:,.0f}", (r["W_S"], r["A"]), fontsize=8, xytext=(7, 5), textcoords="offset points")
    ax.plot([d["W_S"]], [d["A"]], "r*", ms=16, label="r0")
    ax.set_xlabel("take-off wing loading W/S (lb/ft^2)")
    ax.set_ylabel("aspect ratio A")
    ax.set_title("Sizing matrix: cells of the committed re-size grid (450 shp, h_T 1.05, last iteration)", fontsize=9)
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(folder / "carpet.png", dpi=130)
    plt.close(fig)

    # trades of the built aircraft
    t = res["trades"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    panels = (("payload_for_fuel", "payload_lb", "payload (lb), exchanged for fuel at the record's W0"),
              ("altitude_as_built", "mission_altitude_ft", "cruise and loiter altitude (ft)"),
              ("composite_as_built", "composite_factor", "composite factor (1.00 is metal)"))
    for ax, (key, x, label) in zip(axes, panels):
        ax.plot([r[x] for r in t[key]], [r["hours_on_station"] for r in t[key]], "o-")
        ax.axhline(p1.R5_NOMINAL_HOURS, color="0.4", lw=1, ls="--")
        ax.set_xlabel(label)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("hours on station (dashed: the 8 h of R5)")
    fig.suptitle("Trades of the built aircraft r0 (nothing re-sized)", fontsize=10)
    fig.tight_layout()
    fig.savefig(folder / "trades.png", dpi=130)
    plt.close(fig)

    names = {"three_view_pusher.png": "three-view of r0", "three_view_tractor.png": "three-view of the tractor of the concept record",
             "layout.png": "internal layout of r0 with the payload bay of the first check", "weights.png": "empty weight by component",
             "polar.png": "drag polar with the mission points", "constraint_diagram.png": "constraint diagram at r0's weight",
             "carpet.png": "carpet from the committed re-size grid", "vn.png": "V-n diagram", "trades.png": "trades of the built aircraft"}
    (folder / "figures.json").write_text(json.dumps({
        "made_by": "prelim/p1_report.py write_figures", "label": "drawn from the sizing records; geometry only, no flow solution",
        "record": rel(out), "record_commit": res["inputs"]["commit"], "p1_json_sha256": p1.sha256(out / "p1.json"),
        "r0_design_sha256": p1.sha256(p1.R0 / "design_pusher.json"), "figures": names}, indent=1) + "\n")


# ---- report ---------------------------------------------------------------------------------------------------
def findings(res, d):
    """The findings of the package as sentences, each chosen by a flag of the record."""
    out = []
    cl, sc, bay, audit = res["climb_check"]["states"], res["concepts"]["scoring"], res["payload_bay"], res["ledger"]["audit"]
    for key in ("corner_h1", "corner_target"):
        s, m = cl[key], cl[key]["against_stall_at_altitude"]["end_of_climb_weight"]
        if not m["above_floor"]:
            out.append(
                f"**Climb at the {STATE_NAMES[key]} (item 18).** Stage 1's climb leg flies {n(s['stage1_climb_speed_kt'])} kt true airspeed "
                f"from sea level to {n(s['mission_altitude_ft'], 0)} ft. At the top that is {n(m['over_stall'], 3)} of the stall speed "
                f"({n(m['V_stall_kt'])} kt at the end-of-climb weight, clean C_L,max {n(s['clmax_clean'], 3)})"
                + (": below the stall speed. " if not m["above_stall"] else ": below 1.2 V_stall. ")
                + f"Integrated in {n(res['climb_check']['step_ft'], 0)} ft steps the climb burns {n(s['integrated_fuel_lb'])} lb against "
                f"{n(s['two_point_fuel_lb'])} lb ({s['fuel_difference_lb']:+.1f} lb, {100 * s['mission_fuel_share']:.2f} % of the mission fuel"
                + (f", above the {100 * s['tolerance']:g} % threshold" if s["finding_for_r1"] else f", inside the {100 * s['tolerance']:g} % threshold")
                + f"), and the rate of climb at the top is {n(s['rate_at_top_fpm'], 0)} ft/min"
                + (f", below the {n(s['ceiling_rate_fpm'], 0)} ft/min of the service-ceiling definition. " if s["top_of_climb_above_service_ceiling"] else ". ")
                + f"Estimate of the hours on station with the integrated climb: {n(s['hours_estimate'], 2)} h against {n(s['hours_on_station'], 2)} h "
                f"(need {n(s['need_h'])} h). The estimate divides the fuel difference by the loiter fuel flow; the mission was not flown again."
                + (" **Finding for r1 (P9).**" if s["finding_for_r1"] else ""))
    out.append(f"**Concept scoring (NR-4).** Pusher {n(sc['score']['pusher'], 2)}, tractor {n(sc['score']['tractor'], 2)}: "
               + ("**the scoring reverses**; this is reported to the owner and the choice is not re-opened (PD-3). " if sc["reversed"]
                  else "not reversed. ")
               + f"The pusher is {n(sc['pusher_over_tractor_W0'], 3)} times the tractor's weight; the scores are equal at {n(sc['break_even_ratio'], 3)}. "
               f"In the 2026-11-25 record the pusher scored {n(sc['previous_score']['pusher'], 2)}.")
    nose = bay["nose"]
    if nose["retracted_leg_crosses_bay"]:
        out.append(f"**Nose packaging (item 30).** The payload volume of PD-12 ({n(bay['payload_volume_ft3'], 2)} ft^3) is "
                   f"{100 * bay['payload_share_of_free_volume']:.1f} % of the free body volume, so the whole-body check passes. Locally it does not "
                   f"fit yet: a bay at the payload station takes {n(nose['bay_from_ft'], 2)} to {n(nose['bay_to_ft'], 2)} ft at full cross-section, "
                   f"and the nose-gear leg ({n(nose['gear_length_ft'], 2)} ft, station {n(nose['nose_gear_station_ft'], 2)} ft) retracted aft reaches "
                   f"{n(nose['retracted_aft_reaches_ft'], 2)} ft, through that bay"
                   + (f" and past the avionics station ({n(nose['avionics_station_ft'], 2)} ft)" if nose["retracted_leg_passes_avionics_station"] else "")
                   + ". Stage 1 has no stow check for the nose gear. **For P3 (and P4 if the bay or the gear moves).**")
    low = [(r["name"], p) for r in audit["rows"] for p in r.get("points", []) if p["hours_at_corner_h1"] < res["climb_check"]["states"]["corner_h1"]["need_h"]]
    need = res["climb_check"]["states"]["corner_h1"]["need_h"]
    if low:
        out.append("**Unbanded estimates that would break the R5 guarantee at h = 1 if they moved (item 28).** "
                   + "; ".join(f"`{name}` at {p['value']:.4g}: {n(p['hours_at_corner_h1'], 2)} h" for name, p in low)
                   + f" at the record's worst endurance point (need {n(need)} h; {n(audit['corner_h1_hours'], 2)} h there today). "
                   "None of these values is a band: they are the common +-10 % step, a proposed band end, or the +10 % on CD0. "
                   "**For Gate C: whether these entries get a band, and P9 if they do.**")
    else:
        out.append(f"**Unbanded estimates (item 28).** No audited entry, moved by the common +-10 % step, a proposed band end or the +10 % on CD0, "
                   f"takes the worst endurance point at h = 1 below {n(need)} h.")
    like = res["empty_weight"]["table_3_1"]["like_for_like"]
    out.append(f"**Empty weight (items 8, 27).** Like for like (metal, crew items in) the group equations are {n(like['gap_lb'], 0)} lb above the "
               f"Table 3.1 fit. Four features of this aircraft account for {n(like['gap_lb'] - like['remainder_lb'], 0)} lb of it by what-if scaling; "
               f"{n(like['remainder_lb'], 0)} lb is left unexplained. The risk stays named (B-9g).")
    return out


def report_text(out):
    out = Path(out)
    res, d, _, (L, entries) = read(out)
    inp = res["inputs"]
    fig = f"figures/{out.parent.name}_task12_pd_{out.name}"          # docs/validation/figures/<date>_task12_pd_p1
    acc = res["acceptance"]
    t, cl, dec = res["trades"], res["climb_check"]["states"], res["decomposition"]
    lines = []
    add = lines.append

    add("# Task 12 preliminary design P1: Stage 1 package for the baseline r0")
    add("")
    add(f"Generated by `python -m prelim.p1_package --report-only` from `{rel(out)}/p1.json` and the baseline record `{res['baseline']}`. "
        "Every number below is read from those files. Spec: `docs/specs/task12_preliminary_design.md`, package P1 (ruling B-9a). "
        "Tolerances were fixed before the run; nothing was tuned. r0 was not re-sized and no ledger band was changed.")
    add("")
    add(f"Evidence class: **{res['evidence_class']}**. It collects what Stage 1 says about r0 and closes the entry item of B-9a; it verifies no quantity of the aircraft.")
    add("")

    add("## 1. Run")
    add("")
    add(f"- Command: `{inp['command']}`")
    add(f"- Commit `{inp['commit']}`; working tree at the start: {'clean' if not inp['git_dirty'] else 'DIRTY'} (the run's own folder `{inp['excluded']}` is not counted); "
        f"unchanged during the run: {n(inp['tree_unchanged_during_run'])}.")
    add(f"- Seed: none. {cap(inp['seed_note'])}. python {inp['python']}, numpy {inp['numpy']}, pyyaml {inp['pyyaml']}, matplotlib {inp['matplotlib']}.")
    add("- Inputs (sha256, first 12): " + "; ".join(f"`{inp['files'][k]}` {inp['sha256'][k][:12]}" for k in inp["files"]) + ".")
    add(f"- Log: `{rel(out)}/run.log`. Run time {n(res['runtime_s'], 0)} s.")
    add("")

    add("## 2. Acceptance rows")
    add("")
    add("Rows 1 to 6 are the spec's. Rows 7 to 12 are one per added Gate B item; their criteria were written in `tests/task12_pd/test_p1_package.py` and `prelim/p1_package.py` before the run.")
    add("")
    rep, w, bay, sc, e = res["reproduction"], res["weight_statement"], res["payload_bay"], res["concepts"]["scoring"], res["empty_weight"]
    results = {
        1: f"{rep['n_compared']} fields compared, {len(rep['different'])} differ, largest relative difference {rep['max_relative_difference']:.1g}",
        2: f"{acc[1]['n_rows']} rows, {acc[1]['value']} blank cells, {acc[1]['n_failed']} failed rows; R1 to R19 each have a row",
        3: f"sum of components minus the record's empty weight: {w['difference_lb']:+.2g} lb",
        4: f"{acc[3]['n_points']} points, largest difference {acc[3]['value']:.1g}",
        5: f"{acc[4]['value']} entries; the 8 flagged on 2026-11-25 are all there; {len(acc[4]['problems'])} problems",
        6: f"{acc[5]['value']} risks; {acc[5]['n_without_package']} have no package and name their ruling; {len(acc[5]['problems'])} problems",
        7: f"re-sized nominal W0 differs from r0 by {acc[6]['value']:.1g} (relative); built aircraft {n(acc[6]['hours_nominal'], 4)} h against the sized {n(res['sized_loiter_h'], 3)} h",
        8: "climb speed over the stall speed at the top of the climb: " + ", ".join(f"{STATE_NAMES[k]} {n(v, 3)}" for k, v in acc[7]["value"].items())
           + "; integrated climb as a share of the mission fuel: " + ", ".join(f"{100 * v:.2f} %" for v in acc[7]["mission_fuel_share"].values()),
        9: f"pusher {n(sc['score']['pusher'], 3)}, tractor {n(sc['score']['tractor'], 3)}; weight ratio {n(sc['pusher_over_tractor_W0'], 3)} against a break-even of {n(sc['break_even_ratio'], 3)}",
        10: f"Table 15.2 groups against the record's value: {acc[9]['value']:.1g} (relative); {n(acc[9]['unexplained_lb'], 0)} lb of the like-for-like gap unexplained",
        11: f"{acc[10]['value']} entries: " + ", ".join(f"{v} {k}" for k, v in acc[10]["by_class"].items()),
        12: f"{n(bay['payload_volume_ft3'], 2)} ft^3 against {n(bay['free_volume_ft3'], 1)} ft^3 free ({100 * bay['payload_share_of_free_volume']:.1f} %)"}
    tol = {1: f"{p1.TOL_REPRODUCE:g}", 3: f"{p1.TOL_WEIGHT_LB:g} lb", 4: f"{p1.TOL_VN:g}", 7: f"{p1.TOL_REPRODUCE:g}; 0.002 h",
           8: f"1.2 V_stall; {100 * p1.TOL_CLIMB_FUEL:g} % of the mission fuel", 10: f"{p1.TOL_REPRODUCE:g}"}
    lines += table(["#", "Row", "Result", "Tolerance", "Verdict"],
                   [[str(a["row"]), a["what"], results[a["row"]], tol.get(a["row"], "-"), f"**{a['verdict']}**"] for a in acc])

    add("## 3. Findings")
    add("")
    for i, text in enumerate(findings(res, d), 1):
        add(f"{i}. {text}")
    add("")

    add("## 4. Requirements compliance matrix (Stage 1 output 1)")
    add("")
    add("`conceptual/stage1.compliance` on the design sized again here (equal to r0, row 1), with a margin for every numeric rule, and the rows that function does not write: R3, R11 and the robust half of R5 and R7. "
        "Margin is the distance to the limit, positive inside it. Class S1: " + p1.STAGE1_CLASS + ". Class RB: " + p1.ROBUST_CLASS + ". Class PK: " + p1.EVIDENCE_CLASS + ".")
    add("")
    code = {p1.STAGE1_CLASS: "S1", p1.ROBUST_CLASS: "RB", p1.EVIDENCE_CLASS: "PK"}
    lines += table(["#", "Req.", "Requirement", "Units", "Value", "Limit", "Margin", "Verdict", "Class", "Produced by"],
                   [[str(i), r["requirement_id"], r["requirement"], r["units"], cell(r["value"]), cell(r["limit"]), cell(r["margin"]),
                     r["verdict"], code[r["evidence_class"]], r["step"]] for i, r in enumerate(res["compliance"]["rows"], 1)])
    add(f"The service ceiling row now reads the engine table to {n(d['performance']['engine_table_top_ft'], 0)} ft (P0); at Gate B it read above the table top. "
        + ("No row fails. " if not acc[1]["n_failed"] else f"**{acc[1]['n_failed']} rows fail.** ")
        + "The R6 rows have no source (assumption R-f) and are not verdicts.")
    add("")

    add("## 5. Three-view and internal layout (output 2)")
    add("")
    add(f"![three-view]({fig}/three_view_pusher.png)")
    add("")
    add(f"![layout]({fig}/layout.png)")
    add("")
    add("Both are sketches drawn by code from the sizing record: geometry only, no flow solution, and a body of revolution that Stage 1 knows only through its length, diameter and fill factor. P3 redraws the three-view from the loft.")
    add("")
    wg, ht, vt, fus, lay = d["wing"], d["horizontal_tail"], d["vertical_tail"], d["fuselage"], d["layout"]
    lines += table(["Quantity", "Value"], [
        ["wing area, span, aspect ratio, taper", f"{n(wg['area'])} ft^2, {n(wg['span'], 2)} ft, {n(wg['aspect_ratio'])}, {n(wg['taper'], 2)}"],
        ["wing root chord, tip chord, mean chord and its span station", f"{n(wg['root_chord'], 2)} ft, {n(wg['tip_chord'], 2)} ft, {n(wg['mac'], 3)} ft at {n(wg['mac_y'], 2)} ft"],
        ["horizontal tail area, span (volume scale over Table 6.4)", f"{n(ht['area'])} ft^2, {n(ht['span'], 2)} ft ({n(d['ht_volume_scale'], 3)})"],
        ["vertical tail area, height", f"{n(vt['area'])} ft^2, {n(vt['height'], 2)} ft"],
        ["fuselage length, diameter, wetted area", f"{n(fus['length'], 2)} ft, {n(fus['diameter'], 2)} ft, {n(fus['s_wet'])} ft^2"],
        ["tail arm", f"{n(d['tail_arm_ft'], 2)} ft"],
        ["propeller diameter; clearance at rotation", f"{n(d['propeller_diameter_ft'], 2)} ft; {n(lay['prop_clearance_in'])} in"],
        ["gear length; main-wheel half track; wheels retract into", f"{n(d['gear_length_in'])} in; {n(lay['gear_track']['half_track_ft'], 2)} ft; {lay['gear_track']['retracts_into']}"],
        ["wing leading edge at the root; main wheels; CG height", f"{n(lay['x_le'], 2)} ft; {n(lay['x_main'], 2)} ft; {n(lay['h_cg'], 2)} ft"],
        ["fuel volume needed; wing tank volume claimed", f"{n(d['fuel_volume_ft3']['needed'], 2)} ft^3; {n(d['fuel_volume_ft3']['available'], 2)} ft^3"]])

    add("## 6. Weight statement (output 3; Gate B items 8 and 27)")
    add("")
    add("### 6.1 Components, stations and centre of gravity")
    add("")
    lines += table(["Item", "Weight (lb)", "Station (ft from nose)", "Moment (lb ft)"],
                   [[r["item"].replace("_", " "), n(r["weight_lb"], 2), n(r["x_ft"], 2), n(r["moment_lb_ft"], 0)] for r in w["rows"]]
                   + [["**empty weight (sum)**", f"**{n(w['sum_components_lb'], 2)}**", "", ""],
                      ["payload", n(w["payload_lb"], 2), n(w["payload_x_ft"], 2), n(w["payload_lb"] * w["payload_x_ft"], 0)],
                      ["fuel (wing tanks, at the wing station)", n(w["fuel_lb"], 2), n(w["fuel_x_ft"], 2), n(w["fuel_lb"] * w["fuel_x_ft"], 0)],
                      ["**take-off weight**", f"**{n(w['W0_lb'], 2)}**", "", ""]])
    add(f"- Sum of the components against the record's empty weight ({n(w['We_lb'], 3)} lb): {w['difference_lb']:+.2g} lb (tolerance {p1.TOL_WEIGHT_LB:g} lb).")
    add(f"- Centre of gravity, full fuel: {n(w['cg_full_record_ft'], 3)} ft in the record, {n(w['cg_full_from_stations_ft'], 3)} ft from the stations above. "
        f"Empty of fuel, payload on: {n(w['cg_empty_record_ft'], 3)} ft and {n(w['cg_empty_from_stations_ft'], 3)} ft. Zero-fuel weight {n(w['zero_fuel_weight_lb'], 1)} lb.")
    add(f"- Neutral point {n(lay['x_np'], 3)} ft; static margin {n(lay['sm_full'], 4)} MAC full and {n(lay['sm_empty'], 4)} MAC empty (by layout construction, ruling B-6).")
    add("")
    add(f"![weights]({fig}/weights.png)")
    add("")
    add("### 6.2 Build-up against Raymer's approximate group weights (Table 15.2), group by group")
    add("")
    g152 = e["table_15_2"]
    lines += table(["Group", "Build-up, as built (lb)", "Build-up, metal (lb)", "Table 15.2 (lb)", "Rule of the table", "As built minus table (lb)"],
                   [[g["group"], n(g["build_up_lb"]), n(g["build_up_metal_lb"]), n(g["table_15_2_lb"]), g["rule"], f"{g['build_up_minus_table_lb']:+,.1f}"]
                    for g in g152["groups"]]
                   + [["**sum**", f"**{n(g152['sum_build_up_lb'])}**", f"**{n(sum(g['build_up_metal_lb'] for g in g152['groups']))}**",
                       f"**{n(g152['sum_table_lb'])}**", "", f"**{g152['sum_build_up_lb'] - g152['sum_table_lb']:+,.1f}**"]])
    c = d["empty_fraction_comparison"]
    add(f"- As fractions of W0: build-up {n(c['build_up'], 4)}, Table 15.2 {n(c['table_15_2_approximate'], 4)}. Exposed wing area {n(e['s_exposed_ft2'])} ft^2 (from the design sized again; the record does not store it).")
    heavier = [g["group"] for g in g152["groups"] if g["build_up_minus_table_lb"] < -0.5]
    lighter = [g["group"] for g in g152["groups"] if g["build_up_minus_table_lb"] > 0.5]
    metal_below = [g["group"] for g in g152["groups"] if g["metal_minus_table_lb"] < -0.5 and g["build_up_metal_lb"] != g["build_up_lb"]]
    add(f"- The table is heavier than the build-up in: {', '.join(heavier) or 'no group'}; lighter in: {', '.join(lighter) or 'no group'}. "
        f"Groups where the metal build-up is still below the table, so that the composite factors are not the whole difference: {', '.join(metal_below) or 'none'}. "
        "The table's tail rule is applied here to a tail enlarged for rotation.")
    add("- Weight per area of the build-up, as metal, against the table's rule: "
        + "; ".join(f"{g['group']} {n(g['build_up_metal_lb'] / (g['table_15_2_lb'] / float(g['rule'].split()[0])), 2)} against {g['rule'].split()[0]} lb/ft^2"
                    for g in g152["groups"] if "lb/ft^2" in g["rule"]) + ".")
    add("- 'Metal' divides each group by its Table 15.4 factor, as the record's `build_up_metal` does (the sponsons are left as they are).")
    ab = e["anderson_build_up"]
    add(f"- Anderson's build-up of the Gate B report uses the same table and iterates the weight with it: W0 {n(ab['buildup_W0'], 0)} lb, empty {n(ab['buildup_We'], 0)} lb (`{rel(p1.PERF)}`). It is the same comparison at a heavier aircraft, not a second source.")
    add("")
    add("### 6.3 Build-up against the Table 3.1 fit")
    add("")
    lines += table(["Step", "Empty fraction", "Empty weight at r0's W0 (lb)", "Change (lb)"],
                   [[s["label"], n(s["fraction"], 4), n(s["weight_lb"]), "" if i == 0 else f"{s['change_lb']:+,.1f}"]
                    for i, s in enumerate(e["table_3_1"]["steps"])])
    like = e["table_3_1"]["like_for_like"]
    add(f"The fit is a total, so it has no components. The step that needs explaining is the like-for-like one, {like['gap_lb']:+,.0f} lb. "
        "Each line below takes one feature of this aircraft back to a reference value through the exponent of its own group equation, with everything else held. They are what-ifs on the equations, not a re-size, and they are not strictly additive.")
    add("")
    lines += table(["Feature a general-aviation single of the fit does not have", "Metal weight it adds (lb)", "How"],
                   [[f["feature"], n(f["metal_lb"]), f["how"]] for f in like["features"]]
                   + [["**left unexplained**", f"**{n(like['remainder_lb'])}**", "the gap less the four lines"]])
    add(f"- The crew items the fit's aircraft carry and this one does not ({n(c['crew_items_furnishings'] * d['W0_lb'])} lb) and the larger composite saving of the group factors against the fit's single factor then bring the build-up back to {n(c['build_up'], 4)}, "
        f"{n((c['build_up'] - c['table_3_1']) * d['W0_lb'])} lb above the fit ({n(c['table_3_1'], 4)}).")
    add(f"- Table 6.2's fit gives {n(e['table_3_1']['table_6_2_fraction'], 4)}, below both.")
    add("- This explains the difference between the three numbers. It does not show which is right: all three are crewed general-aviation statistics (out-of-calibration entry OC-1). The typical wing loading is read from the chapter notes of the library (Raymer Table 5.5, p. 84).")
    add("")

    add("## 7. Drag, propulsion and mission (output 4; NR-1; item 18)")
    add("")
    add("### 7.1 Drag polar and propeller points of r0")
    add("")
    cd0 = d["CD0"]
    ld = 0.5 / (cd0["mission_altitude"] * d["K"]) ** 0.5
    add(f"- CD0 {n(cd0['mission_altitude'], 5)} at mission altitude, {n(cd0['sea_level'], 5)} at sea level, {n(cd0['takeoff'], 5)} in the take-off and {n(cd0['landing'], 5)} in the landing configuration. "
        f"K {n(d['K'], 5)}, e {n(d['e'], 4)}. Largest L/D of that polar at mission altitude: {n(ld, 2)} (computed here as 1/(2 sqrt(CD0 K))).")
    add(f"- C_L,max {n(d['CL_max']['clean'], 3)} clean, {n(d['CL_max']['takeoff'], 3)} take-off, {n(d['CL_max']['landing'], 3)} landing.")
    add("")
    add(f"![polar]({fig}/polar.png)")
    add("")
    lines += table(["Propeller point", "Speed (kt)", "Shaft power (hp)", "Efficiency", "J", "C_P", "Throttle"],
                   [[k.replace("_", " "), n(v["V_kt"]), n(v["shaft_hp"]), n(v["eta_p"], 4), n(v["J"], 3), n(v["C_P"], 4), n(v["throttle"], 3)]
                    for k, v in d["propeller_points"].items()])
    add(f"Propeller diameter {n(d['propeller_diameter_ft'], 2)} ft at {n(L['propeller_rpm'], 0)} rpm; App. L disk times f = {n(L['prop_real_to_ideal'], 2)}.")
    add("")
    add("### 7.2 Fuel by mission segment")
    add("")
    burned = sum(m["burned_lb"] for m in d["mission"])
    lines += table(["Segment", "Weight at start (lb)", "Fuel burned (lb)", "Mean speed (kt)", "Mean C_bhp", "Time (h)", "Sub-steps on the R17 floor", "Sub-steps in unchoked cells"],
                   [[m["segment"].replace("_", " "), n(m["W_start"]), n(m["burned_lb"], 2), n(m["V_kt"]), n(m["cbhp_mean"], 4), n(m["leg_time_h"], 3),
                     f"{m['speed_floor_fraction']:.0%}", f"{m['turbine_unchoked_fraction']:.0%}"] for m in d["mission"]]
                   + [["**burned in the mission**", "", f"**{n(burned, 2)}**", "", "", "", "", ""],
                      ["**fuel on board (with the 6 % of R10)**", "", f"**{n(d['fuel_lb'], 2)}**", "", "", "", "", ""]])
    add(f"Share of the mission fuel burned in unchoked table cells: {100 * d['unchoked_fuel_share']:.1f} % (Gate B item 11, unchanged).")
    add("")
    add("### 7.3 App. L decomposition on r0 (NR-1)")
    add("")
    add("`measurement/appl_decomposition.case` on r0: the mission with the disk as recorded, and with a flat propeller efficiency swapped in. The flat value is the ledger's `eta_p` at nominal and its band low end scaled by h at the two worst endurance points of the record. "
        "This is what the robust weight owes to the disk, segment by segment. The earlier decomposition (2026-11-26) compared two baselines of the superseded cell; r0 has no flat-propeller twin, so the swap is made on r0 itself.")
    add("")
    for key in ("nominal", "corner_h1", "corner_target"):
        s = dec[key]
        add(f"**{cap(STATE_NAMES[key])}** (take-off weight {n(s['disk']['W0_lb'])} lb, loiter {n(s['loiter_h'], 3)} h, f {n(s['disk_factor'], 4)}, flat efficiency {n(s['flat_eta_p'], 4)}):")
        add("")
        lines += table(["Segment fuel (lb)", "Disk", "Flat", "Disk minus flat"],
                       [[k.replace("_", " "), n(s["disk"]["segment_fuel_lb"][k], 2), n(s["flat"]["segment_fuel_lb"][k], 2), f"{s['disk_minus_flat_lb'][k]:+.2f}"] for k in SEGMENTS]
                       + [["mission fuel with reserve", n(s["disk"]["fuel_with_reserve_lb"], 2), n(s["flat"]["fuel_with_reserve_lb"], 2), f"{s['disk_minus_flat_lb']['fuel_with_reserve']:+.2f}"],
                          ["hours on station on the record's fuel", n(s["hours_on_station"]["disk"], 3), n(s["hours_on_station"]["flat"], 3),
                           f"{s['hours_on_station']['disk'] - s['hours_on_station']['flat']:+.3f}"]])
        dc, fc = s["disk"]["climb"], s["flat"]["climb"]
        add(f"Mean disk efficiency: cruise out {n(s['disk']['mean_eta']['cruise_out'], 4)}, loiter {n(s['disk']['mean_eta']['loiter'], 4)}, cruise back {n(s['disk']['mean_eta']['cruise_back'], 4)}. "
            f"Climb leg: efficiency at mid-altitude {n(dc['eta_mid_altitude'], 4)} (flat {n(fc['eta_mid_altitude'], 4)}), drag over thrust {n(dc['drag_over_thrust'], 3)} ({n(fc['drag_over_thrust'], 3)}), "
            f"climb speed {n(dc['climb_speed_kt'])} kt ({n(fc['climb_speed_kt'])} kt).")
        add("")
    tgt = dec["corner_target"]["disk_minus_flat_lb"]
    add(f"At the worst point of the target the disk costs {tgt['fuel_with_reserve']:+.1f} lb of mission fuel against the flat low end, and the climb leg is {tgt['climb']:+.1f} lb of it. "
        "P6 checks the disk; the next section checks the climb model.")
    add("")
    add("### 7.4 The climb at the worst endurance corner (item 18)")
    add("")
    add("Stage 1's climb leg uses one true airspeed, the best-climb speed at sea level, all the way up, and averages drag over thrust between sea level and the mission altitude at that speed (`conceptual/uav.py`, the climb rows of the mission). "
        "The table compares that speed with the stall speed at the mission altitude, and then integrates the same climb in steps with `prelim.p0_baseline.integrate_climb` (the P0 function), where each altitude flies its own best-climb speed, never below 1.2 V_stall.")
    add("")
    keys = ("nominal", "corner_h1", "corner_target")

    def row(label, f):
        return [label] + [f(cl[k]) for k in keys]
    lines += table(["", *(STATE_NAMES[k] for k in keys)], [
        row("take-off weight (lb)", lambda s: n(s["W0_lb"])),
        row("clean C_L,max", lambda s: n(s["clmax_clean"], 3)),
        row("Stage 1 climb speed (kt true)", lambda s: n(s["stage1_climb_speed_kt"])),
        row("stall speed at the mission altitude, end-of-climb weight (kt)", lambda s: n(s["against_stall_at_altitude"]["end_of_climb_weight"]["V_stall_kt"])),
        row("climb speed over that stall speed", lambda s: n(s["against_stall_at_altitude"]["end_of_climb_weight"]["over_stall"], 3)),
        row("the same at the start-of-climb weight", lambda s: n(s["against_stall_at_altitude"]["start_of_climb_weight"]["over_stall"], 3)),
        row("at or above the stall speed / at or above 1.2 V_stall", lambda s: n(s["against_stall_at_altitude"]["end_of_climb_weight"]["above_stall"]) + " / "
            + n(s["against_stall_at_altitude"]["end_of_climb_weight"]["above_floor"])),
        row("climb fuel, Stage 1 two-point (lb)", lambda s: n(s["two_point_fuel_lb"], 2)),
        row("climb fuel, integrated (lb)", lambda s: n(s["integrated_fuel_lb"], 2)),
        row("difference (lb; relative)", lambda s: f"{s['fuel_difference_lb']:+.2f}; {100 * s['fuel_difference_relative']:+.1f} %"),
        row("as a share of the mission fuel (threshold 1 %)", lambda s: f"{100 * s['mission_fuel_share']:.2f} %"),
        row("time to climb, integrated (min)", lambda s: n(s["integrated_time_min"])),
        row("rate of climb at sea level; at the top (ft/min)", lambda s: f"{n(s['rate_at_sea_level_fpm'], 0)}; {n(s['rate_at_top_fpm'], 0)}"),
        row("integrated climb speed at sea level; one step below the top (kt)", lambda s: f"{n(s['speed_at_sea_level_kt'])}; {n(s['speed_below_top_kt'])}"),
        row("hours on station in the record", lambda s: n(s["hours_on_station"], 3)),
        row("estimate with the integrated climb (h)", lambda s: f"{n(s['hours_estimate'], 3)} ({s['hours_change_estimate']:+.3f})"),
        row("finding for r1", lambda s: n(s["finding_for_r1"]))])
    worst = cl["corner_target"]
    for k in keys:
        m = cl[k]["against_stall_at_altitude"]["end_of_climb_weight"]
        if m["above_floor"]:
            add(f"- {cap(STATE_NAMES[k])}: the Stage 1 speed is at or above 1.2 V_stall at the top of the climb.")
        elif m["above_stall"]:
            add(f"- {cap(STATE_NAMES[k])}: the Stage 1 speed is above the stall speed at the top of the climb but **below 1.2 V_stall**, the ledger's lowest climb speed.")
        else:
            add(f"- {cap(STATE_NAMES[k])}: the Stage 1 speed is **below the stall speed at the mission altitude**. The two-point estimate there evaluates drag at a lift coefficient above C_L,max, which the aircraft cannot fly.")
    add("- This is the first test of item 18 on this design; at Gate B it was not testable.")
    add(f"- The estimate of hours is the fuel difference divided by the loiter fuel flow of the same state ({n(worst['loiter_fuel_flow_lb_h'])} lb/h at the target point). The mission was not flown again with the integrated climb, and the worst-case search was not repeated with it, so the worst point itself may move. "
        f"What can be said: at h = 1 the estimate ({n(cl['corner_h1']['hours_estimate'], 2)} h) is still {'at or above' if cl['corner_h1']['hours_estimate'] >= cl['corner_h1']['need_h'] else 'BELOW'} the {n(cl['corner_h1']['need_h'])} h of R5; "
        f"at the target h_T it ({n(worst['hours_estimate'], 2)} h) is {'at or above' if worst['hours_estimate'] >= worst['need_h'] else 'below'} it.")
    add(f"- The rate of climb at the top of the climb is {n(cl['corner_h1']['rate_at_top_fpm'], 0)} ft/min at the h = 1 point and {n(worst['rate_at_top_fpm'], 0)} ft/min at the target point, against {n(worst['ceiling_rate_fpm'], 0)} ft/min for a service ceiling"
        + (": at the target point the mission altitude is above that aircraft's service ceiling at that weight. " if worst["top_of_climb_above_service_ceiling"] else ". ")
        + "R12's ceiling is a requirement at nominal values, and it is met there. "
        "The info-gap study checks the endurance and the level-flight power of the transit legs; it has no row for the climb to the mission altitude.")
    add("- Class: coding check with finer steps. It shares the polar, the engine table and the propeller model with Stage 1.")
    add("")

    add("## 8. Constraint diagram, carpet plot and trades (output 5; NR-3)")
    add("")
    add("### 8.1 Constraint diagram")
    add("")
    lim = res["constraint"]["limits"]
    add(f"![constraint diagram]({fig}/constraint_diagram.png)")
    add("")
    add(f"`conceptual/stage1.constraint_diagram` at r0's weight and aspect ratio, run here. Stall limit W/S {n(lim['stall'], 2)} lb/ft^2; landing limit {n(lim['landing'], 1)} lb/ft^2; "
        f"best-range wing loading at the cruise dynamic pressure {n(lim['best_range_at_cruise_q'], 2)}; best-loiter wing loading at the loiter dynamic pressure {n(lim['best_loiter_at_loiter_q'], 2)}. r0 is at {n(d['W_S'], 0)}.")
    pr = d["power_required_hp"]
    add("Power required at r0 (hp): " + ", ".join(f"{k.replace('_', ' ')} {n(v)}" for k, v in pr.items()) + f"; installed {n(d['bhp_sl'], 0)}. "
        f"The largest is {100 * max(pr.values()) / d['bhp_sl']:.1f} % of the installed power. These are requirements at nominal values; "
        "the cell and the sized loiter of r0 were set by the robust sizing (rulings R-d, B-2c), which this diagram does not show.")
    add("")
    add("### 8.2 Carpet plot from the committed re-size grid")
    add("")
    add(f"![carpet]({fig}/carpet.png)")
    add("")
    add(f"No new sizing: the cells are the last iteration of `{res['carpet']['source']}` (450 shp, both bands acting, target h_T 1.05).")
    add("")
    lines += table(["W/S", "A", "Robust design", "W0 (lb)", "Sized loiter (h)", "If none, why"],
                   [[n(r["W_S"], 0), n(r["A"], 0), n(r["ok"]), n(r["W0_lb"]) if r["ok"] else "-", n(r["L_sized_h"], 3) if r["ok"] else "-",
                     "" if r["ok"] else r["status"].split(" (")[0]] for r in sorted(res["carpet"]["rows"], key=lambda r: (r["W_S"], r["A"]))])
    add("### 8.3 Trades of the built aircraft (nothing re-sized)")
    add("")
    add(f"![trades]({fig}/trades.png)")
    add("")
    add("The aircraft of r0 as built, rebuilt by the info-gap study's own function with one value changed.")
    add("")
    add("Loiter time against payload, with payload exchanged for fuel at the record's take-off weight:")
    add("")
    lines += table(["Payload (lb)", "Fuel (lb)", "Hours on station", "Fuel volume (ft^3)", "Fits the wing tanks"],
                   [[n(r["payload_lb"], 0), n(r["fuel_lb"]), n(r["hours_on_station"], 2), n(r["fuel_volume_ft3"], 2), n(r["fuel_fits_tanks"])] for r in t["payload_for_fuel"]])
    add("The same payloads with the record's fuel on board (the take-off weight changes):")
    add("")
    lines += table(["Payload (lb)", "Take-off weight (lb)", "Hours on station", "Take-off over 50 ft (ft)", "Landing over 50 ft (ft)"],
                   [[n(r["payload_lb"], 0), n(r["W0_lb"]), n(r["hours_on_station"], 2), n(r["takeoff_ft"], 0), n(r["landing_ft"], 0)] for r in t["payload_at_record_fuel"]])
    add("Altitude of the cruise and loiter:")
    add("")
    lines += table(["Mission altitude (ft)", "Hours on station"], [[n(r["mission_altitude_ft"], 0), n(r["hours_on_station"], 2)] for r in t["altitude_as_built"]])
    add("Composite factor across its band (the empty weight moves, the fuel does not):")
    add("")
    lines += table(["Composite factor", "Take-off weight (lb)", "Hours on station", "Take-off over 50 ft (ft)", "Landing over 50 ft (ft)"],
                   [[n(r["composite_factor"], 3), n(r["W0_lb"]), n(r["hours_on_station"], 2), n(r["takeoff_ft"], 0), n(r["landing_ft"], 0)] for r in t["composite_as_built"]])
    add("Above 20,000 ft the engine's operating altitude is an assumption (R-f), as it is at 20,000 ft.")
    add("")
    add("### 8.4 Stage 1's one-at-a-time trades, re-sized at W/S 13, A 8")
    add("")
    add("`conceptual/stage1.analyse` with one ledger value changed, the tail resized for rotation, then the compliance rows. Each row is another aircraft, for comparison only: r0 is not changed. The sized loiter is 11 h unless it is the value traded.")
    add("")
    rs_rows = []
    for key, label in (("loiter_h", "sized loiter (h)"), ("payload_lb", "payload (lb)"), ("mission_altitude_ft", "mission altitude (ft)"), ("composite_factor", "composite factor")):
        for r in t["resized"][key]:
            v = r["changes"][key]
            rs_rows.append([label, f"{v:g}", n(r["W0_lb"]), n(r.get("fuel_lb")), n(r.get("We_lb")),
                            f"{r['W0_lb'] - d['W0_lb']:+,.1f}" if r["W0_lb"] else "n/a", "; ".join(r.get("failed", [r.get("error", "")])) or "none"])
    lines += table(["Trade", "Value", "W0 (lb)", "Fuel (lb)", "Empty (lb)", "W0 minus r0 (lb)", "Failed compliance rows"], rs_rows)
    add(f"The nominal case of this function is r0 to {p1.TOL_REPRODUCE:g} (row 7).")
    add("")

    add("## 9. Concept record at these sizes (NR-4; Gate A item A9)")
    add("")
    add("The tractor with the same engine and the rubber-engine pusher, sized by Stage 1 at W/S 13, A 8 with the ledger r0 was sized with, the 11 h sized loiter included. The choice of the pusher is not re-opened (PD-3).")
    add("")
    des = res["concepts"]["designs"]
    cols = (("r0 (pusher, M250)", None), ("tractor, M250", des["tractor"]), ("pusher, rubber engine", des["pusher_rubber"]))

    def crow(label, r0_value, f):
        return [label, r0_value] + [f(x) for _, x in cols[1:]]
    lines += table(["Quantity", *(c[0] for c in cols)], [
        crow("take-off weight (lb)", n(d["W0_lb"]), lambda x: n(x["W0_lb"])),
        crow("empty weight (lb)", n(d["We_lb"]), lambda x: n(x["We_lb"])),
        crow("fuel (lb)", n(d["fuel_lb"]), lambda x: n(x["fuel_lb"])),
        crow("engine power (hp); engine weight (lb)", f"{n(d['bhp_sl'], 0)}; {n(d['engine']['weight_lb'], 0)}", lambda x: f"{n(x['bhp'], 0)}; {n(x['engine_weight_lb'], 0)}"),
        crow("engine inside Table 10.4's range", n(d["engine"]["in_range"]), lambda x: n(x["engine_in_range"])),
        crow("horizontal-tail volume scale", n(d["ht_volume_scale"], 3), lambda x: n(x["ht_volume_scale"], 3)),
        crow("gear length (in); propeller clearance at rotation (in)", f"{n(d['gear_length_in'])}; {n(d['layout']['prop_clearance_in'])}",
             lambda x: f"{n(x['gear_length_in'])}; {n(x['prop_clearance_in'])}"),
        crow("nose-wheel load, full; empty", f"{n(d['layout']['nose_load']['full'], 3)}; {n(d['layout']['nose_load']['empty'], 3)}",
             lambda x: f"{n(x['nose_load']['full'], 3)}; {n(x['nose_load']['empty'], 3)}"),
        crow("take-off; landing over 50 ft (ft)", f"{n(d['performance']['takeoff_ft'], 0)}; {n(d['performance']['landing_ft'], 0)}",
             lambda x: f"{n(x['takeoff_ft'], 0)}; {n(x['landing_ft'], 0)}"),
        crow("service ceiling (ft)", n(d["performance"]["service_ceiling_ft"], 0), lambda x: n(x["service_ceiling_ft"], 0)),
        crow("failed compliance rows", "none", lambda x: "; ".join(x["failed"]) or "none"),
        crow("record", f"`{res['baseline']}/design_pusher.json`", lambda x: f"`{rel(out)}/{x['file']}`")])
    add("Scoring table: the round-1 criteria and weights, unchanged (`conceptual/stage1.concept_scores`). Only the weight row is computed; the others are the judgements of Gate A round 1.")
    add("")
    lines += table(["Criterion", "Weight", "Tractor", "Pusher", "Tractor grade", "Pusher grade"],
                   [[r["criterion"], n(r["weight"], 2), n(r["tractor"], 0), n(r["pusher"], 0), n(r["tractor_grade"], 2), n(r["pusher_grade"], 2)] for r in sc["table"]]
                   + [["**weighted score**", "", "", "", f"**{n(sc['score']['tractor'], 2)}**", f"**{n(sc['score']['pusher'], 2)}**"]])
    lines += table(["Feasibility (not scored)", "Tractor", "Pusher"], [[k.replace("_", " "), n(sc["feasibility"]["tractor"][k]), n(sc["feasibility"]["pusher"][k])] for k in sc["feasibility"]["pusher"]])
    add(f"- **The scoring {'REVERSES' if sc['reversed'] else 'does not reverse'}**: highest score {sc['highest_score']}, frozen concept {sc['frozen']}. "
        f"The margin is {n(sc['score']['pusher'] - sc['score']['tractor'], 3)}; on 2026-11-25 it was {n(sc['previous_score']['pusher'] - sc['previous_score']['tractor'], 3)} (`{sc['previous_record']}`, other sizes).")
    add(f"- The pusher weighs {n(sc['pusher_over_tractor_W0'], 3)} times the tractor. With the judgement grades as they are, the scores are equal at {n(sc['break_even_ratio'], 3)}.")
    tr = des["tractor"]
    if tr["failed"]:
        add(f"- The tractor is not a compliant design as analysed. Failed: {'; '.join(tr['failed'])}. Its propeller clearance is {n(tr['prop_clearance_in'])} in on a {n(tr['gear_length_in'], 0)} in gear, against the {n(L['prop_clearance_in'], 0)} in rule. "
            "Whatever cures a failed row adds weight, so the tractor's weight here is on the light side and the comparison favours it.")
    else:
        add("- The tractor passes every compliance row as analysed.")
    rb = des["pusher_rubber"]
    add(f"- The rubber-engine pusher needs {n(rb['bhp'], 0)} hp. It is a reference only: its consumption is Table 3.4's, its lapse the piston (13.9), and its engine is below Table 10.4's range (OC-3, OC-4, OC-5). "
        f"Failed rows: {'; '.join(rb['failed']) or 'none'}; its service ceiling is {n(rb['service_ceiling_ft'], 0)} ft against the {n(L['ceiling_ft'] + L['margin_ceiling_ft'], 0)} ft the row asks (R12 with its margin). "
        "Neither design was sized for the robust target; both carry r0's sized loiter.")
    add("")
    add(f"![tractor]({fig}/three_view_tractor.png)")
    add("")

    add("## 10. V-n diagram (output 6)")
    add("")
    add(f"![V-n]({fig}/vn.png)")
    add("")
    add(f"The points are r0's `vn` entries (row 4). Limit load factor {n(d['n_limit'], 2)}; negative limit {n(L['negative_load_factor'], 2)}; V_C {n(d['V_c_eas_kt']['sea_level'], 0)} kt EAS; "
        f"largest gust load factor {n(d['n_gust'], 4)}; most negative {n(d['n_negative_gust'], 4)}. The negative stall line of the figure is a drawing assumption; P5 computes the negative manoeuvre.")
    add("")
    lines += table(["Case", "Point", "Speed (kt EAS)", "Load factor"],
                   [[p["case"].replace("_", " "), p["point"], n(p["V_eas_kt"], 2), n(p["n"], 4)] for p in res["vn"]["points"]])
    add("The recorded V-n check at V_D and at the level top speed is `docs/validation/2026-11-27_task12_vn_check_ws13a8.md`; it was not run again.")
    add("")

    add("## 11. Stability and trim summary (output 7)")
    add("")
    rot = lay["rotation"]
    lines += table(["Quantity", "Value"], [
        ["neutral point; CG full; CG empty (ft from nose)", f"{n(lay['x_np'], 3)}; {n(lay['cg_full'], 3)}; {n(lay['cg_empty'], 3)}"],
        ["static margin full; empty (MAC); R13 band", f"{n(lay['sm_full'], 4)}; {n(lay['sm_empty'], 4)}; {n(L['static_margin_min'], 2)} to {n(L['static_margin_max'], 2)}"],
        ["tail lift slope (per rad); 1 - d(epsilon)/d(alpha) at the tail", f"{n(lay['CLa_h'], 3)}; {n(lay['dah_da'], 4)}"],
        ["fuselage moment slope (per rad, Raymer (16.22))", n(lay["Cma_fus"], 4)],
        ["wing section moment about the aerodynamic centre", n(lay["cm_wing"], 3)],
        ["trim within the tail's lift limit on every leg", n(lay["trim_ok"])],
        ["rotation speed (kt); tail lift coefficient needed; limit", f"{n(rot['V_kt'])}; {n(rot['CL_tail_needed'], 4)}; {n(L['tail_cl_max_rotation'], 2)}"],
        ["nose-wheel load full; empty (optimum 0.08 to 0.15, limits 0.05 to 0.20)", f"{n(lay['nose_load']['full'], 4)}; {n(lay['nose_load']['empty'], 4)}"]])
    lines += table(["Trim point", "Wing C_L", "Tail C_L"], [[k.replace("_", " "), n(v["CL_wing"], 4), n(v["CL_tail"], 4)] for k, v in lay["trim"].items()])
    add("R13 is met by layout construction (B-6): the wing is placed so that the margin range is centred. The fuselage-inclusive neutral point by an independent route is P4.")
    add("")

    add("## 12. Payload bay, first check (item 30, NR-21, PD-12)")
    add("")
    nose = bay["nose"]
    lines += table(["Quantity", "Value"], [
        [f"payload volume at {n(bay['density_lb_ft3'], 0)} lb/ft^3 (PD-12)", f"{n(bay['payload_volume_ft3'], 2)} ft^3"],
        [f"Stage 1 body volume, Raymer (7.13), projected areas = {n(bay['fuselage_fill'], 2)} x length x diameter", f"{n(bay['body_volume_ft3'], 1)} ft^3"],
        *[[f"less: {i['item']}", f"{n(i['volume_ft3'], 2)} ft^3"] for i in bay["deducted"]],
        ["free volume", f"{n(bay['free_volume_ft3'], 1)} ft^3"],
        ["payload volume over free volume", f"{100 * bay['payload_share_of_free_volume']:.1f} %"],
        ["**fits in the free volume**", f"**{n(bay['fits_in_free_volume'])}**"]])
    add("- Not deducted, because the record gives no size for them: " + "; ".join(bay["not_deducted"]) + ". The free volume is therefore an upper bound and this check cannot fail by a small amount; it shows only that the body as a whole is not short of volume.")
    add(f"- Local reading on the body the three-view draws (its fill is {n(bay['drawn_body']['fill'], 3)} against the ledger's {n(bay['fuselage_fill'], 2)}; volume {n(bay['drawn_body']['volume_ft3'], 1)} ft^3). "
        f"The payload station is {n(nose['payload_station_ft'], 2)} ft from the nose, where the body radius is {n(nose['radius_at_station_ft'], 2)} ft. A bay centred there that fills the whole cross-section needs {n(nose['bay_length_ft'], 2)} ft of length, "
        f"from {n(nose['bay_from_ft'], 2)} to {n(nose['bay_to_ft'], 2)} ft: {100 * nose['payload_share_of_that_volume']:.0f} % of all the volume ahead of the avionics station ({n(nose['avionics_station_ft'], 2)} ft, {n(nose['volume_ahead_of_avionics_station_ft3'], 1)} ft^3). "
        "A real bay does not fill the cross-section, so it is longer.")
    add(f"- The nose gear is at {n(nose['nose_gear_station_ft'], 2)} ft and its leg is {n(nose['gear_length_ft'], 2)} ft long (Stage 1 gives it the main gear's length). "
        f"It cannot retract forward ({n(nose['nose_ahead_of_gear_station_ft'], 2)} ft of nose ahead of it). Retracted aft it reaches {n(nose['retracted_aft_reaches_ft'], 2)} ft: "
        f"{'through the bay' if nose['retracted_leg_crosses_bay'] else 'clear of the bay'}{' and past the avionics station' if nose['retracted_leg_passes_avionics_station'] else ''}. "
        "Stage 1 checks that the main gear stows in the sponsons and has no stow check for the nose gear. The sensor turret is outside the bay (PD-12) but its mount is in the same nose.")
    add("- This local reading is on a drawing convention, not on Stage 1's analysis, and has no verdict. P3 repeats the check with boxes on the loft (gate 4).")
    add("")

    add("## 13. Ledger: band audit and out-of-calibration list (output 8; item 28)")
    add("")
    audit = res["ledger"]["audit"]
    add(f"The ledger of r0 has {audit['n_entries']} entries: {audit['n_banded']} with a band and {audit['n_unbanded']} without. The info-gap study adds two engine multipliers to the banded ones. "
        f"The full ledger with sources is `{res['baseline']}/ledger.yaml`; Appendix A lists every entry.")
    add("")
    add("### 13.1 Band audit of the entries without a band")
    add("")
    add("Classes (judgement of the package lead, `data/task12/pd_p1_judgements.yaml`): **requirement** is what the owner asked for or ruled; **definition** is a design choice, a design rule, a datum of the chosen engine or a model switch; "
        "**needs a band** is an estimate of a physical quantity the built aircraft will have whatever is assumed. " + ", ".join(f"{v} {k}" for k, v in audit["by_class"].items()) + ".")
    add("")
    lines += table(["Entry", "Value", "Class", "Reason"], [[f"`{r['name']}`", cell(r["value"]) + (f" {r['units']}" if r["units"] != "-" else ""), r["class"], r["reason"]]
                                                          for r in audit["rows"] if r["class"] != "needs a band"])
    add(f"**The {audit['by_class']['needs a band']} entries that need a band.** A proposed band is listed for Gate C and is not applied: the ledger is unchanged and no run sized with it. "
        f"{audit['n_proposed_bands']} proposals come from the entry's own source text; the others have none and say why.")
    add("")
    lines += table(["Entry", "Value", "Why it needs a band", "Proposed band", "Basis, or why none", "Measured by"],
                   [[f"`{r['name']}`", cell(r["value"]), r["reason"], "none" if r["proposed_band"] is None else f"{r['proposed_band'][0]:g} to {r['proposed_band'][1]:g}",
                     r["basis"] or r["why_no_proposal"], ", ".join(r["measured_by"]) or f"no package ({r['carried_under'] or 'not carried by a ruling'})"]
                    for r in audit["rows"] if r["class"] == "needs a band"])
    add(f"What each of them moves. Columns 3 to 5: the built aircraft with that one value changed (nominal {n(res['nominal_as_built']['hours_on_station'], 2)} h, "
        f"{n(res['nominal_as_built']['takeoff_ft'], 0)} ft, {n(res['nominal_as_built']['landing_ft'], 0)} ft). Column 6: the same change added to the record's worst endurance point at h = 1 "
        f"({n(audit['corner_h1_hours'], 3)} h there; R5 needs {n(L['r5_robust_hours'])} h). Columns 7 and 8: Stage 1's re-sized trade. The 0.9 and 1.1 times the value are a common step for comparison, **not a band**.")
    add("")
    srows = []
    for r in audit["rows"]:
        for p in r.get("points", []):
            srows.append([f"`{r['name']}`", f"{p['value']:.4g}", f"{p['hours_change']:+.3f}", f"{p['takeoff_change_ft']:+.1f}", f"{p['landing_change_ft']:+.1f}",
                          n(p["hours_at_corner_h1"], 3) + (" **below**" if p["hours_at_corner_h1"] < L["r5_robust_hours"] else ""),
                          f"{p['resized_W0_lb'] - d['W0_lb']:+,.1f}" if p["resized_W0_lb"] else "n/a", "; ".join(x for x in p["resized_failed"] if x) or "none"])
    lines += table(["Entry", "At", "Hours on station, change", "Take-off, change (ft)", "Landing, change (ft)", "Hours at the worst point of h = 1", "Re-sized W0, change (lb)", "Re-sized: failed rows"], srows)
    add("- `leakage_fraction` 0.155 is the parasite drag raised by 10 % (1.155 over 1.05). The drag build-up has no band of its own in the info-gap study, and Gate B found its method resolves CD0 to about +-20 % (G-3).")
    still = [r["name"] for r in audit["rows"] if r.get("points") and all(abs(p["hours_change"]) < 5e-4 and abs(p["takeoff_change_ft"]) < 0.05
                                                                         and abs(p["landing_change_ft"]) < 0.05 for p in r["points"])]
    add("- Entries that move neither the hours nor the field lengths of the built aircraft in these columns: " + (", ".join(f"`{x}`" for x in still) or "none")
        + ". They act on quantities the columns do not show (tail size and stability in the re-sized column, tank volume, loads), or not at all at this design.")
    add("")
    add("### 13.2 Correlations used outside their calibration")
    add("")
    files = dict(p1.evidence_files(), p1=res)

    def evidence(entry):
        return "; ".join(f"{ev['label']}: {cell(p1.lookup(files[ev['file']], ev['path']))}" for ev in entry.get("evidence", []))
    lines += table(["ID", "Correlation", "Calibrated for", "Used here", "Status", "Carried or measured by", "From the records"],
                   [[x["id"] + (" *" if x["flagged_2026_11_25"] else ""), x["correlation"], x["calibrated_for"], x["used_here"], x["status"], x["carried_by"], evidence(x)]
                    for x in res["out_of_calibration"]["entries"]])
    add(f"\\* flagged in the 2026-11-25 package (`docs/validation/2026-11-25_task12_conceptual_m250_appl.md`, section 9). All {len(p1.FLAGGED_2026_11_25)} of its entries are kept; "
        + f"{sum(x['status'] == 'applies to the concept record only' for x in res['out_of_calibration']['entries'])} of the entries now apply to the rubber-engine design of the concept record only. "
        "The entries without the mark are new for r0.")
    add("")

    add("## 14. Risk list (output 9; Gate A item A11)")
    add("")
    add("Every risk names the package of `docs/specs/task12_preliminary_design.md` that measures it. A risk that no package measures says under which ruling it is carried.")
    add("")
    lines += table(["ID", "Risk", "Effect if wrong", "Gate B items", "Measured by", "How", "Carried under", "From the records"],
                   [[k["id"], k["risk"], k["effect"], ", ".join(str(i) for i in k["items"]) or "-", ", ".join(k["measured_by"]) or "**no package**", k["how"],
                     k.get("carried_under", "-"), evidence(k)] for k in res["risks"]["entries"]])

    add("## 15. Test report (output 10)")
    add("")
    if "tests" in res:
        ts = res["tests"]
        add(f"Recorded run at the commit of the record: `{ts['command']}`. Result: `{ts['summary_line']}`, exit code {ts['exit_code']}. Full log: `{rel(out)}/{ts['log']}`. "
            "The tests of this record and of this report are not in that run, because they need the record; they run with the rest of `tests/task12_pd`.")
    else:
        add("No pytest run is recorded in this record (it was made with `--no-tests`).")
    add("")
    eq = res["equations"]
    untested = [x for x in eq if x["tests"] == "**none**"]
    add(f"Method functions of `conceptual/` and the tests in `tests/task12` that call them by name: {len(eq)} functions, {len(untested)} with no test that calls them directly"
        + (": " + ", ".join(f"`{x['function']}`" for x in untested) + ". They may still run inside the pipeline tests." if untested else "."))
    add("")
    lines += table(["Function", "Equations", "Pages", "Tests"], [[f"`{x['function']}`", x["equations"], x["pages"], x["tests"]] for x in eq])

    add("## 16. Assumptions made where the spec left a choice")
    add("")
    add("Each stands until the owner changes it. None is a design choice, so none is a new PD entry.")
    add("")
    for i, text in enumerate((
        "**Trades are given twice.** Of the built aircraft, with nothing re-sized (8.3), and as Stage 1's own one-at-a-time re-sized trades at W/S 13, A 8 (8.4). Reason: the spec names the trades of the Stage 1 package, which are re-sized, and also says the baseline is not re-sized; a re-sized trade row is another aircraft for comparison and changes nothing in r0.",
        "**The carpet plot shows the cells of the last iteration of the committed re-size**, compliant or not. Reason: the spec forbids new sizing for it, and the reason a cell has no design is part of the picture.",
        "**The decomposition swaps the propeller on r0 itself.** Reason: `measurement/appl_decomposition.py` compares two records, and r0 has no flat-propeller twin. Its `case` function is used unchanged. The flat value at a worst point is the ledger's `eta_p` band low end scaled by h, as in the 2026-11-26 decomposition.",
        "**Item 18 is judged at the end-of-climb weight**, where the aircraft is at the mission altitude, against 1.2 V_stall (the ledger's lowest climb speed). The integrated climb reuses P0's function and P0's threshold of 1 % of the mission fuel, applied at each state.",
        "**'These sizes' of the concept record means W/S 13, A 8 with the ledger r0 was sized with**, the 11 h sized loiter and the per-design V_C rule included. Neither comparison design was sized for the robust target.",
        "**The empty-weight what-ifs use the exponents of the group equations**, with everything else held. The typical wing loading of the class (Table 5.5) and the avionics density range of PD-12 were read from the library's chapter notes; the scan of the book is not in this container, so the pages themselves were not opened. Neither is a test target.",
        "**The band audit's three classes are the spec's.** 'Definition' includes design choices and design rules. A band is proposed only where the entry's own source text states two values. The +-10 % step of the sensitivity table is not a band.",
        "**Free fuselage volume** is the (7.13) volume less the two items the record gives a size for. The local reading uses the body the three-view draws, and assumes the nose gear retracts aft.",
        "**The compliance matrix adds five rows** to `stage1.compliance` so that R1 to R19 each have one. The requirement and producing step of each row are a table in `prelim/p1_package.py`.",
        "**The recorded test run leaves out the tests of this record and report**, which cannot exist before the record does.",
        "**No seed**: the package draws no random numbers.",
            ), 1):
        add(f"{i}. {text}")
    add("")

    add("## 17. What this does not show")
    add("")
    add("- It is a package of Stage 1's own numbers. The independent rows are in the Gate B report; the packages named in section 14 measure the rest.")
    add("- The hours with the integrated climb are an estimate. No mission and no worst-case search was run with it. That is P9's to run.")
    add("- The sensitivity of an unbanded entry is one value at a time on top of one stored worst point. It is not an info-gap study with that entry added.")
    add("- The payload-bay check is on a body of revolution with a fill factor. Nothing is lofted (P3).")
    add("- The Stage 3 rows, VSPAERO, the V-n check and the info-gap study were not run again; r0's are quoted.")
    add("- The three-view is not from the loft (P3 redraws it) and no OpenVSP model was made here.")
    add("")

    add("## 18. Files")
    add("")
    add(f"- `{rel(out)}/p1.json` (every result above), `run.log`, `pytest.log`, `design_tractor.json`, `design_pusher_rubber.json`.")
    add(f"- Figures: `docs/validation/{fig}/` with `figures.json`.")
    add("- Code: `prelim/p1_package.py`, `prelim/p1_report.py`; judgements `data/task12/pd_p1_judgements.yaml`; tests `tests/task12_pd/test_p1_package.py`, `test_p1_record.py`, `test_p1_report.py`.")
    add("")

    add("## Appendix A. Ledger of r0")
    add("")
    cls = {r["name"]: r["class"] for r in audit["rows"]}
    lines += table(["Entry", "Value", "Units", "Band", "Confidence", "Audit class (entries without a band)"],
                   [[f"`{k}`", cell(q["value"]), q["units"], f"{q['band'][0]:g} to {q['band'][1]:g}" if "band" in q else "none", q["confidence"], cls.get(k, "-")]
                    for k, q in entries.items()])
    return "\n".join(lines).rstrip() + "\n"

"""Report and figures of preliminary design P4b, generated from the record (OUT/p4b.json).
No number is typed here: every value in the text is read from the record."""
import json
from pathlib import Path

from prelim import p4_balance as p4
from prelim import p4b_trade as t

STEM = "2026-11-28_task12_pd_p4b"
FIGURES = ("layouts", "arm_scan")
ASSUMPTIONS = [
    "Everything P4 assumed stands (its report, section 'Assumptions'): stations, tanks, empty-weight band, Multhopp's fuselage term, Stage 1's trim and rotation with P2's section moment, the wing rule and the tipback rule.",
    "The aft fuselage is lengthened by moving the loft's last control station aft. The engine bay and the engine stay at r0's stations; moving the engine aft with the propeller was not studied (it would take the centre of gravity further aft).",
    "The extension is the least length that leaves 1.0 ft between the rearmost tail point inside the disc and the propeller plane (P4's clearance; a judgement there).",
    "The shaft weight per foot is an assumption with a band, not a number from a source. Raymer p. 221 says only that a longer offset needs a drive shaft with its own bearing support. The steel tube of section 1 is support for the band's low end; its formula and material values are taken from the library's chapter notes and the pages could not be opened in this session.",
    "Fuselage weight by Raymer (15.49) as a ratio: Stage 1's wetted area plus the loft's added skin, the tail arm, the length over diameter. Flight controls by (15.54) as a ratio in fuselage length, charged although the tail does not move aft with the propeller. The added fuselage weight and the shaft sit at the middle of the added length.",
    "The propeller, its hub and the engine weigh what r0 has; a longer shaft's bearings and frames are inside the per-foot value.",
    "Drag: only wetted areas change (P3's route). Form factors, interference factors and reference lengths stay Stage 1's; the lower form factor of a longer body is not credited, and no propeller or slipstream effect on the tail cone or the tails is modelled.",
    "Hours on station are on r0's fuel with r0's engine table; the aircraft is not re-sized. With the empty-weight change in the take-off weight, the geometry stays r0's.",
    "Propeller ground clearance is Stage 1's expression, as P4 used it (hub at the fuselage end, ledger rotation angle of 10 deg with a tail bumper); the tilted disc at the true propeller plane is reported beside it. The gear length is r0's.",
    "The arm scan stops at r0's tail arm: a longer arm than r0's was not studied.",
    "Ballast is at the payload station. The operating-limit figure is the largest need over every payload-off loading, rounded up to a whole pound, and is checked with P4's envelope.",
    "A trial of the code was run before the record, after the choices file and its selection rule were written. It changed one thing: the ballast figure for the operating limit became the largest need over all payload-off loadings (P4's figure, the aftmost loading only, is kept beside it). The rule, the shaft value and the candidates were not changed.",
]


def load(out):
    return json.loads((Path(out) / "p4b.json").read_text())


def f(v, n=3):
    return "-" if v is None else f"{v:,.{n}f}"


def sg(v, n=3):
    return "-" if v is None else f"{v:+,.{n}f}"


def columns(r):
    """(heading, pool name) of the layouts the tables show: A, B, Bs, C and the chosen one if it is none of them."""
    cols = [("A (PD-20)", "A")] + ([("B", "B")] if "B" in r["candidates"] else [])
    for k in ("Bs", "C"):
        if r["named"][k]:
            cols.append((k, r["named"][k]))
    ch = r["selection"]["chosen"]
    if ch and ch not in [c[1] for c in cols]:
        cols.append(("chosen", ch))
    return cols


def write_figures(out, folder):
    """Two figures from the record, matplotlib only: plan sketches of the layouts, and the arm scan."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    out, folder = Path(out), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    r = load(out)
    c = p4.context()
    d, L = c["d"], c["L"]
    cols = columns(r)
    R = 0.5 * d["propeller_diameter_ft"]
    fig, axes = plt.subplots(1, len(cols), figsize=(4.6 * len(cols), 6.5), sharey=True)
    for ax, (title, k) in zip(np.atleast_1d(axes), cols):
        lay, mm = r["candidates"][k]["layout"], r["candidates"][k]["measures"]
        body = t.lengthened_body(c["body"], mm["extension_ft"])
        x = np.linspace(1e-6, body.length, 400)
        half = body.lines(x)[0]
        model = p4.ac.build(p4.record_with_layout(d, L, lay), L, c["A"])
        ax.fill(half, x, color="0.85")
        ax.fill(-half, x, color="0.85")
        for name, col in (("wing", "tab:blue"), ("horizontal_tail", "tab:orange")):
            s = model[name]
            for sign in (1, -1):
                ax.plot([0, sign * s.half_span, sign * s.half_span, 0, 0],
                        [s.x_le, s.x_le + s.le_slope * s.half_span, s.x_le + s.le_slope * s.half_span + s.c_tip, s.x_le + s.c_root, s.x_le], color=col, lw=1.2)
        xp = mm["propeller_plane_x_ft"]
        ax.plot([-R, R], [xp, xp], color="tab:red", lw=2, label="propeller disc")
        ax.axhline(xp - r["clearance_ft"], color="tab:red", lw=0.8, ls=":", label="clearance line")
        ax.axhline(d["fuselage"]["length"], color="0.4", lw=0.8, ls="--", label="end of r0's fuselage")
        ht = d["layout"]["gear_track"]["half_track_ft"]
        ax.plot([-ht, ht], [lay["x_main"]] * 2, "k^", ms=5, label="main wheels")
        ax.set_title(f"{title}\ntail arm {mm['arm_ft']:.2f} ft, extension {mm['extension_ft']:.2f} ft", fontsize=9)
        ax.set_aspect("equal")
        ax.set_xlim(-25, 25)
        ax.invert_yaxis()
        ax.grid(alpha=0.3)
    np.atleast_1d(axes)[0].set_ylabel("ft from the nose")
    np.atleast_1d(axes)[0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Task 12 P4b: plan sketches from the record, geometry only, no flow solution")
    fig.tight_layout()
    fig.savefig(folder / "layouts.png", dpi=130)
    plt.close(fig)
    # the arm scan, at the three shaft weights
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True)
    sets = [(r["shaft_lb_per_ft"]["value"], {k: v["measures"] for k, v in r["candidates"].items()}, r["arm_scan"], "tab:blue")]
    for s, col in zip(r["shaft_band"], ("tab:green", "tab:red")):
        sets.append((s["shaft_lb_per_ft"], s["table"], [k for k in s["table"] if k.startswith("scan_")], col))
    for rate, tab, scan, col in sets:
        arms = [tab[k]["arm_ft"] for k in scan]
        for ax, key, lab in ((axes[0, 0], "empty_weight_change_lb", "empty-weight change, lb"), (axes[0, 1], "hours_for_rule", "hours on station (rule's case b)"),
                             (axes[1, 0], "extension_ft", "fuselage extension, ft"), (axes[1, 1], "propeller_clearance_in", "propeller ground clearance at rotation, in")):
            ax.plot(arms, [tab[k][key] for k in scan], "o-", ms=3, color=col, label=f"shaft {rate:g} lb/ft")
            if "B" in tab:
                ax.plot([tab["B"]["arm_ft"]], [tab["B"][key]], "x", color=col)
            ax.set_ylabel(lab)
            ax.grid(alpha=0.3)
    axes[1, 1].axhline(r["ledger"]["prop_clearance_in"], color="k", lw=1, ls="--", label="least allowed")
    axes[0, 1].axhline(r["r0"]["drag_and_hours"]["hours_on_station"], color="k", lw=1, ls=":", label="r0 unchanged")
    for ax in axes[1]:
        ax.set_xlabel("tail arm, ft (left end: PD-20; right end: r0's arm; crosses: B, r0's planforms)")
    for ax in axes.flat:
        ax.legend(fontsize=7)
    fig.suptitle("Task 12 P4b: the arm scan (straight trailing edges), from the record; balance and weights only, no flow solution")
    fig.tight_layout()
    fig.savefig(folder / "arm_scan.png", dpi=130)
    plt.close(fig)
    side = {"made_by": "prelim/p4b_report.py, matplotlib only", "record": str((out / "p4b.json").relative_to(t.REPO)),
            "p4b_json_sha256": p4.sha256(out / "p4b.json"), "record_commit": r["inputs"]["commit"], "units": "ft, lb, h, in",
            "label": "from the record; geometry, balance and weights only, no flow solution"}
    for name in FIGURES:
        (folder / f"{name}.json").write_text(json.dumps(dict(side, figure=f"{name}.png"), indent=1))


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def report_text(out):
    r = load(out)
    i, ch, sel, cand = r["inputs"], r["choices"], r["selection"], r["candidates"]
    cols = columns(r)
    M = [cand[k]["measures"] for _, k in cols]
    head = ["Quantity"] + [h for h, _ in cols]
    row = lambda name, fn: [name] + [fn(v) for v in M]
    shaft = r["shaft_lb_per_ft"]
    tube = r["shaft_tube_support"]
    w = []
    w += [f"# Task 12 preliminary design P4b: tail and aft-body layout trade", "",
          f"Generated by `python -m prelim.p4b_trade --report-only` from `{i['excluded']}/p4b.json`. Every number below is read from that record. "
          "This is a follow-up to P4 (`docs/validation/2026-11-27_task12_pd_p4.md`) and its decision PD-20; the result is decision PD-21 "
          "(`docs/specs/00_decisions.md` section 9). The choices and the selection rule are in `data/task12/pd_p4b_choices.yaml`, written before any run; "
          f"nothing was tuned. r0 (`{r['baseline']}`) and the P4 record were read and not changed: what is found here is a finding for the closing re-record r1 (PD-7).", "",
          f"Evidence class: **{r['evidence_class']}**.", "",
          f"**In short:** the rule chooses **{r['chosen_label']}** ({sel['reason']})." if sel["chosen"] else f"**In short:** {sel['reason']}.", ""]
    if sel["chosen"]:
        v, a = cand[sel["chosen"]]["measures"], cand["A"]["measures"]
        w += [f"Against PD-20 (A) the chosen layout has a fuselage {v['extension_ft']:.2f} ft longer, a tail arm of {v['arm_ft']:.2f} ft against {a['arm_ft']:.2f} ft, a tailplane of "
              f"{v['ht_area_ft2']:.1f} ft^2 against {a['ht_area_ft2']:.1f} ft^2, an empty-weight change of {v['empty_weight_change_lb']:+.1f} lb against {a['empty_weight_change_lb']:+.1f} lb, "
              f"{v['drag_and_hours']['with_empty_weight_change']['delta_hours']:+.2f} h on station against {a['drag_and_hours']['with_empty_weight_change']['delta_hours']:+.2f} h, "
              f"{v['rotation_used_of_limit']:.3f} of the tail-lift limit at rotation against {a['rotation_used_of_limit']:.3f}, and {v['propeller_clearance_in']:.1f} in of propeller ground "
              f"clearance against {a['propeller_clearance_in']:.1f} in. No layout flies with the payload off without ballast; the chosen one needs "
              f"{v['payload_off']['ballast_every_loading_lb']:.0f} lb at the payload station.", ""]
    w += ["## 1. Run", "",
          f"- Commit `{i['commit']}`, clean tree: {not i['git_dirty']}; tree unchanged during the run: {i['tree_unchanged_during_run']}. Command: `{i['command']}`. Runtime {r['runtime_s']:.0f} s. No random numbers.",
          f"- Python {i['python']}, numpy {i['numpy']}, scipy {i['scipy']}, matplotlib {i['matplotlib']}. Input files and their sha256 are in the record (`inputs.files`).",
          f"- r0: take-off weight {f(r['r0']['W0_lb'], 1)} lb, fuel {f(r['r0']['fuel_lb'], 1)} lb, fuselage {f(r['r0']['fuselage']['length'])} ft, tail arm {f(r['r0']['tail_arm_ft'])} ft, "
          f"propeller plane at {f(r['r0']['propeller_plane_x_ft'])} ft, CD0 at the mission altitude {r['r0']['drag_and_hours']['CD0_mission_altitude']:.6f}, "
          f"{f(r['r0']['drag_and_hours']['hours_on_station'])} h on station by this package's route (unchanged areas).",
          f"- Shaft: **assumed** {shaft['value']:g} lb/ft, band {shaft['band'][0]:g} to {shaft['band'][1]:g} lb/ft. Support, not a test target: the record's power at "
          f"{r['ledger']['propeller_rpm']:g} rpm is a torque of {f(tube['torque_lb_ft'], 1)} lb ft; a steel tube {ch['extension']['shaft_tube_for_support']['outer_diameter_in']:g} in across "
          f"with a {ch['extension']['shaft_tube_for_support']['wall_in']:g} in wall weighs {f(tube['weight_lb_per_ft'], 2)} lb/ft and carries {f(tube['shear_stress_psi'], 0)} psi of shear "
          f"against {f(tube['allowable_over_safety_factor_psi'], 0)} psi allowed.", ""]
    w += ["## 2. The layouts", ""] + [f"- **{k}**: {ch['candidates'][k]}" for k in ("A", "B", "Bs", "C")]
    w += [f"- Placement: {ch['candidates']['placement']}.", f"- Arm scan: {ch['candidates']['arm_scan_points']} tail arms from PD-20's to r0's, straight trailing edges. "
          f"In this record Bs is row {r['named']['Bs'][5:] if r['named']['Bs'] else '-'} and C is row {r['named']['C'][5:] if r['named']['C'] else '-'}.", ""]
    if r["unsolved"]:
        w += ["Not solved: " + "; ".join(f"{k}: {v}" for k, v in r["unsolved"].items()) + ".", ""]
    w += ["## 3. The selection rule (written before the comparison)", "", f"Pool: {ch['selection_rule']['pool']}.", ""] + [f"- {s}" for s in ch["selection_rule"]["steps"]]
    w += [f"- Sensitivity: {ch['selection_rule']['sensitivity']}.", ""]
    w += ["## 4. Comparison", "", f"![plan sketches](figures/{STEM}/layouts.png)", ""]
    dh = lambda v, case, key: v["drag_and_hours"][case][key]
    rows = [row("tail arm, ft", lambda v: f(v["arm_ft"])), row("tailplane / fin area, ft^2", lambda v: f"{f(v['ht_area_ft2'], 2)} / {f(v['vt_area_ft2'], 2)}"),
            row("trailing edges", lambda v: "straight" if v["straight_trailing_edges"] else "as r0"),
            row("wing leading edge from r0's, ft", lambda v: sg(v["wing_shift_ft"])), row("fuselage extension, ft", lambda v: f(v["extension_ft"])),
            row("fuselage length, ft", lambda v: f(v["fuselage_length_ft"])), row("main wheels, ft from the nose", lambda v: f(v["x_main_ft"])),
            row("**empty-weight change, lb**", lambda v: f"**{sg(v['empty_weight_change_lb'], 2)}**"),
            row("of which tailplane / fin, lb", lambda v: f"{sg(v['weight_changes_lb'].get('horizontal_tail', 0.0), 2)} / {sg(v['weight_changes_lb'].get('vertical_tail', 0.0), 2)}"),
            row("of which fuselage with shaft / shaft alone, lb", lambda v: f"{sg(v['weight_changes_lb'].get('fuselage', 0.0), 2)} / {f(v['shaft_lb'], 2)}"),
            row("of which flight controls, lb", lambda v: sg(v["weight_changes_lb"].get("flight_controls", 0.0), 2)),
            row("wetted area: tails / fuselage / total, ft^2", lambda v: f"{sg(v['added_wetted_ft2']['horizontal_tail'] + v['added_wetted_ft2']['vertical_tail'], 2)} / {sg(v['added_wetted_ft2']['fuselage'], 2)} / {sg(v['added_wetted_ft2']['total'], 2)}"),
            row("CD0 change at the mission altitude", lambda v: sg(dh(v, "at_r0_weight", "delta_CD0"), 6)),
            row("hours on station at r0's weight and fuel (change)", lambda v: f"{f(dh(v, 'at_r0_weight', 'hours_on_station'))} ({sg(dh(v, 'at_r0_weight', 'delta_hours'))})"),
            row("**hours with the empty-weight change too (change)**", lambda v: f"**{f(v['hours_for_rule'])}** ({sg(dh(v, 'with_empty_weight_change', 'delta_hours'))})"),
            row(f"propeller ground clearance at rotation, in (at least {r['ledger']['prop_clearance_in']:g})", lambda v: f(v["propeller_clearance_in"], 2)),
            row("same, tilted disc at the true plane, in", lambda v: f(v["propeller_clearance_tilted_disc_at_plane_in"], 2)),
            row(f"tail lift at rotation over the limit of {r['ledger']['tail_cl_max_rotation']:g}", lambda v: f(v["rotation_used_of_limit"])),
            row(f"largest tail lift coefficient in trim (limit {r['ledger']['tail_cl_max_trim']:g})", lambda v: f(v["trim_largest"])),
            row("static margin, full / empty fuel (R13: 0.05 to 0.15)", lambda v: f"{f(v['sm_full'], 4)} / {f(v['sm_empty'], 4)}"),
            row("static margin over all payload-on loadings", lambda v: f"{f(v['static_margin_payload_on'][0], 4)} to {f(v['static_margin_payload_on'][1], 4)}"),
            row("payload-on loadings outside the envelope", lambda v: f"{v['payload_on_outside_envelope']} of {v['payload_on_loadings']}"),
            row("nose-wheel load, payload on, % (5 to 20)", lambda v: f"{f(100 * v['nose_load_payload_on'][0], 1)} to {f(100 * v['nose_load_payload_on'][1], 1)}"),
            row("gear-down payload-on loadings outside the 8 to 15 % optimum", lambda v: str(v["nose_load_payload_on_outside_optimum"])),
            row("least tipback angle, payload on, all empty-weight factors, deg", lambda v: f(v["tipback_min_payload_on_deg"], 2)),
            row(f"largest overturn angle, payload on, deg (at most {r['ledger']['overturn_max_deg']:g})", lambda v: f(v["overturn_max_payload_on_deg"], 2)),
            row("rearmost tail point from the propeller plane, ft (tailplane / fin)", lambda v: f"{sg(v['tail_rearmost_behind_propeller_plane_ft']['horizontal_tail'])} / {sg(v['tail_rearmost_behind_propeller_plane_ft']['vertical_tail'])}"),
            ["row 9 on the loft (P3)"] + [cand[k].get("row9_on_the_loft", {}).get("verdict", "-") for _, k in cols],
            row("payload-off loadings outside the envelope", lambda v: f"{v['payload_off_outside_envelope']} of {v['payload_off_loadings']}"),
            row("nose-wheel load, payload off, %", lambda v: f"{f(100 * v['nose_load_payload_off'][0], 1)} to {f(100 * v['nose_load_payload_off'][1], 1)}"),
            row("aftmost payload-off centre of gravity from the main wheels, ft (+ behind)", lambda v: sg(v["payload_off"]["behind_main_wheels_ft"])),
            row("**ballast at the payload station for every payload-off loading, lb**", lambda v: f"**{f(v['payload_off']['ballast_every_loading_lb'], 0)}**"),
            row("loadings outside the envelope with that ballast", lambda v: f"{v['payload_off']['with_that_ballast']['outside_envelope']} of {v['payload_off']['with_that_ballast']['loadings']}"),
            row("ballast by P4's figure (aftmost loading only), lb", lambda v: f(v["payload_off"]["ballast_to_aft_limit_lb"], 0)),
            row("ballast only to bring the centre of gravity to the wheels, lb", lambda v: f(v["payload_off"]["ballast_to_main_wheels_lb"], 0)),
            row("tailplane area over wing area", lambda v: f(v["tailplane_over_wing_area"])),
            row("tailplane root leading edge behind the wing root trailing edge, ft", lambda v: f(v["tailplane_root_le_behind_wing_root_te_ft"], 2)),
            row("tail arm over fuselage length", lambda v: f(v["tail_arm_over_fuselage_length"]))]
    w += _table(head, rows) + [""]
    names = {"row1_R13": "row 1: R13 at the full-fuel and empty-fuel centre of gravity", "row3_envelope_payload_on": "row 3: every payload-on loading inside the envelope",
             "row4_nose_load_payload_on": "row 4: nose-wheel load 5 to 20 %, payload on", "rotation_tail_lift": "tail lift at rotation within the limit",
             "trim_tail_lift": "tail lift in trim within the limit", "overturn": "overturn angle", "propeller_ground_clearance": "propeller ground clearance at rotation",
             "tails_clear_of_disc": "tails 1.0 ft clear of the disc", "row3_envelope_payload_off": "row 3 with the payload off, no ballast",
             "row4_nose_load_payload_off": "row 4 with the payload off, no ballast"}
    w += ["### Rows, pass or fail", ""] + _table(["Row"] + [h for h, _ in cols] + ["counts in step"],
                                                 [[names[k]] + [f"**{v['rows'][k]}**" for v in M] + ["1" if k in t.PAYLOAD_ON_ROWS else "2"] for k in names])
    w += ["", "A failed row is reported, not tuned: " + ("; ".join(f"{t.label_of(k, r['named'], cand)} fails {', '.join(names[x] for x in v)}" for k, v in sel["failed_step_1"].items()) or "no layout fails a payload-on row") + ".", ""]
    w += ["## 5. The arm scan", "", f"![arm scan](figures/{STEM}/arm_scan.png)", "",
          f"Straight trailing edges, volume coefficients kept, shaft at {shaft['value']:g} lb/ft.", ""]
    w += _table(["row", "tail arm, ft", "tailplane, ft^2", "extension, ft", "wing shift, ft", "empty weight, lb", "hours (a)", "hours (b)", "rotation / limit", "propeller clearance, in", "ballast, lb", "all payload-on rows"],
                [[k[5:], f(cand[k]["measures"]["arm_ft"]), f(cand[k]["measures"]["ht_area_ft2"], 2), f(cand[k]["measures"]["extension_ft"]), sg(cand[k]["measures"]["wing_shift_ft"]),
                  sg(cand[k]["measures"]["empty_weight_change_lb"], 2), f(dh(cand[k]["measures"], "at_r0_weight", "hours_on_station")), f(cand[k]["measures"]["hours_for_rule"]),
                  f(cand[k]["measures"]["rotation_used_of_limit"]), f(cand[k]["measures"]["propeller_clearance_in"], 2), f(cand[k]["measures"]["payload_off"]["ballast_every_loading_lb"], 0),
                  "pass" if cand[k]["measures"]["eligible"] else "fail"] for k in r["arm_scan"]])
    w += ["", "Hours (a): r0's weight and fuel, the layout's wetted areas. Hours (b): the same with the take-off weight raised by the empty-weight change (the rule's number).", ""]
    w += ["## 6. Selection", "",
          f"- Step 1 leaves {len(sel['after_step_1'])} of {len(cand)} layouts. Step 2: {len(sel['passing_payload_off_without_ballast'])} pass with the payload off and no ballast"
          + (", so ballast does not rank the layouts." if not sel["passing_payload_off_without_ballast"] else "."),
          f"- Steps 3 and 4: **{r['chosen_label']}**" + (f", {f(sel['best_hours'])} h; tied within {ch['selection_rule']['hours_tie_h']:g} h: {len(sel['tied_on_hours'])}." if sel["chosen"] else "."),
          f"- By empty weight alone (not the rule) the least change in the pool is {min(((v['measures']['empty_weight_change_lb'], t.label_of(k, r['named'], cand)) for k, v in cand.items() if v['measures']['eligible']), default=(None, 'none'))[1]}.", "",
          "The shaft band:", ""]
    w += _table(["shaft, lb/ft", "chosen", "its empty-weight change, lb", "its hours (b)", "A: empty-weight change, lb", "A: hours (b)", "C at this shaft weight"],
                [[f"{s['shaft_lb_per_ft']:g}", s["chosen_label"], sg(s["table"][s["selection"]["chosen"]]["empty_weight_change_lb"], 2) if s["selection"]["chosen"] else "-",
                  f(s["table"][s["selection"]["chosen"]]["hours_for_rule"]) if s["selection"]["chosen"] else "-", sg(s["table"]["A"]["empty_weight_change_lb"], 2),
                  f(s["table"]["A"]["hours_for_rule"]), f"row {s['named']['C'][5:]} (arm {f(s['table'][s['named']['C']]['arm_ft'])} ft, {sg(s['table'][s['named']['C']]['empty_weight_change_lb'], 2)} lb)" if s["named"]["C"] else "-"]
                 for s in r["shaft_band"]]) + [""]
    if sel["chosen"]:
        v = cand[sel["chosen"]]["measures"]
        mw = v["payload_off"]["main_wheels_moved_for_payload_off"]
        w += ["## 7. Payload off and the main wheels", "",
              f"With the payload off the centre of gravity moves aft of the aft limit on every layout ({v['payload_off_outside_envelope']} of {v['payload_off_loadings']} loadings on the chosen one, "
              f"least static margin {f(v['payload_off']['static_margin_min'], 4)}). It also ends {sg(v['payload_off']['behind_main_wheels_ft'])} ft from the main wheels (positive: behind them). "
              f"Moving the main wheels cannot cure this: the aft limit of R13 is what is broken, and wheels moved aft to {f(mw['x_main_ft'])} ft for payload-off tipback would ask "
              f"{f(mw['rotation_used_of_limit'])} of the tail-lift limit at rotation and put up to {f(100 * mw['nose_load_payload_on_max'], 1)} % of the weight on the nose wheel with the payload on. "
              f"So the main wheels stay where the tipback rule puts them with the payload on, and flight without the payload carries ballast: "
              f"**{f(v['payload_off']['ballast_every_loading_lb'], 0)} lb at the payload station**, with which {v['payload_off']['with_that_ballast']['outside_envelope']} of "
              f"{v['payload_off']['with_that_ballast']['loadings']} loadings are outside the envelope, the nose-wheel load is {f(100 * v['payload_off']['with_that_ballast']['nose_load_min'], 1)} to "
              f"{f(100 * v['payload_off']['with_that_ballast']['nose_load_max'], 1)} % and the least tipback angle is {f(v['payload_off']['with_that_ballast']['tipback_min_deg'], 2)} deg "
              f"(the rule's {r['ledger']['tipback_angle_deg']:g} deg is set with the payload on; the rotation angle is {r['ledger']['rotation_angle_deg_pusher']:g} deg). "
              "This is an operating limit for P8.", ""]
    w += ["## 8. Findings for r1", ""] + [f"{n}. {x}" for n, x in enumerate(r["findings_for_r1"], 1)] + [""]
    w += ["## 9. Assumptions", ""] + [f"- {a}" for a in ASSUMPTIONS] + [""]
    w += ["## 10. What this does not show", "",
          "- No shaft was designed: no bearings, couplings, critical speed or torsional vibration. The per-foot weight is an assumption; the choice was repeated at its band ends (section 6).",
          "- No flow was solved. The tail behind a longer, slender tail cone, the propeller's inflow behind the tails and the slipstream are not modelled; the drag change is wetted area only.",
          "- The tail cone's structure, the tail roots on it, the engine's inlet and exhaust and the tail bumper are not drawn or sized.",
          "- The aircraft was not re-sized and r0 was not changed. Take-off, climb and the other requirement rows were not re-run at the heavier weight; that is r1's work (P9).",
          "- The methods' limits that P4 lists for PD-20 (lattice downwash at the tail, Multhopp's rule behind the wing, an isolated-surface tail lift slope) apply to every layout here; they bear least on the layouts with the tail far behind the wing.", ""]
    return "\n".join(w)

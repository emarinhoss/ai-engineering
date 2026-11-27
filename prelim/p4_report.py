"""Report and figures of preliminary design P4, generated from the record (OUT/p4.json).
No number is typed here: every value in the text is read from the record."""
import json
from pathlib import Path

from prelim import p4_balance as p4

STEM = "2026-11-27_task12_pd_p4"
FIGURES = ("cg_envelope", "fuselage_moment", "planform")
ASSUMPTIONS = [
    "Stations: r0's, with the payload and avionics where P3 put them (PD-19). Gear up, each gear's weight is at the mid-point of its stowed leg (P3).",
    "Fuel: in the inboard part of the P3 tank bay, between the spars, out to the span station that holds the needed volume over the usable fraction, in two tanks of equal volume a side; a part-full tank keeps the centre of a full one. Both tank orders are run.",
    "Empty-weight band (NR-14): every component weight times 0.95 or 1.05, fuel and payload unchanged, no re-size and no move of wing or gear.",
    "The centre of gravity is on the fuselage reference line, as in Stage 1; r0's height above the ground is kept.",
    "Multhopp's Fig. 8 is used as drawn (it is for aspect ratio 8, this wing's); t is the root chord; behind the wing the flow angle rises linearly to the tail's value at the tail's quarter mean chord and stays there.",
    "Only the fuselage is in the strip integral. The sponsons lie inside the wing chord, where the rule gives nothing; Multhopp's nacelle term is not applied; turret and spinner are left out.",
    "The neutral point solves Raymer (16.8) for zero; (16.9) as printed lacks a factor in its denominator (roadmap Appendix A).",
    "Propeller normal force: Ribner's charts for the Hamilton Standard 3155-6 with the side-force factor of the P6 representative blade and its blade angles. P6 failed its validation row 5, so the power-on rows carry no verdict. The downwash slope at the propeller is taken as the tail's.",
    "Trim and rotation are Stage 1's equations with P2's measured section moment. The rotation limit applies to loadings with the gear down, each at its own weight and at Stage 1's rotation speed; the trim limit applies to every loading.",
    "Row 5 uses Stage 1's own wing rule (mean of the full-fuel and empty-fuel static margins at 0.10 MAC) and tipback rule, so that r1 and this package place things the same way.",
    "PD-20: propeller clearance 1.0 ft (band 0.5 to 2.0 ft), a judgement; tail volume coefficients, aspect ratios and tapers kept; trailing edges made straight.",
    "Weights of the r1 layout: ratios of Raymer (15.47), (15.48), (15.49) on r0's component weights; the fin is weighed unswept, as Stage 1 weighs r0's; the aircraft is not re-sized.",
    "VSPAERO: fuselage as a thick body, wing and tails thin, no propeller, sponsons, turret or spinner; loiter Mach number; three mesh levels.",
    "A trial of the methods was run before the record. It changed two things, both before any recorded number: the rotation limit is applied with the gear down only (it had been applied to every loading), and PD-20 got straight trailing edges because its first form does not close. The first form is still solved in the record and shown in section 8.",
]


def load(out):
    return json.loads((Path(out) / "p4.json").read_text())


def f(v, n=3):
    return "-" if v is None else f"{v:,.{n}f}"


def sg(v, n=3):
    return "-" if v is None else f"{v:+,.{n}f}"


def write_figures(out, folder):
    """Three figures from the record, matplotlib only: the centre-of-gravity envelope, the fuselage strip integral
    and a plan sketch of the tail and the propeller disc."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from prelim import p4_methods as m
    out, folder = Path(out), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    r = load(out)
    c = p4.context()
    d, L = c["d"], c["L"]
    cases = (("r0 as P3 arranged it", r["as_arranged"]), ("r1 layout (PD-20)", r["r1"]["evaluation"]))
    # 1. envelope
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    for ax, (title, e) in zip(axes, cases):
        env = e["envelope"]
        for payload, gear, mark, col in ((True, "up", "o", "tab:blue"), (True, "down", "s", "tab:green"), (False, "up", "x", "tab:red")):
            rows = [q for q in e["loadings"] if q["payload_on"] == payload and q["gear"] == gear]
            ax.plot([q["x_cg_ft"] for q in rows], [q["weight_lb"] for q in rows], mark, ms=3, color=col,
                    label=f"payload {'on' if payload else 'off'}, gear {gear}")
        down = sorted((q for q in e["loadings"] if q["gear"] == "down" and q["payload_on"]), key=lambda q: q["weight_lb"])
        ax.plot([q["forward_limit_ft"] for q in down], [q["weight_lb"] for q in down], "k--", lw=1, label="forward limit, gear down (rotation)")
        ax.axvline(env["aft_limit_ft"], color="k", lw=1, label="aft limit (neutral point less 0.05 MAC)")
        ax.axvline(env["x_np_ft"], color="k", lw=1, ls=":", label="neutral point, power off")
        ax.axvline(e["layout"]["x_main"], color="gray", lw=1, ls="-.", label="main wheels")
        ax.set_title(title)
        ax.set_xlabel("centre of gravity, ft from the nose")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("weight, lb")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle("Task 12 P4: every loading of step 1 against the envelope (all tank orders and empty-weight factors)")
    fig.tight_layout()
    fig.savefig(folder / "cg_envelope.png", dpi=130)
    plt.close(fig)
    # 2. strip integral
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    G = m.figure8_integral(c["src"])
    for (title, e), col in zip(cases, ("tab:blue", "tab:orange")):
        lay, n = e["layout"], e["neutral_point"]
        x = np.linspace(0.0, c["body"].length, 1201)
        xm = 0.5 * (x[:-1] + x[1:])
        b = 2.0 * c["body"].lines(xm)[0]
        cr = d["wing"]["root_chord"]
        ahead = cr * (G((lay["x_le"] - np.minimum(x[:-1], lay["x_le"])) / cr) - G((lay["x_le"] - np.minimum(x[1:], lay["x_le"])) / cr)) / np.diff(x)
        te = lay["x_le"] + cr
        behind = np.where(xm > te, n["dah_da"] * np.minimum(1.0, (xm - te) / (n["x_ach_ft"] - te)), 0.0)
        dbda = ahead + behind
        axes[0].plot(xm, dbda, color=col, label=title)
        axes[1].plot(xm, 0.5 * np.pi * b ** 2 * dbda, color=col, label=f"{title}: sum {n['fuselage_moment']['total_ft3']:.1f} ft^3")
    axes[0].set_ylabel("d(beta)/d(alpha), strip mean")
    axes[1].set_ylabel("(pi/2) b^2 d(beta)/d(alpha), ft^2")
    axes[1].set_xlabel("station, ft from the nose")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("Task 12 P4: Multhopp's strip integral (NACA TM 1036 (3.7), Fig. 8) on the loft's width")
    fig.tight_layout()
    fig.savefig(folder / "fuselage_moment.png", dpi=130)
    plt.close(fig)
    # 3. plan sketch
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), sharey=True)
    x = np.linspace(1e-6, c["body"].length, 400)
    half = c["body"].lines(x)[0]
    xp, R = r["propeller_plane_x_ft"], r["propeller_disc_radius_ft"]
    for ax, (title, e) in zip(axes, cases):
        lay = e["layout"]
        model = p4.ac.build(p4.record_with_layout(d, L, lay), L, c["A"])
        ax.fill(np.concatenate([x, x[::-1]]), np.concatenate([half, -half[::-1]]), color="0.85")
        for name, col in (("wing", "tab:blue"), ("horizontal_tail", "tab:orange")):
            s = model[name]
            for sign in (1, -1):
                ax.plot([s.x_le, s.x_le + s.le_slope * s.half_span, s.x_le + s.le_slope * s.half_span + s.c_tip, s.x_le + s.c_root, s.x_le],
                        [0, sign * s.half_span, sign * s.half_span, 0, 0], color=col, lw=1.2)
        ax.plot([xp, xp], [-R, R], color="tab:red", lw=2, label="propeller disc")
        ax.axvline(xp - r["r1"]["clearance_ft"], color="tab:red", lw=0.8, ls=":", label="clearance line")
        ax.plot([lay["x_main"]] * 2, [-d["layout"]["gear_track"]["half_track_ft"], d["layout"]["gear_track"]["half_track_ft"]], "k^", ms=5, label="main wheels")
        ax.set_title(title)
        ax.set_aspect("equal")
        ax.set_xlabel("ft from the nose")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle("Task 12 P4: plan sketch from the record, geometry only, no flow solution")
    fig.tight_layout()
    fig.savefig(folder / "planform.png", dpi=130)
    plt.close(fig)
    side = {"made_by": "prelim/p4_report.py, matplotlib only", "record": str((out / "p4.json").relative_to(p4.REPO)),
            "p4_json_sha256": p4.sha256(out / "p4.json"), "record_commit": r["inputs"]["commit"], "units": "ft, lb",
            "label": "from the record; geometry and balance only, no flow solution"}
    for name in FIGURES:
        (folder / f"{name}.json").write_text(json.dumps(dict(side, figure=f"{name}.png"), indent=1))


def _row1_table(e, w):
    w("| Gear | Empty weight | Weight full / empty (lb) | CG full (ft) | CG empty (ft) | Static margin full | empty | Inside R13 |")
    w("|---|---|---|---|---|---|---|---|")
    for k, v in e["row1"].items():
        gear, fac = k.split("/")
        ok = "yes" if 0.05 <= v["sm_full"] <= 0.15 and 0.05 <= v["sm_empty"] <= 0.15 else "**no**"
        w(f"| {gear.replace('gear_', '')} | {fac.replace('empty_weight_', '')} | {f(v['weight_full_lb'], 1)} / {f(v['weight_empty_lb'], 1)} | {f(v['x_cg_full_ft'])} | "
          f"{f(v['x_cg_empty_ft'])} | {f(v['sm_full'], 4)} | {f(v['sm_empty'], 4)} | {ok} |")


def _envelope_table(e, w):
    env = e["envelope"]
    w("| Group | Loadings | Outside | Too far aft | Too far forward | CG range (ft) | Static margin range | Nose-wheel load, gear down | Outside 5-20 % | Outside 8-15 % | Least tipback angle (deg) | Largest overturn angle (deg) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|")
    groups = [(f"payload on, empty weight x{k}", v) for k, v in env["payload_on_by_empty_weight_factor"].items()]
    for name, g in groups + [("payload on, all", env["payload_on"]), ("payload off, all", env["payload_off"])]:
        w(f"| {name} | {g['loadings']} | {g['outside_envelope']} | {g['too_far_aft']} | {g['too_far_forward']} | {f(g['x_cg_min_ft'])} to {f(g['x_cg_max_ft'])} | "
          f"{sg(g['static_margin_min'], 4)} to {sg(g['static_margin_max'], 4)} | {100 * g['nose_load_min']:.1f} to {100 * g['nose_load_max']:.1f} % | "
          f"{g['nose_load_outside_limits']} | {g['nose_load_outside_optimum']} | {f(g['tipback_min_deg'], 2)} | {f(g['overturn_max_deg'], 2)} |")


def report_text(out):
    out = Path(out)
    r = load(out)
    i, a, r1 = r["inputs"], r["as_arranged"], r["r1"]
    e1, sols = r1["evaluation"], r1["solutions"]
    lay0, lay1 = a["layout"], e1["layout"]
    n0, n1 = a["neutral_point"], e1["neutral_point"]
    d = r["r0"]
    mac = d["wing"]["mac"]
    acc = {q["row"]: q for q in r["acceptance"]}
    rel = out.relative_to(p4.REPO)
    src = r["sources"]["reports"]
    T = []
    w = T.append
    b0, b1 = a["row1"]["gear_up/empty_weight_x1"], e1["row1"]["gear_up/empty_weight_x1"]
    vv = r["vspaero"]["verdict"]
    w("# Task 12 preliminary design P4: balance and longitudinal stability\n")
    w(f"Generated by `python -m prelim.p4_balance --report-only` from `{rel}/p4.json`. Every number below is read from that record. Spec: "
      "`docs/specs/task12_preliminary_design.md`, package P4 (method steps 1 to 4, acceptance rows 1 to 5), and decision PD-20 "
      "(`docs/specs/00_decisions.md` section 9). Tolerances are the spec's or were fixed in `tests/task12_pd/test_p4_methods.py` before the run; "
      f"nothing was tuned. r0 (`{r['baseline']}`) was read and not changed: what P4 finds is listed in section 9 for the closing re-record r1 (PD-7).\n")
    w(f"Evidence class: **{r['evidence_class']}**.\n")
    failed = [str(q["row"]) for q in r["acceptance"] if q["verdict"] == "fail"]
    w(f"**In short:** on r0 as P3 arranged it the static margin is {f(b0['sm_full'], 4)} with full fuel and {f(b0['sm_empty'], 4)} with none, against R13's 0.05 to 0.15; "
      f"rows {', '.join(failed)} fail and are reported, not tuned. The independent neutral point is {sg(n0['difference_mac'], 4)} MAC from Stage 1's (row 2 "
      f"{acc[2]['verdict']}). Moving the wing {sg(sols['wing_alone_r0_tail']['layout']['x_le'] - lay0['x_le'])} ft restores R13 with r0's tail, but that tail is still inside "
      f"the propeller disc. With the tail clear of the disc (PD-20) the wing moves {sg(lay1['x_le'] - lay0['x_le'])} ft, the tail arm goes from {f(lay0['arm'])} to "
      f"{f(lay1['arm'])} ft and the tailplane from {f(lay0['ht_area'], 1)} to {f(lay1['ht_area'], 1)} ft^2; the static margin is then {f(b1['sm_full'], 4)} and "
      f"{f(b1['sm_empty'], 4)}, and {e1['envelope']['payload_on']['outside_envelope']} of {e1['envelope']['payload_on']['loadings']} loadings with the payload on are outside the envelope. "
      f"With the payload off {e1['envelope']['payload_off']['outside_envelope']} of {e1['envelope']['payload_off']['loadings']} are.\n")

    w("## 1. Run\n")
    w(f"- Command: `{i['command']}`")
    w(f"- Commit `{i['commit']}`; working tree at the start: {'clean' if not i['git_dirty'] else 'DIRTY'} (the run's own folder `{i['excluded']}` is not counted); "
      f"unchanged during the run: {'yes' if i['tree_unchanged_during_run'] else 'NO'}.")
    w(f"- Seed: none ({i['seed_note']}). python {i['python']}, numpy {i['numpy']}, scipy {i['scipy']}, pyyaml {i['pyyaml']}, matplotlib {i['matplotlib']}."
      + (f" OpenVSP {r['vspaero']['result']['openvsp']}, {r['vspaero']['result']['vspaero_version']} for step 3 (interpreter `{r['openvsp_python']}`, a session scratchpad, PD-14)."
         if vv.get("run") else " Step 3 was not run."))
    w("- Inputs (sha256, first 12): " + "; ".join(f"`{i['files'][k]}` {i['sha256'][k][:12]}" for k in i["files"]) + ".")
    w(f"- Log: `{rel}/run.log`. Run time {r['runtime_s']:.0f} s.")
    w("- Sources opened on ntrs.nasa.gov in this session (PDFs not committed): " + "; ".join(
        f"{s['number']}, \"{s['title']}\", {s['author']}, NTRS {s['ntrs_id']}, {s['url']}, sha256 {s['pdf_sha256'][:12]}, {s['pdf_pages']} pages" for s in src.values())
      + ". Pages, equations as read and both readings of each figure: `data/task12/pd_p4_sources.yaml`.\n")

    w("## 2. Acceptance rows\n")
    w("Rows 1 to 4 are judged on r0 with the P3 arrangement. Row 5 is the answer to their failures and is judged by repeating rows 1, 3 and 4 on the layout it gives.\n")
    w("| Row | What | Key number | Verdict |")
    w("|---|---|---|---|")
    env0, env1 = a["envelope"], e1["envelope"]
    w(f"| 1 | {acc[1]['what']} | {f(b0['sm_full'], 4)} full, {f(b0['sm_empty'], 4)} empty (gear up, nominal empty weight); power on at loiter "
      f"{f(b0['power_on']['loiter']['sm_full'], 4)} and {f(b0['power_on']['loiter']['sm_empty'], 4)} | **{acc[1]['verdict']}** |")
    w(f"| 2 | {acc[2]['what']} | independent {f(n0['independent_power_off_ft'])} ft, Stage 1 {f(n0['stage1_method_ft'])} ft: {sg(n0['difference_mac'], 4)} MAC | **{acc[2]['verdict']}** |")
    w(f"| 3 | {acc[3]['what']} | payload on: {env0['payload_on']['outside_envelope']} of {env0['payload_on']['loadings']} outside; payload off: "
      f"{env0['payload_off']['outside_envelope']} of {env0['payload_off']['loadings']} outside | **{acc[3]['verdict']}** |")
    w(f"| 4 | {acc[4]['what']} | payload on {100 * env0['payload_on']['nose_load_min']:.1f} to {100 * env0['payload_on']['nose_load_max']:.1f} % "
      f"({env0['payload_on']['nose_load_outside_limits']} outside); payload off {100 * env0['payload_off']['nose_load_min']:.1f} to "
      f"{100 * env0['payload_off']['nose_load_max']:.1f} % ({env0['payload_off']['nose_load_outside_limits']} outside) | **{acc[4]['verdict']}** |")
    w(f"| 5 | {acc[5]['what']} | wing leading edge {f(lay0['x_le'])} to {f(lay1['x_le'])} ft ({sg(lay1['x_le'] - lay0['x_le'])} ft); on that layout row 1 "
      f"{acc[5]['on_the_r1_layout']['1']}, row 3 {acc[5]['on_the_r1_layout']['3_payload_on']} with the payload on and {acc[5]['on_the_r1_layout']['3_all']} with it off, "
      f"row 4 {acc[5]['on_the_r1_layout']['4_payload_on']} with the payload on and {acc[5]['on_the_r1_layout']['4_all']} with it off | **{acc[5]['verdict']}** |")
    w("")
    w(f"- Rows 3 and 4 fail on both layouts with the payload off: {f(d['payload_lb'], 0)} lb leave the nose and the centre of gravity goes behind the main wheels "
      f"(section 6). PD-13 already treats payload-off flight as an operating limit; this package gives the limit a number (ballast, section 6).")
    w(f"- Row 2's evidence class: independent of Stage 1 in the fuselage term only; the wing and tail lift slopes and the downwash are shared.\n")

    w("## 3. Weight and balance (step 1)\n")
    w("Stations of the empty items, ft from the nose. The r1 column is the layout of section 8.\n")
    w("| Item | Weight r0 (lb) | Station, gear down | Station, gear up | Weight r1 layout (lb) | Station r1, gear down | gear up |")
    w("|---|---|---|---|---|---|---|")
    for k in a["items"]["down"]:
        w(f"| {k.replace('_', ' ')} | {f(a['items']['down'][k][0], 2)} | {f(a['items']['down'][k][1])} | {f(a['items']['up'][k][1])} | "
          f"{f(e1['items']['down'][k][0], 2)} | {f(e1['items']['down'][k][1])} | {f(e1['items']['up'][k][1])} |")
    w(f"| payload | {f(d['payload_lb'], 2)} | {f(lay0['payload_x'])} | {f(lay0['payload_x'])} | {f(d['payload_lb'], 2)} | {f(lay1['payload_x'])} | {f(lay1['payload_x'])} |")
    w(f"| empty weight | {f(a['empty_weight_lb'], 2)} | | | {f(e1['empty_weight_lb'], 2)} | | |")
    w("")
    tk = r["tanks"]
    w(f"- **Fuel on the loft.** Between the spars at {tk['spar_fractions'][0]:.2f} and {tk['spar_fractions'][1]:.2f} of the chord; the section area between them has its "
      f"centre at {f(tk['centre_chord_fraction'], 4)} of the chord (NACA 4415). The fuel needs {f(tk['gross_ft3_per_side'], 2)} ft^3 a side of the "
      f"{f(tk['available_gross_ft3_per_side'], 2)} ft^3 the bay has. Tanks, inboard first: "
      + "; ".join(f"span {f(t['y_from_ft'], 2)} to {f(t['y_to_ft'], 2)} ft, {f(t['gross_ft3_per_side'], 2)} ft^3, centre {f(t['centre_behind_root_le_ft'])} ft behind the root leading edge"
                  for t in tk["tanks"])
      + f". Stage 1 puts all fuel at 0.40 of the mean chord, {f(0.40 * mac)} ft behind the leading edge.")
    w(f"- {len(a['loadings'])} loadings: fuel in {r['choices']['balance']['fuel_steps']} steps x 2 tank orders x payload on and off x gear up and down x empty weight at "
      f"{', '.join(f'{q:g}' for q in r['choices']['balance']['empty_weight_factors'])} of r0's. All are in the record (`as_arranged.loadings`).\n")
    w("Centre of gravity at the fuel ends, payload on (tank order does not change the ends):\n")
    _row1_table(a, w)
    w("")
    w(f"- Gear up moves the centre of gravity forward (the main legs fold forward and weigh more than the nose leg, which folds aft). P3's rough figure "
      f"(0.073 full, 0.030 empty) used Stage 1's neutral point, Stage 1's fuel station and the gear down; with Stage 1's neutral-point method this package gives "
      f"{f(b0['stage1_method']['sm_full'], 4)} and {f(b0['stage1_method']['sm_empty'], 4)} gear up.\n")

    w("## 4. Neutral point (step 2)\n")
    w("| Route | Neutral point (ft from the nose) | Fraction of the mean chord behind its leading edge | Against Stage 1 (MAC) |")
    w("|---|---|---|---|")
    x_mac_le = n0["x_ac_ft"] - 0.25 * mac
    routes = [("Stage 1 (r0 record, Raymer (16.9) with (16.22))", d["layout"]["x_np"]),
              ("Stage 1's method recomputed here", n0["stage1_method_ft"]),
              ("independent: Multhopp's strip integral on the loft, power off", n0["independent_power_off_ft"])]
    routes += [(f"independent, power on, {k.replace('_', ' ')} (no verdict)", v["x_np_ft"]) for k, v in n0["power_on"].items()]
    if vv.get("run"):
        routes += [(f"VSPAERO {k} ({lv['mesh']['panels']} panels)" + ("" if lv["valid"] else ", rejected"), lv["x_np_ft"]) for k, lv in r["vspaero"]["result"]["levels"].items()]
    for name, x in routes:
        w(f"| {name} | {f(x)} | {f((x - x_mac_le) / mac, 4)} | {sg((x - d['layout']['x_np']) / mac, 4)} |")
    w("")
    fm = n0["fuselage_moment"]
    w(f"- **Fuselage term.** (1/q) dM/d(alpha) = (pi/2) integral of b^2 d(beta)/d(alpha) dx (NACA TM 1036 (3.7), p. 11) over {r['choices']['neutral_point']['strips']} strips of the "
      f"loft's width: {f(fm['ahead_of_wing_ft3'], 1)} ft^3 ahead of the wing, 0 over the root chord, {f(fm['behind_wing_ft3'], 1)} ft^3 behind it, "
      f"{f(fm['total_ft3'], 1)} ft^3 in all. Over S c that is C_m_alpha = {f(n0['Cma_fus_multhopp_per_rad'], 4)} per rad against {f(n0['Cma_fus_raymer_16_22_per_rad'], 4)} from Raymer's "
      f"(16.22) with the ledger's K_f: the fuselage moves the neutral point {sg(n0['shift_by_fuselage_multhopp_mac'], 4)} MAC by Multhopp and "
      f"{sg(n0['shift_by_fuselage_raymer_mac'], 4)} MAC by (16.22). The nose is long ahead of the wing ({f(lay0['x_le'] / d['wing']['root_chord'], 2)} root chords) and that is where "
      "the upwash acts.")
    w(f"- Shared with Stage 1: wing lift slope {f(n0['CLa_w'], 4)} per rad, tail term eta_h (S_h/S) C_L_alpha_h d(alpha_h)/d(alpha) = {f(n0['tail_term'], 4)}, "
      f"d(alpha_h)/d(alpha) = {f(n0['dah_da'], 4)} from the lattice.")
    alt = n0["upwash_alternatives"]
    s8, lat = alt["figure_8_excess_scaled_by_lift_slope"], alt["vortex_lattice_upwash"]
    w(f"- **Other readings of the upwash, no verdict.** Fig. 8's excess over 1 scaled by r0's lift slope over the figure's 4.5 (x{f(s8['scale'], 3)}): neutral point "
      f"{f(s8['x_np_ft'])} ft ({sg(s8['difference_from_verdict_route_mac'], 4)} MAC). The study's own vortex lattice on the centreline, {f(lat['height_of_axis_above_wing_plane_ft'], 2)} ft "
      f"above the wing plane: {f(lat['x_np_ft'])} ft ({sg(lat['difference_from_verdict_route_mac'], 4)} MAC). Integral of d(beta)/d(alpha) from the leading edge out to "
      + ", ".join(f"{x:g}" for x in lat["integral_at_chords_ahead"]) + " chords: Fig. 8 " + ", ".join(f(v) for v in lat["figure_8"])
      + "; lattice " + ", ".join(f(v) for v in lat["lattice"]) + ".")
    pr = n0["propeller"]
    w(f"- **Power on (no verdict).** Propeller normal force by NACA WR L-25: C_Y'psi = f C_Y'psi0, three blades; side-force factor of the P6 blade {f(pr['side_force_factor'], 1)} "
      f"by its (4), against 80.7 for the charted propeller. Raymer (16.8) with this force at the propeller plane ({f(n0['power_on']['loiter']['x_p_ft'], 2)} ft):\n")
    w("| Point | T_c | Blade angle at 0.75 R (deg) | f (Fig. 1) | C_Y'psi0 (Fig. 2) | Ratio (Fig. 6) | C_Y'psi | F_p_alpha/(q S) | Neutral point shift, r0 as arranged (MAC) | r1 layout (MAC) |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for k, p in pr["points"].items():
        w(f"| {k.replace('_', ' ')} | {f(p['T_c'], 4)} | {f(p['beta_at_075R_deg'], 2)} | {f(p['f'], 4)} | {f(p['CY_psi0_3155_6'], 4)} | {f(p['side_force_ratio'], 4)} | {f(p['CY_psi'], 4)} | "
          f"{f(n0['power_on'][k]['Fp_alpha_over_qS'], 5)} | {sg(n0['power_on'][k]['shift_mac'], 4)} | {sg(n1['power_on'][k]['shift_mac'], 4)} |")
    w("")
    w("- A propeller behind the centre of gravity is stabilising (Raymer p. 428). Not modelled: the slipstream on the tail (the tail is ahead of the propeller), the thrust "
      "line's moment (the hub is on the centreline in r0), blade angles other than the P6 blade's. Raymer p. 418 gives a loss of 4 to 10 % of static margin with power as typical of "
      "propeller aircraft; that allowance is not applied here.\n")

    w("## 5. VSPAERO (step 3, support)\n")
    if not vv.get("run"):
        w(f"**Not run:** {vv['reason']}.\n")
    else:
        res = r["vspaero"]["result"]
        w(f"{res['vspaero_version']} in OpenVSP {res['openvsp']}: the loft's fuselage as a thick body, the wing, tailplane and fin as thin surfaces; no propeller, sponsons, turret or "
          f"spinner. Mach {f(res['mach'], 4)} (loiter), angles of attack {res['alpha_sweep_deg'][0]:g} to {res['alpha_sweep_deg'][1]:g} deg in {res['alpha_sweep_deg'][2]} points, moment "
          f"reference at r0's full-fuel centre of gravity. Geometry is r0's (the layout of section 8 was not run).\n")
        w("| Level | Strips per wing section, points round a wing section, strips per fuselage section, points round the fuselage | Panels | C_L_alpha (per rad) | C_m_alpha (per rad) | Neutral point (ft) | Largest residual of the C_L and C_m lines |")
        w("|---|---|---|---|---|---|---|")
        for k, lv in res["levels"].items():
            w(f"| {k} | {', '.join(str(q) for q in lv['level'])} | {lv['mesh']['panels']:,} | {f(lv['CL_alpha_per_rad'], 4)} | {f(lv['Cm_alpha_per_rad'], 4)} | {f(lv['x_np_ft'])} | "
              f"{lv['CL_fit_max_residual']:.1e}, {lv['Cm_fit_max_residual']:.1e} |")
        w("")
        w(f"- Between the two finest meshes the neutral point moves {f(vv['change_mac'], 4)} MAC; the spec allows {p4.TOL_VSPAERO_MAC:g}. **{vv['note'].capitalize()}.**"
          + ("" if vv["converged"] else " The lift slope also keeps falling as the mesh is refined, so no level can be called the answer. As on 2026-11-24, VSPAERO with a fuselage "
             "in it is not mesh-robust on this aircraft, now with the fuselage as a body (NR-6 and NR-15 stay open in this part)."))
        w("")

    w("## 6. Centre-of-gravity envelope, nose-wheel load and ground angles (rows 3 and 4)\n")
    for title, e in (("r0 as P3 arranged it", a), ("the r1 layout of section 8", e1)):
        env = e["envelope"]
        w(f"**On {title}.** Aft limit {f(env['aft_limit_ft'])} ft (neutral point {f(env['x_np_ft'])} ft less 0.05 MAC). Forward limit by trim {f(env['forward']['trim_ft'])} ft "
          f"(tail lift coefficient {r['as_arranged']['trim']['limit']:g} at {env['forward']['trim_leg'].replace('_', ' ')}, C_L {f(env['forward']['trim_CL'], 3)}); by rotation, gear down, "
          f"{f(env['forward']['rotation_ft'])} ft at the take-off weight (tail lift coefficient {e['rotation']['limit']:g}). Main wheels at {f(e['layout']['x_main'])} ft.\n")
        _envelope_table(e, w)
        w("")
    po = e1["payload_off"]
    w(f"- **Payload off.** On the r1 layout the centre of gravity reaches {f(po['aftmost_loading']['x_cg_ft'])} ft (static margin {sg(po['aftmost_loading']['static_margin'], 4)}), "
      f"behind the main wheels at {f(lay1['x_main'])} ft: the aircraft would sit on its tail. Bringing that loading to the aft limit takes "
      f"{f(po['ballast_at_payload_station_lb'], 0)} lb at the payload station ({f(a['payload_off']['ballast_at_payload_station_lb'], 0)} lb on r0 as arranged). In practice the "
      "aircraft does not fly or stand without its payload or its weight in ballast; an operating limit for P8 (PD-13).")
    w(f"- **Tipback and overturn.** On r0 as arranged the main wheels are where r0 put them, and the aft centre of gravity has moved toward them: the least tipback angle "
      f"with the payload on is {f(env0['payload_on']['tipback_min_deg'], 2)} deg against {a['ground']['tipback_needed_deg']:g}. The r1 layout places the wheels by the rule again "
      f"({f(env1['payload_on_by_empty_weight_factor']['1']['tipback_min_deg'], 2)} deg at the nominal empty weight). Overturn, with r0's track: at most "
      f"{f(env0['payload_on']['overturn_max_deg'], 2)} deg and {f(env1['payload_on']['overturn_max_deg'], 2)} deg with the payload on ({a['ground']['overturn_limit_deg']:g} allowed).")
    w(f"- **Propeller clearance at rotation:** {f(a['ground']['propeller_clearance_in'], 2)} in on r0, {f(e1['ground']['propeller_clearance_in'], 2)} in on the r1 layout "
      f"({a['ground']['propeller_clearance_needed_in']:g} needed). Main wheels at {f(a['ground']['main_wheel_behind_root_le_over_root_chord'], 3)} and "
      f"{f(e1['ground']['main_wheel_behind_root_le_over_root_chord'], 3)} of the root chord behind the leading edge.")
    w(f"- **Nose-wheel load (item 31).** With the payload on it is inside 5 to 20 % everywhere. Against Raymer's 8 to 15 % optimum: {env0['payload_on']['nose_load_outside_optimum']} "
      f"gear-down loadings outside on r0 as arranged, {env1['payload_on']['nose_load_outside_optimum']} on the r1 layout (by empty-weight factor: "
      + ", ".join(f"x{k} {v['nose_load_outside_optimum']}" for k, v in env1["payload_on_by_empty_weight_factor"].items())
      + f"; largest {100 * env1['payload_on']['nose_load_max']:.1f} %).\n")
    w(f"![Centre-of-gravity envelope](figures/{STEM}/cg_envelope.png)\n")

    w("## 7. Trim and rotation with P2's section moment (step 4, item 25)\n")
    w(f"Section moment about the quarter chord: {f(r['cm0_p2'], 4)} measured (P2, `runs/task12/pd/2026-11-27/p2b`) against the ledger's {r['ledger_cm0']:g}; wing moment by Raymer "
      f"(16.16): {f(a['rotation']['p2_section_moment']['cm_wing'], 4)} against {f(a['rotation']['ledger_section_moment']['cm_wing'], 4)}.\n")
    w("| Layout | Forward CG, gear down (ft) | Tail C_L to rotate, P2's moment | with the ledger's moment | Limit | Used | Verdict | Largest tail C_L in trim on the mission | Limit | Verdict | Tail C_L at clean stall, forward CG (reported) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, e in (("r0 record", None), ("r0 as P3 arranged it", a), ("wing alone, r0's tail", r1["wing_alone_evaluation"]), ("r1 layout (PD-20)", e1)):
        if e is None:
            rr = d["layout"]["rotation"]
            w(f"| {name} | {f(min(d['layout']['cg_full'], d['layout']['cg_empty']))} | - | {f(rr['CL_tail_needed'], 4)} | {a['rotation']['limit']:g} | {f(abs(rr['CL_tail_needed']), 3)} | pass (Gate B) | - | - | - | - |")
            continue
        ro, tr = e["rotation"], e["trim"]
        w(f"| {name} | {f(ro['x_cg_ft'])} | {f(ro['p2_section_moment']['CL_tail_needed'], 4)} | {f(ro['ledger_section_moment']['CL_tail_needed'], 4)} | {ro['limit']:g} | "
          f"{f(ro['used_of_limit'], 3)} | **{ro['verdict']}** | {f(tr['largest'], 4)} | {tr['limit']:g} | **{tr['verdict']}** | {f(tr['clean_stall_forward_cg_reported']['CL_tail'], 4)} |")
    w("")
    w(f"- On r0 as arranged the rotation is easier than in the record only because the centre of gravity has moved toward the main wheels, which is the same thing as the lost "
      "tipback angle; it is not a gain. With the wheels back on the tipback rule the tail is again close to its limit, and P2's more negative section moment takes "
      f"{f(abs(e1['rotation']['p2_section_moment']['CL_tail_needed']) - abs(e1['rotation']['ledger_section_moment']['CL_tail_needed']), 4)} of it on the r1 layout.")
    w("- Not covered: trim with flaps down, ground effect, and the elevator's own limits; the tail lift limits are the ledger's judgements (0.5 in trim, 1.0 at rotation).\n")

    w("## 8. Row 5 and PD-20: the wing and the tail for r1\n")
    w(f"The propeller plane is at {f(r['propeller_plane_x_ft'])} ft and the disc radius is {f(r['propeller_disc_radius_ft'])} ft. On r0 the tailplane's root trailing edge is "
      f"{sg(a['tail_rearmost_behind_propeller_plane_ft']['horizontal_tail'])} ft and the fin's {sg(a['tail_rearmost_behind_propeller_plane_ft']['vertical_tail'])} ft from the plane "
      "(P3 row 9). Each form below is solved with the wing by Stage 1's rule (mean of the full-fuel and empty-fuel static margins 0.10 MAC, independent neutral point) and the "
      "main wheels by the tipback rule.\n")
    w("| Form | Clearance (ft) | Closes | Wing leading edge (ft) | Move (ft) | Tail arm (ft) | Tailplane (ft^2) | Fin (ft^2) | Main wheels (ft) | Tail C_L at rotation |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    names = {"wing_alone_r0_tail": "wing alone, r0's tail (row 5 as worded; the tail stays in the disc)",
             "r0_tail_planforms_clear_of_disc": "r0's tail planforms moved clear, volume coefficients kept (first form of PD-20)",
             "chosen": "**straight trailing edges, moved clear, volume coefficients kept (PD-20)**",
             "clearance_band_low": "the same at the low end of the clearance band", "clearance_band_high": "the same at the high end of the clearance band"}
    for k, s in sols.items():
        if not s["closed"]:
            w(f"| {names[k]} | {f(s['clearance_ft'], 1)} | **no** | - | - | - | - | - | - | - |")
            continue
        l = s["layout"]
        w(f"| {names[k]} | {f(s['clearance_ft'], 1)} | yes | {f(l['x_le'])} | {sg(l['x_le'] - lay0['x_le'])} | {f(l['arm'])} | {f(l['ht_area'], 2)} | {f(l['vt_area'], 2)} | "
          f"{f(l['x_main'])} | {f(s['CL_tail_rotation'], 4)} |")
    w("")
    first = sols["r0_tail_planforms_clear_of_disc"]
    w("**Why the first form does not close.** With r0's planforms (unswept leading edge, aspect ratio 4) the root chord runs far behind the tail's mean chord, so the tail must "
      "come forward a long way; keeping the volume coefficient then makes it larger, its root chord longer, and it must come forward again. The scan, wing shift by wing shift:\n")
    w("| Wing shift (ft) | Tail arm (ft) | Tailplane (ft^2) | Static margin full | empty | Tail C_L at rotation |")
    w("|---|---|---|---|---|---|")
    for q in first["scan"]:
        if "tail" in q:
            w(f"| {q['wing_shift_ft']:+.1f} | {q['tail']} | | | | |")
        else:
            w(f"| {q['wing_shift_ft']:+.1f} | {f(q['arm_ft'])} | {f(q['ht_area_ft2'], 1)} | {f(q['sm_full'], 4)} | {f(q['sm_empty'], 4)} | {f(q['CL_tail_rotation'], 4)} |")
    w("")
    best = max((q for q in first["scan"] if "tail" not in q), key=lambda q: 0.5 * (q["sm_full"] + q["sm_empty"]))
    w(f"- The mean static margin never reaches 0.10 (best {f(0.5 * (best['sm_full'] + best['sm_empty']), 4)} at {best['wing_shift_ft']:+.1f} ft, with a tailplane of "
      f"{f(best['ht_area_ft2'], 0)} ft^2 against a wing of {f(d['wing']['area'], 0)} ft^2), and the tail lift coefficient needed to rotate is "
      f"{f(min(abs(q['CL_tail_rotation']) for q in first['scan'] if 'tail' not in q), 3)} or more at every shift, against {a['rotation']['limit']:g}. "
      + ("" if first["closed"] else "**Reported as a failure of that form, not tuned.**"))
    w("- **The form chosen (PD-20).** The trailing edges of both tails are made straight (all the taper on the leading edge; area, aspect ratio and taper unchanged). The trailing "
      f"edge is then at the mean chord's own trailing edge, and the tail needs to come forward much less. Scan of this form at the chosen clearance:\n")
    w("| Wing shift (ft) | Tail arm (ft) | Tailplane (ft^2) | Static margin full | empty | Tail C_L at rotation |")
    w("|---|---|---|---|---|---|")
    for q in sols["chosen"]["scan"]:
        w(f"| {q['wing_shift_ft']:+.1f} | {f(q['arm_ft'])} | {f(q['ht_area_ft2'], 1)} | {f(q['sm_full'], 4)} | {f(q['sm_empty'], 4)} | {f(q['CL_tail_rotation'], 4)} |")
    w("")
    tp0, tp1 = a["tail_planforms"], e1["tail_planforms"]
    w0, w1 = lay0["weights"], lay1["weights"]
    w("**The r1 layout, against r0:**\n")
    w("| Quantity | r0 | r1 layout | Change |")
    w("|---|---|---|---|")
    rows = [("wing leading edge at the root (ft)", lay0["x_le"], lay1["x_le"], 3), ("wing aerodynamic centre (ft)", n0["x_ac_ft"], n1["x_ac_ft"], 3),
            ("tail arm (ft)", lay0["arm"], lay1["arm"], 3), ("tail arm over fuselage length", lay0["arm"] / d["fuselage"]["length"], r1["tail_arm_over_fuselage_length"], 4),
            ("tailplane area (ft^2)", lay0["ht_area"], lay1["ht_area"], 2), ("tailplane span (ft)", tp0["horizontal"]["span"], tp1["horizontal"]["span"], 2),
            ("tailplane root chord (ft)", tp0["horizontal"]["root_chord"], tp1["horizontal"]["root_chord"], 3),
            ("tailplane area over wing area", lay0["ht_area"] / d["wing"]["area"], lay1["ht_area"] / d["wing"]["area"], 3),
            ("tailplane root leading edge behind the wing's root trailing edge (ft)", a["tailplane_root_le_behind_wing_root_te_ft"], e1["tailplane_root_le_behind_wing_root_te_ft"], 2),
            ("fin area (ft^2)", lay0["vt_area"], lay1["vt_area"], 2), ("fin height (ft)", tp0["vertical"]["height"], tp1["vertical"]["height"], 2),
            ("main wheels (ft)", lay0["x_main"], lay1["x_main"], 3), ("nose wheel (ft)", lay0["x_nose"], lay1["x_nose"], 3),
            ("tailplane weight (lb)", w0["horizontal_tail"], w1["horizontal_tail"], 2), ("fin weight (lb)", w0["vertical_tail"], w1["vertical_tail"], 2),
            ("fuselage weight (lb)", w0["fuselage"], w1["fuselage"], 2), ("empty weight (lb)", a["empty_weight_lb"], e1["empty_weight_lb"], 2),
            ("neutral point, independent, power off (ft)", n0["independent_power_off_ft"], n1["independent_power_off_ft"], 3),
            ("d(alpha_h)/d(alpha) at the tail", n0["dah_da"], n1["dah_da"], 4), ("fuselage C_m_alpha, Multhopp (per rad)", n0["Cma_fus_multhopp_per_rad"], n1["Cma_fus_multhopp_per_rad"], 4),
            ("static margin, full fuel", b0["sm_full"], b1["sm_full"], 4), ("static margin, no fuel", b0["sm_empty"], b1["sm_empty"], 4)]
    for name, x0, x1, n in rows:
        w(f"| {name} | {f(x0, n)} | {f(x1, n)} | {sg(x1 - x0, n)} |")
    w("")
    r9 = r1["row9_on_the_loft"]
    w(f"- **Tail and fuselage weight, and where it comes from.** Stage 1's own equations as ratios on r0's component weights: tailplane by Raymer (15.47) (area to the 0.896, and its "
      f"quarter-chord sweep terms), fin by (15.48) (area to the 0.873, weighed unswept as Stage 1 weighs r0's), fuselage by the tail-arm term of (15.49) (arm to the -0.051; a "
      f"shorter arm makes Raymer's fuselage slightly heavier), p. 404: {sg(w1['horizontal_tail'] - w0['horizontal_tail'], 2)}, {sg(w1['vertical_tail'] - w0['vertical_tail'], 2)} and "
      f"{sg(w1['fuselage'] - w0['fuselage'], 2)} lb, {sg(e1['empty_weight_lb'] - a['empty_weight_lb'], 2)} lb in all. There is no boom: the tail stays on the fuselage. The aircraft was "
      "not re-sized; r1 does that.")
    w(f"- **On the loft.** The loft drawn with this layout has the tailplane {sg(r9['behind_plane_ft']['horizontal_tail'])} ft and the fin {sg(r9['behind_plane_ft']['vertical_tail'])} ft "
      f"from the propeller plane inside the disc (negative: ahead of it): P3's row 9 would **{r9['verdict']}**. `geometry3d/aircraft.py` now reads an optional leading-edge slope "
      "of a tail from the record; r0's record has none and its loft is unchanged (P3's tests).")
    w("- **Rows 1, 3 and 4 on this layout:**\n")
    _row1_table(e1, w)
    w("")
    hi, lo = sols["clearance_band_high"], sols["clearance_band_low"]
    w(f"- **Clearance band.** At {f(lo['clearance_ft'], 1)} ft the tailplane is {f(lo['layout']['ht_area'], 1)} ft^2 and the tail lift coefficient at rotation "
      f"{f(lo['CL_tail_rotation'], 4)}; at {f(hi['clearance_ft'], 1)} ft they are {f(hi['layout']['ht_area'], 1)} ft^2 and {f(hi['CL_tail_rotation'], 4)}, beyond the limit of "
      f"{a['rotation']['limit']:g}: the solution does not hold at the high end of the band. The clearance is a judgement and the answer is sensitive to it.")
    w(f"- **Stage 1's neutral point on this layout** would be {f(n1['stage1_method_ft'])} ft ({sg(-n1['difference_mac'], 4)} MAC behind the independent one): if r1 places the wing "
      "with (16.22), the static margin by this package's route is that much less than r1 will print.")
    w(f"- The tailplane is now {f(lay1['ht_area'] / d['wing']['area'], 2)} of the wing area ({f(lay0['ht_area'] / d['wing']['area'], 2)} in r0). It was already enlarged "
      f"{f(d['ht_volume_scale'], 3)} times over Raymer's Table 6.4 volume so that it can rotate the aircraft. Its root leading edge is {f(e1['tailplane_root_le_behind_wing_root_te_ft'], 2)} ft behind the wing's root "
      f"trailing edge ({f(a['tailplane_root_le_behind_wing_root_te_ft'], 2)} ft in r0). The downwash, the fuselage rule behind the wing and the tail's lift slope were not made for a "
      "tail this large and this close to the wing, so the margins of this layout are less certain than r0's were. A tail of this size is a cost of the pusher with its main wheels "
      "behind an aft centre of gravity; whether the configuration should carry it is beyond P4 (PD-3) and is put to Gate C through the findings.\n")
    w(f"![Plan sketch](figures/{STEM}/planform.png)\n")
    w(f"![Fuselage strip integral](figures/{STEM}/fuselage_moment.png)\n")

    w("## 9. Findings for r1\n")
    for k, t in enumerate(r["findings_for_r1"], 1):
        w(f"{k}. {t}")
    w("")
    w("## 10. Assumptions made where the spec left a choice\n")
    for k, t in enumerate(ASSUMPTIONS, 1):
        w(f"{k}. {t}")
    w("")
    w("## 11. What this does not show\n")
    w("- No flow solution of the fuselage. Multhopp's rule is the strip method of NACA TM 1036, checked by its author against seven aircraft (his Table I); its Fig. 8 was read from a scan.")
    w("- The r1 layout was not flown through Stage 1: weight, drag, fuel and tail loop are r0's. It is a set of findings, and r0 still has a tail in the propeller disc and a "
      "static margin outside R13 until r1 is made.")
    w("- No lateral or directional check of the larger, shorter-armed fin (PD-11); its volume coefficient is kept, nothing more.")
    w("- No check that the methods hold for the r1 layout's tail, which is large and close behind the wing (section 8).")
    w("- No dynamic stability, no control power beyond the two ledger limits, no flaps-down trim, no ground effect.")
    w("- The sponson was not resized (P3 finding 7), although the main wheels move; the tail roots now sit over the engine bay and no inlet, exhaust or structure is drawn there.")
    w("- VSPAERO's result is support only" + (" and did not converge." if vv.get("run") and not vv["converged"] else "."))
    w("- Power-on numbers rest on a representative blade whose blade-element validation failed (P6); they carry no verdict.")
    return "\n".join(T) + "\n"

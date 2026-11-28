"""Report and figures of preliminary design P5 (loads), generated from the record (OUT/p5.json).
No number is typed here: every value in the text is read from the record. Run on Opus 5.5 under ruling PD-22."""
import json
import math
from pathlib import Path

from prelim import p5_loads as p5

STEM = "2026-11-28_task12_pd_p5"
FIGURES = ("vn", "alleviation", "operating_limit")
ASSUMPTIONS = [
    "The second text is EASA CS-23 Amendment 4 (2015), not the FAA's 14 CFR Part 23: no FAA text could be opened from this environment (hosts and errors in section 1). That the two texts agree in 23.333 and 23.341 is not checked here.",
    "CS 23.341(c) takes the mean geometric chord (wing area over span) in the mass ratio; Stage 1 and Raymer (14.8) take the mean aerodynamic chord. Row 1 uses the text's chord as written and shows the other beside it. The lift slope in both is Stage 1's at the Mach number of the speed, as the record's `gusts` entries use it.",
    "The time integration is NACA Report 1206's model as printed: rigid aircraft, plunge only (no pitch), constant speed, level flight before the gust, wing lift only, gust uniform across the span; Wagner's and Kussner's functions for infinite aspect ratio, eq. (5) and (6), with the lift slope of the finite wing in the mass ratio; the one-minus-cosine gust of eq. (7) with H = 12.5 chords. The report says the infinite-aspect-ratio functions probably change the result by less than 5 %; no finite-aspect-ratio function was used.",
    "The alleviation factor is the largest acceleration over the gust divided by the quasi-steady sharp-edged value a_ns, as NACA Report 1206 eq. (8) defines it. The response is followed to 3H (37.5 chords) and sampled every 0.001 chord.",
    "The wing's negative maximum lift is 0.9 times P2's measured section value (set 2, Re 6 million, smooth, the lowest set that shows the negative stall) by Raymer (12.15), p. 270. The book states the rule for the positive stall; its use for the negative stall is an assumption.",
    "The negative manoeuvre envelope is Raymer Fig. 14.3, p. 337, and CS 23.333(b) for the normal category: the negative stall line down to -1.8 (R9), -1.8 to V_C, then a straight line to 0 at V_D. The positive side is the stall line capped at +3.8 up to V_D. V_D is Stage 1's, 1.5 V_C (Raymer p. 338).",
    "Weights are r0's nominal values. Zero-fuel weight is take-off weight less r0's fuel (the record's convention). Payload-off weights take off the 500 lb payload; the ballasted ones add P4b's ballast (the largest need over every payload-off loading of its chosen layout) at the payload station. The empty-weight band of the ledger (0.95 to 1.05) is not applied.",
    "The ruled gust rule (PD-8) holds U_de at 30 ft/s up to V_C at every altitude, falling to 15 ft/s at V_D and 15 ft/s above, in equivalent airspeed, as Stage 1 codes it. The operating limit is computed under that rule at the altitudes of the choices file; between two altitudes of the list it is not computed.",
    "Row 4 with the second text: U_de is interpolated linearly in speed between V_C and V_D (CS 23.333(c)(2)(i)) and the load factor follows from it; the text also says the load factors vary linearly between V_C and V_D, which differs slightly at the one point between them (the level top speed at 20,000 ft). Above V_D (the sea-level top speed) the V_D value, 25 ft/s, is held; the text does not cover speeds above V_D.",
    "The weight cost of row 4 is Stage 1 at r0's cell and loiter time with the ledger's positive limit load factor raised to the case's largest positive gust load factor at V_C and V_D. Stage 1 has no negative-load sizing, so the negative load factors carry no weight cost. The re-sized aircraft's other requirement rows were not checked.",
    "r1 findings: every weight raised by P4b's empty-weight change for its chosen layout, the wing unchanged; r0 is not re-sized. The plunge-only gust has no term for where the wing sits or how long the fuselage is.",
    "A trial of the code was run on 2026-11-28 before the record, after the sources and choices file was committed. It changed one thing: CS 23.335(a)(1)(i) (least design cruising speed), read from the same opened file, was added to the sources file and is reported as a finding. No tolerance, rule, weight or row was changed.",
]


def load(out):
    return json.loads((Path(out) / "p5.json").read_text())


def f(v, n=3):
    return "-" if v is None else f"{v:,.{n}f}"


def pct(v, n=2):
    return f"{100 * v:+.{n}f} %"


def write_figures(out, folder):
    """Three figures from the record, matplotlib only: the V-n diagram at sea level and 20,000 ft, the gust factor
    against mass ratio with three histories, and the payload-off operating limit."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    out, folder = Path(out), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    r = load(out)
    r0 = r["r0"]
    vc, vd = r0["V_C_kt"], r0["V_D_kt"]
    lim = r["row3"]["limits"]

    # V-n diagram
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    cases = [("takeoff", r["row3"]["manoeuvre"]["takeoff"], "C0"), ("zero_fuel", r["row3"]["manoeuvre"]["zero_fuel"], "C1"),
             ("payload_off_with_ballast", r["row5"]["cases"]["payload_off_with_ballast"]["manoeuvre"], "C2"),
             ("payload_off_no_ballast (hypothetical)", r["row5"]["cases"]["payload_off_no_ballast"]["manoeuvre"], "C3")]
    rho0 = 0.0023769
    for ax, alt in zip(axes, ("sea_level", "mission_altitude")):
        for name, m, col in cases:
            W_S = m["W_lb"] / r0["S_ft2"]
            V = np.linspace(0.0, vd, 400)
            Vf = V * 1.6878099
            pos = np.minimum(0.5 * rho0 * Vf ** 2 * m["CL_max"] / W_S, r0["limit_load_factor"])
            neg = np.where(V <= vc, np.maximum(0.5 * rho0 * Vf ** 2 * m["CL_neg"] / W_S, r0["negative_load_factor"]),
                           r0["negative_load_factor"] * (vd - V) / (vd - vc))
            ax.plot(V, pos, color=col, lw=1.2, label=f"manoeuvre, {name}")
            ax.plot(V, neg, color=col, lw=1.2)
            key = name.split(" ")[0]
            pts = [p for p in (r["row3"]["points"] if key in ("takeoff", "zero_fuel") else r["row5"]["cases"][key]["points"])
                   if p["altitude"] == alt and (key not in ("takeoff", "zero_fuel") or p["weight"] == key)]
            for p in pts:
                ax.plot([0, p["V_eas_kt"]], [1, p["n_up"]], color=col, lw=0.6, ls=":")
                ax.plot([0, p["V_eas_kt"]], [1, p["n_down"]], color=col, lw=0.6, ls=":")
                ax.plot(p["V_eas_kt"], p["n_up"], "o", color=col, ms=4)
                ax.plot(p["V_eas_kt"], p["n_down"], "s", color=col, ms=4)
        for y, txt in ((lim["positive"], "+3.8"), (lim["negative_gust"], "-1.7 (gust, with 0.1 g margin)"), (lim["negative_manoeuvre"], "-1.8")):
            ax.axhline(y, color="k", lw=0.7, ls="--")
            ax.text(2, y + 0.05, txt, fontsize=7)
        for x, txt in ((vc, "V_C"), (vd, "V_D")):
            ax.axvline(x, color="grey", lw=0.6)
            ax.text(x + 1, -3.4, txt, fontsize=8)
        ax.set_title(f"{'sea level' if alt == 'sea_level' else '20,000 ft'}: ruled gust rule (dots) and manoeuvre (lines)", fontsize=9)
        ax.set_xlabel("equivalent airspeed (kt)")
        ax.set_xlim(0, max(vd, r0["level_top_speed_kt"]["sea_level"]) + 5)
        ax.set_ylim(-3.6, 4.6)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("load factor n")
    axes[0].legend(fontsize=7, loc="center left")
    fig.suptitle("r0 V-n diagram (P5; from the record; not yet Fable-reviewed)", fontsize=10)
    fig.tight_layout()
    fig.savefig(folder / "vn.png", dpi=130)
    plt.close(fig)

    # gust factor
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    cur = r["gust_factor_curve"]
    a1.plot([x["mu"] for x in cur], [x["K_integrated"] for x in cur], "o-", label="time integration (NACA Rep. 1206 eq. (2), (5)-(7))")
    mus = np.linspace(1.5, 210, 300)
    a1.plot(mus, 0.88 * mus / (5.3 + mus), "k--", lw=1, label="Raymer (14.6) = NACA Rep. 1206 eq. (9)")
    for p in r["row2"]["points"]:
        a1.plot(p["mu"], p["K_integrated"], "r^", ms=7)
    a1.plot([], [], "r^", label="r0's four mass ratios")
    a1.set_xscale("log")
    a1.set_xlabel("mass ratio mu")
    a1.set_ylabel("gust factor K")
    a1.legend(fontsize=7)
    a1.grid(alpha=0.3)
    for mu, h in r["histories"].items():
        a2.plot(h["s"], h["y"], label=f"mu {float(mu):g}")
    a2.set_xlabel("penetration s (chords)")
    a2.set_ylabel("a_n / a_ns")
    a2.set_title("acceleration ratio histories, as NACA Rep. 1206 Fig. 1", fontsize=9)
    a2.legend(fontsize=7)
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(folder / "alleviation.png", dpi=130)
    plt.close(fig)

    # operating limit
    fig, ax = plt.subplots(figsize=(7, 5))
    for name, col in (("payload_off_with_ballast", "C2"), ("payload_off_no_ballast", "C3"), ("payload_off_full_fuel_with_ballast", "C4")):
        lim_ = r["row5"]["cases"][name]["operating_limit"]
        ax.plot([x["V_eas_kt"] for x in lim_], [x["altitude_ft"] for x in lim_], "o", color=col, label=name.replace("_", " "))
    ax.axvline(vc, color="grey", lw=0.8)
    ax.text(vc + 1, 1000, "V_C", fontsize=8)
    ax.axhline(23000, color="k", lw=0.6, ls="--")
    ax.text(60, 23300, "R12 23,000 ft", fontsize=8)
    ax.set_xlabel("largest EAS with the ruled gust inside +3.8 and -1.7 (kt; V_D where never reached)")
    ax.set_ylabel("altitude (ft)")
    ax.set_xlim(50, vd + 5)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(folder / "operating_limit.png", dpi=130)
    plt.close(fig)

    side = {"made_by": "prelim/p5_report.py, matplotlib only", "record": str((out / "p5.json").relative_to(p5.REPO)),
            "p5_json_sha256": p5.sha256(out / "p5.json"), "record_commit": r["inputs"]["commit"], "units": "kt EAS, ft, lb",
            "label": "from the record; analytic loads, no flow solution; not yet Fable-reviewed (ruling PD-22)"}
    for name in FIGURES:
        (folder / f"{name}.json").write_text(json.dumps(dict(side, figure=f"{name}.png"), indent=1))


def report_text(out):
    out = Path(out)
    r = load(out)
    i, r0, s = r["inputs"], r["r0"], r["sources"]
    cs, nc = s["cs23"], s["naca1206"]
    a1, a2, a3, a4, a5, r1 = r["row1"], r["row2"], r["row3"], r["row4"], r["row5"], r["r1"]
    T = []
    w = T.append
    w("# Task 12 preliminary design P5: loads (gust second source, negative manoeuvre, V-n diagram)")
    w("")
    w(f"**{r['review']}.** Run on Opus 5.5 under owner ruling PD-22 (`docs/specs/00_decisions.md` section 9); Fable reviews this diff before P9.")
    w("")
    w(f"Generated by `python -m prelim.p5_loads --report-only` from `{i['excluded']}/p5.json`. Every number below is read from that record. "
      f"Record made by `{i['command']}` at commit {i['commit'][:7]} from a clean tree (git_dirty {i['git_dirty']}; tree unchanged during the run: "
      f"{i['tree_unchanged_during_run']}); Python {i['python']}, numpy {i['numpy']}, scipy {i['scipy']}, matplotlib {i['matplotlib']}; no random numbers. "
      f"Baseline r0: `{r['baseline']}` (rebuilt and checked against its record). Spec: `docs/specs/task12_preliminary_design.md`, P5.")
    w("")
    w("## Acceptance")
    w("")
    w("| Row | What | Number | Tolerance | Evidence class | Verdict |")
    w("|---|---|---|---|---|---|")
    w(f"| 1 | CS 23.341(c) at Raymer's gust speed against r0's `gusts` (four points) | worst {pct(a1['worst_deviation'])} | ±{100 * a1['tolerance']:g} % | {a1['evidence_class']} | **{a1['verdict']}** |")
    w(f"| 2 | alleviation factor by time integration against (14.6) at r0's four mass ratios | worst {pct(a2['worst_deviation'])} | ±{100 * a2['tolerance']:g} % | {a2['evidence_class']} | **{a2['verdict']}** |")
    w(f"| 3 | ruled rule, take-off and zero-fuel weight: gust inside +3.8 and -1.7, manoeuvre inside +3.8 and -1.8 | largest {f(a3['worst_up']['n_up'])}, lowest {f(a3['worst_down']['n_down'])} | +3.8 / -1.7 | {a3['evidence_class']} | **{a3['verdict']}** |")
    c4, c4h = a4["cases"]["cs23_speeds"], a4["cases"]["ruled_held_30"]
    w(f"| 4 | CS-23 gust speeds; gust held at 30 ft/s above V_C | {f(c4['largest_up_all'])} / {f(c4['lowest_down_all'])}; {f(c4h['largest_up_all'])} / {f(c4h['lowest_down_all'])} | none | {a4['evidence_class']} | **{a4['verdict']}** |")
    op = a5["cases"][a5["operating_case"]]
    w(f"| 5 | payload off: load factors and operating limit | operating case {f(op['largest_up'])} / {f(op['lowest_down'])} | none | {a5['evidence_class']} | **{a5['verdict']}** |")
    w("")
    w("Every verdict follows from the numbers in the record; reported, not tuned. Rows 4 and 5 have no verdict by the spec.")
    w("")

    w("## 1. Sources")
    w("")
    w("**Step 1, the second text.** The FAA text of 14 CFR 23.333 and 23.341 before amendment 23-64 could not be opened. What was tried (2026-11-28, through the session proxy):")
    w("")
    w("| Host | URL | Result |")
    w("|---|---|---|")
    for b in s["blocked"]:
        w(f"| {b['host']} | `{b['url']}` | {b['result']} |")
    w("")
    w(f"The text used is {cs['document']}: `{cs['url']}` (page `{cs['page_url']}`), sha256 `{cs['pdf_sha256']}`, {cs['pdf_pages']} pages, not committed. {cs['why_this_one']}")
    w("")
    for k in ("gust_envelope", "gust_shape", "manoeuvre_envelope", "negative_manoeuvre_factor", "design_cruise_speed", "dive_speed", "gust_load_factor", "factor_of_safety"):
        w(f"- {cs[k]['paragraph']}: {cs[k]['as_read'].strip()}")
    w("")
    w(f"**Step 2, the source of the factor.** {nc['number']}, {nc['title']}, {nc['author']}, {nc['year']}: `{nc['url']}` (NTRS {nc['ntrs_id']}), sha256 `{nc['pdf_sha256']}`, {nc['pdf_pages']} pages, not committed; {nc['opened']}.")
    w("")
    w(f"- Plunge equation (2), {nc['equation_2']['page']}: {nc['equation_2']['as_read']}; {nc['equation_2']['a_ns']}; {nc['equation_2']['mu_g']}.")
    w(f"- Wagner, eq. {nc['wagner']['equation']}: phi(s) = 1 - {nc['wagner']['A'][0]} exp(-{nc['wagner']['b'][0]} s) - {nc['wagner']['A'][1]} exp(-{nc['wagner']['b'][1]} s), s in chords.")
    k = nc["kussner"]
    w(f"- Kussner, eq. {k['equation']}: psi(s) = 1 - {k['A'][0]} exp(-{k['b'][0]} s) - {k['A'][1]} exp(-{k['b'][1]} s) - {k['A'][2]} exp(-{k['b'][2]} s).")
    w(f"- Both are R. T. Jones's infinite-aspect-ratio functions (NACA Rep. 681) as NACA Report 1206 prints them; {nc['finite_aspect_ratio_note']}.")
    w(f"- Gust, eq. {nc['gust_shape']['equation']}: {nc['gust_shape']['as_read']}.")
    w(f"- Gust factor, eq. {nc['gust_factor']['equation']}: {nc['gust_factor']['as_read']}.")
    w("")
    w("**Library** (cited by number and page; no book text copied): Raymer (14.4)-(14.8), p. 339, as Stage 1 codes them (`conceptual/raymer_loads.py`); "
      "Raymer (12.15), p. 270; Raymer Fig. 14.3, p. 337; Anderson APD (6.54), p. 343, with Example 6.3, p. 344 (492.4 ft/s) as the corner-speed test. "
      "The book pages were not re-opened in this session: the Anderson PDF is not in the container and the Drive connector refused the download (file over 10 MB). "
      "The test of (6.54) recomputes the printed arithmetic.")
    w("")
    w("**The integration.** NACA Report 1206's eq. (2) with its exponential indicial functions turns into ordinary differential equations: the "
      "plunge velocity, one lag state per Wagner term and one per Kussner term (`prelim/p5_loads.plunge_history`). scipy's solve_ivp (DOP853, rtol 1e-10) "
      "integrates them on [0, 2H] and [2H, 3H]. Tests first (`tests/task12_pd/test_p5_loads.py`): with no lag the history equals its closed form to 1e-8; "
      f"the gust factor lies within {s['choices']['tolerances']['code_check_against_eq9_abs']} of eq. (9) from mass ratio 3 to 200 (the report's fit error 0.01 plus its "
      "solution error 0.005), and within 0.02 of the peaks of Fig. 1 read by eye at 3, 20 and 100.")
    w("")
    w("![alleviation](figures/" + STEM + "/alleviation.png)")
    w("")

    w("## 2. Row 1: the second text's formula at Raymer's gust speed")
    w("")
    w(f"CS 23.341(c) has the form of Raymer (14.4)-(14.8). The one difference in what it asks for is the chord: the mean geometric chord, {f(a1['mean_geometric_chord_ft'])} ft, "
      f"against Stage 1's mean aerodynamic chord, {f(a1['mean_aerodynamic_chord_ft'])} ft. U_de {f(r0['gust_ude_fps'], 0)} ft/s at V_C {f(r0['V_C_kt'], 1)} kt EAS.")
    w("")
    w("| Altitude | Weight | r0 `gusts` | CS-23, mean geometric chord | deviation | CS-23, mean aerodynamic chord | deviation |")
    w("|---|---|---|---|---|---|---|")
    for p in a1["points"]:
        w(f"| {p['altitude']} | {p['weight']} | {f(p['record'], 4)} | {f(p['cs23_mean_geometric_chord'], 4)} | {pct(p['deviation'])} | {f(p['cs23_mean_aerodynamic_chord'], 4)} | {pct(p['deviation_with_mac'], 4)} |")
    w("")
    w(f"Verdict **{a1['verdict']}** (worst {pct(a1['worst_deviation'])} against ±{100 * a1['tolerance']:g} %). With the same chord the two texts give the same number: this row shows that Stage 1 codes the rule's formula, and that the text's chord raises the load factor slightly. It does not test the physics.")
    w("")

    w("## 3. Row 2: the alleviation factor from the time integration")
    w("")
    w(f"Mass ratio by (14.8) with Stage 1's chord and lift slope at V_C; gust gradient H = {f(a2['H_chords'], 1)} chords.")
    w("")
    w("| Altitude | Weight | mu | K (14.6) | K integrated | deviation | peak at (chords) | n with (14.6) | n integrated |")
    w("|---|---|---|---|---|---|---|---|---|")
    for p in a2["points"]:
        w(f"| {p['altitude']} | {p['weight']} | {f(p['mu'])} | {f(p['K_14_6'], 4)} | {f(p['K_integrated'], 4)} | {pct(p['deviation'])} | {f(p['peak_at_chords'], 2)} | {f(p['n_14_6'])} | {f(p['n_integrated'])} |")
    w("")
    w(f"Verdict **{a2['verdict']}** (worst {pct(a2['worst_deviation'])} against ±{100 * a2['tolerance']:g} %). The integration re-derives the factor with the model it came from "
      "(rigid, plunge only, two-dimensional lift functions); agreement checks (14.6) and its use at these mass ratios, not the model. Pitch, wing flexibility, the tail and a finite-span lift build-up are not in it.")
    w("")

    w("## 4. Row 3: the ruled rule with the negative manoeuvre")
    w("")
    neg = r["negative_lift"]
    w(f"Negative maximum lift: section {f(neg['section_cl_min'], 3)} (P2, set {neg['section_set']}, Re {neg['section_reynolds'] / 1e6:g} million), wing {f(neg['wing_CL_neg_12_15'], 3)} by (12.15). Positive wing C_L,max {f(r0['CL_max_clean'], 2)} (r0).")
    w("")
    w("| Weight | W (lb) | positive corner (kt) | negative corner (kt) | negative stall at V_C | manoeuvre at V_C | manoeuvre at V_D |")
    w("|---|---|---|---|---|---|---|")
    for wl, m in a3["manoeuvre"].items():
        w(f"| {wl} | {f(m['W_lb'], 1)} | {f(m['positive_corner_kt'], 1)} | {f(m['negative_corner_kt'], 1)} | {f(m['negative_stall_at_V_C'])} | {f(m['positive_at_V_C'], 2)} / {f(m['negative_at_V_C'], 2)} | {f(m['positive_at_V_D'], 2)} / {f(m['negative_at_V_D'], 2)} |")
    w("")
    reach = all(m["negative_corner_below_V_C"] for m in a3["manoeuvre"].values())
    w("The negative stall line reaches -1.8 below V_C at both weights, so the negative manoeuvre limit is reachable and the structure must carry it." if reach
      else "The negative stall line does not reach -1.8 below V_C at every weight; there the negative manoeuvre is limited by stall.")
    w("")
    w("| Altitude | Speed | V EAS (kt) | U_de (ft/s) | Weight | n up | n down |")
    w("|---|---|---|---|---|---|---|")
    for p in a3["points"]:
        w(f"| {p['altitude']} | {p['speed']} | {f(p['V_eas_kt'], 1)} | {f(p['U_de_fps'], 1)} | {p['weight']} | {f(p['n_up'])} | {f(p['n_down'])} |")
    w("")
    w(f"Verdict **{a3['verdict']}**: largest {f(a3['worst_up']['n_up'])} ({a3['worst_up']['altitude']}, {a3['worst_up']['speed']}, {a3['worst_up']['weight']}), margin {f(a3['margin_up'])}; "
      f"lowest {f(a3['worst_down']['n_down'])}, margin {f(a3['margin_down'])} to -1.7. This repeats the Gate B check on r0 (the V_C points equal r0's `gusts`); the new part is the negative manoeuvre.")
    w("")
    w("![vn](figures/" + STEM + "/vn.png)")
    w("")

    w("## 5. Row 4: the second text's gust speeds, and the gust held at 30 ft/s (finding for O-2)")
    w("")
    L4 = a4["limits"]
    w(f"Limits: +{f(L4['positive_limit'], 1)} / {f(L4['negative_limit'], 1)}; ultimate (CS 23.303, factor 1.5) +{f(L4['positive_ultimate'], 2)} / {f(L4['negative_ultimate'], 2)}. No verdict (spec P5 row 4).")
    w("")
    for name, title in (("cs23_speeds", "CS 23.333(c) speeds (50 ft/s at V_C, 25 ft/s at V_D), CS 23.341(c) formula"), ("ruled_held_30", "ruled formula, gust held at 30 ft/s above V_C")):
        cse = a4["cases"][name]
        w(f"**{title}.**")
        w("")
        w("| Altitude | Speed | V EAS (kt) | U_de (ft/s) | Weight | n up | n down | beyond limit | beyond ultimate |")
        w("|---|---|---|---|---|---|---|---|---|")
        for p in cse["points"]:
            bl = ", ".join(x for x, y in (("positive", p["above_positive_limit"]), ("negative", p["below_negative_limit"])) if y) or "no"
            bu = ", ".join(x for x, y in (("positive", p["above_positive_ultimate"]), ("negative", p["below_negative_ultimate"])) if y) or "no"
            w(f"| {p['altitude']} | {p['speed']} | {f(p['V_eas_kt'], 1)} | {f(p['U_de_fps'], 1)} | {p['weight']} | {f(p['n_up'])} | {f(p['n_down'])} | {bl} | {bu} |")
        st = cse["stage1_raised"]
        w("")
        w(f"Weight cost (Stage 1 at L_sized {f(st['L_sized_h'], 2)} h with the positive limit raised to {f(st['limit_load_factor'])}): W0 {f(st['W0_lb'], 1)} lb "
          f"({cse['W0_change_lb']:+,.1f} lb), empty weight {cse['We_change_lb']:+,.1f} lb, of which structure {cse['structure_change_lb']:+,.1f} lb (wing {cse['wing_change_lb']:+,.1f} lb); "
          f"power within the engine: {st['power_ok']}. The negative values carry no weight cost: Stage 1 has no negative-load sizing.")
        w("")

    w("## 6. Row 5: payload off (NR-18) and the operating limit (PD-13)")
    w("")
    w(f"P4b found that no layout flies payload-off without ballast; its chosen layout ({a5['p4b_chosen']}) needs {f(a5['ballast_lb'], 0)} lb at the payload station. "
      f"So the **operating case** is payload off with that ballast; payload off without ballast is **hypothetical** (the aircraft is out of balance and is not flown that way).")
    w("")
    w("| Case | W (lb) | W/S (lb/ft^2) | largest n up (V_C, V_D) | lowest n down (V_C, V_D) | inside +3.8 / -1.7 | lowest listed altitude where the limit is below V_C (ft) |")
    w("|---|---|---|---|---|---|---|")
    for name, cse in a5["cases"].items():
        tag = " (operating case)" if name == a5["operating_case"] else (" (hypothetical)" if name == a5["hypothetical_case"] else "")
        w(f"| {name}{tag} | {f(cse['W_lb'], 1)} | {f(cse['W_S'], 2)} | {f(cse['largest_up'])} | {f(cse['lowest_down'])} | {cse['inside_at_V_C_V_D']} | {f(cse['lowest_altitude_limited_below_V_C_ft'], 0)} |")
    w("")
    w("Operating limit: the largest EAS at which the ruled gust stays inside +3.8 and -1.7 (V_D where no limit is reached).")
    w("")
    names = list(a5["cases"])
    w("| Altitude (ft) | " + " | ".join(names) + " |")
    w("|---|" + "---|" * len(names))
    for k in range(len(a5["cases"][names[0]]["operating_limit"])):
        cells = []
        for n in names:
            x = a5["cases"][n]["operating_limit"][k]
            cells.append(f"{f(x['V_eas_kt'], 1)}" + (f" ({x['limited_by']})" if x["limited_by"] else ""))
        w(f"| {f(a5['cases'][names[0]]['operating_limit'][k]['altitude_ft'], 0)} | " + " | ".join(cells) + " |")
    w("")
    w("![operating limit](figures/" + STEM + "/operating_limit.png)")
    w("")

    w("## 7. Operating limits found")
    w("")
    hyp = a5["cases"][a5["hypothetical_case"]]
    w(f"- Payload off is flown only with {f(a5['ballast_lb'], 0)} lb of ballast at the payload station (P4b). With it, at {f(op['W_lb'], 1)} lb, the ruled gust stays inside the limits at V_C and V_D at sea level and 20,000 ft "
      f"({f(op['largest_up'])} / {f(op['lowest_down'])}); the speed limit first falls below V_C at {f(op['lowest_altitude_limited_below_V_C_ft'], 0)} ft among the listed altitudes. For P8 (EP-9).")
    w(f"- Without the ballast ({f(hyp['W_lb'], 1)} lb, hypothetical) the ruled gust at V_C and V_D at sea level and 20,000 ft is {f(hyp['largest_up'])} / {f(hyp['lowest_down'])}, "
      + ("inside" if hyp["inside_at_V_C_V_D"] else "outside") + f" +3.8 / -1.7; the speed limit falls below V_C from {f(hyp['lowest_altitude_limited_below_V_C_ft'], 0)} ft among the listed altitudes.")
    allm = list(a3["manoeuvre"].values()) + [cse["manoeuvre"] for cse in a5["cases"].values()]
    w("- The negative manoeuvre limit -1.8 is " + ("reachable below V_C at every weight checked" if all(m["negative_corner_below_V_C"] for m in allm)
      else "not reachable below V_C at every weight checked") + "; P8's load-factor command limits (EP-5) must hold it.")
    w("")

    w("## 8. Findings for r1")
    w("")
    w(f"- r1's empty weight is {r1['empty_weight_change_lb']:+.2f} lb (PD-21, P4b). With every weight raised by it and the wing unchanged, row 3's largest gust goes from {f(r1['row3']['worst_up_r0'])} to {f(r1['row3']['worst_up_r1'])} "
      f"and the lowest from {f(r1['row3']['worst_down_r0'])} to {f(r1['row3']['worst_down_r1'])}; row 3 on r1's weights: {r1['row3']['verdict_r1']}.")
    rb = r1["row5_with_ballast"]
    w(f"- Payload off with ballast: {f(rb['W_r0'], 1)} lb on r0, {f(rb['W_r1'], 1)} lb on r1; largest gust {f(rb['largest_up_r0'])} to {f(rb['largest_up_r1'])}, lowest {f(rb['lowest_down_r0'])} to {f(rb['lowest_down_r1'])}.")
    w(f"- What r1 does not change here: {r1['not_changed_by_r1']}")
    w("- If O-2 adopts the second text's gust speeds, row 4's weight cost applies to r1 and is a re-size (PD-8).")
    w("")

    w("## 9. Other findings")
    w("")
    vcm = r["cs23_design_cruise_speed"]
    w(f"- CS 23.335(a)(1)(i) asks for a design cruising speed of at least {f(vcm['V_C_min_kt'], 1)} kt EAS at r0's wing loading; r0's V_C is {f(vcm['V_C_kt'], 1)} kt (R18, ruling B-4); the cap of (a)(3), 0.9 V_H at sea level, is {f(vcm['cap_0_9_V_H_kt'], 1)} kt. "
      f"By 23.335(b)(2)(i) V_D would be at least {f(vcm['V_D_min_kt'], 1)} kt against Stage 1's {f(vcm['V_D_kt'], 1)} kt. {vcm['note']}.")
    w(f"- CS 23.337(b)(1) asks the normal category for a negative manoeuvre factor of at least 0.4 times the positive, {f(-0.4 * r0['limit_load_factor'], 2)} here; R9's -1.8 (the utility value of Raymer Table 14.2) covers it.")
    w(f"- Under the second text's speeds the largest gust is {f(c4['largest_up_all'])} against the limit +{f(L4['positive_limit'], 1)} and ultimate +{f(L4['positive_ultimate'], 2)}, and the lowest {f(c4['lowest_down_all'])} against the limit {f(L4['negative_limit'], 1)} and ultimate {f(L4['negative_ultimate'], 2)}. "
      "The ruled rule's 30 ft/s is Raymer's (p. 339); the second text's value at V_C is 50 ft/s. This is the O-2 question; under PD-8 the ruled rule stands.")
    w("")

    w("## 10. Assumptions")
    w("")
    for a in ASSUMPTIONS:
        w(f"- {a}")
    w("")
    w("## 11. What this does not show")
    w("")
    w("- No pitch, flexibility, tail or continuous-turbulence (power-spectral) gust response; the formula and the integration are both plunge-only.")
    w("- No tail loads, balancing loads or load distribution (P7 takes the load factors to the spar).")
    w("- No negative-load sizing of the structure: Stage 1's weights use the positive ultimate factor only.")
    w("- The FAA text was not opened; CS-23 Amendment 4 stands in for it.")
    w("- Not yet Fable-reviewed (ruling PD-22).")
    w("")
    return "\n".join(T) + "\n"

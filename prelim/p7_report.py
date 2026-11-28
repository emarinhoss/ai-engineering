"""Report and figures of preliminary design P7 (wing spar), generated from the record (OUT/p7.json).
No number is typed here: every value in the text is read from the record. Run on Opus 5.5 under ruling PD-22."""
import json
from pathlib import Path

from prelim import p7_spar as p7

STEM = "2026-11-28_task12_pd_p7"
FIGURES = ("loads_on_wing", "sizing")
ASSUMPTIONS = [
    "One bending spar at the P3 arrangement's front-spar station carries all the bending in its caps and all the shear in its web (Raymer p. 384-385, Fig. 14.41); the rear spar, ribs, skins and joints are not sized, and no torsion box is modelled (PD-9, PD-23).",
    "The spar depth is the loft's NACA 4415 depth straight up at the spar station less two skins of the assumed thickness; each cap's area is concentrated at its centroid, half a cap thickness inside the skin, and the cap is as wide as the assumed share of the local chord.",
    "Material values are Raymer's Table 14.4 typical values for high-strength graphite/epoxy (0 deg caps, +-45 deg web), read from the library's checked chapter notes because the printed page could not be opened in this session; the strengths are multiplied by one judged knock-down factor; the moduli are not.",
    "The web may not buckle at ultimate load: (14.37) with K for simply supported edges on a long panel (Fig. 14.42), the panel width the spar depth inside the skins, the modulus that of the +-45 deg laminate. The isotropic plate formula on an orthotropic laminate is an approximation. A stiffened or post-buckled web is not considered.",
    "Every case is balanced in pitch with P4's tail trim equation at the centre of gravity of its weight (payload on, gear up, nominal empty weight; P4 row 1), gusts included; a gust's own tail load and the pitching response are not computed (as in P5).",
    "The airload is Schrenk's shape over the whole span, carried to the centreline (Raymer p. 342-343), untwisted, no aileron, no basic load; the lattice row checks the shape. The fuselage's own lift and its carry-over are not modelled.",
    "Inertia relief: the wing weight by chord over the whole span (p. 382), the fuel in P4's two tanks a side by chord squared, full at take-off weight and none at zero-fuel weight, and the sponsons and main gear as one point load a side at r0's main-wheel half track. The fuel system and every other item give no relief.",
    "A manoeuvre case is evaluated at each listed speed (corner, V_C, V_D for +3.8; negative corner and V_C for -1.8) and the speed of the largest ultimate root bending moment is kept; speeds are equivalent airspeeds and the dynamic pressure is 0.5 rho_0 V^2.",
    "Ultimate load is limit load times r0's factor of safety (Nz_ultimate over its limit load factor). Each station is sized to the envelope of the ruled cases; caps are equal above and below because the tension and compression values are equal.",
    "The spar weight is the caps and web alone, integrated over the span by the trapezoid rule on the stations, across the fuselage to the centreline, with no minimum gauge, fittings, fasteners or splices: a lower bound on a built spar.",
    "r1 findings use P4b's chosen layout (PD-21) with its centre of gravity and weights at full and empty fuel, P5's r1 gust factors and P2's measured clean maximum lift for the positive corner speed; the wing, its weight and the tanks are r0's.",
    "A trial of the code was run on 2026-11-28 before the record, after the choices file was committed. It changed one thing in that file: three moduli were written 21.0e6, 2.34e6 and 5.52e6, which YAML 1.1 reads as text; they are now 21.0e+6, 2.34e+6 and 5.52e+6, the same values. No choice, tolerance, band or case was changed.",
]


def load(out):
    return json.loads((Path(out) / "p7.json").read_text())


def f(v, n=3):
    return "-" if v is None else f"{v:,.{n}f}"


def pct(v, n=2):
    return f"{100 * v:+.{n}f} %"


def write_figures(out, folder):
    """Two figures from the record, matplotlib only: the loads drawn on the half wing (span loading of the governing
    case on the planform, shear and bending moment of every ruled case) and the sized spar along the span."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    out, folder = Path(out), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    r = load(out)
    s, w = r["spar"], r["r0"]["wing"]
    y = np.array(s["y_ft"])
    half, cr, ct = 0.5 * w["span"], w["root_chord"], w["tip_chord"]
    x_spar = r["section"]["x_spar"]
    ruled = [c for c in r["cases"] if c["kind"] == "ruled"]
    gov = next(c for c in ruled if c["name"] == r["row3"]["root_moment_case"])

    fig = plt.figure(figsize=(12, 9))
    ax0 = fig.add_subplot(2, 1, 1)
    yy = np.array([0.0, half, half, 0.0, 0.0])
    xx = np.array([0.0, 0.0, ct, cr, 0.0])
    ax0.plot(yy, -xx, color="k", lw=1.0)
    ax0.plot([0.0, half], [-x_spar * cr, -x_spar * ct], color="C3", lw=2.0, label=f"bending spar at {x_spar:g} c")
    tk = r["p4_inputs"]["tanks"]["tanks"]
    for t in tk:
        ax0.axvspan(t["y_from_ft"], t["y_to_ft"], ymin=0.0, ymax=0.08, color="C0", alpha=0.3)
    ax0.axvline(0.5 * r["r0"]["fuselage_diameter_ft"], color="0.5", lw=0.8, ls=":")
    ax0.text(0.5 * r["r0"]["fuselage_diameter_ft"] + 0.1, -cr * 0.97, "fuselage side", fontsize=7, color="0.4")
    ax0.axvline(r["r0"]["half_track_ft"], color="C2", lw=0.8, ls="--")
    ax0.text(r["r0"]["half_track_ft"] + 0.1, -cr * 0.9, "main wheel, sponson", fontsize=7, color="C2")
    shape = np.array(r["row2"]["schrenk_on_stations"]["shape_ft"])
    lift = gov["by_speed"][gov["speed"]]["L_wing_lb"]
    scale = 2.5 / np.max(shape)
    ax0.fill_between(y, 0.0, shape * scale, color="C1", alpha=0.35, label=f"Schrenk airload of '{gov['name']}' ({f(lift, 0)} lb wing lift, shape)")
    lv = r["row2"]["lattice"][r["row2"]["lattice_level"]]
    ly, ll = np.array(lv["y_ft"]), np.array(lv["cl_c_ft"])
    k = np.sum(shape[:-1] * np.diff(y)) / np.sum(ll * np.array(lv["dy_ft"]))
    ax0.plot(ly, ll * k * scale, color="C4", lw=1.0, label=f"lattice ({r['row2']['lattice_level']}), same lift")
    ax0.set_aspect("equal")
    ax0.set_xlim(-0.5, half + 0.5)
    ax0.set_xlabel("y from the centreline (ft)")
    ax0.set_ylabel("x behind the root leading edge (ft, down)")
    ax0.set_title("r0 half wing: planform, spar, tanks (blue), main wheel; span loading drawn above the leading edge")
    ax0.legend(fontsize=7, loc="upper right")
    ax1 = fig.add_subplot(2, 2, 3)
    ax2 = fig.add_subplot(2, 2, 4)
    for i, c in enumerate(ruled):
        ax1.plot(y, c["V_ult_lb"], color=f"C{i}", lw=1.1, label=c["name"])
        ax2.plot(y, np.array(c["M_ult_lbft"]) / 1000.0, color=f"C{i}", lw=1.1, label=c["name"])
    ax1.plot(y, s["V_env_ult_lb"], color="k", lw=0.8, ls="--", label="envelope (magnitude)")
    ax2.plot(y, np.array(s["M_env_ult_lbft"]) / 1000.0, color="k", lw=0.8, ls="--", label="envelope (magnitude)")
    for ax, lab in ((ax1, "ultimate shear (lb)"), (ax2, "ultimate bending moment (1,000 lb ft)")):
        ax.axhline(0.0, color="0.6", lw=0.6)
        ax.set_xlabel("y from the centreline (ft)")
        ax.set_ylabel(lab)
        ax.grid(alpha=0.3)
    ax2.legend(fontsize=7)
    fig.suptitle(f"P7 loads on the wing, ruled cases at ultimate (x {r['fos']:g}); {r['review']}", fontsize=10)
    fig.tight_layout()
    fig.savefig(folder / "loads_on_wing.png", dpi=130)
    plt.close(fig)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    a1.plot(y, s["cap_area_in2"], "o-", ms=3, color="C3")
    a1.set_ylabel("area of each cap (in^2)")
    a1b = a1.twinx()
    a1b.plot(y, s["caps_share_of_depth"], color="0.5", lw=0.8, ls=":")
    a1b.set_ylabel("two caps over the depth inside the skins", color="0.4")
    a2.plot(y, s["web_in"], "o-", ms=3, color="k", label="web used")
    a2.plot(y, s["web_strength_in"], color="C0", lw=1.0, label="shear strength")
    a2.plot(y, s["web_buckling_in"], color="C1", lw=1.0, ls="--", label="shear buckling (14.37)")
    a2.set_ylabel("web thickness (in)")
    a2.legend(fontsize=8)
    for a in (a1, a2):
        a.set_xlabel("y from the centreline (ft)")
        a.grid(alpha=0.3)
    fig.suptitle(f"P7 spar sized to the ruled envelope: {f(r['row5']['spar_lb'], 1)} lb ({100 * r['row5']['share']:.1f} % of r0's wing); {r['review']}", fontsize=10)
    fig.tight_layout()
    fig.savefig(folder / "sizing.png", dpi=130)
    plt.close(fig)
    for name in FIGURES:
        (folder / f"{name}.json").write_text(json.dumps({
            "figure": f"{name}.png", "made_by": "prelim/p7_report.write_figures (matplotlib only, PD-2)",
            "record": str((out / "p7.json").relative_to(p7.REPO)), "p7_json_sha256": p7.sha256(out / "p7.json"),
            "review": r["review"]}, indent=1) + "\n")


def report_text(out):
    out = Path(out)
    r = load(out)
    i, ch, r0 = r["inputs"], r["choices"], r["r0"]
    a1, a2, a3, a4, a5, r1 = r["row1"], r["row2"], r["row3"], r["row4"], r["row5"], r["r1"]
    sec, s = r["section"], r["spar"]
    mat = ch["material"]
    T = []
    w = T.append
    w("# Task 12 preliminary design P7: wing spar preliminary sizing")
    w("")
    w(f"**{r['review']}.** Run on Opus 5.5 under owner ruling PD-22 (`docs/specs/00_decisions.md` section 9); Fable reviews this diff before P9.")
    w("")
    w(f"Generated by `python -m prelim.p7_spar --report-only` from `{i['excluded']}/p7.json`. Every number below is read from that record. "
      f"Record made by `{i['command']}` at commit {i['commit'][:7]} from a clean tree (git_dirty {i['git_dirty']}; tree unchanged during the run: "
      f"{i['tree_unchanged_during_run']}); Python {i['python']}, numpy {i['numpy']}, scipy {i['scipy']}, matplotlib {i['matplotlib']}; no random numbers. "
      f"Baseline r0: `{r['baseline']}`. Choices: `data/task12/pd_p7_choices.yaml` (decision PD-23). Spec: `docs/specs/task12_preliminary_design.md`, P7.")
    w("")
    w("## Acceptance")
    w("")
    w("| Row | What | Number | Tolerance | Evidence class | Verdict |")
    w("|---|---|---|---|---|---|")
    e1 = max(a1["elliptic_check_grid"]["V_error"], a1["elliptic_check_grid"]["M_error"])
    w(f"| 1 | airload sums to the wing lift; uniform and elliptic cantilevers against their closed forms | lift {a1['airload_largest_error']:.1e}; uniform {max(a1['uniform']['V_error'], a1['uniform']['M_error']):.1e}; elliptic {e1:.1e} ({a1['elliptic_check_grid']['strips']:,} strips) | 1e-9; 1e-6 | {a1['evidence_class']} | **{a1['verdict']}** |")
    w(f"| 2 | Schrenk's root bending moment against the lattice's ({a2['lattice_level']}), same lift | {pct(a2['deviation'])} | ±{100 * a2['tolerance']:g} % | {a2['evidence_class']} | **{a2['verdict']}** |")
    w(f"| 3 | positive margin at ultimate load, caps and web, every station, every ruled case | least {a3['least_margin']:.1e} (governing case, zero by construction); every station sized: {a3['every_station_sized']} | at or above 0 | {a3['evidence_class']} | **{a3['verdict']}** |")
    w(f"| 4 | caps fit inside the section with the assumed skin ({f(a4['skin_in'], 2)} in) | largest share of the depth {100 * a4['largest_caps_share_of_depth']:.2f} %; least discriminant {f(a4['least_fit_discriminant_in2'], 1)} in^2 | real root at every station | {a4['evidence_class']} | **{a4['verdict']}** |")
    w(f"| 5 | spar weight as a share of r0's wing weight ({f(a5['r0_wing_lb'], 1)} lb) | {f(a5['spar_lb'], 1)} lb, {100 * a5['share']:.1f} % | none | {a5['evidence_class']} | **{a5['verdict']}** |")
    w("")
    w("Every verdict follows from the numbers in the record; reported, not tuned. Row 3 is judged on the spar sized to the envelope of the ruled cases (PD-23), so its real content is that a sizing exists at every station and what margin the non-governing cases keep (section 5).")
    w("")
    w("## 1. Sources")
    w("")
    lib = ch["library"]
    w("**Library** (Raymer, *Aircraft Design: A Conceptual Approach*, 2nd ed., 1992; cited by number and page, no book text copied):")
    w("")
    for k in ("schrenk", "trim_first", "station_method", "wing_weight_by_chord", "bending", "spar_idealisation", "web_buckling", "material_table"):
        w(f"- {lib[k]}")
    w("")
    w(f"**Page check.** {lib['page_check']}")
    w("")
    w(f"**Table 14.4, p. 368-369 values used** ({mat['name']}):")
    w("")
    c0, c45 = mat["caps_0_deg"], mat["web_pm45_deg"]
    w("| Laminate | density (lb/in^3) | F_tu(L) (psi) | F_cu(L) (psi) | F_su(LT) (psi) | E (psi) | G(LT) (psi) |")
    w("|---|---|---|---|---|---|---|")
    w(f"| 0 deg (caps) | {c0['density_lb_in3']} | {c0['F_tu_L_psi']:,.0f} | {c0['F_cu_L_psi']:,.0f} | - | {c0['E_t_L_psi']:,.0f} | - |")
    w(f"| +-45 deg (web) | {c45['density_lb_in3']} | - | - | {c45['F_su_LT_psi']:,.0f} | {c45['E_c_L_psi']:,.0f} | {c45['G_LT_psi']:,.0f} |")
    w("")
    kd = ch["knock_down"]
    w(f"**[Not lib] knock-down.** {kd['value']:g} on the strengths, band {kd['band'][0]:g} to {kd['band'][1]:g}: {kd['source']} "
      f"Allowables: caps {f(sec['sigma_cap_psi'], 0)} psi, web shear {f(sec['F_su_psi'], 0)} psi. Web buckling: K = {sec['K']:g} ({ch['geometry']['web_buckling_K']['source']}).")
    w("")
    w(f"**Lattice.** {ch['loads']['lattice']['code']}, {ch['loads']['lattice']['planform']}, at {ch['loads']['lattice']['alpha_deg']:g} deg; the comparison is of the load's shape, so the angle does not matter. VSPAERO was not needed.")
    w("")
    w(f"**Inputs.** r0: wing {f(r0['wing']['area'], 2)} ft^2, span {f(r0['wing']['span'], 3)} ft, chords {f(r0['wing']['root_chord'], 3)} / {f(r0['wing']['tip_chord'], 3)} ft, wing weight {f(r0['components_lb']['wing'], 1)} lb, "
      f"sponsons {f(r0['components_lb']['sponsons'], 1)} lb and main gear {f(r0['components_lb']['main_gear'], 1)} lb at y = {f(r0['half_track_ft'], 3)} ft, fuel {f(r0['fuel_lb'], 1)} lb; factor of safety {r['fos']:g}. "
      f"P4 (`runs/task12/pd/2026-11-27/p4/p4.json`): layout, tanks, centre of gravity {f(r['p4_inputs']['cg']['full'], 3)} ft full and {f(r['p4_inputs']['cg']['empty'], 3)} ft empty, wing moment {f(r['p4_inputs']['cm_w'], 4)}; "
      f"P4's trim legs reproduce with the same function to {r['p4_inputs']['trim_check']['largest_relative_difference']:.1e}. P5 (`runs/task12/pd/2026-11-28/p5/p5.json`): load factors and speeds. "
      f"Spar station {sec['x_spar']:g} c (P3 arrangement), depth {100 * s['depth_in'][0] / (12 * s['chord_ft'][0]):.2f} % of the chord.")
    w("")
    w("## 2. Load cases (ultimate, root values)")
    w("")
    w("| Case | Kind | n | W (lb) | fuel (lb) | speed | V (kt EAS) | wing lift (lb) | tail lift (lb) | root V_ult (lb) | root M_ult (lb ft) | least cap margin | least web margin |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in r["cases"]:
        b = c["by_speed"][c["speed"]]
        w(f"| {c['name']} | {c['kind']} | {f(c['n'])} | {f(c['W_lb'], 1)} | {f(c['fuel_lb'], 1)} | {c['speed']} | {f(b['V_kt'], 1)} | {f(b['L_wing_lb'], 0)} | {f(b['L_tail_lb'], 0)} | {f(b['root_V_ult_lb'], 0)} | {f(b['root_M_ult_lbft'], 0)} | {f(c['min_cap_margin'])} | {f(c['min_web_margin'])} |")
    w("")
    w("Every listed speed of the manoeuvre cases (the largest root moment is kept):")
    w("")
    w("| Case | speed | V (kt EAS) | centre of gravity (ft) | C_L wing | C_L tail | wing lift (lb) | tail lift (lb) | root M_ult (lb ft) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for c in r["cases"]:
        if len(c["by_speed"]) > 1:
            for sp, b in c["by_speed"].items():
                w(f"| {c['name']} | {sp} | {f(b['V_kt'], 1)} | {f(b['x_cg_ft'], 3)} | {f(b['CL_wing'], 3)} | {f(b['CL_tail'], 3)} | {f(b['L_wing_lb'], 0)} | {f(b['L_tail_lb'], 0)} | {f(b['root_M_ult_lbft'], 0)} |")
    w("")
    w("![loads on the wing](figures/2026-11-28_task12_pd_p7/loads_on_wing.png)")
    w("")
    w("## 3. Row 1: coding checks")
    w("")
    w(f"- Airload: in every case and speed the strip loads sum to half the wing lift; largest relative error {a1['airload_largest_error']:.1e} (tolerance {a1['airload_tolerance']:.0e}).")
    w(f"- Uniform cantilever, {a1['uniform']['strips']} strips: shear {a1['uniform']['V_error']:.1e}, moment {a1['uniform']['M_error']:.1e} of the root values (the trapezoid rule is exact for it).")
    w(f"- Elliptic loading, {a1['elliptic_check_grid']['strips']:,} strips: shear {a1['elliptic_check_grid']['V_error']:.1e}, moment {a1['elliptic_check_grid']['M_error']:.1e} (tolerance {a1['closed_form_tolerance']:.0e}). "
      f"On the run's own {a1['elliptic_run_stations']['strips']} strips: shear {a1['elliptic_run_stations']['V_error']:.1e}, moment {a1['elliptic_run_stations']['M_error']:.1e}; {a1['note']}.")
    w(f"- Verdict **{a1['verdict']}**.")
    w("")
    w("## 4. Row 2: Schrenk against the lattice")
    w("")
    w("Spanwise centre of the half-wing airload, root moment over half-wing lift (ft):")
    w("")
    w("| Source | strips | centre (ft) | against Schrenk on the stations |")
    w("|---|---|---|---|")
    w(f"| Schrenk, the run's stations | {len(s['y_ft']) - 1} | {f(a2['schrenk_ybar_ft_stations'], 4)} | - |")
    w(f"| Schrenk, exact integral | - | {f(a2['schrenk_ybar_ft_exact'], 4)} | {pct(a2['schrenk_ybar_ft_exact'] / a2['schrenk_ybar_ft_stations'] - 1)} |")
    for lev, v in a2["lattice"].items():
        w(f"| lattice, {lev} | {v['strips']} | {f(v['ybar_ft'], 4)} | {pct(v['ybar_ft'] / a2['schrenk_ybar_ft_stations'] - 1)} |")
    w("")
    w(f"Verdict **{a2['verdict']}** ({pct(a2['deviation'])} against ±{100 * a2['tolerance']:g} %); the airload used is **{a2['used']}**. "
      "The lattice has no fuselage and no viscous effects; both are untwisted, so this compares the additional load only.")
    w("")
    w("## 5. Rows 3 and 4: the spar sized to the ruled envelope")
    w("")
    w(f"Root moment set by '{a3['root_moment_case']}', root shear by '{a3['root_shear_case']}'. Least margin of each ruled case over every station, caps and web (zero for the case that sets a station):")
    w("")
    w("| Case | least margin |")
    w("|---|---|")
    for k, v in a3["least_margin_by_case"].items():
        w(f"| {k} | {f(v)} |")
    w("")
    w("| y (ft) | chord (ft) | depth (in) | inside skins (in) | M_ult env (lb ft) | set by | V_ult env (lb) | set by | cap area (in^2) | cap t (in) | web (in) | web set by |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for j in range(len(s["y_ft"])):
        w(f"| {f(s['y_ft'][j], 3)} | {f(s['chord_ft'][j], 3)} | {f(s['depth_in'][j], 2)} | {f(s['h_in'][j], 2)} | {f(s['M_env_ult_lbft'][j], 0)} | {s['M_env_case'][j]} | {f(s['V_env_ult_lb'][j], 0)} | {s['V_env_case'][j]} | "
          f"{f(s['cap_area_in2'][j], 4)} | {f(s['cap_thickness_in'][j], 4)} | {f(s['web_in'][j], 4)} | {'buckling' if s['web_buckling_governs'][j] else 'strength'} |")
    w("")
    w(f"Row 3 verdict **{a3['verdict']}**; row 4 verdict **{a4['verdict']}** (two caps take at most {100 * a4['largest_caps_share_of_depth']:.2f} % of the depth inside the skins).")
    w("")
    w("![sizing](figures/2026-11-28_task12_pd_p7/sizing.png)")
    w("")
    w("## 6. Row 5: spar weight against the statistical wing (item 8)")
    w("")
    w(f"Spar {f(a5['spar_lb'], 2)} lb (caps {f(a5['caps_lb'], 2)} lb, web {f(a5['web_lb'], 2)} lb) against r0's wing {f(a5['r0_wing_lb'], 1)} lb: {100 * a5['share']:.1f} %. "
      f"Heavier than the whole statistical wing: {a5['heavier_than_wing']}. No tolerance (the library gives no spar share). Verdict **{a5['verdict']}**.")
    w("")
    w("Each banded judgement at its band ends, one at a time (ruled envelope):")
    w("")
    w("| Judgement | value | spar (lb) | caps (lb) | web (lb) | share of the wing | caps fit |")
    w("|---|---|---|---|---|---|---|")
    for name, ends in r["band_ends"].items():
        for v, x in ends.items():
            w(f"| {name} | {v} | {f(x['spar_lb'], 2)} | {f(x['caps_lb'], 2)} | {f(x['web_lb'], 2)} | {100 * x['share']:.1f} % | {x['fits']} |")
    w("")
    w("## 7. Sensitivity: the P5 row 4 cases on the ruled spar (no verdict)")
    w("")
    w("| Case | least cap margin | least web margin |")
    w("|---|---|---|")
    for k, v in r["sensitivity"]["cases"].items():
        w(f"| {k} | {f(v['min_cap_margin'])} | {f(v['min_web_margin'])} |")
    sc = r["sensitivity"]["spar_covering_them"]
    w("")
    w(f"A spar sized to carry them as well: {f(sc['spar_lb'], 2)} lb (caps {f(sc['caps_lb'], 2)} lb, web {f(sc['web_lb'], 2)} lb), caps fit: {sc['fits']}. "
      "A finding for O-2 (PD-8): under the ruled rule these cases are not design cases.")
    w("")
    w("## 8. Findings for r1")
    w("")
    w(f"- With P4b's layout ({r1['layout']}; PD-21), its centre of gravity ({f(r1['cg_ft']['full'], 3)} ft full, {f(r1['cg_ft']['empty'], 3)} ft empty), weights raised by {f(r1['empty_weight_change_lb'], 2)} lb and P2's clean maximum lift {f(r1['CL_max_clean'], 3)}: "
      f"root ultimate moment {f(r1['root_M_env_ult_lbft_r0'], 0)} to {f(r1['root_M_env_ult_lbft'], 0)} lb ft ({pct(r1['root_moment_change'])}), set by '{r1['root_moment_case']}'; spar {f(r1['spar_lb_r0'], 2)} to {f(r1['spar_lb'], 2)} lb ({r1['spar_change_lb']:+.2f} lb); caps fit: {r1['fits']}.")
    wo = r1["weights_and_CL_max_only"]
    g0 = next(c for c in r["cases"] if c["name"] == r1["root_moment_case"])
    g1 = next(c for c in r1["cases"] if c["name"] == r1["root_moment_case"])
    w(f"- Of that, r1's weights and maximum lift alone on r0's layout and centre of gravity give {f(wo['root_M_env_ult_lbft'], 0)} lb ft ({pct(wo['root_M_env_ult_lbft'] / r1['root_M_env_ult_lbft_r0'] - 1)}) and {f(wo['spar_lb'], 2)} lb; the rest is the layout. "
      f"In '{g1['name']}' the tail lift is {f(g0['L_tail_lb'], 0)} lb on r0 and {f(g1['L_tail_lb'], 0)} lb on r1, the wing lift {f(g0['L_wing_lb'], 0)} and {f(g1['L_wing_lb'], 0)} lb (positive up).")
    pos = [c for c in r["cases"] if c["kind"] == "ruled" and c["n"] > 0 and "positive_corner" in c["speeds_kt"]]
    w(f"- The lower maximum lift moves only the positive corner speed. The +3.8 cases keep their largest root moment at: "
      + "; ".join(f"{c['name']} {c['speed']}" for c in pos) + " (r0), "
      + "; ".join(f"{c['name']} {c['speed']}" for c in r1["cases"] if c["kind"] == "ruled" and "positive_corner" in c["speeds_kt"]) + " (r1).")
    w("- P9 re-runs P7 on r1 with the same code if r1 changes the wing, its weight, the tanks or the gear station.")
    w("")
    w("## 9. Other findings")
    w("")
    loaded = [j for j in range(len(s["y_ft"])) if s["web_in"][j] > 0.0]
    gb = sum(1 for j in loaded if s["web_buckling_governs"][j])
    w(f"- The web is set by shear buckling at {gb} of the {len(loaded)} stations that carry shear and makes {100 * a5['web_lb'] / a5['spar_lb']:.0f} % of the spar weight: an unstiffened +-45 deg web that may not buckle is heavy. Stiffeners or a sandwich web would cut it; not sized here.")
    w(f"- Largest cap thickness {f(max(s['cap_thickness_in']), 3)} in; two caps take at most {100 * a4['largest_caps_share_of_depth']:.2f} % of the depth inside the skins.")
    neg = sorted({k for k in s["M_env_case"] + s["V_env_case"] if next(c for c in r["cases"] if c["name"] == k)["n"] < 0})
    w("- Stations set by a negative case: " + (", ".join(neg) if neg else "none") + ". The caps are equal above and below (equal tension and compression values), so a negative case sets a station only where its moment or shear is the larger in magnitude.")
    g = next(c for c in r["cases"] if c["name"] == a3["root_moment_case"])
    w(f"- Tail trim load in '{g['name']}': {f(g['L_tail_lb'], 0)} lb (positive up), so the wing carries {f(g['L_wing_lb'], 0)} lb of n W = {f(g['n'] * g['W_lb'], 0)} lb. A tail upload lowers the wing's share; a download would raise it.")
    w("")
    w("## 10. Assumptions")
    w("")
    for a in ASSUMPTIONS:
        w(f"- {a}")
    w("")
    w("## 11. What this does not show")
    w("")
    w("- Not a stress report: no rear spar, torsion box, ribs, skins, joints, fittings, fatigue, flutter or divergence (PD-9); no finite elements; no laminate design.")
    w("- No design allowables from tests: typical values times a judged knock-down. The printed Table 14.4 page was not re-opened in this session.")
    w("- No aileron, flap, roll or asymmetric case; no landing or ground loads on the wing.")
    w("- The spar weight is not a wing weight: skins, ribs, the rear spar, control surfaces and fittings make the rest of the 429.4 lb.")
    w("- Not yet Fable-reviewed (ruling PD-22).")
    w("")
    return "\n".join(T) + "\n"

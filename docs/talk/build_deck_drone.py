"""Build docs/talk/deck_drone.pptx (Task 10 deck, T10.11b) from docs/talk/outline_drone.md.

Run from the repository root with either of:
    python -m docs.talk.build_deck_drone
    python docs/talk/build_deck_drone.py

Rules (CLAUDE.md, and the inlet deck's own):
- Each slide's title, message and speaker notes come from docs/talk/outline_drone.md. A `{name}` in a
  message or note is filled from the values computed below; a name with no value fails the build.
- Every number on a slide is read from a file at build time (v6.json, record.json files, the CSVs,
  result.json files, the spec). Where no file exists the slide says PENDING and names the batch.
- Layout helpers are imported from docs/talk/build_deck.py (importing it runs no code beyond its own
  imports), which this script does not modify.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import figures_drone as fd
from analysis.high_level_bias import v6e_flags
from docs.talk import build_deck as bd

OUTLINE = ROOT / "docs/talk/outline_drone.md"
DEFAULT_OUT = ROOT / "docs/talk/deck_drone.pptx"
V6 = "runs/drone/validation/2026-11-08/v6.json"
SPEC = "docs/specs/task10_drone_sizing.md"
TASKS = "docs/specs/task10_tasks.md"
FIG = "docs/validation/figures/task10/"
LM, CW, CT = bd.LM, bd.CW, bd.CT


# ---- reading files ----------------------------------------------------------------------------
def jload(rel):
    return json.loads((ROOT / rel).read_text())


def csv_rows(rel):
    with open(ROOT / rel, newline="") as f:
        return list(csv.DictReader(f))


def mean_at(rows, strategy, metric, n):
    v = [float(r["value"]) for r in rows
         if r["strategy"] == strategy and r["metric"] == metric and int(r["n"]) == n]
    return float(np.mean(v))


def pct_range(values):
    """'19 to 23 %' from fractional deviations (magnitudes, rounded to whole percent)."""
    m = [abs(v) * 100 for v in values]
    return f"{round(min(m))} to {round(max(m))} %"


def signed_range(values, up, down):
    """'8.0 % high to 11.6 % high' or '10.3 % low to 1.6 % high': both ends keep their sign."""
    lo, hi = min(values) * 100, max(values) * 100
    end = lambda x: f"{abs(x):.1f} % {up if x >= 0 else down}"
    return f"{end(lo)} to {end(hi)}" if lo * hi < 0 else f"{abs(lo):.1f} to {end(hi if hi > 0 else lo)}"


def e387_points(re=203800.0):
    """[(alpha, su2 cl, su2 cd, tunnel cl, tunnel cd)] at the tunnel's own angles for one Re."""
    tunnel = {p["nominal_reynolds"]: p for p in
              yaml.safe_load((ROOT / fd.E387_TUNNEL).read_text())["polars"]}
    tun = tunnel[200000.0] if re < 250000 else tunnel[300000.0]
    out = []
    for f in sorted((ROOT / "runs/e387").glob("*/result.json")):
        r = json.loads(f.read_text())
        if r["params"]["reynolds"] != re:
            continue
        a = r["params"]["alpha_deg"]
        i = int(np.argmin(np.abs(np.array(tun["alpha_deg"]) - a)))
        assert abs(tun["alpha_deg"][i] - a) < 1e-6, f"{f}: no tunnel point at {a} deg"
        out.append((a, r["metrics"]["cl"], r["metrics"]["cd"], tun["cl"][i], tun["cd"][i]))
    return sorted(out)


def values():
    """Every {name} a message or note may use, each computed from a file."""
    v6 = jload(V6)["checks"]
    tol = [c for c in v6 if c["name"][:3] == "V6a" or c["name"][:3] in ("V6b", "V6c", "V6d")]
    tol = [c for c in tol if c["tolerance"] is not None]
    v6f = [c for c in v6 if c["name"].startswith("V6f ")]
    v6e = next(c for c in v6 if c["name"] == "V6e cl_alpha Re 203800")
    grid, pool = jload("runs/drone_grid/2026-11-08/record.json"), jload("runs/drone_pool_lf/2026-11-08/record.json")
    rep = csv_rows(fd.POOL_REPLAY)
    on, feas = csv_rows(fd.ONLINE), csv_rows(fd.ONLINE_FEAS)
    smoke = jload("runs/smoke/airfoil2d-96a9dd0f51/result.json")
    smoke2 = jload("runs/smoke2/airfoil2d-51d551f2cc/result.json")
    pts = e387_points()
    cases = csv_rows("designs/pool_af_cases.csv")

    def band(name):
        return [c["deviation"] for c in v6f if c["name"].startswith(f"V6f {name} ")]

    return {
        "smoke_budget": smoke["params"]["max_iter"],
        "smoke2_iters": smoke2["convergence"]["iterations"],
        "n_pass": sum(c["verdict"] == "pass" for c in tol),
        "n_pending": sum(c["verdict"].startswith("pending") for c in tol),
        "n_fail": sum(c["verdict"] == "fail" for c in tol),
        "f_clalpha_range": pct_range(band("cl_alpha")),
        "f_cd_range": pct_range(band("cd ratio")),
        "f_clmax_range": pct_range(band("cl_max")),
        "v6e_dev": f"{100 * v6e['deviation']:.2f} %",
        "v6e_tol": f"{100 * v6e['tolerance']:.0f} %",
        "grid_n": f"{grid['points_evaluated']:,}",
        "front_n": grid["front_size"],
        "gated_n": f"{grid['points_gated']:,}",
        "pool_front_n": pool["front_size"],
        "ehvi_32": f"{mean_at(rep, 'al_ehvi', 'hv_regret', 32):.3f}",
        "rand_40": f"{mean_at(rep, 'random', 'hv_regret', 40):.3f}",
        "ehvi_on_40": f"{mean_at(on, 'al_ehvi', 'hv_regret', 40):.3f}",
        "rand_on_40": f"{mean_at(on, 'random', 'hv_regret', 40):.3f}",
        "ehvi_gated": f"{mean_at(on, 'al_ehvi', 'n_gated', 40):.1f}",
        "feas_on_40": f"{mean_at(feas, 'al_ehvi_feas', 'hv_regret', 40):.3f}",
        "pool_cases": len(cases),
        "su2_cl_range": signed_range([p[1] / p[3] - 1 for p in pts], "high", "low"),
        "su2_cd_range": signed_range([p[2] / p[4] - 1 for p in pts], "high", "low"),
        "e387_re": f"{203800:,}",
    }


# ---- reading the outline ----------------------------------------------------------------------
def read_outline():
    """[{id, title, message, figure, source, notes}] in file order."""
    slides, cur = [], None
    for line in OUTLINE.read_text(encoding="utf-8").splitlines():
        head = re.match(r"^### (D\d+)\. (.+)$", line)
        if head:
            cur = {"id": head.group(1), "title": head.group(2)}
            slides.append(cur)
        elif cur is not None:
            for key, tag in (("message", "Message"), ("figure", "Figure or table"),
                             ("source", "Source"), ("notes", "Speaker notes")):
                if line.startswith(f"- **{tag}:** "):
                    cur[key] = line[len(f"- **{tag}:** "):].strip()
    return slides


def source_list(source):
    """Backticked paths of a Source line, or the whole PENDING text."""
    if source.startswith("PENDING"):
        return [source]
    return re.findall(r"`([^`]+)`", source)


# ---- slide bodies -----------------------------------------------------------------------------
def body_d2(slide, v):
    rows = [["Question", "Status"],
            ["1. The front of endurance against take-off mass, with the GP's band and the named biases",
             "Exact low-fidelity front computed (D8); band over the SU2 pool PENDING"],
            ["2. Active learning against LHS and random: pool replay, and online against the exact front",
             "Answered on the low-fidelity model (D9, D10); SU2 pool replay PENDING"],
            ["3. Does the two-level model reach a given error with fewer SU2 polars?", "PENDING: multi-fidelity analysis"],
            ["4. Longest endurance under the 4.0 kg cap with P(mass <= cap) >= 0.9, and one SU2 confirmation",
             "PENDING: confirmation run"]]
    bd.add_table(slide, LM, CT + 0.2, [7.4, 4.7], rows, size=13, row_h=0.8)


def body_d3(slide, v):
    y = CT + 0.3
    labels = ["Six inputs\nspan, aspect ratio, taper ratio,\nbattery fraction, camber,\nthickness",
              "Vortex lattice\nCL_alpha, e, strip cl", "Drag build-up\nprofile + parasite + induced",
              "Mass closure\nfixed point on take-off mass", "Mission\nminimum-power cruise",
              "Endurance\nand take-off mass"]
    bw, gx = 1.8, 0.26
    for i, text in enumerate(labels):
        x = LM + i * (bw + gx)
        bd.box(slide, x, y, bw, 1.5, text, size=11, fill=bd.TINT if i in (0, 5) else bd.WHITE)
        if i:
            bd.arrow(slide, x - gx, y + 0.75, x, y + 0.75)
    bd.text_box(slide, LM, y + 1.9, CW, 0.4, "Two fidelity levels: the section data is the only block that differs",
                size=14, color=bd.ACCENT, bold=True)
    bd.box(slide, LM, y + 2.4, 5.8, 1.3,
           "Low: closed-form section\nthin-airfoil lift, constant profile drag\n(under a second per design)", size=12)
    bd.box(slide, LM + 6.3, y + 2.4, 5.8, 1.3,
           "High: SU2 airfoil polar\nSA-BCM, one polar per design at its cruise Reynolds number\n(PENDING: pool batch)", size=12)


def body_d4(slide, v):
    rows = [["Run", "Budget", "Iterations", "cl drift (%)", "cd drift (%)", "Status"]]
    for rel, label in (("runs/smoke/airfoil2d-96a9dd0f51", "first smoke case"),
                       ("runs/smoke2/airfoil2d-51d551f2cc", "rerun with Cauchy stop")):
        r = jload(rel + "/result.json")
        conv, m = r["convergence"], r["metrics"]
        it = conv.get("iterations")
        rows.append([label, r["params"]["max_iter"], it if it else "not recorded (postprocess error)",
                     f"{m['cl_drift_pct']:.2f}", f"{m['cd_drift_pct']:.2f}", conv.get("status")])
    bd.add_table(slide, LM, CT + 0.1, [3.0, 1.2, 3.0, 1.4, 1.4, 2.1], rows, size=12, row_h=0.55)
    cfg = (ROOT / "cases/templates/inc_rans_airfoil.cfg").read_text()
    keys = ("CONV_FIELD", "CONV_CAUCHY_ELEMS", "CONV_CAUCHY_EPS", "CONV_STARTITER")
    lines = [m.group(0).strip() for k in keys for m in re.finditer(rf"^{k}=.*$", cfg, re.MULTILINE)]
    bd.text_box(slide, LM, CT + 2.2, 5.5, 0.4, "Cauchy settings (cases/templates/inc_rans_airfoil.cfg)",
                size=13, bold=True)
    bd.text_box(slide, LM, CT + 2.65, 5.5, 1.6, lines, size=13, font="Consolas", space_after=2)
    bd.text_box(slide, LM + 6.0, CT + 2.2, 6.0, 2.5,
                ["What stays the same: the Drive queue, the worker, the digest check and the gates.",
                 "What is new: the airfoil2d family, its mesh-quality checks and this stopping rule.",
                 "The drift rule and SU2's Cauchy rule measure different things; the record carries both."],
                size=13, bullets=True)


def body_d5(slide, v):
    rows = [["Row", "Deviation", "Tolerance", "Verdict"]]
    for c in jload(V6)["checks"]:
        if c["name"][:3] not in ("V6a", "V6b", "V6c", "V6d") or c["tolerance"] is None:
            continue
        dev = f"{c['deviation']:.2e}" if c["tolerance"] < 1e-4 else f"{100 * c['deviation']:+.2f} %"
        tol = f"{c['tolerance']:.0e}" if c["tolerance"] < 1e-4 else f"{100 * c['tolerance']:.0f} %"
        verdict = c["verdict"]
        if verdict.startswith("pending"):
            verdict = "PENDING: " + verdict.split("(", 1)[1].rstrip(")")
        elif verdict == "fail":
            verdict = "FAIL"
        rows.append([c["name"], dev, tol, verdict])
    bd.add_table(slide, LM, CT - 0.1, [7.0, 1.6, 1.3, 2.2], rows, size=10, row_h=0.31)


def body_d6(slide, v):
    checks = {c["name"]: c for c in jload(V6)["checks"]}
    res = ("101800", "203800", "305200")
    rows = [["Quantity", *[f"Re {int(r):,}" for r in res]]]
    for q, label, unit in (("cl_alpha", "lift slope", "%"), ("alpha_L0", "zero-lift angle", "deg"),
                           ("cd ratio", "profile drag, mean ratio", "%"), ("cl_max", "cl_max", "%")):
        cells = []
        for r in res:
            d = checks[f"V6f {q} Re {r}"]["deviation"]
            cells.append(f"{100 * d:+.1f} %" if unit == "%" else f"{d:+.2f} deg")
        rows.append([label, *cells])
    bd.add_table(slide, LM, CT + 0.1, [4.2, 2.6, 2.6, 2.6], rows, size=14, row_h=0.6, flag=())
    bd.text_box(slide, LM, CT + 3.4, CW, 1.3,
                [("Report-only rows by the spec: closed forms of drone/section.py at the E387's measured camber "
                  "and thickness against Volume 1 runs 211, 213 and 215."),
                 ("The ledger's assumed lift effectiveness does not contain the value the tunnel implies: a ledger "
                  "ruling, not a number to move here.")], size=13, bullets=True)


def body_d7(slide, v):
    _, _ = bd.add_figure_with_caption(slide, FIG + "d_e387_comparison.png", "runs/e387/*/result.json",
                                      LM, CT, 7.0, 4.2)
    checks = [c for c in jload(V6)["checks"] if c["name"].startswith("V6e ")]
    rows = [["Row", "Deviation", "Tol.", "Verdict"]]
    for c in checks:
        tol = "report" if c["tolerance"] is None else f"{100 * c['tolerance']:.0f} %"
        verdict = "report" if c["verdict"] == "report" else c["verdict"].upper() if c["verdict"] == "fail" else c["verdict"]
        rows.append([c["name"][5:], f"{100 * c['deviation']:+.2f} %", tol, verdict])
    bd.add_table(slide, LM + 7.2, CT, [2.0, 1.1, 0.8, 0.9], rows, size=10, row_h=0.45)
    bd.text_box(slide, LM + 7.2, CT + 2.0, 4.9, 2.4,
                [(f"Against the tunnel at the five angles of Re {v['e387_re']}: cl is {v['su2_cl_range']}; "
                  f"cd is {v['su2_cd_range']}."), "Decision 8: accepted as the high level with the miss recorded beside every number.",
                 "Re 305,200 and the fine-mesh pair are not complete; the figure draws what exists."],
                size=12, bullets=True)


def body_d8(slide, v):
    bd.add_figure_with_caption(slide, FIG + "a_front_lowfi.png", "runs/drone_grid/2026-11-08/front.csv",
                               LM, CT, 6.4, 4.3)
    g, p = jload("runs/drone_grid/2026-11-08/record.json"), jload("runs/drone_pool_lf/2026-11-08/record.json")
    bd.text_box(slide, LM + 6.7, CT, 5.4, 4.4,
                [(f"Grid: {g['points_evaluated']:,} points, {g['points_clean']:,} clean, {g['points_gated']:,} gated, "
                  f"{g['points_failed']} failed."),
                 f"Exact front: {g['front_size']} designs.",
                 f"Wall time: {g['wall_seconds']:.0f} s on {g['workers']} workers.",
                 (f"Low pool: {p['points_evaluated']} designs, {p['points_gated']} gated, "
                  f"front of {p['front_size']}, {p['wall_seconds']:.0f} s."),
                 "Both runs are at the medium lattice level."], size=14, bullets=True)


def body_d9(slide, v):
    rep = csv_rows(fd.POOL_REPLAY)
    ns = (8, 16, 24, 32, 40)
    strategies = ("random", "lhs", "al_ehvi", "al_maxvar")
    rows = [["n", *strategies]] + [[n, *[f"{mean_at(rep, s, 'hv_regret', n):.3f}" for s in strategies]] for n in ns]
    _, h = bd.add_figure_with_caption(slide, FIG + "b_pool_replay.png", fd.POOL_REPLAY, LM, CT - 0.05, 8.4, 2.9)
    bd.add_table(slide, LM, CT + h + 0.6, [1.0, 2.0, 2.0, 2.0, 2.0], rows, size=11, row_h=0.27, flag=())


def body_d10(slide, v):
    on, feas = csv_rows(fd.ONLINE), csv_rows(fd.ONLINE_FEAS)
    rows = [["Strategy", "Regret at 40", "Gated picks"]]
    for s, src in (("random", on), ("lhs", on), ("al_ehvi", on), ("al_ehvi_feas", feas), ("al_maxvar", on),
                   ("al_maxvar_feas", feas)):
        rows.append([s, f"{mean_at(src, s, 'hv_regret', 40):.3f}", f"{mean_at(src, s, 'n_gated', 40):.1f}"])
    bd.add_figure_with_caption(slide, FIG + "c_online_regret.png", fd.ONLINE + ", " + fd.ONLINE_FEAS,
                               LM, CT, 7.4, 3.2)
    bd.add_table(slide, LM + 7.6, CT, [1.9, 1.4, 1.2], rows, size=12, row_h=0.4, flag=())
    bd.text_box(slide, LM + 7.6, CT + 3.0, 4.5, 1.8,
                ["The front lies against the gated edge, and the GPs do not know the gates.",
                 "Both runs are published; neither replaces the other."], size=12, bullets=True)


def body_pending(slide, lines, box_text):
    bd.pending(slide, LM, CT + 0.1, CW, "PENDING: no number is shown here until the record exists.")
    bd.box(slide, LM, CT + 0.9, CW, 1.6, box_text, size=14)
    bd.text_box(slide, LM, CT + 2.9, CW, 1.6, lines, size=13, bullets=True)


def body_d11(slide, v):
    tags = defaultdict(int)
    for r in csv_rows("designs/pool_af_cases.csv"):
        tags[(r["tag"], r["mesh_level"])] += 1
    text = "\n".join(f"tag {t}, {m} mesh: {n} cases" for (t, m), n in sorted(tags.items()))
    body_pending(slide, ["Output expected: runs/pool_af/results.csv, then the front with the GP band (figure not drawn).",
                         "The acceptance rule for budget-exhausted runs is still open and applies to this pool."],
                 text)


def body_d12(slide, v):
    body_pending(slide, [("Compared: low-fidelity section data plus an SU2 correction term, against SU2 alone, by held-out "
                          "error at equal numbers of SU2 designs."),
                         "The V6e bias is a known offset the correction term has to absorb."],
                 "Held-out error against the number of SU2 designs\nPENDING: multi-fidelity analysis (T10.10c)")


def body_d13(slide, v):
    body_pending(slide, ["The query is a computation on the fitted surrogate, never a choice by the language model.",
                         "The confirmation is one SU2 polar at the answer, through the queue."],
                 "Design, predicted endurance, P(mass <= cap), SU2 confirmation\nPENDING: confirmation run (T10.10d)")


def body_d14(slide, v):
    text = (ROOT / SPEC).read_text()
    para = re.search(r"Biases that travel with every figure:(.*?)\.\n\n", text, re.DOTALL).group(1)
    items = [" ".join(s.split()) for s in para.split(";")]
    items = [i[:1].upper() + i[1:] for i in items]
    bd.text_box(slide, LM, CT, 5.9, 0.4, "Spec section 13", size=14, bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.45, 5.9, 4.2, items, size=13, bullets=True)
    bd.text_box(slide, LM + 6.3, CT, 5.8, 0.4, "Carried by every SU2 section polar (decision 8)", size=14,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM + 6.3, CT + 0.45, 5.8, 4.2, v6e_flags(), size=13, font="Consolas", bullets=True)


def body_d15(slide, v):
    smoke = jload("runs/smoke/airfoil2d-96a9dd0f51/result.json")
    err = smoke["convergence"]["error"]
    col = re.search(r"\('(rms\[\w+\])',\)", err).group(1)
    tasks = (ROOT / TASKS).read_text()
    inverted = re.search(r"\((\d+) inverted cells\)", tasks).group(1)
    m = smoke["metrics"]
    smoke2_budget = jload("runs/smoke2/airfoil2d-51d551f2cc/result.json")["params"]["max_iter"]
    rows = [["Caught", "By", "Resolution"],
            [f"Postprocess looked for the compressible column {col}", "The first airfoil2d case failing at postprocess",
             "The classifier reads rms[P] (decision 6)"],
            [f"First case unconverged: cl drift {m['cl_drift_pct']:.1f} %, cd drift {m['cd_drift_pct']:.1f} %",
             "The drift rule on the recorded history", f"Budget {smoke2_budget} with a Cauchy stop (decision 6)"],
            ["Fine-mesh case refused on the 1 nm fingerprint", "The worker's mesh fingerprint check",
             "Kept beside the rerun as .first_attempt"],
            [f"Fine E387 mesh has {inverted} inverted cells", "The mesh inversion gate",
             "Strict xfail; the V6e fine row stays not run"],
            ["Point-vortex induced drag under-counts by about 1/N", "The V6a elliptic-wing rows on the first lattice run",
             "Trefftz-plane Glauert series (drone/vlm.py)"],
            ["V6a reference for the AR 100 rectangular wing was wrong, not the solver", "The same V6a rows",
             "Reference corrected before any formal verdict (addendum 2)"]]
    bd.add_table(slide, LM, CT - 0.1, [4.6, 3.7, 3.8], rows, size=11, row_h=0.62, flag=())


BODIES = {"D2": body_d2, "D3": body_d3, "D4": body_d4, "D5": body_d5, "D6": body_d6, "D7": body_d7,
          "D8": body_d8, "D9": body_d9, "D10": body_d10, "D11": body_d11, "D12": body_d12, "D13": body_d13,
          "D14": body_d14, "D15": body_d15}


def fill(text, v):
    """Replace {name} by its value; an unknown name raises KeyError and fails the build."""
    return text.format_map(v)


def ensure_figures():
    names = ("a_front_lowfi.png", "b_pool_replay.png", "c_online_regret.png", "d_e387_comparison.png")
    if not all((ROOT / FIG / n).is_file() for n in names):
        fd.main(ROOT, ROOT / FD_OUT)


FD_OUT = fd.OUT_DIR


def build(out_path=DEFAULT_OUT):
    """Build the deck and save it. Returns the number of slides."""
    ensure_figures()
    v = values()
    slides = read_outline()
    prs = bd.new_deck()
    for i, s in enumerate(slides, start=1):
        message, notes = fill(s["message"], v), fill(s["notes"], v)
        if s["id"] == "D1":
            slide = bd.add_title_slide(prs, i, 
                                       "Sizing a small electric aircraft with the inlet pipeline", message,
                                       [("Status 2026-11-08: validation V6a to V6f recorded, low-fidelity studies "
                                         "complete, SU2 pool pending."),
                                        "Every number is read from a record in this repository at build time."], notes)
            for shape in slide.shapes:                     # the shared title helper labels its slide S1
                if shape.has_text_frame and shape.text_frame.text.startswith("S1  |"):
                    shape.text_frame.paragraphs[0].runs[0].text = f"D1  |  {i}"
            continue
        slide = bd.start_slide(prs, i, s["id"], s["title"], message, source_list(s["source"]), notes)
        BODIES[s["id"]](slide, v)
    prs.save(str(out_path))
    return len(prs.slides)


if __name__ == "__main__":
    n = build()
    print(f"wrote {DEFAULT_OUT.relative_to(ROOT)} with {n} slides")

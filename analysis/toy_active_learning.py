"""A worked toy example of active learning (hypervolume, regret, EHVI, three strategies).

    python -m analysis.toy_active_learning --out runs/toy_active_learning/2026-11-13

Nine designs, two goals (more endurance, less mass). Five designs have run (A to E). Four have not
(F to I) and each has a model prediction that this script fixes by hand. The script calls the
study's own functions in surrogate/acquisition.py, so each number is what the study's code gives.
It writes toy.json, three figures and the walkthrough docs/talk/active_learning_worked_example.md,
all from the numbers computed here. This is a teaching example, not a study result: the
predictions are not from a fitted model, and the goals use the mass itself, not its logarithm.
"""
import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from surrogate.acquisition import (
    ehvi_mc,
    hvi_2d,
    hypervolume_2d,
    max_variance,
    pareto_front,
    ref_point,
)

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "talk" / "active_learning_worked_example.md"

# (endurance in hours, mass in kg). Designs that have run.
RUN = {"A": (4.0, 1.0), "B": (6.0, 1.6), "C": (8.0, 2.4), "D": (5.0, 2.0), "E": (7.0, 2.8)}
# What each candidate would give if we ran it. We know it only here; the strategies do not.
# H fails a gate: running it gives no result.
TRUTH = {"F": (7.0, 1.8), "G": (5.2, 2.2), "H": None, "I": (5.4, 2.5)}
# The model's prediction for each candidate: mean endurance, mean mass, sd endurance, sd mass.
PREDICTION = {"F": (6.8, 1.9, 0.6, 0.12), "G": (5.0, 2.2, 0.3, 0.06),
              "H": (9.0, 2.0, 0.8, 0.20), "I": (5.5, 2.4, 2.0, 0.60)}
# The probability that the design passes the gates, as a feasibility model could give it.
P_FEASIBLE = {"F": 0.9, "G": 0.9, "H": 0.05, "I": 0.9}
HAND_DRAWS, HAND_SEED = 4, 1          # the by-hand expected improvement uses 4 seeded draws
STUDY_SAMPLES, LONG_SAMPLES = 128, 20000


def goals(designs):
    """(n, 2) array of the two goals in minimisation form: negative endurance, mass."""
    return np.array([[-t, m] for t, m in designs.values()], dtype=float)


def strips(front, ref, names):
    """The hypervolume strip by strip, as hypervolume_2d adds it: sort by the first goal, keep the
    lowest mass seen so far, and add (endurance span x mass span) for each design that lowers it."""
    rows, level = [], float(ref[1])
    for i in np.argsort(front[:, 0], kind="stable"):
        f1, f2 = front[i]
        if f2 < level:
            rows.append({"design": names[i], "endurance_span": float(ref[0] - f1),
                         "mass_from": float(f2), "mass_to": level, "mass_span": float(level - f2)})
            rows[-1]["area"] = rows[-1]["endurance_span"] * rows[-1]["mass_span"]
            level = f2
    return rows


def front_of(designs):
    """Names of the non-dominated designs and the (n, 2) goals of that front."""
    f = goals(designs)
    idx = pareto_front(f)
    return [list(designs)[i] for i in idx], f[idx]


def regret(designs, ref, hv_true):
    _, front = front_of(designs)
    return 1.0 - hypervolume_2d(front, ref) / hv_true


def compute():
    """Every number of the example."""
    pool = {**RUN, **{k: v for k, v in TRUTH.items() if v is not None}}      # clean designs
    ref = ref_point(goals(pool))
    true_names, true_front = front_of(pool)
    hv_true = float(hypervolume_2d(true_front, ref))
    run_names, run_front = front_of(RUN)
    hv_run = float(hypervolume_2d(run_front, ref))
    table = strips(run_front, ref, run_names)
    assert abs(sum(r["area"] for r in table) - hv_run) < 1e-9           # the strips are the same sum
    dominated = {}
    f_run = goals(RUN)
    for i, name in enumerate(RUN):
        by = [list(RUN)[j] for j in range(len(RUN)) if j != i and (f_run[j] <= f_run[i]).all()
              and (f_run[j] < f_run[i]).any()]
        if by:
            dominated[name] = by[0]
    res = {"ref": {"endurance": float(-ref[0]), "mass": float(ref[1])}, "run_front": run_names,
           "dominated": dominated, "strips": table, "hv_run": hv_run, "true_front": true_names,
           "hv_true": hv_true, "regret_now": 1.0 - hv_run / hv_true}

    # Improvement from one outcome: we run F and it gives its true value.
    f_out = np.array([[-TRUTH["F"][0], TRUTH["F"][1]]])
    hvi = float(hvi_2d(torch.as_tensor(f_out, dtype=torch.float64), run_front, ref)[0])
    hv_after = float(hypervolume_2d(front_of({**RUN, "F": TRUTH["F"]})[1], ref))
    assert abs(hv_after - hv_run - hvi) < 1e-9                         # improvement = area gained
    res["hvi_F"] = hvi

    # Expected improvement of F by hand: four seeded draws from its prediction.
    mean_f = np.array([-PREDICTION["F"][0], PREDICTION["F"][1]])
    sd_f = np.array([PREDICTION["F"][2], PREDICTION["F"][3]])
    z = np.random.default_rng(HAND_SEED).standard_normal((HAND_DRAWS, 2))
    draws = mean_f + sd_f * z
    draw_hvi = hvi_2d(torch.as_tensor(draws, dtype=torch.float64), run_front, ref).numpy()
    res["hand"] = {"draws": [{"endurance": float(-d[0]), "mass": float(d[1]), "hvi": float(h)}
                             for d, h in zip(draws, draw_hvi)], "mean": float(draw_hvi.mean())}

    # Scores of the four candidates under each strategy.
    names = list(PREDICTION)
    m1 = np.array([-PREDICTION[n][0] for n in names])
    m2 = np.array([PREDICTION[n][1] for n in names])
    v1 = np.array([PREDICTION[n][2] ** 2 for n in names])
    v2 = np.array([PREDICTION[n][3] ** 2 for n in names])
    ehvi = {S: ehvi_mc(m1, v1, m2, v2, run_front, ref, n_samples=S) for S in (STUDY_SAMPLES, LONG_SAMPLES)}
    stand = max_variance(v1 / f_run[:, 0].var(), v2 / f_run[:, 1].var())
    p = np.array([P_FEASIBLE[n] for n in names])
    scores = {"ehvi": ehvi[STUDY_SAMPLES], "ehvi_long": ehvi[LONG_SAMPLES], "maxvar": stand,
              "p_feasible": p, "ehvi_times_p": ehvi[STUDY_SAMPLES] * p}
    res["candidates"] = {n: {k: float(v[i]) for k, v in scores.items()} for i, n in enumerate(names)}
    pick = {"plain EHVI": "ehvi", "maximum variance": "maxvar", "EHVI times P(feasible)": "ehvi_times_p"}
    res["picks"] = {label: names[int(np.argmax(scores[key]))] for label, key in pick.items()}

    # What running each candidate gives.
    outcomes = {}
    for n in names:
        if TRUTH[n] is None:
            outcomes[n] = {"result": "fails a gate: no result", "regret": res["regret_now"]}
        else:
            outcomes[n] = {"result": f"{TRUTH[n][0]:g} h at {TRUTH[n][1]:g} kg",
                           "regret": float(regret({**RUN, n: TRUTH[n]}, ref, hv_true))}
    res["outcomes"] = outcomes
    res["random_expected_regret"] = float(np.mean([o["regret"] for o in outcomes.values()]))
    res["settings"] = {"study_samples": STUDY_SAMPLES, "long_samples": LONG_SAMPLES,
                       "hand_draws": HAND_DRAWS, "hand_seed": HAND_SEED}
    return res, ref, run_front


# ---- figures ------------------------------------------------------------------------------------
BLUE, ACCENT, GREY = "#1F3A5F", "#C8551A", "#8A94A6"


def shade(ax, front, ref, color, alpha, label=None):
    """Shade the hypervolume of a front on axes of mass (x) and endurance (y), in horizontal bands."""
    t, m = -front[:, 0], front[:, 1]
    order = np.argsort(m)
    level, first = -ref[0], True
    for i in order:
        if t[i] > level:
            ax.fill_between([m[i], ref[1]], level, t[i], color=color, alpha=alpha, lw=0,
                            label=label if first else None)
            level, first = t[i], False


def base_axes(ref):
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=160)
    ax.set_xlabel("mass (kg)")
    ax.set_ylabel("endurance (h)")
    ax.set_xlim(0.8, 3.3)
    ax.set_ylim(3.0, 9.8)
    ax.grid(alpha=0.25)
    ax.scatter([ref[1]], [-ref[0]], marker="x", s=60, color=ACCENT, zorder=5, label="reference point")
    return fig, ax


def draw_run(ax):
    for n, (t, m) in RUN.items():
        ax.scatter([m], [t], s=40, color=BLUE, zorder=4)
        ax.annotate(n, (m, t), textcoords="offset points", xytext=(6, 5), fontsize=10)


def figure_hypervolume(res, ref, run_front, out):
    """The strips of Step 2, on axes of mass (x) and endurance (y), each labelled with its area."""
    fig, ax = base_axes(ref)
    t_ref = -ref[0]
    both_names, both = front_of({**RUN, "F": TRUTH["F"]})
    for row in strips(both, ref, both_names):                    # the area gained if F is run
        ax.fill_between([row["mass_from"], row["mass_to"]], t_ref, row["endurance_span"] + t_ref,
                        color=ACCENT, alpha=0.35, lw=0, label="gained if F is run" if row["design"] == "F" else None)
    for row, tint in zip(res["strips"], ("#9DB4D6", "#B7C8E2", "#8FA6CB")):
        ax.fill_between([row["mass_from"], row["mass_to"]], t_ref, row["endurance_span"] + t_ref,
                        color=tint, alpha=0.9, lw=0.8, edgecolor=BLUE,
                        label="hypervolume of the run designs" if row is res["strips"][0] else None)
        ax.text((row["mass_from"] + row["mass_to"]) / 2, t_ref + 0.12, f"{row['design']}: {row['area']:.3f}",
                ha="center", fontsize=8, color=BLUE)
    draw_run(ax)
    t, m = TRUTH["F"]
    ax.scatter([m], [t], s=50, facecolors="none", edgecolors=ACCENT, zorder=4)
    ax.annotate("F (not run)", (m, t), textcoords="offset points", xytext=(6, 5), fontsize=10)
    ax.legend(loc="upper left", fontsize=8, frameon=True)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def figure_candidates(res, ref, run_front, out):
    fig, ax = base_axes(ref)
    shade(ax, run_front, ref, "#9DB4D6", 0.8)
    draw_run(ax)
    for n, (mt, mm, st, sm) in PREDICTION.items():
        ax.errorbar([mm], [mt], xerr=sm, yerr=st, fmt="o", color=ACCENT, capsize=3, zorder=6)
        ax.annotate(n, (mm, mt), textcoords="offset points", xytext=(7, 6), fontsize=11, color=ACCENT)
        if TRUTH[n] is not None:
            ax.scatter([TRUTH[n][1]], [TRUTH[n][0]], marker="D", s=26, color="black", zorder=7)
    ax.scatter([], [], marker="o", color=ACCENT, label="prediction, one sd")
    ax.scatter([], [], marker="D", color="black", s=26, label="what the run would give")
    ax.legend(loc="upper left", fontsize=8, frameon=True)
    ax.text(2.3, 9.45, "H fails a gate: no result", fontsize=9, color=ACCENT)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def figure_scores(res, out):
    names = list(PREDICTION)
    panels = (("plain EHVI", "ehvi"), ("maximum variance (standardised)", "maxvar"),
              ("EHVI times P(feasible)", "ehvi_times_p"))
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.3), dpi=160)
    for ax, (title, key) in zip(axes, panels):
        vals = [res["candidates"][n][key] for n in names]
        best = int(np.argmax(vals))
        bars = ax.bar(names, vals, color=[ACCENT if i == best else GREY for i in range(len(names))])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}", ha="center", va="bottom", fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, max(vals) * 1.18)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


# ---- the walkthrough document -------------------------------------------------------------------
def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def write_document(res, rel_figures, path=DOC):
    r = res
    ref = r["ref"]
    cand = r["candidates"]
    picks = r["picks"]
    hand = r["hand"]
    dom = " ".join(f"{k} is worse than {v} on both goals." for k, v in r["dominated"].items())
    strip_rows = [[row["design"], f"{ref['endurance']:g} to {ref['endurance'] + row['endurance_span']:g}",
                   f"{row['endurance_span']:.2f}", f"{row['mass_from']:g} to {row['mass_to']:g}",
                   f"{row['mass_span']:.2f}", f"{row['area']:.3f}"] for row in r["strips"]]
    best_plain, best_var, best_w = picks["plain EHVI"], picks["maximum variance"], picks["EHVI times P(feasible)"]
    out_rows = [[n, o["result"], f"{o['regret']:.3f}"] for n, o in r["outcomes"].items()]
    pr = PREDICTION
    text = f"""# A worked example of active learning

This document shows the arithmetic behind slides 14 to 16 on a small problem with nine designs. The problem is a teaching example. It is not a study result. The script `analysis/toy_active_learning.py` computes each number with the study's own functions in `surrogate/acquisition.py`. The numbers below come from the script, and a test checks them.

## 1. The setting

Each design has two goals: more endurance and less mass. The code works with both goals in the form "smaller is better". It uses negative endurance and the mass. The study uses the logarithm of the mass. This example uses the mass itself, because it is easier to check by hand.

Five designs have run. Their results are known.

{table(["Design", "Endurance (h)", "Mass (kg)"], [[n, f"{t:g}", f"{m:g}"] for n, (t, m) in RUN.items()])}

Four designs have not run. We call them candidates. The model gives a prediction for each candidate: a mean and a spread (one standard deviation) for each goal. In the study, two Gaussian processes give these predictions. Here we choose them by hand, so that each one teaches a point.

{table(["Candidate", "Predicted endurance (h)", "Predicted mass (kg)", "P(feasible)"], [[n, f"{pr[n][0]:g} ± {pr[n][2]:g}", f"{pr[n][1]:g} ± {pr[n][3]:g}", f"{P_FEASIBLE[n]:g}"] for n in pr])}

We also know what each run would give. The strategies do not know this.

F would give {TRUTH['F'][0]:g} h at {TRUTH['F'][1]:g} kg. G would give {TRUTH['G'][0]:g} h at {TRUTH['G'][1]:g} kg. I would give {TRUTH['I'][0]:g} h at {TRUTH['I'][1]:g} kg. H fails a gate. A run of H gives no result.

## 2. Step 1: the front

A design is on the front if no other design is better on both goals. Here {dom} So the front of the run designs is {", ".join(r["run_front"])}.

## 3. Step 2: the hypervolume

The hypervolume is the area that the front covers, up to a reference point. The code takes the reference point from the worst value of each goal, plus a tenth of its range. Here it is {ref["endurance"]:g} h and {ref["mass"]:g} kg.

Sort the front from the best endurance to the worst. Each front design adds one strip. A strip is a rectangle in Figure 1. It spans the endurance from the reference point up to the design. It spans the mass from the design up to the previous strip. The first strip ends at the reference mass.

{table(["Design", "Endurance range (h)", "Endurance span (h)", "Mass range (kg)", "Mass span (kg)", "Area"], strip_rows)}

The hypervolume of the run designs is the sum of the three areas: {r["hv_run"]:.3f}. Figure 1 shows the strips in blue. The code adds the strips in the same way.

![Figure 1](figures/{rel_figures["hypervolume"]})

## 4. Step 3: the regret

The true front uses all clean designs: the five that have run and the three clean candidates. H is not clean, because it fails a gate. The true front is {", ".join(r["true_front"])}. Its hypervolume is {r["hv_true"]:.3f}.

Regret is the missing share: 1 − {r["hv_run"]:.3f} / {r["hv_true"]:.3f} = {r["regret_now"]:.3f}. A regret of 0 means we have the whole front.

## 5. Step 4: the improvement from one result

Suppose we run F and it gives its true value. The front gains the orange area in Figure 1. That area is the hypervolume improvement. Here it is {r["hvi_F"]:.3f}, the same as the new hypervolume minus the old one. The regret then falls to {r["outcomes"]["F"]["regret"]:.3f}.

## 6. Step 5: the expected improvement

Before the run, we do not know the result. We know only the prediction for F. So we draw possible results from the prediction, and we average their improvements. The table shows four draws.

{table(["Draw", "Endurance (h)", "Mass (kg)", "Improvement"], [[i + 1, f"{d['endurance']:.2f}", f"{d['mass']:.2f}", f"{d['hvi']:.3f}"] for i, d in enumerate(hand["draws"])])}

The mean of the four improvements is {hand["mean"]:.3f}. This is a rough estimate of the expected improvement of F. The study uses {r["settings"]["study_samples"]} draws. With {r["settings"]["study_samples"]} draws, the estimate for F is {cand["F"]["ehvi"]:.3f}. With {r["settings"]["long_samples"]:,} draws it is {cand["F"]["ehvi_long"]:.3f}. More draws make the estimate steadier.

## 7. Step 6: three strategies choose

Figure 2 shows the predictions. Each orange dot is a predicted mean. Its bars are one standard deviation. Each black diamond is what the run would give. H has no diamond, because it fails a gate.

Figure 3 shows the score of each candidate under three strategies. The orange bar is the choice of each strategy.

![Figure 2](figures/{rel_figures["candidates"]})

![Figure 3](figures/{rel_figures["scores"]})

The standardised variance is the sum of the two predicted variances. Each one is divided by the variance of that goal over the run designs. The study uses the scale that each Gaussian process sees.

{table(["Candidate", "EHVI", "Standardised variance", "P(feasible)", "EHVI × P"], [[n, f"{c['ehvi']:.3f}", f"{c['maxvar']:.2f}", f"{c['p_feasible']:g}", f"{c['ehvi_times_p']:.3f}"] for n, c in cand.items()])}

Plain EHVI chooses {best_plain}. The model predicts that {best_plain} has a long endurance at a low mass, so its expected improvement is large. The model does not know that {best_plain} fails a gate.

Maximum variance chooses {best_var}. The model is least sure about {best_var}. It does not ask if {best_var} is a good design.

EHVI times P(feasible) chooses {best_w}. The small value of P(feasible) for H removes H from the race.

Random choice and the Latin hypercube use no model. Random choice picks one of the four candidates with equal chance.

## 8. Step 7: what each choice costs

{table(["If we run", "Result", "Regret after"], out_rows)}

Plain EHVI wastes its run on H. The regret stays at {r["regret_now"]:.3f}. Maximum variance wastes its run on I, a design that the front already beats. Only {best_w} closes the gap, to {r["outcomes"][best_w]["regret"]:.3f}. Random choice has an expected regret of {r["random_expected_regret"]:.3f}.

## 9. How this maps to the slides

- Slide 14 shows the equations for the improvement of one result (Step 4), the expected improvement (Step 5) and the maximum variance score (Step 6).
- Slide 15 uses regret (Step 3) on a pool where no design fails a gate. Here the plain method does well.
- Slide 16 is the open box. Some designs fail a gate. The plain method then picks designs like H, and it loses. The feasibility weight (Step 6) fixes that.
- Backup slide 41 defines the hypervolume and the regret (Steps 2 and 3).

## 10. What the study does differently

- The two goals are endurance and the logarithm of the mass.
- Two Gaussian processes give the predictions. They are fitted on the runs so far, and they change after each run.
- The inputs are six numbers, not the names A to I.
- A logistic regression gives P(feasible) from the gate results so far.
- The study draws {r["settings"]["study_samples"]} samples for each candidate. This is the number that Steps 5 and 6 use for EHVI.

## 11. Check yourself

1. Why does a design that the front already beats add nothing? Answer: it adds no area to the front, so its improvement is 0.
2. Why does maximum variance choose I? Answer: I has the largest spread, and the score counts only spread.
3. Why does P(feasible) help on the open box? Answer: it lowers the score of designs that the model likes but that fail a gate.
4. What does a regret of 0 mean? Answer: the run designs already give the whole true front.
"""
    Path(path).write_text(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res, ref, run_front = compute()
    figs = {"hypervolume": "toy_hypervolume.png", "candidates": "toy_candidates.png",
            "scores": "toy_scores.png"}
    figure_hypervolume(res, ref, run_front, out / figs["hypervolume"])
    figure_candidates(res, ref, run_front, out / figs["candidates"])
    figure_scores(res, out / figs["scores"])
    (out / "toy.json").write_text(json.dumps(res, indent=1) + "\n")
    fig_dir = DOC.parent / "figures" / "toy"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for name in figs.values():
        (fig_dir / name).write_bytes((out / name).read_bytes())
    write_document(res, {k: f"toy/{v}" for k, v in figs.items()})
    print(json.dumps({k: res[k] for k in ("hv_run", "hv_true", "regret_now", "hvi_F", "picks")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

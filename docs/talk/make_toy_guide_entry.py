"""Put the worked example of active learning into the study guide as entry 19A.

    python -m docs.talk.make_toy_guide_entry

Reads runs/toy_active_learning/2026-11-13/toy.json (written by analysis/toy_active_learning.py) and
the three figures beside it. Every number of the entry comes from that record. The entry sits between
the markers TOY_START and TOY_END in docs/talk/study_guide_drone.html, before entry 20. The first run
inserts it, and every later run replaces what is between the markers, so the script is safe to repeat.
The text uses ASD-STE100 Simplified Technical English.
"""
import base64
import json
from pathlib import Path

from analysis import toy_active_learning as toy

ROOT = Path(__file__).resolve().parents[2]
RUN_DIR = ROOT / "runs" / "toy_active_learning" / "2026-11-13"
GUIDE = ROOT / "docs" / "talk" / "study_guide_drone.html"
START, END = "<!-- TOY_START -->", "<!-- TOY_END -->"
CSS_OLD = "figure.gpfig svg{display:block;width:100%;height:auto}"
CSS_NEW = CSS_OLD + "\nfigure.gpfig img{display:block;width:100%;height:auto}"


def figure(name, number, caption):
    data = base64.b64encode((RUN_DIR / name).read_bytes()).decode()
    return (f'<figure class="gpfig"><img alt="Figure {number}" src="data:image/png;base64,{data}">'
            f"<figcaption>Figure {number}. {caption}</figcaption></figure>")


def table(header, rows):
    head = "".join(f"<th>{h}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table class="vars"><tr>{head}</tr>{body}</table></div>'


def qa(question, answer):
    return f'<details><summary>{question}</summary><p class="a">{answer}</p></details>'


def build_entry(res):
    r, ref, c, h = res, res["ref"], res["candidates"], res["hand"]
    pr = toy.PREDICTION
    s = res["settings"]
    run_rows = [[n, f"{t:g}", f"{m:g}"] for n, (t, m) in toy.RUN.items()]
    cand_rows = [[n, f"{pr[n][0]:g} ± {pr[n][2]:g}", f"{pr[n][1]:g} ± {pr[n][3]:g}", f"{toy.P_FEASIBLE[n]:g}"]
                 for n in pr]
    strip_rows = [[x["design"], f"{ref['endurance']:g} to {ref['endurance'] + x['endurance_span']:g}",
                   f"{x['endurance_span']:.2f}", f"{x['mass_from']:g} to {x['mass_to']:g}",
                   f"{x['mass_span']:.2f}", f"{x['area']:.3f}"] for x in r["strips"]]
    draw_rows = [[i + 1, f"{d['endurance']:.2f}", f"{d['mass']:.2f}", f"{d['hvi']:.3f}"]
                 for i, d in enumerate(h["draws"])]
    score_rows = [[n, f"{v['ehvi']:.3f}", f"{v['maxvar']:.2f}", f"{v['p_feasible']:g}", f"{v['ehvi_times_p']:.3f}"]
                  for n, v in c.items()]
    cost_rows = [[n, o["result"], f"{o['regret']:.3f}"] for n, o in r["outcomes"].items()]
    dom = " ".join(f"{k} is worse than {v} on both goals." for k, v in r["dominated"].items())
    plain, var, weighted = r["picks"]["plain EHVI"], r["picks"]["maximum variance"], r["picks"]["EHVI times P(feasible)"]
    var_rows = [
        ["t, m", "endurance (h) and mass (kg) of a design", "the two goals are −t and m: <code>goals()</code>"],
        ["P", "the front of the designs that have run", "<code>front_of(RUN)</code>, <code>pareto_front</code>"],
        ["r", "reference point: worst value of each goal plus a tenth of its range",
         "<code>ref_point(F)</code>"],
        ["HV(P)", "area that the front covers, up to r", "<code>hypervolume_2d(front, ref)</code>"],
        ["HVI(y)", "area that a new result y adds", "<code>hvi_2d(points, front, ref)</code>"],
        ["μ, σ²", "predicted mean and variance of each goal at a candidate",
         "two Gaussian processes in the study; chosen by hand here"],
        ["S", f"number of random draws ({s['study_samples']} in the study)", "<code>n_samples</code>"],
        ["p(x)", "probability that the design passes the gates", "<code>surrogate/feasibility.py</code> in the study"],
    ]
    return f"""{START}
<section class="entry" id="g19a"><header><input type="checkbox" data-id="g19a" id="k19a"><h3><label for="k19a">19A. A worked example: front, hypervolume, regret and three strategies on nine designs</label></h3></header>
<p class="where"><b>In the talk:</b> drone deck version 3, slides 14 to 16 and backup slide 41. <b>Version 3:</b> slides 14, 15 and 16. <b>Record:</b> <code>runs/toy_active_learning/2026-11-13/toy.json</code>; code <code>analysis/toy_active_learning.py</code> and <code>surrogate/acquisition.py</code>; full walkthrough <code>docs/talk/active_learning_worked_example.md</code>. This entry uses ASD-STE100 Simplified Technical English. It is a teaching example, not a study result.</p>
<span class="lbl">Definition</span>
<p>Active learning uses a model's predictions to pick the next design to run. This example has nine designs and two goals. It shows each step of the arithmetic behind slides 14 to 16. The study's own code gives every number.</p>
<p>Read the entry with a pen. Redo steps 2 to 5 yourself, and then check your numbers against the tables.</p>
<span class="lbl">The setting</span>
<p>Each design has two goals: more endurance and less mass. The code works with "smaller is better", so it uses negative endurance and the mass. The study uses the logarithm of the mass. The example uses the mass itself, because it is easier to check by hand.</p>
<p>Five designs have run. Their results are known.</p>
{table(["Design", "Endurance (h)", "Mass (kg)"], run_rows)}
<p>Four designs have not run. We call them candidates. The model gives a mean and a spread (one standard deviation) for each goal. In the study, two Gaussian processes give these predictions. Here we choose them by hand, so that each one teaches a point.</p>
{table(["Candidate", "Predicted endurance (h)", "Predicted mass (kg)", "P(feasible)"], cand_rows)}
<p>We also know what each run would give. The strategies do not know this. F would give {toy.TRUTH["F"][0]:g} h at {toy.TRUTH["F"][1]:g} kg. G would give {toy.TRUTH["G"][0]:g} h at {toy.TRUTH["G"][1]:g} kg. I would give {toy.TRUTH["I"][0]:g} h at {toy.TRUTH["I"][1]:g} kg. H fails a gate, so a run of H gives no result.</p>
<span class="lbl">Step 1: the front</span>
<p>A design is on the front if no other design is better on both goals. {dom} So the front of the run designs is {", ".join(r["run_front"])}.</p>
<span class="lbl">Step 2: the hypervolume</span>
<p>The hypervolume is the area that the front covers, up to a reference point. Here the reference point is {ref["endurance"]:g} h and {ref["mass"]:g} kg.</p>
<p>Sort the front from the best endurance to the worst. Each front design adds one strip. The strip spans the endurance from the reference point up to the design. It spans the mass from the design up to the previous strip. The first strip ends at the reference mass.</p>
<div class="eq">\\[ \\mathrm{{HV}}(P)=\\sum_{{k}}\\big(t_k-t_{{\\mathrm{{ref}}}}\\big)\\big(m_{{k-1}}-m_k\\big),\\qquad m_0=m_{{\\mathrm{{ref}}}} \\]</div>
{table(["Design", "Endurance range (h)", "Endurance span (h)", "Mass range (kg)", "Mass span (kg)", "Area"], strip_rows)}
<p>The hypervolume of the run designs is the sum of the three areas: <b>{r["hv_run"]:.3f}</b>.</p>
{figure("toy_hypervolume.png", 1, "The three strips of the front, with their areas. The orange area is what the front gains if F is run.")}
<span class="lbl">Step 3: the regret</span>
<p>The true front uses all clean designs: the five that have run and the three clean candidates. H is not clean, because it fails a gate. The true front is {", ".join(r["true_front"])}. Its hypervolume is <b>{r["hv_true"]:.3f}</b>. Regret is the missing share of that area.</p>
<div class="eq">\\[ \\mathrm{{regret}}=\\frac{{\\mathrm{{HV}}(P^{{*}})-\\mathrm{{HV}}(P)}}{{\\mathrm{{HV}}(P^{{*}})}}=1-\\frac{{{r["hv_run"]:.3f}}}{{{r["hv_true"]:.3f}}}={r["regret_now"]:.3f} \\]</div>
<p>A regret of 0 means that the run designs already give the whole true front.</p>
<span class="lbl">Step 4: the improvement from one result</span>
<p>Suppose we run F, and it gives its true value. The front gains the orange area in Figure 1. That area is the hypervolume improvement.</p>
<div class="eq">\\[ \\mathrm{{HVI}}(y)=\\mathrm{{HV}}(P\\cup\\{{y\\}})-\\mathrm{{HV}}(P)={r["hv_true"]:.3f}-{r["hv_run"]:.3f}={r["hvi_F"]:.3f} \\]</div>
<p>The regret then falls to {r["outcomes"]["F"]["regret"]:.3f}.</p>
<span class="lbl">Step 5: the expected improvement</span>
<p>Before the run, we do not know the result. We know only the prediction for F. So we draw possible results from the prediction, and we average their improvements.</p>
<div class="eq">\\[ \\mathrm{{EHVI}}(x)\\approx\\frac{{1}}{{S}}\\sum_{{s=1}}^{{S}}\\mathrm{{HVI}}(y_s),\\qquad y_s\\sim\\mathcal{{N}}(\\mu,\\mathrm{{diag}}\\,\\sigma^{{2}}) \\]</div>
{table(["Draw", "Endurance (h)", "Mass (kg)", "Improvement"], draw_rows)}
<p>The mean of the four improvements is {h["mean"]:.3f}. This is a rough estimate of the expected improvement of F. The study uses {s["study_samples"]} draws. With {s["study_samples"]} draws, the estimate for F is {c["F"]["ehvi"]:.3f}. With {s["long_samples"]:,} draws, it is {c["F"]["ehvi_long"]:.3f}. More draws make the estimate steadier.</p>
<span class="lbl">Step 6: three strategies choose</span>
<p>Figure 2 shows the predictions. Each orange dot is a predicted mean. Its bars are one standard deviation. Each black diamond is what the run would give. H has no diamond, because it fails a gate.</p>
{figure("toy_candidates.png", 2, "The predictions of the model for the four candidates, over the area that the front covers now.")}
<p>The standardised variance of a candidate is the sum of the two predicted variances. Each one is divided by the variance of that goal over the run designs. The study uses the scale that each Gaussian process sees.</p>
{table(["Candidate", "EHVI", "Standardised variance", "P(feasible)", "EHVI × P"], score_rows)}
{figure("toy_scores.png", 3, "The score of each candidate under three strategies. The orange bar is the choice of the strategy.")}
<p>Plain EHVI chooses {plain}. The model predicts that {plain} has a long endurance at a low mass, so its expected improvement is large. The model does not know that {plain} fails a gate.</p>
<p>Maximum variance chooses {var}. The model is least sure about {var}. The score does not ask if {var} is a good design.</p>
<p>EHVI times P(feasible) chooses {weighted}. The small value of P(feasible) for H removes H from the race.</p>
<span class="lbl">Step 7: what each choice costs</span>
{table(["If we run", "Result", "Regret after"], cost_rows)}
<p>Plain EHVI wastes its run on {plain}. The regret stays at {r["regret_now"]:.3f}. Maximum variance wastes its run on {var}, a design that the front already beats. Only {weighted} closes the gap, to {r["outcomes"][weighted]["regret"]:.3f}. Random choice has an expected regret of {r["random_expected_regret"]:.3f}.</p>
<span class="lbl">How this maps to the slides</span>
<p>Slide 14 shows the equations of Steps 4, 5 and 6. Slide 15 uses regret on a pool where no design fails a gate. There, the plain method does well.</p>
<p>Slide 16 is the open box, where some designs fail a gate. The plain method then picks designs like H, and it loses. The feasibility weight fixes that. Backup slide 41 defines the hypervolume and the regret.</p>
<span class="lbl">Variables</span>
{table(["Symbol", "Meaning", "In the code"], var_rows)}
<p><strong>What the study does differently.</strong> The two goals are endurance and the logarithm of the mass. Two Gaussian processes give the predictions. They are fitted on the runs so far, and they change after each run. The inputs are six numbers, not the names A to I. A logistic regression gives P(feasible) from the gate results so far.</p>
<details><summary>Check yourself</summary>
{qa("Why does a design that the front already beats add nothing?", "It adds no area to the front, so its improvement is 0.")}
{qa("Why does maximum variance choose I?", "I has the largest spread, and the score counts only spread.")}
{qa("Why does P(feasible) help on the open box?", "It lowers the score of designs that the model likes but that fail a gate.")}
{qa("What does a regret of 0 mean?", "The run designs already give the whole true front.")}
</details>
<details><summary>Interview questions</summary>
{qa("Explain expected hypervolume improvement in two sentences.", "It is the average area that a design would add to the front, over the results that the model thinks are possible. A design scores high when it is predicted to be good, or when it is uncertain and a good result is possible.")}
{qa("Why did plain EHVI lose on the open box?", "It picked designs that looked very good to the model but failed a gate, like H. Those runs gave no result, so the front did not grow.")}
{qa("What is wrong with maximum variance as a strategy?", "It explores the whole box and ignores the goal. It can spend a run on a design that the front already beats, like I.")}
{qa("Is this example evidence that active learning works?", "No. The predictions are chosen by hand to teach each step. The evidence is the pool and open-box replays on slides 15 and 16.")}
</details>
</section>
{END}
"""


def inject(path=GUIDE, res=None):
    """Insert or replace entry 19A in the guide at `path`. Returns the new text."""
    res = res or json.loads((RUN_DIR / "toy.json").read_text())
    text = Path(path).read_text()
    entry = build_entry(res)
    if START in text:
        head, rest = text.split(START, 1)
        text = head + entry.rstrip("\n") + rest.split(END, 1)[1]
    else:
        anchor = '<section class="entry" id="g20"'
        assert text.count(anchor) == 1, "entry 20 not found"
        text = text.replace(anchor, entry + "\n" + anchor)
    if CSS_NEW not in text:
        assert text.count(CSS_OLD) == 1, "figure CSS not found"
        text = text.replace(CSS_OLD, CSS_NEW)
    return text


if __name__ == "__main__":
    GUIDE.write_text(inject())
    print(f"entry 19A written to {GUIDE.relative_to(ROOT)}")

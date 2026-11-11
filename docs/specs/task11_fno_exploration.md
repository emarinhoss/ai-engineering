# Task 11 (exploratory): could a Fourier neural operator cut the SU2 cost here?

Written 2026-11-10 at Éder's request. **Nothing in this note was run.** It reads the results of a
separate public study, `emarinhoss/airfoil-pinn-no` (commit `6f65e8c`), and reasons about what they
imply for this pipeline. Every number about that study is from its `README.md`,
`docs/findings.md`, `results/s2/` or `results/s4/`. Every number about this study is from the
Task 10 records. Anything not measured is marked as a guess.

## 1. What the other study measured

It trained a Fourier neural operator (FNO) to predict the whole flow field around NACA four-digit
airfoils, and scored it against SU2 with one force integrator.

| | Other study | This study |
|---|---|---|
| Flow model | Euler (inviscid, compressible), SU2 8.5.0 | Incompressible RANS, SA with BCM transition, SU2 8.2.0 |
| Inputs | Mach 0.30 to 0.80, alpha −2 to 6 deg, thickness, camber | camber, thickness, Reynolds number 87,400 to 269,000, alpha −2 to 14 deg |
| Mesh | O-grid, 128×49 to 512×193 | C-mesh with a wake cut; first cell at y+ 0.5 |
| What is needed from a run | the field | two numbers per run: cl and cd |
| SU2 cost per case | 210 CPU-seconds | coarse 705 s and medium 1,372 s (medians), fine 3,162 s (one case), on 4 ranks (deck DB12) |
| Cases run | 896 for training | 172 in the pool, 37 worker-hours in total |

Its findings that matter here:

1. **Break-even.** The FNO costs 0.054 s per case against SU2's 210 s, but its fixed cost (the
   896-case campaign, tuning and training) is 236,237 s. It pays back only after **1,126 new cases**.
2. **Accuracy in range.** With 896 training cases and no shock, at the training resolution, the
   FNO's largest lift error is 0.0095 and its largest drag error 7.5 counts, about the same as
   SU2's own coarse-grid error. With a shock: 0.031 and 47 counts.
3. **Data hunger.** With 64 training cases the same figures are 0.042 and 79 counts (no shock).
4. **Resolution transfer is not free.** Trained at 128×49 and evaluated at 256×97, the no-shock
   error rises about fourfold (field error 0.010 to 0.042; lift 0.031; drag 31 counts). A simpler
   method (POD with interpolation) beats the FNO there. The study calls this the largest single
   loss in range.
5. **Outside the training range** drag errors reach 181 counts and are biased, not scattered.
6. **Sharp features are smeared.** The FNO misses 1 to 2 of 27 shocks and overshoots at the rest.
7. The physics-informed network (PINN) was not competitive: 26 to 65 times the reference error.

## 2. What that implies for this pipeline

**Replacing SU2 with an FNO does not pay at this study's size.** The pool is 172 cases. A training
campaign of about 900 coarse cases would cost about 176 worker-hours (900 × 705 s), close to five
times everything SU2 cost here, before the first prediction. The other study needed 1,126 uses to
break even on a cheaper solver; this study makes a few hundred.

**The accuracy is likely worse here than there**, for four reasons. These are arguments, not
measurements.

- *Drag.* Section drag here is about 100 to 200 counts at the low angles that set endurance. An error of 30 counts, which the other
  study saw at a transferred resolution, is 15 to 30 % of the answer. SU2's own drag bias against
  the tunnel is 8.0 %.
- *The boundary layer.* Viscous drag comes from the velocity gradient in cells 1/1000 of a chord
  thick. A truncated Fourier series smooths exactly that region.
- *Transition and separation.* A laminar separation bubble or a transition front is a sharp,
  moving feature, like the shocks the FNO smeared and sometimes missed.
- *The mesh.* The other study's FNO relies on the O-grid being periodic around the airfoil. A
  C-mesh with a wake cut is not, so the exact part of that construction is lost.

**The existing records cannot train a field model.** Runs here keep cl, cd and the convergence
history. The repo holds 15 surface files and one volume field. A field FNO would need a new
campaign with volume output on.

**The pipeline does not need fields.** It needs cl and cd as functions of four inputs. A Gaussian
process on those scalars is what the two-level model already is, and it works with 8 to 32 designs.
An FNO learns tens of thousands of field values per case to deliver two numbers.

## 3. Where an operator could still help

Three uses keep SU2 as the source of every reported number, which the repo rules require.

**A. Warm start (the most promising).** The FNO predicts the field; SU2 starts from it instead of
from the free stream and runs to its own Cauchy stop. The answer is SU2's, every gate still
applies, and a bad prediction costs time, not correctness. The medium runs took 4,100 to 5,000
iterations from the free stream, and the fine ones are budgeted 12,000. *Guess:* a good start saves
a third to a half. This is unmeasured, and steady RANS with transition may spend most of its
iterations on slow modes that a good start does not remove.

**B. Coarse-to-fine correction.** Train an operator from a coarse solution to the fine one, so a
coarse run plus a correction stands in for a fine run. This attacks the resolution cost directly.
But it needs paired coarse and fine fields (fine costs 3,162 s or more each), and finding 4 above
says resolution transfer is where the FNO was weakest. The corrected result would be a prediction,
so it could only be a third fidelity level, never the reported answer.

**C. A section model for the whole design space.** The low model evaluated 531,441 designs in
4.7 hours. If a learned section model at SU2 level replaced its closed-form section, the number of
uses would pass any break-even. But the same job can be done by a GP on (camber, thickness,
Reynolds number, alpha) → (cl, cd) trained on the SU2 cases already recorded. That baseline has to
be beaten first, as POD had to be in the other study.

## 4. A way to try it here, cheapest test first

Each step has a pass condition fixed before it runs. A step that fails stops the line and is
reported as a result.

| Step | What | New SU2 cost | Pass condition |
|---|---|---|---|
| E0 | **Ceiling of a warm start, no machine learning.** Restart one design's cases from a neighbouring converged solution: the next angle, and the coarse solution interpolated onto the medium mesh. Count iterations to the Cauchy stop against the recorded cold starts. | about 10 cases with volume output, 2 to 4 worker-hours | iterations fall by at least 30 %; cl and cd within the run's own drift of the cold-start values |
| E1 | **Scalar baseline.** GP on the recorded pool cases, section inputs to cl and cd, leave-one-design-out. | none | sets the error an FNO must beat |
| E2 | **Small field campaign.** Re-run about 64 pool cases with volume output; train the other repo's FNO adapted to the C-mesh; score fields and forces with this repo's integrator. | about 13 worker-hours | integrated cl and cd no worse than E1 on held-out designs |
| E3 | **FNO warm start.** Start held-out cases from the FNO field. | about 20 cases | saves at least as many iterations as E0's neighbour restart |

E0 decides most of the question. If restarting from a real neighbouring solution does not save
30 %, no learned start will, and the line stops after a few worker-hours. If it does, the neighbour
restart is itself a speed-up that needs no training and can go into the worker as it is.

### E0 as it will run (Éder, 2026-11-10: "run E0 once the fine cases finish"), fixed before any case

Section: pool design 1 (Re 170,203.9), chosen because its recorded coarse and medium runs at 2, 6 and
10 deg all stopped on the Cauchy rule (coarse 3,447 / 3,654 / 4,083 iterations; medium 5,040 / 4,999 /
4,429). Those records were meshed before decision 11, so they are context only: every comparison
below is between new runs on the current mesher. Twelve cases, tag `e0`, budget 6,000 each.

| Batch | Cases | Start |
|---|---|---|
| A, cold | coarse at 2, 6, 10 deg, writing a restart file | free stream |
| A, cold | medium at 2, 6, 10 deg | free stream |
| B, angle step | coarse 6 from coarse 2; coarse 10 from coarse 6; coarse 2 from coarse 6 | neighbour angle, same mesh |
| B, mesh step | medium at 2, 6, 10 deg | coarse solution at the same angle, nearest-neighbour onto the medium mesh |

For each warm case and its cold twin (same params except the start): iterations to the Cauchy
stop, wall time, cl and cd. **Pass**, per kind of start: the median iteration count falls by at
least 30 %, and every warm cl and cd is within the cold twin's own recorded drift of the cold value.
A warm run that exhausts its budget, or a cold twin that does, is reported and counted as no
saving. Wall time is reported beside iterations; the cost of the donor run is charged to the
mesh step (a coarse run is needed first) and not to the angle step (the donor is a case the polar
needs anyway). The restart feature this needs (`save_restart`, `restart_from`) is new worker code
and is smoke-tested on one short case before the batch is staged.

### E0 result (2026-11-11): FAIL for both kinds of start

Record: `runs/e0/` (twelve cases), `runs/e0_analysis/2026-11-11/e0.json`, made by
`python -m analysis.e0_warmstart --out runs/e0_analysis/2026-11-11` with the rule above, unchanged.
All twelve runs exited 0 and stopped on the Cauchy rule inside the 6,000 budget, so no pair counts as
"no saving" by exhaustion. Each runtime ran two 4-rank jobs at a time, for cold and warm alike.

| Kind | Warm case | Iterations warm / cold | Saving | cl diff / allowed | cd diff / allowed |
|---|---|---|---|---|---|
| angle step | 6 deg from 2 | 2,562 / 3,654 | 29.9 % | 0.59 / 1.59 % | 1.66 / 4.37 % |
| angle step | 10 deg from 6 | 3,935 / 4,077 | 3.5 % | 0.03 / 1.21 % | 0.12 / 3.80 % |
| angle step | 2 deg from 6 | 3,498 / 3,447 | -1.5 % | 0.25 / 1.44 % | **4.24 / 2.29 %** |
| mesh step | medium 2 deg from coarse 2 | 932 / 5,040 | 81.5 % | 1.21 / 1.51 % | **2.23 / 1.60 %** |
| mesh step | medium 6 deg from coarse 6 | 1,045 / 4,999 | 79.1 % | 0.99 / 2.20 % | 3.63 / 5.47 % |
| mesh step | medium 10 deg from coarse 10 | 837 / 4,429 | 81.1 % | 0.56 / 1.57 % | 2.51 / 4.41 % |

- **Angle step: fail on both halves.** Median iteration saving 3.5 % against 30 %, and the 2-degree
  warm drag is 4.24 % from its cold twin against that twin's 2.29 % drift.
- **Mesh step: fail on the force half only.** Median iteration saving 81.1 %, far above 30 %, but the
  2-degree warm drag is 2.23 % from its cold twin against that twin's 1.60 % drift. The rule says
  "every", so one miss fails the kind. Wall time with the donor charged falls by a median 29.5 %.
- **Observations, reported and not used to change the verdict.** The warm runs end with far smaller
  drift of their own (cd 0.1 to 0.5 % on the mesh step, against 1.6 to 5.5 % for the cold twins), so
  the two answers of a pair are not equally settled, and the rule compares the warm value against the
  cold run's drift only. Every mesh-step warm cd is below its cold twin (2.2 to 3.6 %). Wall times were
  measured with two jobs per 8-core runtime and are noisier than the iteration counts; the 2-degree
  angle step ran more iterations than its twin yet reports a 40 % shorter wall time.
- **What the result does not show.** Three angles of one section, at one Reynolds number. A rule that
  compared both runs against a common converged reference, or allowed the warm run's own drift, is a
  different test and would have to be fixed before any new run; it is not applied here.
- **By section 4, the line stops:** E1 to E3 are not run. The ruling to open a new test, if any, is
  Éder's.

Cost: the two Colab CPU runtimes that ran the decision 11 E387 cases and E0 used 5.50 compute units
(balance 478.94 before, 473.44 after); both were stopped on 2026-11-11.

### Where the iterations go (2026-11-11, analysis of recorded histories; nothing was re-run)

`analysis/history_cost.py` over the 230 finished airfoil2d runs on the Drive queue (every one exit 0;
record `runs/history_cost/2026-11-11/history_cost_pool.json`, sha256 `511a0731...`, computed on a
Colab runtime from each run's `history.csv`, `case.cfg` and `result.json`). 224 cold starts (183
stopped on the Cauchy rule, 41 used the whole budget) and the 6 warm starts of E0.

- **CFL ceiling.** Every run has `CFL_ADAPT_PARAM` ceiling 20 and reaches it at iteration 61. The
  Cauchy-stopped cold runs then sit at the ceiling for a median 98.4 % of the run (least 88.2 %).
- **Linear solver.** Every run asks for 1E-6 with a cap of 15. No run reaches the cap on any step;
  the mean is 9.8 to 11.7 FGMRES iterations per step (median 10.7), reaching about 10^-6.26.
- **No tail to trim.** In the Cauchy-stopped cold runs, cd is still outside 1 % of its final value at
  a median 87.5 % of the run (cl: 85.5 %); the run stops a median 582 iterations after cd enters that
  band. The budget-exhausted runs are worse: a median 96.9 %.

So the cost is a long transient marched at a capped pseudo-time step, with each step solved to a
tight linear tolerance. The stop rule is not what waits. This says where to test (the CFL ceiling,
then the linear tolerance); it does not say what either change would save, or that the answer would
be unchanged. Any such test needs its pass rule fixed first, against a tightly converged reference.

### Experiment S1/S2: a larger CFL ceiling and a looser linear tolerance. APPROVED 2026-11-11

Drafted 2026-11-11 at Éder's request ("yes, draft the rule") and approved by Éder the same day:
"approved as written, go ahead". The block is frozen from that approval: a change to it after the
first case starts is recorded beside the original, with its date and reason, and never replaces it.
The parameters are `cfl_max`, `linear_tol`, `cauchy_elems` and `cauchy_eps` (`mcp_server/schemas.py`,
`cases/config.py`); the cases are staged by `designs/make_s12.py`.

**Question.** Do a higher `CFL_ADAPT_PARAM` ceiling (S1) or a looser `LINEAR_SOLVER_ERROR` (S2) cut
the wall time of an airfoil2d run by at least 30 % without moving its lift and drag?

**Cases (five, fixed).** Pool design 1 (Re 170,203.9, the E0 section) on the coarse mesh at 2, 6 and
10 deg and on the medium mesh at 6 deg; the E387 at Re 203,800, 4.23 deg, medium mesh (a tunnel
angle). All on the current mesher. Angles above 10 deg and stalled flow are not tested.

**Settings.** One thing changes at a time; everything else is the recorded config.

| Set | CFL ceiling | Linear tolerance | Runs |
|---|---|---|---|
| reference | 20 | 1E-6 | 5, with a tighter stop (below) |
| baseline | 20 | 1E-6 | 5, each run twice |
| S1 | 50, 100, 250 | 1E-6 | 15 |
| S2 | 20 | 1E-4, 1E-2 | 10 |

**Reference.** The same case with today's numerics and a stop that waits longer: budget 20,000 (the
schema's maximum), Cauchy window 500 elements at 1E-7. A reference is valid only if it exits 0,
stops on that rule inside its budget, and its own recorded drift of cl and of cd is below 0.2 %
(`DRIFT_MAX` in `postprocess/history.py`, the classifier's existing limit). A case without a valid
reference is reported and takes no part in a verdict; a verdict needs at least four valid cases.

**Pass, per setting (each ceiling and each tolerance is judged on its own). All three must hold:**

1. *It runs.* Every case exits 0 and stops on the standard Cauchy rule inside the standard budget
   of 6,000. One diverged or budget-exhausted run fails the setting.
2. *The answer does not move.* For every case, the distance of cl from the reference cl is no larger
   than the larger of (the baseline's distance, 0.5 %); the same for cd with 1.0 %. The baseline's
   distance is the larger of its two repeats. "Every" means one miss fails the setting.
3. *It is faster.* The median over the cases of the wall-time saving against the mean of the two
   baseline repeats is at least 30 %. Wall time is the measure, not iterations, because a looser
   linear solve can need more iterations and still take less time; iterations and time per
   iteration are reported beside it.

**How it runs.** One job per runtime at a time, 4 ranks, the same runtime shape for every run, so
that wall times compare. The spread between the two baseline repeats is reported as the noise of
the measurement; a saving smaller than three times the largest spread is reported as not resolved,
whatever its size.

**If more than one setting passes.** The one with the largest median saving is the candidate; a tie
(within the noise above) goes to the setting nearer today's. If an S1 and an S2 setting both pass,
one more set of five runs tests the pair together, under the same three conditions.

**What a pass allows, and what it does not.** A pass allows a proposal to change the default for
future runs; adopting it is Éder's ruling. It does not change any recorded run, and runs at a new
setting are never mixed with the recorded pool in one table without saying so: the config hash
differs. Before a new setting is used for a study answer, the V6e tunnel rows are run again at that
setting and reported, pass or fail. A pass is for the tested range only (attached flow, 2 to 10 deg,
these two mesh levels).

**New code this needs (smoke-tested on one short case before any batch is staged).** Three optional
airfoil2d parameters, absent by default so that existing case ids and config hashes do not change
(the pattern of `save_restart`): the CFL ceiling, the linear tolerance, and the Cauchy window and
threshold for the reference runs.

**Cost (a guess, not measured).** 40 runs. With one job per runtime, about 15 worker-hours, or
about 8 hours of wall time on two runtimes and about 4 compute units.

## 5. Pros and cons

| For | Against |
|---|---|
| Prediction costs milliseconds once trained | Fixed cost is about 900 cases; this study uses 172 |
| As a warm start it cannot corrupt a result | The saving is unmeasured and may be small for this solver |
| Code, scorer and lessons exist in the other repo | Different flow model, mesh and solver version: the trained weights do not transfer |
| Gives fields (pressure, friction), not only forces | The pipeline does not use fields |
| | Drag accuracy is likely worse than SU2's own bias |
| | Unreliable outside its training range, with a biased error |
| | A second model to validate, gate and explain line by line |

## 6. Recommendation

Do not replace SU2 runs with an FNO in this study. Run E0, which needs no model, and decide from
its result. The option most likely to pay is the plainest: restart each case from its neighbour or
from the coarser mesh.

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

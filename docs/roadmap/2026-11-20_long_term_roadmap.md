# Long-term roadmap: suggestions from a review against the book library (2026-11-20)

**Status: proposal. Nothing in this note was run.** It is a list of suggested changes and new
work, written for Éder to accept, cut or reorder. No number below is a result of this study unless
it names the record it was read from. Numbers quoted from books are printed values to be used as
test targets. Three numbers are hand arithmetic and are marked as such; they need a recorded run
before they are used anywhere else.

Branch: `claude/dazzling-edison-2q0tb7`. Nothing on `main` is changed by this note.

## 0. How this was made and how to read it

The study as it stands on `main` (commit `d653fbe`) was read first: `PLAN.md`, the specs in
`docs/specs/`, the reports in `docs/validation/`, and the code in `drone/`, `surrogate/`,
`analysis/`, `geometry/` and `postprocess/`. Then Éder's own technical library (chapter notes of
published textbooks, kept in a separate private repository) was searched for methods, checks and
printed worked examples that bear on what the study does or could do next.

Every suggestion carries one of two tags:

- **[Lib]** the method or the test target is in a library book. The citation gives author, section,
  printed page and equation number so the page can be checked before anything is coded.
- **[Not lib]** the library does not cover it. The item is still proposed, and its source has to be
  found and recorded in the usual way (open, citable) before it enters the repository.

Books cited, with the short names used below:

| Short name | Book |
|---|---|
| Raymer | D. Raymer, *Aircraft Design: A Conceptual Approach*, **2nd ed. (1992)** |
| Anderson APD | J. Anderson, *Aircraft Performance and Design* |
| Anderson CFD | J. Anderson, *Computational Fluid Dynamics: The Basics with Applications* (1995) |
| Mattingly | Mattingly, Heiser, Pratt, *Aircraft Engine Design*, 2nd ed. |
| Cockburn | Cockburn, Karniadakis, Shu (eds.), *Discontinuous Galerkin Methods* (2000 proceedings) |
| Brunton-Kutz | Brunton and Kutz, *Data-Driven Science and Engineering* |
| Kutz | Kutz, *Data-Driven Modeling and Scientific Computation* |
| DMDU | Marchau et al. (eds.), *Decision Making under Deep Uncertainty* |
| LSZ | Law, Stuart, Zygalakis, *Data Assimilation: A Mathematical Introduction* |
| Sutton-Barto | Sutton and Barto, *Reinforcement Learning: An Introduction* |
| Hollister-Pang | Hollister and Pang, *A Concise Introduction to Scientific Visualization* |

Three cautions that apply to every citation:

1. **Edition.** The library holds Raymer's 2nd edition. `data/drone/rules.yaml` cites the 5th
   edition (2018) for the tail volumes and form factors. The values agree, but every Raymer page
   and equation number in this note is from the 2nd edition. A ledger entry that uses one of them
   must name the edition it was read from.
2. **Calibration range.** Raymer's and Anderson's correlations are fitted to manned aircraft at
   Reynolds numbers of about 3e6 to 2e7, in foot-pound-second units. For a 1 to 4 kg aircraft at
   Re 1e5 to 5e5 they are cross-checks and bands, not models to adopt. Each item says which.
3. **Pages come from notes, not from the page images.** The citations were taken from the chapter
   notes; a sample of them was checked against the notes' equation tags and tables. Before a
   printed number becomes a test target, the page itself should be opened once. Misprints that the
   notes flag are listed in Appendix A.

Section 1 summarises where the study stands. Section 2 gives the findings in order of weight.
Sections 3 to 9 are the roadmap, in seven tracks. Section 10 orders the work. Section 11 lists the
decisions that are Éder's. Section 12 lists what the library does not cover.

## 1. Where the study stands (from the records)

- **Inlet line (Tasks 1 to 9).** Two-ramp and three-ramp external-compression inlets, 2D, laminar
  Navier-Stokes in SU2 v8.2.0. Validated against oblique-shock theory, Eckert and Fay-Riddell
  (`docs/validation/2026-11-01_report.md`). EHVI reaches the pool front first on both problems. The
  robust heat-flux query over the envelope has no feasible design
  (`docs/validation/2026-11-04_task9_report.md`). A turbulent pool was never run.
- **Drone line (Task 10).** Six inputs, endurance against take-off mass. Low level: vortex lattice
  plus closed-form section plus drag build-up plus mass closure. High level: 2D SU2 airfoil polars.
  The open items the report itself names (`docs/validation/2026-11-08_task10_report.md`, sections
  6 to 9, and decision 11 in `docs/specs/task10_tasks.md`):
  - V6e fails on the lift slope (+5.5 % and +6.4 % against the E387 tunnel), accepted with the bias
    recorded (decision 8).
  - Every airfoil run is `not_converged` by the drift rule and is kept on a Cauchy stop. Cases at 8
    to 14 deg do not settle (S2R: FAIL).
  - The GP's 90 % intervals cover 43 to 78 % of held-out designs.
  - The inverse answer moved when two designs were added, sits on three bounds of the box, and its
    confirmation missed on endurance (z = -1.90).
  - Near the mass cap, feasibility rests on one assumed band (skin areal density).
  - No whole-aircraft validation (V6g not run). No trim drag. Constant propulsive efficiency.
- **Task 11.** The warm-start campaign W1 stopped at 50 of 123 jobs with no result.
- **Fields.** The repository keeps force coefficients and histories. It holds 15 surface files and
  one volume field. No 3D geometry, no 3D rendering and no 3D CFD exist.

## 2. Findings, in order of weight

1. **The two validation failures share one root: iterative error is not separated from
   discretisation error.** The airfoil mesh table "resolves the drift band, not the mesh" (report
   section 3). Until one angle is run to a residual plateau on three meshes, the +5.5 % lift-slope
   miss cannot be assigned to the turbulence and transition model, the mesh, or the far field.
   Track A, items A1 to A4.
2. **The surrogate's intervals are too narrow, and every downstream answer uses them**
   (P(mass <= cap), the Pareto band, the confirmation test). Six length scales plus three other
   hyperparameters are fitted as point estimates on 8 to 32 designs (`surrogate/gp.py`), and no
   calibration step exists. Track B, items B1 to B4.
3. **The low-fidelity drone model has three errors that are not uniform across the design box**,
   so they move the front, not only its level:
   - trim drag grows with camber, so "flatters every design equally" (spec section 3) does not
     hold across the camber input;
   - profile drag is constant in cl and the span efficiency is the inviscid lattice value, which
     favours high aspect ratio;
   - one constant `section_lift_effectiveness` of 0.75 sets both the lift slope and cl_max, and its
     band [0.6, 0.9] excludes what the tunnel implies (0.93 to 0.97, V6f).
   Track C, items C1 to C5.
4. **The decision question is a deep-uncertainty question and is answered with a one-at-a-time
   sweep.** The answer's feasibility flips inside one assumed band. The library has the tools for
   this and one of them is already implemented and tested. Track D.
5. **Stability is recorded, not gated, and the centre of gravity is assumed at the wing
   aerodynamic centre** (`drone/evaluate.py`, static-margin block). A design that maximises
   endurance with an unstable or untrimmable layout passes every gate today. Track C, item C2.
6. **The structure is sized for a 3.8 g manoeuvre only.** At the low wing loadings the box allows
   (gate 4 admits 20 N/m^2), gust loads may govern. Track C, item C6.
7. **The inlet's recovery has no external reference line, and the geometry is shock-on-lip at Mach
   4.0 while the envelope flies to 4.5.** Track G, items G1 and G5.
8. **A code observation, to be confirmed by a test before it is called a bug:**
   `surrogate/pca_gp.py` `predict` returns the variance of the retained components only. The
   energy of the discarded components is not added, which would make the profile band too narrow
   by construction. Item B5.
9. **Fields are thrown away.** Every model that would need them later (reduced-order models,
   learned warm starts, 3D rendering, the diagnosis of the non-settling cases) starts from zero.
   A storage rule costs little and has to come before Track F. Item F1.
10. **3D work needs a compute decision before a line of code.** The medium airfoil mesh has
    43,008 cells and takes about 23 minutes per angle on 2 to 4 ranks. A RANS wing is millions of
    cells. That does not fit the Colab CPU worker. Item E0.

## 3. Track A: trust the 2D CFD we already have

Goal: turn the recorded FAIL and "not converged" labels into either a fix or a measured, attributed
bias. No new physics. Mostly Colab hours on the existing queue.

| ID | What | Why and source | Acceptance |
|---|---|---|---|
| A1 | Run one E387 angle (4 deg, Re 203,800) on coarse, medium and fine to a residual plateau: restart, no Cauchy stop, residual history kept. | Residuals are the figure of merit; variables look steady long before residuals stop falling. **[Lib]** Anderson CFD 7.3.3, p. 313-316, Fig. 7.10. | The drift of cl and cd over the last 20 % of iterations is at least ten times smaller than the medium-to-fine change. If not reachable, the row says so with the plateau level. |
| A2 | Report grid convergence with observed order and a grid convergence index on the three plateau runs, beside the present percent changes. | **[Not lib]** (Richardson extrapolation and GCI are not in the library; Roache's papers are the source to record). The library supports the caution that a grid-independent answer is not the exact one: Anderson CFD Table 7.5, p. 323, and p. 321-322. | A function with a unit test on a manufactured three-level sequence of known order; then the V6e and V4m rows carry an order and an interval. |
| A3 | Transition and turbulence model experiment on the E387 at identical mesh and convergence: SA fully turbulent, SA-BCM, SST with Langtry-Menter (the template `cases/templates/inc_sst_lm_airfoil.cfg` exists; the spec allowed this attempt and it was not run). | Laminar against turbulent treatment changes a low-Reynolds airfoil result qualitatively. **[Lib]** Anderson CFD 1.2, p. 6-9 (Wortmann FX63-137 at Re 1e5). | A table of cl_alpha and cd for three models against the tunnel. The verdict of V6e is restated per model. Decision 8 stays until Éder rules. |
| A4 | Flat-plate row for the incompressible solver, laminar and SA, at Re 2e5 to 3e5: skin friction against the closed forms. Splits the E387 drag miss into friction and pressure drag. | **[Lib]** Anderson APD (2.27), p. 107 (laminar), (2.29), p. 108 (turbulent, stated accuracy 4 % for 1e5 < Re < 1e9). Transition sensitivity to inflow turbulence: Cockburn ch. 4, p. 84-85. | New hard row V7a. Tolerances fixed in the spec before the run. |
| A5 | Far-field size study on one angle (30 chords against 60 and 120). | A lift-slope error that is a uniform offset at every angle (report section 2) is the signature of a far-field or circulation effect as much as of a model. **[Not lib]** (far-field vortex corrections are not in the library). | cl change between the two largest domains below the A1 drift. |
| A6 | Post-stall angles (8 to 14 deg): one time-accurate run per angle, reported as mean and amplitude with a time-step halving check. | A separated flow has to be marched time-accurately; local time stepping distorts the transient. **[Lib]** Anderson CFD 4.4, p. 151-152; p. 301-303; Table 9.3, p. 433 as the template for the step check. The SU2 dual-time set-up is **[Not lib]**. | For each angle: either a steady answer under A1's rule, or a mean with an amplitude and a period. The pool's rule for dropped angles is then restated on evidence. |
| A7 | Prandtl-Meyer expansion row, the counterpart of V1: reuse `geometry/wedge.py` with a negative angle. | **[Lib]** Anderson CFD 8.3.2, p. 386-387 and p. 413: M1 = 2, turn 5.352 deg, exact M2 = 2.20, p2 = 0.739e5 N/m^2, T2 = 262 K. The wall node behind the corner is excluded (p. 409-413). | New hard row V1b. |
| A8 | Nozzle with a captured normal shock, as an SU2 Euler duct with the pressure outlet that Task 9's V5 needed. | Tests the outlet condition that caused the seven start-up failures. **[Lib]** Anderson CFD 7.6.1, p. 358-361: p_e/p0 = 0.6784, shock at M1 = 2.07, p02/p01 = 0.6882, A1/At = 1.790. Blow-up when the back pressure is lowered too far, and the remedy of a closer start: 7.4.3, p. 333-336. | New hard row V5b on shock position and total-pressure ratio. The two-stage start becomes the default for back-pressured ducts if it is needed here too. |
| A9 | Sensitivity table of the inlet objectives to the entropy-fix coefficient, the CFL cap and the limiter, on the 8/8 case. Mass-flow and total-pressure consistency across the shocks reported for each. | Added dissipation acts as a mass source at a captured shock and changes separated regions first. **[Lib]** Anderson CFD p. 367-370 and Tables 7.14-7.15; 6.6, p. 239-242. Carbuncle and entropy-fix theory itself is **[Not lib]**. | A table in `docs/validation/`; no verdict, a report row. |
| A10 | Mesher: elliptic smoothing outside the algebraic wall layer as a general replacement for the five tangent-smoothing passes of decision 11. | **[Lib]** Anderson CFD 5.7, p. 192-200, eqs. (5.67)-(5.70), solved by successive over-relaxation, (6.36)-(6.37), p. 231-232. Only if a future section fails the gate; decision 11 already clears 87 meshes. | Same quality gate; the mesh-pair row of A1 unchanged within its drift. |

Cost class: A1 to A6 are tens of worker-hours on Colab (the fine mesh took 4,379 to 10,327
iterations under a Cauchy stop, so plateau runs will be longer; measure one first). A7 to A9 are
minutes each.

## 4. Track B: make the surrogate's uncertainty honest

Goal: an interval that covers what it says, an answer that says how stable it is, and a comparison
between strategies that carries its own error bar. All of it runs on the container on committed
pools; no new CFD.

| ID | What | Why and source | Acceptance |
|---|---|---|---|
| B1 | Leave-one-out and k-fold error and coverage for every GP in the study, plus a second split that holds out the designs nearest the box faces, reported separately. | The inverse answer sits on three bounds, where the model extrapolates. **[Lib]** Brunton-Kutz 4.6, p. 190-195 (k-fold, leave-p-out); 4.5, Fig. 4.17, p. 189 (interpolation against extrapolation). The closed-form leave-one-out for a GP is **[Not lib]** (Rasmussen and Williams). | `analysis/gp_diagnostics.py` writes coverage at 50, 80 and 90 % for both splits on the drone pool and both inlet pools. |
| B2 | Rank histogram of held-out values inside the predictive distribution, then one variance inflation factor chosen on the folds, with coverage before and after. | **[Lib]** LSZ, notes to section 4.5, p. 110 (rank histogram), and to section 4.2, p. 103-107 (variance inflation). The transfer from ensemble filters to a GP is by analogy and is said so. A conformal interval is the **[Not lib]** alternative; both are run and compared. | Held-out 90 % coverage inside [0.85, 0.95] on the drone pool over ten seeds, or the report says it is not reached and by how much. |
| B3 | Model selection at each budget: ARD kernel (d + 3 parameters), one length scale (4), and a linear mean with one length scale, ranked by the log marginal likelihood the code already computes with a parameter penalty, and confirmed by B1. | Nine parameters on eight points is the plausible cause of the narrow intervals. **[Lib]** Brunton-Kutz 4.7, eqs. (4.46)-(4.47), p. 197. Printed test targets: the three AIC and three BIC values of p. 199. | The rule for which kernel is used at which n is fixed in the spec before the drone and inlet tables are regenerated. |
| B4 | The inverse query returns a set, not a point: every gate-passing design whose predicted endurance is inside the interval of the best, with the range of each input over that set, and a leave-one-design-out table of where the best moves. | The maximiser of a smooth distribution can jump when the data change slightly. **[Lib]** LSZ 3.3, eq. (3.23), p. 67, Fig. 3.1. This is what happened between 30 and 32 designs. | `inverse.json` gains `near_optimal` and `leave_one_out`. The confirmation rule is restated for a set before any new confirmation runs. |
| B5 | `surrogate/pca_gp.py`: a test that checks the band's coverage of held-out profiles; then add the discarded energy to the variance and choose the rank by the optimal hard threshold instead of 99.9 % capped at 8. | **[Lib]** Brunton-Kutz eq. (1.7), p. 11; eqs. (1.44)-(1.47), p. 42-43. Printed test target: threshold about 56.6 for n = 600 and unit noise, two singular values above it (Fig. 1.23, p. 46). The threshold assumes white noise; CFD profiles are nearly noise-free, so it may keep many modes. | The profile band's coverage is reported before and after, on `runs/profiles/2026-11-02/`. |
| B6 | Robust slope for the two-level model: least squares against least absolute deviations for rho, both reported. | Designs 8 and 28 (budget-exhausted, 38 to 48 % below the low model) move the answer. **[Lib]** Brunton-Kutz 3.5, p. 137-138. | `mf.csv` gains the second slope; the report states whether the two-level conclusion changes. |
| B7 | A sparse quadratic baseline (28 terms in six inputs, penalty chosen by cross-validation, active terms refitted). An explainable reference and a candidate GP mean. | **[Lib]** Brunton-Kutz 3.5, eq. (3.15), p. 139-141, with a printed worked example. | Held-out error beside the GP's in the B1 table. |
| B8 | Strategy comparisons report paired differences over at least 30 seeds with an interval, not "5 of 10 seeds". | **[Lib]** Kutz 12.3, p. 303-309; the protocol of Sutton-Barto 2.3, p. 28-30. | The replay tables of Tasks 4, 9 and 10 regenerated with intervals. |
| B9 | An upper-confidence baseline (mean + c sd) in `surrogate/acquisition.py`, regret reported against c. | **[Lib]** Sutton-Barto 2.7, eq. (2.10), p. 35-36, Fig. 2.6. Bandit setting; no multi-objective form in the book. | One more row in the replay; a report item. |
| B10 | Cost-aware two-level acquisition: choose the fidelity as well as the point, by improvement per worker-second. | The two-level model wins at 8 designs and not at 24; the open question is how to spend a mixed budget. **[Not lib]** (multi-fidelity acquisition is not in the library). The surrogate and the acquisition choose; the language model does not. | Replay on the committed pools against the fixed nested design. |

One item is deliberately small: the convergence classifier of Task 9 did not beat the trivial
baseline, and the seven failures were one start-up mechanism. A single cross-validated shallow tree
(**[Lib]** Brunton-Kutz 5.8, p. 239-244) settles whether any design signal exists; after that the
classifier is dropped or kept on evidence.

## 5. Track C: a better low-fidelity aircraft model

Goal: remove the biases that vary across the box, gate what is only recorded, and validate the
whole aircraft once. Every item changes the low level, so the 9^6 grid (4.6 h) and the low pools
are re-run once, at the end, as a new family version (`drone2`); the Task 10 records keep their
own code and stay as they are.

| ID | What | Why and source | Acceptance |
|---|---|---|---|
| C1 | **Trim drag.** Solve the pitch balance for the tail lift at the cruise point and add the tail's induced drag and the wing's extra lift. The section moment comes from thin-airfoil theory of the NACA camber line (low level) or from SU2 (high level). | Camber is an input from 0 to 6 %, so the tail download is not the same for every design. **[Lib]** Raymer 16.3: moment balance (16.7), p. 416; wing moment (16.16), p. 422; tail lift (16.29)-(16.30), p. 430; trimmed induced drag (16.31), p. 432. No clean printed test target; the test is the limit (zero camber, centre of gravity at the neutral point of the wing alone gives zero tail load). | Report: endurance with and without trim drag over the 192-point pool, and whether the front's order changes. |
| C2 | **A real centre of gravity and a static-margin gate.** Place the masses the closure already computes; compute the neutral point with the tail and a fuselage term; gate the margin to a band (for example 5 to 20 %) fixed in the spec. | **[Lib]** Raymer (16.9)-(16.10), p. 417; fuselage term (16.22), p. 427; power-on allowance, p. 418. Printed target: the DR-1 example, neutral point 1.188 mean chords, p. 579-580. The code comment cites "Anderson ch. 7"; the material is Anderson APD 8.6.7, eqs. (8.76)-(8.78), p. 444. | Unit test on the DR-1 inputs. The gate's rejections on the existing pools are counted before the gate is switched on. |
| C3 | **Downwash at the tail from the lattice itself**, in place of 2 a_w / (pi AR), with Raymer's chart as the cross-check. | **[Lib]** Raymer Fig. 16.12, p. 425; (16.20)-(16.21), p. 426. The DR-1 example reads 0.38 at aspect ratio 6. | The lattice value at the DR-1 geometry inside a tolerance of the chart reading, set before the run. |
| C4 | **Split the lift-effectiveness factor** into a lift-slope factor and a separate stall treatment, and re-centre both on evidence. Add a lift-dependent term to the low-level profile drag, and replace the hard laminar/turbulent switch at Re 5e5 with a banded laminar fraction. | One factor of 0.75 produces the 19 to 23 % slope miss of V6f. **[Lib]** Raymer (12.6)-(12.9), p. 266 (section efficiency about 0.95); wing maximum lift about 0.9 of the section value, (12.15), p. 270; viscous drag due to lift and the span-efficiency fit, (12.48)-(12.49), p. 298-299, printed target e = 0.87 at aspect ratio 6, p. 573; laminar fraction, p. 282-283. Lift-slope targets: Anderson APD Example 2.5 (4.51 per rad, p. 84) and Example 2.8 (0.077 per deg, p. 88-89). All manned-aircraft fits: used as bands. Low-Reynolds section behaviour itself is **[Not lib]**. | V6f re-run: the three "report" rows move toward the tunnel, by amounts stated before the change. Open ruling 2 of the Task 10 report is closed by this item. |
| C5 | **Propeller model.** Replace the constant 0.60 with an actuator-disk ideal efficiency times a banded real-to-ideal factor, at the cruise point and separately at the climb point. Adds a propeller diameter to the ledger. | Efficiency falls at low speed and high thrust, so the present climb power is optimistic. **[Lib]** Mattingly App. L, (L.7)-(L.9), p. 612; real propellers at about 85 % of ideal, p. 609-613; fixed-pitch off-design, Raymer Fig. 13.10, p. 329. Small-propeller data at low Reynolds number is **[Not lib]** (the UIUC propeller database is the open source to record). | Unit tests on the closed forms (L.8)-(L.9). The bias sweep's second-largest term is re-measured. |
| C6 | **Gust loads and a V-n diagram.** Size the spar for the larger of the manoeuvre and the gust load factor; use the lattice's own span loading for the bending moment. | **[Lib]** Raymer (14.2)-(14.8), p. 339; Figs. 14.7-14.8, p. 341; span loading by Schrenk, (14.9)-(14.11), p. 343; corner speed, Anderson APD (6.54), p. 343, printed target 492.4 ft/s (Example 6.3). *Hand arithmetic, not a run: at the lowest wing loadings of the box the gust increment looks comparable to the 3.8 limit.* The gust velocities are manned-aircraft statistics; a small-aircraft gust environment is **[Not lib]**. | A new recorded quantity `n_design` and which case set it. Counted over the pool before the structure is changed. |
| C7 | **Constraint diagram** (power loading against wing loading: stall, climb, sustained turn, launch) as an analysis and as the source of the installed-power rule, replacing "max(2 P_cruise, climb at 2 m/s)". | **[Lib]** Mattingly master equation (2.11), p. 24, with cases (2.12)-(2.17), p. 25-33; Raymer (5.6), (5.24)-(5.31), p. 85-98; Anderson APD 7.3.8, p. 392-395. For a battery aircraft at sea level the lapse and weight-fraction terms are 1. Hand and bungee launch are **[Not lib]**; the closest form is Raymer (5.10), p. 89. | `analysis/constraint_drone.py` and one figure. Each pool design plotted on it. |
| C8 | **Speed optima as unit tests** of `drone/mission.cruise_point`, fed a parabolic polar. | **[Lib]** Anderson APD Example 5.4, p. 223-224: with CD0 = 0.015 and K = 0.08, (CL^1.5/CD)max = 10.83, (L/D)max = 14.43, (CL^0.5/CD)max = 25, speeds in the ratio 0.76 : 1 : 1.32. | Three assertions in `tests/task10/`. |
| C9 | **Mission beyond still-air cruise:** endurance in a head wind, a loiter turn at a stated bank, and the climb segment computed, not allowed for. | **[Lib]** wind correction, Anderson APD (5.179), p. 311; turn radius and rate, (6.33) and (6.36), p. 331-332, printed targets 861 ft and 0.25 rad/s (Examples 6.1, 6.2); inner-wing speed in a turn, Raymer (17.81), p. 475. Battery discharge behaviour is **[Not lib]**. | New recorded outputs; the two objectives unchanged unless Éder rules otherwise. |
| C10 | **Twist and tip stall.** Add a fixed washout (or a seventh input) and promote the tip-stall indicator from a diagnostic to a gate. | The inverse answer sits at taper 0.3, where the tip Reynolds number is lowest. **[Lib]** Raymer p. 56-58 (taper, twist of about 3 deg, not above 5) and p. 43-44; Anderson APD Fig. 2.39 and (2.31), p. 109-110, as a lattice check of induced drag against taper. | Lattice test: induced-drag factor has its minimum near taper 0.3 to 0.35 on an untwisted wing. |
| C11 | **Drag build-up details:** interference factors, hinge gaps, leakage and protuberance allowance, stopped-propeller drag. | **[Lib]** Raymer p. 282-290; printed targets from the DR-1 example, p. 571-572 (fuselage cf 0.0026, form factor 1.25, total 0.0250). Raymer's full skin-friction form carries a Mach factor outside its range here; the study's omission stays, stated. | DR-1 component test. A plausibility bound on whole-aircraft CD0 by equivalent skin friction (Raymer Table 12.3, p. 280), as a report row. |
| C12 | **Whole-aircraft validation (V6g).** Still the missing row. Find one small aircraft with open geometry, mass and flight or tunnel data, and build the model at its geometry. | **[Not lib]**. The component-mass regressions in the library (Raymer Table 15.2, p. 398; Anderson APD (8.83), p. 449) are about ten times too heavy for this class and are used only for trend exponents. | V6g reads pass, fail or "not run" with the data named. This row is what turns the skin areal density band from assumed to measured. |
| C13 | **Carpet plot and growth sensitivities** from the 9^6 grid: wing loading against aspect ratio with the gate lines drawn, and the bias sweep restated as percent endurance per percent of each quantity. | **[Lib]** Raymer p. 525-533 (sizing matrix, carpet plot, Table 19.1). | Two figures from the committed grid; no new run. |

## 6. Track D: the decision under deep uncertainty

Goal: replace "the answer's feasibility rests on the assumed skin areal density band" with a
statement of how much error each candidate design tolerates. This is the track with the best ratio
of insight to cost: it needs only the low model, which runs in under a second.

| ID | What | Why and source | Acceptance |
|---|---|---|---|
| D1 | **Info-gap robustness curves.** Nested boxes over the 21 banded quantities, scaled so that horizon h = 1 is the ledger's bands; the V6e lift bias and the surrogate's error enter as two more uncertain quantities. For three candidates (the 30-design answer, the 32-design answer, one lighter interior design), the largest h at which the worst case still meets mass <= 4 kg and endurance >= a requirement. Plotted against the requirement; curve crossings are the finding. | A design with a lower nominal endurance can tolerate more error; the preference between two designs can reverse with the requirement. **[Lib]** DMDU ch. 5, eqs. (5.3)-(5.5), p. 104-105, Fig. 5.5, p. 109; the engineering example of ch. 10, eqs. (10.4)-(10.8), p. 212-214. The library already has a tested implementation of the scalar-linear case, whose tests reproduce the printed crossing at 2.4 and the zero at 3. The 21-quantity worst-case search is new code: vertices if the response is monotone in each quantity (checked, not assumed), sampling otherwise. | `analysis/infogap_drone.py`, a CSV of h against requirement per candidate, one figure. The robustness is not a probability and the figure says so. |
| D2 | **Opportuneness** on the same boxes: the smallest h at which a windfall endurance becomes possible. | **[Lib]** DMDU eqs. (5.6)-(5.7), p. 106-107. | A second curve per candidate. |
| D3 | **Robustness of the chance constraint:** how wrong the surrogate's predictive tail can be before P(mass > cap) exceeds 0.1. Run after B2. | **[Lib]** DMDU eqs. (5.12)-(5.16), p. 111-112; printed target: failure probability 1.35e-3 at three standard deviations. | One number per candidate with its meaning stated. |
| D4 | **Scenario discovery.** A joint Latin hypercube of a few hundred futures over the banded quantities; each candidate labelled pass or fail in each future; the few-quantity region that holds the failures; regret and the fraction of futures passed. | **[Lib]** DMDU 2.3-2.5, p. 33-42; 7.4.3, p. 153-154. The book names the box-finding algorithm but does not give it, so PRIM is **[Not lib]**; a shallow tree (Brunton-Kutz 5.8) is the library-sourced substitute. | A table of the failing region in plain quantities ("skin above x and efficiency below y"). |
| D5 | **Tipping points and a stress-test map:** the skin areal density at which each candidate breaks the cap, and a pass/fail map over skin density against propulsive efficiency. | **[Lib]** DMDU 4.2, p. 75-76; 12.2, p. 258-267. | One sentence per candidate of the form "holds until"; one figure. |
| D6 | **Calibrate the banded assumptions that have data.** Scalar: a prior from the band of `section_lift_effectiveness`, updated with the tunnel-implied value. Joint: lift, drag and cl_max factors against the V6f rows by an ensemble Kalman analysis or a random-walk sampler on the low model. | The band excludes the data, which is model error, not parameter error, and the result must say so. **[Lib]** Kutz 21.1, eqs. (21.1.12)-(21.1.15), p. 543-544; LSZ eq. (1.7), p. 9, and Example 2.1, p. 45-46; model error, LSZ 2.7, p. 43-45. A tested ensemble Kalman analysis exists in the library. One airfoil at two Reynolds numbers calibrates one section only. | Posterior bands written back to the ledger as a proposal, with the prior kept. Éder rules on adopting them. |
| D7 | **Flexibility:** a design whose battery fraction is fixed after the airframe is weighed, valued against the fixed design over the D4 futures. | **[Lib]** DMDU 6.3, p. 124-126. Lower priority. | One comparison table. |

The same analysis applies to the inlet's open result. Task 9 found no design that meets the heat
cap over the whole envelope; D1 and D5 restate that as "which part of the envelope has to be given
up, and how much cap, for a design to exist".

## 7. Track E: three-dimensional geometry and rendering

Goal: one parametric 3D model of the aircraft that is the single source for the pictures, the
wetted areas and volumes in the drag build-up, and later the CFD surface. Rendering is a view of
recorded data and never a source of it.

### 7.1 Geometry (`geometry3d/`, numpy only)

| ID | What | Source | Acceptance |
|---|---|---|---|
| E1 | **Wing and tails as lofted surfaces:** NACA sections from `drone/naca.py` placed along the span by the planform of `drone/geometry.py`, with twist as a rotation of the chord line, linear interpolation between sections at constant percent chord, closed tips. Output: a structured quad surface, and its triangulation. | **[Lib]** Raymer 7.8, p. 142-147; reference wing (7.5)-(7.9), p. 139-140; tail geometry ranges, Table 4.3, p. 76. | Mean chord and its span station equal those of `drone/geometry.py` to rounding. Printed target: Anderson APD (8.57)-(8.58), p. 427-428. |
| E2 | **Fuselage from control stations**, each a conic defined by its end points, tangent intersection and shape parameter, joined by smooth longitudinal lines. The present body of revolution is the special case. | **[Lib]** Raymer 7.3-7.4, p. 123-134, eqs. (7.1)-(7.4). Printed target: shape parameter 0.4142 with equal tangent lengths gives a circular arc; 0.5 a parabola. No spline-surface or CAD-kernel method is in the library; none is needed for this. | Unit tests on the two conic limits. |
| E3 | **Geometry gates:** watertight (every edge shared by exactly two triangles, outward normals); surface area against Raymer's wetted-area forms and against the area the drag build-up uses; enclosed volume against the fuselage volume the mass closure needs; a smoothness check on buttock and waterline cuts; aft-body angle. | **[Lib]** Raymer (7.10)-(7.13), p. 150-153; lofting checks, 7.7, p. 137-138; aft-body angle of 10 to 12 deg, 8.2, p. 155. *Hand arithmetic: (7.11) gives 2.039 times the exposed area at 12 % thickness; the code uses 2.06.* | Each gate refuses with the offending value, as the mesh-quality gate does. The area and volume used by `drone/drag.py` and the closure come from this model afterwards, and the nominal design's endurance change is reported. |
| E4 | **Placement and layout:** wing at a stated mean-chord fraction relative to the centre of gravity of C2, tail arm from the rules, battery and payload as boxes inside the body with a fit check. | **[Lib]** Raymer p. 112 and p. 140. | The fit check is a new gate: the battery volume the closure assumes has to fit in the body the loft draws. |
| E5 | **Export:** triangle surface for viewing, and a surface for meshing (Track F). | **[Not lib]** (file formats and toolkits are not in the library). | Round trip: exported and re-read area and volume equal to 1e-9. |

### 7.2 Rendering (`viz3d/`)

The toolkits are **[Not lib]**; the library names VTK as the open route (Hollister-Pang ch. 6,
p. 96-97) and gives the principles. Proposed: one optional dependency for off-screen static
renders (PyVista on VTK), kept out of the core package, and one self-contained HTML viewer for
browsing designs, with the mesh embedded so that it opens offline. Both read the E5 export; neither
is imported by anything that computes a result.

| ID | What | Source | Acceptance |
|---|---|---|---|
| E6 | **Design renders:** three orthographic views and one perspective view per design, from a fixed camera table, with the six inputs and the outputs printed on the figure. A design that has no SU2 record is labelled "geometry and low-fidelity model only". | **[Lib]** orthographic views for anything dimensional, because perspective foreshortens: Hollister-Pang ch. 2, p. 35-36. | A golden-image test on the nominal design at a fixed size, with a tolerance. |
| E7 | **Front browser:** the Pareto front as a page where each point opens its render and its record; neighbours on the front shown side by side at one scale. | **[Lib]** linked views and comparison, Hollister-Pang ch. 5, p. 84-87. | The page is generated from the committed front and records only. |
| E8 | **Lattice loads on the geometry:** the vortex-lattice span loading, the strip cl against cl_max (the tip-stall indicator) and the spar bending moment drawn on the wing. This is the first "3D result" and it needs no new solver. | The plot-type rule of Anderson CFD 6.9, p. 264-279: line plots for numbers, colour for the overall picture; both are given. | Values on the figure equal the evaluation record. |
| E9 | **3D flow results** (after Track F): surface pressure and skin-friction maps, cutting planes, streamlines integrated by a Runge-Kutta scheme, a tip-vortex iso-surface with planes behind the tip. Each quantitative claim also appears as a line plot (pressure coefficient against chord at span stations). | **[Lib]** Anderson CFD Figs. 6.25-6.26 and 6.34, p. 272-279; contour-level count, Fig. 6.19, p. 267; integration and field methods, Hollister-Pang ch. 4, p. 64-72; iso-surfaces and slice planes, Kutz 6.2, p. 137-140. Vortex-core criteria and colour-map perception guidance are **[Not lib]**. | See the rules below. |
| E10 | **Uncertainty and numerical error on the picture:** the surrogate's mean beside its standard deviation; coarse, medium and fine meshes shown as an ensemble; time-accurate cases as mean and amplitude. | **[Lib]** Hollister-Pang ch. 5, p. 83-91 (mean with deviation field, contours coloured by crossing probability, ensemble curves). | One such figure for each headline 3D result. |

**Rendering rules (proposed for `CLAUDE.md` if accepted).**

1. Every rendered image has a sidecar record: case id or design id, mesh level, solver version,
   final residual and convergence label, the quantity with its units, the colour map and its range,
   the camera and the projection, and the commit. An image without one is not committed.
2. A plausible flow picture can integrate to wrong forces, and the grid can matter more than the
   flow model (**[Lib]** Raymer 12.7, p. 310-312). No image of a field stands in for a validated
   number; the caption names the validation row the case passed or failed.
3. Colour ranges are fixed per quantity across designs that are compared. Cell data are shown as
   cell data, or the interpolation is stated (**[Lib]** Hollister-Pang p. 64-65).
4. Figures are made by code from records, with no manual edits; a greyscale-safe variant exists for
   each (**[Lib]** Kutz 6.1, p. 129-133).
5. A render of a design that was never solved says so on the image.

## 8. Track F: three-dimensional CFD, as a ladder

Goal: reach a RANS solution of the wing and then the aircraft with the same discipline as the 2D
work: each rung has its own validation row, fixed before the run, and the next rung does not start
on a failed one. The lattice model stays as a cross-check at every rung.

**F0, the decision that comes first: compute.** The numbers on record are 43,008 cells and about
23 minutes per angle for the medium 2D airfoil on 2 to 4 ranks. *Hand arithmetic, not a
measurement: extruding that mesh over a half span at a sensible spanwise spacing gives several
million cells.* The first full-aircraft Navier-Stokes solution in the literature used over 500,000
points (**[Lib]** Anderson CFD p. 517), and a uniformly refined grid that resolves a tip vortex
needs at least 16 times the points of an adapted one (**[Lib]** Cockburn ch. 45, p. 439-444). The
Colab CPU worker will not carry rung F4. Options for Éder: a rented multi-core node for the upper
rungs; SU2 with wall functions on a coarser mesh; or stopping the ladder at F3 and reaching "3D"
through F2 and the lattice. F1 below measures the real cost before the choice, as Task 1 did.

| ID | Rung | What it verifies | Source | Acceptance |
|---|---|---|---|---|
| F1 | **Timing and first light in 3D.** One SU2 3D tutorial case and one extruded-airfoil case on the Colab worker; cost per iteration per cell recorded. | The budget, before any plan depends on it. | As Task 1. | `runs/task12_timing/` with a go/no-go table for F2 to F5 on each compute option. |
| F2 | **Extruded airfoil (quasi-2D)** with symmetry planes: the E387 at one angle. | The 3D mesher, the 3D boundary conditions and the force integration, against a number already on record. The metrics carry over directly to three coordinates (**[Lib]** Anderson CFD 5.3, p. 178-183). | - | cl and cd equal the 2D record inside the A1 drift band. Hard row V8a. |
| F3 | **Inviscid wing.** 3D Euler on the nominal wing and on the elliptic and Warren-12 planforms of V6a and V6b. | Lift slope and induced drag from a field solver against lifting-line and lattice values. Euler captures the vortex system at far lower cost than RANS (**[Lib]** Raymer p. 306-307). Targets: Anderson APD (2.15), p. 81; Helmbold, (2.18a), p. 86; the study's own V6a to V6c rows. | - | Hard row V8b: lift slope and span efficiency inside tolerances set before the run; a three-mesh study under A2. Induced drag by far-field integration is **[Not lib]**. |
| F4 | **RANS wing** at the cruise Reynolds number, with the tip vortex as a verified quantity. | Whether the strip assumption (2D polars integrated over the lattice's loading, one Reynolds number per design) holds: the comparison is 3D RANS against lattice plus 2D polars, component by component. Without local refinement the vortex smears (**[Lib]** Cockburn ch. 45: adaptation from 130,000 to 250,000 cells with a sensor of vorticity and total-pressure loss; an Euler case at Mach 0.84, so the approach transfers and the numbers do not). | - | Report row V8c: lift, drag split and span loading against the low and high levels of Task 10, on three meshes. The first measured answer to "what does the two-level model miss". |
| F5 | **Wing and body, then the whole aircraft** on the E-track geometry. | Interference, which is not additive and whose sign is not predictable in advance (**[Lib]** Anderson APD 2.8.2, p. 103-105; Raymer p. 307-312). | Meshing an aircraft is the cost here (**[Lib]** Raymer p. 311-312); unstructured and prism-layer meshing are **[Not lib]**, and the structured numpy mesher will not extend to this rung without a multi-block design of its own. | Needs C12's validation aircraft so that a tunnel or flight number exists to compare with. Without it the rung is a code-to-code comparison and is labelled so. |
| F6 | **Three-level surrogate:** closed forms, 2D polars, 3D wing. | Whether a handful of 3D runs corrects the two-level model, with B10 choosing the level. | **[Not lib]** | The Task 10 question 3 table with a third column. |

Notes on scope. High-order discontinuous Galerkin methods, hp-adaptation and adjoint error bounds
fill two library books (Cockburn; Feng et al.), but they are not features of the finite-volume
solver used here; they inform F4's refinement sensor and nothing else. A small explainable solver
for teaching rows (the quasi-1D nozzle of Anderson CFD ch. 7, about a hundred lines, with printed
tables to match; stability limits from the tested von Neumann method in the library) is worth
having for the interview and for A8; a hand-written 3D solver is not proposed.

## 9. Track G: fields and reduced-order models; Track H: the inlet line

### 9.1 Track G: store fields, then model them

| ID | What | Source | Acceptance |
|---|---|---|---|
| G1 | **A storage rule.** Every run keeps its wall distributions; volume fields are kept for a stated subset (validation cases, front designs, every failed or non-settling case). Size per case measured first. | Finding 9. | `runs/README.md` states the rule; the worker writes the files and their digests. |
| G2 | **Where to sample.** From the stored wall files, the stations that determine the profile best, by pivoted QR on the leading modes; these are what every future run must keep even when the full field is dropped. | **[Lib]** Brunton-Kutz 3.8, eq. (3.22), p. 149-153. Only 15 surface files exist today, so the rank is at most 15 until G1 has run for a while. | A committed station list with the reconstruction error on held-out cases. |
| G3 | **Gappy reconstruction as a gate on new runs:** rebuild the full wall distribution from the G2 stations; a large residual flags a run unlike any seen before. | **[Lib]** Brunton-Kutz 13.1-13.3, eqs. (13.3)-(13.10), p. 587-588, with a printed test case (p. 596-599). | Unit test on the printed case; then the flag is recorded, not gated, for one pool. |
| G4 | **Modes plus GP for pressure and friction distributions**, with separate mode sets for attached and stalled flow, and B5's variance. | **[Lib]** Brunton-Kutz 12.2, p. 548-551; method of snapshots, eq. (1.14), p. 16; mode libraries, 13.9, p. 619-625. Interpolating coefficients over the design inputs is the study's own GP. Moving features (a transition front, a shock) inflate the rank (12.5, p. 566-571); expect the three-mode floor of Task 4c again unless the coordinate is aligned. | Held-out profile error and band coverage beside the FNO's of Task 4c. |
| G5 | **Dynamic mode decomposition of the non-settling cases**, on A6's time-accurate snapshots: eigenvalues on the unit circle mean a limit cycle (report mean and amplitude); inside it, more iterations would settle. | **[Lib]** Brunton-Kutz 7.2, eqs. (7.18)-(7.23), p. 316-317; noise bias, p. 320-322; Kutz 20.2, p. 527-533. Pseudo-time iterations of a steady solver are not physical time, so only A6's runs qualify. | A classification per case with the eigenvalue plot. |
| G6 | **Warm start, restated.** If W1 is taken up again, the simpler learned start is a G4 field used as the restart. | Inference from Task 11's own conclusion, not from a book. Galerkin projection and hyper-reduction (Brunton-Kutz ch. 13) need the solver's residual, which the release binary does not expose: not proposed. Physics-informed networks: the library's examples are one-dimensional model equations (14.4-14.5, p. 640-648), consistent with Task 11's reading: not proposed. | W1's gates and rule unchanged. |

### 9.2 Track H: the inlet line

| ID | What | Source | Acceptance |
|---|---|---|---|
| H1 | **A reference line on the recovery plots:** the military-standard recovery against Mach number. *Hand arithmetic from the printed formula: about 0.74, 0.67 and 0.59 at Mach 3.5, 4.0 and 4.5.* The confirmed two-ramp design is at 0.345 (`runs/confirm/inlet2r-374dad241f/`). The standard is an engine-face value; the study's station has to be matched or the difference stated. | **[Lib]** Mattingly (4.12c), p. 420; Raymer (13.5), p. 319. Printed checks: 0.9706 at Mach 1.5 (Mattingly Table 10.E1, p. 485). | `physics/` function with a test on the printed values; the line on the Pareto figures with its caveat. |
| H2 | **A second analytic row for the shock code:** two 5 deg ramps and a normal shock over Mach 1 to 2. | **[Lib]** Mattingly Example 10.1, Table 10.1, p. 444; at Mach 2.00: shock angles 34.30 and 37.95 deg, Mach 1.821 then 1.649, recovery 0.8731. Mattingly's eqs. (10.12a,b) are flagged as misprinted and are not to be coded from. Second target: Raymer p. 202. | A test in `tests/test_shock.py`, including the detachment switch at low Mach. |
| H3 | **Optimum ramp split** as an Euler-level check and as a prior mean for the surrogate: recovery of n equal-strength oblique shocks and a normal shock. | **[Lib]** Mattingly Fig. 10.28, p. 438; printed optimum at Mach 1.5 (5.4 and 5.1 deg, 0.9950), p. 485. | The inviscid optimum of the study's own shock relations at Mach 4 beside the laminar front. |
| H4 | **Why the recovery is low, stated with a source:** meeting the standard near Mach 3 takes about 40 deg of turning, and external compression is used to about Mach 2.5. The study caps total turning at 24 deg (two ramps) and 27 deg (three). | **[Lib]** Mattingly Fig. 10.29, p. 438, and p. 437; Raymer p. 204 and Fig. 10.10, p. 206. | One paragraph and the H1 line; no new run. |
| H5 | **Design Mach as a variable.** The geometry is shock-on-lip at Mach 4.0 and the envelope reaches 4.5, so above 4.0 the shocks fall inside the cowl. Practice is to design 0.1 to 0.2 Mach above the maximum speed. | **[Lib]** Raymer p. 212. The above-design case itself is not treated in the books. | A seventh input, or a second pool at design Mach 4.6 to 4.7, by Éder's ruling. This may change the "no feasible design" result of Task 9. |
| H6 | **Mass-flow ratio, spillage and additive drag as recorded outputs**, and additive drag as a candidate third objective. | **[Lib]** Mattingly (10.13)-(10.19), p. 445-454, with Example 10.2; additive drag, (6.5), p. 193, and (10.8), p. 436. Forms that need an engine thrust are not usable here. | New metrics in `postprocess/metrics.py` with a control-volume cross-check, as X1 does for total pressure. |
| H7 | **Starting gate.** The contraction limit for a duct to start, as a gate and as the explanation of the back-pressure failures. | **[Lib]** Mattingly (10.7), p. 434, Fig. 10.22, with a worked case. A8 is its numerical counterpart. | A gate in `physics/gates.py` with the printed case as its test. |
| H8 | **Back-pressure sweep** on one design: critical, subcritical and supercritical operation, recovery against mass-flow ratio. | **[Lib]** Mattingly 10.2.3.3, p. 443-449. Buzz is described as a mechanism only; no criterion a steady solver can evaluate. | One figure; non-settling points handled under A6. |
| H9 | **The turbulent pool that was never run**, with a turbulent flat-plate heating row first. | The library is thin here: a turbulent skin-friction form with a Mach factor (Raymer (12.27), p. 282) and chart readings. Turbulent and hypersonic heat-transfer correlations are **[Not lib]**. | A V2c row with a recorded open source before the pool is staged. |
| H10 | **Mixed compression and three dimensions** (side walls, axisymmetric spike). | Described without a worked design in the library (Mattingly p. 439; Raymer p. 205). | Not scheduled; listed so that it is not forgotten. |

## 10. Order of work

Horizons, not dates. Each horizon ends with a report in `docs/validation/` and nothing in a later
horizon starts on a failed gate of an earlier one.

**Horizon 1: trust (no new physics, mostly existing pools).**
A1, A2, A3, A5 (the lift-slope failure attributed), B1 to B5 (intervals that cover), D1, D4, D5
(the decision restated), C8, H1, H2 (cheap tests with printed targets), G1 (start keeping fields).
Outcome: the Task 10 report's sections 6, 7 and 9 rewritten on calibrated intervals, and the V6e
verdict either fixed or attributed.

**Horizon 2: a better aircraft model.**
C1 to C7, C9 to C11, C13, D6, then one re-run of the grid and the low pools as `drone2`; E1 to E4
(the 3D geometry, which C2 and the wetted areas depend on); A4, A6 to A9; H3 to H7.
Outcome: a low level whose named biases no longer vary with the inputs; a geometry that can be
drawn and gated.

**Horizon 3: see it.**
E5 to E8, E10 (renders, the front browser, lattice loads on the wing); C12 (the validation
aircraft); B6 to B10; D2, D3, D7; G2, G3.
Outcome: every design on the front can be opened and looked at, with its record.

**Horizon 4: three-dimensional flow.**
F0 and F1 (the compute decision on measured cost), then F2, F3, F4 in order, E9 with them; G4, G5;
H8, H9.
Outcome: a measured answer to what the strip model misses, on one wing.

**Horizon 5: the whole aircraft.**
F5, F6, H10, G6. Only with the compute of F0 and the data of C12.

The ten tasks to start with, if only ten are taken: A1, A3, B1, B2, B4, D1, C1, C2, C4, E1.

Model allocation follows `CLAUDE.md`: specs, tolerances, the physics of C1 to C6, every validation
verdict and every diff where a wrong number can pass silently stay with the top model; modules
from a fixed spec and their tests go to the implementing model; figures, tables and rendering code
go to the documentation model with review of anything that prints a number.

## 11. Decisions that are Éder's

1. **Scope.** Which tracks are in. The inlet line (H) and the drone line (A to F) can proceed
   independently.
2. **Compute for 3D** (F0): rent a node, coarsen with wall functions, or stop at the inviscid wing.
3. **A rendering dependency.** The repository avoids heavy frameworks. Off-screen rendering needs
   one (VTK through PyVista), isolated in `viz3d/` and optional. The alternative is matplotlib's 3D
   axes, which cannot draw a lit aircraft or a field correctly.
4. **A new family version** (`drone2`) with a re-run of the grid, against patching Task 10 in
   place. This note recommends the new version; Task 10's records then stay reproducible.
5. **New inputs:** washout (C10), design Mach (H5), propeller diameter as an input or a ledger
   value (C5).
6. **The static-margin band** for the new gate (C2) and whether gust loads may raise the limit load
   factor (C6).
7. **Decision 8** (the accepted lift-slope bias): revisit after A1, A3 and A5, or keep.
8. **The validation aircraft** for V6g (C12): which one, from which open source.
9. **Books to add to the library** (section 12), if the gaps there should be closed from books
   and not only from papers.

## 12. What the library does not cover

Marked **[Not lib]** above. Listed here so that nothing is presented as coming from the books
when it does not, and as a reading list.

- **Low-Reynolds aerodynamics:** laminar separation bubbles, transition modelling, section data at
  Re 1e5 to 5e5. (Raymer p. 45 only warns about the regime.)
- **Electric propulsion:** battery discharge behaviour, motor and controller models, small
  propellers at low Reynolds number, the electric endurance and range equations. The study's
  closed-form endurance is correct and is not from these books.
- **Small unmanned aircraft data:** component masses, skin areal densities, gust environment,
  launch and recovery, any whole-aircraft validation set.
- **Verification practice:** Richardson extrapolation, observed order, the grid convergence index,
  formal iterative-error estimates.
- **Turbulence modelling:** Spalart-Allmaras, SST, the transition options, wall-distance rules,
  wall functions, detached-eddy and large-eddy simulation, unsteady RANS practice.
- **Solver numerics as used by SU2:** low-Mach preconditioning, dual time stepping, carbuncle and
  entropy-fix theory, modern flux functions.
- **3D meshing:** unstructured, prism-layer, overset; far-field corrections; far-field drag
  extraction.
- **Surrogates:** Gaussian-process regression itself, expected hypervolume improvement and
  Bayesian optimisation, co-kriging and multi-fidelity acquisition, conformal prediction,
  variance-based sensitivity indices, the scenario-discovery algorithm, the construction of Sobol
  and Latin hypercube designs.
- **Rendering:** toolkits and file formats, CAD kernels, colour-map perception, vortex-core
  criteria, surface flow topology.
- **Inlets above Mach 2:** no worked example above Mach 2.0, no mixed-compression procedure, no
  buzz criterion, no heat-transfer correlations for turbulent or hypersonic walls. Eckert and
  Fay-Riddell in `physics/heating.py` are not from the library.

## Appendix A: misprints and cautions flagged in the notes

Do not code from these without opening the page.

| Where | Flag |
|---|---|
| Raymer (16.7), p. 416 | printed with a missing overbar |
| Raymer (16.9), p. 417, and the DR-1 example, p. 579-580 | probable misprint in the denominator; the example uses the vertical-tail area ratio |
| Raymer (5.10), p. 89 | subscript printed as "landing" |
| Raymer Fig. 7.4-7.5 tables, p. 121 | no units; the total does not equal the sum of the parts |
| Raymer Fig. 19.1 | text and table disagree |
| Raymer pp. 436-437, 462-463, 546-547 | missing from the scanned copy |
| Anderson APD (5.39)-(5.40) | misprints |
| Anderson APD (6.36), p. 332 | "q" printed for g |
| Anderson APD (8.58), p. 428 | "2.5" printed for 0.25 |
| Anderson CFD Table 7.3, row 16, p. 321 | Mach printed as 0.099 for 0.999 |
| Anderson CFD (5.70), p. 200 | last coefficient misprinted |
| Mattingly (10.12a,b), p. 443 | misprinted |
| Mattingly Table 10.2, p. 457 | some subsonic entries inconsistent |
| Mattingly (L.17) | constant "6605" doubtful |
| Brunton-Kutz eq. near (1.47), p. 43 | possible misprint in an integral's lower limit |
| DMDU Figs. 10.9-10.11 | values are figure readings; the finite-element model is not reproducible |

## Appendix B: printed test targets, in one place

Each is a number printed in a book that a unit test can reproduce before the method is used on the
study's own data.

| Target | Value | Source | Used by |
|---|---|---|---|
| Speed optima, parabolic polar CD0 0.015, K 0.08 | 10.83; 14.43; 25; speed ratio 0.76 : 1 : 1.32 | Anderson APD Ex. 5.4, p. 223-224 | C8 |
| Lift slope, finite wing | 4.51 per rad; 0.077 per deg | Anderson APD Ex. 2.5, p. 84; Ex. 2.8, p. 88-89 | C4, F3 |
| Span efficiency, straight wing, aspect ratio 6 | 0.87 | Raymer p. 573 | C4 |
| Neutral point, DR-1 | 1.188 mean chords | Raymer p. 579-580 | C2 |
| Downwash gradient, DR-1 | 0.38 | Raymer p. 579 | C3 |
| Drag build-up, DR-1 | fuselage cf 0.0026, FF 1.25; total 0.0250 | Raymer p. 571-572 | C11 |
| Corner speed | 492.4 ft/s | Anderson APD Ex. 6.3, p. 344 | C6 |
| Turn radius; turn rate | 861 ft; 0.25 rad/s | Anderson APD Ex. 6.1-6.2, p. 331-333 | C9 |
| Conic shape parameter for a circular arc | 0.4142 | Raymer (7.4), p. 132 | E2 |
| Flat-plate skin friction | 1.328 / sqrt(Re); 0.42 / ln^2(0.056 Re) | Anderson APD (2.27), (2.29), p. 107-108 | A4 |
| Prandtl-Meyer, Mach 2, 5.352 deg | M2 2.20; p2 0.739e5 N/m^2; T2 262 K | Anderson CFD p. 386-387, 413 | A7 |
| Nozzle with normal shock | p02/p01 0.6882; M1 2.07; A1/At 1.790 | Anderson CFD p. 358-361 | A8 |
| Quasi-1D nozzle, exact | exit Mach 3.359; mass flow 0.579 | Anderson CFD Tables 7.3-7.4, p. 319-322 | teaching solver |
| Two 5 deg ramps and a normal shock, Mach 2 | 34.30 deg; 1.821; 37.95 deg; 1.649; 0.8731 | Mattingly Table 10.1, p. 444 | H2 |
| Standard recovery | 0.9706 at Mach 1.5; 0.9537 at 1.7; 0.9445 at 1.8 | Mattingly Table 10.E1, p. 485 | H1 |
| Actuator disk | efficiency at least 0.8 needs thrust coefficient below 1.25 | Mattingly App. L, p. 609-613 | C5 |
| Info-gap robustness | zero at 3; curves cross at 2.4 | DMDU Figs. 5.3 and 5.5, p. 105-109 | D1 |
| Failure probability at three standard deviations | 1.35e-3 | DMDU Fig. 5.7, p. 112 | D3 |
| Optimal hard threshold | about 56.6 for n = 600, unit noise | Brunton-Kutz Fig. 1.23, p. 46 | B5 |
| Information criteria | three AIC and three BIC values | Brunton-Kutz p. 199 | B3 |
| Laminar NACA 0012, Mach 0.8, 10 deg, Re 73 | Cd 0.68287 / 0.67858 / 0.6758 at three orders | Cockburn ch. 1, p. 23-24 (code-to-code, not exact) | optional compressible row |

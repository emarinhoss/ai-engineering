# Task 9 spec: three-ramp inlet over a flight envelope, multi-fidelity, learned feasibility (2026-11-03)

Requested by Éder on 2026-11-03 ("option 1"), after Task 6b. Choices made by Éder: three ramp angles
plus a flight envelope (Mach, wall temperature, altitude) as the six inputs; Euler CFD plus Eckert
as the low-fidelity model. Everything else below is fixed here, before any run. The two-ramp study
stays the main story of the talk; this task is cut if its validation gate fails (schedule below).

## 1. Questions

1. Does active learning beat Latin hypercube and random sampling in six dimensions, where the
   two-ramp replay found only a factor of about 2 (`docs/validation/2026-11-02_replay.md`)?
2. Does a two-level model (Euler + Eckert, then laminar Navier-Stokes) reach a given held-out error
   with fewer Navier-Stokes runs than Navier-Stokes alone?
3. Can a classifier learn where the solver converges, in place of the hand-set total-turning gate?
4. Which ramp angles give the most recovery at the nominal condition while the peak heat flux stays
   under a cap everywhere in the envelope (a robust inverse query), and does SU2 confirm it?

Every answer is reported whichever way it goes.

## 2. Inputs (all six are surrogate inputs)

| Input | Range | Notes |
|---|---|---|
| theta1, theta2, theta3 | 3 to 10 deg each | ramp turning angles; geometry built shock-on-lip at the design Mach 4.0 |
| mach | 3.5 to 4.5 | flight Mach; the geometry does not change with it, so off-design runs spill (M < 4) or ingest shocks (M > 4) |
| altitude_km | 28 to 35 | US Standard Atmosphere 1976, continuous formula; see note |
| T_wall_K | 300 to 600 | isothermal wall on body and cowl |

Altitude note: Éder's choice was 25 to 35 km. At 25 km the unit Reynolds number is about 2.2 times
the 30 km value, so Re at the throat reaches about 1.1e6 to 1.2e6, inside the 1e6 to 3e6 transition
band that `00_decisions.md` section 1.1 uses to justify laminar flow. The lower bound is therefore
28 km (Re at most about 8e5 at Mach 4.5). This is the one change to his choice; it keeps the laminar
argument true over the whole envelope.

## 3. Geometry (family inlet3r, `geometry/inlet3r.py`)

- Ramp 1 from the leading edge O at theta1 to corner C1 = (X1, X1 tan theta1), X1 = 0.10 m as in
  inlet2r. Ramp 2 at theta1 + theta2 from C1 to corner C2. Ramp 3 at theta_t = theta1 + theta2 + theta3
  from C2 to the throat.
- Shock-on-lip at Mach 4.0 for all three shocks: the lip P is where shock 1 (from O) meets shock 2
  (from C1); C2 is the point on ramp 2 from which shock 3 (at its oblique-shock angle) passes through
  P. Cowl, duct (L_D = 0.05 m), throat plane and the external cowl angle follow inlet2r.
- Mesh: inlet2r's eight blocks plus one column for ramp 3 (ten blocks), same spacing rules, same
  mesh-quality gate. Levels coarse, medium, fine as in inlet2r; the pool uses medium.
- First-cell height 0.6 times inlet2r's (12 um at medium). Reason, found while writing gate 5
  before any run: with 20 um the wall-cell Reynolds number reaches 77.6 at the envelope corner
  (28 km, Mach 4.5, 27 deg, 300 K), above the gate's 50; with 12 um it is at most 46.6. V5c checks
  this mesh.

## 4. Gates (`physics/gates.py`, family inlet3r)

1. Attached shocks on all three ramps at the design Mach 4.0 and at the flight Mach.
2. Shock-on-lip construction exists (C2 lies between C1 and the foot of the lip on ramp 2).
3. Every ramp at least 0.02 m long; duct height at least 0.008 m; lip height at most 0.6 of y_top.
4. Total turning at most 27 deg (hard limit). Inside it, convergence is learned (section 7), not
   gated: the two-ramp limit of 24 deg came from one diverged corner, and three weaker shocks may
   converge further.
5. Wall-cell Reynolds number at the flight condition, as in inlet2r.

## 5. Outputs and objectives

- recovery_total at the throat including the terminal normal shock (maximize), as in inlet2r.
- q_peak on ramp 3 and the duct wall (minimize): the inlet2r window moved to the last ramp
  (x from C2, nodes within 2 mm of the throat plane excluded).
- Recorded, not optimized: capture_ratio (mass flow through the throat over freestream flow through
  the lip height), heat load, throat Mach.

## 6. Fidelity levels

- High: laminar Navier-Stokes, medium mesh (the validated inlet2r settings).
- Low: Euler on the same mesh for recovery_total; for heating, the Eckert reference-temperature
  flat-plate relation (`physics/heating.py`) evaluated on ramp 3 with the Euler wall state as the
  edge state and the distance from the leading edge along the wall; q_peak_LF is its maximum over the
  same window. Recovery at low fidelity uses the same throat definition.
- Multi-fidelity model: linear autoregressive (Kennedy and O'Hagan 2000): y_H(x) = rho y_L(x) + d(x),
  one GP for y_L, one GP for the discrepancy d, rho fitted with the hyperparameters. Same GP code as
  Task 4.

## 7. Learned feasibility

Label per run: converged (convergence status "converged") or not (diverged, timeout, nonzero exit).
Classifier: logistic regression on the six scaled inputs and total turning, fitted by plain gradient
descent (a few lines, explainable). Reported: 5-fold cross-validated accuracy, and how many failed
runs it would have skipped against how many good runs it would have lost. It never selects points;
the acquisition multiplies EHVI by the predicted probability of convergence.

## 8. Data and runs

- High-fidelity pool: 160 Sobol points (scrambled, seed 0) over the six inputs, gate-checked, laminar
  medium mesh, max_iter 8000. Low-fidelity pool: Euler at the same 160 points plus 160 more Sobol
  points (seed 1). Runs on the container (four at a time) and on Colab through the queue.
- Measured first, then budgeted: one Euler and one Navier-Stokes run at the nominal point give the
  cost per run; if 160 NS runs do not fit before 2026-11-07 evening, the pool is cut to what fits,
  and the cut is reported.

## 9. Validation before any ML (gate for the whole task)

Nominal point: 7/7/7 deg, Mach 4.0, 30 km, 300 K.

- V5a (hard): Euler at the nominal point against the oblique-shock chain (`physics/shock.py`), V1
  tolerances: the shock-1 angle by the V1 station method (`postprocess/validation.oblique_shock_check`,
  stations at x = 0.04 and 0.08 m on ramp 1), and the wall pressure ratio and wall Mach number on each
  of the three ramps (mean over the middle 60 percent of each ramp, 2 percent). Amended on 2026-11-03
  before the run finished: shocks 2 and 3 converge on the lip a few millimetres apart, so their angles
  are not measured one by one; the ramp plateaus test the same relations (each plateau follows only
  if the shock before it has the right angle).
- V5b (report): Euler recovery_total at the nominal point against the analytic three-shock-plus-
  normal-shock value.
- V5c (hard): Navier-Stokes grid check at the nominal point, medium against fine: recovery_total and
  q_peak inside the V4m tolerances.
- V5d (hard, analytic only): maximizing the analytic chain's recovery (three oblique shocks and a
  terminal normal shock) over the three angles, without constraint, gives equal upstream normal Mach
  numbers for the three oblique shocks to 1e-3 relative (Oswatitsch 1947); this checks the chain
  code. The optimum angles may lie outside the design box; that does not matter for the check.
- V5e (hard): the continuous atmosphere equals the tabulated values at every tabulated altitude to
  1e-4 relative, and the 30 km freestream equals `00_decisions.md` section 1.

## 10. Analyses (after the gate)

1. Replay on the high-fidelity pool, as in Task 4: random, LHS, max-variance, EHVI (with and
   without the feasibility factor), 10 seeds, budgets up to 96; held-out error of both objectives and
   hypervolume regret.
2. Multi-fidelity against single-fidelity: held-out error against the number of NS runs, with the
   whole low-fidelity pool available to the two-level model.
3. Feasibility classifier: cross-validated accuracy, skipped failures, lost good runs.
4. Robust inverse query: maximize predicted recovery at the nominal condition over the three angles,
   subject to P(q_peak <= cap) >= 0.9 at every point of a 5 x 5 x 5 grid over (mach, altitude,
   T_wall); cap fixed before the answer as the 40th percentile of the pool's q_peak. One
   confirmation run at the worst-case envelope point of the answer (C2 tolerance).

## 11. Schedule and cut-off (talk on 2026-11-13; no new features after 2026-11-09)

- 2026-11-04: atmosphere, inlet3r geometry and mesh, gates, config, metrics, tests.
- 2026-11-05: validation V5a to V5e. **Go/no-go:** a hard failure that is not fixed by the evening
  stops the task; the deck keeps the two-ramp study and says what was attempted.
- 2026-11-05 to 11-07: pools. 2026-11-08: analyses and the confirmation run.
- 2026-11-09: report and one talk section of about 5 minutes (taken mainly from section 5).

## 12. Acceptance

Gate V5 passed and recorded; pools recorded with every failure kept; the four questions answered
from records with the comparisons stated as measured, including a null result; tests for the
atmosphere, the inlet3r geometry (all three shocks through P to 1e-9 m; theta3 -> 0 reproduces
inlet2r's lip), the gates, the low-fidelity heating, the two-level GP on a synthetic pair and the
classifier on a synthetic set.

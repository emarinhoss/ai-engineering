# Task 0 decisions: physics, numerics, objectives, tolerances

Written 2026-11-01 (Day 1) by Fable 5.1 as physics and numerics lead. Éder owns these choices and
must confirm the items marked **CONFIRM** before Task 1 starts. Every other spec cites this file.

All analytic numbers below are evaluated from the stated formulas (calorically perfect air,
gamma = 1.4, R = 287.058 J/kg/K, Sutherland viscosity, Pr = 0.72). They are expectations, not
results. The code's unit tests must reproduce them; nothing here comes from a CFD run.

## 1. Flight condition

**Decision: Mach 4.0, US Standard Atmosphere 1976 at 30 km, sub-scale model (body about 0.3 m).**
**CONFIRM** (alternative: Mach 5, same code, see 1.3).

| Quantity | Value |
|---|---|
| T_inf | 226.509 K |
| p_inf | 1197.03 Pa |
| rho_inf = p/(R T) | 0.018410 kg/m^3 |
| a_inf | 301.71 m/s |
| U_inf (M = 4) | 1206.8 m/s |
| mu_inf (Sutherland, mu_ref 1.716e-5, T_ref 273.15, S 110.4) | 1.4752e-5 Pa s |
| Unit Reynolds number | 1.506e6 1/m |
| T0 | 951.3 K |
| p0_inf = p_inf (1 + 0.2 M^2)^3.5 | 1.8175e5 Pa |
| Dynamic pressure 0.7 p M^2 | 13.4 kPa |

### 1.1 Why laminar is defensible

Body length is 0.25 to 0.33 m, so the freestream-based Reynolds number at the throat is at most
5e5 (post-shock edge units: about 7e5). Transition on sharp cold-wall ramps at Mach 3 to 4
occurs at Re_x of 1e6 to 3e6 in ground tests and later in flight; the Re_theta/M_e at the end of
ramp 1 is roughly 100, well below the 200 to 300 transition band. Laminar Navier-Stokes is the
standard model at these conditions. We say plainly in the talk that this is a sub-scale,
high-altitude condition chosen to keep the flow laminar; a full-scale vehicle at 25 km would be
turbulent and would need RANS. Backup (cut first if time is short): one Spalart-Allmaras run at
the design point to show the sensitivity of both objectives to the turbulence assumption.

### 1.2 Wall boundary condition

**Isothermal wall, T_w = 300 K** on all solid surfaces (T_w/T0 = 0.32). Rationale: an isothermal
wall is required for a meaningful heat flux objective; 300 K is the standard cold-wall
condition of short-duration heat-transfer tests and the same wall temperature is used in the
Fay-Riddell validation. The cold wall also thins the boundary layer and delays laminar
separation at the compression corner. A hot-structure wall (600 to 900 K) would lower heating
by a factor 2 to 3; T_w is a fixed input of every run record and may become a surrogate input
later (stretch, see section 3).

### 1.3 Why Mach 4 rather than Mach 5

Both are supported by the same code (one config value). At Mach 5 and 30 km: T0 = 1359 K (edge
of calorically perfect validity in stagnation regions), the laminar compression-corner
interaction separates at smaller ramp angles, and the two-ramp family gives total pressure
recovery of only 0.13 to 0.25 because the terminal normal shock sits at throat Mach 3 to 4. At
Mach 4: T0 = 951 K (perfect gas is accurate), milder separation, recovery 0.24 to 0.43, which
is 35 to 65 percent of the MIL-E-5008B reference value of 0.67. Mach 4 keeps heating a first
order design driver (ramp heating 15 to 40 kW/m^2, stagnation heating on a 10 mm cylinder about
240 kW/m^2) while making the numerics more robust. The real-gas question disappears.

## 2. Geometry family

**Two-ramp external compression inlet with a cowl, truncated at a throat plane normal to the
duct, with the cowl lip placed by the inviscid shock-on-lip rule.**

Points and parameters (all lengths in metres, origin at the ramp leading edge):

- Leading edge O = (0, 0), sharp.
- Ramp 1: angle theta1, horizontal extent X1 = 0.100. Corner C = (X1, X1 tan theta1).
- Ramp 2: angle theta_t = theta1 + theta2, straight from C to the throat plane.
- Cowl lip P = (x_P, y_P): the intersection of the ramp-1 shock (angle beta1 from O) and the
  ramp-2 shock (angle theta1 + beta2' from C), both from the oblique shock relations at the
  design Mach. This is the standard shock-on-lip design rule; the geometry is therefore fully
  determined by (theta1, theta2).
- Cowl inner surface: straight line from P parallel to ramp 2, length L_d = 0.050. The duct is a
  parallel channel of height h = (P - C) . n2 with n2 the unit normal to ramp 2 (internal
  contraction ratio 1, so no Kantrowitz starting issue).
- Throat plane: segment normal to the duct axis at distance L_d from the lip, from the body wall
  to the cowl inner wall. This is the duct outlet marker and the plane on which recovery is
  measured.
- Cowl outer surface: from P at angle theta_t + 6 degrees to the external outlet (vertical line
  at the x of the duct-exit cowl point). The cowl is a sharp wedge of 6 degrees.
- Upstream boundary x_in = -0.030 (symmetry plane y = 0 ahead of the leading edge). Top
  boundary y_top = 0.200 (freestream). The merged shock leaves through the top or the external
  outlet; all boundaries are supersonic.

Design point for validation: theta1 = theta2 = 8 deg: x_P = 0.2023, y_P = 0.0755, h = 0.0309,
throat Mach 2.962 (inviscid), p_th/p_inf = 4.08, two-shock recovery 0.9316.

### 2.1 Design variables and bounds

**Two design variables: theta1 in [5, 12] deg, theta2 in [5, 14] deg, with theta1 + theta2 <= 24
deg (gate 4).** Total turning 10 to 24 deg; all shocks attached with margin (theta_max at M = 3 is
34 deg). The 24 deg cut (Task 0 had 26) removes the corner where the laminar solution does not
converge: on 2026-11-01, 12/14 diverged on two meshes with entropy fix 0.1 and 0.3 and CFL caps 20
and 5, while 12/12, 8/14 and 5/14 converged (runs/dev/2026-11-01_inlet_box_diagnostics); the gate
rejects such designs before submission and excludes 4 of the 96 pool points. Over the box (inviscid):
x_P in [0.151, 0.282], h in [0.019, 0.050], throat Mach 2.41 to 3.32, two-shock recovery 0.80
to 0.98, recovery including the terminal shock 0.24 to 0.43.

Why not a cowl position variable: with recovery and heating as the two objectives, moving the
lip downstream of the shock-on-lip point (spillage) costs nothing in either objective and
moving it upstream (shock ingestion) costs in both, so the Pareto set would sit on the bound.
Cowl position only matters once mass capture is an objective or a constraint; that is a third
objective and out of scope. Why not more ramps: a 3-ramp family reaches better recovery but
needs a 3D design space, which the run budget (about 100 runs) resolves poorly, and the 2D
space lets every surrogate quantity be plotted as a map in the talk.

Why not wall temperature as a third input: it is a boundary condition, not a design choice, and
as an optimisation variable it drives trivially to its hot bound. Stretch option (only if Task 1
timing gives more than 150 runs): add T_w in [300, 900] K as a context input and report
conditional Pareto fronts. Default: cut.

### 2.2 Expected flow features (so nobody is surprised)

Ramp-1 shock, laminar boundary layer with weak viscous interaction near the sharp leading edge
(chi-bar about 0.1 to 0.3), compression-corner shock-boundary-layer interaction with incipient
laminar separation estimated near theta2 of 9 to 10 deg for this cold wall (Needham-Stollery
scaling), so the upper third of the theta2 range has a steady separation bubble and a
reattachment heating peak on ramp 2. Viscous displacement makes the real shocks slightly
steeper than the inviscid design, so the viscous design point has slight shock ingestion and
a weak reflection inside the duct. Cowl boundary layer from a sharp lip. Separation bubbles
that do not converge to a steady state are a recorded failure mode, not something to tune away.
Found on 2026-11-01 (runs/dev): within about 30 mm of a sharp leading edge SU2's wall-node
temperature departs from the imposed 300 K (weak imposition where the first cell is large
relative to the local boundary layer); this region is outside both objectives by construction.

## 3. Objectives (exact definitions)

Both are computed by `postprocess/metrics.py` from the SU2 surface CSV of the throat and wall
markers. SI units throughout; SU2 runs with `REF_DIMENSIONALIZATION= DIMENSIONAL`.

### 3.1 Total pressure recovery (maximise)

On the throat plane (duct outlet marker), with nodes i, trapezoidal weights w_i along the
segment, unit normal n = duct axis direction, mass flux phi_i = rho_i (u_i n_x + v_i n_y),
local total pressure p0_i = p_i (1 + 0.2 M_i^2)^3.5 and the normal-shock total pressure ratio
pi_NS(M) (equal to 1 for M <= 1):

- `recovery_throat` = sum(w phi p0) / sum(w phi) / p0_inf. Mass-flux-weighted mean of p0 at
  the throat, divided by freestream p0. This is the CFD-only quantity.
- `recovery_total` = sum(w phi p0 pi_NS(M)) / sum(w phi) / p0_inf. **This is the objective.**
  Each streamtube is taken through a normal shock at its own Mach number (none if already
  subsonic), which is the standard critical-operation assumption for an inlet feeding a
  subsonic diffuser. It is what makes external compression worth anything: without the
  terminal shock the best inlet in both objectives is a flat plate.
- Diagnostics also recorded: mass-averaged throat Mach, `recovery_total_bulk` (recovery_throat
  times pi_NS at the mass-averaged Mach), capture ratio = sum(w phi) / (rho_inf U_inf y_P),
  and SU2's own `AVG_TOTALPRESS` from `MARKER_ANALYZE` on the same marker (cross-check, must
  agree with recovery_throat x p0_inf within 0.5 percent).

### 3.2 Peak wall heat flux (minimise)

- Surface: the body wall downstream of the compression corner, x >= X1, i.e. ramp 2 including
  the part under the cowl, excluding nodes within 2 mm of the throat plane (outlet boundary
  nodes). Ramp 1 is excluded because a sharp flat plate has a 1/sqrt(x) heating singularity at
  the leading edge whose computed peak is set by the first cell, not by the design. The cowl is
  excluded for the same reason (sharp lip) and reported separately.
- `q_peak_W_m2` = max over that surface of the wall heat flux into the wall (W/m^2), with the
  node location `x_q_peak_m`. Sign convention is checked at load time: for a cold wall the
  integral over the body must be positive; the loader fails if it is not.
- Diagnostics: integrated heat load on the same surface (W per metre depth), `q_peak_cowl`
  (cowl inner surface excluding the first 2 mm from the lip), ramp-1 heat flux profile
  (validation against Eckert, see 4).

## 4. Validation cases and how each is set up in SU2

All at the section 1 freestream unless stated. Pass/fail types: **hard** = must pass before any
production run or ML (a failure means a bug in mesh, BC, units or scheme, and is fixed, not
tuned); **soft** = reported with an explanation; a soft miss does not block.

### V1 Oblique shock, inviscid (Task 1)

Single wedge, theta = 10 deg, X_w = 0.150 m, `SOLVER= EULER`, slip wall. Shock located on two
vertical lines x = 0.04 and x = 0.08 as the y where p crosses the midpoint of p_inf and the
post-shock plateau; beta from the two locations; plateau = median p between wall + 1 mm and
shock - 3 mm at x = 0.08.
Analytic (M = 4, 10 deg): beta = 22.234 deg, p2/p1 = 2.5060, M2 = 3.2861, rho2/rho1 = 1.8853.
Tolerances (hard): |delta beta| <= 0.5 deg; p2/p1 within 2 percent; M2 within 2 percent.

### V2 Laminar wedge (Task 1 timing case, Task 2 heating check)

Same wedge, `SOLVER= NAVIER_STOKES`, isothermal 300 K.
- V2a (report): plateau pressure above the boundary layer at x = 0.08 (between wall + 3 mm and
  shock - 3 mm) must be higher than inviscid by 0 to 6 percent (weak viscous interaction raises
  it; a value below the inviscid one or above 6 percent is investigated).
- V2b (hard): wall heat flux on 0.3 <= x/X_w <= 0.9 against the Eckert reference-temperature
  laminar flat plate with post-shock edge conditions (M_e = 3.286, T_e = 301.1 K, p_e = 2999.8
  Pa; T* = 0.5 (T_e + T_w) + 0.22 (T_aw - T_e), r = sqrt(Pr), St = 0.332 Re*_x^-1/2 Pr^-2/3,
  q = St rho* u_e c_p (T_aw - T_w)). Expected 26.6 kW/m^2 at x = 0.05 and 19.8 kW/m^2 at
  x = 0.09. Mean absolute relative deviation over the window <= 10 percent and no point beyond
  15 percent. Eckert versus similarity solutions is good to about 3 percent at these conditions,
  so 10 percent leaves room for viscous interaction and discretisation.

### V3 Fay-Riddell stagnation heating (Task 2)

Circular cylinder, R = 10 mm, laminar, isothermal 300 K, half domain phi in [0, 100] deg,
symmetry on the stagnation line, farfield (supersonic inflow) on the outer arc
r_out(phi) = R (2.0 + 1.5 sin^2 phi), supersonic outlet at phi = 100 deg.
Reference (two-dimensional Fay-Riddell constant 0.57, modified-Newtonian velocity gradient,
perfect gas, Lewis term dropped):
q_FR = 0.57 Pr^-0.6 (rho_e mu_e)^0.4 (rho_w mu_w)^0.1 sqrt(du_e/dx) (h0 - h_w),
du_e/dx = (1/R) sqrt(2 (p02 - p_inf) / rho_e), with p02 the pitot pressure (21.068 p_inf =
25219 Pa), rho_e = 0.09235 kg/m^3, mu_e = 4.029e-5, rho_w = 0.2928, mu_w = 1.846e-5,
du_e/dx = 7.213e4 1/s, h0 - h_w = c_p (951.3 - 300). Expected q_FR = 2.44e5 W/m^2.
Tolerances: stagnation-point heat flux within 15 percent of q_FR on the fine mesh (hard; the
correlation itself and the Newtonian gradient carry about 10 percent); grid study with
first-cell heights 8, 4, 2 micrometres, medium-to-fine change <= 5 percent (hard). Shock
stand-off versus Billig (delta/R = 0.386 exp(4.67/M^2) = 0.517) within 15 percent (report).
Also report q_FR evaluated with du_e/dx extracted from the CFD edge velocity, which removes
the Newtonian approximation.

### V4 Inlet design point (Task 2)

theta1 = theta2 = 8 deg.
- V4e (hard), `SOLVER= EULER`: area-averaged p0/p0_inf on the throat plane within 2 percent of
  the two-shock value 0.9316; area-averaged throat Mach within 2 percent of 2.962. In the
  inviscid case the lip is exactly on the shocks, so the duct flow is uniform.
- V4v (soft), laminar: p0/p0_inf area-averaged over the middle 50 percent of the duct height
  within 5 percent of 0.9316, with the difference explained (expected: slight ingestion from
  displacement and the reflected shock). The mass-averaged value with boundary layers is the
  objective, not a validation quantity, and is reported next to it.
- Mesh convergence (hard): coarse, medium, fine levels (factor 1.4 per direction and in
  first-cell height) at the design point, plus medium and fine at the most demanding corner
  (theta1 = 12, theta2 = 14: highest throat pressure, wall-cell Reynolds number 42 at medium).
  Medium-to-fine change in recovery_total <= 2 percent relative and in q_peak <= 5 percent at
  both points. If medium fails, fine becomes production and the timing gate is
  re-evaluated; if that is unaffordable, the discretisation uncertainty is reported on every
  plot.

## 5. Tolerance table (replaces every "(proposed)" in PLAN.md)

| Id | Case | Quantity | Tolerance | Type |
|---|---|---|---|---|
| V1 | Euler wedge 10 deg | beta | +-0.5 deg | hard |
| V1 | Euler wedge 10 deg | p2/p1, M2 | 2 percent | hard |
| V2a | laminar wedge | plateau p vs inviscid | +0 to +6 percent | report |
| V2b | laminar wedge | q_w vs Eckert, 0.3 <= x/X_w <= 0.9 | mean 10 percent, max 15 percent | hard |
| V3 | cylinder R = 10 mm | q_stag vs Fay-Riddell (fine mesh) | 15 percent | hard |
| V3 | cylinder grid study | q_stag medium vs fine | 5 percent | hard |
| V3 | cylinder | stand-off vs Billig | 15 percent | report |
| V4e | Euler inlet 8/8 | throat area-avg p0 ratio, Mach | 2 percent | hard |
| V4v | laminar inlet 8/8 | core (mid 50 percent) p0 ratio | 5 percent | soft |
| V4m | inlet grid study | recovery_total; q_peak, medium vs fine | 2 percent; 5 percent | hard |
| X1 | every run | SU2 AVG_TOTALPRESS vs our mass average | 0.5 percent | hard |
| T1 | Task 1 | wall time per medium-mesh production run, 2 cores | <= 5 min go; 5 to 10 min pool 64 and Colab Pro; > 10 min coarse mesh is production | gate |
| C1 | Task 4 | 90 percent interval coverage on held-out | reported; outside 80 to 97 percent is flagged | report |
| C2 | Task 5 | confirmation run inside the 90 percent interval | pass/fail reported | report |

## 6. Numerics (defaults; Task 1 verifies every key against the pinned SU2 version)

- SU2 v8.x release binary (pinned in Task 1, exact version string recorded in every run).
- `FLUID_MODEL= STANDARD_AIR`, Sutherland viscosity, `CONDUCTIVITY_MODEL= CONSTANT_PRANDTL`,
  `PRANDTL_LAM= 0.72`, `REF_DIMENSIONALIZATION= DIMENSIONAL`, `FREESTREAM_OPTION=
  TEMPERATURE_FS`, `MACH_NUMBER= 4.0`, `AOA= 0`.
- Convective scheme `ROE` with `ENTROPY_FIX_COEFF= 0.3`, `MUSCL_FLOW= YES`, limiter
  `VENKATAKRISHNAN_WANG`, `VENKAT_LIMITER_COEFF= 0.05`; viscous terms second-order central;
  gradients `WEIGHTED_LEAST_SQUARES`. Task 0 proposed `AUSMPLUSUP2`; on 2026-11-01 four
  800-iteration Euler-wedge variants (SU2 v8.2.0, medium wedge mesh, this repository's
  config) gave: AUSMPLUSUP2 at fixed CFL 5 diverged (Error Exit at iteration 50);
  AUSMPLUSUP2 with adaptive CFL capped at 20 stalled at log10 rms density -2.5;
  AUSMPLUSUP2 with the plain Venkatakrishnan limiter stalled at -2.4; ROE with entropy fix
  0.1 and the same CFL settings fell from -3.45 to -12.05 in 603 iterations. ROE is therefore
  the default. The cylinder (V3) then showed Roe's carbuncle with entropy fix 0.1 (coarse stalled
  with a non-monotonic heating distribution, medium diverged, fine stalled; see
  runs/dev/2026-11-01_cylinder_v3_attempt1). A six-scheme comparison (attempt 2: HLLC, AUSM+-up2,
  SLAU2, JST, first-order Roe, Roe with entropy fix 0.3) and a split test (attempt 3) showed that
  the entropy fix, not the CFL cap, is the cure: entropy fix 0.3 at CFL max 20 converges on all
  three cylinder meshes and gives stagnation heating within 0.3, 1.1 and 4.5 percent of
  Fay-Riddell (coarse, medium, fine). On the laminar wedge the larger fix moves the Eckert
  deviation from 0.75 to 1.6 percent (gate 10). Final: `ENTROPY_FIX_COEFF= 0.3` for every family.
- `TIME_DISCRE_FLOW= EULER_IMPLICIT`, `LINEAR_SOLVER= FGMRES`, `LINEAR_SOLVER_PREC= ILU`,
  15 Krylov iterations, tolerance 1e-6; `CFL_NUMBER= 1.0` with `CFL_ADAPT= YES`
  (down 0.5, up 1.05, min 1.0, max 20). The Task 0 values (up 1.2, max 100) made the CFL
  controller hunt between 0.5 and 47 with the residual stuck near -3.
- Convergence: `CONV_FIELD= RMS_DENSITY`, `CONV_RESIDUAL_MINVAL= -10` (the initial rms density
  level is about -3.4 in dimensional units, so -10 is more than six orders below it),
  `CONV_STARTITER= 200`, `ITER= 6000` (wedge 4000). The postprocess
  independently classifies each run: converged (residual drop >= 5 orders and both objectives
  drift < 0.2 percent over the last 20 percent of iterations), stationary (objectives drift
  < 0.2 percent but residual stalled), not_converged, diverged (NaN), timeout, error.
  Only converged and stationary runs train the surrogate; the status is recorded on every
  point.
- Boundary markers: `MARKER_ISOTHERMAL` (walls, 300 K) or `MARKER_EULER` for Euler cases,
  `MARKER_SYM` (plane ahead of the leading edge, cylinder stagnation line), `MARKER_FAR`
  (inlet and top; supersonic inflow imposes the freestream), `MARKER_SUPERSONIC_OUTLET` (duct
  and external outlets). `MARKER_ANALYZE= (outlet_duct)` with `MARKER_ANALYZE_AVERAGE=
  MASSFLUX`. Output: `SURFACE_TECPLOT_ASCII` always, volume `TECPLOT_ASCII` for validation cases
  only (SU2's CSV writers hold only the conservative variables; found 2026-11-01).
- Mesh (medium): body and cowl first cell 20 micrometres (wall-cell Reynolds number about 20
  on ramp 2, about 20 to 25 cells inside a 2 mm boundary layer), wall-normal growth <= 1.15,
  61 nodes body-to-lip-line, 33 nodes lip-line-to-top, streamwise first cell 0.1 mm at the
  leading edge, 0.3 mm at the corner and the lip, maximum 1.0 mm. Expected about 25 k cells.
  Coarse and fine scale all sizes by 1.4 and 1/1.4. Cylinder medium: 81 x 81 nodes, first cell
  4 micrometres (wall-cell Reynolds number 22, about 20 cells in the 78 micrometre thermal
  layer); coarse 8 micrometres 57 x 57; fine 2 micrometres 113 x 113.
- Mesh-quality gate (every mesh, before anything is written to the queue): no inverted or
  zero-area cell; minimum interior angle >= 40 deg; first-cell height within 10 percent of the
  requested value on every wall; wall-normal growth ratio <= 1.25 anywhere; aspect ratio
  <= 5000; duct height >= 8 mm; x_P - X1 >= 0.02 m. A failure is an error with the offending
  value, not a warning. Wall-cell Reynolds number gate (physics gate 5) is 50; Task 0 wrote 40,
  which excluded the (12, 14) corner of the box at 42; the grid study covers that corner instead.

## 7. Run budget and sampling design

- Pool-based replay. A Sobol design (scrambled, seed 0) of 96 points in the box, run in
  sequence order so any prefix is usable; 64 is the minimum (balanced prefix). All strategies
  (random, LHS, two active-learning variants) are replayed offline against this pool with 10
  seeds, so the comparison is on identical ground truth and costs no extra CFD.
- Compute (confirmed by Éder 2026-11-01): Colab runtime with 8 vCPU and 51 GB for all runs;
  the worker notebook uses 4 MPI ranks on it. Task 1 measured about 0.1 s per iteration for
  the 17.7k-cell wedge on 2 ranks of that machine, so a medium inlet run (30.6k cells, about
  1300 to 2200 iterations) is 4 to 6 minutes on 2 ranks and less on 4; the pool of 92 fits in
  one night.
- Budget estimate (Task 0): medium mesh, 2 cores, about 5 min per run gives 12 per hour; pool of 96 plus
  about 20 validation and mesh-study runs plus 3 confirmation runs is about 120 runs, two
  Colab nights. If Task 1 gives more than 5 min, see gate T1.
- The surrogate (Gaussian process on 2 inputs, <= 100 points) runs on CPU in seconds; the
  Colab GPU is not needed and we will say so rather than pretend otherwise.

## 8. What changed relative to PLAN.md (summary; PLAN.md carries the same list)

1. Mach 4 at 30 km, sub-scale, instead of an open choice; laminar justified by Re <= 5e5.
2. Two design variables (theta1, theta2) with the cowl lip fixed by the shock-on-lip rule; cowl
   position and wall temperature are not design variables (reasons in 2.1).
3. recovery objective includes the terminal normal shock per streamtube (3.1).
4. Heat flux objective is the peak on ramp 2 including the duct wall (3.2).
5. Mesh generator is a numpy structured multi-block writer in SU2 format, not gmsh: simpler to
   explain, deterministic, and the quality metrics come for free.
6. Tolerances replaced as in section 5 (oblique shock 3 percent -> 2 percent plus 0.5 deg;
   Fay-Riddell 20 -> 15 percent plus a grid-convergence requirement; inlet recovery 5 percent ->
   2 percent inviscid hard, 5 percent viscous-core soft; mesh-convergence and cross-check gates
   added; Eckert flat-plate heating check added).
7. Active-learning comparison done as a pool-based offline replay (7).
8. A `physics/` package (analytic relations and gates) and a `runs/` folder of committed run
   records are added to the layout.

## 9. Task 12 owner rulings (M250 engine, drone conceptual design)

Added 2026-11-24. These are owner (Éder) rulings on Task 12, recorded here because until now they
were only in commit messages, a docstring and the review files. Each points to the commit and
record that carry it out. Nothing below is a new result.

- **R-a (2026-11-23).** Re-size the pusher around the Rolls-Royce M250-B17F (`RR_M250_B17F`, 450 shp,
  212 lb). The TP100 design and its records are kept for comparison. Commit 72bbec7; record
  `runs/task12/stage1/2026-11-23`; report `docs/validation/2026-11-23_task12_conceptual_m250.md`.
- **R-b (2026-11-23).** M250 SFC allowance 1.02 (the table is calibrated to the brochure's guaranteed
  maximum SFC, so 1.02 covers installation losses only); propeller rpm 2,030. TP100 records keep
  1.05 and 2,158. Commit 72bbec7; ledger copy in `runs/task12/stage1/2026-11-23/ledger.yaml`.
- **R-c (2026-11-23).** SFC +-10 % on top of the allowance and power +-10 %, with the power band as a
  cap on the available power: SFC at a given shaft power does not change with it. Commit 72bbec7;
  records `runs/task12/stage3/2026-11-23/m250_info_gap` and `m250_robust_105`.
- **R-d (2026-11-23).** The baseline is the robust design at h_T = 1.05, from a refined grid. Commit
  4d6dac6; record `runs/task12/stage3/2026-11-23/m250_robust_105_refined`; report
  `docs/validation/2026-11-23_task12_m250_robust_refined.md`. Superseded in its cell by the
  baseline-cell choice below; the rule (h_T 1.05) stands.
- **R-e (2026-11-24).** The power cap is clipped at the rated power: a multiplier above 1 cannot take
  the available power above the rating, one below 1 still cuts it. Commits ee68128
  (`TableEngine.power_available`) and 319a20e (the info-gap take-off row, review MB-2). The TP100
  "rescale" records are unchanged.
- **Baseline cell (2026-11-24).** After review MB-1 (`docs/reviews/2026-11-24_task12_m250_baseline_review.md`),
  Éder chose W/S 16, A 7 over W/S 18, A 7 for its cliff margin (cliff h 1.194 against 1.084, for 1 lb
  of take-off weight). Commit 27e1cda; record `runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7`;
  report `docs/validation/2026-11-24_task12_m250_baseline_ws16_a7.md`.
- **MD-1 erratum (2026-11-24).** One candidate of `m250_robust_105` was lost to a working-tree stash.
  The erratum is in `docs/reviews/2026-11-24_task12_m250_baseline_review.md` (section "Draft erratum
  for MD-1"); the report was not changed.
- **R-f (2026-11-24, R6).** The M250-B17F engine's maximum operating altitude and its in-flight
  relight envelope are declared **design assumptions**. No public source gives either one. The
  Stage 1 R6 rows stay "no source". The 23,000 ft ceiling requirement is above every certified B17
  installation found, all at 20,000 ft. Cross-references and the searches that came back empty:
  `docs/validation/2026-11-24_task12_m250_r6_sources.md`. Not re-run: no report was regenerated.

### Owner rulings on the Stage 3 review of the M250 baseline (Éder, 2026-11-24/25)

Answers to the owner questions of `docs/reviews/2026-11-24_task12_stage3_m250_review.md`. The code and
report-generator changes that carry them out are in the commits of 2026-11-25 (engine, perf, aero,
rotation reports; `measurement/ground_effect_validation.py`). No Stage 3 record was re-run for these:
the baseline changes with G-4 and the runs are redone on the new one.

- **G-1 (R7; review S3M-5, question 1).** Field length is the computed take-off and landing distance
  over a 50 ft obstacle, unfactored. No FAR 1.666 or 1.15 factor. Reason: the requirement is the
  distance the aircraft needs, and the repository has judged R7 this way since Stage 1; the factored
  figure (landing 5 % margin, not robust) would be a different requirement. The perf report states
  the basis.
- **G-2 (W0 row; S3M-12, question 2).** Anderson's first estimate with his historical empty fraction of
  0.62 counts as explained, not failed. Reason: 0.62 is a crewed-aircraft historical fraction and does
  not apply to an uncrewed composite UAV. The report gives three values side by side: 0.62 (6,396 lb),
  Stage 1's fraction (3,061 lb) and Anderson's build-up (3,376 lb); the perf report generates them from
  the record.
- **G-3 (CD0 row; S3M-2, question 3).** The row uses Anderson's propeller-aircraft Cfe 0.0043 ((8.40),
  p. 414), with the jet-curve value 0.00312 (Fig. 2.55) reported alongside. Reason: Fig. 2.55's curve is
  drawn through jet fighters and transports; the propeller value is the book's own for this class of
  aircraft. The method resolves CD0 to about +-20 %; the row cannot confirm Stage 1's CD0 to +-10 %.
- **G-4 (propeller; S3M-3, question 4).** Stage 1 moves to the App. L efficiency per flight condition,
  with the static thrust capped at the momentum limit. Reason: App. L gives 0.62 at sea-level climb
  against the flat 0.80 (recorded, perf report), and the review's probe found Stage 1's static thrust cap
  above the ideal momentum value for the disk (a probe, not a recorded run). Implemented by another agent in `conceptual/`; the Stage 1 and Stage 3
  records are redone on the new baseline.
- **G-5 (missing rows; S3M-10, question 5).** Before Gate B only Anderson's static-margin route
  ((8.76)-(8.78), p. 444) is coded (`measurement/anderson.py`, rows in `measurement/stage3_aero.py`).
  Waived: the SU2 polars and C_L,max, the gust load factor second source, and the blade-element
  propeller efficiency. They are listed as open in the Gate B report. Reason: only the static-margin
  route has a library relation that can be coded now; the others need SU2 runs on Colab, a second gust source
  the library does not have, or a blade-element code (S3M-10).
- **G-6 (engine closing row; S3M-6, question 6).** Accepted as "rests on the model" until part-power
  or altitude data exist, carried by the +-10 % SFC band. The engine report states that the brochure
  rows cannot discriminate: a constant SFC also passes.
- **G-7 (ground effect; S3M-9, question 7).** Raymer (12.61) is added as a second reference to the
  ground-effect validation and the rotation report. Result as reported: within Raymer, outside
  Anderson; the books disagree by 29 % at h/b 0.1. Rotation meets its limit with or without ground
  effect, so the validation does not decide the row.

Question 8 of the review (R13: second neutral-point estimate before Gate B) was not ruled in this
batch. The aero report states that R13 is met by layout construction with the same downwash model as
Stage 1 (S3M-8) and that an independent neutral point is needed.

### Owner rulings on the App. L baseline (Éder, 2026-11-26)

- **Edits A and B (APL-1, APL-2).** Approved: the transit-cliff score uses the record's propeller, and the
  TP100 ledger pins `propeller_model: flat` (commit 8501980). Optional edit C (drop the inert `eta_p` from
  the info-gap study under app_l) not made.
- **G-8 (R13; Stage 3 review question 8, S3A).** VSPAERO's wing-and-tail neutral point is re-run on the
  App. L baseline (3,160 lb record, `runs/task12/stage3/2026-11-25/m250_baseline_appl/`) without the
  fuselage, and quoted in Gate B with that limit stated. Not a fuselage-inclusive estimate.
- **G-9 (take-off factor; APL-5).** A recorded sweep of take-off distance over the propeller
  real-to-ideal factor f is run on the App. L baseline and quoted next to R7 in Gate B, with f at static
  and take-off conditions stated as a judgement beyond App. L.

### Owner rulings at Gate B (Éder, 2026-11-26; review docs/reviews/2026-11-26_task12_gateB_performance_review.md)

- **B-1 (7.4 part 1).** The declared evidence classes (independent, partly independent, coding check,
  ruling or waiver, assumption, layout construction) stand in for "independent measurement" for every
  requirement.
- **B-2 (composite band, GB-1).** Record an info-gap run on the frozen design with the composite band
  acting on the Table 15.4 component factors, plus an empty-weight band; decide on a re-size from the result.
- **B-2a (result and re-size, 2026-11-26; record runs/task12/stage3/2026-11-26/composite_band_study/).** The
  agent's mapping is confirmed: `composite_model: saving` (each Table 15.4 saving scaled by (1 - c)/0.05, so
  c = 1.00 is metal) and `empty_weight_factor` 1.0 with band 0.95-1.05. With both bands the frozen design fails
  R5 (guarantee horizon 0.906, worst endurance at h = 1 is 2.915 h against 3.5 h). The design is re-sized
  robustly to h_T 1.05 with both bands acting, and Stage 3, VSPAERO, V-n and the compliance table are re-run
  on the new design before the Gate B pass.
- **B-2b (cell, 2026-11-26; record runs/task12/stage3/2026-11-26/m250_bands_resize/).** W/S 16, A 7 has no
  design under both bands. Before a cell is chosen, the full info-gap study is run on W/S 13 A 8 and W/S 13 A 9
  as well as the tool's lightest design W/S 14 A 8 (cliff horizon 1.062); the cell is chosen from the three
  recorded horizons.
- **B-2c (new baseline, 2026-11-27; record runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/).** W/S 13,
  A 8 is the new baseline (W0 3,517 lb, L_sized 11.00 h, span 46.5 ft; R5 guarantee 1.0501, cliff 1.0924,
  R7 1.2845), chosen over 14/8 for its cliff and R7 margin. The frozen design is superseded. Stage 3,
  VSPAERO wing+tails, the V-n check, the compliance table and the Gate A re-check are re-run on it.
- **B-9 (Gate B on W/S 13 A 8, 2026-11-27; review docs/reviews/2026-11-27_task12_gateB_ws13a8_review.md).**
  (a) Stage 1 package: the baseline record, compliance table and the Gate A re-check are accepted; A9 and A11 are
  inherited from the 2026-11-25 designs, and a Stage 1 package for the new sizes is a preliminary-design entry item.
  (b) The G-9 take-off sweep over f is re-run on the new baseline.
  (c) Ceiling: quote the engine-cycle value 30,407-30,432 ft with the caveat that Stage 1's 31,738 ft reads above the
  30,000 ft engine-table top (clamped); table reads above 30,000 ft are flagged; extending the table to 35,000 ft is a
  preliminary-design entry item. R12 is met by every value.
  (d) B-4 confirmed at the new margins (0.296 g positive, 0.196 g negative): V_C 110 kt and the gust rule stand; the
  preliminary-design envelope-protection item covers level flight at every altitude and a gust criterion above V_C.
  (e) G-2 and B-5 stand at the new values (Anderson W0 +114.9 %; take-off power -11.6 %, CD0 -14.3 %, K.3 -5.7/-5.6 %).
  (f) B-6 covers the VSPAERO L2 full-fuel margin 0.004 above the 5-15 % band.
  (g) The +-5 % empty-weight band stands; the gap to Anderson's build-up (+14.7 %) and to Table 15.2 is a named
  preliminary-design risk.
- **B-10 (gate close-out, 2026-11-27; report docs/validation/2026-11-27_task12_performance.md).** (a) B-8 is
  confirmed at the new baseline's nominal 8 h horizon 0.4135; no new target. (b) The ledger label of
  `prop_real_to_ideal` becomes a judgement (APL-6); no number changes. (c) Before the Gate B ruling, three gaps are
  closed from existing records: a recorded pytest report at the gate commit, a worst-case robustness-curve figure
  (spec 7.3), and the Gate A re-check generated as a record. (d) Gate B passes on the W/S 13, A 8 baseline once (a)-(c)
  are recorded, with the open items carried to preliminary design.
- **B-11 (Gate B passed, 2026-11-27).** The B-10 conditions are recorded: the B-8 confirmation (B-10a), the ledger
  relabel of `prop_real_to_ideal` to `assumed` (fe74282), the robustness figure
  (runs/task12/stage3/2026-11-27/robustness_figure_ws13a8/), the Gate A re-check record
  (runs/task12/stage3/2026-11-27/gateA_recheck_ws13a8/) and the pytest record at the gate commit bc8bf5d (417 passed,
  1 xfailed, exit 0; runs/task12/stage3/2026-11-27/pytest_gate/). Gate B passes on the W/S 13, A 8 baseline
  (docs/validation/2026-11-27_task12_performance.md: 13 pass, 0 fail, 12 not tested), with the open items and
  waivers listed there carried to preliminary design. After the gate commit the figure gained the stored worst
  points at the R7 horizons (plotting only; no record changed).
- **B-3 (R9).** The negative limit is -1.8 with the 0.1 g margin (Gate A round 1 and round 4 rulings);
  spec section 3 is updated.
- **B-4 (R18, V_C).** The per-design V_C rule of 2026-11-23 (10 % above the fastest cruise sub-step,
  rounded up to 5 kt, at least 110 kt EAS; 115 kt for the frozen design) is confirmed and written into
  spec R18. Envelope protection (level top speed above V_D at sea level) is a preliminary-design
  requirement. One recorded V-n check at V_D and at level top speed is run.
- **B-5 (outside rows).** Take-off power (-10.9 %), CD0 (-18.6 %) and Fig. K.3 (about -5.7 %) are explained
  and carried. Spec 7.1a's take-off power row is replaced by the take-off distance row at installed
  power. The +-10 % SFC band covers K.3 as well as the engine model.
- **B-6 (R13 and the G-5 waivers).** R13 is accepted by layout construction with the G-8 VSPAERO run as
  support. SU2 polars and C_L,max, the gust second source, the blade-element propeller and a
  fuselage-inclusive neutral point are named entry items for preliminary design.
- **B-7 (Stage 1 package).** The Stage 1 compliance table is generated for the frozen design and Gate A
  items A1 to A12 are re-checked before the pass.
- **B-8 (8 h nominal).** The nominal's small robustness (horizon 0.198) is acknowledged as what the
  restated R5 of 2026-11-22 allows; no new target.

### Preliminary design started (2026-11-27, after B-11)

- **PD-start (2026-11-27).** Owner instruction after the Gate B pass (Éder, 2026-11-27): "Continue with the design.
  Make common sense assumptions and document your choices. Only prompt for my input if absolutely necessary."
  Preliminary design of the W/S 13, A 8 baseline starts under the assumptions PD-1 to PD-17 of
  `docs/specs/task12_preliminary_design.md` section 2. They are the agent's assumptions, not owner rulings; they
  stand in for rulings until the owner overrides them, and Gate C (section 4 of that spec, item C13) asks him to
  confirm or change them. In short: no rented compute and no 3D CFD, with 2D SU2 polars queued for Colab without
  blocking (PD-1); matplotlib only (PD-2); the configuration stays frozen and only sizes and details change (PD-3);
  no full study of W/S 13, A 7, which is the named fallback (PD-4); wing section NACA 4415 unless its test rejects
  it, measured open data before computed polars (PD-5, PD-6); one preliminary-design baseline record r0 and one
  closing re-record r1 (PD-7); the ruled gust rule stays (PD-8); structures limited to the wing spar (PD-9); one
  representative blade-element propeller (PD-10); envelope protection as a requirement, not a control law (PD-11);
  payload bay at 30 lb/ft^3 (PD-12); lightest weight for loads is zero-fuel with the payload on (PD-13); numpy,
  scipy and matplotlib only (PD-14); spec 7.1a tolerances carry over (PD-15); R1 to R19 and the standing rulings
  unchanged (PD-16); same branch and model allocation (PD-17). Work packages P0 to P10 and Gate C are in that
  spec. Owner items O-1 to O-3 there each have a default; none blocks the work. Nothing was run for this entry.
- **PD-18 (2026-11-27, package P6: the blade of the representative propeller).** An agent's assumption under PD-10, not an
  owner ruling. The representative propeller is three blades at the record's diameter and 2,030 rpm, constant speed, with:
  the planform and thickness distribution of the Navy propeller 5868-9 of NACA Report 640 (the propeller the strip theory
  was checked on), scaled to an activity factor of 100 per blade (band 90 to 140; Raymer p. 327); every station at a section
  lift coefficient of 0.5 at the loiter point (band 0.4 to 0.6); the flat-bottomed propeller sections of NACA Report 259 as
  section data. The entries and their bands are in `data/task12/pd_p6_blade_ledger.yaml`; the Gate B ledger and r0 are not
  edited. No product is selected. The numbers computed with this blade are in
  `docs/validation/2026-11-27_task12_pd_p6.md`; that report says whether they may be used in r1 (they may not while its
  validation row 5 fails). Override: a maker's propeller map replaces the whole check (O-3).
- **PD-19 (2026-11-27, package P3: nose packaging, and what the loft adds to the layout).** An agent's assumption under the
  owner's instruction of PD-start, not an owner ruling. P1 found (its finding 4, "nose packaging") that the nose-gear leg,
  retracted aft, passes through the payload bay and the avionics station, and that Stage 1 has no stow check for the nose gear.
  Choice, the simplest that passes the box gate of P3 (spec gate 4): the nose wheel stays at r0's station and retracts aft into
  a bay on the centreline (two boxes round the leg, one wheel well); the payload bay of PD-12 becomes two boxes above the
  stowed leg and ahead of the wheel well, in fuselage sections made squarer (conic shape parameter 0.70, Raymer (7.2) and
  p. 133); the avionics box sits above the wheel well behind the payload bay; the sensor turret stays where r0 draws it.
  Rejected: forward retraction (the wheel is 1.14 ft from the nose); a shorter nose leg (the leg length follows from the
  propeller's ground clearance, and a shorter nose leg alone puts the aircraft nose-down on the ground); a longer or fuller
  nose (changes the outer lines for a packaging problem that boxes solve). Cost: the payload and the avionics move aft; the
  masses, stations and moment change are in `docs/validation/2026-11-27_task12_pd_p3.md` section 6, for P4. r0 is not edited:
  the moves are findings for r1 (PD-7), and P4 decides whether the wing must move to keep R13. The same entry records the
  loft's other choices, all in `data/task12/pd_p3_arrangement.yaml` with bands where they are judgements: box clearance to the
  skin 1.0 in (the spec names a ledger clearance that the ledger does not have); front spar at 15 % of the chord; the
  fuselage ends in a circle of 20 % of the propeller diameter; the engine bay is drawn round the TCDS envelope at r0's
  engine station; the layout convention of the conceptual render (wing and tail heights, unswept leading edges) is kept.
  Override: a real payload's dimensions (PD-12) or a different gear arrangement replaces the boxes.
- **PD-20 (2026-11-27, package P4: the tail clear of the propeller disc, solved with the wing position).** An agent's
  assumption under PD-3 (tail area and arm and the wing's fore-and-aft position may change) and the owner's instruction of
  PD-start, not an owner ruling. P3 (its row 9) found the horizontal tail 1.78 ft and the fin 0.87 ft behind the propeller
  plane inside the disc: r0 places each tail by its mean chord at a tail arm of 0.475 of the fuselage length (Raymer
  p. 112-113), and on a pusher whose propeller is at the end of the fuselage the root chords then run past it. P3 also moved
  the payload and avionics aft (PD-19), which takes the empty-fuel static margin below R13. Both are answered together,
  because the tail arm and the centre of gravity depend on each other. Choice: (1) both tails get a straight trailing
  edge, with all the taper on the leading edge; areas, aspect ratios and tapers stay as the ledger has them; (2) the tails
  move forward, as one, by the least distance that puts the rearmost point of either tail inside the disc's radius 1.0 ft
  ahead of the propeller plane (clearance band 0.5 to 2.0 ft, a judgement: the library gives no number); (3) their areas
  grow as the arm shortens, so that both tail volume coefficients of r0 are kept (Raymer (6.28), (6.29), p. 111); (4) the
  wing is placed by Stage 1's own rule, the mean of the full-fuel and empty-fuel static margins at 0.10 MAC, with the
  fuselage-inclusive neutral point of P4 (Multhopp, NACA TM 1036) in place of Raymer's (16.22); (5) the main wheels follow
  by Stage 1's tipback rule and the nose wheel stays. The tail and fuselage weights follow Raymer (15.47) to (15.49),
  p. 404, as ratios on r0's weights. History, kept because it is a finding: the entry was first written without (1), with
  r0's tail planforms. A trial of the methods, before any recorded run, showed that form does not close: with an unswept
  leading edge the root chord runs so far behind the mean chord that the tail must come far forward, the kept volume
  coefficient then enlarges it, and no wing position reaches the middle of R13 while the tail can no longer rotate the
  aircraft. That form is still solved in the record and reported as failed. Rejected: a longer fuselage or a shaft
  extension to carry the propeller aft of the tail (lowers the propeller at rotation, adds a shaft whose weight the
  library does not give, and changes the outer lines more than the tail does); tail booms or a propeller ahead of the
  tail on a pylon (a change of configuration, outside PD-3); a cut-out in the tails inside the disc (the loft and the
  weight and lift-slope methods assume plain tapered surfaces). The numbers (arm, areas, wing station, main-wheel station,
  weights, the margins that result, the form that does not close and the solution at the clearance band ends) are in
  `docs/validation/2026-11-27_task12_pd_p4.md`, generated from `runs/task12/pd/2026-11-27/p4/p4.json`; none is typed
  here. r0 is not edited: these are findings for r1 (PD-7). For r1, Stage 1 needs the tail arm and the tails' leading-edge
  sweep as inputs in place of its fixed fraction of the fuselage length. Known cost, reported there: the tailplane becomes
  larger and sits close behind the wing, and the solution does not hold at the high end of the clearance band. Not
  answered here and listed for P9: the sponson that does not hold the retracted main gear (P3 finding 7), and where the
  tail roots sit on the engine bay (inlet, exhaust and structure are not drawn). Override: any other way of clearing the
  disc replaces (1) to (3); the wing rule (4) then runs again.
- **PD-21 (2026-11-28, package P4b: tail and aft-body layout for r1; supersedes PD-20's items (2) and (3)).** An agent's
  assumption under PD-3 (tail area and arm, fuselage lines and the wing's position may change) and the owner's instruction
  of PD-start, not an owner ruling. PD-20's text above is kept as written; its rejection of a longer fuselage was made
  without numbers, and the lead reviewer asked for the trade. P4b ran it with P4's own code and rules (Stage 1 tail rule,
  mean static margin 0.10, tipback 15 deg, R13 full and empty, nose-wheel load 5 to 20 %, tail lift at rotation within 1.0,
  1.0 ft disc clearance, propeller ground clearance at least 9 in). The selection rule was written in
  `data/task12/pd_p4b_choices.yaml` before any run: (1) every payload-on row passes; (2) if any layout flies payload-off
  without ballast, only those stay; (3) most hours on station on r0's fuel with the layout's wetted areas and its
  empty-weight change in the take-off weight; (4) ties within 0.01 h go to the least empty-weight change; (5) if nothing
  passes, the owner decides. Layouts: A, PD-20 as recorded; B, r0's tail planforms and arm with the aft fuselage lengthened;
  Bs, the same with straight trailing edges; an arm scan of eleven tail arms between PD-20's and r0's with straight
  trailing edges, of which C is the row of least empty-weight change. **Choice: Bs. For r1 the tails keep r0's arm and
  areas, get straight trailing edges (PD-20's item (1), kept), and the aft fuselage is lengthened behind the engine bay by
  the least length that leaves 1.0 ft between the tails and the propeller plane; the engine stays at r0's station and a
  shaft carries the propeller; the wing is placed by PD-20's rule (4) and the main wheels by its rule (5).** Numbers,
  copied from the record `runs/task12/pd/2026-11-28/p4b/p4b.json` (commit 03b75ee, clean tree): extension 1.976 ft, to a
  fuselage of 30.559 ft; tail arm 13.577 ft, tailplane 135.48 ft^2, fin 37.08 ft^2; wing leading edge +0.918 ft from r0's;
  main wheels at 14.895 ft; empty weight +27.15 lb against +26.93 lb for PD-20; hours on station -0.158 h against
  -0.423 h (rule's case; -0.042 h against -0.309 h at r0's weight and fuel); tail lift at rotation 0.928 of the limit
  against 0.986; propeller ground clearance at rotation 12.10 in against 15.88 in; tailplane 0.501 of the wing area with
  its root 3.85 ft behind the wing's trailing edge, against 0.611 and 1.06 ft. Reported, not tuned: B fails the propeller
  ground clearance (8.55 in with an extension of 3.928 ft). By empty weight alone the least change is C (arm 12.354 ft,
  +25.17 lb); the rule ranks by hours, and the scan's empty weight is flat within about 2 lb. What rests on an assumption:
  the shaft weight, 5 lb/ft with a band of 2 to 10 lb/ft, for which no open or library number was found (Raymer p. 221
  gives no weight); the trade was repeated at both band ends and the choice does not change. **Payload off: no layout
  passes without ballast** (all 132 payload-off loadings are aft of the aft limit on every layout, and the centre of
  gravity ends 0.263 ft behind the main wheels on the chosen one). Moving the main wheels does not cure it (the aft limit
  of R13 is what breaks, and wheels placed for payload-off tipback would need 2.434 of the tail-lift limit at rotation).
  The smallest ballast is 474 lb at the payload station (465 lb for PD-20); it is an operating limit for P8 under PD-13.
  The report is `docs/validation/2026-11-28_task12_pd_p4b.md`. r0 is not edited: these are findings for r1 (PD-7). Not
  answered here and listed for P9: the shaft, its bearings and critical speed; the tail cone's structure and the tail
  roots on it; the form factor of the longer body; Stage 1 needs the extension, the tail arm and the tails' sweep as
  inputs. Override: a maker's or measured shaft weight outside the band, a different clearance, or an arm longer than
  r0's (not studied; hours were still rising at the scan's end) re-opens the trade with the same code.
- **PD-22 (2026-11-28, owner ruling: packages P5, P7 and P8 run on Opus 5.5 while the Fable model's usage limit is spent).**
  An owner ruling (Éder, 2026-11-28), not an agent's assumption. The Fable 5.1 model's usage limit is spent until
  2026-11-30 17:00 UTC. The owner ruled that packages P5 (loads), P7 (wing spar) and P8 (envelope protection) run now on
  Opus 5.5 in place of the allocation of `docs/specs/task12_preliminary_design.md` section 3 and `CLAUDE.md` (Fable 5.1 for
  physics, tolerances, acceptance tests, verdicts and review of any diff that can change a number). The same rules apply
  unchanged: the spec's acceptance rows and tolerances, tests written first, every number from a recorded run, failed
  checks reported and not tuned. Every report from these packages is marked "not yet Fable-reviewed" near its top, and
  Fable reviews their diffs after the limit resets and before P9's closing re-record r1. Nothing was run for this entry.
  Override: a finding of that review re-opens the package concerned with the same code and records.
- **PD-23 (2026-11-28, package P7: how the wing spar is idealised and sized).** An agent's assumption under PD-9 and the
  owner's instruction of PD-start, not an owner ruling; run on Opus 5.5 under PD-22, not yet Fable-reviewed. Choice, all
  in `data/task12/pd_p7_choices.yaml`, written before any code or run: (1) one bending spar at the P3 arrangement's front
  spar station (0.15 of the chord, band 0.12 to 0.25), its depth the loft's NACA 4415 depth there less two skins of
  0.06 in (band 0.04 to 0.10 in); caps of 0 deg high-strength graphite/epoxy, each 0.10 of the local chord wide (band
  0.06 to 0.15), carry all the bending; a +-45 deg web carries all the shear and does not buckle at ultimate load
  (Raymer (14.37) with K 5.5, simply supported long panel, Fig. 14.42); the rear spar, ribs, skins and joints are not
  sized and no minimum gauge is applied; (2) typical values of Raymer Table 14.4 times one knock-down factor of 0.50
  on the strengths (band 0.35 to 0.65), a judgement for which no open source was opened; (3) every station is sized to
  the envelope of the ruled load cases at ultimate load, so the governing case has a margin of zero by construction and
  P7's row 3 asks whether a sizing exists and what margin the other cases keep; the P5 row 4 cases are applied to that
  spar as a sensitivity; (4) every case is balanced in pitch with P4's tail trim equation, gusts included; (5) inertia
  relief from the wing weight by chord, the fuel in P4's tanks, and the sponsons and main gear at the main wheels;
  nothing else. Rejected: a two-spar box sharing the bending (the share needs a stiffness model PD-9 leaves out); sizing
  to Stage 1's design point alone (the spec asks for every ruled case). r0 is not edited. The numbers are in
  `docs/validation/2026-11-28_task12_pd_p7.md`, generated from `runs/task12/pd/2026-11-28/p7/p7.json`; none is typed
  here. Override: a laminate design with its own allowables, a two-spar box, or a different knock-down replaces (1) to
  (3) with the same code.

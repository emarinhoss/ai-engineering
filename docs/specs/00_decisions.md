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

**Two design variables: theta1 in [5, 12] deg, theta2 in [5, 14] deg.** Total turning 10 to 26
deg; all shocks attached with margin (theta_max at M = 3 is 34 deg). Over the box (inviscid):
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
- Convective scheme `ROE` with `ENTROPY_FIX_COEFF= 0.1`, `MUSCL_FLOW= YES`, limiter
  `VENKATAKRISHNAN_WANG`, `VENKAT_LIMITER_COEFF= 0.05`; viscous terms second-order central;
  gradients `WEIGHTED_LEAST_SQUARES`. Task 0 proposed `AUSMPLUSUP2`; on 2026-11-01 four
  800-iteration Euler-wedge variants (SU2 v8.2.0, medium wedge mesh, this repository's
  config) gave: AUSMPLUSUP2 at fixed CFL 5 diverged (Error Exit at iteration 50);
  AUSMPLUSUP2 with adaptive CFL capped at 20 stalled at log10 rms density -2.5;
  AUSMPLUSUP2 with the plain Venkatakrishnan limiter stalled at -2.4; ROE with entropy fix
  0.1 and the same CFL settings fell from -3.45 to -12.05 in 603 iterations. ROE is therefore
  the default. Risk to watch: Roe's carbuncle on the cylinder (V3); fallback there is `HLLC`.
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
  MASSFLUX`. Output: `SURFACE_CSV` always, volume `CSV` for validation cases only.
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
- Budget estimate: medium mesh, 2 cores, about 5 min per run gives 12 per hour; pool of 96 plus
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

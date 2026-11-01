# Task 2 spec: inlet geometry, cylinder, metrics, validation suite (Days 3-4)

Implements: Sonnet 5.5 (geometry, metrics, validation checks, tests). Haiku 5.5 (validation
figures and the markdown report generator, after the numbers exist). Fable 5.1 reviews the
metric definitions, the mesh gate thresholds, the heat flux sign handling and every validation
verdict. Runs on Colab: Éder (via the Task 1 notebook extended with a case list).
Depends on: `00_decisions.md` sections 2, 3, 4, 5, 6; `01_interfaces.md`; Task 1 code.

## Deliverables

1. `geometry/inlet.py: build(params) -> (geometry, Mesh)` for family `inlet2r`, exactly the
   geometry of `00_decisions.md` section 2 (points O, C, P, E_body, E_cowl, G; lip from the
   inviscid shock intersection using `physics.shock.oblique`). Block layout:
   - Lower row (body to the lip line y = y_P for x <= x_P): L0 [x_in, 0] x [0, y_P];
     L1 [0, X1] x [ramp 1, y_P]; L2 [X1, x_P] x [ramp 2, y_P]; L3 duct: left edge the vertical
     line x = x_P from the body to P, top edge the cowl inner surface P to E_cowl, right edge
     the throat plane E_cowl to E_body, bottom edge the body.
   - Upper row (lip line to y_top): U0, U1, U2 above L0, L1, L2; U3 external: bottom edge the
     cowl outer surface P to G, right edge vertical from G to (x_G, y_top), top edge y_top,
     left edge the vertical line above P.
   - Shared edges by identity; wall-normal distributions: body-clustered one-sided in L0-L2
     left edges, two-sided (body and cowl) on x = x_P and on the throat plane; U-row clustered
     toward the lip line (cowl outer wall in U3). Streamwise: capped geometric from the
     leading edge, clustered at the corner and at the lip, maximum 1.0 mm (medium).
   - Writes `geometry.json` with the keys in `01_interfaces.md`.
2. `geometry/cylinder.py: build(params)`: polar block, phi in [0, 100 deg], r from R to
   r_out(phi) = R (2.0 + 1.5 sin^2 phi), wall-clustered one-sided in r; markers wall,
   symmetry (phi = 0 line extended to the outer boundary, i.e. the row of nodes at phi = 0),
   farfield (outer arc), outlet (phi = 100 deg line). Levels as in `00_decisions.md` 6.
3. `physics/heating.py`: `eckert_flat_plate` and `fay_riddell_cylinder` with formulas from
   `00_decisions.md` 4; `physics/gates.py: check(params)`.
4. `postprocess/surface.py`: load `surface_flow.csv`, split by marker using
   `mesh_markers.json` node ids, order nodes along each marker by walking the boundary lines,
   compute u, v from momentum and density, M from p, rho, u, v (cross-checked with SU2's Mach
   column within 1e-3 where present), heat flux into the wall with the sign check of
   `00_decisions.md` 3.2.
5. `postprocess/metrics.py: compute(case_dir) -> dict` implementing 3.1 and 3.2 exactly,
   including the SU2 `AVG_TOTALPRESS` cross-check (gate X1, 0.5 percent) read from the history.
6. `postprocess/validation.py`: `eckert_check` (V2b), `fay_riddell_check` (V3, including the
   CFD-extracted velocity gradient variant: fit u_e along the wall-normal edge of the boundary
   layer over the first 5 degrees from the stagnation point and report the gradient and the
   Billig stand-off from the pressure jump on the stagnation line), `inlet_check` (V4e, V4v:
   area averages over the whole throat and over its middle 50 percent), `grid_study(case_dirs)`
   (table of metric versus level, relative change, Richardson estimate with observed order
   when three levels are available).
7. `postprocess/report.py` (Haiku): writes `docs/validation/<date>_report.md` with the
   tolerance table of `00_decisions.md` section 5 filled from `runs/`, pass/fail per row, and
   the figures: wedge p and q profiles with analytic lines, cylinder q(phi) with the
   Fay-Riddell point, inlet Mach contours (from the volume CSV) and the throat p0 profile,
   grid-study plots. Every figure caption names the `case_id`s.
8. Extend the Task 1 notebook with a cell that runs a list of case directories sequentially and
   writes records; Task 2's case list: wedge laminar (V2b, reuse Task 1 run if converged),
   cylinder coarse/medium/fine (V3), inlet 8/8 Euler medium (V4e), inlet 8/8 laminar
   coarse/medium/fine (V4v, V4m). Nine runs.

## Acceptance tests

Unit tests without SU2:
- `test_inlet_geometry.py`: for 8/8, `geometry.json` has x_P 0.2023, y_P 0.0755, h 0.0309,
  M2 2.962, recovery_2shock 0.9316 (1e-3 relative); the lip lies on both shock lines within
  1e-9; the throat plane is normal to ramp 2 within 1e-9; over a 7 x 7 grid of the design box
  every mesh passes the quality gate and `physics.gates.check` returns []; same params twice
  give byte-identical `mesh.su2`; cells at medium level between 15 k and 40 k and reported.
- `test_gates.py`: theta1 = 12, theta2 = 14.5 rejected by the schema bound; theta2 = 30 at
  M = 3.2 rejected by gate 1 with the message naming theta_max; a hand-built params set with
  x_P - X1 < 0.02 rejected by gate 2.
- `test_cylinder.py`: node counts per level, first cell within 10 percent of 4 micrometres
  (medium), min angle >= 40 deg, markers present, byte-identical on repeat.
- `test_heating.py`: `fay_riddell_cylinder(4.0, 226.509, 1197.03, 300.0, 0.010)` gives
  q = 2.443e5 W/m^2 within 0.5 percent, du/dx 7.213e4 within 0.5 percent, p02 25219 Pa within
  0.1 percent; `eckert_flat_plate` at the V2b edge conditions gives 26.61 kW/m^2 at x = 0.05 and
  19.84 kW/m^2 at x = 0.09 within 0.5 percent; q scales as x^-1/2.
- `test_metrics.py`: a synthetic throat profile (uniform core p, M plus a parabolic boundary
  layer deficit on both walls, exact node coordinates on an inclined segment) returns the
  mass-averaged p0 computed independently in the test to 1e-6, `recovery_total` consistent with
  per-node `normal()`; a uniform profile returns `recovery_total_bulk == recovery_total` to 1e-9;
  a synthetic body heat flux with a known maximum on ramp 2 and a larger value on ramp 1
  returns the ramp-2 maximum and its x; a profile with negative integral raises.
- `test_surface_split.py`: a small hand-made mesh plus a surface CSV with shuffled rows is
  split and ordered correctly along each marker.
- `test_history.py`: synthetic histories produce each convergence status in
  `00_decisions.md` 6 (converged, stationary, not_converged, diverged).

Colab acceptance (Fable judges from `runs/task2/` and the report):
- V2b hard, V3 hard (both tolerances), V4e hard, V4m hard pass. V2a, V3 stand-off, V4v
  reported with explanation. A hard failure stops the schedule: Fable investigates (mesh,
  scheme fallback list, BCs) and the fix is recorded; nothing is tuned to the answer.
- Production mesh level chosen and written in the report with the medium-to-fine deltas.
- Timing of the laminar inlet medium run re-evaluates gate T1 (overrides the wedge estimate).

## Not in this task

Queue, MCP, batch runs (Task 3). Surrogate (Task 4).

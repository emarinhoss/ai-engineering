# Turbulence-model sensitivity (Spalart-Allmaras), 2026-11-01: backup material, not a validated RANS study

Question it answers: what would change if the boundary layer were turbulent instead of laminar?
Same meshes, freestream, wall temperature and numerics as the laminar production runs, with
`SOLVER= RANS`, `KIND_TURB_MODEL= SA`, freestream turbulence intensity 0.01, scalar upwind for
the turbulence equation (see each case.cfg; SU2 v8.2.0 serial on the Fable cloud container).
SA without a transition model is turbulent from the leading edge. Metrics from
postprocess.metrics.compute (metrics.json in each directory). Laminar comparison values from
runs/dev/2026-11-01_inlet_grid_study_ef03 and runs/dev/2026-11-01_inlet_box_diagnostics.

| Case | Model | Cells | Iterations | recovery_total | recovery_throat | q_peak [kW/m^2] (x) | wall y+ median / max |
|---|---|---|---|---|---|---|---|
| 8/8 medium | laminar | 30 600 | 1230 | 0.3163 | 0.9085 | 29.73 (0.1151) | - |
| 8/8 medium | SA | 30 600 | 412 | 0.3112 | 0.8565 | 76.98 (0.1121) | 2.3 / 3.0 |
| 8/8 fine | SA | 55 640 | 552 | 0.3109 | 0.8592 | 76.29 (0.1126) | 1.7 / 2.6 |
| 12/12 medium | laminar | 25 000-class | 2063 | 0.4065 | - | 46.9 (0.1113) | - |
| 12/12 medium | SA | same mesh | 487 | 0.3925 | 0.7441 | 118.20 (0.1103) | 3.1 / 3.6 |

Reading:
- Turbulent peak heating on ramp 2 is 2.5 to 2.6 times the laminar value at both design points;
  the trade-off keeps its direction (more turning: more recovery, more heating).
- The turbulent boundary layer is much thicker: throat recovery drops from 0.909 to 0.857 at 8/8
  and the penalty grows with turning (0.744 at 12/12); after the terminal shock the difference
  shrinks (0.311 vs 0.316 and 0.393 vs 0.407) because the lower throat Mach weakens the shock.
- No corner separation in the SA cases (the turbulent layer resists the adverse gradient).
- Mesh sensitivity of the SA heating is small (medium to fine: -0.9 percent in q_peak, -0.1
  percent in recovery_total), with y+ median 2.3 on medium and 1.7 on fine. SA is normally run
  at y+ about 1; these numbers are a sensitivity bound, not a validated turbulent heating
  prediction, and they are labelled that way in the talk.
- The laminar assumption rests on Re_L <= 5e5 at this sub-scale, high-altitude condition
  (docs/specs/00_decisions.md section 1.1); the turbulent numbers show what a full-scale,
  lower-altitude version of the same inlet would have to face.

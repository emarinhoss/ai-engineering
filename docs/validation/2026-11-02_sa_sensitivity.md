# Spalart-Allmaras sensitivity on Colab (2026-11-02): a bound on the turbulence assumption

Written by Fable 5.1 from the three records in `runs/sensitivity/` (tag `sensitivity`, solver
`RANS_SA`, SU2 v8.2.0 on Colab, 4 MPI ranks, config hash `2f21e77de356...`), the laminar Colab
records in `runs/val/` (V4m grid study, 8/8), the laminar development record
`runs/dev/2026-11-01_inlet_box_diagnostics/12_12_medium/` and the development SA records in
`runs/dev/2026-11-01_turbulence_sensitivity_SA/`. Every number below is in one of those files
(`result.json` or `metrics.json`). Nothing was tuned.

## What was run

The `RANS_SA` option (commit dbb23c0) is the laminar configuration with `SOLVER= RANS`,
`KIND_TURB_MODEL= SA`, freestream turbulence intensity 0.01, scalar upwind for the turbulence
equation, implicit Euler for it, turbulence CFL reduction 0.5, and no transition model, so the
boundary layer is turbulent from the leading edge. Same meshes, freestream, wall temperature and
numerics as the laminar production runs. Three cases, the same points as the development runs:

| case | design | mesh | cells | iterations | wall time [s] | status |
|---|---|---|---|---|---|---|
| inlet2r-1731bdea74 | 8/8 | medium | 30 600 | 412 | 125 | converged |
| inlet2r-8a09596911 | 8/8 | fine | 55 640 | 552 | 310 | converged |
| inlet2r-d7e3815b57 | 12/12 | medium | 26 000 | 487 | 126 | converged |

## Results against the laminar records

| design, mesh | model | record | recovery_total | recovery_throat | q_peak [kW/m2] | heat load [W/m] |
|---|---|---|---|---|---|---|
| 8/8 medium | laminar | runs/val/inlet2r-d4d29884be | 0.3163 | 0.9085 | 29.73 | 3604 |
| 8/8 medium | SA | runs/sensitivity/inlet2r-1731bdea74 | 0.3112 | 0.8565 | 76.98 | 10 784 |
| 8/8 fine | laminar | runs/val/inlet2r-5e844a838c | 0.3166 | 0.9105 | 29.23 | 3463 |
| 8/8 fine | SA | runs/sensitivity/inlet2r-8a09596911 | 0.3109 | 0.8592 | 76.29 | 10 588 |
| 12/12 medium | laminar | runs/dev/.../12_12_medium (container) | 0.4065 | 0.8222 | 46.86 | 3919 |
| 12/12 medium | SA | runs/sensitivity/inlet2r-d7e3815b57 | 0.3925 | 0.7441 | 118.20 | 12 761 |

Ratios SA to laminar: peak heat flux 2.59 (8/8 medium), 2.61 (8/8 fine), 2.52 (12/12 medium);
integrated heat load on ramp 2 about 3.0 to 3.3; `recovery_total` down by 0.0051, 0.0057 and 0.0140;
`recovery_throat` down by 0.052, 0.051 and 0.078. The terminal normal shock hides most of the throat
loss in `recovery_total`, because the turbulent boundary layer also lowers the throat Mach number
(2.837 against 2.903 at 8/8 medium) and makes the terminal shock weaker.

Mesh dependence of the SA result: medium to fine at 8/8, recovery_total minus 0.07 percent, q_peak
minus 0.89 percent, both smaller than the laminar medium-to-fine changes of the grid study (+0.09 and
minus 1.68 percent). The first wall cell is the one sized for the laminar layer (20 micrometres,
14 micrometres on the fine mesh); the development runs on the container measured wall y+ of 2.3
(medium) and 1.7 (fine), above 1, so the SA layer is under-resolved for a model that does not use
wall functions.

## Reproducibility across machines

The three Colab records reproduce the development SA records made on the container (serial SU2
v8.2.0, hand-edited configs) to every printed digit: recovery_total 0.31115 / 0.31094 / 0.39245,
q_peak 76 976.57 / 76 294.26 / 118 195.7 W/m2 in both. The 4-rank Colab laminar record of 8/8
medium likewise equals the container record (0.31634, 29 725.42 W/m2). The solver is deterministic
across the two machines and the two rank counts at the printed precision.

## What this does and does not say

- It bounds the effect of the turbulence assumption: if the boundary layer were fully turbulent
  from the leading edge, peak heating on ramp 2 would be about 2.5 to 2.6 times the laminar value
  and recovery about 0.005 to 0.014 lower. The trade-off keeps its direction; the heating level does
  not.
- It is not a validated turbulent prediction: no transition model, y+ above 1, no turbulent
  validation case. The talk labels it a sensitivity bound (B1, S22) and keeps the laminar result as
  the model for the sub-scale, 30 km condition (`docs/specs/00_decisions.md`, section 1.1).
- A turbulent Pareto front was not computed. Running the 92-point pool with `RANS_SA` would cost
  about a quarter of the laminar pool in wall time (the SA runs converge in 400 to 550 iterations)
  and is listed as next work, not claimed.

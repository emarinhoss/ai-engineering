# Design-box diagnostics (2026-11-01): where does the laminar inlet solution stop converging?

Medium mesh, final numerics (Roe, entropy fix 0.3, CFL max 20 unless stated), SU2 v8.2.0 serial,
Fable cloud container. metrics.json from postprocess.metrics.compute for the converged cases.

| Case | Total turning | Iterations | Outcome | recovery_total | q_peak [kW/m^2] (x) |
|---|---|---|---|---|---|
| 12_14 (grid study, entropy fix 0.1 and 0.3, medium and fine) | 26 deg | 2300 to 4350 | diverged | - | - |
| 12_14_medium_cfl5 | 26 deg | > 5700 | residual fell to -7.4 then grew to +1.7: diverging | - | - |
| 12_12_medium | 24 deg | 2063 | converged (-10) | 0.4065 | 46.9 (0.1113) |
| 8_14_medium | 22 deg | 2160 | converged (-10) | 0.3876 | 47.9 (0.1136) |
| 5_14_medium | 19 deg | 1952 | converged (-10) | 0.3481 | 43.1 (0.1151) |

Reading: theta2 = 14 deg alone is fine (5/14 and 8/14 converge); the failure is the 26 deg
total-turning corner, where the residual reaches -7.5 and then grows regardless of the time step,
the pattern of a separation that does not settle to a steady state. Decision: physics gate 4 becomes
theta1 + theta2 <= 24 deg (commit after this record); 4 of the 96 Sobol pool points (indices 0, 40,
72, 80) are excluded by it. The 25 deg band between 24 and 26 was not tested; if pool points near
24 deg fail, they are recorded as failures, not re-tuned. These three converged points also show
the trade-off the study is about: recovery 0.32 -> 0.41 and peak heating 30 -> 48 kW/m^2 from 8/8 to
12/12.

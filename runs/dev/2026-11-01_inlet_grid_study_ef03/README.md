# Inlet grid study at the final numerics (entropy fix 0.3, CFL max 20), 2026-11-01

Fable cloud container, SU2 v8.2.0 serial, one core per run (the three 8/8 levels and the two 12/14
levels ran concurrently, so wall times are inflated). metrics.json per converged case from
postprocess.metrics.compute (commit 2efdabe).

| Case | Cells | Iterations | log10 rms(rho) end | recovery_total | recovery_throat | q_peak [kW/m^2] | x_q_peak [m] | capture |
|---|---|---|---|---|---|---|---|---|
| 8_8_coarse | 19 620 | 1064 | -10.00 | 0.3163 | 0.9068 | 30.18 | 0.1147 | 0.9829 |
| 8_8_medium | 30 600 | 1230 | -10.00 | 0.3163 | 0.9085 | 29.73 | 0.1151 | 0.9832 |
| 8_8_fine | 55 640 | 1572 | -10.00 | 0.3166 | 0.9105 | 29.23 | 0.1147 | 0.9834 |
| 12_14_medium | 25 000 | 4347 | diverged (Error Exit, +15.5) | - | - | - | - | - |
| 12_14_fine | 45 240 | 3577 | diverged (Error Exit, +13.6) | - | - | - | - | - |

V4m at 8/8: medium-to-fine change +0.09 percent in recovery_total (tolerance 2) and -1.68 percent in
q_peak (tolerance 5): PASS. The medium mesh is production. Relative to entropy fix 0.1 the
fine-mesh peak heating is 4 percent higher (29.23 vs 28.11 kW/m^2) and the recovery unchanged
(0.3166 vs 0.3169); the entropy fix is part of the model and is stated with the numbers.

12/14: the residual falls to -7.5 by iteration 1200, then grows and the run diverges, on both
meshes and with both entropy fixes. The 14 deg laminar compression corner at this Reynolds number
produces a separation that does not settle to a steady state in this solver setting. The
diagnostics (12/14 at CFL max 5, 12/12) are in ../2026-11-01_inlet_box_diagnostics when done; the
design-box decision (trim theta2, or keep such points as recorded failures) follows from them.

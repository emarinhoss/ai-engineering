# Inlet grid study at entropy fix 0.1 (2026-11-01), before the switch to 0.3

8/8 coarse (19 620 cells, 1361 iterations, 217 s), medium (30 600 cells, see
../2026-11-01_inlet_design_point), fine (55 640 cells, 1842 iterations, 931 s), all converged to -10.
postprocess.metrics.compute (commit 2efdabe):

| Level | recovery_total | recovery_throat | q_peak [kW/m^2] | x_q_peak [m] | capture |
|---|---|---|---|---|---|
| coarse | 0.3165 | 0.9101 | 28.95 | 0.1175 | 0.9838 |
| medium | 0.3166 | 0.9114 | 28.61 | 0.1171 | 0.9842 |
| fine | 0.3169 | 0.9129 | 28.11 | 0.1176 | 0.9844 |

Medium-to-fine: recovery_total +0.09 percent (tolerance 2), q_peak -1.75 percent (tolerance 5): V4m
PASSES at 8/8 for entropy fix 0.1. The sequences are monotone but the observed order is not
defined by the Richardson estimate at ratio 1.4 (changes too small relative to noise).

12/14 medium and fine DIVERGED at entropy fix 0.1 (Error Exit at 3284 and 2295 iterations, residual
to +13): the most demanding corner of the box needs the larger entropy fix, consistent with the
cylinder. Re-run at entropy fix 0.3 in ../2026-11-01_inlet_grid_study_ef03 (pending).

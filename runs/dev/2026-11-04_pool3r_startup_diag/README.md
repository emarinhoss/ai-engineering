# NS pool failures: start-up diagnosis of all seven (2026-11-04)

Seven of the 159 laminar NS runs of the Task 9 pool ended with a solver error (`runs/pool3r/ns/<case>`,
`history_summary.status = error`, SU2 "has diverged"). One of them, `inlet3r-fe9cd9771d`, was
diagnosed on 2026-11-03 from field snapshots (`runs/dev/2026-11-03_pool3r_fail_diag/README.md`):
during the start-up transient, flow enters the domain through the cowl side of the duct outlet, where
the imposed back pressure meets the uniform freestream initial state, and the run diverges. This folder
asks whether the other six are the same failure, and tests it by giving every failed case a start that
avoids that transient. Script: `python -m analysis.diag_pool3r_startup` (SU2 v8.2.0 release binary on
the container, 4 cores, 3 runs at a time). Each run is the recorded pool params plus the config edits
in its `edits.json`. Nothing here changes a pool record.

## 1. What the pool records show

145 of the 159 NS records have an iteration history in the repo (the 144 container runs and the
container rerun of `inlet3r-f52ab49df3`; the 15 Colab records hold summaries only). For each, the
lowest density residual (log10 rms[Rho]) within the first 300 iterations, the iteration where it
occurs, and the later rise above that minimum:

| case | Mach | alt [km] | T_wall [K] | turning [deg] | rho_inf [kg/m3] | p_b/p_inf | rms min (iteration) | rise [orders] | pool exit iteration |
|---|---|---|---|---|---|---|---|---|---|
| inlet3r-3128f74faf | 3.61 | 34.6 | 483 | 21.5 | 0.0090 | 5.31 | -3.75 (89) | 8.3 | 1832 |
| inlet3r-655a005283 | 4.06 | 33.7 | 310 | 18.9 | 0.0103 | 5.18 | -3.86 (110) | 3.5 | 4047 |
| inlet3r-7b08048305 | 3.98 | 30.0 | 481 | 25.7 | 0.0185 | 8.08 | -3.26 (8) | 4.5 | 2357 |
| inlet3r-86f013e6e9 | 3.60 | 33.9 | 365 | 20.6 | 0.0100 | 4.96 | -3.92 (95) | 10.0 | 1508 |
| inlet3r-8a4e02ae3d | 3.76 | 33.9 | 330 | 22.0 | 0.0101 | 5.75 | -3.69 (97) | 5.4 | 2091 |
| inlet3r-8f8909eb13 | 3.75 | 34.0 | 570 | 23.3 | 0.0100 | 6.29 | -3.64 (98) | 5.6 | 1577 |
| inlet3r-fe9cd9771d | 3.59 | 29.1 | 453 | 10.7 | 0.0212 | 2.45 | -4.38 (182) | 8.1 | 1773 |
| inlet3r-37b4fb20ae (control, converged) | 3.99 | 34.5 | 304 | 20.4 | 0.0092 | 5.65 | -3.76 (84) | 2.7 | 1712 |
| inlet3r-afd4cb98b2 (control, converged) | 3.52 | 30.0 | 419 | 14.3 | 0.0184 | 3.14 | -6.34 (300) | -0.0 | 1225 |

- All seven failures share one signature: the residual stops falling at -3.3 to -4.4 before
  iteration 200 and then rises by 3.5 to 10 orders. The 138 converged histories are still falling at
  iteration 300 (median -5.95 there); 134 never rise, and 4 rise by 2.7 to 4.0 orders and recover
  (`37b4fb20ae`, `3c8ab0ac2b`, `6292591c04`, `bc25e48dc0`). So the failures are start-up failures,
  decided in the first few hundred iterations, and the four recovering runs are the same event
  survived.
- Where they sit: 5 of the 7 are in the thinnest air of the pool (rho_inf at or below 0.0103 kg/m3,
  the lowest 19 percent of the 145) and 5 of the 7 are below Mach 3.8. Of the 28 runs with
  rho_inf < 0.0105, 5 failed; of the 45 below Mach 3.8, 5 failed; of the 8 with both, 4 failed; of the
  80 with neither, 1 failed. The imposed back-pressure ratio p_b/p_inf (2.45 to 8.08 among the
  failures; 2.45 to 9.68 over the pool, median 5.32), the total turning and the Euler throat Mach
  number do not separate failures from converged runs.
- `RAMP_OUTLET_PRESSURE` does nothing for `MARKER_OUTLET` in SU2 v8.2.0: `ramp_probe/ramp` (pool
  config of `inlet3r-fe9cd9771d` plus `RAMP_OUTLET_PRESSURE= YES`, coefficients 1373 Pa, 10, 1000)
  and `ramp_probe/plain` (the pool config) give byte-for-byte identical 300-iteration histories, and
  that history equals the pool record's first 300 iterations, so the failures are deterministic.

## 2. The test: two-stage starts

Stage 1 replaces the start-up transient; stage 2 is the pool config itself, restarted from stage 1
(`RESTART_SOL= YES`, nothing else changed). A converged stage 2 is therefore the pool's own fixed
point, reached by another path.

- `pramp`: stage 1 with the duct back pressure set to the freestream pressure, the value consistent
  with the uniform initial state, for 500 iterations; then stage 2.
- `cfl2`: stage 1 with the adaptive CFL capped at 2 instead of 20, for 1000 iterations; then stage 2.

Two converged pool cases ran as controls: `inlet3r-37b4fb20ae` (the pool run that rose 2.7 orders
and recovered) and `inlet3r-afd4cb98b2` (a clean pool run). Their stage-2 metrics must match their
pool records.

| case | pool | pramp stage 1 (end rms) | pramp stage 2 (iterations, end rms) | pramp recovery, q_peak [W/m2] | cfl2 stage 1 (end rms) | cfl2 stage 2 (iterations, end rms) | cfl2 recovery, q_peak [W/m2] |
|---|---|---|---|---|---|---|---|
| inlet3r-3128f74faf | error at 1832 | -6.34 | 1945, -10.00 | 0.48813, 10143 | -5.42 | 2312, -10.00 | 0.48813, 10143 |
| inlet3r-655a005283 | error at 4047 | -6.78 | 1174, -10.00 | 0.34674, 22069 | -5.29 | 1543, -10.00 | 0.34674, 22069 |
| inlet3r-7b08048305 | error at 2357 | -5.92 | 2440, -10.00 | 0.45341, 28739 | -0.93 (rising) | error at 2731 | - |
| inlet3r-86f013e6e9 | error at 1508 | -6.64 | 1575, -10.00 | 0.47064, 13289 | -5.25 | 1940, -10.00 | 0.47064, 13289 |
| inlet3r-8a4e02ae3d | error at 2091 | -6.66 | 1257, -10.00 | 0.44939, 18130 | +7.49 (diverging) | error at 570 | - |
| inlet3r-8f8909eb13 | error at 1577 | -6.25 | 2540, -10.00 | 0.47591, 10012 | +0.20 (rising) | error at 1007 | - |
| inlet3r-fe9cd9771d | error at 1773 | -7.02 | 886, -10.00 | 0.33427, 8233 | -4.39 | 1246, -10.00 | 0.33427, 8233 |
| inlet3r-37b4fb20ae (control) | converged, 0.381652, 22350.58 | -6.72 | 1136, -10.00 | 0.381652, 22350.59 | -5.04 | 1508, -10.00 | 0.381652, 22350.58 |
| inlet3r-afd4cb98b2 (control) | converged, 0.402052, 9958.399 | -6.75 | 768, -10.00 | 0.402052, 9958.399 | -5.46 | 1131, -10.00 | 0.402052, 9958.400 |

Stage-2 numbers are from each case's `result_partial.json` (the pool's own post-processing) and
`history.csv.gz`; stage-1 residuals from `history_stage1.csv.gz`. Every stage 2 that finished reached
the residual target -10.00 with drifts over the last window below 5e-4 percent in recovery and below
5e-5 percent in q_peak; the recorded status reads `stationary` rather than `converged` only because
the drop is measured from the restart (about 4 to 5 orders instead of the 5 the rule asks for).

Findings:

1. **All seven failures converge when the back-pressure transient is removed** (`pramp`, 7 of 7),
   to the pool's residual target, in 886 to 2540 stage-2 iterations. Under the pool's own start
   they diverged between iterations 1508 and 4047.
2. **A smaller CFL is not enough**: `cfl2` converges 4 of 7; `7b08048305`, `8a4e02ae3d` and
   `8f8909eb13` already diverge in stage 1 at CFL 2. These three are the three failures with the
   highest p_b/p_inf (8.08, 5.75, 6.29). With seven cases that is an observation, not a rate.
3. **The two paths reach the same answer.** Where both converge, `pramp` and `cfl2` agree to 1e-8
   in recovery and to the last printed digit in q_peak (same for both controls), so stage 2 is a
   fixed point of the pool problem and not an artefact of the start.
4. **The controls reproduce their pool records**: recovery to 7 significant figures, q_peak within
   0.01 W/m2 (the last printed digit) for both.
5. **The recovered values are ordinary points of the response.** Against the GP fitted on the 152
   converged pool runs (the model of `analysis/inverse3r.py`), the seven gentle-start values lie
   within 0.0015 in recovery and within 1.1 percent in q_peak of the prediction, at most 2.8
   predictive standard deviations away (recovery: z = -2.75, +1.07, -0.04, +1.06, +0.48, -0.45, -2.72;
   log q_peak: z = +0.77, -0.77, +0.38, -0.37, -0.35, -0.11, -0.75, in the order of the table above).
   Nothing in these seven points marks an operating limit of the inlet.

## 3. Conclusion and decision

The seven NS pool failures are one numerical start-up failure: the duct back pressure imposed on the
uniform freestream initial state drives flow back into the domain at the cowl side of the outlet
(2026-11-03 snapshots), and in thin air at the low-Mach end of the envelope the solver does not
survive the transient. Started from a state consistent with the boundary condition, every one of them
converges to the same fixed point the pool solves for. The failures say where this solver set-up and
its start break, not where the inlet stops working, which is what the report and the feasibility
analysis (spec question 3) already assumed from the one diagnosed case.

Decision (2026-11-04, Fable, to be confirmed by Éder): the pool records stay as they are, failed. The
seven gentle-start values are reported here and in the Task 9 report but are not added to
`runs/pool3r/pool3r_table.csv` or to any analysis, because they were produced with a different start
than the other 152 runs and after the analyses were done. A future pool would use the `pramp`
two-stage start from the beginning (spec addendum 4).

## Files

- `pramp/<case>/`, `cfl2/<case>/`: `params.json` (the pool's), `stage1.cfg`, `case.cfg` (stage 2),
  `edits.json`, `history_stage1.csv.gz`, `log_stage1.txt.gz`, `history.csv.gz`, `log.txt.gz`,
  `result_partial.json` (stage 2, pool post-processing; absent metrics where stage 2 failed),
  `surface_flow.dat.gz` (stage 2 surface output; also written by SU2 for two of the three `cfl2`
  failures before they diverged), mesh checks, `solver_version.txt`. Meshes and restart files were
  deleted after the run; `make` rebuilds the mesh from `params.json`.
- `ramp_probe/ramp`, `ramp_probe/plain`: the 300-iteration `RAMP_OUTLET_PRESSURE` check (configs,
  histories, logs, params).

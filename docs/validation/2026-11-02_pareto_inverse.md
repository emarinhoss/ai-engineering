# Task 5 on the complete pool: Pareto front with uncertainty, inverse query, design maps (2026-11-02)

Written by Fable 5.1 from the files in `runs/analysis/2026-11-02/`, produced on the 92 converged pool
records in `runs/pool/results.csv` (commit e8a43b7) by

```
python -m analysis.pareto     --results runs/pool/results.csv --out runs/analysis/2026-11-02/
python -m analysis.inverse    --results runs/pool/results.csv --out runs/analysis/2026-11-02/inverse_q40 --q-cap-quantile 0.4
python -m analysis.design_map --grid runs/analysis/2026-11-02/grid.csv --results runs/pool/results.csv --out runs/analysis/2026-11-02/design_map.png
python -m analysis.plot_pareto runs/analysis/2026-11-02/pareto.csv --out runs/analysis/2026-11-02/pareto_front.png --disc-rec-pct 0.09 --disc-q-pct 1.68 --inverse runs/analysis/2026-11-02/inverse_q40/result.json
```

(logs beside the outputs). Every number below is read from `pareto.csv`, `grid.csv`, `hypers.json`,
`notes.json`, `inverse_q40/result.json` or a record in `runs/pool/`. The surrogate is the same GP as in
the replay (Matern 5/2 with ARD, one GP per objective, inputs scaled to the unit box, fitted by marginal
likelihood on all 92 points). Nothing was tuned after seeing a result.

## 1. Fit on the full pool

`hypers.json`: for `recovery_total` the lengthscales are 10.0 (theta1) and 6.5 (theta2) box widths and the
fitted noise variance is 1.1e-6 in standardised units, which is a noise standard deviation of about 4e-5 in
recovery (the pool spans 0.256 to 0.406). For `log q_peak` the lengthscales are 15.7 and 5.7 box widths
and the noise variance 2.1e-6, about 0.03 percent in q_peak. Lengthscales several times the box mean the
two surfaces are close to linear over the trimmed box, steeper in theta2 than in theta1. The small but
non-zero noise is physically reasonable: the mesh is regenerated for every design (25800 to 37400 cells
in the pool), so the discretisation error is not identical from point to point and the GP treats the
difference as noise.

## 2. Pareto front with uncertainty (`pareto_front.png`, `pareto.csv`)

- The observed front has 26 non-dominated points of 92, from (q_peak 22.5 kW/m2, recovery 0.256) to
  (49.6 kW/m2, 0.406).
- The predicted front (GP mean over the 39083 feasible grid points, 201 by 201 grid with gate 4 applied)
  runs from 21.3 kW/m2 to 51.1 kW/m2 and recovery 0.244 to 0.410, slightly beyond the observed points at
  both ends because the grid reaches the box corners the Sobol design does not hit exactly.
- The predicted front lies above the observed front points by 1.8e-4 to 9.6e-3 in recovery at equal
  q_peak (median 3.4e-3). This is not model error: the GP interpolates the pool to about 1e-5 (replay,
  n = 48). It is the sampling gap of a 92-point design against a continuous front, and it says that the
  best observed points are up to 0.01 in recovery short of the predicted optimum at their heat flux.
- The posterior 5 to 95 percent band of the front (`notes.json`: 50 joint samples of the two GPs on 1500
  feasible points, 25 q levels) is 1.2e-4 to 1.8e-3 wide in recovery (median 1.6e-4). It is barely
  visible on the figure. The discretisation error bar from the grid study (V4m, medium to fine:
  recovery +0.09 percent, q_peak -1.68 percent) is 3.1e-4 in recovery and 530 W/m2 in q_peak at the
  middle of the front, so the horizontal (heat flux) error of the mesh is 25 times the posterior
  uncertainty. This is the B3 point in the talk: on this pool the front is limited by the mesh level,
  not by the surrogate, and the next euro of compute goes to a finer mesh, not to more medium-mesh runs.

## 3. Inverse query: maximum recovery under a heat-flux cap (`inverse_q40/result.json`)

- Cap: the 40th percentile of the pool's q_peak, 31493.2 W/m2, fixed from the pool before the answer
  was computed. Feasibility rule from the spec: P(q_peak <= cap) >= 0.9 under the predictive
  distribution; 15848 of the feasible grid points qualify.
- Answer: theta1 = 11.965 deg, theta2 = 7.115 deg (case id `inlet2r-374dad241f`). Predicted
  recovery 0.34515, 90 percent predictive interval 0.34506 to 0.34523 (std 5.1e-5). Predicted q_peak
  median 31470 W/m2, interval 31450 to 31490 W/m2 (log std 3.9e-4), P(q <= cap) = 0.972.
- Sanity check against the pool: the two nearest runs are `inlet2r-c0882cb42d` (11.877, 6.759:
  recovery 0.33973, q_peak 30591 W/m2, the best observed point under the cap) and `inlet2r-7af9849a8d`
  (11.772, 7.798: 0.35233, 32937 W/m2). The answer sits between them in theta2 and 0.09 deg further
  along theta1, and the predicted values lie between theirs. The surrogate's gain over the best
  observed point under the cap is 0.0054 in recovery, which is 17 times the predicted std and 17 times
  the discretisation error in recovery; the extra heat flux is 880 W/m2, within the cap by 23 W/m2 in
  the median and by 0.972 in probability.
- On the 89-point pool (dry run, not committed) the same query answered theta1 = 12.0 (box edge),
  theta2 = 7.07. The last three pool points moved the answer 0.035 deg in theta1 and 0.045 deg in
  theta2 and the predicted recovery by 2.8e-4. The answer is stable to the sampling at the level of the
  discretisation error.

### Confirmation run (C2)

`inverse_q40/params.json` (`{"family": "inlet2r", "theta1_deg": 11.965, "theta2_deg": 7.115,
"mesh_level": "medium", "tag": "confirm", "save_volume": false}`) was passed through `validate_config`
(schema, gates, geometry, mesh quality: all pass, min angle 58.4 deg, 28800 cells) and staged with
`create_case` and `submit` through the MCP server; its `config_sha256` is `b0c231e7...` (identical to
the pool). The job file `inlet2r-374dad241f.json` was uploaded to the Drive jobs folder at 11:52 UTC
(Drive id `1DdL1kOMnsYHRuHLu_QpWksKcKwc-igQs`, recorded with `record_transfer`). C2 is the test that the
SU2 result falls inside the 90 percent intervals above. It is a strict test: the recovery interval is
1.7e-4 wide and the q_peak interval 40 W/m2 wide, and the replay calibration (`2026-11-02_replay.md`)
found the recovery intervals conservative and the q_peak intervals about nominal, so a miss, if any, is
more likely in q_peak. The outcome is reported either way by `analysis.confirm` once the result is
ingested; until then no claim is made.

## 4. Design maps (`design_map.png`, `oswatitsch_cut.png`, `grid.csv`)

- Recovery mean rises from 0.244 at (5, 5) to 0.410 at the gate-4 edge near (10, 14); q_peak median
  from 21.3 to 51.1 kW/m2 over the same box. Both increase with both angles, faster in theta2, and the
  hatched corner is the gate theta1 + theta2 > 24 deg.
- Posterior std of recovery is 1.8e-5 to 1.1e-4 (median 2.2e-5), largest at the four box corners where
  the design has no point; q_peak relative std 0.013 to 0.069 percent. These are the maps active learning
  would read; with a 92-point pool there is no region of the box where the model is less certain than
  the mesh.
- Oswatitsch cut (theta2 = theta1 + 2 deg): the GP mean recovery is 0.0008 to 0.0022 above the inviscid
  two-oblique-plus-normal-shock analytic curve along the whole cut. The sign is at first surprising for
  a viscous solution. The records explain it: in `inlet2r-fd8bbe1147` the mass-averaged throat Mach is
  2.627 against 2.677 inviscid and the throat recovery 0.853 against 0.866 inviscid, so the boundary
  layers cost 1.5 percent of total pressure before the throat but also lower the throat Mach, and the
  terminal normal shock is weaker by enough to more than pay it back in the total. The difference is of
  the order of the discretisation error and is reported as an observation, not as a validated effect.

## Verdict against the Task 5 acceptance

The front, its band, the discretisation bar, the inverse answer and the design maps come from committed
runs and committed scripts. The acceptance test (confirmation inside the predicted interval, or the miss
documented) is pending the SU2 result of `inlet2r-374dad241f`.

# Task 5 spec: Pareto front with uncertainty, inverse query, confirmation runs (Day 9)

Interprets and writes the narrative: Fable 5.1. Implements the scripts: Sonnet 5.5
(`analysis/pareto.py`, `analysis/inverse.py`). Plots: Haiku 5.5 from the CSVs these scripts
write. Runs: Éder submits the confirmation cases through the MCP tools (that is the one online
active-learning step we actually perform).
Depends on: Task 4 GP fitted on all converged or stationary pool runs; Task 3 queue.

## Deliverables

1. `analysis/pareto.py`: fit the two GPs on all usable pool runs; evaluate on a 201 x 201 grid
   of the box; write `runs/analysis/<date>/grid.csv` (theta1, theta2, mean and std of both
   objectives) and `pareto.csv` with: (a) observed non-dominated pool points (true values),
   (b) the predicted front from the posterior mean on the grid, (c) 50 posterior sample fronts
   (joint draws on the grid with a fixed seed) summarised as the 5 to 95 percent band of
   recovery_total at fixed q_peak levels. The figure must distinguish observed points from
   predicted curves and show the discretisation uncertainty from the grid study as an error
   bar on one observed point.
2. `analysis/inverse.py --q-cap Q`: the inverse-design query "maximise recovery_total subject to
   q_peak <= Q" answered on the grid using the posterior: feasible if the predicted probability
   P(q_peak <= Q) >= 0.9; among feasible points pick the maximum predicted mean recovery;
   report the design (theta1, theta2), predicted means and 90 percent intervals for both
   objectives, and write `params.json` for the confirmation run with tag `confirm`. Default Q:
   the 40th percentile of the pool's q_peak (where the front is steep); a second query at the
   60th percentile if time allows.
3. Confirmation: Éder submits the case(s) through `create_case` and `submit`; after `postprocess`
   the script `analysis/confirm.py` compares the SU2 values with the predicted intervals and
   writes the pass/fail of C2 with the numbers, and refits the GP with the new point to report
   how much the interval shrank (the online active-learning step in the talk).
4. `analysis/design_map.py` (Haiku): maps over the box of recovery_total mean, its std, q_peak
   mean, its std, and the EHVI at the last replay step, with the pool points overlaid; one
   figure, five panels. Also the 1D cut along the Oswatitsch split (theta1 = theta2 - 2 deg)
   with the analytic two-shock-plus-normal-shock curve for context.
5. Backup slide material (cut first): one Spalart-Allmaras run at 8/8 on the medium mesh with
   wall spacing checked for y+ <= 1 from the laminar solution; both objectives reported next to
   the laminar values. If it is not run, the slide says so.

## Acceptance

- `test_pareto.py`: on a synthetic pool the observed front is correctly non-dominated, the
  predicted front is monotone in the two-objective sense, and the band contains the mean curve.
- `test_inverse.py`: on the synthetic pool with a known analytic optimum under the cap, the
  returned design is within one grid cell of the true constrained optimum; an infeasible cap
  returns an explicit "no feasible design at 90 percent" result rather than a point.
- C2 reported honestly: inside or outside the interval, with both predicted and simulated
  values and the refit shrinkage. A miss is explained (which GP, which direction, plausible
  cause: separation onset, mesh, noise floor) and left in the deck.
- Every figure caption lists the `case_id`s or the replay file it was made from.

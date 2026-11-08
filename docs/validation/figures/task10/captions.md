# Task 10 figures: captions

- `a_front_lowfi.png`: Exact Pareto front of the low-fidelity model over the 9^6 grid and the front of the 192-point low pool, endurance against take-off mass. Sources: `runs/drone_grid/2026-11-08/front.csv`, `runs/drone_pool_lf/2026-11-08/front.csv`.
- `b_pool_replay.png`: Pool replay on the 192-point low pool: mean hypervolume regret and held-out RMSE against evaluations, 10 seeds. Source: `runs/replay_drone_pool/2026-11-08/replay.csv`.
- `c_online_regret.png`: Online replay, unrestricted candidates: mean regret and gated picks for the four strategies and the two feasibility-weighted ones. Sources: `runs/replay_drone_online/2026-11-08/online.csv`, `runs/replay_drone_online/2026-11-08_feas/online.csv`.
- `d_e387_comparison.png`: SU2 cl and cd against the UIUC E387 tunnel data at the same angles, one column per Reynolds number with a complete or partial set. Sources: `runs/e387/*/result.json`, `data/validation/e387_uiuc.yaml`.

# Task 4b: a neural-network ensemble against the GP in the same replay (2026-11-02)

Written from `runs/replay/2026-11-02_mlp/replay.csv` (the MLP ensemble replay), the GP replay
`runs/replay/2026-11-02_full/replay.csv`, and the tables in `docs/validation/2026-11-02_replay_gp_vs_mlp.md`
(medians over 10 seeds, from `python -m postprocess.plot_model_compare`). Every number below is in
one of those files. All settings were fixed in `docs/specs/task4b_mlp_ensemble.md` and committed
(c5d8692) before the replay ran; nothing was changed after seeing a result.

## Setup

- Model: a deep ensemble of 5 multilayer perceptrons, each 2 -> 64 -> 64 -> 1 with tanh (4417
  weights per member), trained by full-batch mean squared error with AdamW (learning rate 1e-2,
  weight decay 1e-4, 2000 steps). Prediction is the ensemble mean; uncertainty is the spread
  between members plus the training error as a noise term. One ensemble per output, as for the GP.
- Replay: identical to the GP replay (92 pool points, seeds 0 to 9, 8 initial points, budgets 8 to
  48, strategies random, lhs, al_ehvi, al_maxvar, the same metrics). Only the surrogate changes.
  For random and lhs the selected points do not depend on the model, so those rows compare the two
  surrogates on exactly the same training sets.
- Command: `python -m surrogate.replay --results runs/pool/results.csv --model mlp --n-max 48`
  in four processes (`--first-seed 0, 3, 6, 8`), merged into `replay.csv` (5760 rows); 27 minutes
  of wall time on the container's 4 cores (`parts/started.txt`, `parts/log_*.txt`).

Figure: `docs/validation/2026-11-02_replay_gp_vs_mlp.png` (GP solid, MLP ensemble dashed). The
standard replay figures for the ensemble alone are `2026-11-02_replay_mlp_error_vs_n.png` and
`2026-11-02_replay_mlp_calibration.png`.

## Findings

1. **Held-out accuracy: the GP is better at every budget for every strategy.** The median RMSE of
   recovery is 2.2 to 10.5 times larger with the ensemble, and the relative RMSE of q_peak 1.2 to
   10.3 times larger. At n = 48: recovery RMSE 1.27e-4 against 2.26e-5 (lhs) and 7.41e-5 against
   1.42e-5 (al_maxvar, the best strategy for both models); q_peak 7.6e-4 against 3.9e-4 (lhs). On
   identical training sets the ensemble is worse in 10 of 10 seeds for random and lhs at n = 24
   and at n = 48. With 8 points the ensemble's recovery error is 3.2e-3, 8.6 times the GP's.

2. **Finding the front: the ensemble does as well as the GP.** EHVI driven by the ensemble reaches
   zero hypervolume regret at n = 32 in 10 of 10 seeds, as the GP does. Its median regret is level
   or slightly lower at n = 16 to 24 (0.042 against 0.043, 0.014 against 0.022, 0.006 against 0.013),
   with overlapping interquartile bands. EHVI needs a correct ranking of candidates near the front,
   not interpolation to 1e-5, and the ensemble ranks well enough. Max-variance does worse with the
   ensemble (regret 0.018 against 0.008 at n = 48), because the spread between five networks is a
   noisier guide to where the model is ignorant than the GP variance.

3. **Calibration at n = 48 (44 held-out points): mixed, for a different reason than the GP's.**
   q_peak coverage at the 90 percent level is 0.88 to 0.95 for the ensemble (inside the 80 to 97
   percent band for every strategy) against 0.84 to 0.91 for the GP. Recovery coverage at 90
   percent is 0.84 (random), 0.97 (lhs), 0.98 (al_ehvi) and 1.00 (al_maxvar), against 1.00 for the
   GP everywhere; at the 50 percent level the ensemble covers 0.50 to 0.77 against 0.83 to 0.98.
   The ensemble's intervals are closer to nominal only because its errors are 5 to 10 times larger
   and its spread grows with them; the GP's over-coverage is the conservative side of a much
   smaller error.

4. **Cost.** One EHVI step takes 6.2 s with the ensemble against 1.7 s with the GP at n = 48 (fit
   of both outputs plus acquisition, container CPU); one ensemble fit is about 3 s against 0.7 s.
   The GP needs no GPU, and neither does the ensemble at this size.

## Verdict

On this problem the GP is the right surrogate: 2 to 10 times more accurate on held-out designs,
about a quarter of the cost, and with intervals that come from the posterior rather than from
the disagreement of five trainings. The active-learning conclusion does not depend on that
choice: EHVI with the ensemble finds the whole true front by n = 32 in every seed, as with the GP.

What this does not show: that a neural network cannot match the GP here. The ensemble was not
tuned (width, depth, steps, weight decay, learning rate were fixed in advance by rule), and a
smaller network or more regularisation would likely narrow the gap. The comparison answers the
interview question "why a GP and not a neural network" with recorded numbers, not a general
statement. With 2 inputs and at most 48 smooth samples, a GP's prior is a strong advantage; with
tens of inputs or field outputs the balance changes, which is where an operator network would be
tested next (the 92 wall heat-flux profiles, `docs/specs/task4b_mlp_ensemble.md`).

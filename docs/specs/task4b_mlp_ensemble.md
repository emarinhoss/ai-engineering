# Task 4b spec: a neural-network ensemble against the GP in the same replay (2026-11-02)

Requested by Éder on 2026-11-02 ("can we do a Fourier neural operator, or any other neural network").
Written before any run; every setting below is fixed here and is not changed after seeing a result.

## Question

On this problem (2 inputs, 8 to 48 training runs, 2 scalar outputs), does a neural-network
surrogate with ensemble uncertainty match the exact GP on held-out error, interval calibration and,
when EHVI uses it, hypervolume regret? The answer is reported whichever way it goes.

Why not a Fourier neural operator: an FNO maps functions to functions and needs field data on a
grid, typically hundreds to thousands of samples. The pool has 92 scalar results and 3 volume
fields. A 1D operator on the 92 wall heat-flux profiles is possible later (needs the surface files
out of Drive); it is not part of this task.

## Model (`surrogate/mlp.py`, class `MLPEnsemble`, same interface as `surrogate.gp.GP`)

- A deep ensemble in the sense of Lakshminarayanan, Pritzel and Blundell (2017), without variance
  heads: K = 5 independent multilayer perceptrons, each 2 -> 64 -> 64 -> 1 with tanh activations.
- Inputs: the unit-square inputs of the replay mapped to [-1, 1] (x' = 2x - 1). Output: the
  standardised target (the replay's `Standardizer`), one ensemble per output, as for the GP.
- Initialisation: uniform(-1/sqrt(fan_in), +1/sqrt(fan_in)) for weights and biases (the PyTorch
  `nn.Linear` default), from one `torch.Generator` seeded with 0, so a fit is deterministic given
  its data. The members differ only by their initial weights.
- Training: full batch, mean squared error, AdamW with learning rate 1e-2 and weight decay 1e-4,
  2000 steps, float64. The five members are trained together as one batched tensor; Adam and the
  weight decay act elementwise, so this is the same arithmetic as five separate trainings.
- Prediction: mean = average of the member predictions; variance = sample variance (ddof 1) of the
  member predictions, floored at 1e-12. With `noise=True` the noise variance is added: the mean
  over members of the training MSE, plus the GP's noise floor 1e-6 (standardised units).
- `hypers()`: members, noise variance (training MSE), final training loss.

## Replay

`python -m surrogate.replay --results runs/pool/results.csv --model mlp --n-max 48 --out
runs/replay/2026-11-02_mlp/replay.csv`. Same pool (92 points), seeds 0 to 9, n_init 8, budgets
8 to 48, the same four strategies, the same metrics and the same CSV format as the GP replay in
`runs/replay/2026-11-02_full/`. Only the surrogate changes. For `random` and `lhs` the selected
points are identical to the GP replay (selection does not use the model), so their rows compare
the two models on exactly the same training sets.

## Report

- `postprocess.plot_replay` on the MLP CSV (prefix `2026-11-02_replay_mlp`), and a head-to-head
  figure and table (`postprocess/plot_model_compare.py`): median and interquartile band over seeds
  of held-out RMSE of recovery, relative RMSE of q_peak and hypervolume regret against n, GP solid
  and MLP dashed; coverage at the 90 percent level at n = 48.
- `docs/validation/2026-11-02_replay_mlp.md`: the numbers and the verdict, written from the files.
- Deck: one backup slide (B7) with the head-to-head figure; outline and study guide updated.

## Acceptance

The replay runs to completion with the settings above; the report states the comparison at every
budget, including where the ensemble wins, if it does. Tests: the ensemble fits a smooth function
of two inputs to small error, is deterministic given its data, returns positive variances that grow
away from the data, and the replay runs with `model="mlp"` on the synthetic pool.

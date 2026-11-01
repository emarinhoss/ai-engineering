# Task 4 spec: Gaussian-process surrogate, acquisition, pool replay (Days 7-8)

Designs the experiment and reviews: Fable 5.1. Implements: Sonnet 5.5 (GP, acquisition,
replay harness, tests). Haiku 5.5 (plots from the replay CSVs). Runs: CPU, anywhere (Colab GPU
not needed; the replay for 4 strategies x 10 seeds x 40 steps of a 2-input GP on <= 100 points
takes minutes on CPU).
Depends on: `runs/pool/` with >= 64 converged or stationary pool runs; `01_interfaces.md`.

## Model

- Inputs x = (theta1, theta2) scaled to [0, 1]^2 with the design-box bounds. Outputs:
  y1 = recovery_total, y2 = log(q_peak_W_m2); each standardised with training mean and std.
- One exact Gaussian process per output (independent), pure PyTorch (float64):
  constant mean, Matern-5/2 kernel with ARD lengthscales (2), signal variance, noise variance
  with a floor of 1e-6 in standardised units. Hyperparameters by maximising the log marginal
  likelihood with Adam (lr 0.05, 300 steps) from 3 fixed restarts (log-lengthscales -1, 0, 1),
  keep the best. Posterior mean and variance in closed form via Cholesky with jitter 1e-8.
  Target size: `surrogate/gp.py` under 150 lines, every line explainable.
- Why a GP and not an ensemble: 2 inputs, under 100 points, calibrated intervals come from the
  posterior, and the acquisition needs a cheap posterior at thousands of candidates. Deep
  ensembles are mentioned in the talk as the alternative for high-dimensional inputs.

## Acquisition (minimisation form f1 = -recovery_total, f2 = log q_peak)

- `ehvi_mc(gp1, gp2, X_cand, front, ref, n_samples=128, seed)`: Monte-Carlo expected
  hypervolume improvement with the 2D hypervolume computed exactly by sorting; ref point =
  nadir of the observed objectives plus 10 percent of their ranges; ties broken by the larger
  summed standardised variance.
- `max_variance(gp1, gp2, X_cand)`: sum of standardised posterior variances (pure exploration
  baseline, learns the whole map).
- Candidates: in replay the unselected pool points; online a 2048-point scrambled Sobol set
  (seed 1) plus the pool.

## Replay harness (`surrogate/replay.py`)

- Pool: all pool runs with status converged or stationary. Initial design: 8 points drawn at
  random from the pool with `seed`; identical across strategies for that seed.
- Strategies, each adding one point per step until n = 40 (or 48 if the pool has 96):
  `random` (uniform over unselected pool points), `lhs` (for each budget n in the report list a
  fresh maximin LHS of size n, seed-dependent, mapped to nearest unused pool points: an
  offline space-filling baseline, not sequential), `al_ehvi`, `al_maxvar`.
- Metrics at n in {8, 12, 16, 20, 24, 32, 40, 48}: RMSE on the held-out pool points for
  recovery_total (absolute) and for q_peak (relative, from exp of the log prediction);
  hypervolume regret = HV(true pool front) - HV(true values of the selected points' front),
  normalised by HV(true pool front); 50/80/90/95 percent interval coverage on held-out
  points (C1); wall time per step. 10 seeds (0-9). Output `runs/replay/<date>/replay.csv`
  with one row per strategy, seed, n, metric, value, plus the GP hyperparameters per fit.
- Honesty rule from PLAN.md: the plots show all strategies with median and interquartile band
  over seeds. If active learning does not beat random or LHS on a metric, the text says so and
  the investigation (kernel, noise floor, acquisition) is reported as a finding, not as a
  reason to change the result.

## Acceptance tests

- `test_gp.py`: (a) 1D sine with 20 noiseless points: posterior mean RMSE at 200 interior test
  points < 1e-2 after fitting; (b) posterior mean and variance at 5 test points match a numpy
  reference implementation on a fixed 6-point dataset to 1e-8; (c) LML gradient versus finite
  differences agrees to 1e-5; (d) predictive variance at a training point <= noise variance +
  1e-6; (e) standardisation round-trips.
- `test_hypervolume.py`: 2D hypervolume of a hand-set front equals the hand-computed value;
  dominated points do not change it; EHVI of a candidate far inside the dominated region is
  ~0 and of one far beyond the front is large.
- `test_acquisition.py`: on a synthetic two-objective toy (Fonseca-Fleming scaled to 2D),
  `al_ehvi` reaches lower hypervolume regret than `random` at n = 24 in at least 7 of 10
  seeds; this guards the implementation, not the physics result.
- `test_replay.py`: on a synthetic pool (analytic two-shock recovery and the Eckert-like
  heating proxy from `physics`) the harness runs all strategies for 2 seeds to n = 16 in under
  60 s and writes a CSV with the expected columns and row count.
- Review by Fable: calibration plot (coverage versus nominal level) and error-versus-n plots
  exist for all four strategies with seeds; the replay used only runs whose `case_id` is in
  `runs/pool/`; the gate in PLAN.md Task 4 ("do not tune until AL wins") is respected and the
  replay CSV is committed.

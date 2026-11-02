# Task 4c spec: a 1D neural operator for the ramp-2 heat-flux profile (2026-11-02)

Requested by Éder on 2026-11-02 after Task 4b. Written before any profile was extracted and before
any model was trained; every setting below is fixed here and is not changed after seeing a result.

## Question

Can a Fourier neural operator (FNO) learn the whole wall heat-flux distribution on ramp 2 as a
function of (theta1, theta2) from the 92 pool runs, and how does it compare with the classical
baseline for a parameter-to-function map, principal components plus a GP on the coefficients? The
answer is reported whichever way it goes. A secondary question: does the peak of a predicted
profile estimate q_peak as well as the scalar GP of Tasks 4 and 5 does?

## Data (`runs/profiles/2026-11-02/`)

- Source: the 92 pool cases re-run serially on the container with the SU2 v8.2.0 release binary
  (`python -m analysis.rerun_surfaces`), from each case's recorded `params.json` through the normal
  staging pipeline. Each re-run is accepted only if `recovery_total` and `q_peak_W_m2` equal the
  Colab record to a relative 1e-6 (`rerun_check.csv`); a case that fails is listed and left out.
- Profile (`analysis/profiles.py`): the body-wall nodes of ramp 2 with the same window as the
  q_peak objective (`postprocess/metrics.py`: x >= X1, nodes within 2 mm of the throat plane
  excluded), ordered along the wall. Coordinate s = (x - x_start) / (x_end - x_start) on that
  window, so every design maps to s in [0, 1]. q is interpolated linearly onto 128 uniform points
  in s. The mesh is rebuilt from `params.json` (`worker.make_case`) to identify the body nodes, and
  its fingerprint must equal the record's. Data checks: q > 0 everywhere; the profile maximum is
  within 0.5 percent of the recorded q_peak (interpolation may only lower it).
- Target y(s) = log q(s). Inputs: (theta1, theta2) scaled to the unit square as in the replay.
- Output table `profiles.csv`: case_id, theta1, theta2, x_start, x_end, q_0 .. q_127 (W/m^2).

## Models

1. **PCA + GP (baseline)**, `surrogate/pca_gp.py`. Centre the training targets by their mean
   profile and divide by one global standard deviation; singular value decomposition; keep the
   smallest number of components that explains 99.9 percent of the training variance, at most 8.
   One GP (`surrogate.gp.GP`, Matern 5/2, ARD) per component coefficient, coefficients standardised.
   Prediction: mean profile from the predicted coefficients; variance per point from the
   coefficient variances times the squared component values (independent components).
2. **FNO ensemble**, `surrogate/fno.py`. Input on the 128-point grid: three channels, s, theta1 and
   theta2 (the two angles as constant channels). Lift to width 32 by a pointwise linear map; four
   Fourier layers, each the sum of a spectral convolution on the lowest 16 modes and a pointwise
   linear map, followed by GELU (no GELU after the last); project 32 -> 64 -> 1. The profile is not
   periodic, so the grid is padded with 32 zeros at the end before the Fourier layers and cropped back
   to 128 points after them (Li et al. 2021 pad the same way for non-periodic problems). Target scaled as for
   PCA + GP. Training: full batch, mean squared error, AdamW (learning rate 3e-3, weight decay 1e-4),
   3000 steps, float32. Five members with seeds 0 to 4; mean and variance between members, as in
   Task 4b.

## Evaluation (`analysis/operator_compare.py`)

- Regime A, all data: 5-fold cross-validation over the designs (fold assignment from a permutation
  with seed 0), so every design is predicted once by models trained on 73 or 74 others.
- Regime B, little data: 24 random training designs, the other designs held out; 5 repeats with
  seeds 0 to 4.
- Per held-out design: relative L2 error of q on the 128 points, ||q_hat - q|| / ||q||; maximum
  pointwise relative error; relative error of the profile peak; peak location error in mm (x of the
  argmax); fraction of the 128 points inside the 90 percent band (mean +/- 1.645 std in log q).
  For the peak, also the scalar GP on log q_peak (`surrogate.gp.GP`) trained on the same designs.
- Reported: median and 90th percentile over held-out designs, per model and regime; wall time to
  train.
- Figure: held-out profiles at four designs fixed now by rule, the pool designs nearest to
  (6, 6), (11, 6), (6, 13) and (10, 12) degrees, from regime A; truth, PCA + GP and FNO with their
  90 percent bands; and the distribution of the relative L2 error per model and regime.
- Report `docs/validation/2026-11-02_operator_profiles.md`, one backup slide, study guide entry.

## Acceptance

Profiles extracted for every re-run that matches its record; both models evaluated in both regimes
with the settings above; the report states which model is better on each metric and by how much,
including if the FNO is not. Tests: profile extraction on a committed surface file (8/8 laminar,
`runs/dev/2026-11-01_inlet_grid_study_ef03/8_8_medium`) reproduces its recorded q_peak; PCA + GP
and FNO fit a smooth synthetic family of profiles; the FNO spectral layer keeps only the requested
modes; the comparison runs end to end on a small synthetic data set.

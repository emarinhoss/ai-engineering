# Task 4c: a 1D Fourier neural operator for the ramp-2 heat-flux profile

Spec: `docs/specs/task4c_operator_profiles.md` (fixed before any profile was extracted or any model
trained). Runs finished 2026-11-03 UTC; the record directory keeps the spec date.

## Records

| What | Where |
|---|---|
| 92 pool re-runs on the container (SU2 v8.2.0 release binary), checked against the Colab records | `runs/profiles/2026-11-02/rerun_check.csv`, `runs/profiles/2026-11-02/surfaces/` |
| 92 ramp-2 profiles, 128 points each | `runs/profiles/2026-11-02/profiles.csv` |
| Per-design metrics, both regimes, three models | `runs/profiles/2026-11-02/operator_compare.csv` |
| Predictions at the four figure designs | `runs/profiles/2026-11-02/figure_profiles.csv` |
| Summary table and figure | `docs/validation/2026-11-02_operator_summary.md`, `docs/validation/2026-11-02_operator.png` |
| Truncation-floor diagnostic (post hoc, section 4) | `runs/profiles/2026-11-02/pca_floor.csv`, `analysis/pca_floor.py` |

Commands:

```
python -m analysis.rerun_surfaces --su2-cmd SU2_CFD --work WORK --out runs/profiles/2026-11-02 --jobs 4
python -m analysis.profiles --surfaces runs/profiles/2026-11-02/surfaces --check runs/profiles/2026-11-02/rerun_check.csv --out runs/profiles/2026-11-02/profiles.csv
python -m analysis.operator_compare --profiles runs/profiles/2026-11-02/profiles.csv --out runs/profiles/2026-11-02 --jobs 4
python -m analysis.operator_compare --report runs/profiles/2026-11-02 --fig-dir docs/validation --prefix 2026-11-02_operator
python -m analysis.pca_floor --profiles runs/profiles/2026-11-02/profiles.csv --out runs/profiles/2026-11-02
```

## 1. Data

- All 92 pool cases were re-run from their recorded `params.json`. All 92 converged. Largest
  relative difference from the Colab record: 3.3e-16 in `recovery_total`, 0 in `q_peak_W_m2`. No case
  was left out. Wall time per case on the container: 279 to 547 s (median 379 s), four at a time.
- Process note: the first background run stopped at its 2-hour limit after 72 cases; the restart ran
  the other 20, but their rows in `rerun_check.csv` were lost because a git branch switch replaced the
  tracked file while the driver appended to it. Those 20 cases were run a third time to write their
  rows. Their surface files from the two runs are identical after decompression.
- All 92 profiles pass the data checks: q > 0 everywhere, and the profile maximum is within 0.5 percent
  of the recorded q_peak. The ramp-2 window is 110 to 218 mm long (median 143 mm), so the 128-point
  grid step is 0.86 to 1.72 mm.

## 2. Results (median, 90th percentile in brackets, over held-out designs)

Regime A: 5-fold cross-validation, every design predicted once by models trained on 73 or 74 others
(92 held-out profiles). Regime B: 24 training designs, 5 repeats (340 held-out profiles).

| Metric | Regime | PCA + GP | FNO ensemble | scalar GP (peak only) |
|---|---|---|---|---|
| Relative L2 error of q | A | 0.32% (0.71%) | 0.11% (0.23%) | - |
| | B | 0.36% (0.78%) | 0.15% (0.35%) | - |
| Maximum pointwise relative error | A | 1.8% (3.3%) | 0.45% (0.84%) | - |
| | B | 2.2% (4.0%) | 0.73% (2.3%) | - |
| Relative error of the peak | A | 0.18% (0.61%) | 0.092% (0.33%) | 0.013% (0.063%) |
| | B | 0.17% (0.64%) | 0.096% (0.29%) | 0.026% (0.13%) |
| Peak location error (mm) | A | 0 (1.24) | 0 (0) | - |
| | B | 0 (1.35) | 0 (1.18) | - |
| Fraction of points inside the 90% band | A | 0.11 (0.32) | 0.93 (1.0) | - |
| | B | 0.40 (0.70) | 0.81 (0.98) | - |
| Fit time per split (s) | A | 4.7 | 1030 | - |
| | B | 1.4 | 342 | - |

PCA + GP kept 3 components in every split (99.9 percent rule of the spec). Fit times are wall times
on the container CPU with four splits running at once, one thread each; the FNO time is for five
members of 3000 steps. No GPU was used.

## 3. What the numbers say

1. **Profile accuracy: the FNO is better, by a factor of about 2.5 to 3.** Median relative L2 error
   0.11 against 0.32 percent with all data, 0.15 against 0.36 percent with 24 runs. Per design, the
   FNO error is lower for 91 of 92 designs in regime A (median ratio 2.7) and for 92 percent of the
   340 held-out profiles in regime B (median ratio 2.4). The maximum pointwise error is 3 to 4 times
   lower.
2. **Both models are far below what a plot can show.** In the figure the predicted profiles lie on the
   SU2 profile at all four designs. Both are well inside any engineering tolerance on wall heating;
   the comparison is between two accurate models.
3. **Peak location:** the FNO puts the peak on the same grid point as SU2 for 93 percent of designs in
   regime A (PCA + GP: 64 percent). Errors, when present, are one or two grid steps (at most 1.6 mm
   for the FNO, 2.3 mm for PCA + GP).
4. **Uncertainty:** the FNO band holds 93 percent of points with all data (target 90) and 81 percent
   with 24 runs (under-covers). The PCA + GP band holds only 11 and 40 percent: it is far too narrow,
   because its variance carries only the coefficient uncertainty and not the error of the dropped
   components (section 4).
5. **For the objective q_peak, the scalar GP stays the best tool.** Its median peak error is 0.013
   percent with all data, 7 times lower than the FNO's peak (0.092 percent) and 13 times lower than
   PCA + GP's (0.18 percent). With 24 runs: 0.026 against 0.096 and 0.17 percent. The scalar GP
   models exactly the quantity that is asked; a profile model spends its capacity on the whole
   curve. The secondary question of the spec is answered: no, the predicted profile's peak is not as
   good as the scalar GP.
6. **Cost:** the FNO ensemble takes about 1000 s per fit with all data, 220 times the PCA + GP.

## 4. Post-hoc diagnostic: the PCA + GP error is truncation error

This section was added after seeing the results. It changes nothing in section 2. `analysis/pca_floor.py`
projects each held-out profile onto the first k training components on the same splits, which is the
smallest error any coefficient model can reach with k components:

| k | Training variance kept (min over splits) | Floor, regime A: median (90th pct) | Floor, regime B |
|---|---|---|---|
| 3 (the spec's rule) | 0.99924 | 0.32% (0.71%) | 0.36% (0.76%) |
| 5 | 0.99988 | 0.12% (0.26%) | 0.14% (0.30%) |
| 8 | 0.99999 | 0.056% (0.086%) | 0.055% (0.12%) |

With k = 3 the floor equals the PCA + GP error to the printed digits, so the GPs on the three
coefficients are nearly exact and all of the PCA + GP profile error is the truncation the 99.9
percent rule allows. With 5 components the floor equals the FNO error; with 8 it is half of it. A
PCA + GP with more components might therefore match or beat the FNO, but **that was not run**: the
component rule was fixed in the spec before any result, and changing it now would be tuning the
baseline after seeing the answer. The honest statement is: under the pre-registered settings the FNO
wins on the profile by about 3 times; the margin comes from the baseline's truncation, not from a
limit of GP regression.

## 5. Verdict against the acceptance criteria

- Profiles extracted for every re-run that matches its record: 92 of 92. PASS.
- Both models evaluated in both regimes with the spec settings: done (10 splits, 3 models).
- Which model is better on each metric, and by how much: section 3. FNO better on profile error, peak
  location and band coverage; scalar GP better on the peak; PCA + GP about 220 times cheaper to fit.
- Tests (`tests/test_operator.py`): profile extraction reproduces the recorded q_peak of the committed
  8/8 surface file; PCA + GP and FNO fit a synthetic family; the spectral layer keeps only the
  requested modes; the comparison runs end to end. 4 passed.

## 6. Limits

- Two inputs and one flight condition: the operator maps (theta1, theta2) to a profile on a fixed
  window coordinate. It has not been tested on a different mesh resolution, which is where a neural
  operator's resolution independence would matter.
- The FNO here is used as a function-valued regressor; the angle inputs enter as constant channels.
- All profiles come from laminar runs; the Spalart-Allmaras bound (`docs/validation/2026-11-02_sa_sensitivity.md`)
  applies to them as to the scalar objective.

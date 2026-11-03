Source: runs/profiles/2026-11-02/operator_compare.csv. Median (90th percentile) over held-out designs;
fit_seconds per split (5 members for the FNO); cov90 is the mean fraction of the 128 points inside the band.

### Regime A: 5-fold cross-validation (train 73 or 74)

| metric | PCA + GP | FNO ensemble | scalar GP (peak only) |
|---|---|---|---|
| rel_l2 | 0.00323 (0.00712) | 0.00112 (0.00233) |  |
| max_rel | 0.0177 (0.0331) | 0.00449 (0.00839) |  |
| peak_rel | 0.00176 (0.00606) | 0.000922 (0.00331) | 0.000134 (0.000625) |
| peak_x_mm | 0 (1.24) | 0 (0) |  |
| cov90 | 0.109 (0.319) | 0.926 (1) |  |
| fit_seconds | 4.72 (5.14) | 1.03e+03 (1.04e+03) |  |

PCA components kept: [3]

### Regime B: 24 training designs, 5 repeats

| metric | PCA + GP | FNO ensemble | scalar GP (peak only) |
|---|---|---|---|
| rel_l2 | 0.00364 (0.00778) | 0.00153 (0.0035) |  |
| max_rel | 0.0216 (0.0404) | 0.00734 (0.0229) |  |
| peak_rel | 0.00172 (0.00642) | 0.000957 (0.00294) | 0.000264 (0.00128) |
| peak_x_mm | 0 (1.35) | 0 (1.18) |  |
| cov90 | 0.402 (0.704) | 0.805 (0.977) |  |
| fit_seconds | 1.42 (1.49) | 342 (344) |  |

PCA components kept: [3]

A run record is the full, reproducible trace of one SU2 run: the input parameters (`params.json`), the derived
geometry and mesh-quality report, the exact configuration (`case.cfg`), the solver version string, the
residual history, the surface output and log (gzip-compressed), and a `result.json` with the convergence
status and the metrics. Each record lives in `runs/<tag>/<case_id>/`, where `case_id` is a hash of the
parameters, so the same inputs always map to the same folder. A number may appear in docs or slides only
if the `case_id` that produced it is in this folder. Volume CSVs are too large for git and stay on Drive;
`result.json` records their sha256.

The exact file list, the `result.json` schema and the Drive queue layout are in
`docs/specs/01_interfaces.md` (sections "Job directory" and "Run record"). Task 1 records are written
under `runs/task1/` by `notebooks/00_su2_colab.ipynb`.

# Low-fidelity design grid, 2026-11-08

Run of `notebooks/10_drone_lowfi_grid_colab.ipynb` on a Colab CPU runtime (8 workers) at commit
4f086e5, the 9^6 grid of `docs/specs/task10_drone_sizing.md` section 8 through `analysis/drone_grid.py`.

- `record.json`: the run's own record (commit, ledger file hashes, wall time, point counts, sha256 of
  both CSVs), copied from Drive unchanged.
- `front.csv`: the exact Pareto front (endurance against take-off mass), 249 designs, sha256 verified
  against `record.json` on download.
- `grid.csv` is **not committed**: it is 229,089,020 bytes (531,441 rows), above GitHub's file limit.
  It stays on Drive at `su2queue/drone_grid/20261108T060338Z_4f086e5/grid.csv` with sha256
  `84587dc3b3ea2108f041eeafb49ee1a301714dc702bb7b90b4950f3d858bff8f` (from `record.json`). Anyone
  with the Drive folder can verify it with `sha256sum`; the grid is also reproducible from the commit
  and the ledger hashes in `record.json`, which is what the record is for.

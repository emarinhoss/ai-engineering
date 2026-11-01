# Task 1 spec: SU2 on Colab, first light, oblique-shock validation, timing (Days 1-2)

Implements: Sonnet 5.5 (code, tests, notebook). Reviews: Fable 5.1 (physics module, BCs, heat
flux sign, V1 postprocess) before anything is committed. Runs on Colab: Éder.
Depends on: `docs/specs/00_decisions.md` sections 1, 4 (V1, V2a), 6; `01_interfaces.md`.

## Goal

SU2 runs headless on a Colab CPU runtime from a pinned release binary; our own mesh and config
reproduce the oblique shock relations; the laminar wedge gives a wall time per iteration per
cell on 2 cores that sets the run budget for everything after.

## Deliverables

1. `physics/constants.py`, `physics/atmosphere.py`, `physics/shock.py` (oblique, normal,
   theta_max, Prandtl-Meyer not needed). Pure functions, numpy only, docstrings with the
   formula. `physics/atmosphere.state(30)` returns the table in `00_decisions.md` section 1.
2. `geometry/structured.py`: block-structured quad mesher.
   - `stretch_one_sided(L, N, d0)` nodes on [0, L], first spacing d0, geometric ratio solved by
     bisection, ratio reported; `stretch_two_sided(L, N, d0, d1)`; `stretch_capped(L, N, d0,
     dmax)` geometric growth then uniform at dmax.
   - `Block(edges)`: four discretised edges (bottom, right, top, left as point arrays with
     matching counts on opposite sides); interior by transfinite (Coons) interpolation.
   - `Mesh.from_blocks(blocks, shared_edges)`: global node numbering by edge identity (no
     coordinate-tolerance merging), quads oriented counter-clockwise, boundary lines per marker.
   - `Mesh.quality()`: min interior angle, max aspect ratio, max adjacent-cell size ratio along
     wall-normal lines, inverted-cell count, first-cell height per wall marker.
   - `Mesh.write_su2(path)` (ASCII, NDIME 2, NELEM, NPOIN, NMARK) and `write_markers(path)`.
3. `geometry/wedge.py: build(params)`: single wedge, X_w = 0.15, blocks: two columns
   ([x_in, 0] and [0, X_w]) by two rows (wall to y_split = 0.06, y_split to y_top = 0.20).
   Medium level sizes from `00_decisions.md` section 6; levels scale by 1.4.
4. `cases/config.py: render(params, geometry, markers)` with a template for EULER and
   NAVIER_STOKES, keys from `00_decisions.md` section 6. `cases/check_keys.py` compares every key
   in a rendered config with the pinned SU2 `config_template.cfg` and fails on unknown keys.
5. `postprocess/history.py: summarize()` and `postprocess/validation.py:
   oblique_shock_check(case_dir)` implementing V1 exactly as in `00_decisions.md` 4.V1 (volume
   CSV, two stations, plateau median, beta from two shock locations).
6. `notebooks/00_su2_colab.ipynb`: cells in this order, each idempotent:
   a. `nproc`, `free -h`, OS release; clone repo at a given commit; `pip install -e .`.
   b. Download the pinned SU2 release zip (serial and mpi variants), unzip to `/content/su2`,
      record sha256 and `SU2_CFD --help` first lines into `solver_version.txt`.
   c. First light: run the SU2 Tutorials inviscid wedge (`compressible_flow/Inviscid_Wedge`,
      LGPL, downloaded from the su2code/Tutorials repository) for 300 iterations; record wall
      time. Purpose: prove the binary runs; no physics claim.
   d. Our Euler wedge (V1): build mesh, render config, run, run `oblique_shock_check`, print the
      pass/fail table.
   e. Our laminar wedge (V2 timing): run to convergence with the time per iteration logged;
      report seconds per iteration per thousand cells for serial and `mpirun -n 2`; run V2a;
      check the heat-flux sign (integral over `body` positive for the cold wall) and record which
      sign convention this SU2 version uses.
   f. Write the run records to `runs/task1/<case_id>/` as specified in `01_interfaces.md` and
      print the budget estimate: seconds per run for a 25 k cell mesh at the observed iteration
      count, runs per hour, and the gate T1 verdict.
7. `tests/`: see acceptance.

## Acceptance tests (all must pass; Fable runs them on the delivered diff)

Unit tests, no SU2 needed (`pytest -q`):
- `test_shock.py`: oblique(M=2, 10 deg) -> beta 39.3139 deg, p 1.70658, M2 1.64052,
  p0 0.984644; oblique(4, 10 deg) -> beta 22.2341, p 2.50604, rho 1.88528, T 1.32927,
  M2 3.28605, p0 0.925428; oblique(4, 14 deg) -> beta 26.0505, p 3.43347, M2 3.00084;
  oblique(2.5, 20 deg) -> beta 42.8902, p 3.21091; normal(2) -> p0 0.720874, p 4.5, M2 0.57735;
  normal(3.5) -> p0 0.212948; theta_max(2) = 22.974 deg, theta_max(4) = 38.774 deg; all to
  1e-4 relative (angles 1e-3 deg). oblique returns NaN beta beyond theta_max.
- `test_atmosphere.py`: 30 km -> T 226.509, p 1197.03, rho 0.018410 (1e-4), mu 1.4752e-5
  (1e-3), a 301.71 (1e-3).
- `test_structured.py`: stretch functions return N points, first spacing within 1e-9 of d0,
  monotone; a single rectangular block gives N1 x N2 nodes and (N1-1)(N2-1) quads, all
  counter-clockwise, quality min angle 90 deg within 1e-6; two blocks sharing an edge give
  exactly N_shared duplicate-free nodes; `write_su2` then a tiny reader round-trips node count,
  element count and marker line counts; an intentionally inverted cell is reported.
- `test_wedge.py`: medium wedge mesh for theta 10 deg passes the quality gate; first-cell height
  on `body` within 10 percent of 20 micrometres; same params twice give byte-identical
  `mesh.su2` and `case.cfg` (determinism); coarse/medium/fine cell counts scale about 1.96x.
- `test_config.py`: rendered config contains every marker in `mesh_markers.json` and no other;
  `MACH_NUMBER= 4.0`, `FREESTREAM_TEMPERATURE= 226.509`, `REF_DIMENSIONALIZATION= DIMENSIONAL`;
  EULER has `MARKER_EULER` and no `MARKER_ISOTHERMAL`; NAVIER_STOKES has
  `MARKER_ISOTHERMAL= ( body, 300.0 )` and `KIND_TURB_MODEL= NONE`.
- `test_oblique_check.py`: a synthetic volume CSV with an exact analytic oblique shock field
  (p jump across the line y = x tan beta, M = 4, 10 deg, plus 0.3 percent noise) passes V1 with
  the measured beta within 0.2 deg.

Colab acceptance (Éder runs the notebook, Fable reads `runs/task1/`):
- First light completes; version string recorded.
- V1 hard tolerances pass (beta 0.5 deg, p2/p1 and M2 2 percent).
- Laminar wedge converges (status converged or stationary); V2a reported; heat flux sign
  recorded; seconds per iteration per thousand cells recorded for 1 and 2 processes.
- Gate T1 evaluated (`00_decisions.md` 5) and written in the notebook output and in
  `runs/task1/README.md`.

## Not in this task

Inlet geometry, cylinder, metrics, Eckert check (Task 2). No MCP, no queue (Task 3).

## Manual smoke test Éder can do today (before the notebook exists)

On a Colab CPU runtime:
```
!nproc && free -h && head -2 /etc/os-release
!wget -q https://github.com/su2code/SU2/releases/download/v8.2.0/SU2-v8.2.0-linux64.zip
!unzip -q -o SU2-v8.2.0-linux64.zip -d /content/su2 && ls /content/su2/bin
!/content/su2/bin/SU2_CFD --help | head -5
```
If the asset name differs, take the latest `v8.*-linux64.zip` from
https://github.com/su2code/SU2/releases and report the version. If the binary fails to run,
fall back to `pip install condacolab` then `conda install -c conda-forge su2` and report the
version. Report: core count, RAM, SU2 version string, and whether `mpirun` exists
(`!which mpirun`).

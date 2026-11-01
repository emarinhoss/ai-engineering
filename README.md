# ai-engineering

Aero-thermal design of a two-ramp supersonic inlet, using a validated SU2 workflow, a Gaussian-process surrogate with active learning, and a thin agent layer that drives the workflow.

The framing is "a physics-ML engineer who automates his own workflow": the physics and the statistics are the substance, and the agent layer is a convenience over tools that are validated and gated. The problem is a two-dimensional inlet at Mach 4.0 and 30 km for a sub-scale body of about 0.3 m (`docs/specs/00_decisions.md`, section 1), solved as laminar Navier-Stokes in SU2 with an isothermal 300 K wall. The two design variables are the ramp angles theta1 and theta2; the objectives are total pressure recovery to maximise and peak wall heat flux on ramp 2 to minimise, and the output is a Pareto front with uncertainty. The LLM never chooses where to sample next: the surrogate and the acquisition function do.

Plan: [PLAN.md](PLAN.md). Decisions and specs: [docs/specs/](docs/specs/).

## Status (2026-11-01)

- **Code.** Tasks 1 to 5 are on `main`: physics relations and gates, the parametric inlet and cylinder geometry with its mesher, SU2 configs and post-processing, the MCP server and Colab queue worker, the Gaussian-process surrogate with its replay harness, and the Pareto, inverse-query and design-map analysis. Task 6 (agent evaluation) is specified in `docs/specs/task6_agent_eval.md` and has not been run.
- **Official Colab records.** Task 1 is recorded in `runs/task1/` (see `runs/task1/README.md`). The official Task 2 validation batch (10 jobs, `PLAN.md`) and the Task 3 pool (92 runnable points of the 96-point Sobol design, after 4 gate exclusions, `docs/specs/00_decisions.md`, section 2.1) are running on Colab.
- **Validation.** The table below gives the verdicts from `docs/validation/2026-11-01_report.md`. Most rows are **development runs** (`runs/dev/`, SU2 v8.2.0 on the development container); rows marked official come from `runs/task1/`.
- **Not run yet.** The Spalart-Allmaras sensitivity run, the active-learning replay on the official pool, the confirmation run for the inverse query, and the agent fault-injection runs. No result is claimed for any of them.

Verdicts and measured values as reported in `docs/validation/2026-11-01_report.md`. PASS and FAIL are checked against the tolerance, REPORT is informational, and "not run" means the check could not run.

| Check | Type | Verdict | Measured | Records |
|---|---|---|---|---|
| V1 oblique shock, Euler wedge 10 deg | hard | PASS | beta +0.13 deg; p2/p1 -0.12 %; M2 -0.19 % | official, `runs/task1/` |
| V2a laminar plateau pressure vs inviscid | report | REPORT | +1.69 % (expected band 0 to +6 %) | official, `runs/task1/` |
| V2b laminar wedge heat flux vs Eckert, 0.3 <= x/X_w <= 0.9 | hard | PASS | mean 1.60 %, max 1.95 % | development, final numerics |
| V3 cylinder stagnation heating vs Fay-Riddell, fine mesh | hard | PASS | -4.49 % | development, final numerics |
| V3 cylinder grid study, medium to fine | hard | PASS | -3.46 % | development, final numerics |
| V3 cylinder at entropy fix 0.1 (Roe carbuncle) | hard | FAIL | fine mesh +216.84 %; grid study +628.92 % | development, superseded (`runs/dev/2026-11-01_cylinder_v3_attempt1/`) |
| V4e Euler inlet 8/8, throat p0 and Mach | hard | PASS | -0.34 % and -0.14 % | development (`runs/dev/2026-11-01_inlet_design_point/`) |
| V4v laminar inlet 8/8, mid-50 % core p0 | soft | PASS | +0.39 % | development (`runs/dev/2026-11-01_inlet_design_point/`) |
| V4m inlet 8/8 grid study, recovery and peak heat flux, medium to fine | hard | PASS | +0.09 % and -1.68 % | development, final numerics |
| V4m inlet 12/14 corner grid study | hard | not run | diverged on both meshes | development (`runs/dev/2026-11-01_inlet_grid_study_ef03/`) |
| X1 SU2 mass-averaged total pressure vs our mass average, 8/8 runs | hard | PASS | 0.000 % | development, final numerics |
| V3 cylinder stand-off vs Billig | report | not run | no volume output | development |

Read the table with three things in mind:

- The official Task 1 records were run at entropy fix 0.1. The final numerics (Roe, entropy fix 0.3, CFL capped at 20, for every family) were chosen after the V3 failure and are used by every row marked final numerics (`docs/specs/00_decisions.md`, section 6; `runs/dev/2026-11-01_cylinder_v3_attempt3/README.md`).
- The official first-light tutorial step exited with an error and was not repeated; no physics claim depends on it (`runs/task1/README.md`).
- Known limits: within about 30 mm of a sharp leading edge, SU2's wall-node temperature departs from the imposed 300 K, so that region is kept out of both objectives (`runs/dev/2026-11-01_numerics/README.md`). The 26 deg total-turning corner does not converge, so the design box is trimmed to 24 deg total turning (`runs/dev/2026-11-01_inlet_box_diagnostics/README.md`).

## How it works

A design is two numbers, theta1 and theta2. Before anything is written to the queue, a strict schema and the physics gates check it (attached shocks, the 24 deg total-turning limit, the wall-cell Reynolds number, per `docs/specs/00_decisions.md`, sections 2.1 and 6). The numpy structured mesher builds the two-ramp inlet and its cowl, and a mesh-quality gate refuses a bad mesh with the offending value. SU2 configurations are generated from a template, and the MCP server exposes validate, create, submit, status and ingest as typed tools. Jobs travel as small JSON files on a Google Drive queue because Colab cannot accept inbound connections: a Colab worker polls the queue, rebuilds the mesh from the uploaded parameters, checks it against a fingerprint, runs SU2 and writes `result.json` or `error.json`. Post-processing in `postprocess/metrics.py` turns the surface output into the two objectives and cross-checks the recovery against SU2's own total-pressure average.

A Gaussian process (exact, in PyTorch, Matern 5/2 kernel with automatic relevance lengths) is fitted for each objective on the completed runs. Acquisition is Monte-Carlo expected hypervolume improvement, with a max-variance rule as the control. The replay harness compares these with random and Latin hypercube sampling on the same committed pool, over 10 seeds (`PLAN.md`, Task 4), so every strategy sees identical ground truth and no extra CFD is needed. The Pareto front with its posterior band, an inverse query under a heat-flux cap, and design maps are built from the surrogate, and the inverse answer is then checked by a real SU2 run submitted through the MCP tools.

## How to run

### Tests and lint

```
python -m pytest -q     # tests/; the worker tests use a fake solver (tests/fake_su2.py), no SU2 needed
ruff check .
```

### Notebooks

- `notebooks/00_su2_colab.ipynb` (Task 1): clones this repository inside Colab, downloads the SU2 v8.2.0 release binaries from the su2code GitHub releases, checks the version, runs the wedge cases and writes the records to `su2queue/runs/task1/` on Google Drive. The committed copy is `runs/task1/`.
- `notebooks/01_worker_colab.ipynb` (Task 3): mounts Drive, installs SU2 and serves the queue. See "Running the worker" below.

Both notebooks clone this repository, so the commit that created the jobs and the commit the worker runs must match.

### Running the worker

The worker runs in Colab, next to SU2, and polls a Drive folder. It never decides anything about
physics: it rebuilds the mesh and config from the uploaded `params`, checks their sha256 against the
job file, runs SU2 and writes the result. Layout and flags: `docs/specs/01_interfaces.md`.

```
pip install -e .        # at the same commit that created the jobs (the worker compares commits)
python -m worker.run_worker --queue /content/drive/MyDrive/su2queue \
    --su2-cmd "mpirun -n 2 SU2_CFD" --poll 20 --timeout 2400
```

- `jobs/<case_id>.json` is the `job.json` of a staged case (uploaded by Claude). A job is pending
  until `runs/<case_id>/status/` holds `2-done` or `2-failed`; the oldest `created_at` goes first.
- `jobs/<batch_id>.batch.json` holds many jobs in one file (made by the MCP tool `export_batch`); the
  worker handles each entry like a single job file, mixed with single files by `created_at`.
- Done: `runs/<case_id>/result.json` and a copy `runs/<case_id>.result.json`. Failed: `error.json`
  with `reason` in `mesh_mismatch`, `config_mismatch`, `bad_job`, `make_error`, `timeout`,
  `nonzero_exit`, `nan`, `postprocess_error`. Download the right file and hand its text to the MCP
  tools `ingest_result` or `ingest_error`.
- Restart after a crash (Colab runtime reset): start the same command again. A job left at
  `1-running` whose `heartbeat.json` is older than `--stale-minutes` (default 10) is re-run;
  finished jobs are never touched. `Ctrl-C` flags nothing.
- To retry a failed job, delete its `status/2-failed` and `status/1-running` files by hand; the
  worker itself never deletes or moves anything.
- `--once` processes at most one job and exits (tests). One worker per queue folder.
- Tests: `python -m pytest -q tests/test_worker_*.py tests/test_ingest.py` (fake SU2, no SU2 needed).

## Repository layout

- `physics/`: analytic relations (shocks, atmosphere, Eckert, Fay-Riddell) and the physics gates.
- `geometry/`, `cases/`, `postprocess/`: parametric geometry and mesh, SU2 configs, metrics and validation checks.
- `mcp_server/`, `worker/`: the MCP tools and the Colab queue worker.
- `surrogate/`, `analysis/`: models, acquisition and the replay harness; Pareto front and inverse query.
- `notebooks/`: Colab notebooks. `designs/`: committed design tables, including the 96-point Sobol pool. `tests/`: pytest.
- `runs/`: committed run records (inputs, configuration, solver version, history, result). See `runs/README.md`.
- `docs/specs/`: decisions (`00_decisions.md`), interfaces (`01_interfaces.md`) and per-task specs. `docs/validation/`: generated validation reports. `docs/transcripts/`: recorded agent sessions.

## Honesty rules

Every number, plot and claim in the docs or slides must come from a run recorded in `runs/`, and anything not yet run is said to be not yet run. Validation against analytic cases comes before any machine learning, and a failed check is reported rather than tuned away: the cylinder failure at entropy fix 0.1 stays in `runs/dev/` beside the change that fixed it. Active learning is compared with random and Latin hypercube sampling on the same pool, and the comparison is reported whether or not active learning wins. Only converged and stationary runs train the surrogate (`docs/specs/00_decisions.md`, section 6). Only open data and open solvers are used, and no secrets or personal data are committed.

## Licence

The code in this repository is the author's. The repository does not yet contain a licence file for that code. SU2 is licensed under the LGPL and is not vendored here: the notebooks download the SU2 release binaries at run time from the su2code GitHub releases, and the tutorial case from su2code/Tutorials.

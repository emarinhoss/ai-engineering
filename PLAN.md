# Plan: Aero-thermal inlet design with an active-learning surrogate and an automation layer

Interview talk: Friday 2026-11-13, one hour, open topic, slides and results only.
Audience: AI Engineering Manager; Lead ML & AI Orchestration Engineer; Staff Engineer, Thermal,
HVAC and Fluids; Senior Aerodynamics Engineer.
Planning started 2026-11-01 (Day 1). Day 12 is 2026-11-12. Nov 13 is the talk.

## Framing

"A physics-ML engineer who automates his own workflow." The physics and the statistics are the
substance. The agent layer (Claude Code driving an MCP server) is a thin convenience layer on top
of tools that are validated and gated. The LLM never decides where to sample next; the surrogate
and acquisition function do, deterministically and auditably.

## Problem

- 2D two-ramp external-compression inlet with a cowl, laminar Navier-Stokes in SU2, isothermal
  wall at 300 K. Mach 4.0, US Standard Atmosphere at 30 km, sub-scale body of about 0.3 m
  (Re about 5e5, laminar defensible). Decided in Task 0; see `docs/specs/00_decisions.md`.
- Design variables: 2, the ramp angles theta1 in [5, 12] deg and theta2 in [5, 14] deg. The
  cowl lip sits at the inviscid shock-on-lip point, so the geometry follows from the angles.
  Cowl position and wall temperature are not design variables (reasons in the decisions file).
- Objectives: maximize total pressure recovery at the throat including a terminal normal shock
  per streamtube; minimize peak wall heat flux on ramp 2 (including the duct wall). Exact
  definitions in `docs/specs/00_decisions.md` section 3. Output: a Pareto front with uncertainty.
- Validation cases: V1 oblique shock (Euler wedge), V2 laminar wedge pressure and Eckert
  flat-plate heating, V3 Fay-Riddell stagnation heating on a 10 mm cylinder with a grid study,
  V4 inlet design point (Euler and laminar) with a grid study.
- Stretch (only if Days 7-8 finish early): multi-fidelity, with cheap analytic or inviscid
  estimates as the low-fidelity model and Navier-Stokes as the high-fidelity model.

## Constraints and decisions

- Compute: Google Colab only. CPU for SU2 (expect about 2 cores), GPU for the surrogate.
- ML stack: PyTorch (BoTorch/GPyTorch allowed for acquisition if they save time).
- Agent layer: Claude Code only (no API key). The MCP server runs where Claude Code runs.
- Colab bridge: Colab cannot accept inbound connections. Jobs go through a queue folder on Google
  Drive. A Colab worker polls the queue, runs SU2, and writes results back. The worker
  checkpoints so a disconnect loses at most one run.
- Public repo: open data and open solvers only. No AFRL, RAND, ERC or Anduril material, no
  non-public data of any kind.
- Builder split: Claude writes code and tests; Éder runs SU2 on Colab and owns the physics and ML
  choices he will defend. Every module must be simple enough for Éder to explain line by line.

## Model allocation

Fable 5.1 orchestrates. For each task it writes a spec and a pass/fail acceptance test; a cheaper
model implements; Fable reviews the diff against the spec before merging.

| Model | Use for | Do not use for |
|---|---|---|
| Fable 5.1 | Architecture, experiment design, numerics and physics judgment, tolerances, diff review against the spec, interpreting results, talk narrative, final adversarial review | Boilerplate, bulk edits |
| Sonnet 5.5 | Implementing modules from specs: mesh generator, config templating, MCP server, queue worker, surrogate and active-learning code, tests | Choosing boundary conditions or validation tolerances |
| Haiku 5.5 | README and docstrings, plotting scripts, log parsing, schema definitions, lint and test runs, slide text drafts, renames and formatting | Anything where a wrong number can pass silently (BCs, mesh, units, metrics) |

Rule: anything where an error can pass silently stays with Fable, or gets Fable review before it
is used. Haiku gets only mechanical work with a visible failure mode.

## Schedule and tasks

Each task lists owner model, deliverable, and acceptance test. Tolerances are final as of Task 0
(2026-11-01); the full table with hard/soft/report types is `docs/specs/00_decisions.md`
section 5 and the per-task specs are in `docs/specs/`.

### Task 0 (Day 1, Fable 5.1): review this plan

- Check the physics: is laminar acceptable for the chosen Mach/Re, what wall BC, what geometry
  family, which 2 to 4 design variables, which Mach number and flight condition.
- Replace every "(proposed)" tolerance with a justified one.
- Write per-task specs in `docs/specs/` for Tasks 1 to 5 before any code is written.
- Done when: `docs/specs/` exists and the tolerances below are final.
- Status 2026-11-01: done and confirmed by Éder (Mach 4, laminar, 300 K wall, two variables,
  objective definitions).

### Task 1 (Days 1-2): SU2 on Colab and timing (Sonnet 5.5 implements, Fable reviews)

- Deliverable: `notebooks/00_su2_colab.ipynb` installs a pinned SU2 v8 binary, runs the SU2
  tutorial wedge (first light), then our own Euler and laminar wedge from the new `physics/`,
  `geometry/structured.py`, `geometry/wedge.py`, `cases/config.py` modules, and records wall
  time, residual history and outputs. Spec: `docs/specs/task1_su2_colab_timing.md`.
- Acceptance: one laminar case completes; seconds per iteration per thousand cells recorded for
  1 and 2 processes; run budget computed. Gate T1: medium-mesh production run <= 5 min on
  2 cores means go with a 96-point pool; 5 to 10 min means pool 64 and Colab Pro; > 10 min
  means the coarse mesh becomes production (design space stays at 2 variables).
- Acceptance (physics, final): Euler wedge at 10 deg, shock angle within 0.5 deg and p2/p1 and
  M2 within 2% of the oblique-shock relation (V1, hard). Laminar plateau pressure 0 to 6%
  above inviscid (V2a, report). Heat flux sign convention recorded.

### Task 2 (Days 3-4): geometry, mesh, config, post-processing (Sonnet 5.5; Fable reviews BCs and metrics)

- Deliverable: `geometry/` parametric two-ramp inlet and cylinder on a numpy structured
  multi-block mesher writing SU2 format (gmsh dropped: simpler to explain, deterministic,
  quality metrics for free); `cases/` SU2 config templating from a parameter dict;
  `postprocess/` metrics for recovery and peak heat flux with units and sign checked, plus the
  validation checks and report. Spec: `docs/specs/task2_geometry_mesh_config_postprocess.md`.
- Acceptance: a unit test for each function; mesh-quality gate (min angle, aspect ratio, first
  cell height / y+) rejects bad meshes with a clear error; same input gives same mesh and
  config (deterministic).
- Validation (final): laminar wedge heating within 10% mean (15% max) of the Eckert
  flat-plate reference (V2b, hard); cylinder stagnation heating within 15% of Fay-Riddell on
  the fine mesh with medium-to-fine change <= 5% (V3, hard); Euler inlet throat p0 and Mach
  within 2% of the two-shock relations (V4e, hard); laminar inlet core p0 within 5% (V4v,
  soft, explained); inlet grid study medium-to-fine change <= 2% in recovery and <= 5% in
  peak heat flux (V4m, hard); SU2's own mass-averaged total pressure agrees with ours within
  0.5% on every run (X1, hard). Nine Colab runs.

### Task 3 (Days 5-6): MCP server, queue worker, first batch (Sonnet 5.5; Haiku for schemas and docs)

- Deliverable: `mcp_server/` exposing `create_case`, `validate_config`, `submit`, `status`,
  `postprocess`, `list_results`, `queue_batch`; strict pydantic schemas and physics gates;
  `worker/` Colab queue worker with restart-safe claim and status flags on a Google Drive
  folder; the 96-point scrambled Sobol pool (`designs/pool_sobol96.csv`, run in sequence order
  so any prefix is usable, 64 minimum) queued and run overnight.
  Spec: `docs/specs/task3_mcp_server_queue_worker.md`.
- Acceptance: Claude Code can create, submit and retrieve one case end to end through the MCP
  tools; invalid parameters are rejected before submit; a killed worker resumes without
  duplicating or losing completed runs; every run records inputs, solver version, and logs.

### Task 4 (Days 7-8): surrogate and active learning (Sonnet 5.5 implements; Fable designs experiment and reviews)

- Deliverable: `surrogate/` exact Gaussian process per objective in pure PyTorch (Matern 5/2
  ARD, marginal-likelihood fit, under 150 lines), Monte-Carlo expected hypervolume improvement
  and a max-variance variant; an offline pool-based replay harness that compares `al_ehvi`,
  `al_maxvar`, `random` and `lhs` on the same pool with 10 seeds, reporting held-out error,
  hypervolume regret and interval coverage versus number of runs.
  Spec: `docs/specs/task4_surrogate_active_learning.md`.
- Acceptance: error vs number of simulations is plotted for all three strategies with several
  seeds; calibration plot (predicted interval coverage) produced. Gate: if active learning does
  not beat the baselines, report that honestly and investigate; do not tune until it does.

### Task 5 (Day 9): Pareto front, UQ, inverse query (Fable 5.1 interprets; Haiku plots)

- Deliverable: Pareto front with uncertainty (observed points, predicted front, posterior
  band, discretisation error bar); one inverse-design query ("maximum recovery under a
  heat-flux cap", cap at the 40th percentile of pool heating) answered by the surrogate and
  then confirmed with a real SU2 run submitted through the MCP tools; design maps over the box.
  Spec: `docs/specs/task5_pareto_uq_inverse.md`.
- Acceptance: the confirmation run falls inside the predicted interval, or the miss is
  documented and explained.

### Task 6 (Day 10): agent layer evaluation (Sonnet 5.5 builds the fault injection; Fable reviews)

- Deliverable: full Claude Code transcripts driving the MCP tools; injected faults (solver
  divergence, bad mesh, malformed config) and what caught each.
- Acceptance: at least one real failure documented with root cause and guard. Claims about the
  agent stay modest: tools plus gates plus logs.

### Task 7 (Day 11): deck (Fable 5.1 narrative; Haiku drafts text and figures)

Proposed structure for 60 minutes (about 40 talk, 20 discussion):

1. Problem and why it matters (5 min).
2. Physics setup and validation (10 min).
3. Automation layer: MCP tools, gates, queue (8 min).
4. Surrogate, active learning, UQ (12 min).
5. Results, Pareto front, inverse query (8 min).
6. What failed, limits, next steps (5 min).
7. Discussion (about 20 min); keep backup slides for fidelity questions (turbulence model, wall
   BC, mesh convergence).

### Task 8 (Day 12): rehearsal and buffer

- Time the talk; rehearse answers to likely questions from the aerodynamics and thermal
  engineers; fix figures. No new features.

## Risks

- Fidelity questions from the aero and thermal engineers: have clear answers and state limits
  openly. A defensible simple model beats an impressive untrusted one.
- Shock-resolved meshes under parametric geometry changes: keep the geometry family simple; the
  mesh-quality gate is mandatory.
- Colab limits: sessions disconnect and have usage caps; queue plus checkpointing is required.
  A cheap paid tier is an option if run budget is the bottleneck.
- Run budget: about 120 runs are needed (96 pool, about 20 validation and grid study, 3
  confirmation). If runs are slow the pool shrinks to 64 and the coarse mesh may become
  production; the validation work is never reduced. Colab Pro (more CPU cores) is the cheap
  fix if gate T1 fails.
- Colab free tier stops when the browser disconnects: overnight batches need an open tab on a
  machine that does not sleep, or Colab Pro. The worker is restart-safe either way.
- Laminar separation at the compression corner for theta2 above about 10 deg may converge
  slowly or not at all: such runs are recorded with their status and reported as a limit of the
  laminar model, not tuned away.
- Scope creep: multi-fidelity and extra geometries are cut first.

## Cut order if time runs short

1. Multi-fidelity stretch.
2. Second geometry family.
3. Inverse-design query (keep the Pareto front).
4. Fault-injection breadth (keep one documented real failure).

Never cut: validation against analytic cases, the active learning vs baseline comparison, and
the calibration plot.

## Change log

### 2026-11-01, Task 0 (Fable 5.1)

1. Flight condition fixed: Mach 4.0, 30 km standard atmosphere, sub-scale body about 0.3 m,
   laminar (Re <= 5e5), isothermal wall 300 K. Mach 5 rejected because the two-ramp family
   then gives recovery of only 0.13 to 0.25 and harsher laminar separation; Mach 4 gives 0.24
   to 0.43 with T0 = 951 K (perfect gas accurate).
2. Design variables fixed at two (theta1, theta2) with the shock-on-lip rule for the cowl lip.
   Cowl position was dropped because with these two objectives it is degenerate (spillage is
   free, ingestion costs); wall temperature was dropped as a design variable.
3. Objective definitions made exact (recovery includes the terminal normal shock per
   streamtube; peak heat flux is on ramp 2 including the duct wall, sharp leading edges
   excluded because their computed peak is a mesh artefact).
4. All "(proposed)" tolerances replaced by the table in `docs/specs/00_decisions.md` section 5,
   with hard/soft/report types; grid-convergence requirements and an Eckert flat-plate heating
   check added; a cross-check of our mass average against SU2's `AVG_TOTALPRESS` added.
5. Mesh generator changed from gmsh to a numpy structured multi-block writer.
6. Active learning versus baselines defined as a pool-based offline replay on a committed
   Sobol pool (identical ground truth, no extra CFD).
7. Layout additions: `physics/`, `analysis/`, `designs/`, `runs/`, `tests/`, `docs/validation/`.
8. Task 1 scope grew to include the analytic module, the mesher core and the wedge, because
   the timing case needs our own mesh; Task 2 scope is the inlet, the cylinder, metrics and
   the validation suite.

### 2026-11-01, Day 1 status (Fable 5.1)

Far ahead of the schedule: the code of Tasks 1 to 4 is implemented, reviewed and on `main`
(236 tests). SU2 v8.2.0 runs both on Colab and on the Fable cloud container, which allowed the
numerics and validation work to be done on Day 1 instead of Days 2 to 4.

- Task 1 done: Colab records in `runs/task1/` (V1 PASS, laminar wedge converged, heat flux sign
  positive into the wall, gate T1 GO: about 4 minutes per medium inlet run on Colab).
- Numerics changed twice on evidence (`docs/specs/00_decisions.md` section 6, `runs/dev/`):
  AUSM+-up2 diverged or stalled, Roe with entropy fix 0.1 converged on the wedge and inlet but
  gave Roe's carbuncle on the cylinder; entropy fix 0.3 cures it (Fay-Riddell within 0.3, 1.1
  and 4.5 percent on three meshes) at a cost of 0.9 percent on flat-plate heating. Final:
  Roe, entropy fix 0.3, CFL adapt capped at 20, for every family.
- Validation on development runs at the final numerics (official Colab records pending): V1,
  V2a, V2b (0.75 percent), V3 with grid study, V4e, V4v, V4m (recovery +0.09 percent, peak
  heating -1.7 percent medium to fine) all pass; the superseded entropy-fix-0.1 cylinder runs
  stay in the report as FAIL rows; report in `docs/validation/2026-11-01_report.md`.
- Design box trimmed: total turning <= 24 deg (gate 4). The 12/14 corner (26 deg) diverges on
  two meshes and two CFL caps; 12/12, 8/14 and 5/14 converge. 4 of 96 pool points excluded.
- Queue transport is the Google Drive connector of the Claude Code cloud session (jobs and
  results as small JSON files; the Colab worker regenerates meshes and verifies a
  rounded-coordinate fingerprint, because byte hashes differ across platforms).
- Official validation batch done on Colab (8 vCPU runtime, 4 MPI ranks) and ingested through
  the MCP tools into `runs/val/`: 8 converged records plus the 2 expected 12/14 failures
  (`error.json`, SU2 exit code 1). From those records (`docs/validation/2026-11-01_colab_records.md`):
  V3 fine mesh -4.5 percent from Fay-Riddell (PASS, grid change -3.5 percent), V4m +0.09 /
  -1.68 percent (PASS), V4e metrics form -0.31 percent, X1 at 1e-6. V1/V2a/V2b official rows stay
  with `runs/task1/` and the development report (surface files stay on Drive).
- Task 6 fault matrix done early (`docs/faults/`, 11 faults, no SU2 needed); the fake solver now
  writes a consistent surface on the mesh, and a diverged surface file reads "solution diverged"
  instead of "check the units". 265 tests.
- Pool: 92 jobs running on Colab since 18:23 UTC at about 4.4 minutes per point (4 ranks);
  results are ingested in batches into `runs/pool/`. Task 4 replay runs at 64 pool points.
- Pool job inlet2r-db92dcf68d was refused by the worker (`config_mismatch`): the geometry
  comment line of case.cfg had `h_duct` differing in its last digit (3e-18) between the container
  and Colab, the lines SU2 reads were identical. Fix on main: `config_sha256` hashes only the
  lines SU2 reads; the worker and ingest also accept the older whole-file hash. By 20:30 UTC
  the worker had refused about 62 of the 92 pool jobs for this reason (last-digit float
  differences in the geometry comment are common, not rare) and finished 37. Operator step:
  restart the Colab worker cell on the new main; its command now carries
  `--retry-reason config_mismatch`, so the refused jobs are re-run without touching Drive.
- Transfer integrity: a Haiku agent retyping base64 altered 2 of 4 result files (one mixed the
  fields of two records). The worker now writes a sha256 digest next to every result and failure
  (back-filled at start-up) and ingest refuses a text that does not match it. The 16 pool and
  13 validation records ingested before digests existed are to be re-checked against the
  back-filled digests after the restart (to do; the integrity checks they passed cover case id,
  mesh fingerprint and config hash, not every digit of the metrics).

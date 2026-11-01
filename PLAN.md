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

- 2D supersonic inlet / ramp, viscous (laminar or RANS Navier-Stokes) in SU2, with an isothermal
  wall boundary condition so wall heat flux is meaningful.
- Design variables: 2 to 4 (e.g. ramp angle(s), cowl position, wall temperature). Decide after the
  timing test (Task 1).
- Objectives: maximize total pressure recovery; minimize peak wall heat flux. Output: a Pareto
  front with uncertainty.
- Validation cases: oblique-shock relations (inlet); Fay-Riddell stagnation heating on a blunt
  edge.
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

Each task lists owner model, deliverable, and acceptance test. Tolerances marked (proposed) are
first guesses; Task 0 confirms or replaces them.

### Task 0 (Day 1, Fable 5.1): review this plan

- Check the physics: is laminar acceptable for the chosen Mach/Re, what wall BC, what geometry
  family, which 2 to 4 design variables, which Mach number and flight condition.
- Replace every "(proposed)" tolerance with a justified one.
- Write per-task specs in `docs/specs/` for Tasks 1 to 5 before any code is written.
- Done when: `docs/specs/` exists and the tolerances below are final.

### Task 1 (Days 1-2): SU2 on Colab and timing (Sonnet 5.5 implements, Fable reviews)

- Deliverable: `notebooks/00_su2_colab.ipynb` installs SU2, runs one ramp case headless, and
  records wall time, residual history and outputs.
- Acceptance: one laminar case completes; wall time recorded; run budget computed (runs per
  hour on Colab). Gate: if a run takes more than about 5 minutes, shrink the design space to 2
  to 3 variables and/or coarsen the mesh before continuing.
- Acceptance (physics, proposed): shock angle and post-shock pressure ratio within 3% of the
  oblique-shock relation for the inviscid-dominated region.

### Task 2 (Days 3-4): geometry, mesh, config, post-processing (Sonnet 5.5; Fable reviews BCs and metrics)

- Deliverable: `geometry/` parametric ramp/inlet and gmsh mesh generator; `cases/` SU2
  config templating from a parameter dict; `postprocess/` functions for total pressure recovery
  and peak wall heat flux, with units checked.
- Acceptance: a unit test for each function; mesh-quality gate (min angle, aspect ratio, first
  cell height / y+) rejects bad meshes with a clear error; same input gives same mesh and
  config (deterministic).
- Validation: blunt-edge stagnation heating within about 20% of Fay-Riddell (proposed; the
  correlation itself has uncertainty); inlet recovery against the oblique-shock/normal-shock
  estimate (proposed 5%).

### Task 3 (Days 5-6): MCP server, queue worker, first batch (Sonnet 5.5; Haiku for schemas and docs)

- Deliverable: `mcp_server/` exposing `create_case`, `validate_config`, `submit`, `status`,
  `postprocess`, `list_results`; strict JSON schemas; `worker/` Colab queue worker with
  checkpointing; first space-filling design (Latin hypercube or Sobol) queued and run overnight.
- Acceptance: Claude Code can create, submit and retrieve one case end to end through the MCP
  tools; invalid parameters are rejected before submit; a killed worker resumes without
  duplicating or losing completed runs; every run records inputs, solver version, and logs.

### Task 4 (Days 7-8): surrogate and active learning (Sonnet 5.5 implements; Fable designs experiment and reviews)

- Deliverable: `surrogate/` PyTorch ensemble or GP with calibrated uncertainty; multi-objective
  acquisition (e.g. expected hypervolume improvement); an offline replay harness that compares
  active learning, random and LHS sampling on the same run budget.
- Acceptance: error vs number of simulations is plotted for all three strategies with several
  seeds; calibration plot (predicted interval coverage) produced. Gate: if active learning does
  not beat the baselines, report that honestly and investigate; do not tune until it does.

### Task 5 (Day 9): Pareto front, UQ, inverse query (Fable 5.1 interprets; Haiku plots)

- Deliverable: Pareto front with uncertainty; one inverse-design query ("minimum recovery loss
  under a heat-flux cap") answered by the surrogate and then confirmed with a real SU2 run.
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
- Run budget: if runs are slow there will be fewer than about 150 total; reduce the number of
  design variables rather than the validation work.
- Scope creep: multi-fidelity and extra geometries are cut first.

## Cut order if time runs short

1. Multi-fidelity stretch.
2. Second geometry family.
3. Inverse-design query (keep the Pareto front).
4. Fault-injection breadth (keep one documented real failure).

Never cut: validation against analytic cases, the active learning vs baseline comparison, and
the calibration plot.

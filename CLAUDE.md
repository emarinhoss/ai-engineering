# Repository guide for Claude

Read `PLAN.md` first. It holds the problem, schedule, per-task acceptance tests and model
allocation. Task 0 (review the plan and write `docs/specs/`) comes before any code.

## Rules

- Public repo. Use only open data and open solvers. Never add material from AFRL, ERC, RAND,
  Anduril, or any non-public source. Do not commit secrets, tokens or personal data.
- Never invent results. Every number, plot or claim in docs or slides must come from a run
  recorded in this repo. If something was not run, say so.
- Validation against analytic cases (oblique shock, Fay-Riddell) comes before any ML. A failed
  validation is reported, not tuned away.
- Report active learning vs random/LHS honestly, including if active learning does not win.
- Code must be simple enough for Éder to explain line by line in the interview. Prefer clear
  over clever; avoid heavy frameworks where a short function does the job.
- The LLM never chooses sampling points. The surrogate and acquisition function do.
- Gate bad inputs before submit: strict schemas, mesh-quality checks, config validation.
- Every run records inputs, solver version, seed and logs, and must be reproducible.

## Model allocation

- Fable 5.1: architecture, tolerances, numerics and physics judgment, diff review, narrative.
- Sonnet 5.5: implement modules from specs, tests.
- Haiku 5.5: docs, plotting, log parsing, schemas, lint, formatting, slide text drafts.
- Anything where a wrong number can pass silently stays with Fable or gets Fable review.

## Environment

- Colab runs SU2 (CPU) and trains the surrogate (GPU). Jobs reach Colab through a Google Drive
  queue folder polled by a worker; Colab cannot take inbound connections.
- Agent layer is Claude Code only (no API key).
- Commit to `main` with clear messages. Commit only when asked.

## Layout (created as tasks land)

- `geometry/`, `cases/`, `postprocess/`: parametric geometry, mesh, SU2 configs, metrics.
- `mcp_server/`, `worker/`: MCP tools and the Colab queue worker.
- `surrogate/`: models, acquisition, replay harness.
- `notebooks/`: Colab notebooks.
- `docs/specs/`: per-task specs written in Task 0.

# Task 3 spec: MCP server, Colab queue worker, pool batch (Days 5-6)

Implements: Sonnet 5.5 (server, worker, fake-SU2 tests). Haiku 5.5 (pydantic schema module from
the table in `01_interfaces.md` with its bounds test; README section "Running the worker";
`designs/` CSV writer). Fable 5.1 reviews the gate order, the claim/resume logic and the
batch before it is queued. Runs: Éder starts the worker in Colab and leaves it polling.
Depends on: `01_interfaces.md` (job layout, run record, API), Tasks 1 and 2 code.

## Design

- Transport is the Google Drive connector of the Claude Code cloud session (decided
  2026-11-01; see `01_interfaces.md` "Queue transport"). The MCP server writes a local staging
  job and the small `job.json` is uploaded by Claude; the Colab worker regenerates mesh and
  config from params at the same commit, verifies `mesh_fingerprint`, runs SU2 and writes results to
  `su2queue/runs/`. No API tokens, no secrets. The MCP server never runs SU2; the worker never
  decides anything about physics. The MCP server is registered for the cloud session through
  a committed `.mcp.json` (stdio, `python -m mcp_server`).
- MCP server: Python `mcp` (FastMCP) over stdio, registered in Claude Code with
  `claude mcp add su2 -- python -m mcp_server`. Tools return JSON text. Tools:
  - `validate_config(params) -> {ok, stage, errors, warnings, geometry?, mesh_quality?}`:
    runs schema -> physics gates -> geometry -> mesh -> mesh-quality gate -> config render ->
    key check, in that order, stopping at the first failing stage. Writes nothing.
  - `create_case(params) -> {ok, case_id, path, mesh_quality, warnings}`: same pipeline, then
    writes the job directory with status `0-created`. Refuses to overwrite an existing
    case_id unless `force=true` and the existing status is created or failed.
  - `submit(case_id) -> {ok, status}`: `0-created` -> `1-pending`.
  - `status(case_id=None) -> [{case_id, status, iterations, elapsed_s, last_rms_rho}]` from
    flag files, heartbeat and the tail of `history.csv`.
  - `postprocess(case_id, recompute=false) -> result.json content`, computing it with
    `postprocess.metrics` if missing or asked; copies the committed subset to `runs/<tag>/`.
  - `list_results(tag=None, status=None) -> table` (case_id, theta1, theta2, status,
    recovery_total, q_peak, wall_time_s).
  - `queue_batch(design_csv, tag, mesh_level) -> [case_ids]`: create and submit every row
    (theta1_deg, theta2_deg) in order; stops at the first failing row and reports it.
  - `record_transfer(case_id, direction, drive_file_id, sha256)`: logs an upload or download
    done through the connector so the audit trail is complete.
  - `ingest_result(case_id, result_json_text)`: validates the downloaded result against the run
    record schema, checks `mesh_fingerprint` and `case_id` match the staged job, stores it, and
    copies the committed subset to `runs/<tag>/`.
  Every tool call appends one line to `$SU2_QUEUE_DIR/mcp_log.jsonl` (time, tool, args hash,
  outcome) so Task 6 has an audit trail.
- Worker `worker/run_worker.py --queue /content/drive/MyDrive/su2queue --su2-cmd "mpirun -n 2
  SU2_CFD" --poll 20 --timeout 2400`:
  1. On start: write `worker/heartbeat.json`; scan `jobs/*.json`; a job whose run directory has
     `1-running` but a heartbeat older than 10 minutes is a crash victim and is re-run
     (outputs overwritten).
  2. Loop: pick the oldest pending job (by created_at in the job file); create
     `runs/<case_id>/`, flag `0-seen`; regenerate mesh and config from params at the current
     commit, compare sha256 with the job file (mismatch -> `2-failed`, reason mesh_mismatch);
     flag `1-running`.
  3. Run SU2 in the run directory with a timeout; stream stdout to `log.txt`; heartbeat every
     30 s with the latest iteration parsed from `history.csv`.
  4. On exit: `postprocess.history.summarize` and `postprocess.metrics.compute`; write
     `result.json`, `solver_version.txt`, copy `result.json` to `runs/<case_id>.result.json`;
     flag `2-done`, or `2-failed` with `error.json` {reason: timeout|nonzero_exit|nan|
     mesh_mismatch|postprocess_error, detail}. Call `os.sync()`.
  5. Never deletes, never moves, idempotent on re-run. One worker at a time.
- Pool design: `designs/make_pool.py` writes `designs/pool_sobol96.csv` (scipy Sobol, d = 2,
  scrambled, seed 0, first 96 points scaled to the box, columns index, theta1_deg,
  theta2_deg) and commits it. The batch is queued in index order.

## Acceptance tests

Unit and integration tests without SU2 (`tests/fake_su2.py` is a script that reads a config,
writes a plausible `history.csv` and `surface_flow.dat` (Tecplot ASCII) with an analytic
field, sleeps a configurable time, and can be told to exit non-zero, emit NaN, or hang):
- `test_schemas.py` (Haiku): every bound in the `01_interfaces.md` table accepted at the
  bound and rejected just outside; unknown field rejected; `case_id` stable across key order.
- `test_pipeline_order.py`: `validate_config` with a schema error reports stage "schema" and
  does not build a mesh (mesher patched to raise); with a gate error reports stage "gates";
  with a forced inverted cell reports stage "mesh_quality" and the offending value.
- `test_mcp_tools.py`: through the FastMCP in-process client: `create_case` then `submit`
  then `status` shows pending; `create_case` twice without force errors; `queue_batch` on a
  3-row CSV creates 3 pending jobs in order; `list_results` on an empty queue returns [].
- `test_worker_end_to_end.py`: worker with fake SU2 on a temp queue finishes one job with
  `4-done`, a complete `result.json`, `solver_version.txt`, and the committed subset copied.
- `test_worker_resume.py`: start a job with a slow fake SU2, kill the worker process mid-run,
  restart it with the same queue: the job is re-run once (not twice), completed jobs are not
  touched (their `result.json` mtime unchanged), no duplicate outputs.
- `test_worker_failures.py`: timeout -> `4-failed` reason timeout; non-zero exit -> reason
  nonzero_exit; NaN residual -> reason nan and `convergence.status == diverged`.
- `test_pool.py`: `pool_sobol96.csv` has 96 unique rows inside the box, regenerating with the
  same seed is identical, the first 64 rows are a balanced Sobol prefix (each quarter of the
  box holds 16 points).

Colab and desktop acceptance:
- Éder, from Claude Code on his machine: `validate_config` -> `create_case` -> `submit` ->
  (worker in Colab) -> `status` -> `postprocess` -> `list_results` for the 8/8 design, end to
  end, with the transcript saved to `docs/transcripts/task3_first_case.md`.
- Invalid parameters (theta2 = 20) are rejected before anything is written.
- Pool batch queued; by Day 7 morning at least 64 pool runs are `4-done` with status converged
  or stationary; failed ones are listed with reasons (they are results too).

## Risks and mitigations

- Drive sync latency (tens of seconds) is fine for a 5 minute job cadence; the worker tolerates
  partially synced directories by requiring `job.json` and `case.cfg` to exist and the status
  flag `1-pending` to be at least 10 s old before claiming.
- Colab free tier stops the runtime when the browser disconnects for long. Éder keeps the tab
  open on a machine that does not sleep, or uses Colab Pro; the worker is restart-safe either
  way and a restart loses at most the running job.

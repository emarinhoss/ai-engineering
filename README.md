# ai-engineering

Aero-thermal supersonic inlet design with a physics-informed active-learning surrogate and a thin
agent-automation layer. Built in two weeks as the subject of an interview talk (2026-11-13).

- Solver: SU2 (open source), run on Google Colab.
- Surrogate: PyTorch, with calibrated uncertainty and multi-objective active learning.
- Automation: an MCP server that Claude Code drives, plus a Colab queue worker.
- Plan: see [PLAN.md](PLAN.md). Decisions and specs: [docs/specs/](docs/specs/).

Status: Task 0 done (plan reviewed, specs written). No code, no runs, no results yet.

## Running the worker

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

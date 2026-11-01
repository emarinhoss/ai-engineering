# First live MCP call from Claude Code (2026-11-01)

Context: the repository's `.mcp.json` registers `python -m mcp_server` (stdio) with
`SU2_QUEUE_DIR=./su2queue_local`. In the Claude Code cloud session the tools appeared as
`mcp__su2__{validate_config, create_case, submit, status, postprocess, list_results,
queue_batch, export_batch, record_transfer, ingest_result, ingest_error}`.

Call: `list_results(tag="val")`.

Result (verbatim, reformatted): ten rows, all `status: pending`, metrics null (no results ingested
yet): cylinder-941780775b, cylinder-fd9d9778c5, cylinder-854aee41c4 (theta null, family cylinder);
wedge-b39d378f9c (theta1 10.0); inlet2r-619144f64c, -bb81bb26f0, -d4d29884be, -5e844a838c
(theta 8/8); inlet2r-20b8dcc9ec, -dbccca19df (theta 12/14, staged before gate 4 was trimmed to
24 deg; kept as a recorded failure case).

What this shows for Task 6: the LLM reads the queue through a typed tool; it did not choose any
sampling point (the ten jobs were defined by the validation plan and the pool by a Sobol design);
the tool answered from flag files and result.json only. Earlier the same session staged these jobs
by calling the queue functions directly (same code path as the tools) and the four pool batch
files through `queue_batch` and `export_batch`; every transfer to Drive is in
`su2queue_local/mcp_log.jsonl` (316 lines at this point, not committed: it contains local paths).

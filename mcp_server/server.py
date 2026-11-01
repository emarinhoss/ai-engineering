"""FastMCP server "su2": tools that stage SU2 jobs. Run with `python -m mcp_server` (stdio).

The server never runs SU2 and never chooses sampling points; it checks, builds and stages
jobs under $SU2_QUEUE_DIR and logs every call to mcp_log.jsonl. Tools return JSON text.
(mcp 2.x calls the class MCPServer; in mcp 1.x the same thing is mcp.server.fastmcp.FastMCP.)

TODO (not in this half of Task 3; they need postprocess.metrics and the worker):
  - postprocess(case_id, recompute=False): compute result.json, copy the committed subset to runs/.
  - ingest_result(case_id, result_json_text): validate against the run record, check case_id
    and mesh_sha256 against the staged job, store it, copy the committed subset to runs/<tag>/.
  - status(): iterations, elapsed_s, last_rms_rho from heartbeat.json and history.csv.
  - the Colab worker (worker/run_worker.py) and its fault-injection tests (fake SU2).
  - fold mcp_server.queue.build_case into worker.make_case.make.
"""
import json

from mcp.server.mcpserver import MCPServer

from mcp_server import queue

mcp = MCPServer("su2")


def _json(obj):
    return json.dumps(obj, sort_keys=True)


@mcp.tool()
def validate_config(params: dict) -> str:
    """Check case parameters through schema, physics gates, mesh and config; writes nothing,
    never runs SU2. Returns ok, the failing stage (schema, gates, geometry, mesh_quality,
    config, config_keys), errors and warnings."""
    return _json(queue.validate_only(params))


@mcp.tool()
def create_case(params: dict, force: bool = False) -> str:
    """Validate the parameters and stage a job directory with status created; refuses bad input
    and existing case_ids (force replaces a created or failed one). Never runs SU2 and never
    chooses sampling points: the caller supplies the parameters."""
    return _json(queue.create(params, force=force))


@mcp.tool()
def submit(case_id: str, force: bool = False) -> str:
    """Mark a created job as pending so it can be uploaded to the worker's Drive queue.
    It does not upload anything and never runs SU2."""
    return _json(queue.submit(case_id, force=force))


@mcp.tool()
def status(case_id: str | None = None) -> str:
    """List staged jobs (or one) with their status from the flag files."""
    return _json(queue.status(case_id))


@mcp.tool()
def list_results(tag: str | None = None, status: str | None = None) -> str:
    """Table of staged jobs with metrics from result.json where available (null otherwise),
    optionally filtered by tag or status."""
    return _json(queue.list_results(tag=tag, status=status))


@mcp.tool()
def queue_batch(design_csv: str, tag: str, mesh_level: str = "medium") -> str:
    """Create and submit one inlet2r job per row (theta1_deg, theta2_deg) of a committed design
    CSV, in file order, stopping at the first failing row. Never chooses the points itself."""
    return _json(queue.queue_batch(design_csv, tag, mesh_level))


@mcp.tool()
def record_transfer(case_id: str, direction: str, drive_file_id: str, sha256: str) -> str:
    """Log a Drive upload or download of a job or result file done through the connector
    (direction is 'upload' or 'download'); changes no file besides the audit log."""
    return _json(queue.record_transfer(case_id, direction, drive_file_id, sha256))

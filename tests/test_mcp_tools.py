import asyncio
import json

import pytest
from mcp import Client

from mcp_server import queue
from mcp_server.server import mcp

WEDGE = {"family": "wedge", "theta1_deg": 8.0, "tag": "test"}


@pytest.fixture(autouse=True)
def queue_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SU2_QUEUE_DIR", str(tmp_path))
    return tmp_path


def call(tool, **args):
    """Call a tool through the in-process MCP client; return the decoded JSON."""
    async def go():
        async with Client(mcp) as client:
            res = await client.call_tool(tool, args)
            assert not res.is_error, res
            return json.loads(res.content[0].text)
    return asyncio.run(go())


def test_tools_are_registered():
    async def go():
        async with Client(mcp) as client:
            return {t.name for t in (await client.list_tools()).tools}
    assert asyncio.run(go()) == {"validate_config", "create_case", "submit", "status",
                                 "list_results", "queue_batch", "record_transfer"}


def test_create_submit_status(queue_env):
    created = call("create_case", params=WEDGE)
    assert created["ok"] and created["case_id"].startswith("wedge-")
    cid = created["case_id"]
    job = queue_env / "jobs" / cid
    for name in ("params.json", "geometry.json", "mesh.su2", "mesh_markers.json",
                 "mesh_quality.json", "case.cfg", "job.json"):
        assert (job / name).is_file(), name
    assert call("status", case_id=cid)[0]["status"] == "created"

    assert call("submit", case_id=cid) == {"ok": True, "case_id": cid, "status": "pending",
                                           "job_json": str(job / "job.json")}
    rows = call("status")
    assert [(r["case_id"], r["status"]) for r in rows] == [(cid, "pending")]
    assert call("submit", case_id=cid)["ok"] is False          # already pending

    info = json.loads((job / "job.json").read_text())
    assert info["case_id"] == cid and info["params"] == json.loads((job / "params.json").read_text())
    assert len(info["mesh_sha256"]) == 64


def test_create_twice_errors_unless_force(queue_env):
    first = call("create_case", params=WEDGE)
    again = call("create_case", params=WEDGE)
    assert again["ok"] is False and again["stage"] == "exists" and again["case_id"] == first["case_id"]
    assert call("create_case", params=WEDGE, force=True)["ok"] is True
    call("submit", case_id=first["case_id"])
    assert call("create_case", params=WEDGE, force=True)["stage"] == "exists"   # pending: not replaced


def test_validate_config_writes_nothing(queue_env):
    res = call("validate_config", params=WEDGE)
    assert res["ok"] and res["stage"] == "done"
    assert not (queue_env / "jobs").exists()
    bad = call("validate_config", params={**WEDGE, "theta1_deg": 99})
    assert bad["ok"] is False and bad["stage"] == "schema"
    assert not (queue_env / "jobs").exists()


def test_inlet2r_create(queue_env):
    res = call("create_case", params={"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0,
                                      "tag": "test"})
    assert res["ok"], res
    assert res["mesh_quality"]["pass"] and res["mesh_quality"]["n_inverted"] == 0
    assert (queue_env / "jobs" / res["case_id"] / "case.cfg").is_file()


def test_queue_batch_creates_pending_jobs_in_order(tmp_path):
    design = tmp_path / "design.csv"
    angles = [(9.0, 0), (5.0, 0), (7.0, 0)]
    design.write_text("index,theta1_deg,theta2_deg\n" +
                      "".join(f"{i},{a},{b}\n" for i, (a, b) in enumerate(angles)))
    res = queue.queue_batch(str(design), "pool", "coarse", family="wedge")
    assert res["ok"] and len(res["case_ids"]) == 3
    rows = queue.status()
    assert [r["case_id"] for r in rows] == res["case_ids"]
    assert [r["status"] for r in rows] == ["pending"] * 3
    assert [r["theta1_deg"] for r in queue.list_results(tag="pool")] == [9.0, 5.0, 7.0]
    # Running it again changes nothing and does not fail.
    assert queue.queue_batch(str(design), "pool", "coarse", family="wedge")["case_ids"] == res["case_ids"]


def test_queue_batch_stops_at_first_failure(tmp_path):
    design = tmp_path / "design.csv"
    design.write_text("index,theta1_deg,theta2_deg\n0,9.0,0\n1,30.0,0\n2,7.0,0\n")
    res = queue.queue_batch(str(design), "pool", "coarse", family="wedge")
    assert res["ok"] is False and len(res["case_ids"]) == 1
    assert res["failed"]["row"] == 1 and res["failed"]["stage"] == "schema"
    assert len(queue.status()) == 1


def test_queue_batch_through_the_tool_uses_inlet2r(tmp_path):
    design = tmp_path / "d.csv"
    design.write_text("index,theta1_deg,theta2_deg\n0,8.0,8.0\n")
    res = call("queue_batch", design_csv=str(design), tag="test", mesh_level="coarse")
    assert res["ok"] and res["case_ids"][0].startswith("inlet2r-")
    assert call("status")[0]["status"] == "pending"


def test_list_results_on_an_empty_queue():
    assert call("list_results") == []
    assert call("status") == []


def test_list_results_reads_result_json(queue_env):
    cid = call("create_case", params=WEDGE)["case_id"]
    rows = call("list_results", tag="test")
    assert rows[0]["recovery_total"] is None and rows[0]["status"] == "created"
    (queue_env / "jobs" / cid / "result.json").write_text(json.dumps(
        {"metrics": {"recovery_total": 0.7, "q_peak_W_m2": 1e5}, "run": {"wall_time_s": 12.0},
         "convergence": {"status": "converged"}}))
    row = call("list_results", tag="test")[0]
    assert (row["recovery_total"], row["q_peak_W_m2"], row["wall_time_s"], row["convergence"]) == \
        (0.7, 1e5, 12.0, "converged")
    assert call("list_results", tag="other") == [] and call("list_results", status="pending") == []


def test_record_transfer_and_audit_log(queue_env):
    cid = call("create_case", params=WEDGE)["case_id"]
    ok = call("record_transfer", case_id=cid, direction="upload", drive_file_id="1AbCdEfGh",
              sha256="a" * 64)
    assert ok["ok"]
    assert call("record_transfer", case_id=cid, direction="sideways", drive_file_id="1AbCdEfGh",
                sha256="a" * 64)["ok"] is False
    assert call("record_transfer", case_id="../../etc", direction="upload", drive_file_id="1AbCdEfGh",
                sha256="a" * 64)["ok"] is False
    lines = [json.loads(x) for x in (queue_env / "mcp_log.jsonl").read_text().splitlines()]
    assert [x["tool"] for x in lines] == ["create", "record_transfer", "record_transfer", "record_transfer"]
    assert all({"time", "tool", "args_sha256", "ok"} <= set(x) for x in lines)
    assert lines[1]["case_id"] == cid and lines[1]["sha256"] == "a" * 64 and lines[2]["ok"] is False


def test_path_traversal_in_case_id_is_refused(queue_env):
    assert call("submit", case_id="../x")["ok"] is False
    assert call("status", case_id="../x")[0]["status"] == "unknown"
    assert call("status", case_id="wedge-0123456789")[0]["status"] == "unknown"


def test_csv_missing(tmp_path):
    res = queue.queue_batch(str(tmp_path / "nope.csv"), "pool", "coarse")
    assert res["ok"] is False and res["failed"]["stage"] == "csv"



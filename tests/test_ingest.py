"""Results coming back: stage a job, run the worker on a separate "drive" folder, ingest the files."""
import json
import shutil

import pytest

from mcp_server import queue
from tests.test_worker_end_to_end import worker

WEDGE = {"family": "wedge", "theta1_deg": 8.0, "mesh_level": "coarse", "tag": "test", "max_iter": 300}


@pytest.fixture
def staging(tmp_path, monkeypatch):
    monkeypatch.setenv("SU2_QUEUE_DIR", str(tmp_path / "staging"))
    monkeypatch.setattr(queue, "REPO", tmp_path / "repo")
    return tmp_path


def stage_and_upload(tmp_path, params=WEDGE):
    """create_case + submit in the staging queue; copy job.json into the drive folder's jobs/."""
    cid = queue.create(params)["case_id"]
    assert queue.submit(cid)["ok"]
    drive = tmp_path / "drive"
    (drive / "jobs").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(queue.queue_dir() / "jobs" / cid / "job.json", drive / "jobs" / f"{cid}.json")
    return cid, drive


def test_ingest_result_stores_flags_and_commits_the_subset(staging):
    cid, drive = stage_and_upload(staging)
    assert worker(drive, "--once") == 0
    text = (drive / "runs" / f"{cid}.result.json").read_text()
    staged = queue.queue_dir() / "jobs" / cid

    res = queue.ingest_result(cid, text)
    assert res["ok"] and res["status"] == "done"
    assert queue.status(cid)[0]["status"] == "done"
    assert (staged / "result.json").read_text() == text
    dest = staging / "repo" / "runs" / "test" / cid
    assert res["committed_to"] == str(dest)
    assert sorted(p.name for p in dest.iterdir()) == [
        "case.cfg", "geometry.json", "mesh_quality.json", "params.json", "result.json",
        "solver_version.txt"]
    assert (dest / "solver_version.txt").read_text().startswith("SU2 vFAKE")
    assert (dest / "case.cfg").read_text() == (staged / "case.cfg").read_text()

    row = queue.list_results(tag="test")[0]                   # list_results reads the ingested file
    assert row["status"] == "done" and row["convergence"] == "converged"
    assert row["wall_time_s"] == json.loads(text)["run"]["wall_time_s"]
    assert queue.ingest_result(cid, text)["ok"]               # idempotent
    tools = [json.loads(x)["tool"] for x in (queue.queue_dir() / "mcp_log.jsonl").read_text().splitlines()]
    assert tools.count("ingest_result") == 2                  # audited


def test_ingest_result_rejects_bad_results_and_stores_nothing(staging):
    cid, drive = stage_and_upload(staging)
    assert worker(drive, "--once") == 0
    rec = json.loads((drive / "runs" / f"{cid}.result.json").read_text())
    staged = queue.queue_dir() / "jobs" / cid

    def refused(record, case=cid, fragment=""):
        res = queue.ingest_result(case, record if isinstance(record, str) else json.dumps(record))
        assert res["ok"] is False and res["errors"], res
        assert fragment in " ".join(res["errors"])
        assert not (staged / "result.json").exists()
        assert queue.status(cid)[0]["status"] == "pending"
        assert not (staging / "repo").exists()
        return res

    refused({**rec, "case_id": "wedge-0000000000"}, fragment="case_id")
    refused(rec, case="wedge-0000000000", fragment="no staged job")
    refused(rec, case="../x", fragment="bad case_id")
    refused({**rec, "job": {**rec["job"], "mesh_fingerprint": "f" * 64}}, fragment="job.mesh_fingerprint")
    refused({**rec, "job": {**rec["job"], "config_sha256": "f" * 64}}, fragment="job.config_sha256")
    refused({k: v for k, v in rec.items() if k != "job"}, fragment="'job'")
    for block in queue.RUN_BLOCKS:
        refused({k: v for k, v in rec.items() if k != block}, fragment=block)
        refused({**rec, block: "not an object"}, fragment=block)
    refused({**rec, "params": {**rec["params"], "theta1_deg": 9.0}}, fragment="params")
    refused({**rec, "convergence": {**rec["convergence"], "status": "diverged"}}, fragment="ingest_error")
    refused({**rec, "run": {**rec["run"], "wall_time_s": "fast"}}, fragment="wall_time_s")
    refused("{not json", fragment="not valid JSON")
    refused([1, 2], fragment="JSON object")


def test_ingest_error_stores_error_json_and_flags_failed(staging, monkeypatch):
    cid, drive = stage_and_upload(staging)
    monkeypatch.setenv("FAKE_SU2_EXIT", "3")
    assert worker(drive, "--once") == 0
    text = (drive / "runs" / cid / "error.json").read_text()

    for bad in ("{oops", "[]", json.dumps({"reason": 5, "detail": "x"}),
                json.dumps({"reason": "timeout"}), json.dumps({"case_id": "wedge-0000000000",
                                                              "reason": "timeout", "detail": ""})):
        assert queue.ingest_error(cid, bad)["ok"] is False
    assert queue.ingest_error("wedge-0000000000", text)["ok"] is False
    assert queue.status(cid)[0]["status"] == "pending"

    res = queue.ingest_error(cid, text)
    record = staging / "repo" / "runs" / "test" / cid
    assert res == {"ok": True, "case_id": cid, "status": "failed", "reason": "nonzero_exit",
                   "committed_to": str(record)}
    staged = queue.queue_dir() / "jobs" / cid
    assert (staged / "error.json").read_text() == text
    assert queue.status(cid)[0]["status"] == "failed"
    # a failure is a run record too: inputs and the error, no result.json
    assert (record / "error.json").read_text() == text
    assert {p.name for p in record.iterdir()} >= {"params.json", "case.cfg", "geometry.json", "error.json"}
    assert not (record / "result.json").exists()


def test_a_later_result_replaces_a_failed_flag(staging, monkeypatch):
    cid, drive = stage_and_upload(staging)
    monkeypatch.setenv("FAKE_SU2_EXIT", "3")
    worker(drive, "--once")
    assert queue.ingest_error(cid, (drive / "runs" / cid / "error.json").read_text())["ok"]
    monkeypatch.delenv("FAKE_SU2_EXIT")
    for flag in ("2-failed", "1-running"):
        (drive / "runs" / cid / "status" / flag).unlink()      # the operator's way to retry a job
    worker(drive, "--once")
    assert queue.ingest_result(cid, (drive / "runs" / f"{cid}.result.json").read_text())["ok"]
    assert queue.status(cid)[0]["status"] == "done"
    record = staging / "repo" / "runs" / "test" / cid
    assert (record / "result.json").exists() and not (record / "error.json").exists()


def test_postprocess_returns_the_metrics_block(staging):
    cid, drive = stage_and_upload(staging)
    assert queue.postprocess(cid)["ok"] is False              # nothing yet
    assert queue.postprocess("wedge-0000000000")["stage"] == "unknown_case"
    assert worker(drive, "--once") == 0
    text = (drive / "runs" / f"{cid}.result.json").read_text()
    queue.ingest_result(cid, text)

    res = queue.postprocess(cid)
    assert res["ok"] and res["source"] == "result.json"
    assert res["metrics"] == json.loads(text)["metrics"]
    assert "heat_load_body_W_per_m" in res["metrics"]

    # recompute needs the surface file; with it the answer is the worker's own number
    assert queue.postprocess(cid, recompute=True)["ok"] is False
    staged = queue.queue_dir() / "jobs" / cid
    shutil.copyfile(drive / "runs" / cid / "surface_flow.dat", staged / "surface_flow.dat")
    shutil.copyfile(drive / "runs" / cid / "history.csv", staged / "history.csv")
    again = queue.postprocess(cid, recompute=True)
    assert again["source"] == "recomputed" and again["metrics"] == res["metrics"]

    (staged / "result.json").unlink()                         # missing result.json, surface staged
    assert queue.postprocess(cid)["source"] == "recomputed"


def test_ingest_tools_are_registered_and_return_json(staging):
    import asyncio

    from mcp import Client

    from mcp_server.server import mcp

    async def go():
        async with Client(mcp) as client:
            res = await client.call_tool("ingest_result", {"case_id": "wedge-0000000000",
                                                           "result_json_text": "{}"})
            res2 = await client.call_tool("postprocess", {"case_id": "wedge-0000000000"})
            return json.loads(res.content[0].text), json.loads(res2.content[0].text)
    first, second = asyncio.run(go())
    assert first["ok"] is False and second["stage"] == "unknown_case"

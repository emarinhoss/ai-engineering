"""mcp_server.ingest_files: a directory of downloaded records goes through the ingest checks."""
import json

import pytest

from mcp_server import ingest_files, queue
from tests.test_ingest import stage_and_upload, worker


@pytest.fixture
def staging(tmp_path, monkeypatch):
    monkeypatch.setenv("SU2_QUEUE_DIR", str(tmp_path / "staging"))
    monkeypatch.setattr(queue, "REPO", tmp_path / "repo")
    return tmp_path


def test_ingest_dir_accepts_results_and_errors_and_refuses_bad_files(staging, tmp_path, monkeypatch):
    cid, drive = stage_and_upload(staging)
    assert worker(drive, "--once") == 0
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / f"{cid}.result.json").write_text((drive / "runs" / f"{cid}.result.json").read_text())
    (inbox / "wedge-0000000000.result.json").write_text("{}")       # unknown case: refused
    (inbox / "notes.txt").write_text("ignored")
    ids = tmp_path / "ids.json"
    ids.write_text(json.dumps({cid: "drive-id-1"}))
    assert ingest_files.main([str(inbox), "--drive-ids", str(ids)]) == 1
    assert queue.status(cid)[0]["status"] == "pending"              # no digest file: not ingested
    (inbox / f"{cid}.result.sha256").write_text((drive / "runs" / f"{cid}.result.sha256").read_text())
    assert ingest_files.main([str(inbox), "--drive-ids", str(ids)]) == 1   # the unknown case still fails
    assert queue.status(cid)[0]["status"] == "done"
    record = staging / "repo" / "runs" / "test" / cid
    assert (record / "result.json").exists()

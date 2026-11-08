"""The staging queue accepts the Task 10 families' case ids (create, submit, export)."""
import json

import pytest

from mcp_server import queue

SMOKE = {"family": "airfoil2d", "camber_pct": 4.0, "thickness_pct": 12.0, "reynolds": 2.0e5,
         "alpha_deg": 6.0, "transition": "BCM", "mesh_level": "medium", "tag": "test", "max_iter": 3000}


def test_airfoil2d_job_can_be_created_submitted_and_exported(tmp_path, monkeypatch):
    monkeypatch.setenv("SU2_QUEUE_DIR", str(tmp_path))
    created = queue.create(SMOKE)
    assert created["ok"], created
    cid = created["case_id"]
    assert cid.startswith("airfoil2d-") and len(cid) == len("airfoil2d-") + 10
    submitted = queue.submit(cid)
    assert submitted["ok"], submitted
    job = json.loads((tmp_path / "jobs" / cid / "job.json").read_text())
    assert {k: job["params"][k] for k in SMOKE} == SMOKE and job["case_id"] == cid   # defaults filled
    text = queue.export_batch([cid])
    assert cid in text


@pytest.mark.parametrize("cid", ["airfoil2d-0123456789", "drone-abcdef0123", "inlet2r-0123456789"])
def test_case_id_pattern_accepts_every_family(cid):
    assert queue.CASE_ID_RE.match(cid)


def test_case_id_pattern_rejects_unknown_family_and_short_hash():
    assert not queue.CASE_ID_RE.match("rocket-0123456789")
    assert not queue.CASE_ID_RE.match("airfoil2d-01234")

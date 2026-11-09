"""--shard K/N: N workers on one queue take disjoint, complete sets of jobs (Fable, 2026-11-09)."""
import hashlib
import json
from pathlib import Path

import pytest

from worker import run_worker


def _ids(n):
    return [f"airfoil2d-{hashlib.sha256(str(i).encode()).hexdigest()[:10]}" for i in range(n)]


def test_shards_partition_the_case_ids():
    ids = _ids(500)
    for n in (1, 2, 3, 4):
        owners = [[c for c in ids if run_worker.in_shard(c, (k, n))] for k in range(n)]
        assert sum(len(o) for o in owners) == len(ids)                 # complete
        assert len({c for o in owners for c in o}) == len(ids)         # disjoint
        if n > 1:
            assert all(len(o) > 0.15 * len(ids) for o in owners)       # roughly balanced


def test_parse_shard_accepts_k_of_n_and_refuses_the_rest():
    assert run_worker.parse_shard("0/1") == (0, 1)
    assert run_worker.parse_shard(" 2/3 ") == (2, 3)
    for bad in ("2/2", "1/0", "a/2", "1", "", "-1/2"):
        with pytest.raises(ValueError):
            run_worker.parse_shard(bad)


def test_jobs_in_state_respects_the_shard(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    ids = _ids(12)
    for i, cid in enumerate(ids):
        job = {k: "" for k in run_worker.JOB_KEYS}
        job.update(case_id=cid, created_at=f"2026-11-09T00:00:{i:02d}+00:00", params={})
        (jobs / f"{cid}.json").write_text(json.dumps(job))
    everything = [j["case_id"] for j in run_worker.jobs_in_state(tmp_path, {"new"}, 600)]
    assert set(everything) == set(ids)
    a = [j["case_id"] for j in run_worker.jobs_in_state(tmp_path, {"new"}, 600, (0, 2))]
    b = [j["case_id"] for j in run_worker.jobs_in_state(tmp_path, {"new"}, 600, (1, 2))]
    assert set(a) | set(b) == set(ids) and not set(a) & set(b)
    assert a == sorted(a, key=lambda c: ids.index(c))                  # still oldest first


def test_heartbeat_file_is_per_shard(tmp_path):
    args = run_worker.parse_args(["--queue", str(tmp_path), "--shard", "1/2", "--worker-id", "w"])
    run_worker.write_worker_heartbeat(args, "airfoil2d-0000000000")
    beat = json.loads((Path(tmp_path) / "worker" / "heartbeat.1of2.json").read_text())
    assert beat["shard"] == "1/2" and beat["current_case"] == "airfoil2d-0000000000"
    args = run_worker.parse_args(["--queue", str(tmp_path), "--worker-id", "w"])
    run_worker.write_worker_heartbeat(args)
    assert (Path(tmp_path) / "worker" / "heartbeat.json").exists()

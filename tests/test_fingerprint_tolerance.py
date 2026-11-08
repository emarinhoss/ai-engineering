"""The mesh fingerprint must not change under floating-point noise between machines.

Found 2026-11-08 on the fine airfoil2d mesh (runs/mesh/airfoil2d-e161fb7e6b): the Colab worker and
the staging machine built meshes whose every quality figure agrees to 16 significant digits, yet
the 1 nm fingerprints differed, so the job failed with mesh_mismatch before SU2 started. Rounding
to 1 nm puts a coordinate within libm-level noise (about 1e-14 m on a 30 m coordinate) of a
rounding boundary with probability about 1e-5 per coordinate, which over 1.7e5 coordinates is a
coin toss per mesh. The fingerprint now rounds to 1 micrometre (3 percent of the smallest first
cell this study meshes), and the worker still accepts a job that carries the old 1 nm digest.
"""
import json
from pathlib import Path

from geometry.structured import mesh_fingerprint, mesh_fingerprint_nm
from tests.test_worker_end_to_end import PARAMS, stage_job, worker
from tests.test_worker_failures import error_of

# A four-node, one-quad SU2 mesh with one marker. 0.1234565005 m sits exactly on a 1 nm rounding
# boundary (123456500.5 nm) and 0.5 um inside a 1 um cell, so a 0.1 nm nudge flips the nm digest
# and leaves the um digest alone, while a 2 um shift changes both.
NODES = [(0.0, 0.0), (0.1234565005, 0.0), (0.1234565005, 0.0500000005), (0.0, 0.0500000005)]


def su2_text(nodes):
    out = ["NDIME= 2", "NELEM= 1", "9 0 1 2 3 0", f"NPOIN= {len(nodes)}"]
    out += [f"{x:.16e} {y:.16e} {k}" for k, (x, y) in enumerate(nodes)]
    out += ["NMARK= 1", "MARKER_TAG= wall", "MARKER_ELEMS= 1", "3 0 1"]
    return "\n".join(out) + "\n"


def write(path, nodes):
    path.write_text(su2_text(nodes))
    return path


def nudged(nodes, dx):
    return [(x + dx, y) for x, y in nodes]


def test_sub_nanometre_noise_does_not_change_the_fingerprint(tmp_path):
    a = mesh_fingerprint(write(tmp_path / "a.su2", NODES))
    b = mesh_fingerprint(write(tmp_path / "b.su2", nudged(NODES, 1e-10)))
    assert a == b


def test_the_legacy_nanometre_digest_is_the_one_that_flipped(tmp_path):
    a = mesh_fingerprint_nm(write(tmp_path / "a.su2", NODES))
    b = mesh_fingerprint_nm(write(tmp_path / "b.su2", nudged(NODES, 1e-10)))
    assert a != b
    assert len(a) == 64


def test_a_two_micrometre_shift_is_a_different_mesh(tmp_path):
    a = mesh_fingerprint(write(tmp_path / "a.su2", NODES))
    b = mesh_fingerprint(write(tmp_path / "b.su2", nudged(NODES, 2e-6)))
    assert a != b


def test_connectivity_and_markers_still_count(tmp_path):
    a = mesh_fingerprint(write(tmp_path / "a.su2", NODES))
    text = su2_text(NODES).replace("9 0 1 2 3 0", "9 0 1 3 2 0")
    (tmp_path / "c.su2").write_text(text)
    assert mesh_fingerprint(tmp_path / "c.su2") != a
    (tmp_path / "m.su2").write_text(su2_text(NODES).replace("MARKER_TAG= wall", "MARKER_TAG= wing"))
    assert mesh_fingerprint(tmp_path / "m.su2") != a


def test_worker_accepts_a_job_file_carrying_the_legacy_digest(tmp_path):
    """Job files staged before the change carry the 1 nm digest; the worker must run them."""
    queue_dir = tmp_path / "queue"
    job = stage_job(queue_dir)
    run_dir = queue_dir / "runs" / job["case_id"]
    scratch_mesh = Path(queue_dir).parent / "scratch" / f"{PARAMS['theta1_deg']}" / "mesh.su2"
    legacy = mesh_fingerprint_nm(scratch_mesh)
    assert legacy != job["mesh_fingerprint"], "the staged job should now carry the micrometre digest"
    (queue_dir / "jobs" / f"{job['case_id']}.json").write_text(json.dumps({**job, "mesh_fingerprint": legacy}))
    assert worker(queue_dir, "--once") == 0
    assert (run_dir / "result.json").exists(), (run_dir / "error.json").read_text() if (run_dir / "error.json").exists() else "no result"


def test_worker_still_refuses_an_edited_digest(tmp_path):
    queue_dir = tmp_path / "queue"
    job = stage_job(queue_dir)
    path = queue_dir / "jobs" / f"{job['case_id']}.json"
    path.write_text(json.dumps({**job, "mesh_fingerprint": "0" * 64}))
    assert worker(queue_dir, "--once") == 0
    err = error_of(queue_dir, job)
    assert err["reason"] == "mesh_mismatch"
    assert err["detail"]["our_mesh_fingerprint"] == job["mesh_fingerprint"]
    assert "our_mesh_fingerprint_nm" in err["detail"]

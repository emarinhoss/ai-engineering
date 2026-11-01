"""mcp_server.verify_digests: committed records against the worker's digests."""
import hashlib

from mcp_server import verify_digests


def test_verify_reports_match_mismatch_and_missing(tmp_path):
    runs = tmp_path / "runs" / "pool"
    (runs / "inlet2r-aaaaaaaaaa").mkdir(parents=True)
    (runs / "inlet2r-bbbbbbbbbb").mkdir()
    good = b'{"case_id": "inlet2r-aaaaaaaaaa"}\n'
    (runs / "inlet2r-aaaaaaaaaa" / "result.json").write_bytes(good)
    (runs / "inlet2r-bbbbbbbbbb" / "error.json").write_bytes(b'{"reason": "nan"}\n')
    digests = tmp_path / "digests"
    digests.mkdir()
    (digests / "inlet2r-aaaaaaaaaa.result.sha256").write_text(hashlib.sha256(good).hexdigest() + "\n")
    (digests / "inlet2r-bbbbbbbbbb.error.sha256").write_text("0" * 64 + "\n")
    (digests / "inlet2r-cccccccccc.result.sha256").write_text("1" * 64 + "\n")
    (digests / "inlet2r-dddddddddd.result.sha256").write_text("not a digest\n")
    rows = verify_digests.verify(digests, tmp_path / "runs")
    assert rows == [("inlet2r-aaaaaaaaaa", "result", "match"), ("inlet2r-bbbbbbbbbb", "error", "MISMATCH"),
                    ("inlet2r-cccccccccc", "result", "missing"), ("inlet2r-dddddddddd", "result", "bad digest")]
    assert verify_digests.main([str(digests), "--runs", str(tmp_path / "runs")]) == 1

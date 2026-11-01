"""Check committed run records against the digests the worker wrote on Drive.

For every <case_id>.result.sha256 / <case_id>.error.sha256 file in a directory (downloaded from
runs/ on Drive; 64 hex digits each, so a transcription error shows up as a non-match or a bad
digit), compare with the sha256 of runs/<tag>/<case_id>/result.json or error.json in the repo.
Records ingested before digests existed (2026-11-01) are verified this way after the fact.

    python -m mcp_server.verify_digests <digest_dir> [--runs runs]

Prints match / MISMATCH / missing per digest; exits 1 on any mismatch.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def verify(digest_dir, runs_dir):
    """[(case_id, kind, verdict)] with verdict match | MISMATCH | missing | bad digest."""
    out = []
    for path in sorted(Path(digest_dir).glob("*.sha256")):
        case_id, kind = path.name[: -len(".sha256")].rsplit(".", 1)
        expected = path.read_text().strip().lower()
        if not HEX64.match(expected):
            out.append((case_id, kind, "bad digest"))
            continue
        local = list(Path(runs_dir).glob(f"*/{case_id}/{kind}.json"))
        if not local:
            out.append((case_id, kind, "missing"))
            continue
        got = hashlib.sha256(local[0].read_bytes()).hexdigest()
        out.append((case_id, kind, "match" if got == expected else "MISMATCH"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("digest_dir")
    ap.add_argument("--runs", default=REPO / "runs")
    args = ap.parse_args(argv)
    rows = verify(args.digest_dir, args.runs)
    for case_id, kind, verdict in rows:
        print(f"{case_id} {kind}: {verdict}")
    counts = {v: sum(r[2] == v for r in rows) for v in ("match", "MISMATCH", "missing", "bad digest")}
    print(", ".join(f"{n} {v}" for v, n in counts.items()))
    return 1 if counts["MISMATCH"] or counts["bad digest"] else 0


if __name__ == "__main__":
    sys.exit(main())

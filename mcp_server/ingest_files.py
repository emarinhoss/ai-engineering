"""Ingest downloaded result.json / error.json files from a directory.

Files are named <case_id>.result.json or <case_id>.error.json (the Drive names of the results;
an error.json downloaded from a case folder must be renamed to <case_id>.error.json). Next to each
one, <case_id>.result.sha256 or <case_id>.error.sha256 holds the worker's digest of the file
(downloaded from runs/ on Drive); a file is ingested only if its text matches that digest, unless
--allow-undigested is given. Each file goes through queue.ingest_result or queue.ingest_error,
which check it against the staged job and copy the record to runs/<tag>/<case_id>/; nothing is
stored when a check fails. An optional JSON file {case_id: drive_file_id} logs the download in the
audit log (record_transfer).

    python -m mcp_server.ingest_files <dir> [--drive-ids ids.json] [--allow-undigested]

Prints one line per file and a summary; exits 1 if any file was refused.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from mcp_server import queue


def ingest_dir(directory, drive_ids=None, require_digest=True):
    """[(file name, result dict)] for every <case_id>.result.json / <case_id>.error.json in directory."""
    drive_ids = drive_ids or {}
    out = []
    for path in sorted(Path(directory).iterdir()):
        name = path.name
        if name.endswith(".result.json"):
            case_id, fn = name[: -len(".result.json")], queue.ingest_result
        elif name.endswith(".error.json"):
            case_id, fn = name[: -len(".error.json")], queue.ingest_error
        else:
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:          # a damaged copy: not even text
            out.append((name, {"ok": False, "stage": "digest", "errors": [f"not valid UTF-8: {exc}"]}))
            continue
        digest_file = path.with_name(name[: -len(".json")] + ".sha256")
        digest = digest_file.read_text().strip() if digest_file.exists() else ""
        if not digest and require_digest:
            why = (f"no {digest_file.name} next to the file (use --allow-undigested only for files "
                   "that cannot have one)")
            out.append((name, {"ok": False, "stage": "digest", "errors": [why]}))
            continue
        res = fn(case_id, text, digest)
        if res.get("ok") and case_id in drive_ids:
            queue.record_transfer(case_id, "download", drive_ids[case_id],
                                  hashlib.sha256(text.encode()).hexdigest())
        out.append((name, res))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("directory")
    ap.add_argument("--drive-ids", help="JSON file {case_id: drive file id}")
    ap.add_argument("--allow-undigested", action="store_true",
                    help="ingest files that have no <case_id>.*.sha256 digest next to them")
    args = ap.parse_args(argv)
    ids = json.loads(Path(args.drive_ids).read_text()) if args.drive_ids else {}
    results = ingest_dir(args.directory, ids, require_digest=not args.allow_undigested)
    bad = 0
    for name, res in results:
        if res.get("ok"):
            print(f"{name}: {res['status']}" + (f" ({res['reason']})" if "reason" in res else ""))
        else:
            bad += 1
            print(f"{name}: REFUSED at stage {res.get('stage')}: {res.get('errors')}")
    print(f"{len(results) - bad} ingested, {bad} refused")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

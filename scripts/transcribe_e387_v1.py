"""Transcribe the E387 polars of Summary of Low-Speed Airfoil Data, Volume 1 (Appendix B, page 279,
Fig. 4.19, model E387 (A)) from a PDF of that page into data/validation/e387_uiuc.yaml.

Nothing is typed: the page's text layer is read with pdftotext -layout, the four print columns are
cut at fixed character positions and read top to bottom, and every "alpha Cl Cd" row between the
"E387 (A)" heading and the next airfoil's heading is parsed by a regular expression. The PDF is NOT
committed (SoarTech copyright); its sha256 is written beside the data so a reader with the book can
check the page. Usage: python scripts/transcribe_e387_v1.py <page.pdf> [--page 279]

Checks before anything is written: five runs (209, 211, 555, 213, 215), each with strictly
increasing alpha and eleven rows, Reynolds numbers 61,500 / 101,800 / 152,700 / 203,800 / 305,200,
which are the run numbers and Reynolds numbers printed on the page. A page that parses to anything
else raises, so a different page or a mis-cut column cannot write a wrong table silently.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import yaml

YAML = Path("data/validation/e387_uiuc.yaml")
BOUNDS = [(0, 24), (24, 48), (48, 72), (72, 400)]          # the four print columns of Appendix B
ROW = re.compile(r"^(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)$")
EXPECTED = {209: 61500, 211: 101800, 555: 152700, 213: 203800, 215: 305200}
NOMINAL = {61500: 6e4, 101800: 1e5, 152700: 1.5e5, 203800: 2e5, 305200: 3e5}
NEXT_HEADING = "FX 63-137"


def columns_in_reading_order(text):
    cols = [[] for _ in BOUNDS]
    for line in text.splitlines():
        for i, (a, b) in enumerate(BOUNDS):
            seg = line[a:b].strip()
            if seg:
                cols[i].append(seg)
    return [s for c in cols for s in c]


def parse_runs(stream):
    start = next(i for i, s in enumerate(stream) if s.startswith("E387"))
    end = next(i for i, s in enumerate(stream) if i > start and s.startswith(NEXT_HEADING))
    runs, cur = [], None
    for s in stream[start:end]:
        if s.startswith("Run:"):
            cur = {"run": int(s.split(":")[1]), "rows": []}
            runs.append(cur)
        elif s.startswith("Re ="):
            cur["re"] = int(s.split("=")[1])
        elif (m := ROW.match(s)) and cur is not None:
            cur["rows"].append(tuple(float(v) for v in m.groups()))
    return runs


def check(runs):
    got = {r["run"]: r["re"] for r in runs}
    if got != EXPECTED:
        raise SystemExit(f"runs/Reynolds parsed {got} differ from the page's {EXPECTED}")
    for r in runs:
        a = [row[0] for row in r["rows"]]
        if len(a) != 11 or any(x >= y for x, y in pairwise(a)):
            raise SystemExit(f"run {r['run']}: {len(a)} rows, alpha {a}")
        if any(row[2] <= 0 for row in r["rows"]):
            raise SystemExit(f"run {r['run']}: non-positive Cd")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=279)
    args = ap.parse_args(argv)
    pdf = Path(args.pdf)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    if "Appendix B: Airfoil Polar Data" not in text or str(args.page) not in text.splitlines()[0]:
        raise SystemExit("this does not look like the Appendix B page asked for")
    runs = parse_runs(columns_in_reading_order(text))
    check(runs)
    doc = yaml.safe_load(YAML.read_text())
    doc["source"] = ("Selig, Guglielmo, Broeren and Giguere, Summary of Low-Speed Airfoil Data, Volume 1, "
                     f"SoarTech Publications, 1995, Appendix B 'Airfoil Polar Data', page {args.page}, "
                     "Fig. 4.19, model E387 (A), drag-polar runs 209, 211, 555, 213 and 215 (lift and drag "
                     "at the same angles). The page was supplied by Eder as a one-page PDF (sha256 "
                     f"{digest}); its text layer was read with pdftotext -layout and parsed by "
                     "scripts/transcribe_e387_v1.py, which refuses any page that does not parse to exactly "
                     "these five runs. The PDF is not committed (copyright); only the figures are.")
    doc["retrieval"] = "done"
    doc["retrieved_on"] = "2026-11-08"
    doc["retrieved_by"] = "Eder (PDF of the page); transcribed by scripts/transcribe_e387_v1.py"
    doc["page_pdf_sha256"] = digest
    doc["polars"] = [{"run": r["run"], "reynolds": float(r["re"]), "nominal_reynolds": NOMINAL[r["re"]],
                      "alpha_deg": [row[0] for row in r["rows"]], "cl": [row[1] for row in r["rows"]],
                      "cd": [row[2] for row in r["rows"]]} for r in runs]
    YAML.write_text(yaml.safe_dump(doc, sort_keys=False, width=100, allow_unicode=True))
    print(f"wrote {YAML}: {len(runs)} runs, {sum(len(r['rows']) for r in runs)} points, pdf sha256 {digest[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""One drone design: section polar from airfoil2d cases, then the high-fidelity evaluation (T10.7d).

    python -m analysis.drone_design --params params.json --cases a/result.json b/result.json --out DIR
"""
import argparse
import hashlib
import json
from pathlib import Path

from analysis.drone_polar import polar
from drone import evaluate, ledger
from worker import make_case


def design_id(params):
    """"drone-" + first 10 hex digits of the sha256 of the canonical params."""
    return "drone-" + hashlib.sha256(make_case.canonical_json(params).encode()).hexdigest()[:10]


def design_record(params, case_records, fixed=None, accept_exhausted=frozenset()):
    section = polar(case_records, accept_exhausted=accept_exhausted)
    result = evaluate.evaluate({**params, "fidelity": "high"}, fixed or ledger.load_all(),
                               section=section)
    return {"params": params, "cases": [r["case_id"] for r in case_records],
            "section": {"cl_max": section.cl_max, "alpha_L0": section.alpha_L0,
                        "cl_alpha_per_deg": section.cl_alpha_per_deg,
                        "flags": list(section.flags), "source": section.source},
            "result": result}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--params", required=True)
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    params = json.loads(Path(a.params).read_text())
    records = [json.loads(Path(p).read_text()) for p in a.cases]
    rec = design_record(params, records)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(rec, indent=2, default=float))
    (out / "params.json").write_text(json.dumps(params, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

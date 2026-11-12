"""Fit and freeze the W1 field model (docs/specs/task11_fno_exploration.md; task W1.6).

    python -m analysis.w1_fit --fields <dir>/fields.npz --out runs/w1_model/<date>

The rule lets the number of components be tuned by leave-one-design-out on the training set only.
Candidates: K_CANDIDATES. For each training design, fit on the other designs with the largest
candidate and predict every held-out case with each candidate (the components and their GPs do not
depend on k). Error of one prediction: root mean square over nodes of (predicted - true) / the
field's training standard deviation, one number per field, then their mean. The candidate with the
least mean error is fitted on all training fields and saved. Writes model.npz and model.json
(settings, leave-one-out table, sha256 of the fields file and of the model).
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from surrogate.field_pca_gp import FieldPCAGP

K_CANDIDATES = (4, 8, 16, 32)


def field_error(pred, true, block):
    """Per field: RMS over nodes of (pred - true) / block. Returns a (4,) array."""
    return np.sqrt((((pred - true) / block) ** 2).mean(0))


def leave_one_design_out(X, F, designs, ks=K_CANDIDATES):
    """{k: (n_cases, 4) per-field errors}, every case predicted by a model that never saw its design."""
    block = (F - F.mean(0)).reshape(-1, 4).std(0)
    errs = {k: [] for k in ks}
    for d in np.unique(designs):
        held = designs == d
        model = FieldPCAGP().fit(X[~held], F[~held], k=min(max(ks), int((~held).sum())))
        for x, f in zip(X[held], F[held]):
            for k in ks:
                errs[k].append(field_error(model.predict(x, k=k), f, block))
    return {k: np.array(v) for k, v in errs.items()}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fields", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    z = np.load(a.fields)
    X, F, designs = z["X"], z["F"], z["designs"]
    errs = leave_one_design_out(X, F, designs)
    table = {k: {"mean": float(e.mean()), "per_field": e.mean(0).tolist(), "worst_case": float(e.mean(1).max())}
             for k, e in errs.items()}
    best = min(table, key=lambda k: table[k]["mean"])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model = FieldPCAGP().fit(X, F, k=best)
    model.save(out / "model.npz")
    info = {"k": best, "candidates": list(K_CANDIDATES), "fields": ["Pressure", "Velocity_x", "Velocity_y", "Nu_Tilde*Re"],
            "inputs": ["camber_pct", "thickness_pct", "log10_reynolds", "alpha_deg"],
            "training_cases": len(X), "training_designs": len(np.unique(designs)),
            "explained_variance": model.explained, "leave_one_design_out": table,
            "fields_npz_sha256": sha256(a.fields), "model_npz_sha256": sha256(out / "model.npz")}
    (out / "model.json").write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps(info, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

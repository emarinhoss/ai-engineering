"""Aggregate airfoil2d case records (result.json dicts) into one SectionData polar (Task 10.7c).

Which records are kept (2026-11-08): a record is kept if its status is converged or stationary, or if
it is "not_converged" but SU2 stopped on its own convergence criterion: exit code 0, no timeout, and
fewer iterations than params["max_iter"]. Every airfoil2d run that converged on SU2's Cauchy
criterion is classified not_converged by the 20-percent-window drift rule, so discarding them would
discard every run. Their drift is carried as a flag (cauchy_stopped, cl_drift_max_pct,
cd_drift_max_pct) and not used to drop the run. A run that merely exhausted its iteration budget, or
timed out, is NOT kept.
"""
from drone.section import from_polar

DESIGN_KEYS = ("camber_pct", "thickness_pct", "reynolds", "transition", "airfoil")
GOOD = ("converged", "stationary")


def _cauchy_stopped(r):
    run, conv = r.get("run"), r["convergence"]
    if conv["status"] in GOOD or run is None or "iterations" not in conv:
        return False
    return (run["exit_code"] == 0 and not run["timeout"]
            and conv["iterations"] < r["params"]["max_iter"])


def polar(records):
    """SectionData from the result.json records of one design at several angles of attack."""
    if not records:
        raise ValueError("no records")
    first = records[0]["params"]
    design = {k: first.get(k) for k in DESIGN_KEYS}
    for r in records:
        if {k: r["params"].get(k) for k in DESIGN_KEYS} != design:
            raise ValueError(f"records mix designs: {design} and "
                             f"{ {k: r['params'].get(k) for k in DESIGN_KEYS} }")
    kept = [r for r in records if r["convergence"]["status"] in GOOD or _cauchy_stopped(r)]
    if len(kept) < 3:
        raise ValueError(f"{len(kept)} converged angles of {len(records)}; need at least 3")
    kept.sort(key=lambda r: r["params"]["alpha_deg"])
    shape = (f"airfoil={design['airfoil']}" if design["airfoil"] is not None else
             f"camber={design['camber_pct']} thickness={design['thickness_pct']}")
    source = (f"airfoil2d {shape} "
              f"Re={design['reynolds']} transition={design['transition']} "
              f"cases={','.join(r['case_id'] for r in kept)}")
    s = from_polar([r["params"]["alpha_deg"] for r in kept], [r["metrics"]["cl"] for r in kept],
                   [r["metrics"]["cd"] for r in kept], source)
    if len(kept) < len(records):
        s.flags.append("missing_angles")
    stopped = [r for r in kept if _cauchy_stopped(r)]
    if stopped:
        s.flags.append("cauchy_stopped")
        s.flags.append(f"cl_drift_max_pct={max(r['convergence']['drift_pct']['cl'] for r in stopped):.1f}")
        s.flags.append(f"cd_drift_max_pct={max(r['convergence']['drift_pct']['cd'] for r in stopped):.1f}")
    return s

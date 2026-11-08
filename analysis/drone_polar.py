"""Aggregate airfoil2d case records (result.json dicts) into one SectionData polar (Task 10.7c)."""
from drone.section import from_polar

DESIGN_KEYS = ("camber_pct", "thickness_pct", "reynolds", "transition")
GOOD = ("converged", "stationary")


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
    kept = [r for r in records if r["convergence"]["status"] in GOOD]
    if len(kept) < 3:
        raise ValueError(f"{len(kept)} converged angles of {len(records)}; need at least 3")
    kept.sort(key=lambda r: r["params"]["alpha_deg"])
    source = (f"airfoil2d camber={design['camber_pct']} thickness={design['thickness_pct']} "
              f"Re={design['reynolds']} transition={design['transition']} "
              f"cases={','.join(r['case_id'] for r in kept)}")
    s = from_polar([r["params"]["alpha_deg"] for r in kept], [r["metrics"]["cl"] for r in kept],
                   [r["metrics"]["cd"] for r in kept], source)
    if len(kept) < len(records):
        s.flags.append("missing_angles")
    return s

"""The recorded V6e bias that travels with every SU2 (high-level) section polar (decision 8).

Decision 8 (Éder, 2026-11-08): the medium-mesh SA-BCM polar is the high level, with the V6e miss
recorded beside every number it produces. This module reads the miss from the recorded validation
run rather than from a literal, so the flag cannot drift from the record: each "V6e <quantity>
Re <re>" row with a tolerance becomes one flag, `v6e:<quantity>:Re<re>=<deviation %>:<verdict>`.
"""
import json
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "runs/drone/validation/2026-11-08/v6.json"
RULING = "v6e_ruling=decision8_accepted_with_bias"


def v6e_flags(record=RECORD):
    """Flags from the toleranced V6e rows of the recorded validation run, plus the ruling."""
    checks = json.loads(Path(record).read_text())["checks"]
    flags = []
    for c in checks:
        if not c["name"].startswith("V6e ") or c.get("tolerance") is None:
            continue
        # "V6e cl_alpha Re 203800" -> quantity "cl_alpha", re "203800"
        _, quantity, _, re = c["name"].split(" ", 3)
        flags.append(f"v6e:{quantity}:Re{re}={100 * c['deviation']:+.1f}%:{c['verdict']}")
    if not flags:
        raise ValueError(f"no toleranced V6e row in {record}")
    return flags + [RULING]

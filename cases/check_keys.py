"""Find config keys that the pinned SU2 config_template.cfg does not know.

Usage: python -m cases.check_keys case.cfg [config_template.cfg]
"""
import sys
from pathlib import Path

DEFAULT_TEMPLATE = Path(__file__).parent / "su2_v8.2.0_config_template.cfg"


def keys(text):
    """Keys = tokens before '=' on lines that are not comments."""
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("%") or "=" not in line:
            continue
        found.append(line.split("=", 1)[0].strip())
    return found


def unknown_keys(cfg_text, template_text):
    """Keys present in cfg_text but not in the SU2 template, in file order."""
    known = set(keys(template_text))
    return [k for k in keys(cfg_text) if k not in known]


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    template = Path(sys.argv[2]) if len(sys.argv) == 3 else DEFAULT_TEMPLATE
    bad = unknown_keys(Path(sys.argv[1]).read_text(), template.read_text())
    if bad:
        sys.exit("unknown SU2 keys: " + ", ".join(bad))
    print("all keys known")

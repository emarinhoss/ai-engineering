"""Summary of a recorded pytest run (junit xml) for the gate record. Counts come from the xml; the commit,
clean-tree flag, exit code and wall time were taken by the caller before and after the run.
    python -m postprocess.task12_pytest_summary DIR COMMIT CLEAN_TREE EXIT_CODE WALL_S"""
import json
import platform
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

d, commit, clean, rc, wall = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "true", int(sys.argv[4]), float(sys.argv[5])
suite = ET.parse(d / "junit.xml").getroot()
suite = suite if suite.tag == "testsuite" else suite[0]
cases = suite.findall("testcase")
skipped = [c for c in cases if c.find("skipped") is not None]
xfailed = [c for c in skipped if (c.find("skipped").get("type") or "") == "pytest.xfail"]
failed = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
summary = {"command": "python -m pytest -q -p no:cacheprovider tests/task12 --junitxml=" + str(d / "junit.xml"),
           "commit": commit, "clean_tree": clean, "exit_code": rc, "tests": len(cases),
           "passed": len(cases) - len(failed) - len(skipped), "failed": len(failed), "xfailed": len(xfailed),
           "skipped_other": len(skipped) - len(xfailed), "duration_s": float(suite.get("time")), "wall_s": wall,
           "python": platform.python_version(), "log": str(d / "pytest.log"), "junit": str(d / "junit.xml")}
(d / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))

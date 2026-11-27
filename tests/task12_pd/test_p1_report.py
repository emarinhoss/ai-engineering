"""The committed P1 report is the text the record generates, and it states the things a reader must not miss."""
import json

from prelim import p1_package as p1
from prelim.p1_report import report_text

OUT = p1.REPO / "runs/task12/pd/2026-11-27/p1"
REPORT = p1.REPO / "docs/validation/2026-11-27_task12_pd_p1.md"
FIGURES = p1.REPO / "docs/validation/figures/2026-11-27_task12_pd_p1"
R0 = json.loads((p1.R0 / "design_pusher.json").read_text())


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_carries_each_acceptance_verdict_of_the_record():
    text = REPORT.read_text()
    numbers = [str(i) for i in range(1, 13)]
    block = text.split("## 2. Acceptance rows", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in block.splitlines() if ln.startswith("| ") and ln.split("|")[1].strip() in numbers]
    acc = json.loads((OUT / "p1.json").read_text())["acceptance"]
    assert len(rows) == len(acc) == 12
    for line, a in zip(rows, acc):
        assert line.split("|")[1].strip() == str(a["row"]) and line.rstrip().endswith(f"**{a['verdict']}** |")


def test_report_quotes_r0_values_as_the_record_has_them():
    text = REPORT.read_text()
    for value in (f"{R0['W0_lb']:,.2f}", f"{R0['We_lb']:,.3f}", f"{R0['fuel_lb']:,.2f}", f"{R0['layout']['sm_full']:,.4f}",
                  f"{R0['performance']['service_ceiling_ft']:,.0f}", f"{R0['CD0']['mission_altitude']:,.5f}",
                  f"{R0['propeller_points']['loiter']['eta_p']:,.4f}", f"{R0['wing']['mac']:,.3f}"):
        assert value in text, value


def test_every_linked_figure_exists_with_its_sidecar():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert len(links) >= 8
    for link in links:
        assert (p1.REPO / "docs/validation/figures" / link).stat().st_size > 1000, link
    side = json.loads((FIGURES / "figures.json").read_text())
    assert side["label"] == "drawn from the sizing records; geometry only, no flow solution"
    assert side["p1_json_sha256"] == p1.sha256(OUT / "p1.json")
    assert sorted(side["figures"]) == sorted(p.name for p in FIGURES.glob("*.png"))


def test_report_says_what_the_package_is_not():
    text = REPORT.read_text()
    assert "a package, not a measurement" in text
    assert "is not applied" in text and "**not a band**" in text
    assert "The mission was not flown again" in text or "the mission was not flown again" in text
    assert "The choice of the pusher is not re-opened (PD-3)" in text
    assert "## 16. Assumptions made where the spec left a choice" in text
    assert "## 17. What this does not show" in text
    for section in ("## 4. Requirements compliance matrix", "## 5. Three-view and internal layout", "## 6. Weight statement",
                    "## 7. Drag, propulsion and mission", "## 8. Constraint diagram, carpet plot and trades", "## 10. V-n diagram",
                    "## 11. Stability and trim summary", "## 13. Ledger", "## 14. Risk list", "## 15. Test report"):
        assert section in text, section                         # the ten outputs of spec section 4

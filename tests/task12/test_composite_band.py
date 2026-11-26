"""Owner ruling B-2 (review GB-1): the composite band reaches the build-up and the build-up carries an
empty-weight band. At the nominal values nothing changes; records without the new ledger lines read as before."""
import json
from pathlib import Path

import pytest
import yaml

from conceptual import raymer_weights as wts
from conceptual import uav
from measurement import composite_band_study as cb
from measurement import info_gap as ig
from measurement import stage3_perf as sp

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05"
OLD_M250 = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"
STATE_KEYS = ("We", "fuel", "bhp", "D_prop", "CD0_alt", "CD0_takeoff", "Nz")


def built(model, empty_weight):
    """The frozen record with a case ledger held in memory (nothing written)."""
    text = cb.case_ledger((FROZEN / "ledger.yaml").read_text(), uav.LEDGER.read_text(), model, empty_weight)
    raw = yaml.safe_load(text)
    L = {k: (q["value"] if isinstance(q["value"], str) else float(q["value"]))
         for g in ("requirements", "assumptions") for k, q in raw[g].items()}
    d = json.loads((FROZEN / "design_pusher.json").read_text())
    return ig.Built("frozen", record=(d, L, FROZEN / "m250_table.json")), raw["assumptions"]


def test_composite_fudge_mappings():
    f0 = wts.COMPOSITE_FUDGE
    assert wts.composite_fudge(1.0, None) == f0                       # no model: the printed factors, c ignored
    assert wts.composite_fudge(0.95, "saving") == f0                  # exactly, not approximately
    assert wts.composite_fudge(0.95, "scale") == f0
    assert all(v == pytest.approx(1.0, abs=1e-12) for v in wts.composite_fudge(1.0, "saving").values())   # metal
    assert wts.composite_fudge(0.90, "saving")["wing"] == pytest.approx(0.70, abs=1e-12)     # twice the saving
    assert wts.composite_fudge(1.0, "scale")["wing"] == pytest.approx(0.85 / 0.95, abs=1e-12)
    with pytest.raises(ValueError):
        wts.composite_fudge(0.95, "metal")


def test_current_ledger_carries_both_lines_and_they_are_nominal():
    L, entries = uav.load_ledger()
    assert L["composite_model"] == "saving" and L["composite_factor"] == wts.COMPOSITE_FIRST_PASS
    assert L["empty_weight_factor"] == 1.0 and entries["empty_weight_factor"]["band"] == [0.95, 1.05]
    names = [v["name"] for v in ig.uncertain_variables(entries)]
    assert "empty_weight_factor" in names and "composite_model" not in names


@pytest.mark.parametrize("model,empty_weight", [("saving", True), ("scale", True), ("saving", False)])
def test_nominal_design_is_unchanged_by_the_new_lines(model, empty_weight):
    """The frozen record rebuilt with the new lines against the same rebuild without them: equal to 1e-9
    (in fact identical), state and components, and the weight fixed point."""
    old, _ = built(None, False)
    new, _ = built(model, empty_weight)
    a, b = old.nominal_state, new.nominal_state
    for k in STATE_KEYS:
        assert b[k] == pytest.approx(a[k], rel=1e-9, abs=0.0), k
    assert b["components"] == a["components"] and b["power_req"] == a["power_req"]
    assert new.w0_for({}) == pytest.approx(old.w0_for({}), rel=1e-9)
    # and against the record itself, at the tolerance the record was written to reproduce
    assert b["fuel"] == pytest.approx(new.d["fuel_lb"], rel=sp.REBUILD_TOLERANCE)
    assert b["We"] == pytest.approx(new.d["We_lb"], rel=sp.REBUILD_TOLERANCE)


def test_records_without_the_new_lines_read_as_before():
    """A ledger copy with no composite_model line: composite_factor does not reach the build-up (as before),
    and no empty_weight_factor line means a multiplier of 1."""
    for path in (FROZEN / "design_pusher.json", OLD_M250):
        b = ig.Built(str(path))
        assert "composite_model" not in b.L and "empty_weight_factor" not in b.L
        base = b.build({}, mission=False, W0=b.d["W0_lb"])[0]
        moved = b.build({"composite_factor": 1.0}, mission=False, W0=b.d["W0_lb"])[0]
        assert moved["components"] == base["components"] and moved["We"] == base["We"]
        assert base["We"] == sum(base["components"].values())


def test_composite_band_reaches_the_build_up():
    """With the `saving` line, composite_factor 1.00 gives the metal build-up of the record's own
    comparison, and the built aircraft gets heavier and loses endurance."""
    b, _ = built("saving", False)
    W0 = b.d["W0_lb"]
    nom = b.build({}, mission=False, W0=W0)[0]
    metal = b.build({"composite_factor": 1.0}, mission=False, W0=W0)[0]
    f = wts.COMPOSITE_FUDGE
    for name, key in (("wing", "wing"), ("horizontal_tail", "tails"), ("fuselage", "fuselage"), ("main_gear", "landing_gear")):
        assert metal["components"][name] == pytest.approx(nom["components"][name] / f[key], rel=1e-12)
    assert metal["components"]["avionics"] == nom["components"]["avionics"]
    # the record's build_up_metal leaves the sponsons at their composite factor 0.90 (uav.statistical_empty_fractions);
    # here they go to metal with the fuselage group, so the two differ by exactly that
    sponsons = nom["components"]["sponsons"]
    assert metal["components"]["sponsons"] == pytest.approx(sponsons / f["fuselage"], rel=1e-12)
    record_metal = b.d["empty_fraction_comparison"]["build_up_metal"] * W0
    assert metal["We"] == pytest.approx(record_metal + sponsons * (1.0 / f["fuselage"] - 1.0), rel=1e-6)
    assert b.w0_for({"composite_factor": 1.0}) > W0 + 100.0
    assert b.w0_for({"composite_factor": 0.90}) < W0 - 100.0


def test_empty_weight_factor_multiplies_the_sum():
    b, entries = built("saving", True)
    W0 = b.d["W0_lb"]
    nom = b.build({}, mission=False, W0=W0)[0]
    up = b.build({"empty_weight_factor": 1.05}, mission=False, W0=W0)[0]
    assert up["components"] == nom["components"]
    assert up["We"] == pytest.approx(1.05 * nom["We"], rel=1e-12)
    variables = {v["name"]: v for v in ig.uncertain_variables(entries)}
    assert ig.bounds(variables["empty_weight_factor"], 2.0)[:2] == pytest.approx((0.90, 1.10))
    assert ig.bounds(variables["composite_factor"], 2.0)[:2] == pytest.approx((0.85, 1.0))     # clipped at metal


def test_case_ledger_text():
    rec, cur = (FROZEN / "ledger.yaml").read_text(), uav.LEDGER.read_text()
    assert cb.case_ledger(rec, cur, None, False) == rec
    both = cb.case_ledger(rec, cur, "scale", True)
    added = [ln for ln in both.splitlines() if ln not in rec.splitlines()]
    assert len(added) == 2 and "{value: scale," in added[0] and added[1] == cb.ledger_line(cur, "empty_weight_factor")
    assert cb.ledger_line(cb.case_ledger(rec, cur, "saving", False), "composite_model") == cb.ledger_line(cur, "composite_model")


# ---- the committed record (runs/task12/stage3/2026-11-26/composite_band_study) ------------------------------
STUDY = ROOT / "runs/task12/stage3/2026-11-26/composite_band_study"
DOC = ROOT / "docs/validation/2026-11-26_task12_composite_band_study.md"


def test_recorded_study_reproduces_the_frozen_record_with_the_bands_off():
    res = json.loads((STUDY / "summary.json").read_text())
    assert res["reproduction"]["identical"] and not res["runs"][0]["code_dirty"]
    frozen = json.loads((FROZEN / "info_gap.json").read_text())["h_hat"]
    assert res["cases"]["bands_off"]["h_hat"]["R5_guarantee"] == frozen["R5_guarantee"]["h_hat"]
    assert res["cases"]["bands_off"]["new_variables_inert"] == {"composite_factor": True}
    for case in ("composite_saving", "composite_saving_empty_weight", "composite_scale", "composite_scale_empty_weight"):
        assert not any(res["cases"][case]["new_variables_inert"].values()), case
        assert (STUDY / case / "ledger.yaml").read_text() == cb.case_ledger(
            (FROZEN / "ledger.yaml").read_text(), uav.LEDGER.read_text(), *cb.CASES[case]), case


def test_report_is_the_generated_text_of_the_record():
    res = json.loads((STUDY / "summary.json").read_text())
    assert DOC.read_text() == cb.report_text(res, str(STUDY.relative_to(ROOT)))

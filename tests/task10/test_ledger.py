"""T10.1: the data ledger has a source for everything and a band for every assumption."""
import glob

import pytest
import yaml

from drone import ledger

FILES = ("air", "battery", "propulsion", "structure", "rules")
REQUIRED = {
    "air": {"density_kg_m3", "dynamic_viscosity_Pa_s"},
    "battery": {"pack_specific_energy_Wh_per_kg", "volumetric_energy_density_Wh_per_L", "depth_of_discharge"},
    "propulsion": {"propulsive_efficiency", "specific_power_W_per_kg"},
    "structure": {"skin_areal_density_kg_m2", "spar_allowable_stress_Pa", "limit_load_factor", "factor_of_safety"},
    "rules": {"payload_mass_kg", "tail_volume_horizontal", "tail_volume_vertical", "tail_arm_chords",
              "fuselage_fineness", "rate_of_climb_m_s", "climb_allowance_s", "mass_cap_kg"},
}


@pytest.mark.parametrize("name", FILES)
def test_every_quantity_has_units_source_confidence_and_a_band_if_assumed(name):
    with open(f"data/drone/{name}.yaml") as f:
        doc = yaml.safe_load(f)
    assert doc["set"] == f"drone/{name}"
    names = set()
    for q in doc["quantities"]:
        for key in ("name", "value", "units", "source", "confidence"):
            assert key in q, (name, q.get("name"), key)
        assert q["confidence"] in ("published", "derived", "assumed")
        assert len(q["source"]) > 20, (name, q["name"])
        if q["confidence"] == "assumed":
            lo, hi = q["band"]
            assert lo <= q["value"] <= hi and lo < hi, (name, q["name"])
        names.add(q["name"])
    assert REQUIRED[name] <= names, REQUIRED[name] - names


def test_loader_returns_values_and_quantities():
    assert ledger.load("rules")["payload_mass_kg"] == 0.5
    assert ledger.load("rules")["mass_cap_kg"] == 4.0
    q = ledger.quantity("battery", "pack_specific_energy_Wh_per_kg")
    assert q.confidence == "assumed" and q.band[0] < q.value < q.band[1]
    allq = ledger.load_all()
    assert set(allq) >= set(FILES)


def test_air_is_sea_level_isa():
    air = ledger.load("air")
    assert air["density_kg_m3"] == pytest.approx(1.225, rel=1e-4)
    assert air["dynamic_viscosity_Pa_s"] == pytest.approx(1.789e-5, rel=2e-3)


def test_validation_data_files_exist_with_sources():
    with open("data/validation/warren12.yaml") as f:
        w = yaml.safe_load(f)["warren12"]
    for key in ("root_chord", "tip_chord", "semispan", "sweep_le_deg", "moment_reference_x",
                "CL_alpha_per_rad", "Cm_alpha_per_rad", "source"):
        assert key in w, key
    assert w["CL_alpha_per_rad"] == pytest.approx(2.743, abs=1e-3)
    with open("data/validation/e387_uiuc.yaml") as f:
        e = yaml.safe_load(f)
    assert e["set"] == "validation/e387_uiuc" and "source" in e
    if e.get("retrieval") == "pending":
        pytest.skip("E387 polars not yet transcribed (retrieval pending; notebooks/12_drone_validation_data_colab.ipynb)")
    res = {p["reynolds"] for p in e["polars"]}
    assert {1e5, 2e5, 3e5} <= {float(r) for r in res}
    for p in e["polars"]:
        assert len(p["alpha_deg"]) == len(p["cl"]) == len(p["cd"]) >= 8


def test_assumptions_document_is_not_stale():
    """docs/drone_assumptions.md is generated; a byte comparison, as in tanker_comparison."""
    import subprocess
    out = subprocess.run(["python", "scripts/make_drone_assumptions.py", "--check"], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert glob.glob("docs/drone_assumptions.md")

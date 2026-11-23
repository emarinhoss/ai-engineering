"""The TP100 table (data/task12/tp100_table.json) against the App. K cycle it was built from."""
import json

import numpy as np
import pytest

from conceptual.engine_model import M250_TABLE, TP100_TABLE, TableEngine
from conceptual.units import KT, isa
from measurement import tp100_engine as tp
from measurement import turboprop_cycle as tc

ENG = TableEngine()


def _member():
    k, ref = tp.calibrated(**tp.NOMINAL)
    return k, ref


def test_table_records_its_cycle():
    assert ENG.meta["member"]["Tt4"] == tp.NOMINAL["Tt4"]
    assert ENG.meta["calibration_bsfc"] == tp.BSFC_RATED


@pytest.mark.parametrize("h, v", [(20000.0, 90.0), (21000.0, 97.0), (6000.0, 140.0)])
def test_power_available_matches_cycle(h, v):
    k, ref = _member()
    a = isa(h)
    direct = tc.full_throttle(ref, v * KT / a["a"], a["T"], a["p"], k, pi_c_max=ref["pi_c"])["shaft_hp"]
    assert ENG.power_available(h, v) == pytest.approx(direct, rel=0.01)


@pytest.mark.parametrize("h, v, frac", [(20000.0, 90.0, 0.5), (21000.0, 97.0, 0.42), (6000.0, 140.0, 0.73)])
def test_part_power_sfc_matches_cycle(h, v, frac):
    """Between grid nodes linear interpolation of a convex curve reads high; 2 % is allowed."""
    k, ref = _member()
    a = isa(h)
    shp = frac * ENG.power_available(h, v)
    direct = tc.shaft_power_at(ref, v * KT / a["a"], a["T"], a["p"], shp, k, pi_c_max=ref["pi_c"])["bsfc"]
    assert ENG.bsfc(h, v, shp) == pytest.approx(direct, rel=0.02)


def test_above_full_throttle_is_refused():
    with pytest.raises(ValueError):
        ENG.bsfc(20000.0, 90.0, 1.01 * ENG.power_available(20000.0, 90.0))


def test_lapse_is_rated_power_at_sea_level():
    assert ENG.lapse(0.0, 66.0) == pytest.approx(1.0, abs=0.01)


# ---- table_for_run: the engine table of a Stage 1 run, TP100 or M250 -------------------------------------------------
def test_table_for_run_finds_the_copy_in_the_run_folder(tmp_path):
    import shutil

    from conceptual.engine_model import M250_TABLE, TP100_TABLE, table_for_run
    shutil.copyfile(M250_TABLE, tmp_path / "m250_table.json")
    assert table_for_run(tmp_path) == tmp_path / "m250_table.json"
    other = tmp_path / "b"
    other.mkdir()
    shutil.copyfile(TP100_TABLE, other / "tp100_table.json")
    assert table_for_run(other) == other / "tp100_table.json"


def test_table_for_run_uses_the_recorded_hash_old_and_new_style(tmp_path):
    import hashlib
    import json

    from conceptual.engine_model import M250_TABLE, TP100_TABLE, table_for_run
    old = tmp_path / "old"
    old.mkdir()
    (old / "inputs.json").write_text(json.dumps({"tp100_table_sha256": hashlib.sha256(TP100_TABLE.read_bytes()).hexdigest(),
                                                 "commit": "HEAD"}))
    assert table_for_run(old) == TP100_TABLE                      # records before the M250 name only the TP100
    new = tmp_path / "new"
    new.mkdir()
    (new / "inputs.json").write_text(json.dumps({"engine_table_file": "m250_table.json", "commit": "HEAD",
                                                 "engine_table_sha256": hashlib.sha256(M250_TABLE.read_bytes()).hexdigest()}))
    assert table_for_run(new) == M250_TABLE
    (new / "inputs.json").write_text(json.dumps({"engine_table_file": "m250_table.json", "commit": "HEAD",
                                                 "engine_table_sha256": "0" * 64}))
    with pytest.raises(ValueError):                               # no table with that hash at that commit
        table_for_run(new)


def test_power_cap_is_clipped_at_the_rating_and_a_cap_below_one_cuts_power():
    """Owner ruling R-e, review MD-4: a cap above 1 cannot take the available power above the rating."""
    e = TableEngine(M250_TABLE)
    assert e.rated == 450.0
    for h, v in ((0.0, 90.0), (0.0, 140.0), (10000.0, 120.0), (20000.0, 120.0)):
        base = e.power_available(h, v)
        assert e.scaled(power_cap=1.1).power_available(h, v) <= 450.0 + 1e-9
        assert e.scaled(power_cap=1.1).power_available(h, v) == pytest.approx(min(450.0, base * 1.1))
        assert e.scaled(power_cap=0.9).power_available(h, v) == pytest.approx(0.9 * base)
    assert e.power_available(0.0, 140.0) == pytest.approx(450.0)            # sea level at the rating
    assert e.scaled(power_cap=1.1).power_available(0.0, 140.0) == pytest.approx(450.0)      # clipped
    assert e.power_available(20000.0, 120.0) < 400.0                         # well below the rating aloft
    assert e.scaled(power_cap=1.1).power_available(20000.0, 120.0) == pytest.approx(
        1.1 * e.power_available(20000.0, 120.0))                             # the cap still acts there
    assert json.loads(M250_TABLE.read_text())["rated_shp"] == 450.0


def test_tp100_available_power_is_bit_for_bit_the_pre_clip_formula():
    """The clip never acts for power_cap = 1 (every TP100 record, rescale path): same floats as min(rated, full) x scale."""
    e = TableEngine(TP100_TABLE)
    for power in (1.0, 0.9, 1.1, 360.0 / 241.0):
        for rerate in (False, True):
            m = e.scaled(sfc=1.05, power=power, rerate=rerate)
            for h in np.linspace(0.0, 25000.0, 11):
                for v in np.linspace(60.0, 160.0, 7):
                    old = min(m.rated, m._full_throttle(h, v)) * m.power_scale * m.power_cap
                    assert m.power_available(h, v) == old

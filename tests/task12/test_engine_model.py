"""The TP100 table (data/task12/tp100_table.json) against the App. K cycle it was built from."""
import pytest

from conceptual.engine_model import TableEngine
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

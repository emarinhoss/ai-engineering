"""Closing check of Gate A round 4: self-consistent V_max, margin rows, local refinement."""
import pytest

from conceptual import stage1, uav
from conceptual.units import HP, KT, isa
from measurement.rubber_tp100 import tp100_ledger_values


def _design():
    L = tp100_ledger_values()
    engs, _ = stage1.engine_options("PBS_TP100", 1.05)
    return uav.evaluate("pusher", 14.0, 9.5, L, engine=engs["PBS_TP100"]), L


def test_vmax_balances_thrust_and_drag_at_its_own_speed():
    d, L = _design()
    sl = isa(0.0)
    m = d["engine_model"]
    v = uav._vmax_consistent(d["W0"], d["geom"]["S"], d["geom"], L, sl, 0.0, d["K"], d["bhp"], m, 60.0 * KT)
    cd0, _ = uav._polar(d["geom"], L, v, sl, d["bhp"])
    thrust = HP * d["bhp"] * m.lapse(0.0, v / KT) * L["eta_p"] / v
    assert thrust == pytest.approx(uav.perf.drag(d["W0"], d["geom"]["S"], sl["rho"], v, cd0, d["K"]), rel=1e-3)


def _rows(margins):
    d, L = _design()
    Lm = dict(L, **margins)
    lay = {"sm_full": 0.1, "sm_empty": 0.1, "nose_load": {"full": 0.1, "empty": 0.1},
           "gear_track": {"half_track_ft": 4.0, "fits": True}, "prop_clearance_in": 12.0, "trim_ok": True,
           "rotation": {"CL_tail_needed": 0.5}}
    per = dict(uav.performance(d, L), service_ceiling_ft=L["ceiling_ft"] + 300.0)
    comp = stage1.compliance(d, Lm, lay, per, 10.0, 20.0, {"max_operating_altitude_ft": 29528.0})
    return {c["requirement"].split(",")[0][:22]: c for c in comp}


def test_margins_tighten_the_ceiling_row():
    bare = _rows({"margin_ceiling_ft": 0.0})
    tight = _rows({"margin_ceiling_ft": 500.0})
    key = "R12 service ceiling (l"
    assert bare[key]["met"] is True and tight[key]["met"] is False


def test_refine_moves_to_a_lighter_compliant_neighbour(monkeypatch):
    weights = {(10.0, 9.0): 3000.0, (10.5, 9.0): 2990.0, (11.0, 9.0): 2985.0}

    def fake_analyse(concept, W_S, A, L, engine):
        return {"design": {"W0": weights.get((W_S, A), 3100.0), "ledger_used": L, "ok": (W_S, A) in weights},
                "layout": None, "performance": None, "fuel_volume": (0, 0)}

    def fake_compliance(d, L, lay, per, need, avail, eng_raw):
        return [{"requirement": "x", "met": d["ok"]}]
    monkeypatch.setattr(stage1, "analyse", fake_analyse)
    monkeypatch.setattr(stage1, "compliance", fake_compliance)
    tried = [{"W_S": 10.0, "A": 9.0, "W0": 3000.0, "failed": []}]
    a, best = stage1._refine("pusher", fake_analyse("p", 10.0, 9.0, {}, None), tried[0], 30.0, {}, None, {}, tried)
    assert (best["W_S"], best["A"]) == (11.0, 9.0) and a["design"]["W0"] == 2985.0


def test_wind_limit_at_design_payload_is_the_design_wind_and_payload_buys_wind():
    d, L = _design()
    engs, _ = stage1.engine_options("PBS_TP100", 1.05)
    lim = stage1.wind_limits(d, engs["PBS_TP100"], payloads=(500.0, 400.0))
    assert lim["500"] == pytest.approx(L["headwind_kt"], abs=0.1)
    assert lim["400"] > lim["500"]

from pathlib import Path

import pytest

from cases.check_keys import unknown_keys
from cases.config import render

SU2_TEMPLATE = Path(__file__).parents[1] / "cases" / "su2_v8.2.0_config_template.cfg"

EXTRA = {"nodes": 100, "cells": 80, "level": "medium", "first_cell_m": {"body": 2e-5}}
MARKERS = {
    "wedge": ["body", "symmetry", "inlet", "top", "outlet"],
    "inlet2r": ["body", "cowl", "symmetry", "inlet", "top", "outlet_duct", "outlet_ext"],
    "cylinder": ["wall", "symmetry", "farfield", "outlet"],
}


def markers(family):
    return {**{m: [1, 2] for m in MARKERS[family]}, **EXTRA}


def params(family="wedge", **kw):
    return {"family": family, "solver": "NAVIER_STOKES", "theta1_deg": 10.0, "tag": "test", **kw}


def lines(cfg):
    return [ln.strip() for ln in cfg.splitlines()]


@pytest.mark.parametrize("family", list(MARKERS))
@pytest.mark.parametrize("solver", ["EULER", "NAVIER_STOKES"])
def test_every_marker_present_and_no_other(family, solver):
    cfg = render(params(family, solver=solver), {}, markers(family))
    marker_lines = [ln for ln in lines(cfg) if ln.startswith("MARKER_")]
    named = set()
    for ln in marker_lines:
        body = ln.split("=", 1)[1]
        if ln.startswith("MARKER_ANALYZE_AVERAGE"):
            continue
        named |= {t.strip() for t in body.replace("(", " ").replace(")", " ").split(",")
                  if t.strip() and not t.strip().replace(".", "").isdigit()}
    assert named == set(MARKERS[family])


def test_required_values():
    cfg = lines(render(params(), {}, markers("wedge")))
    for line in ["MACH_NUMBER= 4.0", "FREESTREAM_TEMPERATURE= 226.509",
                 "FREESTREAM_PRESSURE= 1197.03", "REF_DIMENSIONALIZATION= DIMENSIONAL",
                 "KIND_TURB_MODEL= NONE", "ITER= 6000", "CONV_NUM_METHOD_FLOW= ROE", "ENTROPY_FIX_COEFF= 0.3",
                 "MARKER_ISOTHERMAL= ( body, 300.0 )", "MARKER_SYM= ( symmetry )",
                 "MARKER_FAR= ( inlet, top )", "MARKER_SUPERSONIC_OUTLET= ( outlet )",
                 "MARKER_MONITORING= ( body )", "OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII )"]:
        assert line in cfg


def test_euler_vs_navier_stokes():
    euler = render(params(solver="EULER"), {}, markers("wedge"))
    ns = render(params(), {}, markers("wedge"))
    assert "MARKER_EULER= ( body )" in euler and "MARKER_ISOTHERMAL" not in euler
    assert "SOLVER= EULER" in lines(euler)
    assert "HEAT" not in euler.split("HISTORY_OUTPUT=")[1].splitlines()[0]
    assert "MARKER_ISOTHERMAL= ( body, 300.0 )" in lines(ns) and "MARKER_EULER" not in ns
    assert "SOLVER= NAVIER_STOKES" in lines(ns)
    assert "HEAT" in ns.split("HISTORY_OUTPUT=")[1].splitlines()[0]


def test_inlet_analyze_and_wall_temperature():
    cfg = lines(render(params("inlet2r", T_wall_K=450.0), {}, markers("inlet2r")))
    assert "MARKER_ISOTHERMAL= ( body, 450.0, cowl, 450.0 )" in cfg
    assert "MARKER_ANALYZE= ( outlet_duct )" in cfg
    assert "MARKER_ANALYZE_AVERAGE= MASSFLUX" in cfg
    assert "MARKER_PLOTTING= ( body, cowl, outlet_duct )" in cfg
    assert "MARKER_MONITORING= ( body, cowl )" in cfg
    wedge = render(params(), {}, markers("wedge"))
    assert "MARKER_ANALYZE" not in wedge


def test_save_volume_and_options():
    cfg = lines(render(params(save_volume=True, mach=5.0, max_iter=4000), {}, markers("wedge")))
    assert "OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII, TECPLOT_ASCII )" in cfg
    assert "MACH_NUMBER= 5.0" in cfg and "ITER= 4000" in cfg


def test_marker_mismatch_raises():
    missing = markers("wedge")
    del missing["top"]
    with pytest.raises(ValueError, match="top"):
        render(params(), {}, missing)
    extra = {**markers("wedge"), "spare": [1]}
    with pytest.raises(ValueError, match="spare"):
        render(params(), {}, extra)


def test_deterministic():
    a = render(params(), {"X_w": 0.15}, markers("wedge"))
    b = render(params(), {"X_w": 0.15}, markers("wedge"))
    assert a == b


@pytest.mark.skipif(not SU2_TEMPLATE.exists(), reason="SU2 v8.2.0 config_template.cfg not downloaded")
@pytest.mark.parametrize("solver", ["EULER", "NAVIER_STOKES"])
@pytest.mark.parametrize("family", list(MARKERS))
def test_no_unknown_su2_keys(solver, family):
    cfg = render(params(family, solver=solver, save_volume=True), {}, markers(family))
    assert unknown_keys(cfg, SU2_TEMPLATE.read_text()) == []

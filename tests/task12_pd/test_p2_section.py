"""Preliminary design P2 (docs/specs/task12_preliminary_design.md, "P2. Wing section and section data"): the
acceptance tests of the package, written before prelim/p2_section.py.

The methods are tested here on made-up inputs with known answers and on the committed source file; the tests of
the committed P2 record are in test_p2_record.py. Tolerances are the spec's or are fixed here before any run; a
test may not loosen one. No test requires an acceptance row to pass: a section outside the band is a result.
"""
import json
import math

import pytest
import yaml

from conceptual import raymer_aero as aero
from conceptual import uav
from conceptual.units import KT, isa
from measurement import info_gap
from prelim import p2_section as p2

R0_DESIGN = json.loads((p2.R0 / "design_pusher.json").read_text())
LEDGER, ENTRIES = uav.load_ledger(p2.R0 / "ledger.yaml")
SOURCE = yaml.safe_load(p2.SOURCE.read_text())


# ---- the numbers fixed before the run ------------------------------------------------------------------
def test_tolerances_and_bands_are_the_ones_fixed_in_the_spec():
    assert p2.R0 == p2.REPO / "runs/task12/pd/2026-11-27/p0/r0"
    assert p2.CL_MAX_BAND == (1.3, 1.7) == tuple(ENTRIES["airfoil_cl_max"]["band"])        # row 1, spec 7.1a
    assert p2.CM0_BAND == (-0.10, -0.04) == tuple(ENTRIES["airfoil_cm0"]["band"])          # row 3
    assert p2.RECORD_CL_MAX_CLEAN == 1.35 == pytest.approx(R0_DESIGN["CL_max"]["clean"], abs=1e-12)   # row 2
    assert (p2.SU2_TOL_SLOPE, p2.SU2_TOL_CL0, p2.SU2_TOL_CLMAX) == (0.05, 0.05, 0.10)     # row 5
    assert p2.LINEAR_RANGE_DEG == (-6.0, 6.0)            # where the lift curve is fitted by a straight line
    assert p2.WING_SECTION == "naca4415" and p2.TAIL_SECTION == "naca0012"                # PD-5
    # gross-error check of the digitized points against thin-airfoil theory (not a spec row; fixed here)
    assert (p2.TOL_ALPHA0_DEG, p2.SLOPE_RATIO_RANGE) == (1.0, (0.85, 1.15))


# ---- the source: the committed file is the archive's file, and the record of it tells the truth ---------------
def test_committed_source_files_are_the_ones_the_source_record_names():
    for name, f in SOURCE["digitization"]["files"].items():
        if f["committed_as"] is None:
            continue
        assert p2.sha256(p2.REPO / f["committed_as"]) == f["sha256"], name
        assert SOURCE["digitization"]["commit"] in f["url"]
    assert SOURCE["sections"]["naca4415"]["file"] == "142.ALL" and SOURCE["sections"]["naca4415"]["page"] == 142
    index = (p2.DATA / "NACA.LST").read_text()
    assert any(line.split() == ["142.all", "NACA", "4415"] for line in index.splitlines())
    assert not any(line.split()[-1:] == ["0012"] for line in index.splitlines())            # no 0012 in the archive


def test_source_record_says_what_was_not_done():
    assert SOURCE["report"]["opened_in_this_session"] is False and SOURCE["reading"]["read_twice"] is False
    assert SOURCE["sections"]["naca4415"]["page_checked_against_the_report"] is False
    assert SOURCE["sections"]["naca4415"]["figure"] is None
    assert SOURCE["sections"]["naca0012"]["status"] == "not obtained"
    assert any(b["host"] == "ntrs.nasa.gov" and "403" in b["error"] for b in SOURCE["report"]["blocked"])
    for path in p2.DATA.iterdir():
        assert "@" not in path.read_text(), path                                           # no e-mail address committed


# ---- the loader -------------------------------------------------------------------------------------------------
SAMPLE = """  alpha,  Cl(or Cm[c/4] for ranges 7-12)
 Data set
   1
   2.000000    0.60000000
   -.500000     .35000000
 Data set
   2
 Data set           2 does not exist.
 Data set
   7
   2.000000    -.09000000
 Found           1 double points.
  Cl,  Cd(or Cm[a.c.] for ranges 7-12)
 Data set
   1
    .600000     .00700000
 Data set
   7
    .600000    -.09500000
 Alpha, Cl, Cd(interpolated)
 Data set
   1
   2.000000     .600000     .00700000
"""


def test_parser_reads_the_four_blocks_and_skips_missing_sets_and_the_interpolated_block():
    d = p2.parse_digitized(SAMPLE)
    assert d == {"alpha_cl": {1: [(2.0, 0.6), (-0.5, 0.35)]}, "alpha_cm": {7: [(2.0, -0.09)]},
                 "cl_cd": {1: [(0.6, 0.007)]}, "cl_cmac": {7: [(0.6, -0.095)]}}


def test_parser_on_the_committed_file():
    d = p2.load_section("naca4415")
    assert sorted(d["alpha_cl"]) == [1, 2, 3, 4, 5] and sorted(d["alpha_cm"]) == [7, 8, 9]
    assert sorted(d["cl_cd"]) == [1, 2, 3, 4] and sorted(d["cl_cmac"]) == [7, 8, 9]
    assert [len(d["alpha_cl"][k]) for k in (1, 2, 3, 4)] == [15, 19, 18, 13]
    assert d["alpha_cl"][1][0] == (20.4159, 1.21442)                    # first line of the file's first set
    raw = (p2.DATA / "142.ALL").read_text()
    assert " 20.415900    1.21442000" in raw
    with pytest.raises(ValueError, match="not obtained"):
        p2.load_section("naca0012")


# ---- step 1: Reynolds and Mach numbers ---------------------------------------------------------------------------
def test_chord_reynolds_and_mach_are_the_definitions():
    a = isa(0.0)
    r = p2.chord_reynolds_mach(100.0, 2.0, a)
    assert r["reynolds"] == pytest.approx(a["rho"] * 100.0 * 2.0 / a["mu"], rel=1e-12)
    assert r["mach"] == pytest.approx(100.0 / a["a"], rel=1e-12)
    assert 6.2e6 < p2.chord_reynolds_mach(100.0, 1.0, a)["reynolds"] * 10 < 6.5e6   # sea level: about 6,400 per ft/s per ft


def test_flight_conditions_are_r0s_speeds_and_chords():
    rows = p2.reynolds_table(R0_DESIGN, LEDGER)
    by = {(r["condition"], r["station"]): r for r in rows}
    assert {r["station"] for r in rows} == {"root", "mean", "tip"}
    assert {r["condition"] for r in rows} >= {"stall, sea level, W0", "loiter, mission altitude", "cruise out, mission altitude"}
    stall = by[("stall, sea level, W0", "mean")]
    assert stall["V_kt"] == pytest.approx(R0_DESIGN["performance"]["V_stall_clean_kt"], rel=1e-12)
    a = isa(0.0)
    assert stall["reynolds"] == pytest.approx(a["rho"] * stall["V_kt"] * KT * R0_DESIGN["wing"]["mac"] / a["mu"], rel=1e-12)
    loiter = by[("loiter, mission altitude", "tip")]
    row = next(m for m in R0_DESIGN["mission"] if m["segment"] == "loiter")
    assert loiter["V_kt"] == pytest.approx(row["V_kt"], rel=1e-12) and loiter["altitude_ft"] == LEDGER["mission_altitude_ft"]
    assert loiter["chord_ft"] == R0_DESIGN["wing"]["tip_chord"]
    assert by[("stall, sea level, W0", "root")]["reynolds"] > stall["reynolds"] > by[("stall, sea level, W0", "tip")]["reynolds"]


def test_nearest_tabulated_reynolds_number_is_nearest_by_ratio():
    table = [3.0e6, 6.0e6, 9.0e6]
    assert p2.nearest_reynolds(3.5e6, table) == 3.0e6
    assert p2.nearest_reynolds(math.sqrt(18.0) * 1e6 * 0.999, table) == 3.0e6      # the boundary is the geometric mean
    assert p2.nearest_reynolds(math.sqrt(18.0) * 1e6 * 1.001, table) == 6.0e6
    assert p2.nearest_reynolds(2.0e6, table) == 3.0e6 and p2.nearest_reynolds(2.0e7, table) == 9.0e6


# ---- step 2: what is read off a set of points ----------------------------------------------------------------
def test_line_fit_returns_slope_zero_lift_angle_and_scatter():
    pts = [(a, 0.1 * (a + 4.0)) for a in (-8.0, -6.0, -3.0, 0.0, 2.5, 6.0, 9.0)]
    f = p2.line_fit(pts, (-6.0, 6.0))
    assert f["n_points"] == 5
    assert f["slope_per_deg"] == pytest.approx(0.1, rel=1e-12) and f["cl_at_zero"] == pytest.approx(0.4, rel=1e-12)
    assert f["alpha_zero_lift_deg"] == pytest.approx(-4.0, rel=1e-12) and f["rms_residual"] == pytest.approx(0.0, abs=1e-12)
    bumped = [(a, cl + (0.02 if i % 2 else -0.02)) for i, (a, cl) in enumerate(pts)]
    assert 0.0 < p2.line_fit(bumped, (-6.0, 6.0))["rms_residual"] <= 0.02


def test_section_summary_takes_the_highest_and_lowest_plotted_points():
    lift = [(-14.0, -0.80), (-12.0, -0.85), (-6.0, -0.2), (0.0, 0.4), (6.0, 1.0), (12.0, 1.40), (14.0, 1.45), (16.0, 1.30)]
    moment = [(-8.0, -0.02), (-6.0, -0.09), (0.0, -0.10), (6.0, -0.08), (14.0, -0.01)]
    s = p2.section_summary(lift, moment, [(0.4, 0.0065), (0.0, 0.0070), (1.0, 0.0100)])
    assert (s["cl_max"], s["alpha_cl_max_deg"]) == (1.45, 14.0)
    assert (s["cl_min"], s["alpha_cl_min_deg"]) == (-0.85, -12.0) and s["cl_min_is_a_turning_point"] is True
    assert s["cm_c4_linear_range"] == pytest.approx(-0.09, rel=1e-12) and s["cm_n_points"] == 3
    assert (s["cd_min"], s["cl_at_cd_min"]) == (0.0065, 0.4)
    assert s["fit"]["slope_per_deg"] == pytest.approx(0.1, rel=1e-9)
    # the lowest point is the last one measured: the data does not show the negative stall
    s2 = p2.section_summary(lift[1:], moment, None)
    assert s2["cl_min"] == -0.85 and s2["cl_min_is_a_turning_point"] is False and s2["cd_min"] is None


# ---- gross-error check: thin-airfoil theory ---------------------------------------------------------------------
def test_thin_airfoil_zero_lift_angle_of_a_parabolic_arc_and_of_a_flat_plate():
    h = 0.03                                             # parabolic arc z = 4 h x (1 - x): alpha_0L = -2 h rad
    assert p2.thin_airfoil_alpha0_deg(lambda x: 4.0 * h * (1.0 - 2.0 * x)) == pytest.approx(math.degrees(-2.0 * h), rel=1e-6)
    assert p2.thin_airfoil_alpha0_deg(lambda x: 0.0 * x) == pytest.approx(0.0, abs=1e-12)


def test_naca_four_digit_camber_slope():
    m, p = 0.04, 0.4
    slope = p2.naca4_camber_slope(m, p)
    assert float(slope(0.4)) == pytest.approx(0.0, abs=1e-15)                              # maximum camber at 0.4 chord
    assert float(slope(0.0)) == pytest.approx(2.0 * m / p, rel=1e-12)
    assert float(slope(1.0)) == pytest.approx(-2.0 * m / (1.0 - p), rel=1e-12)
    assert -5.0 < p2.thin_airfoil_alpha0_deg(slope) < -3.5                                 # 4 % camber: a few degrees


# ---- step 3: wing maximum lift ----------------------------------------------------------------------------------
def test_leading_edge_sweep_of_a_tapered_wing_with_an_unswept_quarter_chord():
    assert p2.leading_edge_sweep_deg(5.0, 5.0, 40.0) == 0.0
    assert p2.leading_edge_sweep_deg(8.0, 4.0, 40.0) == pytest.approx(math.degrees(math.atan(1.0 / 20.0)), rel=1e-12)


def test_wing_maximum_lift_routes():
    w = p2.wing_cl_max(1.40, LEDGER)
    assert w["clean_12_15"] == pytest.approx(0.9 * 1.40, rel=1e-12) == pytest.approx(aero.wing_cl_max(1.40), rel=1e-12)
    assert w["clean_12_16_zero_sweep"] == pytest.approx(w["clean_12_15"], rel=1e-12)       # Fig. 12.8 starts at 0.9
    expected = uav._cl_max(dict(LEDGER, airfoil_cl_max=1.40))                              # as Stage 1 (12.21)
    for k in ("clean", "takeoff", "landing"):
        assert w[k] == pytest.approx(expected[k], rel=1e-12)
    at_record = p2.wing_cl_max(LEDGER["airfoil_cl_max"], LEDGER)
    for k in ("clean", "takeoff", "landing"):
        assert at_record[k] == pytest.approx(R0_DESIGN["CL_max"][k], rel=1e-12)


# ---- verdicts ------------------------------------------------------------------------------------------------------
def test_row_verdicts_follow_from_the_numbers():
    assert p2.verdict_band(1.30, p2.CL_MAX_BAND) == "pass" and p2.verdict_band(1.70, p2.CL_MAX_BAND) == "pass"
    assert p2.verdict_band(1.29, p2.CL_MAX_BAND) == "outside the band"
    assert p2.verdict_band(-0.11, p2.CM0_BAND) == "outside the band" and p2.verdict_band(-0.09, p2.CM0_BAND) == "pass"
    assert p2.verdict_wing(1.34, 1.35) == "finding for r1" and p2.verdict_wing(1.35, 1.35) == "pass (not lower)"


def test_computed_polar_against_measured_uses_the_row_5_tolerances():
    measured = {"fit": {"slope_per_deg": 0.100, "cl_at_zero": 0.40}, "cl_max": 1.45}
    good = p2.compare_computed({"fit": {"slope_per_deg": 0.104, "cl_at_zero": 0.44}, "cl_max": 1.54}, measured)
    assert good["within"] == {"slope": True, "cl_at_zero": True, "cl_max": True} and good["all_within"] is True
    assert good["slope_relative_difference"] == pytest.approx(0.04, rel=1e-9)
    bad = p2.compare_computed({"fit": {"slope_per_deg": 0.106, "cl_at_zero": 0.46}, "cl_max": 1.80}, measured)
    assert bad["within"] == {"slope": False, "cl_at_zero": False, "cl_max": False} and bad["all_within"] is False
    assert bad["cl_max_difference"] == pytest.approx(0.35, rel=1e-9)


XFOIL_SAMPLE = """
       XFOIL         Version 6.99

 Calculated polar for: NACA 4415

 xtrf =   1.000 (top)        1.000 (bottom)
 Mach =   0.080     Re =     3.000 e 6     Ncrit =   9.000  9.000

   alpha    CL        CD       CDp       CM     Top_Xtr  Bot_Xtr  Top_Itr  Bot_Itr
  ------ -------- --------- --------- -------- -------- -------- -------- --------
   0.000   0.4820   0.00650   0.00044  -0.1035   0.4849   0.2501  31.6359 119.5453
   1.000   0.5962   0.00647   0.00047  -0.1038   0.4597   0.3391  33.0707 124.2155
"""


def test_xfoil_polar_file_is_parsed_row_by_row():
    rows = p2.parse_xfoil_polar(XFOIL_SAMPLE)
    assert rows == [{"alpha_deg": 0.0, "cl": 0.4820, "cd": 0.00650, "cm": -0.1035},
                    {"alpha_deg": 1.0, "cl": 0.5962, "cd": 0.00647, "cm": -0.1038}]


# ---- R17 re-flown: the built aircraft with another section maximum lift ----------------------------------------
@pytest.fixture(scope="module")
def built():
    return info_gap.Built(p2.R0 / "design_pusher.json")


def test_refly_at_the_records_value_is_r0(built):
    r = p2.refly(built, LEDGER["airfoil_cl_max"])
    loiter = next(m for m in R0_DESIGN["mission"] if m["segment"] == "loiter")
    assert r["hours_on_station"] == pytest.approx(loiter["leg_time_h"], abs=0.002)
    assert r["loiter_speed_kt"] == pytest.approx(loiter["V_kt"], rel=2e-4)
    assert r["loiter_floor_fraction"] == loiter["speed_floor_fraction"]
    assert r["W0_lb"] == pytest.approx(R0_DESIGN["W0_lb"], abs=info_gap.W0_TOL_LB)      # the weight fixed point of Built
    assert r["V_stall_clean_sl_kt"] == pytest.approx(R0_DESIGN["performance"]["V_stall_clean_kt"], rel=1e-6)
    assert r["takeoff_ft"] == pytest.approx(R0_DESIGN["performance"]["takeoff_ft"], rel=1e-6)
    assert r["landing_ft"] == pytest.approx(R0_DESIGN["performance"]["landing_ft"], rel=1e-6)


def test_refly_with_less_maximum_lift_loiters_faster_and_shorter(built):
    base, low = p2.refly(built, LEDGER["airfoil_cl_max"]), p2.refly(built, 1.40)
    assert low["CL_max"]["clean"] == pytest.approx(0.9 * 1.40, rel=1e-12)
    assert low["V_stall_clean_sl_kt"] == pytest.approx(base["V_stall_clean_sl_kt"] * math.sqrt(1.5 / 1.40), rel=1e-9)
    assert low["hours_on_station"] < base["hours_on_station"]
    assert low["loiter_speed_kt"] > base["loiter_speed_kt"]
    assert low["W0_lb"] == pytest.approx(base["W0_lb"], abs=1e-6)       # the aircraft is not re-sized

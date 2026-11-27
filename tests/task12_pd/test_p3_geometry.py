"""Preliminary design P3, lofted geometry and geometry gates (spec docs/specs/task12_preliminary_design.md, P3).

Acceptance tests of the package: the tolerances are the spec's (gate 3: 5 %, gate 8: 2 %, gates 2 and 7: 1e-9) or
are fixed here (gate 5's bound, the printed-table tolerances). The tests of a gate check that the gate measures what
it says, on shapes with known answers; they do not require r0's loft to pass a gate. What r0's loft gave is in the
record and its tests (test_p3_record.py).
"""
import json
import math

import numpy as np
import pytest
import yaml

from geometry3d import aircraft as ac
from geometry3d import fuselage as fz
from geometry3d import gates, mesh, sections
from geometry3d.surfaces import Ellipsoid, LiftingSurface
from prelim import p3_loft as p3


@pytest.fixture(scope="module")
def src():
    return yaml.safe_load(p3.TAIL_SOURCE.read_text())


@pytest.fixture(scope="module")
def loft():
    d, L, A = p3.inputs()
    m = ac.build(d, L, A)
    return d, L, A, m, ac.meshes(m)


# ---- tolerances are the spec's -------------------------------------------------------------------------------
def test_tolerances_are_the_specs():
    assert gates.TOL_WETTED == 0.05 and gates.TOL_OPENVSP == 0.02
    assert gates.TOL_TARGET == 1e-9 and gates.TOL_ROUND_TRIP == 1e-9
    assert (gates.SMOOTH_STEPS, gates.SMOOTH_FROM, gates.SMOOTH_BOUND) == (4000, 0.05, 0.01)


# ---- sections: printed targets from the open reports ------------------------------------------------------
def test_thickness_polynomial_gives_the_printed_ordinates_of_report_460(src):
    t = src["section_equations"]["basic_ordinates_20_percent"]
    x = np.array(t["station_percent"]) / 100.0
    assert 100.0 * sections.thickness(x, 0.20) == pytest.approx(t["ordinate_percent"], abs=0.001)
    assert list(sections.THICKNESS_COEFFS) == src["section_equations"]["thickness"]["coefficients"]


def test_naca0012_of_the_loft_is_the_section_report_586_tested(src):
    t = src["section_equations"]["naca0012_ordinates"]
    x = np.array(t["station_percent"]) / 100.0
    assert 100.0 * sections.thickness(x, 0.12) == pytest.approx(t["ordinate_percent"], abs=0.0015)
    xs, zs = sections.naca4("0012", 41)
    assert zs == pytest.approx(-zs[::-1], abs=1e-15) and xs == pytest.approx(xs[::-1], abs=1e-15)   # symmetrical


def test_cambered_section_follows_the_reports_rule():
    """Report 460, p. 5: maximum mean-line ordinate m at x = p; the surfaces lie y_t either side of the mean line,
    at right angles to it."""
    y, dy = sections.mean_line(np.array([0.0, 0.4, 1.0]), 0.04, 0.4)
    assert y == pytest.approx([0.0, 0.04, 0.0], abs=1e-15) and dy[1] == pytest.approx(0.0, abs=1e-15)
    x = np.array([0.1, 0.3, 0.7])
    (xu, zu), (xl, zl) = sections.surfaces(x, 0.04, 0.4, 0.15)
    yc, dyc = sections.mean_line(x, 0.04, 0.4)
    assert np.hypot(xu - xl, zu - zl) == pytest.approx(2 * sections.thickness(x, 0.15), rel=1e-12)
    assert (zu - zl) / (xu - xl) == pytest.approx(-1.0 / dyc, rel=1e-9)            # the chord through the mean line is normal to it
    assert 0.5 * (zu + zl) == pytest.approx(yc, abs=1e-15)


def test_sources_are_recorded_and_no_pdf_is_committed(src):
    for key, ntrs in (("tr586", "19930091662"), ("tr460", "19930091108"), ("tr824", "19930090976")):
        r = src["reports"][key]
        assert r["ntrs_id"] == ntrs and ntrs in r["url"] and r["url"].startswith("https://ntrs.nasa.gov/") and len(r["pdf_sha256"]) == 64
    assert src["reports"]["tr824"]["pdf_sha256"] == yaml.safe_load(
        (p3.REPO / "data/task12/pd_p2_section_source.yaml").read_text())["report"]["pdf_sha256"]
    assert not list(p3.REPO.glob("data/task12/**/*.pdf")) and not list(p3.REPO.glob("geometry3d/**/*.pdf"))


def test_naca0012_table_rows(src):
    n = src["naca0012"]
    rows = [dict(zip(n["columns"], r)) for r in n["rows"]]
    assert len(rows) == 7 and all(r["alpha_l0_deg"] == 0 and r["cl_opt"] == 0 for r in rows)
    first = rows[0]                                             # the row Table II repeats
    assert (first["reynolds_millions"], first["cl_max"], first["a0_per_deg"], first["cd0_min"]) == (8.37, 1.66, 0.099, 0.0069)
    assert "1.66" in n["cross_check"] and "0.099" in n["cross_check"] and "0.0069" in n["cross_check"]
    by_R = sorted(rows, key=lambda r: r["reynolds_millions"])
    assert [r["cl_max"] for r in by_R[:-1]] == sorted(r["cl_max"] for r in by_R[:-1])      # maximum lift rises with R
    assert "not measured" in n["negative_cl_max"].lower()


def test_tail_reynolds_numbers_and_interpolation(loft):
    d, L = loft[0], loft[1]
    t = p3.tail_section(d, L)
    stall = t["conditions"]["stall, clean, sea level"]["horizontal_tail"]
    atm = p3.uav.isa(0.0)
    assert stall["reynolds"] == pytest.approx(atm["rho"] * d["performance"]["V_stall_clean_kt"] * p3.KT * d["horizontal_tail"]["mac"] / atm["mu"])
    lo, hi = (next(r for r in t["rows"] if r["reynolds_millions"] == v) for v in (1.74, 3.54))
    assert 1.74e6 < stall["reynolds"] < 3.54e6 and lo["cl_max"] < stall["cl_max"] < hi["cl_max"]
    assert stall["cl_max_negative"] == -stall["cl_max"]
    for c in t["conditions"].values():
        for tail in ("horizontal_tail", "vertical_tail"):
            assert c[tail]["inside_table"]


# ---- conics: Raymer (7.2)-(7.4) ------------------------------------------------------------------------------
def test_conic_is_raymers_construction():
    A, B, C = np.array([0.0, 2.0]), np.array([3.0, 0.5]), np.array([2.5, 2.4])
    for rho in (0.3, 0.4142, 0.5, 0.7):
        p = fz.conic(A, B, C, rho, 201)
        assert p[0] == pytest.approx(A) and p[-1] == pytest.approx(B)
        D = 0.5 * (A + B)
        assert p[100] == pytest.approx(D + rho * (C - D), abs=1e-14)                      # shoulder point, (7.2)
        t0, t1 = p[1] - p[0], p[-1] - p[-2]
        cross = lambda u, v: abs(u[0] * v[1] - u[1] * v[0]) / (np.linalg.norm(u) * np.linalg.norm(v))
        assert cross(t0, C - A) < 2e-2 and cross(t1, B - C) < 2e-2                        # leaves A along AC, arrives along CB


def test_conic_printed_cases_of_7_4():
    c = gates.conic_targets()
    assert c["circle_radius_error_exact_rho"] < 1e-12            # rho = sqrt(2) - 1, equal tangents: a circular arc
    assert c["circle_radius_error_printed_rho"] < 1e-4           # 0.4142 as printed: a circle to its rounding
    assert c["parabola_error"] < 1e-12                           # rho = 0.5: a parabola
    assert fz.RHO_CIRCLE == pytest.approx(0.4142, abs=5e-5)
    assert np.abs(np.linalg.norm(fz.conic((0, 1), (1, 0), (1, 1), 0.5, 51), axis=1) - 1.0).max() > 0.01   # and 0.5 is not a circle


def test_inside_section_agrees_with_the_outline():
    for rho in (0.4142, 0.6, 0.7):
        ring = fz.section_ring(1.2, 0.9, 1.5, rho, 13)
        assert len(ring) == 48
        assert fz.inside_section(0.999 * ring[:, 0], 0.999 * ring[:, 1], 1.2, 0.9, 1.5, rho).all()
        assert not fz.inside_section(1.001 * ring[:, 0], 1.001 * ring[:, 1], 1.2, 0.9, 1.5, rho).any()


# ---- mesh: watertight, area, volume, STL ------------------------------------------------------------------
def box_mesh():
    ring = np.array([[0, 0, 0], [0, 2, 0], [0, 2, 3], [0, 0, 3]], dtype=float)
    return mesh.loft(np.array([ring + [x, 0, 0] for x in (0.0, 1.0, 4.0)]))


def test_loft_of_a_box_has_its_area_and_volume():
    V, T = box_mesh()
    assert mesh.area(V, T) == pytest.approx(2 * (2 * 3 + 4 * 2 + 4 * 3), rel=1e-14)
    assert mesh.volume(V, T) == pytest.approx(24.0, rel=1e-14)
    assert mesh.watertight(V, T)["ok"]


def test_watertight_gate_refuses_a_hole_and_a_turned_triangle():
    V, T = box_mesh()
    hole = mesh.watertight(V, T[1:])
    assert not hole["ok"] and hole["edges_unmatched"] == 3
    turned = T.copy()
    turned[0] = turned[0][::-1]
    bad = mesh.watertight(V, turned)
    assert not bad["ok"] and bad["edges_repeated"] > 0
    assert not mesh.watertight(V, T[:, ::-1])["ok"]              # all normals inward: negative volume


def test_ellipsoid_mesh_converges_to_the_sphere():
    e = Ellipsoid((1.0, 2.0, 3.0), 2.0, 2.0, 2.0)
    V, T = mesh.loft(e.rings(96, 96), *e.ends())
    assert mesh.watertight(V, T)["ok"]
    assert mesh.area(V, T) == pytest.approx(4 * math.pi * 4.0, rel=2e-3)
    assert mesh.volume(V, T) == pytest.approx(4 / 3 * math.pi * 8.0, rel=2e-3)
    assert e.inside([[1.0, 2.0, 4.9]])[0] and not e.inside([[1.0, 2.0, 5.1]])[0]


def test_stl_round_trip_is_exact(tmp_path):
    e = Ellipsoid((0.1, 0.2, 0.3), 1.3, 0.7, 0.9)
    parts = {"box": box_mesh(), "body": mesh.loft(e.rings(12, 12), *e.ends())}
    g = gates.gate7_round_trip(parts, tmp_path / "t.stl")
    assert g["verdict"] == "pass" and g["largest_relative_difference"] <= 1e-9
    assert (tmp_path / "t.stl").read_text().startswith("solid box")


# ---- lifting surfaces --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("taper", [0.3, 0.45, 1.0])
def test_mean_chord_from_the_loft_equals_raymer_7_8_and_7_9(taper):
    S, A = 200.0, 7.0
    b = math.sqrt(A * S)
    cr = 2 * S / (b * (1 + taper))
    w = LiftingSurface("4415", 3.0, 0.0, b / 2, cr, taper * cr)
    mac, y, area = w.mean_chord(17)
    assert mac == pytest.approx(2 / 3 * cr * (1 + taper + taper ** 2) / (1 + taper), rel=1e-13)       # (7.8), p. 140
    assert y == pytest.approx(b / 6 * (1 + 2 * taper) / (1 + taper), rel=1e-13)                       # (7.9), p. 140
    assert area == pytest.approx(S, rel=1e-13)


def test_wing_mesh_is_closed_and_its_area_is_the_section_perimeter_times_the_planform():
    w = LiftingSurface("4415", 0.0, 0.0, 10.0, 2.0, 2.0)                                  # constant chord
    V, T = mesh.loft(w.rings(8, 41), "strip", "strip")
    assert mesh.watertight(V, T)["ok"]
    xs, zs = sections.naca4("4415", 41)
    loop = np.column_stack([xs, zs])
    perimeter = np.linalg.norm(np.roll(loop, -1, axis=0) - loop, axis=1).sum()            # with the flat base
    section_area = 0.5 * abs(np.sum(xs * np.roll(zs, -1) - np.roll(xs, -1) * zs))
    assert mesh.area(V, T) == pytest.approx(perimeter * 2.0 * 20.0 + 2 * section_area * 4.0, rel=1e-12)
    assert mesh.volume(V, T) == pytest.approx(section_area * 4.0 * 20.0, rel=1e-12)
    assert w.inside([[1.0, 3.0, 0.1]])[0] and not w.inside([[1.0, 3.0, 0.5]])[0] and not w.inside([[1.0, 11.0, 0.1]])[0]


def test_tank_volume_of_a_constant_chord_wing():
    w = LiftingSurface("0012", 0.0, 0.0, 10.0, 2.0, 2.0)
    depth = sections.depth_between(0.0, 0.0, 0.12, 0.15, 0.60)
    assert 0.09 < depth < 0.12                                    # between the spars the section is thinner than its 12 %
    assert w.volume_between(0.15, 0.60, 1.0, 8.0) == pytest.approx(depth * 0.45 * 4.0 * 7.0, rel=1e-12)


# ---- fuselage body ------------------------------------------------------------------------------------------------
def cylinder_body(R=1.5, L=20.0, rho=fz.RHO_CIRCLE):
    return fz.Body([(0.0, R, R, R, rho), (L, R, R, R, rho)], 0.2 * L)


def test_body_volume_by_sections_equals_the_closed_surface():
    b = cylinder_body()
    V, T = mesh.loft(b.rings(400, 49), start=(0.0, 0.0, 0.0), end="fan")
    assert mesh.watertight(V, T)["ok"]
    exact = math.pi * 1.5 ** 2 * (16.0 + 4.0 * 2 / 3)             # cylinder plus half an ellipsoid of length 4
    assert b.volume_by_sections(4000) == pytest.approx(exact, rel=2e-3)
    assert mesh.volume(V, T) == pytest.approx(exact, rel=5e-3)
    top, side = b.projected_areas()
    assert top == pytest.approx(side) and top == pytest.approx(3.0 * 16.0 + math.pi * 1.5 * 4.0 / 2, rel=1e-4)


def test_clearance_margin_of_a_box_in_a_cylinder():
    b = cylinder_body()
    box = ac.box(8.0, 12.0, -0.9, 0.9, -0.9, 0.9)                 # corner at radius 1.2728 in a cylinder of 1.5
    # the test moves the corner outward by c in y and in z: (0.9 + c) sqrt(2) = 1.5
    assert ac.clearance_margin(b, box) == pytest.approx(1.5 / math.sqrt(2) - 0.9, abs=2e-3)
    assert ac.clearance_margin(b, ac.box(8.0, 12.0, -1.2, 1.2, -1.2, 1.2)) < 0.0          # outside
    assert ac.overlap_volume(box, ac.box(11.0, 13.0, 0.0, 2.0, 0.0, 2.0)) == pytest.approx(0.81)
    assert ac.overlap_volume(box, ac.box(12.0, 13.0, 0.0, 2.0, 0.0, 2.0)) == 0.0          # touching is not overlapping


class Stage1Body:
    """The Stage 1 body of revolution, for the smoothness gate: it has a break of slope at 60 % of its length."""
    length = 28.58

    def section_measures(self, x, n=None):
        r = np.array([ac.stage1_radius(v, self.length, 3.57) for v in x])
        return 2 * math.pi * r, math.pi * r ** 2


def test_smoothness_gate_refuses_the_stage1_break_and_passes_a_smooth_body():
    kinked = gates.slope_changes(Stage1Body())
    assert kinked["perimeter"]["largest_slope_change_per_ft"] > gates.SMOOTH_BOUND
    assert kinked["area"]["largest_slope_change_per_ft"] > gates.SMOOTH_BOUND
    assert kinked["perimeter"]["at_x_ft"] == pytest.approx(0.6 * 28.58, abs=0.02)
    smooth = gates.slope_changes(cylinder_body())
    assert all(v["largest_slope_change_per_ft"] < gates.SMOOTH_BOUND for v in smooth.values())


def test_stowed_gear_boxes():
    tyre = {"diameter": 1.5, "width": 0.5}
    leg, axle, b = ac.stowed_gear((10.0, 0.0, -1.0), -6.0, tyre, 0.25, 0.05, -1)
    assert leg == 5.0 and axle == 5.0
    assert b["wheel"]["lo"][0] == pytest.approx(5.0 - 0.8) and b["wheel"]["hi"][0] == pytest.approx(5.0 + 0.8)
    assert b["leg_2"]["lo"][0] == pytest.approx(b["wheel"]["hi"][0]) and b["leg_1"]["hi"][0] == pytest.approx(10.175)
    assert b["wheel"]["hi"][2] - b["wheel"]["lo"][2] == pytest.approx(1.6)
    assert all(ac.overlap_volume(b[p], b[q]) == 0.0 for p, q in (("leg_1", "leg_2"), ("leg_2", "wheel")))


# ---- the loft of r0: what must hold by construction, and the nose packaging of PD-19 -------------------
def test_loft_uses_r0_and_the_recorded_sections(loft):
    d, L, A, m, parts = loft
    assert (ac.WING_SECTION, ac.TAIL_SECTION) == ("4415", "0012")
    w = m["wing"]
    assert (w.half_span, w.c_root, w.c_tip, w.x_le) == (d["wing"]["span"] / 2, d["wing"]["root_chord"], d["wing"]["tip_chord"], d["layout"]["x_le"])
    f = m["fuselage"]
    assert f.length == d["fuselage"]["length"]
    half, top, bottom, _ = f.lines(np.linspace(0.01, f.length, 500))
    assert max(half.max(), top.max(), bottom.max()) == pytest.approx(d["fuselage"]["diameter"] / 2, rel=1e-12)   # Stage 1's diameter kept
    for v in A["arrangement"]["engine_envelope_in"]:
        assert f"{v:.3f}" in d["engine_source"]                  # the TCDS envelope quoted in the record
    assert m["ground_z"] == pytest.approx(-d["layout"]["h_cg"])


def test_gates_1_2_and_7_hold_on_r0s_loft(loft, tmp_path):
    d, L, A, m, parts = loft
    assert gates.gate1_watertight(parts)["verdict"] == "pass"
    g2 = gates.gate2_targets(m, d)
    assert g2["verdict"] == "pass" and abs(g2["mac_rel"]) < 1e-9 and abs(g2["mac_y_rel"]) < 1e-9
    assert gates.gate7_round_trip(parts, tmp_path / "loft.stl")["verdict"] == "pass"


def test_stage1_areas_are_the_build_ups(loft):
    d, L = loft[0], loft[1]
    s1 = gates.stage1_areas(d, L)
    assert s1["fuselage"] == d["fuselage"]["s_wet"]
    assert s1["fuselage"] == pytest.approx(3.4 * L["fuselage_fill"] * d["fuselage"]["length"] * d["fuselage"]["diameter"], rel=1e-12)
    g = p3.uav._geometry(d["W0_lb"], d["W_S"], d["A"], "pusher", L)       # Stage 1's own function (tail sized by the ledger copy)
    assert s1["wing"] == pytest.approx(g["s_wet_wing"], rel=1e-12) and s1["vertical_tail"] == pytest.approx(g["s_wet_vt"], rel=1e-12)
    assert s1["sponsons"] == pytest.approx(g["s_wet_sponsons"], rel=1e-12)


def test_wetted_area_gate_judges_each_component_at_five_per_cent(loft):
    d, L, A, m, parts = loft
    g3 = gates.gate3_wetted(m, parts, d, L)
    assert set(g3["components"]) == {"wing", "fuselage", "horizontal_tail", "vertical_tail", "sponsons"}
    for k, r in g3["components"].items():
        assert r["loft_wetted_ft2"] <= r["loft_whole_ft2"]
        assert r["verdict"] == ("pass" if abs(r["loft_wetted_ft2"] / r["stage1_ft2"] - 1) <= 0.05 else "fail")
    assert g3["verdict"] == ("fail" if g3["failing"] else "pass")
    assert g3["exposed_planform_ft2"]["wing"] < d["wing"]["area"]


def test_nose_packaging_passes_the_box_gate(loft):
    """Decision PD-19: with the nose gear stowed aft, the payload bay, the avionics, the gear bay and the engine are
    inside the fuselage skin with the clearance, no two boxes overlap, and the bay holds the volume of PD-12."""
    d, L, A, m, parts = loft
    g4 = gates.gate4_volumes(m, parts, d, L, A)
    need = g4["clearance_required_in"]
    assert need == 1.0
    in_fuselage = {k: b for k, b in g4["boxes"].items() if b["inside"] == "fuselage"}
    assert set(in_fuselage) == {"engine", "payload_bay_forward", "payload_bay_aft", "avionics_bay", "nose_gear_leg_1",
                                "nose_gear_leg_2", "nose_gear_wheel"}
    for k, b in in_fuselage.items():
        assert b["verdict"] == "pass" and b["clearance_in"] >= need, k
    assert g4["overlaps"] == []
    assert g4["payload_bay"]["verdict"] == "pass" and g4["payload_bay"]["needed_ft3"] == pytest.approx(500.0 / 30.0)
    assert g4["avionics_bay"]["verdict"] == "pass" and g4["tank"]["verdict"] == "pass"
    legs = g4["legs"]
    assert legs["nose"]["stowed_axle_x"] > legs["nose"]["pivot_x"]                     # aft
    assert legs["nose"]["pivot_x"] == d["stations"]["nose_gear"]["x"]                    # the wheel station is r0's
    assert g4["verdict"] == ("fail" if g4["failing"] else "pass")


def test_ground_gate_reproduces_stage1s_clearance(loft):
    d, L, A, m, parts = loft
    g6 = gates.gate6_ground(m, parts, d, L)
    assert g6["propeller_clearance_stage1_expression_in"] == pytest.approx(d["layout"]["prop_clearance_in"], rel=1e-9)
    assert g6["cg_angle_at_main_wheel_deg"] == pytest.approx(L["tipback_angle_deg"], abs=1e-6)       # Stage 1 places the wheel so
    assert max(g6["overturn_deg"].values()) == pytest.approx(L["overturn_max_deg"], abs=1e-6)


def test_propeller_disc_row_sees_a_surface_behind_the_plane(loft):
    m = dict(loft[3])
    V, T = box_mesh()
    m["propeller"] = {"x": 3.0, "z": 0.0, "radius": 5.0}
    assert gates.row9_propeller_disc(m, {"wing": (V, T)})["failing"] == {"wing": 1.0}
    m["propeller"] = {"x": 4.5, "z": 0.0, "radius": 5.0}
    assert gates.row9_propeller_disc(m, {"wing": (V, T)})["verdict"] == "pass"


def test_gate8_is_not_run_without_openvsp_and_judges_at_two_per_cent():
    comp = {k: {"loft_wetted_ft2": 100.0, "loft_whole_ft2": 110.0} for k in ac.COMPONENTS}
    assert gates.gate8_openvsp(comp, "no interpreter") == {"verdict": "not run", "reason": "no interpreter"}
    areas = {p: 100.0 for ps in ac.COMPONENTS.values() for p in ps}
    vsp = {"openvsp": "x", "default_mesh": {"wetted_ft2": dict(areas, wing=103.0), "whole_ft2": areas},
           "fine_mesh": {"wetted_ft2": areas, "whole_ft2": areas}}
    g = gates.gate8_openvsp({**comp, "sponsons": {"loft_wetted_ft2": 200.0, "loft_whole_ft2": 220.0}}, vsp)
    assert g["failing"] == ["wing"] and g["verdict"] == "fail" and g["components"]["sponsons"]["verdict"] == "pass"


def test_build_up_as_recorded_reproduces_r0(loft):
    d, L, A, m, parts = loft
    b = p3.buildup_with_loft_areas(d, gates.gate3_wetted(m, parts, d, L)["components"])
    assert b["as_recorded"]["CD0_mission_altitude"] == pytest.approx(d["CD0"]["mission_altitude"], rel=1e-9)
    assert b["as_recorded"]["CD0_sea_level"] == pytest.approx(d["CD0"]["sea_level"], rel=1e-9)
    assert b["as_recorded"]["hours_on_station"] == pytest.approx(L["loiter_h"], abs=5e-3)
    assert b["areas_stage1_rebuilt_ft2"] == pytest.approx(b["areas_stage1_ft2"], rel=1e-9)        # Stage 1 itself uses these areas
    assert p3.uav._geometry.__name__ == "_geometry"                                               # the patch is undone
    smaller = all(b["areas_loft_ft2"][k] <= b["areas_stage1_ft2"][k] for k in b["areas_loft_ft2"])
    if smaller:
        assert b["delta_CD0_mission_altitude"] < 0 and b["delta_hours"] > 0

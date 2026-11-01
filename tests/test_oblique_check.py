import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from physics.constants import GAMMA
from postprocess.validation import oblique_shock_check

MACH, THETA_DEG, P_INF = 4.0, 10.0, 1197.03


def _reference_oblique(M, theta):
    """Weak-branch theta-beta-M solution, used only if physics.shock is not importable."""
    def turn(beta):
        return math.atan(2 / math.tan(beta) * (M**2 * math.sin(beta)**2 - 1)
                         / (M**2 * (GAMMA + math.cos(2 * beta)) + 2))
    mu = math.asin(1 / M)
    betas = np.linspace(mu + 1e-6, math.pi / 2, 20001)
    b_hi = betas[np.argmax([turn(b) for b in betas])]       # beta at theta_max
    lo, hi = mu + 1e-9, b_hi
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if turn(mid) < theta else (lo, mid)
    beta = 0.5 * (lo + hi)
    mn1 = M * math.sin(beta)
    mn2 = math.sqrt((1 + 0.2 * mn1**2) / (1.4 * mn1**2 - 0.2))
    return {"beta": beta, "p_ratio": 1 + 2 * GAMMA / (GAMMA + 1) * (mn1**2 - 1),
            "M2": mn2 / math.sin(beta - theta)}


@pytest.fixture(autouse=True)
def shock_reference(monkeypatch):
    try:
        import physics.shock
    except ImportError:
        physics = types.ModuleType("physics")
        physics.__path__ = []
        shock = types.ModuleType("physics.shock")
        shock.oblique = _reference_oblique
        physics.shock = shock
        monkeypatch.setitem(sys.modules, "physics", physics)
        monkeypatch.setitem(sys.modules, "physics.shock", shock)


def write_tecplot(path, columns):
    """Tecplot ASCII, one FEQUADRILATERAL zone; the connectivity is trivial (unused by the check)."""
    names = list(columns)
    nodes = np.column_stack([columns[n] for n in names])
    n_elem = len(nodes) // 4
    elements = np.arange(4 * n_elem).reshape(n_elem, 4) + 1
    with open(path, "w") as f:
        f.write('TITLE = "Visualization of the solution"\n')
        f.write("VARIABLES = " + ",".join(f'"{n}"' for n in names) + "\n")
        f.write(f"ZONE NODES= {len(nodes)}, ELEMENTS= {n_elem}, DATAPACKING=POINT, "
                "ZONETYPE=FEQUADRILATERAL\n")
        np.savetxt(f, nodes, fmt="%.9e", delimiter="\t")
        np.savetxt(f, elements, fmt="%d")


def write_flow(path, beta_deg, noise=0.003, seed=1, width=0.4e-3, uniform_p=False,
               conservative=False):
    """Analytic field: pressure and Mach jump across y = x tan(beta), smeared over `width`.

    conservative=True writes Density, Momentum_x/y and Energy instead of Pressure and Mach."""
    ref = _reference_oblique(MACH, math.radians(THETA_DEG))
    p2, m2 = P_INF * ref["p_ratio"], ref["M2"]
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for x in np.linspace(0.0, 0.15, 151):
        wall = x * math.tan(math.radians(THETA_DEG))
        y = np.arange(wall, 0.2, 0.2e-3)
        xs.append(np.full(len(y), x))
        ys.append(y)
    x, y = np.concatenate(xs), np.concatenate(ys)
    behind = 0.5 * (1 - np.tanh((y - x * math.tan(math.radians(beta_deg))) / width))  # 1 below shock
    p = (P_INF + (p2 - P_INF) * behind) * (1 + noise * rng.standard_normal(len(x)))
    mach = (MACH + (m2 - MACH) * behind) * (1 + noise * rng.standard_normal(len(x)))
    if uniform_p:
        p = np.full(len(x), P_INF)
    if conservative:
        rho = np.full(len(x), 0.0184)                         # density is arbitrary for the check
        u = mach * np.sqrt(GAMMA * p / rho)
        columns = {"x": x, "y": y, "Density": rho, "Momentum_x": rho * u,
                   "Momentum_y": np.zeros(len(x)), "Energy": p / (GAMMA - 1) + 0.5 * rho * u**2}
    else:
        columns = {"x": x, "y": y, "Pressure": p, "Mach": mach}
    write_tecplot(path / "flow.dat", columns)


def test_synthetic_exact_shock_passes(tmp_path):
    ref = _reference_oblique(MACH, math.radians(THETA_DEG))
    write_flow(tmp_path, math.degrees(ref["beta"]))
    out = oblique_shock_check(tmp_path, THETA_DEG)
    assert out["pass"]
    assert out["beta_deg"] == pytest.approx(out["beta_ref_deg"], abs=0.2)
    assert out["p_ratio"] == pytest.approx(out["p_ratio_ref"], rel=0.01)
    assert out["M2"] == pytest.approx(out["M2_ref"], rel=0.01)
    assert out["beta_ref_deg"] == pytest.approx(22.234, abs=1e-3)


def test_wrong_shock_angle_fails(tmp_path):
    write_flow(tmp_path, 23.0)  # shock 0.77 deg too steep, tolerance is 0.5
    out = oblique_shock_check(tmp_path, THETA_DEG)
    assert not out["pass"]
    assert out["beta_deg"] == pytest.approx(23.0, abs=0.3)


def test_conservative_variables_give_the_same_result(tmp_path):
    ref = _reference_oblique(MACH, math.radians(THETA_DEG))
    write_flow(tmp_path, math.degrees(ref["beta"]), conservative=True)
    out = oblique_shock_check(tmp_path, THETA_DEG)
    assert out["pass"]
    assert out["p_ratio"] == pytest.approx(out["p_ratio_ref"], rel=0.01)
    assert out["M2"] == pytest.approx(out["M2_ref"], rel=0.01)


def test_uniform_flow_is_reported_not_raised(tmp_path):
    write_flow(tmp_path, 22.234, uniform_p=True)             # no shock anywhere
    out = oblique_shock_check(tmp_path, THETA_DEG)
    assert not out["pass"] and "error" in out["details"]


REAL_RUN = Path("/tmp/claude-0/-home-user-ai-engineering/4e62754b-8c8b-5b87-a61c-cb95358da47b/"
                "scratchpad/fmt")


@pytest.mark.skipif(not (REAL_RUN / "flow.dat").exists(), reason="real SU2 flow.dat not available")
def test_real_su2_flow_dat_is_readable():
    """A real SU2 v8.2.0 file (300 iterations only): finite numbers, pass is not asserted."""
    out = oblique_shock_check(REAL_RUN, THETA_DEG)
    for key in ("beta_deg", "p_ratio", "M2"):
        assert math.isfinite(out[key]), (key, out["details"])

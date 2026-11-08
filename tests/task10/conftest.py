"""Acceptance tests for Task 10 (docs/specs/task10_drone_sizing.md, docs/specs/task10_tasks.md).

Written by Fable before the code, against the interfaces in task10_tasks.md. Every file skips while
the `drone` package does not exist and runs as soon as it does. The numbers here are analytic or
come from a named open source; none comes from the implementation under test.
"""
import math

import pytest

try:                      # the whole directory is skipped until the drone package exists (T10.2)
    import drone  # noqa: F401
except ImportError:
    collect_ignore_glob = ["test_*.py"]

NOMINAL = {"family": "drone", "span_m": 2.0, "aspect_ratio": 10.0, "taper_ratio": 0.6,
           "battery_fraction": 0.30, "camber_pct": 4.0, "thickness_pct": 12.0, "fidelity": "low",
           "tag": "test"}


def helmbold(ar):
    """Lift-curve slope of a flat wing by Helmbold's formula, per radian."""
    return 2.0 * math.pi * ar / (2.0 + math.sqrt(ar * ar + 4.0))


def lifting_line(ar):
    """Prandtl lifting-line slope for an elliptic wing, per radian."""
    return 2.0 * math.pi * ar / (ar + 2.0)


@pytest.fixture
def nominal():
    return dict(NOMINAL)


@pytest.fixture
def fixed():
    """The fixed quantities of the study, from the ledger (T10.1)."""
    from drone import ledger
    return ledger.load_all()

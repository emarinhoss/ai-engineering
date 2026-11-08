"""Loader for the drone data ledger, data/drone/<set>.yaml.

Every quantity has a value, units, confidence and source. A quantity graded assumed must carry a
band, and the band must contain the value. The loader raises ValueError on any quantity that breaks
these rules; it never drops one silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = REPO_ROOT / "data" / "drone"
SET_NAMES = ("air", "battery", "propulsion", "structure", "rules")
CONFIDENCES = ("published", "derived", "assumed")
MIN_SOURCE_CHARS = 21  # the source must be more than 20 characters


@dataclass(frozen=True)
class Quantity:
    value: float
    units: str
    confidence: str
    band: tuple[float, float] | None
    source: str


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _parse_quantity(set_name: str, raw) -> tuple[str, Quantity]:
    where = set_name
    if not isinstance(raw, dict):
        raise TypeError(f"{where}: quantity entry is not a mapping: {raw!r}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{where}: quantity without a name: {raw!r}")
    where = f"{set_name}:{name}"
    value = raw.get("value")
    if not _is_number(value):
        raise ValueError(f"{where}: value is not a number ({value!r})")
    units = raw.get("units")
    if not isinstance(units, str):
        raise TypeError(f"{where}: missing units")
    confidence = raw.get("confidence")
    if confidence not in CONFIDENCES:
        raise ValueError(f"{where}: confidence {confidence!r} is not one of {CONFIDENCES}")
    source = raw.get("source")
    if not isinstance(source, str) or len(source.strip()) < MIN_SOURCE_CHARS:
        raise ValueError(f"{where}: missing or too short a source")
    band_raw = raw.get("band")
    band = None
    if band_raw is None:
        if confidence == "assumed":
            raise ValueError(f"{where}: assumed value without a band")
    else:
        if not (
            isinstance(band_raw, (list, tuple))
            and len(band_raw) == 2
            and all(_is_number(b) for b in band_raw)
        ):
            raise ValueError(f"{where}: band must be [lo, hi] of two numbers, got {band_raw!r}")
        lo, hi = float(band_raw[0]), float(band_raw[1])
        if not (lo < hi and lo <= value <= hi):
            raise ValueError(f"{where}: band [{lo}, {hi}] does not contain {value} with lo < hi")
        band = (lo, hi)
    return name, Quantity(float(value), units, confidence, band, source)


def _read(name: str) -> dict[str, Quantity]:
    if name not in SET_NAMES:
        raise ValueError(f"unknown drone set {name!r}; expected one of {SET_NAMES}")
    path = LEDGER_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict) or doc.get("set") != f"drone/{name}":
        raise ValueError(f"{path}: 'set' must be drone/{name}")
    quantities: dict[str, Quantity] = {}
    for raw in doc.get("quantities") or []:
        qname, q = _parse_quantity(name, raw)
        if qname in quantities:
            raise ValueError(f"{name}: duplicate quantity {qname!r}")
        quantities[qname] = q
    return quantities


def load(name: str) -> dict[str, float]:
    """Values of one set, {quantity name: value}."""
    return {k: q.value for k, q in _read(name).items()}


def quantity(name: str, key: str) -> Quantity:
    """One quantity with its units, confidence, band and source."""
    quantities = _read(name)
    if key not in quantities:
        raise KeyError(f"{name}: no quantity {key!r}")
    return quantities[key]


def load_all() -> dict[str, dict[str, float]]:
    """Values of all five drone sets, keyed by the short set name."""
    return {name: load(name) for name in SET_NAMES}

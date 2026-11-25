"""Test set-up for Task 12.

Owner ruling G-4 (2026-11-25) made `propeller_model: app_l` the default in data/task12/ledger.yaml. The TP100
records were sized with the flat propeller efficiency, and measurement/rubber_tp100.py builds the TP100 ledger
from the current default ledger plus two pinned lines (TP100_LEDGER). That module has no `propeller_model` pin
yet, so these tests pin it here, for the TP100 helper only: the TP100 comparison runs stay flat, as their
records were. Once TP100_LEDGER carries `"propeller_model": "flat"` this file can go.
"""
from measurement import rubber_tp100

rubber_tp100.TP100_LEDGER.setdefault("propeller_model", "flat")

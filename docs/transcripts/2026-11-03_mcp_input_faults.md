# Transcript: input faults F1 and F2 through the live MCP tool (2026-11-03)

Claude Code (this repository's session) called the MCP tool `validate_config` of the `su2` server
six times on 2026-11-03, for Task 6b (`docs/specs/task6b_real_su2_faults.md`). The tool writes
nothing and never runs SU2. Replies are quoted exactly as returned. The agent chose these inputs to
exercise the gates; it chose no sampling point.

## Calls 1 to 3: the agent left out a required field

The agent sent F1, F2 and a control case without the `tag` field. The schema refused all three
before any other stage:

```
params: {"family": "inlet2r", "theta1_deg": 8, "theta2_deg": 20, "solver": "NAVIER_STOKES", "mesh_level": "medium"}
reply:  {"errors": ["tag: Field required"], "ok": false, "stage": "schema", "warnings": []}

params: {"family": "inlet2r", "theta1_deg": 12, "theta2_deg": 14, "solver": "NAVIER_STOKES", "mesh_level": "medium"}
reply:  {"errors": ["tag: Field required"], "ok": false, "stage": "schema", "warnings": []}

params: {"family": "inlet2r", "theta1_deg": 8, "theta2_deg": 8, "solver": "NAVIER_STOKES", "mesh_level": "medium"}
reply:  {"errors": ["tag: Field required"], "ok": false, "stage": "schema", "warnings": []}
```

This was a real mistake by the agent, not a planned fault. The strict schema caught it, and the
reply named the field.

## Call 4: F1, a parameter out of bounds

```
params: {"family": "inlet2r", "theta1_deg": 8, "theta2_deg": 20, "solver": "NAVIER_STOKES", "mesh_level": "medium", "tag": "fault-demo"}
reply:  {"errors": ["theta2_deg: 20 outside [5, 14] for family inlet2r"], "ok": false, "stage": "schema", "warnings": []}
```

## Call 5: F2, the 26 deg corner that diverged in SU2

```
params: {"family": "inlet2r", "theta1_deg": 12, "theta2_deg": 14, "solver": "NAVIER_STOKES", "mesh_level": "medium", "tag": "fault-demo"}
reply:  {"errors": ["gate 4 (total turning): theta1+theta2 = 26 deg exceeds 24 deg"], "ok": false, "stage": "gates", "warnings": []}
```

## Call 6: the control case passes every stage

```
params: {"family": "inlet2r", "theta1_deg": 8, "theta2_deg": 8, "solver": "NAVIER_STOKES", "mesh_level": "medium", "tag": "fault-demo"}
reply (abridged; the full reply also lists every geometry point):
  {"case_id": "inlet2r-8db0aefa62", "errors": [], "ok": true, "stage": "done", "warnings": [],
   "geometry": {... "cells": 30600, "nodes": 31063, "recovery_2shock_inviscid": 0.9315837515932961, ...},
   "mesh_quality": {"failures": [], "n_inverted": 0, "min_angle_deg": 61.848002716642604,
                    "max_aspect_ratio": 235.56715148132153, "max_growth": 1.2000000000005155, "pass": true, ...}}
```

Nothing was staged: `validate_config` only checks. The same two input faults are F1 and F2 in
`docs/faults/fault_matrix.md` (tests with the fake solver). The real-SU2 faults are in
`docs/faults/real_fault_matrix.md`.

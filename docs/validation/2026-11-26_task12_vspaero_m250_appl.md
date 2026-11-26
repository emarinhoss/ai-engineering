# Task 12: VSPAERO neutral point of the App. L baseline, wing and tails only (owner ruling G-8)

Owner ruling G-8 (`docs/specs/00_decisions.md`, 2026-11-26): VSPAERO's wing-and-tail neutral point is re-run on the App. L baseline (3,160 lb record) **without the fuselage** and quoted in Gate B with that limit stated.

**The limit, stated plainly.** This model has **no fuselage**. The fuselage's destabilising pitch moment is missing from the VSPAERO numbers, so **the VSPAERO static margin is expected to read high**. It is **not an independent fuselage-inclusive neutral point** and does not close R13. The fuselage-plate configuration of the earlier run was not mesh-robust and is not run here (see `2026-11-24_task12_vspaero_m250.md`).

Numbers are from `runs/task12/openvsp/2026-11-26_m250_baseline_appl_vspaero/results.json` (script `conceptual/vspaero_check.py` with the new `--no-fuselage` option, commit `464f91b` at run time; OpenVSP 3.57.1, VSPAERO v.7.2.2, Python 3.12.3). Model: `runs/task12/openvsp/2026-11-26_m250_baseline_appl/m250_baseline_appl.vsp3`, built from `runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json` (command in its `model.json`). Same settings as the accepted 2026-11-24 runs: thin vortex lattice, default wake, alpha -2 to 8 deg (6 points), ISA 20,000 ft, loiter Mach 0.1577 and cruise Mach 0.2299 (from the new record's mission), moments about the record's full-fuel CG, mesh levels L1 (wing 352, wing + tails 896 panels) and L2 (1,472 and 3,712 panels). Cases run: wing L1/L2, wing + tails L1/L2; all four passed the validity gate. Reference: S 197.52 ft^2, MAC 5.567 ft, span 37.18 ft (A 7.00), CG at x = 11.274 ft (full), 11.454 ft (empty). Quantities below are at the loiter Mach; the cruise Mach moves them the same way (`results.json`).

The model limits of the 2026-11-24 report apply unchanged: display airfoils (NACA 4415 / 0012), inviscid lattice, no propeller, turret or sponsons, no fuselage.

## Stage 1 values from the new record

From `design_pusher.json`: neutral point 11.921 ft from the nose (Raymer (16.9) with the fuselage moment term, Cma_fus 0.1413); static margin 0.1162 full fuel and 0.0838 empty (the 2026-11-26 aero report prints 0.116 and 0.084 for Stage 1 and 0.083 for its lattice row; the record's empty value is 0.0838). Without the fuselage moment term the same equation gives a neutral point 12.050 ft (computed by the script from the record, `raymer_stage1` in `results.json`).

## Neutral point and static margin (wing + tails, no fuselage)

| Quantity | VSPAERO L1 | VSPAERO L2 | Stage 1 record | VSPAERO minus record (L1 / L2) |
|---|---|---|---|---|
| CL_alpha, aircraft, per rad | 5.872 | 5.774 | 6.078 | -3.4 / -5.0 % |
| Cm_alpha at full-fuel CG, per rad | -0.935 | -0.965 | -0.706 | more stable by 0.23 / 0.26 |
| **Neutral point**, ft from nose | 12.160 | 12.204 | 11.921 (12.050 without fuselage term) | **+0.240 / +0.283 ft** (+0.110 / +0.154 ft vs without fuselage term) |
| **Static margin, full fuel**, MAC | 0.159 | 0.167 | 0.1162 | **+0.043 / +0.051** |
| **Static margin, empty**, MAC | 0.127 | 0.135 | 0.0838 | **+0.043 / +0.051** |

Wing alone (consistency check): VSPAERO neutral point 9.874 / 9.933 ft against the record's wing aerodynamic centre at 10.037 ft, 0.163 / 0.105 ft (2.9 / 1.9 % MAC) ahead. CL_alpha of the wing alone 4.708 / 4.651 per rad against Raymer's bare planform 4.783 (-1.6 / -2.8 %) and the installed 5.154 of the record (-8.7 / -9.8 %, the fuselage factor and exposed-area ratio a wing alone does not carry).

## Mesh sensitivity (L1 to L2, loiter)

| Quantity | wing alone | wing + tails |
|---|---|---|
| CL_alpha | -1.2 % | -1.7 % |
| CL0 | +0.0051 | +0.0044 |
| Cm_alpha | -5.3 % (positive, wing alone) | magnitude +3.2 % (more stable) |
| **neutral point** | +0.058 ft (9.874 to 9.933) | **+0.044 ft (12.160 to 12.204)** |
| **static margin, full fuel** | +0.0105 MAC | **+0.0079 MAC** |
| K from Trefftz plane (so e) | -13.8 % (e 1.006 to 1.167) | -10.8 % (e 1.031 to 1.155) |
| K from surface integration | +5.0 % (e 0.950 to 0.905) | +2.8 % (e 0.934 to 0.908) |

**Mesh spread of the neutral point: 0.044 ft, 0.008 MAC, for a four-fold increase in panel count.** Lift slope, neutral point and margin are converged to about 2 %, 0.05 ft and 0.01 MAC. **Induced drag is not converged** and the Trefftz-plane e at L2 (above 1) is not physical for a nearly planar wing; this is the same behaviour as the 2026-11-24 run, was not investigated further, and no induced-drag conclusion is drawn from it. A mesh finer than L2 was not run, so "converged" is a statement of the L1 to L2 change only.

## Old baseline against new (same script, same settings, wing + tails, loiter, L1 / L2)

| Quantity | Old baseline (2026-11-24, 3,061 lb class, S 194.81 ft^2) | New App. L baseline (S 197.52 ft^2) |
|---|---|---|
| Stage 1 neutral point, ft | 11.866 | 11.921 |
| Stage 1 margin full / empty | 0.1161 / 0.0839 | 0.1162 / 0.0838 |
| VSPAERO CL_alpha wing alone | 4.703 / 4.652 | 4.708 / 4.651 |
| VSPAERO CL_alpha wing + tails | 5.867 / 5.775 | 5.872 / 5.774 |
| VSPAERO neutral point, ft | 12.106 / 12.150 | 12.160 / 12.204 |
| VSPAERO margin, full fuel | 0.160 / 0.168 | 0.159 / 0.167 |
| VSPAERO margin, empty | 0.127 / 0.135 | 0.127 / 0.135 |
| VSPAERO minus Stage 1, neutral point, ft | +0.240 / +0.285 | +0.240 / +0.283 |
| VSPAERO minus Stage 1, margin | +0.043 / +0.051 | +0.043 / +0.051 |
| Neutral point mesh spread, ft | +0.044 | +0.044 |

Old values are from `runs/task12/openvsp/2026-11-24_m250_baseline_vspaero/results.json` (the old report rounds the old offsets to +0.24 / +0.28 ft). The two baselines give the same VSPAERO-minus-Stage-1 offset to within 0.002 ft, expected because the layout rule (margins centred in the band) and the lattice are the same; this says the new baseline did not change the picture, not that either neutral point is confirmed.

## How to read it for Gate B

- VSPAERO wing + tails puts the full-fuel margin at 0.159 to 0.167 MAC and the empty margin at 0.127 to 0.135, with the neutral point 0.24 to 0.28 ft aft of Stage 1's. R13's band is 5 to 15 % MAC at full fuel: the full-fuel VSPAERO value is above the upper end, but **it has no fuselage, so it is expected to read high**. Stage 1's own equation with the fuselage term dropped gives a neutral point 0.13 ft aft of the with-fuselage value; about half of VSPAERO's offset (+0.110 / +0.154 ft of +0.240 / +0.283 ft) therefore remains after the fuselage term is removed from Stage 1, and comes from the wing and tail terms (downwash, tail lift slope), not from the fuselage. This report does not decompose that remainder.
- What it does show: with the fuselage omitted, a second code (vortex lattice with its own downwash) puts the wing-and-tail neutral point within 0.04 MAC of Stage 1's and never below it. What it cannot show: the margin with the fuselage. R13 stays open for a fuselage-inclusive independent estimate (the fuselage-plate configuration is not usable).
- The model, conditions and mesh levels were fixed before the run; nothing was tuned. The run was done twice (the second after fixing the solver-version field, below); results identical.

## Script change

`conceptual/vspaero_check.py` gained `--no-fuselage` (runs only the wing and wing + tails cases and their mesh pairs); the default behaviour and the 2026-11-24 outputs are unchanged. `select_cases()` is tested in `tests/task12/test_vspaero_check.py`. A second fix: the solver version was searched for in the first 2,000 characters of the log, where the header is not (it is at line 77), so `vspaero_version` was null in a first pass of this run; it now reads the whole log. The 2026-11-24 record had the field added by hand for the same reason.

## Reproduction

```
<Python 3.12 with OpenVSP> -m conceptual.openvsp_model --design runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json --out runs/task12/openvsp/2026-11-26_m250_baseline_appl --name m250_baseline_appl
<Python 3.12 with OpenVSP> -m conceptual.vspaero_check --design runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json --model runs/task12/openvsp/2026-11-26_m250_baseline_appl/m250_baseline_appl.vsp3 --out runs/task12/openvsp/2026-11-26_m250_baseline_appl_vspaero --no-fuselage
```

About 2 minutes on 4 cores. The bulk solution and mesh files are deleted by the script after the panel count is read.

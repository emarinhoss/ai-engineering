# Task 12 Stage 3 output: measured performance of the frozen design (spec 7.3)
**Superseded (ruling B-2c, 2026-11-27).** This report describes the W/S 16, A 7 design and is kept as the record of it; the Gate B performance report of the W/S 13, A 8 baseline is `docs/validation/2026-11-27_task12_performance.md`.

Written by hand on 2026-11-26 from the records and generated reports listed in section 10. **No run was
made for this report and no figure was made for it.** Every number is copied from a record or from a
report generated from a record; each table names its file. Margins in section 4 are the limit minus the
quoted value (a subtraction of two quoted numbers, nothing else). Where a number comes straight from a
JSON record it is printed to three or four significant decimals; where it comes from a report it is
printed as the report prints it.

This report does not decide Gate B. Section 7 lays the evidence against the pass criterion of spec 7.4;
the owner rules.

## 1. The design that was measured

The frozen design is the App. L baseline (owner rulings R-a to R-e, baseline cell, G-4):
`runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/`.

Source: `target_result.json` and `design_pusher.json` of that record.

| Quantity | Value |
|---|---|
| Concept | pusher, Rolls-Royce M250-B17F, 450 shp, 212 lb |
| W/S, A | 16 lb/ft^2, 7 |
| Take-off weight W0 | 3,160.3 lb |
| Empty weight | 1,683.0 lb |
| Fuel | 977.3 lb |
| Payload | 500.0 lb |
| Wing area, span | 197.52 ft^2, 37.18 ft |
| Sized loiter | 9.03125 h |
| V_C placard | 115 kt EAS |
| Power margin | 34.7 % |
| Propeller model | App. L actuator disk, real-to-ideal factor f = 0.85 (ledger band 0.80 to 0.90) |
| Stage 1 compliance rows failed | none (`failed: []`) |

Two things to know before reading on:

- **The Stage 1 App. L report is a different aircraft.** `docs/validation/2026-11-25_task12_conceptual_m250_appl.md`
  (record `runs/task12/stage1/2026-11-25`) describes the design sized without margin: 3,005 lb, W/S 22, A 8.
  Its compliance table is not the frozen design's. For the frozen design no Stage 1 compliance table was
  generated; the record says only that no Stage 1 row failed, and the values below are read from its
  `design_pusher.json`.
- **The fuel is sized for the worst case, not for 8 h.** The loiter was sized up to 9.03125 h so that the
  worst case at h = 1.05 still gives 3.5 h on station. At nominal values the aircraft therefore flies
  9.031 h on station (`info_gap.json`, `nominal.R5_hours`).

## 2. What kind of evidence there is

Each Stage 3 row has a class (definitions from the perf report):

- **independent**: another source, method and input.
- **partly independent**: another relation, with inputs or sub-models shared with Stage 1.
- **coding check**: same inputs and an algebraically equal formula. It can only show that the code is
  consistent; it does not verify the quantity.
- **not judged**: reported without a verdict (same table or model as Stage 1, or the relation does not
  apply).

**Independent evidence on this design, all of it:**

| Row | Result | Source file |
|---|---|---|
| Wing lift slope (vortex lattice against Raymer (12.6)) | -3.4 %, within ±5 % | `2026-11-26_task12_stage3_aero_m250_appl.md` |
| Zero-lift drag (Anderson (2.37), Cfe 0.0043) | -18.63 %, outside ±10 %, favourable direction | `2026-11-26_task12_stage3_perf_m250_appl.md` |
| Brochure part-power SFC, three points | +0.7 to +1.7 %, within ±10 %, but the rows cannot fail (G-6) | `2026-11-26_task12_stage3_engine_m250_appl.md` |
| Gust load factors | not computed (no second source) | perf report |

Everything else is partly independent, a coding check, not judged, or not run. **There is no independent
check of the propeller**, in flight or at take-off: Stage 1 moved to the App. L disk (G-4) and the
blade-element check was waived (G-5), so the Stage 3 propeller rows use the same relation and factor as
Stage 1.

## 3. Measurement table

### 3.1 Performance rows

Source: `docs/validation/2026-11-26_task12_stage3_perf_m250_appl.md`, generated from
`runs/task12/stage3/2026-11-26/m250_baseline_appl_measure/perf.json` (commit `0fe7021`, clean tree).
Counts from that report: 12 within, 3 outside, 6 not judged, 1 not computed.

| Quantity | Class | Stage 1 | Stage 3 | Difference | Tolerance | Verdict |
|---|---|---|---|---|---|---|
| installed power, sea-level climb 1,000 ft/min (hp) | coding check | 206.8 | 206.8 | -0.00 % | ±5 % | within |
| installed power, 100 ft/min at the ceiling altitude 23000 ft (hp) | coding check | 294 | 294 | +0.00 % | ±5 % | not judged (numerically inside) |
| installed power, take-off over 50 ft in the field length (hp) | partly independent | 159.7 | 142.3 | -10.89 % | ±5 % | **outside** |
| installed power, sustained 30 deg turn at loiter speed (hp) | coding check | 262.5 | 262.5 | +0.00 % | ±5 % | within |
| installed power, level cruise at mission altitude (hp) | coding check | 228.5 | 228.5 | -0.00 % | ±5 % | within |
| mission fuel (200 nm out + 8 h + 200 nm back, headwind) (lb) | coding check | 977.3 | 977.3 | +0.00 % | ±5 % | not judged (numerically inside) |
| take-off weight, Anderson first estimate (empty fraction 0.62) (lb) | partly independent | 3,160.3 | 7,108.7 | +124.94 % | ±10 % | **outside** (G-2: explained) |
| take-off weight, Anderson build-up (8.83) (lb) | coding check | 3,160.3 | 3,448.5 | +9.12 % | none (cross-check) | not judged |
| zero-lift drag coefficient, mission altitude, clean | independent | 0.02472 | 0.02011 | -18.63 % | ±10 % | **outside** |
| propeller efficiency, climb (sea level, full power) | coding check | 0.7202 | 0.7202 | -5.493e-13 | ±0.05 | within |
| propeller efficiency, cruise (outbound leg) | coding check | 0.8141 | 0.8141 | +2.633e-13 | ±0.05 | within |
| propeller efficiency, loiter | coding check | 0.7861 | 0.7861 | +1.761e-13 | ±0.05 | within |
| best-range speed, mission altitude (kt) | coding check | 114.6 | 114.6 | +0.00 % | ±3 % | within |
| best-endurance speed, mission altitude (kt) | coding check | 87.05 | 87.05 | +0.00 % | ±3 % | within |
| sea-level rate of climb at W0, Anderson closed form (ft/min) | coding check | 2,636.1 | 2,237.8 | -15.11 % | none (cross-check) | not judged |
| sea-level rate of climb at W0, excess power at Stage 1's speed (ft/min) | coding check | 2,636.1 | 2,636.1 | +0.00 % | ±3 % | within |
| best-climb speed, sea level (kt) | coding check | 98.99 | 64.56 | -34.79 % | none (cross-check) | not judged |
| service ceiling (100 ft/min) at W0 (ft) | coding check | 29,746.6 | 29,350.1 | -396.4 ft | ±1,000 ft | not judged (numerically inside) |
| take-off distance over 50 ft, sea level (ft) | partly independent | 793.5 | 802.8 | +1.18 % | ±15 % | within |
| landing distance over 50 ft, sea level (ft) | partly independent | 1,419.2 | 1,426.1 | +0.49 % | ±15 % | within |
| corner speed V*, sea level, EAS (kt) | coding check | 115.3 | 115.3 | +0.00 % | ±5 % | within |
| gust load factors (V_C and V_D points) | independent | 3.239 | - | - | ±5 % | **not computed** |

The mission-fuel row is named "8 h" by the generator; the record's loiter is the sized 9.03125 h and
the 977.3 lb is the fuel for it.

### 3.2 Engine rows

Source: `docs/validation/2026-11-26_task12_stage3_engine_m250_appl.md`, generated from `engine.json` in
the same record folder (commit `3f0c099`). The report gives no class column; the class below is its own
wording (section 1 of that report and spec 7.1b).

| Quantity | Class | Stage 1 / brochure | App. K family (min - max) | Difference | Tolerance | Verdict |
|---|---|---|---|---|---|---|
| shaft hp available at 20,000 ft, 95 kt (hp) | not judged (same table) | 196.713 | 196.549 - 196.755 | -0.1 to +0.0 % | ±10 % | not judged; numerically inside |
| shaft hp available at 25,000 ft, 95 kt (hp) | not judged (same table) | 156.037 | 155.899 - 156.074 | -0.1 to +0.0 % | ±10 % | not judged; numerically inside |
| shaft SFC over cruise_out, leg average (lb/(hp h)) | not judged (same table) | 0.670 | 0.655 - 0.662 | -2.3 to -1.3 % | ±10 % | not judged; numerically inside |
| shaft SFC over loiter, leg average (lb/(hp h)) | not judged (same table) | 0.825 | 0.800 - 0.824 | -3.1 to -0.1 % | ±10 % | not judged; numerically inside |
| shaft SFC over cruise_back, leg average (lb/(hp h)) | not judged (same table) | 0.748 | 0.728 - 0.744 | -2.7 to -0.6 % | ±10 % | not judged; numerically inside |
| service ceiling (App. K power, pi_c held) (ft) | not judged (same table) | 29,746.593 | 29,715.765 - 29,748.251 | -31 to +2 ft | ±1,000 ft | not judged; numerically inside |
| shaft SFC at normal_cruise (380 shp, sea level static) | independent, cannot fail (G-6) | 0.635 | 0.642 - 0.644 | +1.0 to +1.5 % | ±10 % | within |
| shaft SFC at cruise_a_90pct (377 shp, sea level static) | independent, cannot fail (G-6) | 0.637 | 0.643 - 0.646 | +1.0 to +1.4 % | ±10 % | within |
| shaft SFC at cruise_b_75pct (314 shp, sea level static) | independent, cannot fail (G-6) | 0.673 | 0.678 - 0.685 | +0.7 to +1.7 % | ±10 % | within |

Stage 1's leg SFC carries the 1.02 allowance; the family is raw App. K without it. A constant SFC of 0.613
would also pass the three brochure rows (-3.5 %, -3.8 %, -8.9 %), so they cannot tell engine models apart.

Model check of the cycle code against Mattingly's own figures (spec 7.1b item 1), same source file,
section 5. Tolerances were fixed on 2026-11-21.

| Group | Rows | Result |
|---|---|---|
| Fig. K.4 tau_t* at pi_c 5, 10, 20, 35 | 4 | all within ±0.015 (-0.001 to -0.008) |
| Fig. K.2 F/m0 at pi_c 5, 17 | 2 | +3.6 %, +3.0 %, within ±5 % |
| Fig. K.3 S at pi_c 5 | 1 | -4.6 %, within ±5 % |
| Fig. K.3 S at pi_c 17 and 35 | 2 | -5.7 %, -5.6 %, **outside** ±5 % |
| Fig. K.7 F/F_SL at 5,000 to 30,000 ft | 6 | all within ±0.015 (-0.001 to +0.006) |
| Fig. K.9 minimum S at M0 0.3, 0.5, 0.8 | 3 | -8.6 %, -7.9 %, -6.8 %, within ±10 % |

16 of 18 rows within. On fuel consumption the model reads low against the book in every row (-8.6 to
-4.6 %).

Validity (spec 7.1b item 2), same source file, section 4: **71.8 %** of the mission fuel is burned in
table cells where App. K's choked-turbine assumption fails (the whole loiter, 557.8 lb, and 95.8 of the
137.2 lb of the return cruise). The table is validated at sea level, static, 70 to 100 % power only; the
mission legs run at 14 to 29 % of the rating at 20,000 ft.

### 3.3 Aerodynamic rows

Source: `docs/validation/2026-11-26_task12_stage3_aero_m250_appl.md`, generated from `aero.json` in the
same record folder (commit `3f0c099`).

| Quantity | Class | Stage 1 / Raymer | Measured | Difference | Tolerance | Verdict |
|---|---|---|---|---|---|---|
| wing lift slope, per rad (bare planform, inviscid, M 0) | independent | 4.739 | 4.576 | -3.4 % | ±5 % | within |
| span efficiency e | independent | 0.839 | 0.991 | +0.152 | ±0.05 | not judged (not comparable as specified) |
| downwash gradient at the tail (z = 1.39 ft) | coding check | 0.457 | 0.458 | +0.001 | none | not judged (same model, 7.1c item 3) |
| static margin, full fuel, MAC | coding check | 0.116 | 0.116 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76)-(8.78) with lattice downwash, full fuel | coding check | 0.116 | 0.116 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76) as printed (no downwash), full fuel | partly independent | 0.116 | 0.396 | +0.280 | ±0.03 | not judged (book's simplification); numerically outside |
| static margin, empty fuel, MAC | coding check | 0.084 | 0.083 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76)-(8.78) with lattice downwash, empty fuel | coding check | 0.084 | 0.083 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76) as printed (no downwash), empty fuel | partly independent | 0.084 | 0.364 | +0.280 | ±0.03 | not judged (book's simplification); numerically outside |

### 3.4 Rotation with ground effect

Source: `docs/validation/2026-11-26_task12_stage3_rotation_m250_appl.md`, generated from `rotation.json`
and `ground_effect_validation.json` in the same record folder (commit `3f0c099`). The row has no 7.1a
tolerance and the record gives it no class. Everything but the ground-effect lift factor is Stage 1's
layout.

| Quantity | Stage 1 | With ground effect | Difference | Limit | Limit met |
|---|---|---|---|---|---|
| rotation tail CL needed (0.8 V_TO, forward CG, sea level) | -0.982 | -0.947 | +0.035 (-3.6 %) | abs <= 1.00 | yes / yes |

Validation of the ground-effect lattice (induced-drag ratio, tolerance ±15 %, fixed in advance): inside
Raymer (12.61) at 4 of 4 h/b values, inside Anderson (6.77) at 1 of 4. The two books differ by 29 % at
h/b 0.1. The limit is met with and without ground effect, so the validation does not decide the row
(G-7).

### 3.5 VSPAERO neutral point, wing and tails only (supporting, ruling G-8)

Source: `docs/validation/2026-11-26_task12_vspaero_m250_appl.md`, from
`runs/task12/openvsp/2026-11-26_m250_baseline_appl_vspaero/results.json` (OpenVSP 3.57.1, VSPAERO
v.7.2.2). **The model has no fuselage.** The fuselage's destabilising moment is missing, so the margin is
expected to read high. It is not a fuselage-inclusive neutral point and has no 7.1a verdict.

| Quantity | VSPAERO L1 | VSPAERO L2 | Stage 1 record | VSPAERO minus record (L1 / L2) |
|---|---|---|---|---|
| CL_alpha, aircraft, per rad | 5.872 | 5.774 | 6.078 | -3.4 / -5.0 % |
| Neutral point, ft from nose | 12.160 | 12.204 | 11.921 (12.050 without the fuselage term) | +0.240 / +0.283 ft |
| Static margin, full fuel, MAC | 0.159 | 0.167 | 0.1162 | +0.043 / +0.051 |
| Static margin, empty, MAC | 0.127 | 0.135 | 0.0838 | +0.043 / +0.051 |

Mesh spread of the neutral point from L1 to L2: 0.044 ft, 0.008 MAC. Induced drag is not converged on
these meshes and no drag conclusion is drawn from the run.

### 3.6 Rows of spec 7.1 with no measurement

| Spec 7.1 row | Status | Source |
|---|---|---|
| Section polars and C_L,max at the design Reynolds number (SU2) | not run (G-5 waived) | perf and aero reports |
| Propeller efficiency by blade element | no code (G-5 waived) | perf report |
| Gust load factors, second source | not computed: Anderson ch. 6 has no gust relation (G-5 waived) | perf report |
| Drag due to lift | no judged row: the span-efficiency row is not comparable as specified | aero report |
| Range and endurance | no row of their own in 7.1a; covered by the mission-fuel row (a coding check) | perf report |
| Trim | no Stage 3 row; Stage 1's flag `trim_ok` is true in the record | `design_pusher.json` |

## 4. Performance against each requirement

"Basis" says what the statement rests on. Limits are from spec section 3 and the record's ledger copy.
Sources for the values: `design_pusher.json`, `target_result.json` and `info_gap.json` of the frozen
record, and the Stage 3 reports of section 3.

| ID | Requirement | Value on the frozen design | Margin | Basis and class |
|---|---|---|---|---|
| R1, R2 | single turboprop, one engine | RR M250-B17F, one | - | by construction |
| R3 | rubber engine first, then a real engine and a fixed-engine re-size | fixed-engine re-size around the M250-B17F | - | by process (ruling R-a). The rubber-engine step is in earlier records, not measured here |
| R4 | payload 500 lb | 500.0 lb (W0 - fuel - empty weight) | 0 | by construction; `appl_decomposition/decomposition.json` |
| R5 | 8 h on station at nominal values | 9.031 h | +1.031 h | **coding check plus model.** Mission fuel is a coding check (not judged). The SFC in the mission cells rests on the engine model (71.8 % of the fuel in unchoked cells; no altitude or low-power data). Anderson's fuel fraction 0.3097 against Stage 1's 0.3092 is partly independent: his relations, Stage 1's polar, SFC and propeller |
| R5 | at least 3.5 h for every member of the bands (h = 1) | R5 guarantee horizon 1.051; worst case at h = 1: 3.768 h | +0.051 in h; +0.268 h at h = 1 | **info-gap study on the Stage 1 model.** A search, not a proof. The propeller factor at the worst point is a judgement (section 5.4) |
| R6 | cruise and loiter at 20,000 ft, ISA | mission flown at 20,000 ft | - | by construction. **The engine's maximum operating altitude and relight envelope are design assumptions (ruling R-f); no public source gives either.** Not checked |
| R7 | take-off over 50 ft at most 2,500 ft | 793.5 ft (Stage 1), 802.8 ft (Anderson) | 1,706.5 ft / 1,697.2 ft | **partly independent**, within ±15 %. Unfactored (G-1). Both routes share the thrust function, which rests on f at low speed (judgement, G-9). Sweep over f in section 5.5 |
| R7 | landing over 50 ft at most 2,500 ft | 1,419.2 ft (Stage 1), 1,426.1 ft (Anderson) | 1,080.8 ft / 1,073.9 ft | **partly independent**, within ±15 %. Unfactored (G-1). At take-off weight. Approach and flare are the same geometry as Raymer's; the braking roll has its own relation |
| R7 | clean stall at most 70 kt | 59.17 kt | 10.83 kt | **ledger value.** Rests on the clean C_L,max 1.35 of the record; the SU2 C_L,max row was not run (G-5). The stall clause is not inside the R7 horizon (that is take-off and landing distance only) |
| R8 | retractable tricycle gear | main gear retracts into sponsons, `fits: true` | - | by construction |
| R9 | limit load +3.8 / -1.5, factor of safety 1.5, gusts checked, composite factor band | n_limit 3.8, ultimate 5.7; largest positive gust 3.239; negative gust -1.239 | 0.561 below 3.8 | **Stage 1 only.** Gust second source not computed (G-5). Corner speed is a coding check. See the three notes under the table |
| R10 | 6 % reserve and trapped fuel | factor 1.06 on the mission fuel | - | by construction |
| R11 | cruise legs at best-range speed | 141.2 kt out, 128.7 kt back (true airspeed) | - | by construction of the mission code, which chooses each leg's speed with the engine table, the headwind and the 1.3 V_stall floor. The still-air closed form gives 114.6 kt (coding check). No row checks the speed choice |
| R12 | sea-level climb at least 1,000 ft/min | 2,636.1 ft/min (Stage 1); bracket 2,238 to 2,845 ft/min | 1,636.1 ft/min; 1,238 ft/min at the lower bracket | **coding check; closed form not judged.** Not inside the Gate B horizon |
| R12 | service ceiling at least 23,000 ft (ledger adds a 500 ft margin) | 29,746.6 ft (Stage 1); bracket 29,350.1 to 29,893 ft | 6,746.6 ft; 6,350.1 ft at the lower bracket | **not judged (same engine table, 7.1b).** No altitude data behind the table. 23,000 ft is above every certified B17 installation found (20,000 ft). Not inside the Gate B horizon |
| R13 | static margin 5 to 15 % MAC, full to empty fuel | 0.1162 full, 0.0838 empty | 0.034 from each end | **layout construction, not a measurement** (section 5.6). VSPAERO wing and tails is supporting only (G-8) |
| R14 | no crew systems | none in the weight build-up | - | by construction |
| R15 | flight avionics fixed in the ledger | 60 lb uninstalled, 96.5 lb installed | - | by construction (ledger assumption, band 40 to 100 lb) |
| R16 | sustained 30 deg turn at loiter, 20,000 ft | 262.5 hp installed power needed against 450 | 187.5 hp | **coding check.** Not inside the Gate B horizon |
| R17 | every leg at least 1.3 V_stall | enforced in the speed choice; the whole loiter flies on the floor (96.9 kt against a best-endurance speed of 87.05 kt) | 0 on the loiter | by construction |
| R18 | one V_C placard, structure and gusts sized at it | 115 kt EAS; fastest cruise sub-step 104.27 kt EAS | 10.73 kt | by construction of the per-design rule. Holds only if the autopilot enforces it: the record's level top speed is 198.5 kt EAS at sea level and 129.8 kt EAS at 20,000 ft, both above V_C |
| R19 | 25 kt headwind on both transit legs | ground speed 116.2 kt at 141.2 kt, 103.6 kt at 128.7 kt | - | by construction. The headwind strength is outside the info-gap horizon (owner, 2026-11-22) |

Notes on R9:

- **Negative limit.** Spec section 3 says -1.5. The record's ledger says -1.8 (changed at Gate A,
  2026-11-20) with a 0.1 g margin. The record's negative gust, -1.239, is inside both.
- **Composite factor band.** R9 carries the factor as a band 0.90 to 1.00. In the info-gap study of the
  frozen design `composite_factor` is in `inert_variables`: moving it changes neither the hours on station
  nor the distances. By a search of the code (not a run) the ledger factor is read only in the Table 3.1
  empty-fraction comparison lines of `conceptual/uav.py`; the component build-up uses Raymer's Table 15.4
  factors in code. So this band is not propagated to the built aircraft.
- **Gusts above V_C.** The gust load factors of this design at its level top speed are not in the record.

Other Stage 1 rows (nose-wheel load, propeller clearance, fuel volume, trim) are not requirements R1 to
R19. The record's only statement on them is that none failed.

**Summary of the table.**

- Met by construction or by process, nothing to measure: R1, R2, R3, R4, R8, R10, R14, R15, R17, R19.
- Met on the record, with a caveat on the kind of evidence: R5 (both parts), R7 (three clauses), R9, R11,
  R12 (both clauses), R13, R16, R18.
- Not checked, rests on a declared assumption: R6 (engine altitude limit and relight, ruling R-f).
- No requirement has a recorded value on the wrong side of its limit.

## 5. Robustness

### 5.1 Horizons

Source: `runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/info_gap.json` (`h_hat`) and
`target_result.json` (`modes`). Report: `docs/validation/2026-11-25_task12_m250_baseline_appl.md`, which
prints the same horizons to two decimals (1.05, 1.18, 1.51). Seed 20261122, commit `8501980`; the tree
had one untracked path (the run's own output folder).

| Quantity | Horizon h | Threshold (spec 7.1a) | Note |
|---|---|---|---|
| R5 guarantee: 3.5 h on station for every member | 1.051 | at least 1 | binding mode: endurance |
| - endurance mode | 1.051 | | about the target by construction: the fuel is sized until the worst case at 1.05 gives 3.5 h |
| - transit-cliff mode (the mission can still be flown) | 1.178 | | worst cliff ratio at h = 1.05: 0.899 |
| R7: field length 2,500 ft | 1.506 | at least 1 | minimum of take-off and landing |
| - take-off | 1.506 | | binds; rests on f at low speed |
| - landing | 1.606 | | |
| 8 h on station, mission fuel only | 0.198 | none | information: not the Gate B criterion |
| 8 h on station, reserve usable | 0.368 | none | information |

The 8 h nominal loiter holds only to h = 0.198. Spec 7.1a expected zero here; it is above zero because
the loiter was sized to 9.03125 h.

Check of the search by sampling (same file, `sampling`): at each horizon 200 random points and 32 corner
points were tried and none was worse than the search's worst case (`n_beating_search` 0 in every row).
At h = 1 the search's worst case needs 952.0 lb of fuel for 3.5 h on station against the 977.3 lb on
board.

### 5.2 Worst case against h

Source: same `info_gap.json`, `worst_case_curve`. There is no figure of this curve for the frozen design;
the table is the record. The only figure of this run is
`figures/2026-11-25_task12_m250_baseline_appl/w0_against_power.png`, which has one point (450 hp,
3,160 lb).

| h | Worst hours on station | Worst take-off over 50 ft (ft) | Worst landing over 50 ft (ft) |
|---|---|---|---|
| 0 | 9.031 | 793.5 | 1,419.2 |
| 0.25 | 7.727 | 879.4 | 1,495.7 |
| 0.5 | 6.428 | 987.9 | 1,587.9 |
| 0.75 | 5.081 | 1,144.2 | 1,705.2 |
| 1.0 | 3.768 | 1,366.8 | 1,855.4 |
| 1.5 | mission not flyable | 2,468.8 | 2,340.0 |
| 2.0 | mission not flyable | no climb gradient after lift-off | 3,545.7 |
| 3.0 | mission not flyable | thrust below rolling resistance | landing does not close (no braking force) |

"Mission not flyable" is the record's reason "no speed on the leg within the engine's power": this is the
transit cliff, which the horizon 1.178 locates.

### 5.3 One quantity at a time, at the band ends (h = 1)

Source: same `info_gap.json`, `one_at_a_time`. Nominal: 9.031 h, 793.5 ft, 1,419.2 ft. Four of the 28
active quantities are shown; 26 of the 54 are inert.

| Quantity | Band | Hours on station (low / high end) | Take-off (ft, low / high end) |
|---|---|---|---|
| engine SFC multiplier | 0.9 to 1.1 | 10.656 / 7.702 | no effect |
| propeller factor f | 0.80 to 0.90 | 8.460 / 9.582 | 809.8 / 778.9 |
| engine power cap | 0.9 to 1.1 | 8.986 / 9.043 | 822.6 / 793.5 |
| airfoil C_L,max | 1.3 to 1.7 | 8.785 / 9.152 | 861.2 / 737.9 |

With the SFC 10 % high alone the aircraft flies 7.702 h on station, below the nominal 8 h and above the
3.5 h guarantee. That is what the restated R5 allows.

### 5.4 Where the guarantee is thin

Source: `runs/task12/stage3/2026-11-26/appl_decomposition/decomposition.json`, quoted in the last two
sections of `docs/validation/2026-11-25_task12_m250_baseline_appl.md`.

- This baseline is 43.4 lb heavier than the flat-propeller baseline (3,160.3 against 3,116.9 lb): +27.3 lb
  of fuel and +16.1 lb of empty weight. Sized to an 8 h loiter the two differ by 7.2 lb; the rest comes
  from what the worst case at h = 1.05 needs.
- At the worst endurance point the disk costs +19.7 lb of fuel against the flat low end, of which the
  climb leg is +18.5 lb. The disk's efficiency in that climb is 0.6673; the flat low end is 0.7475.
- So the robust weight rests on the disk at its most heavily loaded point, where f = 0.85 at low speed is
  a judgement beyond App. L, and on Stage 1's two-point climb model. No run varies f over its band for
  the climb alone.
- The seed corners were found for the flat propeller and carry `eta_p`, which is inert here. The mode
  search added the f-low corner and the second iteration closed with no violation, so the result stands.

### 5.5 Take-off against the propeller factor f (ruling G-9)

Source: `docs/validation/2026-11-26_task12_takeoff_f_sweep.md`, from
`runs/task12/stage1/2026-11-26/takeoff_f_sweep/sweep.json` (commit `ea0abb1`, clean tree). Not a re-size:
weight, fuel and engine are held; only f changes.

| f | Static thrust (lb) | Ground roll (ft) | Take-off over 50 ft (ft) | Margin to 2,500 ft (ft) | Landing over 50 ft (ft) |
|---|---|---|---|---|---|
| 0.60 | 1,572 | 421 | 929 | 1,571 | 1,419 |
| 0.65 | 1,659 | 392 | 886 | 1,614 | 1,419 |
| 0.70 | 1,743 | 368 | 853 | 1,647 | 1,419 |
| 0.75 | 1,825 | 347 | 829 | 1,671 | 1,419 |
| 0.80 | 1,906 | 328 | 810 | 1,690 | 1,419 |
| 0.85 | 1,984 | 312 | 793 | 1,707 | 1,419 |
| 0.90 | 2,061 | 297 | 779 | 1,721 | 1,419 |

R7 take-off is met at every f from 0.60 to 0.90 at nominal values of everything else. **f at static and
take-off conditions is a judgement beyond App. L**, which speaks of efficiency in flight; the book gives
no static number. The sweep is at sea level ISA and the record's weight only, and it does not combine a
low f with the other worst-case quantities beyond what the info-gap study already does inside the band
0.80 to 0.90.

### 5.6 R13: what holds the static margin

Source: `docs/validation/2026-11-26_task12_stage3_aero_m250_appl.md` and
`docs/validation/2026-11-26_task12_vspaero_m250_appl.md`.

- The layout code places the wing so that the full and empty margins are centred in the band (their sum
  is 0.200). The margins 0.116 and 0.083 are therefore not measured margins above the 5 % floor.
- What is physical is the CG travel, 0.032 MAC, and the accuracy of the neutral point.
- The empty-fuel margin changes by -0.059 MAC per 0.1 of downwash gradient and reaches the floor at a
  gradient of 0.515 (lattice at the nominal tail height: 0.457). Over the band of tail heights the
  margins run 0.071 to 0.144.
- The static-margin rows use the same lattice downwash as Stage 1, so they are not independent (7.1c
  item 3). Anderson's (8.76)-(8.78) with the same downwash is algebraically Raymer's (16.9).
- VSPAERO, wing and tails without fuselage, puts the neutral point 0.240 to 0.283 ft aft of Stage 1's and
  never ahead of it. About half of that offset (+0.110 / +0.154 ft) remains after the fuselage term is
  removed from Stage 1's own equation; the report does not decompose the remainder.
- **There is no independent fuselage-inclusive neutral point.** The fuselage-plate VSPAERO configuration
  of 2026-11-24 was not mesh-robust and was not run on this design.
- Static margin, trim drag, downwash and tail height are not in the info-gap horizon (`tail_height_over_df`
  is inert in the study; trim drag is not modelled).

### 5.7 What the info-gap study does not cover

Source: `info_gap.json`, `exclusions`, and the baseline report.

- Headwind strength (25 kt fixed) and the Oswald efficiency e are outside the horizon (owner, 2026-11-22).
- ISA temperature deviation is not varied.
- The engine control law and the shape of the part-power SFC curve are not varied (only a uniform
  multiplier on the table).
- Trim drag is not modelled.
- R12 (climb and ceiling) and R16 (turn) are not inside the horizon. Nor is the 70 kt stall clause of R7.
- Each worst case is a search, not a proof. The grid of the sizing is one cell (W/S 16, A 7).

## 6. Disagreements and their diagnosis

Rows outside tolerance are reported, not tuned. Diagnoses are the generated ones of the perf, engine and
aero reports unless marked.

| Row | Size | Diagnosis | Status |
|---|---|---|---|
| Installed power for take-off (Mattingly against Raymer) | -10.89 % against ±5 % | Two models of the climb-out after lift-off, where both are near zero climb gradient and the distance is most sensitive to power. At Mattingly's 142.3 hp Raymer's route gives 4,550 ft. k_TO does not explain it (138.1, 142.3, 148.9 hp at k_TO 1.15, 1.2, 1.25). The row says nothing about the installed power: the rating, 450 hp, is far above both | outside; diagnosed in the report; no owner ruling on it |
| Take-off weight, Anderson first estimate | +124.94 % against ±10 % | His empty fraction 0.62 is a historical value for crewed aircraft. The denominator 1 - 0.3097 - 0.62 is small. With Stage 1's fraction 0.5326 the same route gives 3,168.9 lb (+0.3 %) | outside; counted as explained by ruling G-2 |
| Zero-lift drag | -18.63 % against ±10 % | Anderson's Cfe 0.0043 gives 0.02011; the Cfe that reproduces Stage 1 is 0.005284. The method resolves CD0 to about ±20 % and has no place for sponsons, sensor, engine and leakage terms. Stage 1 is the higher, conservative value | outside; G-3 fixed the coefficient; the row cannot confirm Stage 1's CD0 to ±10 % |
| Fig. K.3 S at pi_c 17 and 35 (cycle model against the book) | -5.7 %, -5.6 % against ±5 % | none recorded. The model reads low on fuel consumption in all six S rows | outside; reported, not tuned; no diagnosis |
| Sea-level rate of climb, closed form | -15.11 % (no tolerance) | (5.121) assumes power available independent of speed; the disk's efficiency rises with speed (0.5902 at 64.6 kt, 0.7195 at 99.0 kt). Bracket 2,238 to 2,845 ft/min; Stage 1's 2,636 lies inside | not judged; the excess-power row (0.00 %) is the coding check |
| Best-climb speed | -34.79 % (no tolerance) | Same cause: the closed form returns the minimum-power speed 64.6 kt; with the disk the best climb moves to 99.0 kt (1.67 V_stall), an interior maximum | not judged |
| Take-off weight, Anderson build-up | +9.12 % (no tolerance) | Raymer's own Table 15.2 approximate method, so not independent | not judged |
| Span efficiency | +0.152 against ±0.05 | The lattice gives the inviscid planform value; Raymer's (12.49) is a whole-aircraft fit with separation drag. The spec asked for the inviscid share of (12.49), which Raymer does not give | not judged (not comparable as specified) |
| Static margin by Anderson (8.76) as printed | +0.280 against ±0.03 | The printed relation leaves out downwash and tail efficiency | not judged (book's simplification) |
| Ground-effect lattice against Anderson (6.77) | -38.1 %, -25.0 %, -16.8 % at h/b 0.1, 0.2, 0.3 against ±15 % | The two books differ by 29 % at h/b 0.1; the lattice is inside Raymer (12.61) at every h/b | reported; does not decide the rotation row (G-7) |
| VSPAERO full-fuel margin 0.159 to 0.167, above the R13 band | +0.043 / +0.051 MAC over Stage 1 | No fuselage in the model, so expected to read high; about half the offset is not the fuselage term | supporting only (G-8); R13 not closed |

By 7.1a a row outside tolerance sends the design back to Stage 1 if it moves a requirement margin below
zero. No record shows that for any row above: the take-off power row is not about installed power, the
CD0 row is in the favourable direction, and the first-estimate weight is ruled explained. For the two
Fig. K.3 rows no run translates the cycle model's low reading into fuel for this design; the ±10 % SFC
band of the info-gap study is what carries it.

## 7. Against the Gate B pass criterion (7.4)

Spec 7.4: "Pass when every requirement is met by the independent measurement with its margin, every row
is inside tolerance or explained, and the robustness horizon at the requirements is at least the value
fixed at Gate A." The three parts are taken in turn. This section does not decide the gate.

### 7.1 Every requirement met by the independent measurement with its margin

| Requirement | Met on the record? | By an independent measurement? |
|---|---|---|
| R1, R2, R3, R4, R8, R10, R14, R15, R17, R19 | yes | nothing to measure: by construction or process |
| R5, 8 h nominal | yes, 9.031 h | **no.** Coding check; SFC rests on the engine model (G-6); Anderson's fuel fraction is partly independent |
| R5, 3.5 h at h = 1 | yes, horizon 1.051 | **no.** Info-gap study on the Stage 1 model |
| R6 | not checked | **no.** Declared assumption (R-f) |
| R7 take-off and landing distance | yes | **partly.** Anderson's relations, with Stage 1's thrust function, CD0 and C_L,max. Unfactored by ruling G-1. No independent check of take-off thrust |
| R7 stall 70 kt | yes, 59.17 kt | **no.** Ledger C_L,max; SU2 row waived (G-5) |
| R9 | yes | **no.** Stage 1 only; gust second source waived (G-5); corner speed is a coding check |
| R11 | by construction | **no.** No row checks the speed choice |
| R12 climb | yes | **no.** Coding check; closed form does not apply with the disk |
| R12 ceiling | yes | **no.** Not judged: same engine table (7.1b), no altitude data |
| R13 | yes, by construction | **no.** Same downwash model; VSPAERO has no fuselage (G-8) |
| R16 | yes | **no.** Coding check |
| R18 | yes, by construction | **no.** Depends on the autopilot enforcing V_C |

**As written, this part is not met**: no requirement that needs a measurement is met by a fully
independent one. R7's distances are the nearest (partly independent). What exists instead is listed in the
right-hand column: coding checks, rulings G-1, G-5 and G-6, the assumption R-f, and construction for R13.

### 7.2 Every row inside tolerance or explained

| Group | Rows |
|---|---|
| Inside tolerance (judged) | perf: 12 rows; engine: 3 brochure rows; aero: lift slope; cycle model: 16 of 18 |
| Outside, explained by owner ruling | Anderson first-estimate W0 (G-2) |
| Outside, diagnosed in the report, no ruling that it counts as explained | take-off power (-10.89 %); CD0 (-18.63 %; G-3 fixed the coefficient and states the row cannot confirm Stage 1 to ±10 %) |
| Outside, reported, no diagnosis | Fig. K.3 S at pi_c 17 and 35 |
| Not judged, numerically outside or without tolerance | closed-form rate of climb and best-climb speed; span efficiency; Anderson (8.76) as printed; Anderson build-up W0 |
| Not judged, numerically inside | engine power, SFC and ceiling rows (7.1b); ceiling power; mission fuel; service ceiling; downwash and static-margin rows (7.1c) |
| Not computed or not run | gust load factors; SU2 polars and C_L,max; blade-element propeller (all G-5 waived) |
| Outside its own validation, does not decide a row | ground-effect lattice against Anderson (G-7) |

**Not met as written**: three rows are outside without a ruling (take-off power, CD0, the two Fig. K.3
rows counted as one item), and three spec rows have no measurement. Whether the diagnoses and the G-5
waiver are enough is the owner's call.

### 7.3 Robustness horizon at least 1 at R7 and at R5's robust endurance

| Requirement | Horizon | Threshold | On the record |
|---|---|---|---|
| R5, 3.5 h on station | 1.051 | 1 | met |
| R7, field length (take-off binds) | 1.506 | 1 | met |

**Met on the record**, with these limits stated: each horizon is a search on the Stage 1 model, not a
proof; the exclusions of section 5.7 apply; the take-off horizon rests on f at low speed (judgement); R7
is unfactored (G-1); the R5 horizon is 1.05 by construction of the sizing, so the margin over 1 is the
one that was asked for and no more.

### 7.4 Summary, criterion by criterion

| Part of 7.4 | Status |
|---|---|
| Every requirement met by the independent measurement | every requirement is met on the record or by construction, except R6 (assumption, not checked); **not met as written**, because the evidence is not independent |
| Every row inside tolerance or explained | **not met as written**: one row explained by ruling, three outside without a ruling, three rows of 7.1 not measured (waived) |
| Robustness horizon at least 1 | **met on the record** (1.051 and 1.506) |

## 8. Not run or waived

| Item | Status | Where stated |
|---|---|---|
| SU2 section polars and C_L,max | not run; waived before Gate B (G-5). The 70 kt stall rests on the ledger's 1.35 | perf and aero reports |
| Gust load factor, second source | not computed; waived (G-5) | perf report |
| Propeller efficiency by blade element | no code; waived (G-5) | perf report |
| Engine closing check (maker's part-power curve, altitude rating) | no data; accepted as "rests on the model" (G-6) | engine report |
| Engine maximum operating altitude and relight | no public source; design assumptions (R-f) | `2026-11-24_task12_m250_r6_sources.md` |
| FAR field-length factors on R7 | not applied (G-1) | perf report |
| Fuselage-inclusive independent neutral point | not run; the fuselage-plate VSPAERO case is not mesh-robust (G-8) | VSPAERO report |
| VSPAERO mesh finer than L2 | not run | VSPAERO report |
| Re-size of the design with the engine family's SFC | not done; the bands are carried by the info-gap study | engine report |
| Take-off sweep at another site, weight, temperature or lapse | not run | sweep report |
| Static C_T/C_P varied in the take-off sweep | not varied | sweep report |
| f varied over its band for the climb leg alone | not run | baseline report |
| Stage 1 compliance table and report for the frozen design | not generated; the record carries `failed: []` only | this report, section 1 |
| Gust load factors at the level top speed of the frozen design | not in the record | this report, section 4 |
| Figure of the worst-case curve for the frozen design | none exists; the table in 5.2 is the record | this report |
| Compressibility, fuselage and nacelle on the lattice, slipstream at the tail | not measured | aero report |
| Flap's own ground effect in the rotation row | not computed | rotation report |

## 9. Open items

1. **R13 has no independent neutral point with the fuselage.** It is met by layout construction with the
   shared lattice downwash. Review question 8 was answered by G-8 with a wing-and-tail run only.
2. **No independent propeller check**, in flight, in climb or at take-off (G-4 plus G-5). f = 0.85 at low
   speed and the band 0.80 to 0.90 are judgements. The robust weight is sensitive to exactly this through
   the climb leg (section 5.4), and R7's binding horizon is now the take-off one.
3. **Engine model.** 71.8 % of the mission fuel is burned in unchoked cells; the table is validated at sea
   level, 70 to 100 % power only; the brochure rows cannot fail (G-6); the cycle model reads 4.6 to 8.6 %
   low on fuel consumption against the book with 2 of 18 rows outside. The ±10 % SFC band stands in for
   data.
4. **R6.** Engine altitude limit and relight are assumptions (R-f). The 23,000 ft ceiling of R12 is above
   every certified B17 installation found (20,000 ft).
5. **Take-off power row, -10.89 %.** Diagnosed, not ruled.
6. **CD0, -18.63 %.** The method cannot confirm Stage 1 to ±10 % (G-3). No second route has been run.
7. **Fig. K.3 rows outside.** Reported; no diagnosis and no run of their effect on this design's fuel.
8. **Coding checks are not verifications.** Mission fuel, the power rows, the climb, the ceiling and the
   corner speed agree with Stage 1 because inputs and formula are shared.
9. **Climb model.** Stage 1's climb leg is a two-point estimate (mean drag over thrust of sea level and
   the mission altitude at one speed); the worst case leans on it.
10. **Composite factor band is inert** in the built aircraft (section 4, R9 note). Whether R9's band
    should act on the build-up is for the owner.
11. **R9 negative limit**: -1.5 in spec section 3, -1.8 in the ledger. Section 3 of the spec was not
    updated.
12. **V_C placard.** The level top speed is above V_C at sea level and at 20,000 ft; R18 holds only with
    autopilot enforcement, and the gust factors at top speed are not recorded for this design.
13. **The 8 h nominal has little robustness** (h = 0.198; 7.702 h with the SFC 10 % high alone). This is
    what the restated R5 allows, and it should be said at the gate.
14. **Record hygiene.** The engine, aero and rotation records (commit `3f0c099`) carry no dirty-tree flag;
    the perf and sweep records do (clean). The robust-sizing run had one untracked path (its own output).
    The two added sections of the baseline report are hand-written and a regeneration would drop them.
15. **Info-gap exclusions** as listed in section 5.7.

## 10. Numbers that differ between sources

None of these is a conflict in the records; each is two different quantities or two roundings. They are
listed so that nobody quotes the wrong one.

| Number | Values | Why |
|---|---|---|
| Static margin, empty fuel | 0.0838 (record, VSPAERO report); 0.084 and 0.083 (aero report) | rounding of the Stage 1 value and of the lattice row |
| Raymer bare-planform lift slope | 4.739 (aero report); 4.783 (VSPAERO report) | Mach 0 against the loiter Mach (`results.json`: 4.7394 at 0.0, 4.7830 at 0.158) |
| Service ceiling | 29,746.6 ft (Stage 1); 29,350.1 ft and 29,893 ft (Anderson bracket, perf); 29,715.765 to 29,748.251 ft (engine family) | different relations; the review's "29,350 to 29,748" mixes two of them |
| Horizons | 1.05, 1.18, 1.51 (baseline report table); 1.051, 1.178, 1.506 (records, `run.log`) | rounding |
| Climb propeller efficiency | 0.7202 at 99.2 kt (`propeller_points`); 0.7195 at 99.0 kt (climb bracket); 0.7271 (decomposition, mid-altitude of the climb) | different points |
| Loiter propeller efficiency | 0.7861 (leg start, perf row); 0.7917 (mean over sub-steps, decomposition); 0.7677 (held in Anderson's route) | different points |
| Unchoked fuel share | 71.8 % (frozen design); 54.5 % (Stage 1 App. L report) | different aircraft (3,160 lb against 3,005 lb) |
| Anderson W0 values in ruling G-2 | 6,396, 3,061, 3,376 lb (ruling text, old baseline); 7,108.7, 3,168.9, 3,448.5 lb (this design) | the ruling quotes the 2026-11-24 baseline |
| "0.62 at sea-level climb" in ruling G-4 | 0.6205 (Stage 3 value on the 2026-11-24 baseline, perf report comparison table); 0.7202 (this design, at its own best-climb speed of 99.2 kt) | different design and speed; on this design the disk gives 0.5902 at 64.6 kt |
| Take-off thrust speed | 0.707 V_TO (Stage 1, sweep); 0.7 V_LO (Anderson row) | two books' rules |
| Negative limit load factor | -1.5 (spec section 3); -1.8 (ledger) | Gate A change not carried into the spec table |

## 11. Records and reports used

| What | Record | Report |
|---|---|---|
| Frozen design, robust sizing, info-gap study | `runs/task12/stage3/2026-11-25/m250_baseline_appl/` (`curve.json`, `run.log`, `P450/h1.05/design_pusher.json`, `target_result.json`, `info_gap.json`, `ledger.yaml`) | `docs/validation/2026-11-25_task12_m250_baseline_appl.md` |
| Decomposition of the +43 lb | `runs/task12/stage3/2026-11-26/appl_decomposition/decomposition.json` | same report, last sections |
| Stage 3 engine, perf, aero, rotation, ground effect | `runs/task12/stage3/2026-11-26/m250_baseline_appl_measure/` | `docs/validation/2026-11-26_task12_stage3_{engine,perf,aero,rotation}_m250_appl.md` |
| VSPAERO, wing and tails | `runs/task12/openvsp/2026-11-26_m250_baseline_appl_vspaero/results.json` | `docs/validation/2026-11-26_task12_vspaero_m250_appl.md` |
| Take-off sweep over f | `runs/task12/stage1/2026-11-26/takeoff_f_sweep/sweep.json` | `docs/validation/2026-11-26_task12_takeoff_f_sweep.md` |
| Stage 1 App. L run (a different design, section 1) | `runs/task12/stage1/2026-11-25` | `docs/validation/2026-11-25_task12_conceptual_m250_appl.md` |
| R6 sources | no run | `docs/validation/2026-11-24_task12_m250_r6_sources.md` |
| Rulings | - | `docs/specs/00_decisions.md` section 9 (R-a to R-f, G-1 to G-9) |
| Reviews | - | `docs/reviews/2026-11-24_task12_stage3_m250_review.md`, `2026-11-25_task12_appl_propeller_review.md`, `2026-11-26_task12_stage3_appl_review.md` |

Numbers marked "computed" in the reviews are not records and are not quoted here.

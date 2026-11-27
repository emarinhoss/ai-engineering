# Task 12 Stage 3 output: measured performance of the W/S 13, A 8 baseline (spec 7.3)

Written by hand on 2026-11-27 from the records and generated reports listed in section 11. **No run was
made for this report.** The figure, the Gate A record and the pytest record named in section 13 were made
afterwards from existing records (ruling B-10). It replaces
`docs/validation/2026-11-26_task12_performance.md`, which stays as the record of the superseded W/S 16,
A 7 design.

How to read the numbers:

- Every number is copied from a committed record or from a report generated from one. Each table names
  its file.
- A number from a generated report is printed as that report prints it. A number read from a JSON record
  is rounded to the digits shown (horizons to four decimals, weights to 0.1 lb).
- "Margin" is the limit minus the quoted value, or the reverse. It is a subtraction of two numbers quoted
  in the same row and nothing else. Other sums and differences are marked "arithmetic".
- Numbers of the superseded design are copied from the 2026-11-26 report and are named as such.
- Numbers that the reviews mark as a probe or as the reviewer's own run are not records and are not
  quoted. Section 12 lists what was left out.

This report does not decide Gate B. Section 6 lays the evidence against the pass criterion of spec 7.4.
The owner rules.

## 1. Summary

### 1.1 The baseline

The baseline is W/S 13, A 8 (ruling B-2c, 2026-11-27):
`runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/`.

Source: `design_pusher.json` and `cell_result.json` of that record.

| Quantity | Value |
|---|---|
| Concept | pusher, Rolls-Royce M250-B17F, 450 shp, 212 lb |
| W/S, A | 13 lb/ft^2, 8 |
| Take-off weight W0 | 3,517.3 lb |
| Empty weight | 1,918.6 lb |
| Fuel | 1,098.7 lb |
| Payload | 500.0 lb |
| Wing area, span | 270.56 ft^2, 46.52 ft |
| Horizontal tail area | 135.48 ft^2 (volume scale 1.59) |
| Sized loiter | 11.00 h |
| V_C placard, V_D | 110 kt EAS, 165 kt EAS |
| Power margin | 37.5 % |
| Propeller model | App. L actuator disk, real-to-ideal factor f = 0.85 (ledger band 0.80 to 0.90), diameter 6.91 ft |
| Stage 1 compliance rows failed | none (`failed: []`; compliance table: 19 pass, 0 fail, 11 not tested) |

Three things to know before reading on:

- **The fuel is sized for the worst case, not for 8 h.** The loiter was sized up to 11.00 h so that the
  worst case at h = 1.05 still gives 3.5 h on station. At nominal values the aircraft flies 11.000 h on
  station (`info_gap.json`, `nominal.R5_hours`).
- **V_C is set by the 110 kt floor.** The fastest cruise sub-step is 94.96 kt EAS. The 10 % rule gives
  104.5 kt (compliance row 19), rounded up to 105 kt, which is below the 110 kt EAS floor of spec R18.
- **There is no Stage 1 package for these sizes.** The latest package,
  `docs/validation/2026-11-25_task12_conceptual_m250_appl.md`, describes a different aircraft (3,005 lb,
  W/S 22, A 8). Ruling B-9a accepts the record, the compliance table and the Gate A re-check of
  `docs/reviews/2026-11-27_task12_gateB_ws13a8_review.md` (section 5) in its place.

### 1.2 Why the frozen design was replaced

The frozen design was W/S 16, A 7 (3,160.3 lb, sized loiter 9.03125 h; values from the 2026-11-26
report). Review GB-1 found that the composite band of R9 never reached the built aircraft, and that no
band acted on the weight equations themselves. Ruling B-2 asked for an info-gap run with both.

**The B-2 band result.** Source: `docs/validation/2026-11-26_task12_composite_band_study.md`, from
`runs/task12/stage3/2026-11-26/composite_band_study/summary.json` (commit `b652c6e`, clean tree, seed
20261122). The frozen design was not re-sized in this study.

| Case on the frozen design | R5 guarantee horizon | Worst hours on station at h = 1 | R7 horizon |
|---|---|---|---|
| new bands off (reproduces the frozen record) | 1.0514 | 3.768 | 1.5059 |
| composite band, mapping `saving` | 0.9624 | 3.281 | 1.3898 |
| composite band `saving` + empty-weight band (ruling B-2) | **0.9062** | **2.915** | 1.2880 |
| composite band, mapping `scale` (comparison) | 1.0104 | 3.554 | 1.4529 |
| composite band `scale` + empty-weight band (comparison) | 0.9496 | 3.206 | 1.3484 |

- `composite_model: saving` scales each Table 15.4 weight saving by (1 - c)/0.05, so c = 1.00 is a metal
  aircraft. `empty_weight_factor` is 1.0 with a band 0.95 to 1.05 on the summed build-up. Both mappings
  are judgements. The owner confirmed them (B-2a).
- With both bands the frozen design fails R5: horizon 0.9062 against 1, and 2.915 h against 3.5 h at
  h = 1. R7 still holds (horizon 1.2880).
- Ruling B-2a: re-size to h_T 1.05 with both bands acting.

**The re-size.** Source: `docs/validation/2026-11-26_task12_m250_bands_resize.md`, from
`runs/task12/stage3/2026-11-26/m250_bands_resize/curve.json` (commit `5998763`, seed 20261122; the tree
had one untracked path, the run's own output folder). Grid: W/S 13 to 17, A 7 to 10, 450 shp as is.

W0 over the grid at h_T 1.05, last iteration (lb; "-" means no design):

| A \ W/S | 13 | 14 | 15 | 16 | 17 |
|---|---|---|---|---|---|
| 7 | 3493 | - | - | - | - |
| 8 | 3517 | 3460 | - | - | - |
| 9 | 3563 | 3506 | - | - | - |
| 10 | 3632 | 3556 | - | - | - |

- **W/S 16, A 7 has no design under both bands.** The report's reason: "too heavy already at 8 h: cliff
  corner not flyable (no speed on the leg within the engine's power)".
- The tool's lightest design is W/S 14, A 8 at 3,460 lb, with a cliff horizon of 1.0615.
- One candidate (W/S 17, A 10) is unresolved: its weight iteration did not converge.

**The choice among three cells.** Ruling B-2b asked for the full info-gap study on W/S 13, A 8 and
W/S 13, A 9 next to the winner. Source: `docs/validation/2026-11-26_task12_m250_bands_cells.md`, from
`runs/task12/stage3/2026-11-26/m250_bands_cells/summary.json`.

| | W/S 14, A 8 (re-size winner) | **W/S 13, A 8 (chosen)** | W/S 13, A 9 |
|---|---|---|---|
| W0 (lb) | 3460 | 3517 | 3563 |
| fuel (lb) | 1095 | 1099 | 1095 |
| L_sized (h) | 10.91 | 11.00 | 11.16 |
| span (ft) | 44.5 | 46.5 | 49.7 |
| power margin | 36.6 % | 37.5 % | 39.7 % |
| R5 guarantee horizon (full study) | 1.0503 | 1.0501 | 1.0505 |
| cliff mode horizon | 1.0615 | 1.0924 | 1.0999 |
| R7 horizon (take-off binds in all three) | 1.2748 | 1.2845 | 1.2762 |
| worst endurance at h = 1 (h) | 3.827 | 3.827 | 3.826 |
| worst cliff ratio at h = 1 | 0.9477 | 0.9231 | 0.9147 |
| worst take-off / landing at h = 1 (ft) | 1636 / 1835 | 1585 / 1790 | 1620 / 1795 |
| nominal 8 h horizon | 0.4091 | 0.4135 | 0.4206 |

- Ruling B-2c chose W/S 13, A 8 over W/S 14, A 8 "for its cliff and R7 margin". Against the winner it
  costs +57 lb of W0, +3 lb of fuel and +2.1 ft of span, for +0.0309 of cliff horizon and +0.0097 of R7
  horizon (cells report, "Differences from the winner").
- Only these three cells have a full study. W/S 13, A 7 (3,493 lb in the grid) and the other cells do not.
- The alternatives' L_sized was bisected against the corner sets of the re-size, not against their own
  mode searches. That the guarantee of W/S 13, A 8 reaches 1.05 is therefore a result of its own study
  (1.0501), not a construction.

### 1.3 What the records show, in short

- **No recorded value of the baseline is on the wrong side of a requirement.** Section 2: 13 clauses
  pass, 0 fail, 12 are not tested (by construction, by process or resting on a declared assumption).
- **Both Gate B horizons are at least 1**: R5 guarantee 1.0501, R7 1.2845 (section 3).
- **Three perf rows and two cycle-model rows are outside tolerance.** Each is carried by a ruling
  (G-2, G-3, B-5, B-9e). Two ceiling rows are not judged and numerically outside. Their cause is the
  engine table's top altitude (B-9c). Section 4.
- **The evidence is mostly not independent.** Ruling B-1 accepts the declared evidence classes in place
  of "independent measurement". Section 4.1 lists the independent rows: there are four, and one of them is not computed.
- **Gust margins are thin**: 0.296 g positive and 0.196 g negative, about half those of the superseded
  design (0.561 and 0.461). Ruling B-9d confirms B-4 at these margins (section 5.2).
- **The design leans further on the unvalidated part of the engine table**: 77.4 % of the mission fuel
  burns in unchoked cells (71.8 % on the superseded design). Section 4.3.

## 2. Verdict per requirement

Evidence classes are those of ruling B-1: independent, partly independent, coding check, ruling or
waiver, assumption, layout construction. Two more labels are used and are not B-1 classes: "by
construction" (nothing to measure; the compliance table's own rule) and "info-gap search" (the robustness
study of spec 7.2 on the Stage 1 model).

Verdict: **pass** means a recorded value was compared with a limit and is on the right side. **not
tested** means no numerical test exists; the reason is in the class column. Limits are those of spec
section 3 and of the record's ledger copy with the Gate A margins (ceiling +500 ft, negative gust 0.1 g,
power margin 0).

Sources: C = `docs/validation/2026-11-27_task12_stage1_compliance_ws13a8.md`
(`runs/task12/stage3/2026-11-27/compliance_ws13a8/compliance.json`, commit `e506e25`, clean tree), with
its row number; D = `design_pusher.json` of the baseline; I = `info_gap.json` of the baseline; P, E, A =
the Stage 3 perf, engine and aero reports of 2026-11-27; V = the V-n report of 2026-11-27.

| ID | Requirement | Value | Margin or horizon | Evidence class (B-1) | Source | Verdict |
|---|---|---|---|---|---|---|
| R1, R2 | single turboprop, one engine | RR M250-B17F, one | - | by construction | C row 1 | not tested |
| R3 | rubber engine first, then a real engine and a fixed-engine re-size | fixed-engine re-size around the M250-B17F | - | ruling (R-a). No rubber-engine design was sized at these sizes | no compliance row | not tested |
| R4 | payload 500 lb | 500 lb | 0 | by construction | C row 2; D `payload_lb` | not tested |
| R5 | 8 h on station at nominal values | 11.000 h | +3.000 h; the 8 h hold to h = 0.4135 (no threshold) | coding check plus assumption. Mission fuel is a coding check, not judged (7.1b). The SFC in the mission cells rests on the engine model (G-6) | I `nominal`, `h_hat.R5`; P mission-fuel row | pass |
| R5 | at least 3.5 h for every member of the bands (h = 1) | horizon 1.0501; worst case at h = 1: 3.827 h | +0.0501 in h; +0.327 h at h = 1 | info-gap search on the Stage 1 model. A search, not a proof | I `h_hat.R5_guarantee`, `worst_case_curve` | pass |
| R6 | cruise and loiter at 20,000 ft, ISA | mission flown at 20,000 ft | - | by construction | C row 5 | not tested |
| R6 | engine can operate and relight there | no source for the maximum operating altitude or the relight envelope | - | assumption (R-f). Not checked, none invented | C rows 4, 5 | not tested |
| R7 | take-off over 50 ft at most 2,500 ft | 711 ft (Stage 1), 719 ft (Anderson) | 1,789 ft / 1,781 ft; horizon 1.2845 | partly independent, within ±15 % (+1.14 %). Unfactored (G-1). Both routes share the thrust function, which rests on f at low speed (G-9; sweep in section 5.3) | C row 6; P; I `h_hat.TO` | pass |
| R7 | landing over 50 ft at most 2,500 ft | 1,348.6 ft (Stage 1), 1,354.3 ft (Anderson) | 1,151.4 ft / 1,145.7 ft; horizon 1.6406 | partly independent, within ±15 % (+0.42 %). Unfactored (G-1). At take-off weight | C row 7; P; I `h_hat.LD` | pass |
| R7 | clean stall at most 70 kt | 53.33 kt | 16.67 kt | assumption plus waiver. Rests on the record's clean C_L,max 1.35; the SU2 C_L,max row is waived (G-5, B-6). Not inside the R7 horizon | C row 8 | pass |
| R8 | retractable tricycle gear | main gear retracts into sponsons, `fits: true` | - | by construction | C rows 9, 27 | not tested |
| R9 | positive limit load +3.8, gusts checked, larger case used | n_limit 3.8; largest gust 3.504 (V_C, 20,000 ft, zero-fuel weight); ultimate 5.7 | 0.296 below 3.8 | waiver. Stage 1's own loads code only; the gust second source is waived (G-5, B-6). Corner speed is a coding check | C row 10; V; D `gusts` | pass |
| R9 | negative gust at or above -1.7 (-1.8 with the 0.1 g margin, B-3) | -1.504 | 0.196 | waiver, as above | C row 11; V | pass |
| R10 | 6 % reserve and trapped fuel | factor 1.06 | - | by construction | C row 12 | not tested |
| R11 | cruise legs at best-range speed | 129.3 kt out, 119.1 kt back (true airspeed) | - | by construction of the mission code. The still-air closed form gives 103.6 kt (coding check). No row checks the speed choice | D `mission`; P | not tested |
| R12 | sea-level climb at least 1,000 ft/min | 2,325.8 ft/min (Stage 1); bracket 1,915 to 2,540 ft/min | 1,325.8 ft/min; 915 ft/min at the lower bracket | coding check; the closed form is not judged. Not inside the Gate B horizon | C row 13; P | pass |
| R12 | service ceiling at least 23,500 ft (23,000 ft plus the Gate A margin) | 30,407 to 30,432 ft (engine cycle, the value to quote, B-9c). Stage 1: 31,738 ft, above the engine table's top (30,000 ft, clamped). Closed form, lower bound: 29,955 ft | 6,907 ft on the lowest cycle value; 8,238 ft on Stage 1's; 6,455 ft on the closed form's lower bound | coding check, not judged (same engine table, 7.1b), with ruling B-9c. No altitude data behind the table. Not inside the Gate B horizon | C row 14; E; P | pass |
| R13 | static margin 5 to 15 % MAC, full fuel | 0.1126 | 0.0374 from the upper end | layout construction (B-6). VSPAERO wing and tails is support only (G-8, B-9f) | C row 15; A | pass |
| R13 | static margin 5 to 15 % MAC, empty fuel | 0.0874 | 0.0374 from the floor | layout construction (B-6) | C row 16; A | pass |
| R14 | no crew systems | none in the weight build-up | - | by construction | C row 17 | not tested |
| R15 | flight avionics fixed in the ledger | 60 lb uninstalled, 96.5 lb installed | - | by construction (ledger assumption, band 40 to 100 lb) | C row 18; D `components_lb` | not tested |
| R16 | sustained 30 deg turn at loiter, 20,000 ft | 243.5 hp needed against 450 | 206.5 hp | coding check. Not inside the Gate B horizon | C row 22; P | pass |
| R17 | every leg at least 1.3 V_stall | enforced in the speed choice; the whole loiter flies on the floor (`speed_floor_fraction` 1.0; 87.3 kt against a best-endurance speed of 78.74 kt) | 0 on the loiter | by construction | C row 20; D `mission`; P | not tested |
| R18 | one V_C placard, structure and gusts sized at it | 110 kt EAS (the floor); rule value 104.5 kt; fastest cruise sub-step 94.96 kt EAS | 5.5 kt on the rule value; 15.04 kt on the sub-step | by construction of the per-design rule (B-4). Holds only with envelope protection: level top speed is 185.2 kt EAS at sea level and 120.9 kt EAS at 20,000 ft (B-9d) | C row 19; V | pass |
| R19 | 25 kt headwind on both transit legs | 129.27 kt airspeed with 104.27 kt ground speed out; 119.07 kt with 94.06 kt back | - | by construction. The headwind strength is outside the info-gap horizon (owner, 2026-11-22) | C row 21; D `mission` | not tested |

**Counts: 25 clauses. 13 pass, 0 fail, 12 not tested.**

- Not tested, by construction or by process: R1/R2, R3, R4, R6 (altitude), R8, R10, R11, R14, R15, R17,
  R19. That is 11.
- Not tested, rests on a declared assumption: R6 (engine operating altitude and relight, R-f). That is 1.
- No requirement has a recorded value on the wrong side of its limit.

How this count relates to the compliance table (19 pass, 0 fail, 11 not tested over 30 rows):

- The compliance table has 8 rows that are not requirements R1 to R19 (rows 23 to 30: power margin, fuel
  volume, nose-wheel load full and empty, gear stowage, propeller clearance, trim, rotation). All 8 pass.
  Its other 11 passes are the R7, R9, R12, R13, R16 and R18 rows above.
- It has no row for R3 or R11, and its R5 row (row 3, "sized to it") is not tested. The two R5 verdicts
  above come from the info-gap record instead.

Notes on single requirements:

- **R9, two values for the same gust point.** The record holds 3.504 in `gusts` (lift slope at the
  speed's own Mach number; the value the structure was sized with) and 3.481 in `vn` (slope at the sizing
  Mach). This report quotes the first.
- **R9, composite band.** The band 0.90 to 1.00 now acts on the build-up (`composite_model: saving`,
  B-2a). `composite_factor` is no longer in `inert_variables` of the info-gap record. One at a time at
  the band ends it moves the hours on station from 11.890 to 10.145 (section 3.4).
- **R12 ceiling.** Row 14 of the compliance table prints 31,738 ft. That value leans on the table clamp.
  Section 4.7 gives the three values and the ruling.
- **Rows that pass with little room** (not requirements R1 to R19): the rotation tail CL is 0.9677
  against 1 (compliance row 30); the nose-wheel loads 0.1633 and 0.1515 pass the 5 to 20 % limits but
  are above the 0.08 to 0.15 optimum named in the row label (rows 25, 26).
- **Trim.** No Stage 3 row. Stage 1's flag `trim_ok` is true (compliance row 29). The largest tail CL in
  trim is 0.133 at the start of the loiter (`layout.trim`), against the ledger's `tail_cl_max_trim` 0.5.

## 3. Robustness

### 3.1 Horizons

Source: `info_gap.json` (`h_hat`) and `cell_result.json` (`modes`) of the baseline. Commit `20fa0e1`.
The tree had one untracked path, the run's own output folder (`git_dirty: true`). Base seed 20261122;
the ten sampling entries use seeds 20261122 to 20261163.

| Quantity | Horizon h | Threshold (spec 7.1a) | Note |
|---|---|---|---|
| **R5 guarantee: 3.5 h on station for every member** | **1.0501** | at least 1 | binding mode: endurance |
| - endurance mode | 1.0500 | | about the target by construction: the fuel is sized until the worst case at 1.05 gives 3.5 h (3.501 h at h_T 1.05) |
| - transit-cliff mode (the mission can still be flown) | 1.0924 | | worst cliff ratio 0.9231 at h = 1 and 0.9635 at h_T 1.05 |
| **R7: field length 2,500 ft** | **1.2845** | at least 1 | minimum of take-off and landing |
| - take-off | 1.2845 | | binds; rests on f at low speed |
| - landing | 1.6406 | | |
| 8 h on station, mission fuel only | 0.4135 | none | information: not the Gate B criterion |
| 8 h on station, reserve usable | 0.5387 | none | information |

- The R5 guarantee has two recorded values: 1.0501 from the full study (`info_gap.json`,
  1.05010986) and 1.0500 from the mode scan (`cell_result.json`, 1.05004883). Both are at or above the
  target h_T 1.05 of ruling R-d. The margin over 1.05 is the one that was asked for and no more.
- Against the superseded design (2026-11-26 report): the R7 horizon fell from 1.506 to 1.2845 and the
  cliff horizon from 1.178 to 1.0924. The R5 guarantee is the target in both. The two new bands account
  for the change: the superseded design under both bands had an R7 horizon of 1.2880 (section 1.2).

**Check of the search by sampling** (`h_hat.*.sampling`). At each horizon 200 random points and 32 corner
points were tried. None was worse than the search's worst case: `n_beating_search` is 0 in all ten
entries. At h = 1 the search's worst case needs 1,065.6 lb of fuel for 3.5 h on station against the
1,098.7 lb on board.

### 3.2 Worst case against h

Source: `info_gap.json`, `worst_case_curve`. The figure of this curve is
`runs/task12/stage3/2026-11-27/robustness_figure_ws13a8/robustness.png` (GB-7 closed, section 13). The
table is the record.

| h | Worst hours on station | Worst take-off over 50 ft (ft) | Worst landing over 50 ft (ft) |
|---|---|---|---|
| 0 | 11.000 | 711.0 | 1,348.6 |
| 0.25 | 9.215 | 815.4 | 1,422.0 |
| 0.5 | 7.369 | 971.5 | 1,515.2 |
| 0.75 | 5.586 | 1,205.9 | 1,633.9 |
| **1.0** | **3.827** | **1,584.6** | **1,789.7** |
| 1.5 | mission not flyable | 6,143.4 | 2,275.8 |
| 2.0 | mission not flyable | no climb gradient after lift-off | 3,523.4 |
| 3.0 | mission not flyable | no climb gradient after lift-off | landing does not close (no braking force) |

- "Mission not flyable" is the record's reason "no speed on the leg within the engine's power". This is
  the transit cliff, which the horizon 1.0924 locates.
- At h = 1.5 the worst take-off is 6,143.4 ft, far past 2,500 ft. The take-off distance grows steeply
  between h = 1 and h = 1.5; the horizon 1.2845 is where it crosses 2,500 ft.
- At h = 1 the worst take-off is 1,584.6 ft (1,367 ft on the superseded design, 2026-11-26 report).

### 3.3 The worst points at h = 1

Source: `info_gap.json`, `worst_case_curve` entry h = 1 (`moved`), and `cell_result.json`,
`modes.*.worst_at_h1`. Each list names the quantities the search moved to a band end; all others are at
their nominal values.

- **Endurance, 3.827 h.** Propeller factor f 0.80; airfoil C_L,max 1.3; wing t/c 0.12; laminar fraction
  of the wing 0.10; sensor drag area 0.8 ft^2; fuselage fineness 6; fuselage fill 0.85; composite factor
  1.00 (metal); empty-weight factor 1.05; avionics 100 lb; gust speed 50 ft/s; main-gear station guess
  0.3; pusher rotation angle 15 deg; sponson length per tyre 3; sponson depth per tyre 1.4; sponson
  weight per wetted area 1.8; engine SFC multiplier 1.1; engine power cap 0.9.
- **Transit cliff, ratio 0.9231.** The same point with the engine SFC multiplier at 0.9 instead of 1.1.
- **Take-off, 1,584.6 ft.** f 0.80; airfoil C_L,max 1.3; wing t/c 0.12; flap span fraction 0.5; take-off
  flap fraction 0.4; laminar fraction of the wing 0.10; sensor drag area 0.8 ft^2; fuselage fineness 6;
  fuselage fill 0.85; composite factor 1.00; empty-weight factor 1.05; avionics 100 lb; gust speed
  50 ft/s; rolling friction 0.05; take-off flap deflection 40 deg; strut width 4 in; main-gear station
  guess 0.3; pusher rotation angle 15 deg; sponson length per tyre 4.8; sponson depth per tyre 1.4;
  sponson weight per wetted area 1.8; nose tyre scale 1.0; engine power cap 0.9.
- **Landing, 1,789.7 ft.** Airfoil C_L,max 1.3; wing t/c 0.12; flap span fraction 0.5; laminar fraction
  0.5 (wing) and 0.2 (fuselage); sensor drag area 0.2 ft^2; fuselage fineness 6; fuselage fill 0.85;
  composite factor 1.00; empty-weight factor 1.05; avionics 100 lb; gust speed 50 ft/s; braking friction
  0.3; free roll 3 s; strut width 2 in; main-gear station guess 0.3; pusher rotation angle 15 deg;
  sponson length per tyre 4.8; sponson depth per tyre 1.4; sponson interference factor 1.3; sponson
  weight per wetted area 1.8; nose tyre scale 0.6.

Both new bands sit at their heavy end in all four worst points. The gust speed at 50 ft/s enters as
structure weight, not as a load check (section 5.2).

### 3.4 One quantity at a time, at the band ends (h = 1)

Source: `info_gap.json`, `one_at_a_time`. Nominal: 11.000 h, 711.0 ft, 1,348.6 ft. Six of the 30 active
quantities are shown; 25 of the 55 are inert.

| Quantity | Band | Hours on station (low / high end) | Take-off (ft, low / high end) |
|---|---|---|---|
| engine SFC multiplier | 0.9 to 1.1 | 12.924 / 9.426 | no effect |
| propeller factor f | 0.80 to 0.90 | 10.333 / 11.635 | 727.8 / 697.6 |
| engine power cap | 0.9 to 1.1 | 10.952 / 11.012 | 742.1 / 711.0 |
| airfoil C_L,max | 1.3 to 1.7 | 10.715 / 11.133 | 770.6 / 662.6 |
| **composite factor (new, B-2a)** | 0.90 to 1.00 | 11.890 / 10.145 | 666.0 / 762.6 |
| **empty-weight factor (new, B-2a)** | 0.95 to 1.05 | 11.557 / 10.457 | 681.9 / 742.4 |

- The largest single effect is the SFC: 9.426 h with the SFC 10 % high alone. That is the lowest value
  in the 30 active rows, and it is above 8 h.
- The gust speed at 50 ft/s alone gives 10.403 h (11.000 h at 30 ft/s).

### 3.5 The nominal 8 h horizon and ruling B-8

- The 8 h nominal loiter holds to **h = 0.4135** on mission fuel and to 0.5387 with the reserve usable.
  There is no threshold on either (spec 7.1a).
- Spec 7.1a expected zero here. It is above zero because the loiter was sized to 11.00 h.
- **Ruling B-8** acknowledges the nominal's small robustness "as what the restated R5 of 2026-11-22
  allows; no new target". The ruling text quotes the superseded design's horizon, 0.198. On this
  baseline the value is 0.4135. Ruling B-9 does not restate B-8 at the new value (section 8.4).

### 3.6 What the info-gap study does not cover

Source: `info_gap.json`, `exclusions` (five entries), and the cells and re-size reports.

- Headwind strength (25 kt fixed) and the Oswald efficiency e are outside the horizon (owner, 2026-11-22).
- ISA temperature deviation is not varied.
- The engine control law is not varied.
- The shape of the part-power SFC curve is not varied (only a uniform multiplier on the table).
- Trim drag (downwash and tail height) is not modelled. `tail_height_over_df` is inert in the study.
- R12 (climb and ceiling) and R16 (turn) are not inside the horizon. Nor is the 70 kt stall clause of R7.
- The empty-weight multiplier acts on the summed weight only. The component list and the centre of
  gravity do not change with it, and R13 was not re-checked at the band ends (composite band note).
- For h above 1 the composite factor stays at 1.00 (clipped); the empty-weight factor is not clipped.
- Each worst case is a search, not a proof. The grid of the re-size is 1 lb/ft^2 in W/S and 1 in A, and
  three cells have a full study.
- The step-doubling check of the re-size (W0 +1.2 lb, fuel +0.7 lb with the mission sub-steps doubled)
  was recorded for the W/S 14, A 8 winner only, not for this cell.

## 4. Stage 3 cross-checks

### 4.1 What kind of evidence there is

Classes as the perf report defines them:

- **independent**: another source, method and input.
- **partly independent**: another relation, with inputs or sub-models shared with Stage 1.
- **coding check**: same inputs and an algebraically equal formula. It can only show that the code is
  consistent; it does not verify the quantity.
- **not judged**: reported without a verdict (same table or model as Stage 1, or the relation does not
  apply).

**Independent evidence on this design, all of it:**

| Row | Result | Source file |
|---|---|---|
| Wing lift slope (vortex lattice against Raymer (12.6)) | -3.2 %, within ±5 % | aero report |
| Zero-lift drag (Anderson (2.37), Cfe 0.0043) | -14.32 %, outside ±10 %, favourable direction | perf report |
| Brochure part-power SFC, three points | +0.7 to +1.7 %, within ±10 %, but the rows cannot fail (G-6) | engine report |
| Gust load factors | not computed (no second source; G-5, B-6) | perf report |

Everything else is partly independent, a coding check, not judged, or not run. **There is no independent
check of the propeller**, in flight or at take-off: Stage 1 is on the App. L disk (G-4) and the
blade-element check is waived (G-5), so the Stage 3 propeller rows use the same relation and factor as
Stage 1. Ruling B-1 accepts the declared classes in place of "independent measurement".

### 4.2 Performance rows

Source: `docs/validation/2026-11-27_task12_stage3_perf_m250_ws13a8.md`, generated from
`runs/task12/stage3/2026-11-27/m250_ws13a8_measure/perf.json` (commit `1cfa964`, clean tree). Counts from
that report: 12 within, 3 outside, 6 not judged, 1 not computed. These are the same counts as on the
superseded design.

| Quantity | Class | Stage 1 | Stage 3 | Difference | Tolerance | Verdict |
|---|---|---|---|---|---|---|
| installed power, sea-level climb 1,000 ft/min (hp) | coding check | 223 | 223 | -0.00 % | ±5 % | within |
| installed power, 100 ft/min at the ceiling altitude 23000 ft (hp) | coding check | 281.1 | 281.1 | +0.00 % | ±5 % | not judged (numerically inside) |
| installed power, take-off over 50 ft in the field length (hp) | partly independent | 154.7 | 136.7 | -11.62 % | ±5 % | **outside** (B-5, B-9e: explained) |
| installed power, sustained 30 deg turn at loiter speed (hp) | coding check | 243.5 | 243.5 | +0.00 % | ±5 % | within |
| installed power, level cruise at mission altitude (hp) | coding check | 211.4 | 211.4 | +0.00 % | ±5 % | within |
| mission fuel (200 nm out + 11 h + 200 nm back, headwind) (lb) | coding check | 1,098.7 | 1,098.7 | +0.00 % | ±5 % | not judged (numerically inside) |
| take-off weight, Anderson first estimate (empty fraction 0.62) (lb) | partly independent | 3,517.3 | 7,557.8 | +114.88 % | ±10 % | **outside** (G-2, B-9e: explained) |
| take-off weight, Anderson build-up (8.83) (lb) | coding check | 3,517.3 | 4,035.8 | +14.74 % | none (cross-check) | not judged |
| zero-lift drag coefficient, mission altitude, clean | independent | 0.02208 | 0.01892 | -14.32 % | ±10 % | **outside** (G-3, B-5, B-9e: explained) |
| propeller efficiency, climb (sea level, full power) | coding check | 0.7041 | 0.7041 | +3.346e-13 | ±0.05 | within |
| propeller efficiency, cruise (outbound leg) | coding check | 0.8073 | 0.8073 | -5.54e-14 | ±0.05 | within |
| propeller efficiency, loiter | coding check | 0.7733 | 0.7733 | -9.437e-14 | ±0.05 | within |
| best-range speed, mission altitude (kt) | coding check | 103.6 | 103.6 | +0.00 % | ±3 % | within |
| best-endurance speed, mission altitude (kt) | coding check | 78.74 | 78.74 | +0.00 % | ±3 % | within |
| sea-level rate of climb at W0, Anderson closed form (ft/min) | coding check | 2,325.8 | 1,915.2 | -17.66 % | none (cross-check) | not judged |
| sea-level rate of climb at W0, excess power at Stage 1's speed (ft/min) | coding check | 2,325.8 | 2,325.8 | +0.00 % | ±3 % | within |
| best-climb speed, sea level (kt) | coding check | 93.55 | 58.47 | -37.49 % | none (cross-check) | not judged |
| service ceiling (100 ft/min) at W0 (ft) | coding check | 31,738.2 | 29,954.9 | -1,783 ft | ±1,000 ft | not judged (numerically outside; B-9c) |
| take-off distance over 50 ft, sea level (ft) | partly independent | 711 | 719 | +1.14 % | ±15 % | within |
| landing distance over 50 ft, sea level (ft) | partly independent | 1,348.6 | 1,354.3 | +0.42 % | ±15 % | within |
| corner speed V*, sea level, EAS (kt) | coding check | 104 | 104 | +0.00 % | ±5 % | within |
| gust load factors (V_C and V_D points) | independent | 3.504 | - | - | ±5 % | **not computed** (G-5, B-6) |

- The closed-form climb rows carry the class "coding check" in the record but are not judged: the closed
  form assumes power available independent of speed, which the disk does not give (review S3A-4).
- The record's `mission` loiter is the sized 11.00 h and the 1,098.7 lb is the fuel for it. The row label
  now says so (review W-6, fixed in the regenerated report).

### 4.3 Engine rows

Source: `docs/validation/2026-11-27_task12_stage3_engine_m250_ws13a8.md`, generated from `engine.json` in
the same record folder (commit `abb1e03`, `uncommitted_code_changes: false`). The report gives no class
column; the class below is its own wording (its section 1 and spec 7.1b).

| Quantity | Class | Stage 1 / brochure | App. K family (min - max) | Difference | Tolerance | Verdict |
|---|---|---|---|---|---|---|
| shaft hp available at 20,000 ft, 95 kt (hp) | not judged (same table) | 196.713 | 196.549 - 196.755 | -0.1 to +0.0 % | ±10 % | not judged; numerically inside |
| shaft hp available at 25,000 ft, 95 kt (hp) | not judged (same table) | 156.037 | 155.899 - 156.074 | -0.1 to +0.0 % | ±10 % | not judged; numerically inside |
| shaft SFC over cruise_out, leg average (lb/(hp h)) | not judged (same table) | 0.687 | 0.671 - 0.679 | -2.4 to -1.2 % | ±10 % | not judged; numerically inside |
| shaft SFC over loiter, leg average (lb/(hp h)) | not judged (same table) | 0.856 | 0.829 - 0.857 | -3.3 to +0.1 % | ±10 % | not judged; numerically inside |
| shaft SFC over cruise_back, leg average (lb/(hp h)) | not judged (same table) | 0.763 | 0.742 - 0.759 | -2.7 to -0.5 % | ±10 % | not judged; numerically inside |
| service ceiling (App. K power, pi_c held) (ft) | not judged (same table) | 31,738.180 | 30,407.137 - 30,432.458 | -1,331 to -1,306 ft | ±1,000 ft | not judged; **numerically outside** (B-9c) |
| shaft SFC at normal_cruise (380 shp, sea level static) | independent, cannot fail (G-6) | 0.635 | 0.642 - 0.644 | +1.0 to +1.5 % | ±10 % | within |
| shaft SFC at cruise_a_90pct (377 shp, sea level static) | independent, cannot fail (G-6) | 0.637 | 0.643 - 0.646 | +1.0 to +1.4 % | ±10 % | within |
| shaft SFC at cruise_b_75pct (314 shp, sea level static) | independent, cannot fail (G-6) | 0.673 | 0.678 - 0.685 | +0.7 to +1.7 % | ±10 % | within |

Stage 1's leg SFC carries the 1.02 allowance; the family is raw App. K without it. A constant SFC of 0.613
would also pass the three brochure rows (-3.5 %, -3.8 %, -8.9 %), so they cannot tell engine models apart.

Model check of the cycle code against Mattingly's own figures (spec 7.1b item 1), same source file,
section 5. Tolerances were fixed on 2026-11-21. These rows test the cycle code against the book and do
not depend on the aircraft.

| Group | Rows | Result |
|---|---|---|
| Fig. K.4 tau_t* at pi_c 5, 10, 20, 35 | 4 | all within ±0.015 (-0.001 to -0.008) |
| Fig. K.2 F/m0 at pi_c 5, 17 | 2 | +3.6 %, +3.0 %, within ±5 % |
| Fig. K.3 S at pi_c 5 | 1 | -4.6 %, within ±5 % |
| Fig. K.3 S at pi_c 17 and 35 | 2 | -5.7 %, -5.6 %, **outside** ±5 % (B-5, B-9e: explained and carried) |
| Fig. K.7 F/F_SL at 5,000 to 30,000 ft | 6 | all within ±0.015 (-0.001 to +0.006) |
| Fig. K.9 minimum S at M0 0.3, 0.5, 0.8 | 3 | -8.6 %, -7.9 %, -6.8 %, within ±10 % |

16 of 18 rows within. On fuel consumption the model reads low against the book in every row (-8.6 to
-4.6 %).

**Validity (spec 7.1b item 2; review W-7).** Same source file, section 4.

- **77.4 %** of the mission fuel is burned in table cells where App. K's choked-turbine assumption fails
  (record `unchoked_fuel_share`). On the superseded design it was 71.8 %.
- The whole loiter (645.7 lb) and the whole return cruise (147.3 of 147.3 lb) are in unchoked cells.
- The table is validated at sea level, static, 70 to 100 % power only. The mission legs run at 13 to
  27 % of the rating at 20,000 ft. The loiter runs at 77.8 shp falling to 59.2 shp.
- The leg-mean loiter SFC is 0.856 (0.825 on the superseded design). A larger wing flies slower on less
  power, where the model's SFC is highest and least supported.
- Nothing new is wrong. The ±10 % SFC band stands in for data and is doing more work (G-6, B-5).

### 4.4 Aerodynamic rows

Source: `docs/validation/2026-11-27_task12_stage3_aero_m250_ws13a8.md`, generated from `aero.json` in the
same record folder (commit `1cfa964`; the record carries no dirty-tree flag).

| Quantity | Class | Stage 1 / Raymer | Measured | Difference | Tolerance | Verdict |
|---|---|---|---|---|---|---|
| wing lift slope, per rad (bare planform, inviscid, M 0) | independent | 4.906 | 4.749 | -3.2 % | ±5 % | within |
| span efficiency e | independent | 0.811 | 0.990 | +0.179 | ±0.05 | not judged (not comparable as specified) |
| downwash gradient at the tail (z = 1.43 ft) | coding check | 0.451 | 0.452 | +0.001 | none | not judged (same model, 7.1c item 3) |
| static margin, full fuel, MAC | coding check | 0.113 | 0.112 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76)-(8.78) with lattice downwash, full fuel | coding check | 0.113 | 0.112 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76) as printed (no downwash), full fuel | partly independent | 0.113 | 0.367 | +0.254 | ±0.03 | not judged (book's simplification); numerically outside |
| static margin, empty fuel, MAC | coding check | 0.087 | 0.087 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76)-(8.78) with lattice downwash, empty fuel | coding check | 0.087 | 0.087 | -0.000 | ±0.03 | not judged (same model); numerically inside |
| static margin by Anderson (8.76) as printed (no downwash), empty fuel | partly independent | 0.087 | 0.342 | +0.254 | ±0.03 | not judged (book's simplification); numerically outside |

The downwash row: Stage 1's value is 0.451 and the Stage 3 fine-lattice value is 0.452 (0.4518 in the
rotation report). Each is quoted as what it is (review GB-1e).

### 4.5 Rotation with ground effect

Source: `docs/validation/2026-11-27_task12_stage3_rotation_m250_ws13a8.md`, generated from `rotation.json`
and `ground_effect_validation.json` in the same record folder (commit `1cfa964`; no dirty-tree flag in
either). The row has no 7.1a tolerance and the record gives it no class. Everything but the ground-effect
lift factor is Stage 1's layout.

| Quantity | Stage 1 | With ground effect | Difference | Limit | Limit met |
|---|---|---|---|---|---|
| rotation tail CL needed (0.8 V_TO, forward CG, sea level) | -0.968 | -0.930 | +0.038 (-3.9 %) | abs <= 1.00 | yes / yes |

- The margin without ground effect is 0.032 (1.00 less 0.968). It is thin. The tail is large: 135.48 ft^2
  against a wing of 270.56 ft^2, at volume scale 1.59.
- Validation of the ground-effect lattice (induced-drag ratio, tolerance ±15 %, fixed in advance): inside
  Raymer (12.61) at 4 of 4 h/b values, inside Anderson (6.77) at 1 of 4 (-38.1 %, -25.0 %, -16.8 % at
  h/b 0.1, 0.2, 0.3). The two books differ by 29 % at h/b 0.1.
- The limit is met with and without ground effect, so the validation does not decide the row (G-7).

### 4.6 Rows outside tolerance, and the rulings that carry them

Rows outside tolerance are reported, not tuned. Diagnoses are the generated ones of the perf, engine and
aero reports.

| Row | Size | Diagnosis | Carried by |
|---|---|---|---|
| Installed power for take-off (Mattingly against Raymer) | -11.62 % against ±5 % | Two models of the climb-out after lift-off, where both are near zero climb gradient and the distance is most sensitive to power. k_TO does not explain it (132.7, 136.7, 142.6 hp at k_TO 1.15, 1.2, 1.25). At Mattingly's 136.7 hp Raymer's route gives 4,758 ft, of which 3,809 ft is the climb segment. The row says nothing about the installed power: the rating, 450 hp, is far above both | **B-5**: explained and carried; the row is replaced in spec 7.1a by the take-off distance at installed power (711 against 719 ft, +1.14 %, within ±15 %). **B-9e**: stands at -11.6 % |
| Take-off weight, Anderson first estimate | +114.88 % against ±10 % | His empty fraction 0.62 is a historical value for crewed aircraft. The denominator 1 - 0.3138 - 0.62 is small. Three values side by side: 0.62 gives 7,558 lb; Stage 1's fraction 0.5455 gives 3,554 lb (+1.0 %); Anderson's build-up (8.83) gives 4,036 lb (+14.7 %, not judged). Anderson's fuel fraction is 0.3138 against Stage 1's 0.3124, so the difference is the empty fraction | **G-2**: explained, not failed. **B-9e**: stands at +114.9 % |
| Zero-lift drag | -14.32 % against ±10 % | Anderson's Cfe 0.0043 gives 0.01892 against Stage 1's 0.02208. The Cfe that reproduces Stage 1 is 0.005019. The method resolves CD0 to about ±20 % and has no place for sponsons, sensor, engine and leakage terms. Stage 1 is the higher, conservative value. On the superseded design the row was -18.63 % | **G-3** fixed the coefficient; **B-5**: explained and carried; **B-9e**: stands at -14.3 % |
| Fig. K.3 S at pi_c 17 and 35 (cycle model against the book) | -5.7 %, -5.6 % against ±5 % | None recorded. The model reads low on fuel consumption in all six S rows. No run translates the low reading into fuel for this design | **B-5**: the ±10 % SFC band covers K.3 as well as the engine model. **B-9e**: stands |
| Service ceiling, closed form (perf) | -1,783 ft against ±1,000 ft; not judged | Stage 1's ceiling is above the engine table's top altitude and leans on the clamp (section 4.7) | **B-9c** |
| Service ceiling, App. K power (engine) | -1,331 to -1,306 ft against ±1,000 ft; not judged | The same: "the difference here is the table's edge, not the family's spread" (engine report) | **B-9c** |
| Sea-level rate of climb, closed form | -17.66 % (no tolerance) | (5.121) assumes power available independent of speed; the disk's efficiency rises with speed (0.5567 at 58.5 kt, 0.7047 at 93.5 kt). Bracket 1,915 to 2,540 ft/min; Stage 1's 2,326 lies inside | not judged; the excess-power row (0.00 %) is the coding check |
| Best-climb speed | -37.49 % (no tolerance) | Same cause: the closed form returns the minimum-power speed 58.5 kt; with the disk the best climb moves to 93.5 kt (1.75 V_stall), an interior maximum | not judged |
| Take-off weight, Anderson build-up | +14.74 % (no tolerance) | Raymer's own Table 15.2 approximate method, so not independent. On the superseded design the row was +9.12 % | not judged. **B-9g**: the gap is a named preliminary-design risk |
| Span efficiency | +0.179 against ±0.05 | The lattice gives the inviscid planform value; Raymer's (12.49) is a whole-aircraft fit with separation drag. The spec asked for the inviscid share of (12.49), which Raymer does not give | not judged (not comparable as specified) |
| Static margin by Anderson (8.76) as printed | +0.254 against ±0.03 | The printed relation leaves out downwash and tail efficiency | not judged (book's simplification) |
| Ground-effect lattice against Anderson (6.77) | -38.1 %, -25.0 %, -16.8 % against ±15 % | The two books differ by 29 % at h/b 0.1; the lattice is inside Raymer (12.61) at every h/b | **G-7**: does not decide the rotation row |
| VSPAERO full-fuel margin at L2, 0.1538 | 0.004 above the R13 band | No fuselage in the model, so expected to read high. The mesh spread L1 to L2 is 0.009 MAC, larger than the excess; L1 (0.1448) is inside the band | support only (G-8). **B-9f**: B-6 covers it |

By 7.1a a row outside tolerance sends the design back to Stage 1 if it moves a requirement margin below
zero. No record shows that for any row above: the take-off power row is not about installed power, the
CD0 row is in the favourable direction, the first-estimate weight is ruled explained, and every ceiling
value meets R12 (section 4.7).

**The empty-weight cross-check has moved** (B-9g). The record's `empty_fraction_comparison` reads 0.5455
for the build-up, 0.5156 for Table 3.1 with the composite factor, 0.4952 for Table 6.2 and 0.6220 for
Table 15.2. The metal build-up is 0.5863. At the joint worst end of the two new bands the fraction is
0.5863 x 1.05 = 0.616 (arithmetic), close to the Table 15.2 level. So the bands at h = 1 reach about as
far as that cross-check, and no further.

### 4.7 The service ceiling and ruling B-9c

Three recorded values, and why they differ:

| Value | Ceiling (ft) | Margin to 23,500 ft (ft) | Source |
|---|---|---|---|
| Stage 1 (design record) | 31,738.2 | 8,238 | `design_pusher.json`; compliance row 14 |
| App. K cycle power, Stage 1's own bisection (family min to max) - **the value to quote (B-9c)** | 30,407.1 to 30,432.5 | 6,907 on the lower | engine report |
| Closed form (5.121), efficiency at its own speed (lower bound; the perf row's value) | 29,954.9 | 6,455 | perf report |
| Closed form, efficiency at Stage 1's speed (upper bound) | 32,473 | - | perf report, `climb_bracket` |

- **Cause.** The engine table ends at 30,000 ft and the lookup holds its power constant above it. Stage
  1's ceiling (31,738 ft) is above the top and leans on that clamp. The cycle's own power keeps falling;
  the engine row repeats Stage 1's bisection with it and gets 30,407 to 30,432 ft, which is 1,306 to
  1,331 ft lower. On the superseded design, whose ceiling (29,746.6 ft) was below the table top, the same
  row differed by -31 to +2 ft (2026-11-26 report).
- The closed-form row's own value, 29,955 ft, is below 30,000 ft and does not use the clamp. Its bracket
  is 29,955 to 32,473 ft, 2,518 ft wide (arithmetic); Stage 1's value lies inside.
- **Caveat on the quoted value.** The 30,407 to 30,432 ft still rests on a cycle model with no altitude
  data behind it, and on the assumption R-f for the engine's operating altitude.
- **R12 is met by every value**, by at least 6,455 ft. The power row at 23,000 ft (281.1 hp needed
  against 450) is evaluated inside the table.
- **Ruling B-9c.** Quote the cycle value with the caveat; flag table reads above 30,000 ft; extending the
  table to 35,000 ft is a preliminary-design entry item. The flag is in the code since commit `5bb3f81`
  (`service_ceiling_above_table_top` in `conceptual/uav.py`). The baseline record was made before it and
  does not store the flag; the perf and compliance reports state the caveat in their text.

### 4.8 Rows of spec 7.1 with no measurement

| Spec 7.1 row | Status | Source |
|---|---|---|
| Section polars and C_L,max at the design Reynolds number (SU2) | not run (G-5 waived; B-6: preliminary-design entry item) | perf and aero reports |
| Propeller efficiency by blade element | no code (G-5 waived; B-6) | perf report |
| Gust load factors, second source | not computed: Anderson ch. 6 has no gust relation (G-5 waived; B-6) | perf report |
| Drag due to lift | no judged row: the span-efficiency row is not comparable as specified | aero report |
| Range and endurance | no row of their own in 7.1a; covered by the mission-fuel row (a coding check) | perf report |
| Trim | no Stage 3 row; Stage 1's flag `trim_ok` is true | compliance row 29 |

## 5. Stability, V-n and the take-off sweep

### 5.1 Stability: R13 and ruling B-6

Sources: the aero report (section 4.4) and `docs/validation/2026-11-27_task12_vspaero_m250_ws13a8.md`,
from `runs/task12/openvsp/2026-11-27_m250_ws13a8_vspaero/results.json` (commit `2964a2b`, clean tree;
OpenVSP 3.57.1, VSPAERO v.7.2.2).

**What holds the static margin.**

- The layout code places the wing so that the full and empty margins are centred in the band (their sum
  is 0.200). The margins 0.1126 and 0.0874 are therefore not measured margins above the 5 % floor.
- What is physical is the CG travel, 0.025 MAC, and the accuracy of the neutral point.
- The empty-fuel margin changes by -0.054 MAC per 0.1 of downwash gradient and reaches the floor at a
  gradient of 0.521 (lattice at the nominal tail height: 0.451). Over the band of tail heights the
  margins run 0.080 to 0.133.
- The static-margin rows use the same lattice downwash as Stage 1, so they are not independent (7.1c
  item 3). Anderson's (8.76)-(8.78) with the same downwash is algebraically Raymer's (16.9).

**VSPAERO, wing and tails only (support, rulings G-8 and B-6).** The model has no fuselage. The
fuselage's destabilising moment is missing, so the margin is expected to read high. It is not a
fuselage-inclusive neutral point and has no 7.1a verdict.

| Quantity | VSPAERO L1 | VSPAERO L2 | Stage 1 record | VSPAERO minus record (L1 / L2) |
|---|---|---|---|---|
| CL_alpha, aircraft, per rad | 6.097 | 6.000 | 6.225 | -2.1 / -3.6 % |
| Neutral point, ft from nose | 12.820 | 12.876 | 12.624 (12.723 without the fuselage term) | +0.196 / +0.252 ft |
| Static margin, full fuel, MAC | 0.1448 | 0.1538 | 0.1126 | +0.0322 / +0.0412 |
| Static margin, empty, MAC | 0.1197 | 0.1287 | 0.0874 | +0.0323 / +0.0413 |

- Mesh spread of the neutral point from L1 to L2: 0.056 ft, 0.009 MAC. A mesh finer than L2 was not run.
  Induced drag is not converged on these meshes and no drag conclusion is drawn from the run.
- **L1 is inside the R13 band. L2 is 0.004 above its upper end.** The excess is on the over-stable side,
  smaller than the mesh spread, and from a model without a fuselage. Ruling B-9f: B-6 covers it.
- The risk R13 guards is the 5 % floor at empty fuel. VSPAERO puts the empty margin at 0.120 to 0.129 and
  the neutral point 0.20 to 0.25 ft aft of Stage 1's, never ahead of it. That supports the floor. It does
  not prove it: the fuselage term moves the neutral point forward, and Stage 1's own equation prices it
  at 0.099 ft (12.723 less 12.624).
- After the fuselage term is removed from Stage 1's own equation, +0.097 / +0.152 ft of the offset
  remains. The report does not decompose the remainder.
- This run is closer to Stage 1 than the one B-6 accepted: the superseded design read 0.159 and 0.167 at
  full fuel (+0.043 / +0.051 over Stage 1; 2026-11-26 report).

**Ruling B-6.** R13 is accepted by layout construction with the G-8 VSPAERO run as support. **There is
no independent fuselage-inclusive neutral point.** It is a named entry item for preliminary design.
Static margin, trim drag, downwash and tail height are not in the info-gap horizon.

### 5.2 V-n check: rulings B-4 and B-9d

Source: `docs/validation/2026-11-27_task12_vn_check_ws13a8.md`, from
`runs/task12/stage3/2026-11-27/vn_check_ws13a8/vn.json` (commit `897b5e9`, clean tree). Stage 1's own
loads code (`conceptual/raymer_loads.py`), the design rebuilt from its record, not re-sized. The check
reproduces the record's `vn` and `gusts` entries to 1.2e-07. This is not a second source for the gust
loads; that row is waived (G-5).

**Speeds and limits.**

- V_C 110.0 kt EAS, V_D 165.0 kt EAS (1.5 V_C), corner speed 104.0 kt EAS.
- Level top speed: 185.2 kt EAS at sea level, 120.9 kt EAS at 20,000 ft.
- Limits: positive 3.8; negative -1.8 with a 0.1 g margin, so the negative gust must stay at or above
  -1.7 (B-3).
- Weights: take-off 3,517.3 lb and zero-fuel 2,418.6 lb. The zero-fuel weight includes the 500 lb payload.
- Gust rule (Raymer p. 339): U_de 30 ft/s up to V_C, falling to 15 ft/s at V_D, 15 ft/s above.

**Load factors.** The last two columns are a sensitivity, not the rule: U_de held at 30 ft/s at every
speed.

| Altitude | Speed | V EAS (kt) | U_de (ft/s) | Weight | n gust + | n gust - | exceeds | n gust + (U_de 30) | n gust - (U_de 30) |
|---|---|---|---|---|---|---|---|---|---|
| sea level | V_C | 110.0 | 30.0 | take-off | 2.577 | -0.577 | no | 2.577 | -0.577 |
| sea level | V_C | 110.0 | 30.0 | zero fuel | 2.991 | -0.991 | no | 2.991 | -0.991 |
| sea level | V_D | 165.0 | 15.0 | take-off | 2.194 | -0.194 | no | 3.388 | -1.388 |
| sea level | V_D | 165.0 | 15.0 | zero fuel | 2.505 | -0.505 | no | 4.011 | -2.011 |
| sea level | level top speed | 185.2 | 15.0 | take-off | 2.346 | -0.346 | no | 3.692 | -1.692 |
| sea level | level top speed | 185.2 | 15.0 | zero fuel | 2.696 | -0.696 | no | 4.393 | -2.393 |
| 20,000 ft | V_C | 110.0 | 30.0 | take-off | 2.888 | -0.888 | no | 2.888 | -0.888 |
| **20,000 ft** | **V_C** | 110.0 | 30.0 | **zero fuel** | **3.504** | **-1.504** | no | 3.504 | -1.504 |
| 20,000 ft | V_D | 165.0 | 15.0 | take-off | 2.452 | -0.452 | no | 3.904 | -1.904 |
| 20,000 ft | V_D | 165.0 | 15.0 | zero fuel | 2.920 | -0.920 | no | 4.841 | -2.841 |
| 20,000 ft | level top speed | 120.9 | 27.0 | take-off | 2.877 | -0.877 | no | 3.084 | -1.084 |
| 20,000 ft | level top speed | 120.9 | 27.0 | zero fuel | 3.488 | -1.488 | no | 3.761 | -1.761 |

The manoeuvre load factor is capped at the structural limit 3.8 at every point (the aerodynamic limit is
above 3.8 at all twelve; 4.254 at V_C at take-off weight is the lowest).

**Result under the rule: no point exceeds a limit.** The governing point is V_C at 20,000 ft at zero-fuel
weight: +3.504 / -1.504.

| Margin | Superseded design (2026-11-26 report) | This baseline |
|---|---|---|
| Largest positive gust | 3.239 | 3.504 |
| Positive margin to 3.8 | 0.561 | 0.296 |
| Negative margin to -1.7 | 0.461 | 0.196 |

The margins roughly halved although V_C dropped by 5 kt. W/S fell from 16 to 13 and the aspect ratio rose
from 7 to 8.

**The sensitivity (not the rule, not a failure).** With the gust held at 30 ft/s at every speed, five
points pass a limit:

| Point | Positive / negative | Against the limits |
|---|---|---|
| Sea level, V_D, zero fuel | 4.011 / -2.011 | passes both |
| Sea level, level top speed, zero fuel | 4.393 / -2.393 | passes both |
| 20,000 ft, V_D, take-off weight | 3.904 / -1.904 | passes both |
| 20,000 ft, V_D, zero fuel | 4.841 / -2.841 | passes both |
| 20,000 ft, level top speed, zero fuel | 3.761 / -1.761 | positive inside 3.8 by 0.039; negative past -1.7 and inside -1.8 |

What the owner was told and ruled on (review W-5, ruling B-9d):

- Three points passed a limit in this sensitivity on the superseded design; five do now, at lower speeds.
- The largest value is +4.841 / -2.841. The positive side is below the ultimate 5.7 (record
  `Nz_ultimate`). The record carries no negative ultimate; 1.5 x -1.8 = -2.7 (arithmetic), and -2.841 is
  past it.
- **Level flight at 20,000 ft reaches the edge.** The level top speed there is 120.9 kt EAS, 10.9 kt
  above V_C. No dive is needed, only full power. Under the rule the point is 3.488 with 27.0 ft/s, inside.
- **At sea level the level top speed is 185.2 kt EAS**, 20.2 kt above V_D and 75.2 kt above V_C. The
  structure is not cleared to it.
- The ledger bands the gust speed 30 to 50 ft/s. The info-gap study moves it to 50 ft/s at the worst
  points and pays for it in structure weight (10.403 h alone, section 3.4). The built nominal structure
  does not carry it.

**Rulings.** B-4: the per-design V_C rule is confirmed; envelope protection is a preliminary-design
requirement. **B-9d: B-4 is confirmed at the new margins (0.296 g positive, 0.196 g negative). V_C
110 kt and the gust rule stand. The preliminary-design envelope-protection item covers level flight at
every altitude and a gust criterion above V_C.** R18 holds only if the autopilot holds the aircraft at
or below V_C.

Not checked: a negative manoeuvre load (the record has no negative C_L,max); the gust at a weight below
zero-fuel weight with the payload off; a second gust source (G-5).

### 5.3 Take-off against the propeller factor f (rulings G-9 and B-9b)

Source: `docs/validation/2026-11-27_task12_takeoff_f_sweep_ws13a8.md`, from
`runs/task12/stage3/2026-11-27/takeoff_f_sweep_ws13a8/sweep.json` (commit `0807120`, clean tree). **This
sweep has now been run on the baseline** (review W-2 closed). Not a re-size: weight (3,517.3 lb), wing,
drag, C_L,max, engine power (450 hp) and propeller diameter (6.91 ft) are held; only f changes. At
f = 0.85 the sweep gives the record's distances.

| f | Static thrust (lb) | Thrust at 0.707 V_TO (lb) | Ground roll (ft) | Take-off over 50 ft (ft) | Margin to 2,500 ft (ft) | Landing over 50 ft (ft) |
|---|---|---|---|---|---|---|
| 0.60 | 1,572 | 1,247 | 374 | 855 | 1,645 | 1,349 |
| 0.65 | 1,659 | 1,324 | 348 | 811 | 1,689 | 1,349 |
| 0.70 | 1,743 | 1,400 | 327 | 776 | 1,724 | 1,349 |
| 0.75 | 1,825 | 1,474 | 308 | 749 | 1,751 | 1,349 |
| 0.80 | 1,906 | 1,546 | 292 | 728 | 1,772 | 1,349 |
| 0.85 | 1,984 | 1,617 | 277 | 711 | 1,789 | 1,349 |
| 0.90 | 2,061 | 1,687 | 264 | 698 | 1,802 | 1,349 |

- **R7 take-off is met at every f from 0.60 to 0.90** at nominal values of everything else. The worst
  case, f = 0.60, gives 855 ft, a margin of 1,645 ft. Landing does not depend on f.
- **f at static and take-off conditions is a judgement beyond App. L**, which speaks of efficiency in
  flight. The book gives no static number. The sweep range is wider than the ledger band (0.80 to 0.90)
  on purpose.
- The sweep does not combine a low f with the other worst-case quantities. The info-gap study does that
  inside the band only: 1,584.6 ft at h = 1 with f at 0.80, and the R7 horizon 1.2845 (section 3).
- Limits: sea level ISA at the record's weight only. Static C_T/C_P was not varied (it is inert under
  App. L). Which thrust term sets the thrust at each f was not recorded.

## 6. Against the Gate B pass criterion (7.4)

Spec 7.4: "Pass when every requirement is met by the independent measurement with its margin, every row
is inside tolerance or explained, and the robustness horizon at the requirements is at least the value
fixed at Gate A." The three parts are taken in turn. This section does not decide the gate.

### 6.1 Every requirement met by the independent measurement with its margin

Ruling B-1: the declared evidence classes stand in for "independent measurement" for every requirement.
Section 2 gives the class of each. In summary:

| Requirement | Met on the record? | Class that stands in (B-1) |
|---|---|---|
| R1, R2, R3, R4, R8, R10, R11, R14, R15, R17, R19; R6 altitude | by construction or process | nothing to measure |
| R5, 8 h nominal | yes, 11.000 h | coding check; SFC rests on the engine model (G-6) |
| R5, 3.5 h at h = 1 | yes, horizon 1.0501 | info-gap search on the Stage 1 model |
| R6 engine operability | not checked | assumption (R-f) |
| R7 take-off and landing distance | yes | partly independent; unfactored (G-1); no independent check of take-off thrust (sweep, G-9) |
| R7 stall 70 kt | yes, 53.33 kt | assumption (ledger C_L,max); SU2 row waived (G-5, B-6) |
| R9 | yes | waiver: Stage 1 only (G-5, B-6); V-n check with the same code (B-4, B-9d) |
| R12 climb | yes | coding check; closed form does not apply with the disk |
| R12 ceiling | yes, on every value | coding check, not judged (7.1b); ruling B-9c |
| R13 | yes, by construction | layout construction; VSPAERO without fuselage as support (B-6, B-9f) |
| R16 | yes | coding check |
| R18 | yes, by construction | per-design rule (B-4); depends on envelope protection (B-9d) |

**As written, no requirement that needs a measurement is met by a fully independent one.** With B-1, each
has a declared class, and none has a recorded value on the wrong side of its limit.

### 6.2 Every row inside tolerance or explained

| Group | Rows |
|---|---|
| Inside tolerance (judged) | perf: 12 rows; engine: 3 brochure rows; aero: lift slope; cycle model: 16 of 18 |
| Outside, explained by owner ruling | Anderson first-estimate W0 (G-2, B-9e); take-off power (B-5, B-9e); CD0 (G-3, B-5, B-9e); Fig. K.3 S at pi_c 17 and 35 (B-5, B-9e) |
| Outside without a ruling | none |
| Not judged, numerically outside, carried by a ruling | service ceiling, perf and engine rows (B-9c); Anderson build-up W0 (B-9g) |
| Not judged, numerically outside or without tolerance, no ruling needed | closed-form rate of climb and best-climb speed; span efficiency; Anderson (8.76) as printed |
| Not judged, numerically inside | engine power and SFC rows (7.1b); ceiling power; mission fuel; downwash and static-margin rows (7.1c) |
| Not computed or not run | gust load factors; SU2 polars and C_L,max; blade-element propeller (all G-5 waived; B-6 entry items) |
| Outside its own validation, does not decide a row | ground-effect lattice against Anderson (G-7) |
| Support only, 0.004 above the band at L2 | VSPAERO full-fuel margin (G-8, B-6, B-9f) |

**On the rulings, every outside row is explained.** The "outside without a ruling" group of the
2026-11-26 report is empty. Three rows of spec 7.1 still have no measurement, by waiver.

### 6.3 Robustness horizon at least 1 at R7 and at R5's robust endurance

| Requirement | Horizon | Threshold | On the record |
|---|---|---|---|
| R5, 3.5 h on station | 1.0501 | 1 | met |
| R7, field length (take-off binds) | 1.2845 | 1 | met |

**Met on the record**, with these limits stated:

- Each horizon is a search on the Stage 1 model, not a proof. The exclusions of section 3.6 apply.
- The take-off horizon rests on f at low speed (judgement). R7 is unfactored (G-1).
- The R5 horizon is 1.05 by construction of the sizing, so the margin over 1 is the one that was asked
  for and no more.
- Both new bands are judgements (B-2a). The ±5 % empty-weight band stands (B-9g); the gap to Anderson's
  build-up and to Table 15.2 is a named risk, not a banded quantity.

### 6.4 Summary, criterion by criterion

| Part of 7.4 | Status |
|---|---|
| Every requirement met by the independent measurement | every requirement is met on the record or by construction, except R6 engine operability (assumption, not checked). Not independent as written; **B-1 accepts the declared classes** |
| Every row inside tolerance or explained | **every outside row is carried by a ruling** (G-2, G-3, B-5, B-9c, B-9e, B-9f, B-9g); three rows of 7.1 not measured (G-5 waiver, B-6) |
| Robustness horizon at least 1 | **met on the record** (1.0501 and 1.2845) |

**What stood between the records and a pass in the review of 2026-11-27, and where each stands:**

| Review item | Status now |
|---|---|
| W-1: the performance report described the superseded design | this report |
| W-2: take-off sweep over f not run on the baseline | run (section 5.3); R7 met at every f from 0.60 to 0.90 |
| W-3: no Stage 1 package; A9 and A11 not testable | ruled (B-9a): record, compliance table and Gate A re-check accepted; A9 and A11 inherited; the package is a preliminary-design entry item |

No record in the repository shows a remaining blocker. The pass itself is the owner's decision.

## 7. Rulings this report depends on (GB-4)

All in `docs/specs/00_decisions.md` section 9 unless another place is named.

| Ruling | What it decides here |
|---|---|
| R-a | the pusher is sized around the M250-B17F (450 shp, 212 lb) |
| R-b | SFC allowance 1.02; propeller rpm 2,030 |
| R-c | SFC ±10 % and power ±10 %, the power band as a cap |
| R-d | the baseline is the robust design at h_T 1.05 |
| R-e | the power cap is clipped at the rated power |
| R-f | engine maximum operating altitude and relight envelope are design assumptions (R6) |
| Baseline cell (2026-11-24) | W/S 16, A 7 over W/S 18, A 7. **Superseded by B-2c** |
| G-1 | R7 is the computed distance over 50 ft, unfactored |
| G-2 | Anderson's first estimate with the 0.62 fraction counts as explained |
| G-3 | CD0 row uses Cfe 0.0043; the row cannot confirm Stage 1's CD0 to ±10 % |
| G-4 | Stage 1 uses the App. L efficiency per flight condition |
| G-5 | waived before Gate B: SU2 polars and C_L,max, gust second source, blade-element propeller |
| G-6 | engine closing row "rests on the model", carried by the ±10 % SFC band |
| G-7 | Raymer (12.61) added to the ground-effect validation; it does not decide the rotation row |
| G-8 | VSPAERO wing-and-tail neutral point quoted without the fuselage |
| G-9 | recorded take-off sweep over f quoted next to R7 |
| Edits A and B (2026-11-26) | the transit-cliff score uses the record's propeller; the TP100 ledger pins the flat propeller |
| Per-design V_C rule (2026-11-23; spec R18, ledger source text) | V_C 10 % above the fastest cruise sub-step, rounded up to 5 kt, at least 110 kt EAS |
| R5 restatement; headwind and Oswald exclusions (2026-11-22; spec R5, `info_gap.json` `exclusions`) | 8 h nominal and 3.5 h at h = 1; headwind and e outside the horizon |
| Gate A margins (round 4; ledger) | ceiling +500 ft, negative gust 0.1 g, power margin 0 |
| Spec 7.1b and 7.1c rulings (2026-11-21) | engine-table rows and downwash rows are not independent and are not judged |
| B-1 | the declared evidence classes stand in for "independent measurement" |
| B-2, B-2a | composite band acts on the Table 15.4 savings; empty-weight band 0.95 to 1.05; re-size to h_T 1.05 |
| B-2b | full study on three cells before the choice |
| B-2c | W/S 13, A 8 is the baseline; the frozen design is superseded |
| B-3 | negative limit -1.8 with the 0.1 g margin |
| B-4 | per-design V_C rule confirmed; envelope protection is a preliminary-design requirement; one recorded V-n check |
| B-5 | take-off power, CD0 and Fig. K.3 are explained and carried; take-off power row replaced by the distance row |
| B-6 | R13 accepted by layout construction with the VSPAERO run as support; four named entry items |
| B-7 | Stage 1 compliance table generated; Gate A items A1 to A12 re-checked |
| B-8 | the nominal's small robustness is acknowledged; no new target (quotes 0.198; see section 8.4) |
| B-9a | record, compliance table and Gate A re-check accepted; A9 and A11 inherited; Stage 1 package is an entry item |
| B-9b | take-off sweep re-run on the baseline |
| B-9c | quote the cycle ceiling with the caveat; flag reads above the table top; table extension is an entry item |
| B-9d | B-4 confirmed at 0.296 g and 0.196 g; envelope protection covers level flight at every altitude and a gust criterion above V_C |
| B-9e | G-2 and B-5 stand at the new values (+114.9 %; -11.6 %, -14.3 %, -5.7 / -5.6 %) |
| B-9f | B-6 covers the VSPAERO L2 full-fuel margin 0.004 above the band |
| B-9g | the ±5 % empty-weight band stands; the gap to Anderson's build-up (+14.7 %) and to Table 15.2 is a named risk |

The Gate A re-check that spec 7.1c item 4 and B-7 ask for is section 5 of
`docs/reviews/2026-11-27_task12_gateB_ws13a8_review.md`. It is a review, not a generated record. Its
outcome: no item fails. A1, A3, A4, A5 and A12 pass. A8 passes on the reviewer's own run of the tests,
which is not a record. A2, A6, A7 and A10 pass on what the records can show, with one clause each that
only a package or a new row could show. A9 and A11 are inherited (B-9a).

## 8. Open items and waivers carried to preliminary design (GB-5)

### 8.1 Entry items named by a ruling

| # | Item | Ruling |
|---|---|---|
| 1 | SU2 section polars and C_L,max at the design Reynolds number. The 70 kt stall rests on the record's 1.35 | G-5, B-6 |
| 2 | Gust load factor from a second source | G-5, B-6 |
| 3 | Propeller efficiency by blade element. There is no independent propeller check, in flight, in climb or at take-off | G-5, B-6 |
| 4 | Fuselage-inclusive independent neutral point. R13 is met by layout construction only | B-6 |
| 5 | Stage 1 package for the W/S 13, A 8 sizes (three-view, weight statement, trades, carpet plot, V-n diagram, out-of-calibration list, risk list). A9 (concept scoring) and A11 (risk list) are inherited from the 2026-11-25 designs | B-9a |
| 6 | Extend the engine table to 35,000 ft. This changes `service_ceiling_ft` in the baseline record, so it is a re-record | B-9c |
| 7 | Envelope protection: the autopilot holds V_C in level flight at every altitude, and a gust criterion above V_C is set. Level top speed is above V_C at 20,000 ft and above V_D at sea level | B-4, B-9d |
| 8 | Empty weight: the gap to Anderson's build-up (+14.7 %) and to Table 15.2 (0.6220 against the build-up's 0.5455) is a named risk | B-9g |

### 8.2 Standing waivers and assumptions

| # | Item | Ruling |
|---|---|---|
| 9 | Engine maximum operating altitude and relight envelope are assumptions. The 23,000 ft ceiling requirement is above every certified B17 installation found (20,000 ft) | R-f |
| 10 | Engine closing check (maker's part-power curve, altitude rating): no data. The engine rows rest on the model | G-6 |
| 11 | **Engine table, unchoked share (W-7).** 77.4 % of the mission fuel burns in unchoked cells; the table is validated at sea level, 70 to 100 % power only; the legs run at 13 to 27 % of the rating; the cycle model reads 4.6 to 8.6 % low on fuel consumption against the book with 2 of 18 rows outside. The ±10 % SFC band stands in for data and for K.3 | G-6, B-5 |
| 12 | FAR field-length factors are not applied to R7 | G-1 |
| 13 | f = 0.85 at low speed and the band 0.80 to 0.90 are judgements. R7's binding horizon is the take-off one | G-4, G-9 |
| 14 | CD0: the method cannot confirm Stage 1 to ±10 %. No second route has been run | G-3, B-5 |

### 8.3 Open items from the reviews, no ruling of their own

| # | Item | Review |
|---|---|---|
| 15 | The disk model is favourable in cruise (0.807 on this design against the old flat 0.80). It has no tip-Mach or off-design loss, uses the full disk area, and has no hub, spinner or pusher-fuselage blockage | APL-7, APL-9 |
| 16 | One f is applied at every point, so the band cannot represent a propeller good in cruise and poor in climb. The ledger labelled `prop_real_to_ideal` `confidence: published` although the band is a judgement; relabelled `assumed` (B-10b, section 13) | APL-6, S3A-8 |
| 17 | Static C_T/C_P is inert under App. L (`static_ct_over_cp` is in `inert_variables`), not "not varied" | APL-4 |
| 18 | Climb speed at the worst endurance corner near the 20,000 ft stall: **not testable on this design**, because no decomposition was run on it (section 9, item 1) | S3A-1 |
| 19 | Anderson's 0.62 route holds the disk efficiencies at the record weight (0.7936 and 0.7530) while W0 iterates. It is not self-consistent with the disk | S3A-5 |
| 20 | The closed-form climb rows keep the class "coding check" in the record; their verdict is "not judged" | S3A-4 |
| 21 | Span efficiency is not comparable as specified; the ground-effect lattice is outside Anderson (6.77) at 3 of 4 h/b | S3A disclose list |
| 22 | The propeller fixed point returns without a flag if it does not converge | S3M-11(b) |
| 23 | Climb model: Stage 1's climb leg is a two-point estimate. Not re-examined on this design | 2026-11-26 report, item 9 |
| 24 | Coding checks are not verifications. Mission fuel, the power rows, the climb and the corner speed agree with Stage 1 because inputs and formula are shared | 2026-11-26 report, item 8 |
| 25 | Rotation margin is thin: tail CL 0.968 of 1.00 without ground effect (0.032), with a tail half the wing area | W review, 2e and A4 |
| 26 | Gust sensitivity: with the gust held at 30 ft/s the worst point (-2.841) is past 1.5 x -1.8 = -2.7 (arithmetic). No negative manoeuvre load is computed | W-5 |
| 27 | A2: the build-up empty fraction 0.5455 is 0.030 above the Table 3.1 composite fit 0.5156 (arithmetic). No report explains the difference for this design | W review, section 5 |
| 28 | A7: 58 of the 111 ledger entries have no band (19 requirements, 39 assumptions). The out-of-calibration list exists only in the 2026-11-25 package | W review, section 5 |
| 29 | A8: closed (B-10c). Recorded report at the gate commit: `runs/task12/stage3/2026-11-27/pytest_gate/` (section 13). The earlier last record was 336 passed, 1 xfailed (`runs/task12/stage1/2026-11-25/test_report.txt`) | W review, section 5 |
| 30 | A10: no row has ever checked the payload-bay volume. There is no Stage 1 three-view of this design; the OpenVSP model is the only drawing | W review, section 5 |
| 31 | Nose-wheel loads 0.1633 and 0.1515 are above the 0.08 to 0.15 optimum (inside the 5 to 20 % limits) | compliance report |
| 32 | Figure of the worst-case curve: closed (B-10c), `runs/task12/stage3/2026-11-27/robustness_figure_ws13a8/` (section 13) | GB-7 |
| 33 | Record hygiene. `aero.json`, `rotation.json` and `ground_effect_validation.json` carry a commit and no dirty-tree flag. The baseline's `info_gap.json` and `cell_result.json` have `git_dirty: true` with one untracked path, the run's own output folder. `runs/task12/openvsp/2026-11-27_m250_ws13a8/model.json` has `git_dirty: true` with no file list. The re-size record is as the baseline's | W-11 |
| 34 | Info-gap exclusions as listed in section 3.6 | - |

### 8.4 Points where a ruling text and the baseline differ

- **B-8** quotes the superseded design's nominal horizon, 0.198. The baseline's is 0.4135. B-9 restates
  B-4, G-2, B-5 and B-6 at the new values, and not B-8. The acknowledgement was made by reason ("what the
  restated R5 allows"), and the new value is larger. A one-line confirmation is for the owner.
- **Ledger label.** `prop_real_to_ideal` was `confidence: published` while its band is a judgement
  (item 16). Closed by B-10b: relabelled `assumed` (section 13).

## 9. Not run on this design

Nothing in this list has a record for W/S 13, A 8. Where a record exists for another design, that is
said.

**From the review of 2026-11-27 (its list, less the take-off sweep, which has now been run):**

1. **The App. L decomposition** (what the robust weight owes to the disk, climb leg by climb leg). The
   record `runs/task12/stage3/2026-11-26/appl_decomposition/` compares the flat and App. L baselines of
   the superseded cell. Section 5.4 of the 2026-11-26 report is therefore not carried over.
2. **A figure of the worst-case curve.** Now made (section 13). The table in section 3.2 is the record.
3. **A Stage 1 package** for these sizes: three-view, weight statement, trade tables (including the
   composite-factor trade, which the code can now run), carpet plot, V-n diagram, out-of-calibration
   list, risk list (B-9a: entry item).
4. **A rubber-engine design and a tractor design at these sizes.** The last recorded concept scoring is
   in the 2026-11-25 package, on other designs (B-9a: A9 inherited).
5. **SU2 section polars and C_L,max; the blade-element propeller; the gust second source** (G-5, B-6).
6. **A fuselage-inclusive neutral point** (B-6). The fuselage-plate VSPAERO configuration of 2026-11-24
   was not mesh-robust and was not run on this design.

**Also not run on this design:**

7. An engine table to 35,000 ft, and a baseline record that stores the above-table-top flag (B-9c).
8. A recorded run of the rate of climb against altitude above 30,000 ft. The review's explanation of the
   wider ceiling bracket rests on a probe, which is not quoted here.
9. A run that translates the Fig. K.3 low reading into fuel for this design.
10. A re-size with the engine family's SFC (the bands are carried by the info-gap study).
11. The engine closing check: no maker's part-power curve or altitude rating exists in the sources (G-6).
12. A full info-gap study of any cell other than W/S 14, A 8, W/S 13, A 8 and W/S 13, A 9.
13. The step-doubling check (mission sub-steps doubled) on this cell; it exists for W/S 14, A 8 only.
14. R13 at the ends of the empty-weight band; the multiplier does not move the centre of gravity.
15. A VSPAERO mesh finer than L2; VSPAERO with propeller, turret or sponsons.
16. Compressibility, fuselage and nacelle on the lattice; the propeller slipstream at the tail.
17. The flap's own ground effect in the rotation row.
18. A negative manoeuvre load factor; a gust check below zero-fuel weight with the payload off.
19. The take-off sweep at another site, weight, temperature or engine-lapse case; f varied over its band
    for the climb leg alone.
20. FAR field-length factors on R7 (G-1: not applied by ruling).
21. A payload-bay volume check.
22. A recorded test report at the gate commit. Now made (section 13).
23. A Gate A re-check as a generated record. Now made (section 13).

## 10. Numbers that differ between sources

None of these is a conflict in the records. Each is two different quantities or two roundings. They are
listed so that nobody quotes the wrong one.

| Number | Values | Why |
|---|---|---|
| R5 guarantee horizon | 1.0501 (`info_gap.json`, full study); 1.0500 (`cell_result.json`, endurance mode scan) | two searches of the same quantity |
| Service ceiling | 31,738.2 ft (Stage 1, clamped table); 30,407.1 to 30,432.5 ft (engine cycle); 29,954.9 and 32,473 ft (closed-form bracket) | section 4.7. Quote the cycle value with its caveat (B-9c) |
| Worst gust load factor | 3.504 (`gusts`, the sizing value); 3.481 (`vn`) | lift slope at the speed's own Mach number against the sizing Mach |
| Static margin, empty fuel | 0.0874 (record, compliance, VSPAERO report); 0.087 (aero report) | rounding |
| Static margin, full fuel | 0.1126 (record); 0.113 and 0.112 (aero report) | rounding of the Stage 1 value and of the lattice row |
| Downwash gradient | 0.451 (Stage 1); 0.452 and 0.4518 (Stage 3 lattice) | the lattice evaluated again |
| Raymer bare-planform lift slope | 4.906 (aero report, Mach 0); 4.953 (VSPAERO report) | the VSPAERO report's value is at Mach 0.158, a fixed value carried over from the superseded design, not this run's loiter Mach 0.142 |
| Climb propeller efficiency | 0.7041 at 93.3 kt (`propeller_points`); 0.7047 at 93.5 kt (climb bracket) | different points |
| Loiter propeller efficiency | 0.7733 (leg start, perf row); 0.7530 (held in Anderson's route) | different points |
| Cruise propeller efficiency | 0.8073 (outbound leg start, perf row); 0.7936 (held in Anderson's route) | different points |
| Unchoked fuel share | 77.4 % (this baseline); 77.7 % (W/S 14, A 8, re-size report); 71.8 % (superseded design) | different aircraft |
| Take-off distance, Stage 1 | 711 ft, 711.0 ft (reports); 710.957 ft (records) | rounding |
| V_C rule value | 104.5 kt (10 % above 94.96 kt, compliance row 19); 105 kt (rounded up to 5 kt); 110 kt (the floor, which sets V_C) | three steps of the same rule |
| Numbers inside rulings G-2, B-4, B-5 and B-8 | 6,396, 3,061 and 3,376 lb (G-2); 115 kt (B-4); -10.9 %, -18.6 % (B-5); 0.198 (B-8) | the ruling texts quote earlier designs. B-9d and B-9e restate B-4, G-2 and B-5 at the new values; B-8 is not restated |
| Take-off thrust speed | 0.707 V_TO (Stage 1, sweep); 0.7 V_LO (Anderson row) | two books' rules |

## 11. Records and reports used

| What | Record | Report |
|---|---|---|
| Baseline design, modes, info-gap study | `runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/` (`design_pusher.json`, `cell_result.json`, `info_gap.json`, `ledger.yaml`, `m250_table.json`, `run.log`) | `docs/validation/2026-11-26_task12_m250_bands_cells.md` |
| Choice of cell | `runs/task12/stage3/2026-11-26/m250_bands_cells/summary.json` | same |
| Re-size under both bands | `runs/task12/stage3/2026-11-26/m250_bands_resize/` (`curve.json`, `P450/h1.05/`) | `docs/validation/2026-11-26_task12_m250_bands_resize.md` |
| Band study on the frozen design | `runs/task12/stage3/2026-11-26/composite_band_study/summary.json` | `docs/validation/2026-11-26_task12_composite_band_study.md` |
| Stage 3 engine, perf, aero, rotation, ground effect | `runs/task12/stage3/2026-11-27/m250_ws13a8_measure/` | `docs/validation/2026-11-27_task12_stage3_{engine,perf,aero,rotation}_m250_ws13a8.md` |
| VSPAERO, wing and tails | `runs/task12/openvsp/2026-11-27_m250_ws13a8_vspaero/results.json`; model `runs/task12/openvsp/2026-11-27_m250_ws13a8/` | `docs/validation/2026-11-27_task12_vspaero_m250_ws13a8.md` |
| V-n check | `runs/task12/stage3/2026-11-27/vn_check_ws13a8/vn.json` | `docs/validation/2026-11-27_task12_vn_check_ws13a8.md` |
| Stage 1 compliance table | `runs/task12/stage3/2026-11-27/compliance_ws13a8/compliance.json` | `docs/validation/2026-11-27_task12_stage1_compliance_ws13a8.md` |
| Take-off sweep over f | `runs/task12/stage3/2026-11-27/takeoff_f_sweep_ws13a8/sweep.json` | `docs/validation/2026-11-27_task12_takeoff_f_sweep_ws13a8.md` |
| Superseded design (comparison values) | `runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/` | `docs/validation/2026-11-26_task12_performance.md` |
| R6 sources | no run | `docs/validation/2026-11-24_task12_m250_r6_sources.md` |
| Rulings | - | `docs/specs/00_decisions.md` section 9 |
| Spec | - | `docs/specs/task12_drone_conceptual_design.md` sections 3, 7.1a to 7.4 |
| Robustness figure | `runs/task12/stage3/2026-11-27/robustness_figure_ws13a8/` (`robustness.png`, `plotted_data.json`) | script `postprocess/task12_robustness_figure.py` |
| Gate A re-check | `runs/task12/stage3/2026-11-27/gateA_recheck_ws13a8/gateA.json` | `docs/validation/2026-11-27_task12_gateA_recheck_ws13a8.md` |
| Pytest at the gate commit | `runs/task12/stage3/2026-11-27/pytest_gate/` (`summary.json`, `junit.xml`, `pytest.log`) | - |
| Reviews | - | `docs/reviews/2026-11-26_task12_gateB_performance_review.md` (GB-1 to GB-7); `docs/reviews/2026-11-27_task12_gateB_ws13a8_review.md` (W-1 to W-11, Gate A re-check) |

## 12. Earlier review items, and what was left out

### 12.1 Items of the 2026-11-26 review (GB)

| Item | How this report handles it |
|---|---|
| GB-1 (composite band) | closed by B-2, B-2a, B-2b, B-2c; told in section 1.2; the two bands are in sections 3.3 and 3.4 |
| GB-1a (engine record dirty flag) | corrected: `engine.json` has `uncommitted_code_changes: false`; aero, rotation and ground-effect records have no flag (section 8.3, item 33) |
| GB-1b (R12 ceiling margin) | margins are taken from 23,500 ft (sections 2 and 4.7) |
| GB-1c (R9 prints -1.5) | -1.8 with -1.7 is printed and the negative margin 0.196 is given (section 2) |
| GB-1d (R18 text) | the spec carries the per-design rule; V_C is the 110 kt floor, so spec and record agree (sections 1.1 and 2) |
| GB-1e (downwash value) | 0.451 and 0.452 each quoted as what it is (sections 4.4 and 10) |
| GB-1f (R19 pairs unlike speeds) | leg airspeed is paired with leg ground speed (section 2) |
| GB-1g (rounding rule) | stated at the top |
| GB-1h (seed) | base seed 20261122; the ten sampling entries use 20261122 to 20261163 (section 3.1) |
| GB-2 (R9) | closed in the spec (B-3); the two gust values are noted (sections 2 and 10) |
| GB-3 (V_D exceedance) | the V-n check exists; section 5.2 |
| GB-4 (ruling list) | section 7 |
| GB-5 (missing open items) | section 8.3 |
| GB-6 (empty weight) | section 4.6, last paragraph; B-9g |
| GB-7 (robustness curves) | closed: figure of section 13 |

### 12.2 Items of the 2026-11-27 review (W)

| Item | Status |
|---|---|
| W-1 | this report |
| W-2 | run; section 5.3 |
| W-3 | ruled, B-9a |
| W-4 | ruled, B-9c; section 4.7 |
| W-5 | ruled, B-9d; section 5.2 |
| W-6 | the "8 h" label, the cruise Mach and the VSPAERO Mach note are fixed in the regenerated reports; spec R18 and 7.1a point to this baseline; G-2 and B-5 are restated by B-9e |
| W-7 | section 4.3; open item 11 |
| W-8 | G-2 covers the Anderson first-estimate row; section 4.6 |
| W-9, W-10, W-11 | notes; W-10 is ruled by B-9f; W-11 is open item 33 |

### 12.3 Numbers left out because they are not records

- The review's probe of the rate of climb against altitude above 30,000 ft (W review, section 2a). Only
  the recorded bracket and the recorded cause are quoted.
- The reviewer's own test run at `4ee2ae4` (W review, A8). Only the last recorded count is quoted.
- The "computed" numbers of the 2026-11-26 review (the composite band along one direction, the gust
  load at level top speed). The recorded band study and the recorded V-n check replace them.
- Section 5.4 of the 2026-11-26 report (the +43 lb decomposition): it belongs to the superseded cell.

No number in this report is untraced. The arithmetic done here is: the margins of section 2; 2,518 ft
(bracket width); 0.099 ft (fuselage term); 0.032 (rotation margin); 0.616 (0.5863 x 1.05); -2.7
(1.5 x -1.8); 0.030 (0.5455 less 0.5156); 10.9, 20.2 and 75.2 kt (level top speed less V_C or V_D);
0.039 (3.8 less 3.761); 0.461 (the superseded design's negative gust -1.239 against -1.7).

## 13. Close-out of ruling B-10 (added 2026-11-27)

No number above was changed. The three gaps of B-10c are closed from existing records, and the ledger
label of B-10b is changed.

| Gap or item | Closed by | What it shows |
|---|---|---|
| Robustness-curve figure (GB-7, spec 7.3) | `runs/task12/stage3/2026-11-27/robustness_figure_ws13a8/robustness.png`, data and source hashes in `plotted_data.json` | Plotted from `info_gap.json` `worst_case_curve` (8 stored horizons, h = 0 to 3) and `cell_result.json`. R5 worst endurance at the stored horizons up to 1.0501 against 3.5 h and h_T 1.05; R7 take-off and landing at the stored horizons. The transit-cliff ratio is stored at three horizons only (1, 1.05, 1.0924), so it is plotted as three points, not a curve. Horizons with no flyable mission or an unbounded field length are named on the axes, not plotted. Nothing is interpolated |
| Gate A re-check as a record (B-10c) | `runs/task12/stage3/2026-11-27/gateA_recheck_ws13a8/gateA.json`; `docs/validation/2026-11-27_task12_gateA_recheck_ws13a8.md` | A1 to A12 with the verdicts of the review (section 5) and ruling B-9a; A9 and A11 inherited. Values are read from the records in code |
| Recorded pytest report (A8) | `runs/task12/stage3/2026-11-27/pytest_gate/summary.json` | `tests/task12` at commit `bc8bf5d`, clean tree: 417 passed, 0 failed, 1 xfailed, exit code 0 |
| Ledger label (B-10b, APL-6) | `data/task12/ledger.yaml`, `prop_real_to_ideal` | `confidence` changed from `published` to `assumed`, which is the ledger's label for a judgement (the ledger header defines it so; there is no label called judgement). Value 0.85 and band 0.80 to 0.90 unchanged. Older records keep their own ledger copies |

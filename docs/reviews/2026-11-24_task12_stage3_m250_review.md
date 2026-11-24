# Review: Stage 3 re-measurement of the M250 baseline (2026-11-24)

Independent, read-only review (Fable) of commits c099f50 to a77cdb5:

- c099f50, 6b4eb0e: code (M250 route in `measurement/stage3_engine.py`, App. L propeller rows in
  `measurement/stage3_perf.py`, record ledger in `measurement/stage3_aero.py`, tests).
- e1473cd, 009a4ce, abf7fd0, a77cdb5: records in
  `runs/task12/stage3/2026-11-24/m250_baseline_measure/` and the four reports
  `docs/validation/2026-11-24_task12_stage3_{engine,perf,aero,rotation}_m250.md`.

Baseline measured: RR M250-B17F pusher, W/S 16, A 7, W0 3,117 lb
(`runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/`).

No tracked file was changed and nothing was committed. The reviewer's probe scripts and their
outputs were kept in the session scratchpad and are not committed. **Every number marked "probe"
below comes from those scripts, not from a run recorded in this repo.** The VSPAERO work of the
other agent was not reviewed. `python -m pytest -q tests/task12` on a77cdb5: 296 passed,
1 xfailed, exit code 0.

## Verdict

**The records are sound and reproducible. Three of the report's diagnoses are not, and the
package is not ready for Gate B as it stands.**

In plain words:

- All four M250 records regenerate to every digit, and every generated report number matches its
  record. The hand-written sections quote the records correctly.
- No coding, unit, speed or altitude error was found behind any out-of-tolerance row.
- Three explanations need correcting:
  1. The engine report's book-validation section tests the constant-cp burner. The M250 table
     uses the variable-cp (MSH) burner. The list of failing book rows is therefore the wrong list
     (S3M-1).
  2. CD0 at -41 % comes mostly from the friction coefficient the measurement chose (0.00312, a
     curve drawn through jet data). Anderson's own propeller-aircraft value is 0.0043, which gives
     -19 % (S3M-2).
  3. The take-off power row is not caused by k_TO 1.2. A larger k_TO raises the power needed; the
     difference comes from the climb-out segment (S3M-7).
- The climb propeller efficiency of 0.62 is real physics. It shows that Stage 1's sea-level climb
  rate and take-off thrust are optimistic. The requirements still hold with large margins in the
  reviewer's probes (S3M-3).
- Of the 14 rows the performance report counts as "within", 10 share their inputs and their
  formula with Stage 1 and can only show that the code is consistent. Every row that carries an
  independent input, other than cruise and loiter propeller efficiency and the field distances,
  fell outside tolerance (S3M-4).
- R7 is met with a large margin as the repository defines it (distance over 50 ft, no factor).
  With the FAR factor 1.666 the landing margin is 5 % and is not robust (S3M-5).

## What holds

**Reproducibility (probe: each module re-run with output to the scratchpad)**

- `perf.json`, `aero.json`, `rotation.json` and `engine.json` regenerate identical in every value.
  Only the commit hash and the output paths differ.
- The generated parts of the four reports regenerate identical apart from the header line. The
  engine report has no hand-written part.
- Records carry design, ledger and engine-table hashes, commit 6b4eb0e and a clean-tree flag.
- TP100 records: `runs/task12/stage3/2026-11-22/aero.json` and `2026-11-21/rotation.json`
  regenerate identical. In `2026-11-22/perf.json` all 20 earlier rows, the mission legs, the
  Anderson detail and the CD0 detail are identical; a re-run now adds the three propeller rows
  (see S3M-11).

**Hand-written sections against the records**

| Statement | Record | Result |
|---|---|---|
| TP100 pass: take-off power -7.1 %, W0 +87 %, CD0 -39 % | `2026-11-22/perf.json`: -7.07 %, +86.95 %, -38.97 % | equal |
| Anderson W0 with Stage 1's empty fraction 0.5348: 3,060.6 lb | `perf.json` `anderson_w0` | equal; 500 / (1 - 0.3018 - 0.62) = 6,394 lb by hand |
| 1,286 lb on 37.5 ft^2, 34 lb/ft^2 | row note; disk area from D 6.909 ft | equal (probe 34.3 lb/ft^2) |
| 182.3 x 0.80 / 0.62 = about 235 hp | arithmetic | equal (235.2) |
| 73.1 % of mission fuel in unchoked cells | record `unchoked_fuel_share` | equal |
| Lattice margins 0.116 and 0.083, agree to 0.001 | `aero.json`: 0.1156, 0.0834, difference 0.0005 | equal |
| Ground-effect table, 4 rows | `ground_effect_validation.json` | equal |
| Mission legs at 14 to 29 % of the rating | 64.8 and 130.5 hp of 450 | equal |

**Checks for a coding or input error (probes)**

- Propeller rows. Hand calculation of the climb row: T = 1,286 lb, q = 16.9 lb/ft^2, disk
  37.49 ft^2, C_T = 2.03, ideal efficiency 0.730, times 0.85 = 0.6205. The record has 0.6205.
  (L.8) is coded correctly. Density is sea level for climb and 20,000 ft for cruise and loiter.
- CD0 row. S_wet 913.06 ft^2, S 194.81 ft^2, fuselage length 27.8 ft and the Reynolds number
  2.65e7 are right. The formula (2.37) is coded correctly. The difference is the coefficient, not
  an error (S3M-2).
- Anderson first estimate. The fuel fraction 0.3018 is close to Stage 1's 0.3048 although it uses
  Anderson's own speeds and fixed take-off, climb and landing fractions. The denominator
  1 - 0.3018 - 0.62 = 0.078 is small, so W0 is very sensitive to the empty fraction. The
  implementer's diagnosis is right.
- Best-climb speed. Stage 1 lands on its 1.2 V_stall floor (71.0 kt); the closed form gives
  1.09 V_stall. The diagnosis is right.
- Stage 1's ceiling. The table's top altitude is 30,000 ft and the lookup returns 124.2 shp at
  every altitude above it. The statement is right.

**Code changes in c099f50 and 6b4eb0e**

- The M250 route reads the record's own ledger and table, checks that the table is the family's
  nominal member (pi_c gap 0), and marks the table rows "not judged" as 7.1b requires.
- The TP100 route (`measure`) is untouched by the diff.
- `stage3_aero` now reads the ledger copy beside the record. For the TP100 record this changes
  nothing (identical regeneration).
- The actuator-disk functions and the fixed-point loop are correct and tested by hand values.

## Findings

| ID | Severity | Finding | Fix |
|---|---|---|---|
| S3M-1 | high | **Engine report section 5 validates the wrong burner.** `book_validation()` uses the cycle code's default, the constant-cp burner. Its numbers equal the constant-cp rows of `runs/task12/stage3/2026-11-21/appk_validation.json` (S 0.851, 0.623, 0.575; Fig. K.9 ratios 1.14, 1.13, 1.11). The M250 table is built with the MSH burner (`m250_table.json`, key `burner`). The recorded MSH results are different: Fig. K.9 part throttle is inside its limit (-8.6, -7.9, -6.8 %), and Fig. K.3 S fails at pi_c 17 (-5.7 %) and 35 (-5.6 %); 16 of 18 rows pass. The section is headed "spec 7.1b item 1", which asks for the variable-cp burner. The sentence "the part-throttle trend of the cycle code is therefore not validated against the book" is wrong for the model in use. The sign also changes: the MSH model reads fuel consumption low against the book, not high. | Pass `burner="msh"` in `book_validation()` for the M250 report (or read the recorded MSH rows), regenerate, and correct the summary of failing rows. |
| S3M-2 | high | **The CD0 diagnosis is incomplete.** The row uses C_fe = 1.5 x flat plate at the fuselage Reynolds number = 0.00312, the dashed curve of Anderson's Fig. 2.55. That curve is drawn through jet fighters and transports. Anderson's own propeller-aircraft design uses C_fe = 0.0043 ((8.40), p. 414, library notes). Probe: 0.0043 gives CD0 0.0202, -19 %; Raymer's Table 12.3 light single (0.0055) gives 0.0258, +4 %. Stage 1's build-up corresponds to C_fe 0.0053. So about half of the -41 % is the measurement's choice of coefficient. The rest is real content of Stage 1's build-up: sponsons 0.0048 (19 % of CD0 from 6 % of the wetted area, form factor 3.2, interference factor 1.5), engine and sensor 0.0025, leakage 5 %, and a horizontal tail of 97.6 ft^2. The row is outside tolerance either way, in the favourable direction (the independent value is lower). It cannot confirm Stage 1's CD0 to +-10 %. | Re-run the row with Anderson's 0.0043 and report both. State that the method resolves CD0 to about +-20 %. If a tighter check is wanted, it needs another route (the VSPAERO parasite-drag estimate, or a wetted-area check on the OpenVSP model). |
| S3M-3 | medium | **Climb propeller efficiency 0.62 is real, and its consequences were not run.** Inputs: 450 shp, 70.7 kt (1.2 V_stall at the weight after take-off), sea level, D 6.909 ft. This is the most heavily loaded point of the mission, and it is the point Stage 1 uses for its sea-level climb rate. Probes with the App. L efficiency in place of 0.80: sea-level climb at 1.2 V_stall 2,413 ft/min, best 2,679 ft/min at 99 kt (Stage 1: 3,267); power for 1,000 ft/min 204 hp (Stage 1: 182; the report's 235 hp is a safe upper figure); ceiling 29,950 ft (Stage 1: 31,827); climb at 23,000 ft 555 ft/min; efficiency along a full-power climb 0.62 at sea level to 0.73 at 20,000 ft. Take-off: Stage 1's static thrust cap is 2,647 lb, which is above the ideal momentum-theory static thrust of this disk at 450 shp, 2,218 lb. With the App. L thrust (1,578 lb at 0.7 V_TO) the take-off distance is 789 ft against 656 ft. R7 and R12 keep large margins in all of these. The ledger band for `eta_p` (0.75 to 0.85) does not cover 0.62, so the info-gap study does not see this. | Record these as a run. Either give Stage 1 a speed-dependent propeller efficiency for take-off and climb, or state that 0.80 is a cruise and loiter value only. Review `static_ct_over_cp` 2.5 against the momentum limit. |
| S3M-4 | medium | **The performance report does not separate independent rows from coding checks.** Ten of the 14 "within" rows use Stage 1's own inputs in an algebraically equal formula: four power rows, mission fuel, best-range and best-endurance speed, climb rate, corner speed, ceiling. The report says so for mission fuel and corner speed, and in one closing sentence for the engine table, but the header counts them all as "within". Three of them (power at the ceiling, ceiling, mission fuel) are rows that 7.1b declares not independent and "not used as agreement checks"; the engine report marks its ceiling row "not judged", the performance report marks its ceiling row "within". The Anderson ceiling (32,306 ft) also sits above the table's 30,000 ft top and leans on the clamp more than Stage 1 does; the row note does not say so. | Add a column: independent, partly independent, or coding check. Mark the three 7.1b rows "not judged". Add the clamp note to the ceiling row. |
| S3M-5 | medium | **R7 margin depends on a definition that is not written down.** The repository judges R7 on the plain distance over 50 ft: take-off 656 ft (Anderson 667), landing 1,419 ft (Anderson 1,426) against 2,500 ft, info-gap h 1.605. That margin is real. The figure "2,377 ft" is the Anderson landing distance times the FAR factor (1,426.1 x 1.666 = 2,376); it appears in no report. With the factor the nominal margin is 124 to 136 ft (5 %). The baseline's own info-gap curve gives a worst-case landing of 1,856 ft at h = 1, which is 3,092 ft with the factor; the factored limit is reached at about h = 0.26 (reviewer's interpolation of the recorded curve). Landing is computed at take-off weight; at the landing weight of 2,232 lb the factored figure is 2,184 ft (probe). The Anderson landing row repeats Raymer's approach and flare geometry, so it checks the coding, as its note says. | Owner ruling on whether R7 carries the FAR factor. Write the answer in R7. |
| S3M-6 | medium | **The judged engine row passes almost automatically.** The brochure part-power rows (+0.7 to +1.7 %, "within") are the same three points as the 2026-11-23 engine validation. A model with constant SFC 0.613 gives -3.5, -3.8 and -8.9 % and would also pass +-10 % (probe; finding M-3 of the engine review said this for +-5 %). The row is at sea level and 70 to 100 % power; the mission is at 20,000 ft. The report states the range but presents the row as the independent engine check. For information (probe, the reviewer's own estimate, not from the library): a straight fuel-flow line through the brochure's 450 and 314 shp points, scaled to 20,000 ft with corrected power and corrected fuel flow, gives SFC within 0.6 to 1.7 % of the table at all nine mission points; in corrected terms the mission runs at 34 to 68 % of the rating. | Say in the report that the row cannot fail for a model calibrated at take-off. Keep 7.1b item 3 open ("rests on the model"). |
| S3M-7 | low | **Take-off power, -9.9 %: the stated cause has the wrong sign.** Probe: Mattingly's route needs 113.9 hp at k_TO 1.15, 117.8 at 1.2 and 123.0 at 1.25, so a larger k_TO needs more power. At Stage 1's 130.8 hp, Raymer's climb segment is 1,640 ft of the 2,500 ft (drag at 1.15 V_stall with C_L = 0.9 C_L,max), and Mattingly's whole airborne part is 970 ft (drag at 1.2 V_stall with C_L = C_L,max / 1.44). At 117.8 hp Raymer's method gives 5,244 ft. The row compares two models near zero climb gradient, where 10 % of power doubles the distance. It says nothing about the installed 450 shp. | Correct the diagnosis. Consider replacing the row by the distance at installed power, which is the quantity R7 uses. |
| S3M-8 | medium | **R13 is met by construction, and the aero report has stale text.** `uav.layout` places the wing so that the full-fuel and empty-fuel margins are centred in the band: 0.116 + 0.084 = 0.200. The 0.033 MAC above the floor is therefore not a measured margin. What is physical is the CG travel, 0.032 MAC, and the accuracy of the neutral point. Probe: the empty-fuel margin falls by 0.059 MAC per 0.1 of downwash gradient and reaches 0.05 at a gradient of 0.514 (record: 0.457). Over the tail heights the lattice can evaluate (0.18 to 0.9 D_f) the gradient is 0.480 to 0.406 and the margins stay inside R13 (empty 0.070 or more, full 0.146 or less). The table marks the static-margin rows "within: yes" although Stage 1 now uses the same lattice downwash (7.1c item 3). Stale sentences: "Stage 1 called its far-wake formula conservative ... here it gives 0.456" (0.456 is Stage 1's lattice value); "the nominal height is the render's, since Stage 1 fixes none" (the ledger fixes 0.4 D_f); the "0.0 ft: 0.695" point is inside the wake sheet that `uav.lattice_downwash` refuses. | Mark the rows "not judged (same model)". Say that the wing is placed to centre the margin. Remove the stale sentences and the 0.0 ft point. An independent neutral point is needed for R13 (the VSPAERO run may give one). |
| S3M-9 | low | **Ground-effect validation.** It fails against Anderson's G as stated. Raymer's (12.61), in the library, gives 0.511, 0.747, 0.844, 0.921 at h/b 0.1 to 0.5; the lattice is 13, 8, 5 and 2 % below it, inside +-15 % (reviewer's arithmetic). The two books differ from each other by 29 % at h/b 0.1. The reference was fixed in advance, so this is not a pass. `ground_effect_validation.json` has no generating script in the repository. The rotation limit is met without ground effect (-0.983 against 1.00), so the row decides nothing. | Add the script. Owner decision on whether to add (12.61) as a second reference. |
| S3M-10 | medium | **Rows of 7.1 without a measurement:** section C_L,max and polars (SU2 not run), gust load factor (no second source), Anderson's static margin (not coded), blade-element propeller efficiency (not coded). The single report of spec 7.3 (measurement table, requirement margins, robustness curves) does not exist yet; no document lists R1 to R19 against the Stage 3 values. | Run or waive each row by owner ruling. Write the 7.3 report. |
| S3M-11 | low | **Code and record notes.** (a) `stage3_engine --design` on a TP100 record uses the record's ledger but writes the hash of the default ledger and no design path. (b) `_prop_eta_fixed_point` returns without a flag if 100 passes do not converge. (c) The cruise and loiter shaft powers fed to App. L are Stage 1's power required divided by 0.80, so thrust is not exactly drag; the effect is under 0.001 in efficiency (probe). (d) Commit 6b4eb0e also carries `conceptual/vspaero_check.py` and its test, which belong to other work. (e) A re-run of the TP100 performance record now has 23 rows and "14 within, 5 outside"; the TP100 climb efficiency is 0.627, also outside. (f) `runs/task12/stage3/2026-11-20/engine.json` does not regenerate with the present code (probe: 189 values differ); it predates the MSH burner and the widened family, and the diff does not touch its route. | Fix (a) and (b). Note (e) in the TP100 report or leave the record as is. |
| S3M-12 | low | **Anderson first estimate, +105 %.** The diagnosis holds. The record's own comparison gives empty fractions of 0.527 (Table 3.1), 0.511 (Table 6.2), 0.535 (build-up), 0.570 (metal) and 0.607 (metal with crew items). Anderson's 0.62 is close to the last one. | Report the row as "explained: historical crewed metal aircraft", if the owner agrees. |

## Gate B readiness (spec 7.4)

The reviewer does not rule. "Pass" means the criterion is met on the records; "fail" means it is
not met as written; "ruling" means the owner must decide.

Requirements met by the independent measurement:

| Item | Status | Basis |
|---|---|---|
| R5, 8 h nominal | ruling | Mission fuel is a coding check (0.00 %). Anderson's fuel fraction (0.302 against 0.305) is partly independent. The engine SFC in the mission cells rests on the model (7.1b item 3). |
| R5, 3.5 h at h = 1 | pass | `info_gap.json` of the baseline: h 1.052. The study does not include the Stage 3 findings (S3M-3). |
| R6, 20,000 ft | ruling made | R-f: design assumptions; no source. |
| R7 take-off | pass | 667 ft (Anderson), 789 ft with App. L thrust (probe), against 2,500 ft. |
| R7 landing, unfactored | pass | 1,426 ft against 2,500 ft; h 1.605. |
| R7 landing, FAR factor | ruling | 2,376 ft nominal; not robust (S3M-5). |
| R7 stall 70 kt | ruling | 59.2 kt with the ledger C_L,max 1.35; the SU2 row was not run. |
| R9 | ruling | Gust 3.23 against 3.8 from Stage 1 only; no second source. Corner speed is a coding check. |
| R12 climb | pass | 3,275 ft/min (Anderson, efficiency 0.80); 2,413 to 2,679 ft/min with App. L (probe); requirement 1,000. |
| R12 ceiling | pass | 30,420 to 30,453 ft (cycle, record); 29,950 ft with App. L (probe); requirement 23,000. Stage 1's 31,827 ft is 1,400 ft high from the table clamp. |
| R13 | ruling | Met by construction with the shared downwash model (S3M-8). |
| R16 to R19 | pass as coding checks | Power rows agree to 0.00 %. |

Rows inside tolerance or explained:

| Row | Status |
|---|---|
| W0, Anderson first estimate | explained; owner to accept (S3M-12) |
| CD0 | fail as explained; explanation to be corrected, still outside (S3M-2) |
| Take-off power | fail as explained; explanation to be corrected (S3M-7) |
| Best-climb speed | explained |
| Climb propeller efficiency | explained; consequences to be recorded (S3M-3) |
| Engine book validation | fail as reported: wrong burner (S3M-1) |
| Engine closing row | ruling: within, but cannot fail (S3M-6) |
| Engine validity | reported: 73.1 % of fuel in unchoked cells |
| Lift slope | pass (-3.4 %) |
| Span efficiency | ruling: not comparable as specified |
| Rotation with ground effect | ruling: model fails its validation; limit met without it |
| SU2 C_L,max, gust, Anderson static margin, blade element | fail: not computed (S3M-10) |

Robustness horizon at least 1: pass on the baseline's record (R5 guarantee 1.052, R7 1.605),
subject to S3M-5.

Output of 7.3: fail; the report does not exist.

## Owner questions

1. Does R7 carry the FAR landing factor 1.666? If yes, landing does not meet horizon 1.
2. Is Anderson's 0.62 empty fraction accepted as not applicable to an uncrewed composite
   aircraft, so that the +105 % row counts as explained?
3. Which C_fe should the CD0 row use: Anderson's propeller value 0.0043, the Fig. 2.55 curve, or
   both? Is a row that resolves CD0 to about +-20 % enough, or is a second route wanted?
4. Should Stage 1 keep a flat propeller efficiency of 0.80 for take-off and sea-level climb, now
   that App. L gives 0.62 there and the static thrust cap exceeds the momentum limit?
5. Are the missing rows (SU2 polars, gust, Anderson's static margin, blade element) to be run
   before Gate B, or waived one by one?
6. Is the engine closing check accepted as "rests on the model" until part-power or altitude
   data are found?
7. Should the ground-effect model also be compared with Raymer's (12.61)?
8. R13: is a second neutral-point estimate required before Gate B?

## Numbers that may be quoted

From the records, with the caveat that the engine model is checked at sea level and 70 to 100 %
power only:

- Propeller efficiency by App. L: climb 0.62, cruise 0.81, loiter 0.79 (Stage 1: 0.80).
- Lift slope: lattice 4.576 per rad against 4.739, -3.4 %.
- Take-off 667 ft and landing 1,426 ft over 50 ft by Anderson (Stage 1: 656 and 1,419 ft).
- Service ceiling with the cycle's own power: 30,420 to 30,453 ft.
- Anderson's W0 with his 0.62 empty fraction: 6,396 lb; with Stage 1's 0.535: 3,061 lb.

Not to be quoted until corrected: the list of failing App. K book rows (S3M-1), "CD0 -41 % because
of engine, sensor and gear terms" (S3M-2), and "take-off power from k_TO" (S3M-7). Probe numbers
in this review are not recorded runs.

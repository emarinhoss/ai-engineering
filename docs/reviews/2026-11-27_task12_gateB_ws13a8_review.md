# Review: Gate B re-runs on the new baseline W/S 13, A 8 (commits abb1e03..4ee2ae4)

Reviewed at HEAD `4ee2ae4` on 2026-11-27. Nothing but this file was changed.

How to read the numbers:

- **Read** means copied from a record or from a report generated from a record. Only these may be quoted elsewhere.
- **Arithmetic** means a sum, difference or product of two read values, done here.
- **Probe** means an unrecorded check I ran to understand a gap. A probe result is described in words only. It is not a result and must not be quoted.

Baseline record: `runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/` (ruling B-2c). Read: W0 3,517.3 lb, empty 1,918.6 lb, fuel 1,098.7 lb, sized loiter 11.00 h, span 46.52 ft, wing 270.56 ft^2, V_C 110 kt EAS, power margin 37.5 %. Horizons: R5 guarantee 1.0501, cliff 1.0924, R7 1.2845 (take-off 1.2845, landing 1.6406).

## Verdict

- **No recorded value of the new baseline is on the wrong side of a requirement.** The compliance table has 19 pass, 0 fail, 11 not tested.
- **Every outside row is covered by a ruling** (G-2, G-3, B-5, B-6). The ruling texts quote the superseded design's numbers and need one line each.
- **Three things stand between the records and a Gate B pass.** None is a failed margin.
  1. The Gate B performance report still describes the superseded W/S 16, A 7 design (section 6).
  2. The take-off sweep over the propeller factor f (ruling G-9) was not run on the new baseline.
  3. The new baseline has no Stage 1 package. Gate A items A9 and A11 cannot be tested on it, and the owner must say whether the record, the compliance table and this re-check are enough (section 5).
- **Two things the owner should know.** The Stage 1 service ceiling (31,738 ft) rests on the engine table held constant above its top altitude. The gust margins are about half what they were, so envelope protection matters more.

## Findings by severity

| # | Severity | Finding | Section |
|---|---|---|---|
| W-1 | blocks the pass | The performance report (spec 7.3 output) describes the superseded design | 6 |
| W-2 | blocks the pass unless waived | G-9 take-off sweep over f not run on the new baseline; the R7 horizon fell from 1.506 to 1.2845 and take-off binds | 6, 7 |
| W-3 | blocks the pass until ruled | No Stage 1 package for W/S 13, A 8: A9 and A11 not testable, A2 and A7 only in part | 5 |
| W-4 | should fix | Stage 1 ceiling 31,738 ft is above the engine table's top (30,000 ft), where the lookup holds power constant. The cycle's own power gives 30,407 to 30,432 ft. No flag is raised on the extrapolation. R12 is not affected | 2a |
| W-5 | should fix (owner information) | Gust margins fell to 0.296 g (positive) and 0.196 g (negative). Level top speed is above V_C at 20,000 ft as well as at sea level. One sensitivity point passes the negative ultimate | 3 |
| W-6 | should fix | Stale fixed text: "8 h" label on an 11.00 h loiter (perf and compliance), "cruise Mach 0.16" (aero), Mach 0.158 in the VSPAERO lift-slope comparison, spec R18 and 7.1a pointers, numbers inside rulings G-2 and B-5 | 2, 4, 6 |
| W-7 | note | The design moved further into the unvalidated part of the engine table: 77.4 % of the fuel in unchoked cells (71.8 % before), loiter SFC 0.856 (0.825 before) | 2e |
| W-8 | note | The Stage 3 agent's statement that no ruling covers the Anderson first-estimate row is wrong: G-2 covers it | 2b |
| W-9 | note | Commit 897b5e9 changed report text only | 1 |
| W-10 | note | VSPAERO L2 full-fuel margin 0.004 above the band is inside the mesh spread and covered by B-6 | 4 |
| W-11 | note | Record hygiene and rounding | 2f, 4 |

## 1. Diff review of 897b5e9

**Result: text only. No number changed.**

What the commit changed (read from `git show 897b5e9`):

- `measurement/vn_check.py`: the title ("frozen design" to "design record"), the docstring, and one sentence that now prints V_C and V_D from `res['V_C_eas_kt']` and `res['V_D_eas_kt']` instead of the fixed "115" and "172.5". Both keys are written by `compute()`.
- `measurement/stage1_compliance.py`: the title, the docstring, and the pointer to the V-n report, which now reads "the V-n check of the same design".
- `tests/task12/test_vn_check.py`: one new test that the report text takes its speeds from the result.

No line in `compute()`, `point()` or the compliance rebuild was touched.

Check I ran (not a record; it writes nothing): the current `report_text` applied to each committed record, compared with the committed report.

| Record | Report | Difference |
|---|---|---|
| `2026-11-26/vn_check/vn.json` (superseded design) | `2026-11-26_task12_vn_check.md` | title line only |
| `2026-11-27/vn_check_ws13a8/vn.json` | `2026-11-27_task12_vn_check_ws13a8.md` | none |
| `2026-11-26/compliance_frozen/compliance.json` | `2026-11-26_task12_stage1_compliance_frozen.md` | title line and the V-n pointer sentence |
| `2026-11-27/compliance_ws13a8/compliance.json` | `2026-11-27_task12_stage1_compliance_ws13a8.md` | none |

So the old code would have printed "115 kt" and "172.5 kt" for a 110 kt design. The fix was needed, and the superseded reports still regenerate with their own numbers.

Small points:

- The compliance report no longer names the V-n report file. A reader has to find it. The record path would be better than no pointer.
- The new test covers the V-n text only. The compliance text change has no test.
- The usage example in the `vn_check.py` docstring still gives the superseded design's paths.

## 2. Stage 3 on the new baseline

Sources (read): `docs/validation/2026-11-27_task12_stage3_{perf,engine,aero,rotation}_m250_ws13a8.md`, generated from `runs/task12/stage3/2026-11-27/m250_ws13a8_measure/`. Perf counts: 12 within, 3 outside, 6 not judged, 1 not computed. These are the same counts as on the superseded design.

### 2a. Service ceiling: why the gap grew from -396 ft to -1,783 ft

**Cause: Stage 1's ceiling crossed the top of the engine table.** It is not a new modelling difference.

The values (read):

| Quantity | Superseded W/S 16, A 7 | New W/S 13, A 8 | Source |
|---|---|---|---|
| Stage 1 ceiling | 29,746.6 ft | 31,738.2 ft | design records |
| Closed form (5.121), efficiency at its own speed (lower bound, the row's value) | 29,350.1 ft | 29,954.9 ft | perf reports |
| Closed form, efficiency at Stage 1's speed (upper bound) | 29,893 ft | 32,473 ft | perf reports, `climb_bracket` |
| Bracket width (arithmetic) | 543 ft | 2,518 ft | |
| App. K cycle power, Stage 1's own bisection (family min to max) | 29,715.8 to 29,748.3 ft | 30,407.1 to 30,432.5 ft | engine reports |
| Engine row minus Stage 1 | -31 to +2 ft | -1,331 to -1,306 ft | engine reports |

The chain of causes, each from a record or the code:

1. **The larger wing raised the ceiling.** W/S fell from 16 to 13 and the aspect ratio rose from 7 to 8, with the same 450 shp engine. Stage 1's 100 ft/min altitude rose by 1,992 ft (arithmetic) and passed 30,000 ft.
2. **The engine table ends at 30,000 ft.** `m250_table.json` has `h_ft` from 0 to 30,000 ft (read). `conceptual/engine_model.py` clamps the inputs to the table (line 53; the module docstring says so). Above 30,000 ft the lookup returns the 30,000 ft power.
3. **So above 30,000 ft Stage 1 climbs on power that no longer falls.** The engine row shows the size of this. It repeats Stage 1's bisection with the cycle's own power and gets 30,407 to 30,432 ft, which is 1,306 to 1,331 ft below Stage 1. On the superseded design, whose ceiling was below the table top, the same row differed by -31 to +2 ft. The engine report says this in words ("the difference here is the table's edge, not the family's spread").
4. **The closed-form row uses the same clamped table.** Its offset from Stage 1 has two recorded parts: it takes the disk efficiency at the minimum-power speed, where the disk is less efficient, and it has no 1.2 V_stall floor. Below the table top that offset was worth 396 ft. Above the top the rate of climb falls slowly with altitude, so the same kind of offset is worth much more altitude. **Probe (not a result):** I evaluated both routes from 20,000 to 33,000 ft on both designs. The rate of climb falls several times more slowly per 1,000 ft above 30,000 ft than below it, and the new design still climbs at more than 100 ft/min at 30,000 ft while the superseded one did not. That is consistent with points 1 to 3. If the report is to quote this, it needs a recorded run.

**The bracket was produced both times.** The 2026-11-26 perf report gives 29,350 to 29,893 ft and the 2026-11-27 report gives 29,955 to 32,473 ft. Both are in `climb_bracket` of their records. Stage 1's value lies inside the bracket in both. What changed is the width, 543 ft against 2,518 ft, and the upper bound is now 2,473 ft above the table top (arithmetic).

**This has been seen before.** The 2026-11-24 M250 baseline (flat propeller) had Stage 1 at 31,827 ft and the engine row at 30,420 to 30,453 ft (-1,407 to -1,374 ft), with the same sentence about the table edge (read, `2026-11-24_task12_stage3_engine_m250.md`). No gate on reading the table above its top was added then.

**R12 is not affected.**

- The requirement is 23,000 ft plus the 500 ft Gate A margin. Margins to 23,500 ft (arithmetic): 8,238 ft on Stage 1's value, 6,907 ft on the lowest cycle value, 6,455 ft on the closed form's lower bound.
- The power row at 23,000 ft (281.1 hp needed against 450) is evaluated inside the table.
- R6 is not affected. The engine's operating altitude is still assumption R-f, and 23,000 ft is still above every certified B17 installation found.
- R12 is not inside the info-gap horizon (record `exclusions` and the earlier report).

**What is wrong and should be fixed (W-4):**

- 31,738 ft should not be quoted as the ceiling without the caveat. The compliance table row 14 prints it plain. The best recorded value is the engine row's 30,407 to 30,432 ft, which still rests on a cycle model with no altitude data.
- A silent clamp is the kind of input that should be gated (`CLAUDE.md`: gate bad inputs). The lookup should at least flag a read above the table top, or the table should run to 35,000 ft. Extending the table changes `service_ceiling_ft` in the baseline record, so it is a re-record and an owner decision (Q3).
- The generated note of the perf row says both ceilings "lean on that clamp, and this one more where it lies higher". The row's own value, 29,955 ft, is below 30,000 ft and does not use the clamp. The sentence is printed whenever either value is above the top (`stage3_perf.py` lines 576-580). Wording defect, no number.

Verdict on the row: **not judged (7.1b: same table), numerically outside, explained.** The same holds for the engine report's ceiling row.

### 2b. Anderson W0 first estimate, +114.9 %

**Ruling G-2 covers it. The Stage 3 agent's statement that no ruling covers it is wrong (W-8).**

- G-2 (`00_decisions.md` section 9) says the first estimate with Anderson's historical empty fraction 0.62 "counts as explained, not failed", because 0.62 is a crewed-aircraft fraction. The ruling is by reason, not by value.
- The generated perf report already cites G-2 for this row.
- The three values G-2 asks for are in the record (read): 7,557.8 lb with 0.62; 3,554.0 lb with Stage 1's fraction 0.5455 (+1.0 %); 4,035.8 lb with Anderson's build-up (8.83) (+14.7 %, not judged). Anderson's fuel fraction is 0.3138 against Stage 1's 0.3124, so the difference is the empty fraction.
- The numbers in the ruling text (6,396, 3,061 and 3,376 lb) are the 2026-11-24 baseline's. The ruling needs a line that it stands at the new values (Q5).

One thing has moved and should be said at the gate. The build-up row grew from +9.12 % to +14.74 %. It is not judged, because (8.83) is Raymer's own Table 15.2 method. But the record's `empty_fraction_comparison` now reads 0.5455 for the build-up against 0.6220 for Table 15.2. On the 3,005 lb Stage 1 package design the two were 0.525 and 0.529. Table 15.2 weighs the wing and tails per square foot, and this design has 270.6 ft^2 of wing and 135.5 ft^2 of horizontal tail. The new empty-weight band (0.95 to 1.05, ruling B-2a) and the composite band now act on the build-up. At their joint worst end the fraction is about 0.586 x 1.05 = 0.616 (arithmetic from `build_up_metal` 0.5863), which is close to the Table 15.2 level. So the bands at h = 1 reach about as far as that cross-check. This answers the old GB-6 note in part.

### 2c. Take-off power, CD0 and Fig. K.3 under B-5

**All three are still explained at the new values.** B-5 quotes the superseded design's numbers and needs a line (Q5).

| Row | Superseded | New | Still explained? |
|---|---|---|---|
| Installed power for take-off (Mattingly against Raymer) | -10.89 % | -11.62 % | **Yes.** The diagnosis is regenerated at the new values: 132.7, 136.7 and 142.6 hp at k_TO 1.15, 1.2 and 1.25, so k_TO does not explain it. At Mattingly's 136.7 hp Raymer's route gives 4,758 ft, with 3,809 ft of it in the climb segment. The row compares two climb-out models where the distance is most sensitive to power. B-5 replaced it by the distance row at installed power: 711 ft against 719 ft, +1.14 %, within ±15 % |
| Zero-lift drag (Anderson (2.37), Cfe 0.0043) | -18.63 % | -14.32 % | **Yes, and closer.** 0.01892 against Stage 1's 0.02208. Stage 1 is the higher, conservative value. The Cfe that reproduces Stage 1 is 0.005019. The method resolves CD0 to about ±20 % (G-3) |
| Fig. K.3 S at pi_c 17 and 35 | -5.7 %, -5.6 % | -5.7 %, -5.6 % | **Yes, unchanged.** These rows test the cycle code against the book and do not depend on the aircraft. 16 of 18 within. The ±10 % SFC band carries them (B-5) |

No run translates the K.3 low reading into fuel for this design. That was true before and B-5 accepted it.

### 2d. Rate of climb and the other not-judged rows

| Row | Value (read) | Judgement |
|---|---|---|
| Sea-level rate of climb, closed form (5.121) | 1,915.2 against 2,325.8 ft/min, -17.66 % (was -15.11 %) | Not judged, correctly. The closed form assumes power available independent of speed. The disk gives 0.5567 at the closed form's 58.5 kt and 0.7047 at Stage 1's 93.5 kt. Bracket 1,915 to 2,540 ft/min; Stage 1 inside. R12's 1,000 ft/min holds at the lower bound by 915 ft/min (arithmetic) |
| Rate of climb, excess power at Stage 1's speed | 2,325.8 against 2,325.8, 0.00 % | Within. This is the coding check of the climb arithmetic |
| Best-climb speed | 58.47 against 93.55 kt, -37.49 % (was -34.79 %) | Not judged, same cause. Stage 1's speed is 1.75 V_stall, above the 1.2 V_stall floor, an interior maximum |
| Power at the ceiling altitude 23,000 ft | 281.1 against 281.1 hp | Not judged (7.1b), numerically inside |
| Mission fuel | 1,098.7 against 1,098.7 lb | Not judged (7.1b), numerically inside. **The label says "8 h". The record's loiter is the sized 11.00 h** (`mission` leg time 11.0; nominal hours on station 11.000 in `info_gap.json`). The compliance table's row 3 has the same label (W-6) |
| Anderson build-up W0 | +14.74 % | Not judged (same-author method); see 2b |
| Span efficiency | 0.990 against 0.811, +0.179 (was +0.152) | Not judged: the lattice value is inviscid, (12.49) is a whole-aircraft fit. Not comparable as specified |
| Static margin by Anderson (8.76) as printed | +0.254 at full and empty fuel | Not judged: the printed relation leaves out downwash and tail efficiency |
| Downwash and static-margin rows | 0.451 against 0.452; 0.113 and 0.087 | Not judged: same model as Stage 1 (7.1c item 3) |
| Gust load factors | Stage 1 3.504, Stage 3 none | Not computed (G-5 waiver stands) |
| Lift slope | 4.749 against 4.906, -3.2 % | Within ±5 %. Independent |
| Take-off and landing distance | +1.14 %, +0.42 % | Within ±15 %. Partly independent |

### 2e. Engine, rotation and ground effect

- **Engine rows.** Power at 20,000 and 25,000 ft and the three leg SFC rows are not judged (same table) and numerically inside. The three brochure rows are within (+0.7 to +1.7 %) and, as before, cannot fail (G-6).
- **The design leans more on the unvalidated part of the table (W-7).** Read: 77.4 % of the mission fuel is burned in unchoked cells, against 71.8 %. The whole loiter (645.7 lb) and the whole return cruise (147.3 lb) are unchoked. The loiter runs at 77.8 falling to 59.2 shp, and the leg-mean loiter SFC is 0.856 against 0.825 on the superseded design. A bigger wing flies slower on less power, where the model's SFC is worst and least supported. Nothing new is wrong. The ±10 % SFC band is doing more work.
- **Rotation.** Tail CL needed -0.968 without ground effect, -0.930 with it, against the limit 1.00. Met both ways. The margin without ground effect is 0.032 (arithmetic). The tail is large: 135.5 ft^2, half the wing area, at volume scale 1.59.
- **Ground-effect validation.** Inside Raymer (12.61) at 4 of 4 h/b, inside Anderson (6.77) at 1 of 4. Same as before. G-7 stands: it does not decide the row.

### 2f. Record hygiene

- `perf.json`, `vn.json` and `compliance.json` carry a clean-tree flag. `engine.json` carries `uncommitted_code_changes: false`. `aero.json`, `rotation.json` and `ground_effect_validation.json` carry a commit but no dirty flag (as on the superseded design, GB-1a).
- The baseline's own `info_gap.json` and `cell_result.json` have `git_dirty: true`, with one untracked path, the run's own output folder.
- `runs/task12/openvsp/2026-11-27_m250_ws13a8/model.json` has `git_dirty: true` with no file list.

## 3. V-n check

Sources (read): `docs/validation/2026-11-27_task12_vn_check_ws13a8.md`, `runs/task12/stage3/2026-11-27/vn_check_ws13a8/vn.json` (commit `897b5e9`, clean tree).

### Method and inputs: correct

| Item | Check | Result |
|---|---|---|
| Gust relation | Raymer (14.4)-(14.8) in `conceptual/raymer_loads.py`: mass ratio at altitude density, alleviation 0.88 mu/(5.3 + mu), EAS with sea-level density | as coded and as the record's `gusts` and `vn` entries; reproduction error 1.2e-07 |
| Gust velocity rule | 30 ft/s up to V_C, linear to 15 ft/s at V_D, 15 ft/s beyond (Raymer p. 339, civil normal category) | `design_gust_velocity`; the record shows 30.0, 15.0 and 27.0 ft/s at the right speeds |
| V_C | Rule B-4 / R18: 10 % above the fastest cruise sub-step, rounded up to 5 kt, at least 110 kt EAS | Fastest sub-step 94.96 kt EAS; the 10 % rule gives 104.5, rounded 105. **The 110 kt floor sets V_C**, not the 10 % rule |
| V_D | 1.5 V_C (spec R18) | 165.0 kt EAS |
| Limits | +3.8; -1.8 with the 0.1 g margin, so -1.7 (B-3, ledger) | as the record's `limits` |
| Weights | take-off 3,517.3 lb and zero-fuel 2,418.6 lb (arithmetic: W0 less fuel) | zero-fuel weight includes the 500 lb payload |

The corner speed is 104.0 kt EAS, now below V_C (it was 115.3 against 115). At V_C the aerodynamic manoeuvre limit is above 3.8 at both weights, so the structural limit governs there.

### Result under the rule

No point exceeds a limit. The governing point is V_C at 20,000 ft at zero-fuel weight: +3.504 / -1.504.

| Margin | Superseded design | New baseline |
|---|---|---|
| Largest positive gust | 3.239 | 3.504 |
| Positive margin to 3.8 (arithmetic) | 0.561 | 0.296 |
| Negative margin to -1.7 (arithmetic) | 0.461 | 0.196 |

The margins roughly halved although V_C dropped by 5 kt. The gust increment goes with speed over wing loading and with the lift slope. W/S fell from 16 to 13 and the aspect ratio rose from 7 to 8, which outweighs the lower speed.

### The five points that exceed with the gust held at 30 ft/s

This is a sensitivity. It is not the rule and not a failure. Values read from the report (positive / negative):

| Point | Superseded design | New baseline | Against the limits |
|---|---|---|---|
| Sea level, V_D, zero fuel | 3.815 / -1.815 | 4.011 / -2.011 | exceeds both |
| Sea level, level top speed, zero fuel | 4.258 / -2.258 | 4.393 / -2.393 | exceeds both |
| 20,000 ft, V_D, take-off weight | 3.560 / -1.560 (inside) | 3.904 / -1.904 | **new**; exceeds both |
| 20,000 ft, V_D, zero fuel | 4.446 / -2.446 | 4.841 / -2.841 | exceeds both |
| 20,000 ft, level top speed, zero fuel | 3.541 / -1.541 (inside) | 3.761 / -1.761 | **new**; positive inside by 0.039, negative past -1.7 and inside -1.8 |

What the owner should know:

1. **Lower V_C and V_D did not help.** Three points exceeded before and five do now, at lower speeds. The lighter wing loading is the reason.
2. **The worst point passes the negative ultimate.** The largest value is +4.841 / -2.841 (20,000 ft, V_D, zero fuel). The positive side is below the ultimate 5.7 (record `Nz_ultimate`). On the negative side the ultimate is 1.5 x -1.8 = -2.7 (arithmetic; the record carries only the positive ultimate), and -2.841 is past it. On the superseded design the worst was -2.446, inside -2.7.
3. **Level flight at 20,000 ft now reaches the edge.** The level top speed there is 120.9 kt EAS, 10.9 kt above V_C. No dive is needed, only full power. A full 30 ft/s gust at that speed at zero-fuel weight gives 3.761, which is 0.039 inside the positive limit and uses up the 0.1 g negative margin. Under the rule the same point is 3.488 with 27.0 ft/s, inside.
4. **At sea level the level top speed is 185.2 kt EAS**, 20.2 kt above V_D and 75.2 kt above V_C (arithmetic). The structure is not cleared to it. The V-n report says so.

### Is 15 ft/s at V_D adequate here?

- **As a conceptual-design rule, yes.** It is Raymer's rule, applied as written. Under it the V_D points are 2.194 to 2.920, far inside. V_C governs the structure, which is how the rule is meant to work.
- **The rule assumes something this airframe does not give by itself.** The gust falls to half at V_D because V_D is meant to be a rare excursion. Here full power in level flight takes the aircraft past V_C at 20,000 ft and past V_D at sea level. How often it is above V_C is set by the autopilot alone.
- **The ledger's own band says the gust could be larger.** `gust_ude_fps` is banded 30 to 50 ft/s (50 is the transport value up to 20,000 ft, Raymer Fig. 14.6). The info-gap study moves it to 50 at the worst point and pays for it in structure weight (one at a time: 11.00 to 10.40 h on station; read). So the robust endurance already carries a harder gust at V_C. The built nominal structure does not.
- **Not checked:** a negative manoeuvre load (no negative CL_max in the record); the gust at a weight below zero-fuel weight with the payload off; a second gust source (G-5).

### Is envelope protection (B-4) now more important?

**Yes.** Three reasons, all from the records:

1. The margin at the governing point is 0.296 g instead of 0.561 g, and 0.196 g on the negative side instead of 0.461 g.
2. Protection is now needed in level flight at the mission altitude, not only in a descent or at sea level. The spec's R18 text speaks of "keeping level top speed below V_D (at sea level ...)". For this design the autopilot must also hold V_C at 20,000 ft against available power.
3. The speed margin between normal operation and V_C is unchanged in kind (fastest cruise sub-step 94.96 kt EAS against V_C 110), but the margin between V_C and the first sensitivity exceedance has shrunk to 10.9 kt at 20,000 ft.

I do not propose changing the rule. I propose that the owner confirm B-4 at these margins and that the preliminary-design entry item name the 20,000 ft case and the gust criterion above V_C (Q4).

## 4. VSPAERO, wing and tails without fuselage

Sources (read): `docs/validation/2026-11-27_task12_vspaero_m250_ws13a8.md`, `runs/task12/openvsp/2026-11-27_m250_ws13a8_vspaero/results.json`. I checked the table against the record: every value matches.

| Quantity | L1 | L2 | Stage 1 |
|---|---|---|---|
| Static margin, full fuel, MAC | 0.1448 | 0.1538 | 0.1126 |
| Static margin, empty, MAC | 0.1197 | 0.1287 | 0.0874 |
| Neutral point, ft from nose | 12.820 | 12.876 | 12.624 (12.723 without the fuselage term) |

**Judgement under B-6: accepted as support. Nothing here blocks.**

- B-6 accepts R13 by layout construction, with the G-8 run as support, and names a fuselage-inclusive neutral point as a preliminary-design entry item. That stands for this design.
- **The 0.004 excess at L2 does not decide anything.** It is on the over-stable side. The model has no fuselage, so it reads high. The mesh spread from L1 to L2 is 0.009 MAC, larger than the excess. L1 is inside the band.
- **The new run is closer to Stage 1 than the one B-6 accepted.** The superseded design read 0.159 and 0.167 at full fuel, both above the band, and +0.043 / +0.051 over Stage 1. The new one reads +0.032 / +0.041 over Stage 1.
- **The risk R13 guards is the 5 % floor at empty fuel.** VSPAERO puts the empty margin at 0.120 to 0.129 and the neutral point 0.20 to 0.25 ft aft of Stage 1's, never ahead. That supports the floor. It does not prove it: the fuselage term moves the neutral point forward, and Stage 1's own equation prices it at 0.099 ft (arithmetic: 12.723 less 12.624), about 0.016 MAC.
- The aero report's own sensitivity (read): the empty margin reaches the floor at a downwash gradient of 0.521 against the lattice's 0.451; over the band of tail heights the margins run 0.080 to 0.133; the CG travel is 0.025 MAC.

Small points (W-6, W-11):

- The wing-alone lift slope is compared with Raymer's bare planform "at the loiter Mach 0.158 of the table" (4.953). The run's loiter Mach is 0.1420 (`results.json` `conditions`). `conceptual/vspaero_check.py` line 254 fixes the Mach numbers 0.158 and 0.227, which were the superseded design's. The effect is small (4.906 at Mach 0, 4.953 at 0.158) and no verdict rests on it, but it is the same kind of fixed text that 897b5e9 removed from the V-n report.
- Two rounding slips in the hand-written text: the L2 offset from the no-fuselage neutral point is 0.152 ft, not 0.153 (12.8757 less 12.7234); the full-fuel margin change L1 to L2 is 0.0091, not 0.0090.
- The aero report says "at cruise Mach 0.16". That string is fixed in `measurement/stage3_aero.py` line 253. The record's cruise Mach is 0.210.

## 5. Gate A re-check on the new baseline (ruling B-7)

Checklist: spec section 6, items A1 to A12. Earlier reviews: `docs/reviews/2026-11-20_task12_gateA_round1.md` to `round3.md`, `2026-11-21_task12_gateA_round4.md` and `round5.md`. No Gate A re-check was recorded for the superseded W/S 16, A 7 design.

**What exists for this design:** the design record and its ledger copy, the info-gap study, the compliance table, the Stage 3, V-n and VSPAERO records, and an OpenVSP model. **What does not exist:** a Stage 1 package (spec section 4 output) for W/S 13, A 8. The latest package, `docs/validation/2026-11-25_task12_conceptual_m250_appl.md`, describes the 3,005 lb W/S 22, A 8 design sized without margin. So the three-view, weight statement, trades, carpet plot, V-n diagram, out-of-calibration list and risk list of this design were not generated.

| # | Item | Verdict | Record that shows it |
|---|---|---|---|
| A1 | Every requirement traces to a number with its margin | **pass** | Compliance table `2026-11-27_task12_stage1_compliance_ws13a8.md`: 30 rows, 19 pass, 0 fail, 11 not tested (by construction, notes, flags). R5's 3.5 h guarantee is in `cell_result.json` and `info_gap.json` (horizon 1.0501; worst case at h = 1 is 3.827 h). Notes: the table gives value and limit, not a margin column; R3 and R11 have no row; R6 is "not checked" (assumption R-f) |
| A2 | Weight closes; fractions sum below 1; fit against build-up reported and explained | **pass on closure; the explanation is not written for this design** | `design_pusher.json`: the 13 components sum to the empty weight 1,918.56 lb; empty + fuel + payload = 3,517.249 lb against W0 3,517.250 lb (arithmetic). Fractions 0.5455 + 0.3124 = 0.858, payload 0.142. `empty_fraction_comparison` records the build-up 0.5455 against Table 3.1 x 0.95 0.5156, Table 6.2 0.4952 and Table 15.2 0.6220. The build-up is now 0.030 above the composite fit; on the package design it was 0.006 below. No report explains the difference for this design |
| A3 | Fuel closes for every segment, with the 6 % allowance | **pass** | `mission` in the record: six segments from 3,517.25 to 2,480.75 lb; 1.06 x 1,036.50 = 1,098.69 lb = the fuel (arithmetic). The Stage 3 mission-fuel row reproduces every segment fraction to six decimals |
| A4 | Static margin in R13 full and empty; trim with authority; rotation possible | **pass** | Compliance rows 15, 16, 29, 30. Margins 0.1126 and 0.0874 (by layout construction, B-6). `layout.trim`: tail CL at most 0.133 (loiter start) against the trim limit 0.5; 0.020 to 0.025 on the cruise legs. Rotation tail CL 0.968 of 1.00; 0.930 with ground effect (Stage 3 rotation report). The rotation margin is thin |
| A5 | Structure sized for the larger of manoeuvre and gust at both altitudes | **pass** | `n_limit` 3.8 = larger of 3.8 and the gust 3.504; `gusts` has both altitudes and both weights; ultimate 5.7. V-n check: no point exceeds under the rule. See section 3 for the thinner margins |
| A6 | Installed power at 20,000 ft meets climb and ceiling; production engine within the rubber engine's band; fixed-engine re-size recorded | **pass on power; the rubber-band clause is not testable** | Compliance row 23: 281.1 hp needed (ceiling case) against 450, margin 37.5 %. Rows 13 and 14: climb 2,326 ft/min, ceiling above 23,500 ft on all three recorded values (section 2a). The fixed-engine re-size is this record. No rubber-engine design was sized for this cell; the engine was fixed by ruling R-a. Its altitude operation is assumption R-f |
| A7 | Every assumption has a source and a band; out-of-calibration uses listed | **pass on sources; partly on bands; the list is not testable** | Ledger copy `ledger.yaml`: 111 entries, every one with a source. 58 have no band: 19 requirements and 39 assumptions (among them `airfoil_efficiency`, `tail_eta_h`, `c_ht`, `c_vt`, `flap_delta_cl_max`, `cl_ground`, `engine_sfc_allowance`). This is as at earlier rounds, which passed A7. New since then: the composite band acts through `composite_model: saving` and `empty_weight_factor` is banded 0.95 to 1.05 (B-2a). 25 of the 55 info-gap variables are inert. The out-of-calibration list exists only in the 2026-11-25 package |
| A8 | Every Raymer equation used has a passing printed-value test | **pass on my run; no recorded test report at this commit** | `python -m pytest -q tests/task12` at HEAD `4ee2ae4`: 397 passed, 1 xfailed (my run, not a record). The last recorded count is 336 passed, 1 xfailed, in `runs/task12/stage1/2026-11-25/test_report.txt`. The equation-to-test table is section 10 of the 2026-11-25 package; the methods do not depend on the sizes |
| A9 | Concept choice justified by its scoring table; rejected concept kept | **not testable on this design** | The last recorded scoring is the 2026-11-25 package: pusher 4.11 (3,005 lb) against tractor 3.95 (2,715 lb). No tractor was sized under both bands at h_T 1.05, and W0 carries 0.40 of the score. The pusher was frozen at Gate A round 3 and only sizes may change after a pass (spec section 6), so the item is inherited, not re-shown |
| A10 | Layout fits: tanks, payload bay, gear, CG range | **pass on the recorded rows; the payload bay is not testable** | Compliance rows 24 to 28: fuel 21.92 of 73.17 ft^3; main gear stows in sponsons at half-track 4.731 ft; propeller clearance 14.44 in against 8.95; nose-wheel load 0.163 and 0.151, inside 5 to 20 % and above the 8 to 15 % optimum. CG 11.938 to 12.091 ft, travel 0.025 MAC, margins inside R13. No row has ever checked the payload-bay volume (open since round 3). No Stage 1 three-view of this design; the OpenVSP model `runs/task12/openvsp/2026-11-27_m250_ws13a8/` is the only drawing |
| A11 | Every risk names how Stage 3 will measure it | **not testable on this design** | No risk list was generated for it. The 2026-11-25 package's list (nine risks, each with a measurement) is the same configuration. Of its measurements, run on the new baseline: Anderson's weight estimate, the lattice, rotation with a ground image, the V-n check at level top speed. Waived: the SU2 polar (G-5). No data: the maker's engine curves |
| A12 | Defaults R10 to R15 confirmed or changed by the owner | **pass** | Confirmed at rounds 1 and 2; R12 revised at round 4; R13 ruled at Gate B (B-6). The re-size introduced no new default. The ledger's `loiter_h` is 11.0 with its source text stating the 8 h requirement and the sized loiter |

**Entry criterion.** Spec section 6 asks that "the package of section 4 is complete" before a Gate A review. It is not, for this design. B-7 asked only for the compliance table and the A1 to A12 re-check, and both now exist. Whether that is enough is Q1.

**Outcome of the re-check.** No item fails. A1, A3, A4, A5 and A12 pass. A8 passes on my run of the tests, which is not a record. A2, A6, A7 and A10 pass on what the records can show, with one clause each that only a package or a new row could show. A9 and A11 are inherited from the frozen configuration and cannot be tested on these sizes.

## 6. What the Gate B performance report must change

`docs/validation/2026-11-26_task12_performance.md` has one commit (`d3ecb12`). None of the fixes of the earlier review have been made. It describes the superseded design throughout. The cleanest route is a new report for the new baseline, with the old one kept as the record of what Gate B first saw.

### Sections and numbers to replace

| Section | Replace with | Source |
|---|---|---|
| Title, intro, 1 | "new baseline W/S 13, A 8 (B-2c)", and why the W/S 16, A 7 design was superseded: under both bands its R5 horizon was 0.906 and its worst endurance at h = 1 was 2.915 h (B-2a) | `00_decisions.md`; `composite_band_study/`; `2026-11-26_task12_m250_bands_{resize,cells}.md` |
| 1, design table | W0 3,517.3, empty 1,918.6, fuel 1,098.7, payload 500.0 lb; wing 270.56 ft^2, span 46.52 ft; sized loiter 11.00 h; V_C 110 kt EAS (the floor binds); power margin 37.5 %; f 0.85 | `design_pusher.json`, `cell_result.json` |
| 1, "no compliance table" paragraph | the table now exists: 19 pass, 0 fail, 11 not tested | compliance report 2026-11-27 |
| 2 | lift slope -3.2 %; CD0 -14.32 %; brochure rows unchanged | perf, aero, engine reports 2026-11-27 |
| 3.1 to 3.4 | all rows from the 2026-11-27 reports (section 2 above lists the ones that moved). Keep the hand note on the "8 h" label, now 11.00 h | same |
| 3.2 validity | 77.4 %; loiter 645.7 lb and return cruise 147.3 of 147.3 lb unchoked; legs at 13 to 27 % of the rating | engine report |
| 3.5 | 0.1448 / 0.1538 full, 0.1197 / 0.1287 empty; neutral point 12.820 / 12.876 against 12.624 (12.723); mesh spread 0.056 ft, 0.009 MAC | VSPAERO report |
| 4, every row | values of the compliance table and V-n report. R7: 711 / 719 ft and 1,348.6 / 1,354.3 ft; stall 53.33 kt. R9: 3.504 / -1.504 against +3.8 / -1.7. R12: 2,325.8 ft/min with bracket 1,915 to 2,540; ceiling per section 2a with the table-edge caveat. R13: 0.1126 / 0.0874. R16: 243.5 hp. R18: 110 kt, fastest sub-step 94.96 kt EAS, level top speed 185.2 and 120.9 kt EAS. R19: 129.3 and 119.1 kt true airspeed, 104.3 and 94.1 kt ground speed | records named |
| 5.1 | R5 guarantee 1.0501 (endurance mode; cliff 1.0924); R7 1.2845 (take-off 1.2845, landing 1.6406); 8 h nominal 0.4135; reserve usable 0.5387. Sampling: `n_beating_search` 0 in all ten entries | `info_gap.json`, `cell_result.json` |
| 5.2 | worst hours 11.000, 9.215, 7.369, 5.586, 3.827 at h 0 to 1; take-off 711, 815, 971, 1,206, 1,585 ft; landing 1,349, 1,422, 1,515, 1,634, 1,790 ft; not flyable from h = 1.5 | `worst_case_curve` |
| 5.3 | SFC 12.924 / 9.426 h; f 10.333 / 11.635 h; power cap 10.952 / 11.012 h; C_L,max 10.715 / 11.133 h. **Add the two new bands:** composite factor 11.890 / 10.145 h; empty-weight factor 11.557 / 10.457 h. 30 active, 25 inert of 55 | `one_at_a_time` |
| 5.4 | **not run on this design.** The decomposition record compares the flat and App. L baselines of the superseded cell. Say so, or drop the section | - |
| 5.5 | **not run on this design** (W-2). Either run the sweep or state that the table is the superseded design's | - |
| 5.6 | CG travel 0.025 MAC; floor reached at a gradient of 0.521 (lattice 0.451); margins 0.080 to 0.133 over the tail-height band; VSPAERO offsets +0.196 / +0.252 ft | aero and VSPAERO reports |
| 5.7 | the record's five exclusions; the grid of the re-size and the three cells studied | `info_gap.json`; cells report |
| 6 | every size in the diagnosis table; add the ceiling rows with the table-edge cause; VSPAERO line is now "L2 0.004 above the band" | section 2 above |
| 7 | 7.1 to 7.3 with the new values. 7.2 changes in kind: take-off power, CD0 and K.3 are now explained by ruling (B-5), so the "outside without a ruling" group is empty. 7.1 is answered by B-1 | rulings |
| 8 | remove "compliance table not generated" and "gust at level top speed not in the record"; add the items of "not run on this design" below | - |
| 9 | items 5, 6, 7, 10, 11 are ruled (B-5, B-2, B-3); item 12 is ruled and recorded (B-4, V-n check); item 13 is ruled (B-8) with the new horizon 0.4135 | rulings |
| 10 | every row; drop the R9 -1.5 row (spec fixed); add the three ceiling values and the two gust values (3.504 and 3.481) | records |
| 11 | new record and report paths; rulings B-1 to B-8, B-2a to B-2c | - |

**Not run on the new baseline, to be stated as such:** the take-off sweep over f (G-9); the App. L decomposition; a figure of the worst-case curve; a Stage 1 package; a rubber-engine or tractor design at these sizes; the SU2, blade-element and second gust rows (G-5); a fuselage-inclusive neutral point (B-6).

### Earlier review items: which still apply

**GB-1, minor items a to h**

| Item | Status for the new report |
|---|---|
| a. Engine record dirty flag | **Applies, corrected:** `engine.json` has `uncommitted_code_changes: false`; aero, rotation and ground-effect records have none (section 2f) |
| b. R12 ceiling margin taken from 23,000 ft | **Applies.** Take margins from 23,500 ft: 8,238, 6,907 and 6,455 ft for the three values, with the table-edge caveat |
| c. R9 prints -1.5 | **Applies as a report fix.** The spec now says -1.8 with -1.7 (B-3). Print it and give the negative margin, 0.196 |
| d. R18 omits the spec text and the 110 / 115 difference | **Changed.** The spec now carries the per-design rule. For this design V_C is the 110 kt floor, so the spec and the record agree. The spec's R18 still says "115 kt EAS for the frozen design" and points to the 2026-11-26 V-n report: update both |
| e. Lattice downwash value | **Applies.** Stage 1 0.451, Stage 3 0.452 (0.4518); quote each as what it is |
| f. R19 pairs unlike speeds | **Applies.** Pair leg airspeed with leg ground speed: 129.27 with 104.27 kt and 119.07 with 94.06 kt |
| g. Rounding rule statement | **Applies** |
| h. Seed | **Applies.** Base seed 20261122; the ten sampling entries run 20261122 to 20261163 |

**GB-1 itself (composite band).** Closed by B-2, B-2a, B-2b and B-2c. The new report must tell it: the band now acts on the Table 15.4 savings, the empty-weight band exists, the superseded design failed R5 under both, and the design was re-sized. `composite_factor` is no longer in `inert_variables` (read). `conceptual/stage1.py` now includes it in the trades when `composite_model` is set, but no trade table exists for this design.

**GB-2 (R9).** Closed in the spec (commit `d94bd31`). Report fix as item c. Keep the note that the record holds two values for the worst gust point, 3.504 (`gusts`, the sizing value) and 3.481 (`vn`).

**GB-3 (V_D exceedance).** The run it asked for exists. The report must state: level top speed 185.2 kt EAS at sea level, above V_D 165 and V_C 110; 120.9 kt EAS at 20,000 ft, between V_C and V_D; no exceedance under the rule; the five sensitivity points; envelope protection as a preliminary-design requirement (B-4). Section 3 above has the wording.

**GB-4 (ruling list).** Still applies, and has grown. List: R-a to R-f; G-1 to G-9; edits A and B; the baseline-cell ruling (now superseded); the per-design V_C rule; the R5 restatement and the headwind and Oswald exclusions (2026-11-22); the Gate A margins (500 ft, 0.1 g, power 0); B-1 to B-8 with B-2a, B-2b and B-2c. Spec 7.1a still names the superseded record as "the Stage 1 value" and the 2026-11-26 compliance table: both pointers must move to the new baseline. The Gate A re-check that 7.1c item 4 and B-7 ask for is section 5 of this review.

**GB-5 (missing open items).**

| Item | Status |
|---|---|
| APL-7, APL-9: disk favourable in cruise, no tip-Mach, hub or blockage loss | **Applies.** Cruise efficiency 0.807 on this design |
| APL-6, S3A-8: one f at every point; ledger labels `prop_real_to_ideal` "published" | **Applies** |
| APL-4: static C_T/C_P is inert, not "not varied" | **Applies** (`static_ct_over_cp` is in `inert_variables`) |
| S3A-1: climb speed at the worst endurance corner near the 20,000 ft stall | **Not testable on this design:** no decomposition was run on it. State that |
| S3A-5: Anderson's 0.62 route holds the disk efficiencies at the record weight | **Applies** (0.7936 and 0.7530 held) |
| S3A-4: closed-form climb rows classed "coding check" | **Applies in part.** The verdicts are "not judged"; the class column still says "coding check" |
| Span efficiency and ground-effect validation missing from the open items | **Applies** |
| S3M-11(b): the propeller fixed point returns without a flag if it does not converge | **Applies** |

**GB-6.** Applies with new numbers: the Anderson build-up row is +14.74 %, and the empty-weight band now exists (section 2b).

**GB-7.** Applies: still no figure of the worst-case curve.

### Spec and decision edits that go with it

- Spec R18: "115 kt EAS for the frozen design" and the V-n report pointer.
- Spec 7.1a: the record pointer, the compliance-table pointer, and "-10.9 %".
- `00_decisions.md`: one line under G-2 and B-5 with the new values, if the owner confirms (Q5).

## 7. Owner questions

**Blocking a Gate B pass:**

1. **Stage 1 package for the new baseline (W-3).** A9 and A11 cannot be tested on W/S 13, A 8, and the weight explanation, out-of-calibration list and three-view do not exist for it.
   - (a) Accept the record, the compliance table and this re-check, with A9 and A11 inherited from the frozen configuration.
   - (b) Generate a Stage 1 package for the baseline first.
   - **Recommend (a).** The configuration was frozen at Gate A and only sizes changed, which the spec allows. Make the package a preliminary-design entry item.

2. **Take-off sweep over f (ruling G-9; W-2).** G-9 asks for a recorded sweep quoted next to R7 in Gate B. It exists only for the superseded design.
   - (a) Run it on the new baseline (`measurement/takeoff_f_sweep.py`, a few minutes).
   - (b) Waive it for this design.
   - **Recommend (a).** The R7 horizon fell from 1.506 to 1.2845, take-off binds, and the worst take-off at h = 1 is 1,585 ft against 1,367 ft before. The low-speed propeller factor now matters more.

3. **The performance report (W-1).** Not a question, but the gate cannot pass on a report of another aircraft. Recommend a new report for the baseline along section 6.

**Not blocking:**

4. **Service ceiling above the engine table (W-4).**
   - (a) Quote the cycle value 30,407 to 30,432 ft with the caveat; add a flag on any table read above 30,000 ft; leave the record.
   - (b) Extend the table to 35,000 ft and re-record the baseline.
   - **Recommend (a) now, (b) at preliminary-design entry.** R12 holds by more than 6,400 ft on every recorded value, so nothing is decided by the difference. Option (b) changes the baseline record.

5. **Envelope protection at the thinner margins (W-5).** Confirm that B-4 stands with a positive gust margin of 0.296 g and level top speed above V_C at 20,000 ft.
   - (a) Confirm B-4, and word the preliminary-design item to cover level flight at every altitude and a gust criterion above V_C.
   - (b) Raise V_C or the limit load factor now.
   - **Recommend (a).** Nothing exceeds under the rule. Option (b) is a re-size, and the info-gap study already carries a 50 ft/s gust as weight.

6. **Rulings that quote the superseded design.** Do G-2 (+114.9 %, 7,558 lb) and B-5 (-11.6 %, -14.3 %, -5.7 / -5.6 %) stand at the new values?
   - **Recommend yes**, with one line each in `00_decisions.md`. Both were ruled by reason, and the reasons hold (section 2b, 2c).

7. **R13 with VSPAERO L2 0.004 above the band.** Does B-6 cover it?
   - **Recommend yes.** It is inside the mesh spread, on the over-stable side, without a fuselage, and closer to Stage 1 than the run B-6 accepted.

8. **Empty weight.** Anderson's build-up is now +14.7 % and Table 15.2 gives 0.622 against the build-up's 0.5455. Is the ±5 % empty-weight band still the owner's choice?
   - **Recommend yes**, recorded as a named preliminary-design risk. With the composite band at its metal end the two bands together reach about the Table 15.2 level.

## Checks I ran

None of these is a record.

- `report_text` of `vn_check` and `stage1_compliance` applied to the four committed records and compared with the committed reports (section 1).
- The rate of climb against altitude on both designs, by Stage 1's search and by the closed form (section 2a, described in words only).
- Sums of the record's component weights, weight fractions and segment fuel (section 5, marked arithmetic).
- `python -m pytest -q tests/task12`: 397 passed, 1 xfailed.

Files most relevant:

- `/home/user/ai-engineering/runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/` (`design_pusher.json`, `cell_result.json`, `info_gap.json`, `ledger.yaml`, `m250_table.json`)
- `/home/user/ai-engineering/runs/task12/stage3/2026-11-27/m250_ws13a8_measure/` (`perf.json`, `engine.json`, `aero.json`, `rotation.json`)
- `/home/user/ai-engineering/runs/task12/stage3/2026-11-27/vn_check_ws13a8/vn.json` and `compliance_ws13a8/compliance.json`
- `/home/user/ai-engineering/runs/task12/openvsp/2026-11-27_m250_ws13a8_vspaero/results.json`
- `/home/user/ai-engineering/conceptual/engine_model.py` (line 53, the table clamp)
- `/home/user/ai-engineering/measurement/stage3_perf.py` (lines 576-580), `measurement/stage3_aero.py` (line 253), `conceptual/vspaero_check.py` (line 254)
- `/home/user/ai-engineering/docs/validation/2026-11-26_task12_performance.md`
- `/home/user/ai-engineering/docs/specs/task12_drone_conceptual_design.md` (R18, section 6, 7.1a) and `docs/specs/00_decisions.md` (section 9)

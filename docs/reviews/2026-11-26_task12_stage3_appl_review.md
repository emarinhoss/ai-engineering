# Review: Task 12 commits 951708a..7a21167 (App. L baseline re-size, Stage 3 on the record's propeller, APL wording)

Read-only: nothing edited, stashed or committed, and `git status` is clean at the end. `pytest tests/task12` on 7a21167 gives 351 passed, 1 xfailed (run by me, cache and bytecode writes off).

"Read" means taken from a repo record or report. "Computed" means from my scratch scripts, which call the repo's `info_gap.Built`, `uav` and `anderson` functions on the recorded designs. Computed numbers are not recorded runs and must not be quoted in reports until recorded. Scripts are in `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/` (`corner.py`, `seg.py`, `climb.py`, `roc.py`, `and.py`, `regen.py`).

## Verdict

- **Records are sound.** `2026-11-26/m250_baseline_appl_measure/perf.json` regenerates with 0 differences in rows, Anderson detail and mission legs (computed). The new worst-case endurance (3.507 h) and the old one (3.512 h) reproduce from the records (computed).
- **Disk use is correct** in the power, mission-fuel, propeller, ceiling and engine-point rows.
- **Two generated statements in the perf report are wrong for the app_l record** (S3A-2, S3A-3), and two rows are misclassified (S3A-4). Fix these before the Gate B report quotes them.
- **The +43 lb is a climb-segment effect**, not a band-width effect (S3A-1).
- **The evidence is enough to write the 7.3 report** as a report with open items. It is not enough for a 7.4 "pass" without owner rulings, R13 first.

## Findings

### S3A-1 (should-fix: the baseline report does not explain the +43 lb). The climb leg drives it.

Split of the +43.4 lb (read from the two `target_result.json`):

| Quantity | Old (flat) | New (app_l) | Change |
|---|---|---|---|
| W0 (lb) | 3,116.9 | 3,160.3 | +43.4 |
| Fuel (lb) | 950.0 | 977.3 | +27.3 |
| Empty weight (lb) | 1,667.0 | 1,683.0 | +16.1 |
| L_sized (h) | 8.78125 | 9.03125 | +0.25 (8 lattice steps) |
| W0 at 8 h sized loiter (lb) | 3,017.0 | 3,024.2 | +7.2 |

- About 10 lb is the nominal mission costing more at equal sized loiter (computed from the two slopes, 127.9 and 132.0 lb/h).
- About 33 lb is the extra 0.25 h of sized loiter the worst case needs.
- The "~2.5 lb nominal probe" is not in any record I found; the records give +7.2 lb at L = 8 h.

The band low end is not the cause. Mean efficiencies per leg (computed):

| Case | Cruise out | Loiter | Cruise back |
|---|---|---|---|
| Old worst case, flat at h 1.05 | 0.7475 | 0.7475 | 0.7475 |
| New worst case, f 0.7975 | 0.7455 | 0.7384 | 0.7472 |
| New nominal, f 0.85 | 0.8144 | 0.7917 | 0.8156 |

- Relative low ends are nearly equal: 0.7475/0.80 = -6.6 % against 0.7975/0.85 = -6.2 %.
- The nominal cruise bonus (0.814 against 0.80) disappears at the corner because the aircraft there is heavier and draggier and loads the disk more: W0 3,560 lb against 3,160, L/D 9.9 against 12.3 (computed).

The climb leg carries the difference. New design at the E2 corner with 3.5 h loiter, app_l against a flat 0.7475 swapped in (computed):

| Segment fuel (lb) | Disk, f 0.7975 | Flat 0.7475 |
|---|---|---|
| Climb | 83.1 | 64.6 |
| Cruise out | 232.9 | 233.0 |
| Loiter | 349.8 | 348.9 |
| Cruise back | 215.6 | 216.1 |
| Mission fuel with reserve | 976.6 | 956.9 |

| Climb inputs at the corner | Disk | Flat |
|---|---|---|
| Efficiency at mid-altitude | 0.667 | 0.7475 |
| D/T | 0.550 | 0.480 |
| Best-climb speed (kt) | 87.7 | 80.9 |
| Climb fraction | 0.9765 | 0.9817 |

- At nominal the same swap costs only 4.8 lb: climb +5.7, cruise legs -3.9, loiter +2.8 (computed).
- In hours at the corner: 3.507 h with the disk against 3.713 h flat on the new design; 3.318 h against 3.512 h on the old design (computed).
- Consequence: the robust weight now hinges on the disk at its most heavily loaded point, where f = 0.85 is least supported (APL-5), and on a two-point climb model (mean D/T of sea level and 20,000 ft at one TAS).
- At the corner that TAS (87.7 kt) is about the 20,000 ft stall speed, 87.9 kt, by my hand calculation with W/S 18.0 and C_L,max 1.29. This is existing Stage 1 behaviour, not from these commits.
- Fix: add a recorded old-against-new decomposition to `docs/validation/2026-11-25_task12_m250_baseline_appl.md`: segment fuel at the worst point under both propeller models and efficiency per leg. State that the climb leg and the take-off use of f drive the change.

### S3A-2 (blocking for the Gate B report: wrong generated text). Best-climb-speed diagnosis is false for app_l.

- The report says "Stage 1 searches speeds from 1.2 V_stall upward and lands on that floor (98.99 kt)" (`measurement/stage3_perf.py` `_diag_best_climb`, and the row note in `speed_rows`).
- For this record 1.2 V_stall is 71.0 kt (read: V_stall 59.17 kt). Stage 1's 98.99 kt is an interior maximum at 1.67 V_stall. My search over speed with the disk gives 2,636.1 ft/min at 99.05 kt (computed).
- Real cause of -34.8 %: the disk's efficiency rises with speed (0.590 at 64.6 kt, 0.622 at 71 kt, 0.7195 at 99 kt, computed), so thrust power grows faster than power required. The closed form (5.118)/(5.41) assumes constant power available and returns the minimum-power-required speed, 64.56 kt.
- "The sea-level rate of climb agrees to +7.93 %" is also wrong wording for a row outside ±3 %.
- Fix: branch the note and the diagnosis on `is_app_l`, state the cause above, then regenerate.

### S3A-3 (blocking for the Gate B report: the row is not apples to apples). Sea-level rate of climb, +7.9 %.

- The row puts the efficiency at Stage 1's speed (0.7195 at 99 kt) into (5.121), which then subtracts the minimum power required, which occurs at 64.6 kt. The two speeds cannot occur together.
- The result is an upper bound by construction: max over V of [eta(V) P - P_R(V)] cannot exceed eta(99) P - P_R,min.
- The +209 ft/min is exactly (P_R(99 kt) - P_R,min)/W: 71.3 hp against 51.3 hp (computed). It measures the level-flight power curve and says nothing about Stage 1's climb code. It can never be negative.
- With the efficiency at the closed form's own speed (0.5902), (5.121) gives 2,238 ft/min, -15.1 % (computed). Stage 1's 2,636 lies between the two.
- The same relation is used the other way in `ceiling_anderson`, which takes the efficiency at the closed form's speed (lower bound: 29,350 ft against 29,747 ft, read). The two (5.121) rows are inconsistent with each other.
- The report has "No diagnosis is coded for this row".
- What the row should say: "(5.121) assumes power available independent of speed. With the App. L disk it is not, so the closed form does not apply. Bracket: 2,238 ft/min (efficiency at its own speed, 64.6 kt) to 2,845 ft/min (efficiency at Stage 1's speed). Stage 1's 2,636 lies inside. Not judged."
- Add a real coding check: (eta P - D V)/W at Stage 1's speed with the disk efficiency there. It gives 2,636.1 ft/min, 0.00 % (computed).
- R12 is not at risk: even the lower bound is 2.2 times the 1,000 ft/min.

### S3A-4 (should-fix: classification). `roc_sl` and `v_best_climb` are no longer coding checks.

- Under app_l they are not "same inputs and an algebraically equal formula". They are a constant-efficiency closed form against a speed-dependent model.
- The header count "coding check: ... 2 outside" reads as two coding errors; there are none.
- Fix: for app_l mark both "not judged (closed form assumes constant power available)" and report the bracket. Keep the flat behaviour for flat records. Spec 7.1a intends these rows to "check the arithmetic", which the excess-power check in S3A-3 does.
- The other classes are right:
  - Power rows and mission fuel: coding.
  - Three propeller rows: coding, deviation about 1e-13.
  - Take-off power, the two field distances, W0 first estimate: partly independent.
  - CD0 and gust: independent.
- Independent evidence left after G-4:

  | Row | Result |
  |---|---|
  | Lift slope | -3.4 %, within |
  | CD0 | -18.6 %, outside, favourable direction |
  | Brochure SFC rows | within, but cannot fail (G-6) |
  | Gust | not computed |

  The 7.3 report must say this in one place.

### S3A-5 (note, with a wording fix). Holding the disk efficiency per leg at the record weight in the Anderson W0 route is a fair choice.

- Read: cruise efficiency 0.8028, loiter 0.7677, fuel fraction 0.3097 against Stage 1's 0.3092; W0 7,108.7 lb with empty fraction 0.62 and 3,168.9 lb with Stage 1's 0.5326.
- With Stage 1's empty fraction, letting the efficiency follow the iterated W0 gives 3,169.9 lb against 3,168.9 held (computed): no effect.
- With 0.62 and the efficiency following W0, my iteration did not close; it ran past 24,000 lb with the loiter efficiency falling to 0.54 (computed).
- So the choice only matters for the row G-2 already rules "explained", and 7,109 lb is not a self-consistent estimate for this propeller.
- The move from 6,396 to 7,109 lb is the small denominator: 1 - 0.3097 - 0.62 = 0.0703 against 0.0782 (computed from read values).
- Fix: the row note still says "polar, SFC used, eta_p ... from the record or its ledger copy". Replace with the docstring's statement, print the two efficiencies in the detail line, and say the 0.62 route does not close if the disk follows the weight (after recording that).

### S3A-6 (note). Take-off power -10.9 % and CD0 -18.6 % stay outside: disclose, do not fix.

- Take-off power: the diagnosis is the corrected S3M-7 one and its numbers match the record (142.3 against 159.7 hp; Raymer's route at 142.3 hp gives 4,550 ft, read). It says nothing about the installed 450 shp.
- The quantity R7 uses is the distance at installed power: 793.5 ft Stage 1, 802.8 ft Anderson, +1.2 % (read).
- That row shares the thrust function, which under app_l rests on f at low speed (APL-5, a judgement). So there is no independent check of take-off thrust either. Say so next to R7.
- CD0: as G-3 ruled. The method resolves about ±20 %. Stage 1 is the higher, conservative value.

### S3A-7 (should-fix: test coverage). The flat reproduction is good for the M250 flat record's performance rows, thin elsewhere.

- Proven:
  - `stage1` and `stage3` of every perf row except CD0 to 1e-9 against the 2026-11-24 `perf.json`, plus mission legs and five Anderson keys.
  - The committed `m250_baseline_measure_rerun/perf.json` matches the old file except CD0 (G-3), classes and verdicts, and one 1e-16 rebuild value (my diff).
- Not proven:
  - Engine route: only `_record_points` shaft power is compared. `_level_power` (the `_segment_points` path), the engine rows and the engine ceiling are not; no flat `engine.json` was rerun.
  - No TP100 flat record (`2026-11-22/perf.json`, `engine.json`) is compared in this test file.
  - Verdicts and classes are not asserted.
  - The loop skips ids missing from the old file, so a dropped row would pass.
  - The app_l record has no regression test against its own `perf.json`.
- Fix: add a TP100 perf case and an engine-rows case; assert the row id set; add an app_l record-against-`perf.json` test.

### S3A-8 (should-fix). 7a21167: wording is right, but `conceptual/report.py` not being updated matters.

- The APL-4, 5, 6 and 8 texts in `raymer_propulsion.py`, `uav._thrust_fn` and the ledger are accurate. They match APL-4's f^(2/3) and quote no unrecorded sweep.
- `conceptual/report.py:296` and `:471` still say "capped at the momentum limit". Any regeneration, or the next app_l Stage 1 report, brings back the rejected wording and drops the judgement caveat.
- The hand-edited file also still carries the header "Generated by ... Every number is read from those files". The edit is disclosed in the file, which is honest but fragile.
- Fix: move the sentences into `report.py` behind the app_l branch, regenerate, and confirm the diff is text only.
- The ledger hash is now e04178026a08; no record carries it. That is fine (source text only), but the next run's hash will differ from the baseline's a869023c4431 for that reason. Say so in the next report.
- APL-6 is only half done: the band is called a judgement in the source text, but `confidence` still reads `published` and nothing lists it as an owner open item.

### S3A-9 (note). Baseline report method text is stale for app_l.

- The seed corners carry `eta_p`, which is inert. The first endurance corner therefore has a nominal propeller: iteration 1 gives W0 3,060 lb and a worst endurance of 2.974 h (read, `run.log`).
- The mode search then adds the f-low corner and the result converges with no violation, so the result is valid.
- The sentence "the directions of the ledger quantities carry over" is not true for the propeller. Map `eta_p` to `prop_real_to_ideal` in the seeds, or say it.
- The binding R7 mode changed from landing (1.605) to take-off (1.506) (read). The report does not remark on it.

### S3A-10 (note). Record hygiene.

- The 2026-11-26 Stage 3 records carry a commit and a command, but I found no dirty-tree flag in their `inputs`.
- The perf report prints "## Against an earlier record" twice with the same heading; label which is which.
- The VSPAERO cross-check (`docs/validation/2026-11-24_task12_vspaero_m250.md`) is on the old 3,117 lb baseline, not this one.

## Is the evidence enough for the Gate B performance report (spec 7.3, `docs/specs/task12_drone_conceptual_design.md:325`)?

Yes for writing it. Every input exists on the App. L baseline: engine, perf, aero, rotation and ground-effect records of 2026-11-26, and the info-gap study with its worst-case curve and the robust sizing of 2026-11-25. Margins (read):

| Item | Value | Requirement |
|---|---|---|
| R5 guarantee horizon | 1.051 | at least 1 |
| R7 horizon (take-off binds) | 1.506 | at least 1 |
| Cliff horizon | 1.178 | n/a |
| Take-off over 50 ft | 793 ft Stage 1, 803 ft Anderson | 2,500 ft |
| Landing over 50 ft | 1,419 ft Stage 1, 1,426 ft Anderson | 2,500 ft |
| Service ceiling | 29,350 to 29,748 ft | 23,000 ft |
| Sea-level climb | 2,636 ft/min | 1,000 ft/min |
| Power margin | 34.7 % | n/a |

A 7.4 "pass" cannot be claimed as written: "every requirement met by the independent measurement" does not hold for R5, R9, R12 and R13, which rest on coding checks, waivers or construction.

**Fix before Gate B (cheap, all text or regeneration):**
1. S3A-2 and S3A-3: correct the best-climb diagnosis and the rate-of-climb row, then regenerate the perf report.
2. S3A-4: reclassify the two rows.
3. S3A-8: put the APL wording into `conceptual/report.py`.
4. S3A-1: add the +43 lb decomposition as a recorded run.
5. Owner ruling on R13 (question 8 of the Stage 3 review is still open).
6. If the APL-5 take-off sweep over f is to be quoted, record it.

**Disclose as open items in the report:**
- R13 is met by layout construction with the shared lattice downwash. There is no independent neutral point; VSPAERO exists only for the old baseline and without a usable fuselage.
- No independent propeller check (G-4 plus G-5), including take-off and static thrust. f = 0.85 at low speed and the 0.80 to 0.90 band are judgements, and the robust W0 is sensitive to exactly that through the climb leg (S3A-1).
- Take-off power row -10.9 %: two models near zero climb gradient; not about installed power.
- CD0 -18.6 % (G-3): method resolves about ±20 %.
- Anderson W0 +125 % (G-2): explained, and not self-consistent with the disk (S3A-5).
- Rate of climb and best-climb speed: closed form not applicable with the disk; give the bracket.
- Engine:
  - 71.8 % of mission fuel is burned in unchoked cells.
  - The table is validated at sea level, 70 to 100 % power only.
  - The brochure rows cannot fail (G-6).
  - The MSH model reads 4.6 to 8.6 % low on fuel consumption against the book, with 2 of 18 rows outside (read).
  - R6 altitude and relight are assumptions (R-f), and the 23,000 ft ceiling is above the certified 20,000 ft.
- Not run or waived (G-5): SU2 polars and C_L,max (the 70 kt stall rests on the ledger's 1.35), gust second source, blade element.
- Span efficiency is not comparable as specified.
- Ground effect: within Raymer, outside Anderson; it does not decide rotation (G-7).
- R7 is unfactored (G-1).
- Mission fuel, the power rows, ceiling and corner speed are coding checks, not verifications.
- The climb leg is a two-point energy estimate (S3A-1).
- Info-gap exclusions as listed in the baseline report.

Files: `/home/user/ai-engineering/measurement/stage3_perf.py`, `/home/user/ai-engineering/measurement/stage3_engine.py`, `/home/user/ai-engineering/tests/task12/test_stage3_propeller.py`, `/home/user/ai-engineering/conceptual/report.py`, `/home/user/ai-engineering/docs/validation/2026-11-26_task12_stage3_perf_m250_appl.md`, `/home/user/ai-engineering/docs/validation/2026-11-25_task12_m250_baseline_appl.md`, `/home/user/ai-engineering/runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/`.

# Review: MD-3 to MD-7 fixes and the refined robust M250 baseline (2026-11-24)

Independent, read-only review (Fable) of two commits:

- ee68128: code fixes for MD-3 to MD-7 of `docs/reviews/2026-11-23_task12_m250_design_review.md`
  (power cap clipped at the rating, owner ruling R-e; one power-band default; report text).
- 4d6dac6: the refined robust run that the owner made the Task 12 baseline (ruling R-d).

No tracked file was changed and nothing was committed. The reviewer's probe scripts and their
outputs were kept in the session scratchpad and are not committed; every "probe" number below is
from those scripts, not from a run recorded in this repo. `pytest tests/task12` on 4d6dac6:
275 passed, 1 xfailed.

Records and reports reviewed:

- Baseline: `runs/task12/stage3/2026-11-23/m250_robust_105_refined` and
  `docs/validation/2026-11-23_task12_m250_robust_refined.md` (the report file is dated 2026-11-23).
- Regenerated in ee68128: `2026-11-23_task12_conceptual_m250.md`, `..._m250_robust.md`,
  `..._m250_robust_grid2.md`, each against its own record.
- Not regenerated: `2026-11-23_task12_m250_info_gap.md`.

## Verdict

**Passed with actions. The baseline numbers can be quoted; no run has to be repeated.**

In plain words:

- ee68128 does what MD-4 to MD-7 asked. The clip is right in the engine table, the TP100 records
  still rebuild exactly, the band form has one default taken from the record's engine, a
  contradicting form is refused, and the records state the form. No regression found.
- The refined run is clean. Every number in its report comes from its record, the report
  regenerates byte-identical, and the recorded design and its corner values rebuild to every digit.
- The W/S = 18 grid edge is real. A probe at W/S 18.25 to 19 and A 6 to 9 found nothing lighter
  than the recorded 3,116 lb. Above W/S 18.5 the transit cliff removes the A 6 and A 7 designs.
- Four things remain, none of which changes a quoted number:
  1. The baseline is the lightest by 0.3 to 2 lb over its neighbours, which is inside the 4 lb
     resolution of the grid, and it has the smallest cliff margin of the valley (cliff h 1.084)
     (MB-1).
  2. The clip does not reach the info-gap take-off row, which still uses 495 shp at +10 % (MB-2).
  3. The committed M250 info-gap report was not regenerated, so MD-3 is still open in that
     document (MB-3).
  4. The MD-1 erratum is missing. A draft is below (MB-4).

## What holds

**The clip (MD-4, ruling R-e)**

- `TableEngine.power_available` returns min(rated x power_scale, min(rated, table) x power_scale x
  cap).
- Probe, M250 table: 5,880 points (altitude -1,000 to 26,000 ft, speed 0 to 200 kt, cap 0.5 to
  2.0). The largest available power is 450.0 shp. Every value equals min(450, cap x uncapped
  value). For every cap below 1 the value is exactly cap x the uncapped value, so a cap below 1
  still cuts power.
- With `power` (rescale) and `rerate` the limit moves with `power_scale`, as it should: the clip
  never acts for cap = 1 (probe: TP100 with power 0.9 to 1.5, both rerate settings).
- The clip changed nothing in the sizing. The iteration 2 cells of the refined run equal the
  reviewer's earlier probe values, made before the clip, in every digit (W/S 18, A 7:
  3,115.9895485745133 lb; W/S 18, A 8: 3,136.5733682637074 lb).
- The older M250 robust records rebuild under the clipped code: the one-at-a-time power rows, the
  worst points and the corner values of `m250_robust_105` and `m250_robust_105_grid2` are equal to
  the records in every digit.

**TP100 "rescale" records still rebuild exactly**

- `runs/task12/stage1/2026-11-21f`: default form rescale, rebuild check passes (fuel
  1,065.3534932862146 lb both sides).
- `runs/task12/stage3/2026-11-22/info_gap.json`: engine rows rebuild to the same digits as before
  the commit (9.62383 / 6.67148 h and 8.48666 / 7.54168 h; the sixth-digit difference is the one
  reported in the first review and is older than both commits).
- `curve_targets_v2` at 420 and 450 hp: worst-point hours rebuild exactly (3.503640327566754 and
  3.500493560806026 h). Sized again from scratch: W0 4,490.652016715837 and 4,557.564908450865 lb,
  equal to the records in every digit.

**Band form (MD-5)**

- One default: `Built(power_band=None)`, `study(power_band=None)` and the command line
  (`--power-band` default None) all take the form from the record's engine table (M250 cap, TP100
  rescale). The module global is gone. `robust_sizing.power_band()` reads the same dictionary.
- Refusal checked on real records: cap on the TP100 Stage 1 record and on a photo-scaled TP100
  record is refused; rescale on the M250 Stage 1 record and on the refined record is refused. The
  override flag works.
- The refined record states the form in `curve.json` (inputs), `target_result.json`, all three
  `robust_candidate.json` files and `info_gap.json` (which also names the engine, 450 shp,
  allowance 1.02 and 2,030 rpm). All say cap.

**Committed reports against their records (`git show ee68128 -- docs/`)**

- The Stage 1 M250 report and both older robust reports regenerate byte-identical from their own
  records with the committed code. Only text changed in the commit; no number moved.
- The new Stage 1 lines are from records: R5 guarantee h 0.933 is `m250_info_gap/info_gap.json`
  (0.93347), and that record's design file is byte-identical to the Stage 1 design file.
- MD-6: the summary now says "R6 not checked (no source)". MD-7: the headline says the design is
  sized without margin and misses Gate B; the allowance row follows the ledger (x1.02); "3127 to
  3127 lb" is gone; the Stage 1 report names 72bbec7 as the code as run.
- The first robust report now lists the errored candidate W/S 19, A 8 with its error.

**The refined run (4d6dac6)**

- Run on ee68128 with a clean tree apart from its own output folder. Ledger, engine table and
  seed-corner hashes in the record equal the committed files. The reflog shows no reset or other HEAD
  movement between 22:53 (ee68128) and 01:03 (4d6dac6) and the stash list is empty, so nothing like the MD-1 stash happened. All 12
  candidates of the last iteration are classified; none ended in an error.
- The report regenerates byte-identical from `curve.json`. The cell in `curve.json` equals
  `target_result.json`.
- Report against record:

| Quantity | Report | Record |
|---|---|---|
| W0, W/S, A | 3116 lb, 18, 7 | 3,115.990 lb, 18, 7 |
| Span, fuel, L_sized | 34.8 ft, 977 lb, 8.84 h | 34.811 ft, 977.306 lb, 8.84375 h |
| V_C, power margin | 120 kt, 33.4 % | 120 kt (fastest step 106.65 kt), 0.3344 |
| Endurance h, cliff h | 1.05, 1.08 | 1.05115, 1.08374 |
| R5 guarantee h, R7 h | 1.05, 1.51 | 1.05121, 1.51447 (landing; take-off 1.65363) |
| Worst endurance, worst cliff ratio at h_T | 3.51 h, 0.97 | 3.50647 h, 0.97219 |
| Unchoked fuel share | 66.4 % | 0.66427 |
| Step bias, W0 and fuel | +0.9, +0.6 lb | +0.903, +0.581 lb |
| Grid table (12 cells) | as printed | iteration 2 candidates, all equal |

- The ledger copy differs from the committed ledger only in `loiter_h` (8.84375), the fixed V_C
  (120 kt) and the removed V_C rule. All three table copies have the committed hash.
- The recorded design rebuilds: the probe re-size of W/S 18, A 7 against the recorded corner sets
  gives 3,115.9895485745133 lb. The corner hours (3.6150, 3.5065 h), the cliff ratio (0.97219),
  the one-at-a-time power rows and the worst point at h_hat (3.50006 h) are equal to the record.
- The final corner sets (two endurance, one cliff) are the same three corners as in the two older
  M250 runs.

**Worst points beyond the corners (probe)**

- 150 random members, 150 random corners and 150 points with one to five variables flipped off
  the worst corner, at h = 1.05 and again at h = 1.0512. No point was unflyable, none needed more
  than the record's fuel for 3.5 h (largest 976.64 lb at 1.05 and 977.29 lb at 1.0512, against
  977.31 lb), and none had a cliff ratio above 1.
- Five coordinate searches from random corners (three endurance, two cliff) at h = 1.05 all end
  at the recorded worst points: 3.50647 h and cliff ratio 0.97219.
- Cliff mode: along the recorded cliff direction the ratio is 0.97219 at h = 1.05, 0.99995 at
  1.0837 and 1.00164 at 1.0857. No single flip raises it. Over 274 points per level (single
  flips, 120 multi-flips, 100 random corners) none is above the recorded direction. The cliff h
  of 1.084 holds.

**The W/S = 18 edge (probe)**

Lightest compliant W0 (lb) at h_T = 1.05 against the recorded corner sets. "rec" is a recorded
cell of the refined run; the others are probe values, sized against the corner sets only (no
mode search), and are not recorded runs. The number in brackets is the cliff ratio at h_T.

| A \ W/S | 18 | 18.25 | 18.5 | 18.75 | 19 |
|---|---|---|---|---|---|
| 6 | none rec | | none (cliff at 8 h) | | none (cliff at 8 h) |
| 6.5 | 3,116.3 (0.988) | | | | |
| 7 | 3,116.0 rec (0.972) | 3,118.7 (0.984) | 3,117.8 (0.994) | none | none |
| 7.5 | 3,129.1 (0.964) | | 3,126.4 (0.983) | | |
| 8 | 3,137 rec (0.954) | | 3,133.0 (0.974) | | 3,130.4 (0.993) |
| 9 | | | | | 3,147.9 (0.979) |

- Nothing at W/S 18.25 to 19 is lighter than 3,116.0 lb. At A 7 the weight rises slightly with
  W/S at the same L_sized (fuel 977, 982, 985 lb at W/S 18, 18.25, 18.5) and the cliff removes
  the design between W/S 18.5 and 18.75. At A 6 the cliff removes it already at W/S 18. At A 8
  designs survive to W/S 19 but are 14 to 21 lb heavier.
- W/S 19, A 9 reproduces the first run's recorded cell (3,147.86 lb).

**W/S 18, A 6 has no design: plausible**

- The record shows why. At L = 8.53125 h the cliff ratio is 0.99958 and the new endurance corner
  gives 3.369 h. One lattice step up, at 8.5625 h, the cliff ratio is 1.00054. Endurance needs
  about 8.75 h (as at W/S 17, A 6), which is beyond the cliff. So no L exists.
- The reviewer's earlier probe, before the clip, gave the same result.
- In iteration 1 this same candidate was the lightest (3,087 lb) with one endurance corner. Its
  mode search found the second endurance corner, and iteration 2 then removed it. That is the
  loop working as designed.

**W/S 16, A 6 unresolved in iteration 1: fine**

- In iteration 1 the weight iteration did not converge at L = 8.5625 h (first guess 4,479 lb, no
  retry by rule RC2-6). The candidate was marked unresolved, not heavy or light.
- In iteration 2 the bisection took another path (8.5 small, 8.75 ok, 8.625, 8.6875 and 8.71875
  small) and never visited 8.5625 h. All nine points closed. The answer is bracketed on the
  lattice: 3.4987 h at 8.71875 h, 3.5175 h at 8.75 h. The cell (3,131 lb) is valid.
- Iteration 1 only serves to find new corners. The result rests on iteration 2, where the mode
  searches found no violation. The missing candidate in iteration 1 cannot change that.
- The hole itself is still there at L = 8.5625 h for this candidate (MB-6).

## Findings

| ID | Severity | Finding | Fix |
|---|---|---|---|
| MB-1 | medium, judgment | **The baseline is the lightest by less than the resolution, and it has the least cliff margin.** W/S 18, A 7 (3,116.0 lb) beats W/S 16, A 7 (3,116.9 lb) by 1 lb and the probe point W/S 18, A 6.5 by 0.3 lb. The lattice step is worth about 4 lb and the valley is flat within 25 lb (3,116 to 3,140 lb over 11 cells). The design sits next to the cliff: cliff ratio 0.972 at h_T and cliff h 1.084, against 1.16 (W/S 17, A 8) and 1.21 (W/S 15, A 6) in the older records. W/S 16, A 7 has a cliff ratio of 0.887 at h_T for 1 lb more. The cliff is a hard failure (the mission cannot be flown), not a shortfall of hours. The run is correct; this is about which cell to freeze. | Quote "about 3,120 lb". Owner to confirm R-d with the cliff margin in view. If margin matters more than 1 lb, run the mode study on W/S 16, A 7 (about 30 minutes) and compare cliff h. |
| MB-2 | low | **The clip does not reach the info-gap take-off row.** `info_gap.field_detail` multiplies the rated bhp by the power multiplier itself (`uav._takeoff` does not use the table), so at +10 % take-off uses 495 shp. In the refined record the one-at-a-time take-off row is 731.4 / 689.0 ft at x0.9 / x1.1 against 707.9 ft nominal; under R-e the x1.1 end should equal the nominal. Random members with a multiplier above 1 have the same optimism. **No h_hat changes:** the take-off worst point has the multiplier at 0.835 (its harmful end), and R7 h = 1.514 is set by landing. The sentence "a multiplier above 1 cannot take the available power above the rated power" in `info_gap.engine_lines` is not true for this row. | For the cap form use bhp x min(1, multiplier) in `field_detail`; add a test. No re-run needed for any quoted number. |
| MB-3 | medium, carried | **MD-3 is still open in the committed document.** `2026-11-23_task12_m250_info_gap.md` was not regenerated (its record has no engine field), so it still quotes 0.9335, 1.60 and 1.39 with no engine, allowance or validation caveat, and the cliff h of 1.002 is still in no report. The code fix only acts on records made from ee68128 on. | Either run `info_gap` again on the Stage 1 record (the new record carries the engine; say that the favourable take-off end changes with MB-2), or let `report_text` read the engine from the design record. Lower priority now that the Stage 1 point is not the baseline. |
| MB-4 | low | **No erratum for MD-1, and the three robust reports do not refer to each other.** The first report lists the errored candidate but not its cause. Each of the three reports says "lightest" (3,127, 3,120, 3,116 lb) with no pointer to the others. The refined report does not say that it is the baseline. Rulings R-d and R-e are in commit messages and one docstring only, not in `docs/specs/` or the ledger. | Commit the erratum below. Record R-d and R-e where the other Task 12 rulings are kept. |
| MB-5 | low | **Report text on the clip.** MD-4 asked for the clip to be stated in the reports. The robust report says "cap" but not "clipped at the rating". The info-gap engine line prints the clip sentence for every record with an engine field, also for a rescale (TP100) record, where it does not apply. | Add one sentence to the robust report's engine paragraph. Print the clip sentence only when the form is cap. |
| MB-6 | low, latent | **A convergence hole stays in the weight iteration.** W/S 16, A 6 at L = 8.5625 h with first guess 4,479 lb does not converge. It did not matter here (see above). If the bisection of a later run lands on it in the last iteration, the cell will be unresolved. | No action for this run. If it recurs, look at that point directly rather than changing the guess rule. |
| MB-7 | low | **Text and hygiene left over.** (a) The grid table says "too heavy above it" for W/S 18, A 6; the record shows the cause is the cliff corner (ratio 1.0005 at 8.5625 h). (b) The two older robust reports still give commit 93a36f9 plus a dirty tree and do not name 72bbec7 (MD-7 was applied to the Stage 1 report only). (c) The MD-1 hygiene fix (read ledger and table once, check the hashes at the end) is not in the code; the refined run was clean by evidence, not by a check. (d) `robust_sizing --modes` on an M250 record without `--engine-as-is` now uses the right form (cap) but its `inputs` block would still describe the photo-scaled TP100. (e) `info_gap.main` reads any `modes.json` beside `--out` as "the same record" without comparing the design path. | (a) Use the trace's last heavy reason. (b) Pass `committed_after` when they are next regenerated. (c) Add the end-of-run hash check. (d), (e) Take the labels from the record; compare the design path. |

Not a regression: regenerating the TP100 info-gap report of 2026-11-22 fails with
`KeyError: 'band_weight'`. The same line is in the parent commit; that record is older than the
key.

## Draft erratum for MD-1

Text for the owner to commit here. It applies to
`docs/validation/2026-11-23_task12_m250_robust.md` and to the record
`runs/task12/stage3/2026-11-23/m250_robust_105`. The report is generated, so the erratum is kept
in this review and not typed into the report.

> **Erratum, 2026-11-24: one candidate of `m250_robust_105` was lost to a working-tree stash.**
>
> - What happened. A `git stash` was made at 20:09:51 on 2026-11-23, while iteration 2 of the run
>   was going (it began at 20:05:13). The sizing workers read `data/task12/ledger.yaml` from the
>   working tree for every candidate. For a short time they read the file as committed at 93a36f9,
>   which had the TP100 values (SFC allowance 1.05, 2,158 rpm) and not the M250 values (1.02,
>   2,030 rpm).
> - What was lost. One candidate, W/S 19, A 8. It ends in iteration 2 with "error: rebuild does
>   not reproduce the record: fuel_lb 975.0694933491487 against 999.8326520140836" (logged at
>   20:10:19). In iteration 1 it was the second lightest candidate (3,109.7 lb at L 8.78 h,
>   against 3,106.5 lb for W/S 17, A 8).
> - What the report says. As regenerated at ee68128 the report counts 1 errored candidate and
>   lists it with its error. It does not give the cause. The first version of the report said
>   "Unresolved candidates: 0". The record's `git_dirty` lists do not show the stash.
> - The winner of that run stands. A reviewer's probe re-sized W/S 19, A 8 against the run's
>   final corner sets and got L_sized 8.9375 h and W0 3,130.4 lb. That is above the recorded
>   winner (W/S 17, A 8, 3,126.7 lb). The probe is not a recorded run; its script and output were
>   kept outside the repo. A second probe on the committed code of ee68128 (clipped cap) gave the
>   same value, 3,130.4 lb.
> - No other candidate is affected as far as the record shows: every other candidate of both
>   iterations is classified, and the recorded winner rebuilds from the committed code to every
>   digit (3,126.668243003735 lb).
> - Status of the run. `m250_robust_105` (3,127 lb) and `m250_robust_105_grid2` (3,120 lb) are
>   superseded as the Task 12 baseline by `m250_robust_105_refined` (W/S 18, A 7, 3,116 lb; owner
>   ruling R-d). The refined grid stops at W/S 18 and does not contain W/S 19, A 8; the 3,130.4 lb
>   above is the only value for that cell and it is a probe value.
> - Rule from now on: no stash, checkout or branch switch while a run is going.

## Owner questions

1. R-d with the cliff margin in view (MB-1): keep W/S 18, A 7 (3,116 lb, cliff h 1.084), or take
   a cell further from the cliff for about 1 lb, such as W/S 16, A 7 (3,117 lb, cliff ratio 0.887
   at h_T, cliff h not yet measured)?
2. Should the take-off row follow R-e as well (MB-2)? No guarantee changes either way.
3. Is the Stage 1 info-gap report worth a re-run now that the Stage 1 point is not the baseline
   (MB-3), or is a pointer to this review enough?
4. Where should rulings R-d and R-e be written down (MB-4)?
5. Still open from before: a source for the M250-B17F altitude and relight envelope (R6), and
   part-power and altitude fuel-flow data (66 % of the baseline's mission fuel is burned in
   unchoked table cells, and all of it after take-off in unvalidated ones).

## Numbers that may be quoted

Always with the caveat: the engine model is checked at sea level, 70 to 100 % power only; the SFC
band of ±10 % stands in for the missing data.

- **Baseline (ruling R-d), robust size at h_T = 1.05:** W0 3,116 lb, W/S 18, A 7, span 34.8 ft,
  fuel 977 lb, sized loiter 8.84 h, V_C 120 kt EAS, power margin 33.4 %. R5 guarantee h 1.051,
  endurance h 1.051, cliff h 1.084, R7 h 1.514 (landing; take-off 1.654). Unchoked fuel share
  66.4 %. Sub-step bias +0.9 lb.
- **As a weight, quote "about 3,120 lb":** the valley is flat (3,116 to 3,140 lb over W/S 15 to
  18, A 6 to 8) and the grid resolves about 4 lb. That is about 115 lb (4 %) above the Stage 1
  point (3,001 lb, R5 guarantee h 0.933).
- **The edge:** no lighter design at W/S 18.25 to 19 (probe values, not recorded runs); the
  transit cliff removes A 6 at W/S 18 and A 7 between W/S 18.5 and 18.75.
- **Older robust records:** W/S 17, A 8 at 3,127 lb and W/S 15, A 6 at 3,120 lb stay valid as
  cells of the same valley and are superseded as the baseline.
- **TP100 records:** unchanged.

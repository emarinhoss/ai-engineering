# Review: pusher re-sized around the RR M250-B17F (2026-11-23)

Independent, read-only review (Fable) of commit 72bbec7 against its parent 93a36f9. No tracked
file was changed and nothing was committed. The reviewer's probe scripts and their outputs were
kept in the session scratchpad and are not committed; every "probe" number below is from those
scripts, not from a run recorded in this repo. `pytest tests/task12` on the committed tree:
269 passed, 1 xfailed.

Records and reports reviewed:

- Stage 1: `runs/task12/stage1/2026-11-23`, `docs/validation/2026-11-23_task12_conceptual_m250.md`
- Engine v2: `runs/task12/stage3/2026-11-23/m250_engine_v2`, `..._m250_engine_v2.md`
- Info-gap: `runs/task12/stage3/2026-11-23/m250_info_gap`, `..._m250_info_gap.md`
- Robust sizing at h_T = 1.05: `.../m250_robust_105` and `.../m250_robust_105_grid2`,
  `..._m250_robust.md` and `..._m250_robust_grid2.md`

## Verdict

**Passed with actions. The numbers can be quoted; no run has to be repeated.**

In plain words:

- The commit does what the three rulings ask. The M250-B17F is the chosen engine, the allowance is
  1.02, and the power band is a cap. The cap reached every worker.
- The TP100 records still rebuild with their own values (1.05, 2,158 rpm, rescale).
- Every number in the five reports comes from its record. The recorded designs rebuild from the
  committed code to every digit.
- The two robust guarantees (1.053 and 1.051) hold up under a wider search.
- Three things need fixing, all in reporting or run hygiene, none in the results:
  1. A `git stash` during the first robust run cost that run one candidate. The report does not say
     so. The winner is not affected (MD-1).
  2. The robust optimum sits in a flat valley, and both recorded grids found it at their lower
     corner. The quoted weight depends on the grid by about 10 lb. Quote "about 3,120 lb" (MD-2).
  3. The info-gap report quotes h_hat without the "engine model unvalidated" caveat (MD-3).
- A cap above 1 gives more than the 450 shp rating at sea level. That is not physical, but it
  changes no recorded number (MD-4).

## What holds

**Rulings**

- **R-a.** `stage1.CHOSEN_ENGINE` is `RR_M250_B17F`. Every M250 record names the engine, 450 hp,
  212 lb and the table hash `114b0e0f...`, which is the committed table.
- **R-b.** The ledger and every M250 ledger copy carry `engine_sfc_allowance` 1.02 and
  `propeller_rpm` 2,030. The engine model's SFC scale is 1.02.
- **R-c.** SFC ±10 % is applied on top of the allowance. The power band is a cap on available
  power, and SFC at a given shaft power does not move with it (probe: 0.6333 at 20,000 ft, 120 kt,
  150 shp for caps 0.9, 1.0 and 1.1).

**The cap reached the workers (point 2)**

- `robust_sizing.use_engine_as_is` and `info_gap.study` set the module's `POWER_BAND` before the
  pools fork, so the workers inherit it.
- Checked by number, not by reading. For all three design records the recorded one-at-a-time rows
  rebuild with an explicit `power_band="cap"` and not with `"rescale"`:

| Record | Recorded hours at power x0.9 / x1.1 | Cap (probe) | Rescale (probe) |
|---|---|---|---|
| Stage 1 design | 7.9567 / 8.0148 | 7.9567 / 8.0148 | 8.4366 / 7.6038 |
| Robust, W/S 17, A 8 | 8.8308 / 8.8893 | 8.8308 / 8.8893 | 9.3863 / 8.4144 |
| Robust, W/S 15, A 6 | 8.6073 / 8.6736 | 8.6073 / 8.6736 | 9.1485 / 8.2095 |

- The sizing workers' corner values also rebuild with the cap only (W/S 17, A 8: 3.6012 and
  3.5141 h, cliff ratio 0.9057; rescale would give 3.3651 and 3.8016 h).
- `curve.json`, `info_gap.json` and `modes.json` state `power_band: cap`. The reports say "cap".

**TP100 reproducibility (point 3)**

- `runs/task12/stage1/2026-11-21f`: the ledger copy has 1.05 and 2,158 rpm. The rebuild check
  passes (fuel 1,065.3535 lb both sides). Sized again from scratch with today's code it gives
  W0 3,354.891 lb (record 3,354.891).
- `runs/task12/stage3/2026-11-22/info_gap.json`: with `rescale`, hours at SFC x0.9 / x1.1 are
  9.62383 / 6.67148 (record 9.62384 / 6.67148) and at power x0.9 / x1.1 8.48666 / 7.54168 (record
  8.48667 / 7.54169). The difference in the sixth digit is older than this commit: the parent
  commit's code gives the same digits as today's.
- `curve_targets_v2` at 420 and 450 hp: re-sized today W0 is 4,490.652016715837 and
  4,557.564908450865 lb, equal to the records in every digit. The ledger copies regenerate
  byte-identical. The worst-point hours rebuild exactly (3.50364 and 3.50049 h).
- The TP100 Stage 1 report regenerates with the same numbers. Four text lines differ (wording
  only; the old text said "allowance x1.00 applied", the new says 1.05).

**Unchoked fuel share (point 4)**

- The share is the fuel burned in unchoked sub-steps over the fuel burned from take-off to the end
  of the last cruise. Recomputed from the mission rows of each record:

| Design | Unchoked / burned (lb) | Share | Where |
|---|---|---|---|
| Stage 1, W/S 21, A 8 | 561.8 / 856.8 | 65.6 % | loiter 523 of 523, cruise back 39 of 131 |
| Robust, W/S 17, A 8 | 677.0 / 884.4 | 76.6 % | loiter 541 of 541, cruise back 136 of 136 |
| Robust, W/S 15, A 6 | 564.6 / 892.9 | 63.2 % | loiter 537 of 537, cruise back 28 of 141 |

- The loiter (about 60 % of the burn) is always unchoked. The cruise legs sit at about half
  power, which is where the table crosses the critical ratio, so the share moves between 63 and
  77 % as cruise-back steps fall either side. It is a threshold count, not a smooth measure.
- All fuel after take-off (97 %) is outside the validated range, because the validation is at sea
  level only. The Stage 1 and robust reports say this.
- The caveat is clear in the Stage 1 report (status paragraph and summary) and in both robust
  reports (header, own section, limits). It is missing from the info-gap report (MD-3).

**Robust guarantees (point 5)**

- Recorded R5 guarantee h: 1.0527 (W/S 17, A 8) and 1.0508 (W/S 15, A 6). The recorded worst
  points rebuild exactly (3.50055 and 3.50065 h at h_hat).
- Probe, per design: 150 random members, 150 random corners and 150 points with one to five
  variables flipped off the worst corner, at h = 1.05 and again at h_hat. No point was unflyable,
  none needed more than the record's fuel for 3.5 h, and none had a cliff ratio above 1.
- Probe: five coordinate searches per design from random corners (three endurance, two cliff) at
  h = 1.05 all end at the recorded worst points: 3.5137 h and cliff ratio 0.906 (W/S 17, A 8);
  3.5046 h and 0.880 (W/S 15, A 6).

**Stage 1 against the robust re-size (point 6)**

- The Stage 1 design (L = 8.0 h) has an R5 guarantee of 0.933 and a cliff at h = 1.002.
- The robust run rejects W/S 21, A 8 at h_T = 1.05 because the cliff corner cannot be flown. That
  agrees with a cliff at 1.002.
- At W/S 17, A 8 the guarantee is 1.053 with L = 8.875 h. That is 0.137 of h per hour of sized
  loiter, the same slope as the TP100 study (0.13 per hour). The two results are consistent.

**Records and reports (point 7)**

- The Stage 1, info-gap and both robust reports regenerate byte-identical from their records. The
  engine v2 report differs only in list brackets on one line.
- The Stage 1 design sized from scratch with the committed code gives W0 3,001.1320 lb (record
  3,001.1325) and the same unchoked share.
- R6 is stated as absent, not invented: both R6 rows are notes ("no starting envelope in our
  sources", "no maximum operating altitude in our sources (not checked, none invented)").
- Every M250 ledger copy differs from the committed ledger only in `loiter_h`, the fixed V_C and
  the removed V_C rule. Every table copy has the committed hash.
- The dropped stash commit (247d464, 20:09:51) differs from 72bbec7 in report text only, so the
  code that ran is the committed code.

## Findings

| ID | Severity | Finding | Fix |
|---|---|---|---|
| MD-1 | medium | **The stash leaked into the first robust run.** The stash was made at 20:09:51, inside iteration 2 of `m250_robust_105` (20:03 to 20:13). The workers read `data/task12/ledger.yaml` from the working tree for every candidate, so for a short time they read the TP100 values. One candidate was lost: W/S 19, A 8 ends with "error: rebuild does not reproduce the record: fuel_lb 975.07 against 999.83". In iteration 1 it was the second lightest (3,109.7 lb). The report says "Unresolved candidates: 0" and does not list the error. The `git_dirty` lists do not show the stash. **The winner stands:** a probe re-size of W/S 19, A 8 against the final corner sets gives L 8.9375 h and 3,130.4 lb, above the recorded 3,126.7 lb. The rebuild check caught this only because the allowance changed; an edit to another ledger value during a run would pass silently. | Add a note to the record and report. List errored candidates in the report. Read the ledger and table once at the start of a run and check their hashes again at the end. Do not stash or switch branches while a run is going. |
| MD-2 | medium | **The quoted W0 depends on the grid by about 10 lb.** Both recorded optima are at the lower corner of their grid (W/S 17, A 8; then W/S 15, A 6). Probe re-sizes with the recorded corner sets (table below) find 3,116 lb at W/S 18, A 7 and 3,117 lb at W/S 16, A 7, below the recorded "lightest" 3,120 lb. The valley is flat: 3,116 to 3,137 lb over W/S 15 to 18, A 6 to 8. It is bounded: A 5 and W/S 14 or less are heavier, and from W/S 18 to 19 upward the transit cliff removes designs. The 1/32 h lattice alone is worth about 4 lb. Neither robust report mentions the other. | Quote "about 3,120 lb". State the resolution. Mark the first report's "lightest" as superseded. If one design is to be frozen, run one grid over W/S 14 to 19, A 5 to 8. |
| MD-3 | medium | **The info-gap report quotes h_hat with no caveat.** `2026-11-23_task12_m250_info_gap.md` gives 0.9335, 1.60 and 1.39 without naming the engine, the 1.02 allowance, the unchoked share or the validation limits. The cliff h of 1.002 (`modes.json`) is in no report. | Add an engine paragraph to `info_gap.report_text` (engine, allowance, unchoked share, validated range). Report the two mode values. |
| MD-4 | low | **A cap above 1 exceeds the rating at sea level.** With cap 1.10, available power is 489 to 495 shp against the 450 shp rating, which is a gearbox and torque limit. At 20,000 ft it is 217 to 226 shp, below the rating, which is a fair reading of an uncertain thermal limit. **No recorded number changes.** Every recorded worst point has the multiplier below 1. Hours rise steadily with the multiplier (3.49 to 3.59 h from 0.895 to 1.2 at the Stage 1 worst point). With the cap clipped at the rating, hours and cliff ratios are identical to six decimals for all three records, and the Stage 1 +10 % trade stays at 2,999.2 lb. Only the favourable end of the info-gap take-off row (757.5 ft at +10 %) uses 495 shp. The seed endurance corner carries 1.105, its harmless end under the cap; the binding corner is the one the mode search added (0.895). | Clip: available = min(rating, table x cap). Say so in the docstring and reports. No re-run needed. |
| MD-5 | low, latent | **The band form is a module global with two defaults.** `info_gap.study()` defaults to rescale; the command line defaults to cap. Nothing checks the form against the record's engine, so a TP100 record run from the command line without `--power-band rescale`, or an M250 record run through `study()` or `--modes` without `--engine-as-is`, would silently use the wrong form. `target_result.json`, `robust_candidate.json` and the iteration folders do not state the form. No existing record is affected. | Take the form from the record's engine and refuse a mismatch. Write `power_band` into `target_result.json`. |
| MD-6 | low | **R6 is unchecked, but the summary reads as a clean pass.** "19 checked rows met, 0 not met" does not say that the R6 altitude row moved from a check to a note for this engine. | Add "R6 not checked: no altitude or relight data in our sources" to the summary line. |
| MD-7 | low | **Text.** The Stage 1 report's headline 3,001 lb does not say that this design misses the Gate B R5 guarantee (0.933) and that the robust size is about 3,120 lb. Its history table still says "SFC allowance 5 %". The robust summary reads "designs from 450 hp up (W0 3127 to 3127 lb)" and plots one point. The reports give commit 93a36f9 plus a dirty tree and do not name 72bbec7 as the code as run. | Edit the text. Use the `committed_after` sentence the report function already takes. |

Probe for MD-2: lightest compliant W0 (lb) at h_T = 1.05 against the recorded final corner sets.
"rec" is a recorded cell; the others are probe values and are not recorded runs.

| A \ W/S | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 |
|---|---|---|---|---|---|---|---|---|
| 4 | | | 3,205 | | | | | |
| 5 | | 3,162 | 3,140 | 3,150 | 3,144 | none (cliff) | | |
| 6 | 3,190 | 3,150 | 3,140 | 3,120 rec | 3,131 | 3,122 rec | none | none rec |
| 7 | | | | 3,134 rec | 3,117 | 3,124 rec | 3,116 | none rec |
| 8 | | | | | | 3,127 rec | 3,137 | 3,130 (rec: error, MD-1) |

The probe reproduces the two recorded winners exactly (3,126.668243003735 and
3,120.2363390860314 lb).

## Owner questions

1. Should the cap be clipped at the 450 shp rating (MD-4)? No number changes either way.
2. Which design is the baseline now: the Stage 1 point (3,001 lb, misses the Gate B R5 guarantee)
   or the robust size (about 3,120 lb)? If the robust one, which point of the valley? W/S 15, A 6
   has span 35.3 ft and cliff h 1.21; W/S 17, A 8 has span 38.4 ft and cliff h 1.16.
3. Is there an open source for the M250-B17F's maximum operating altitude and relight envelope?
   Until then R6 stays open.
4. Still open from the engine review: part-power and altitude fuel-flow data. Until they exist,
   63 to 77 % of the mission fuel rests on unchoked table cells and all of it after take-off on
   unvalidated ones.
5. Is a note enough for the candidate lost to the stash (MD-1), or should the first grid be run
   again in one piece (about 70 minutes)?

## Numbers that may be quoted

Always with the caveat: the engine model is checked at sea level, 70 to 100 % power only; the SFC
band of ±10 % stands in for the missing data.

- **Stage 1 (8 h mission, no robustness margin):** W0 3,001 lb, W/S 21, A 8, span 33.8 ft, fuel
  920 lb, empty 1,582 lb. SFC ±10 % moves W0 to 2,842 and 3,187 lb; the power cap ±10 % to 3,007
  and 2,999 lb. Unchoked fuel share 65.6 %. R5 guarantee h 0.933 (below 1), cliff h 1.002, R7 h
  1.39.
- **Robust size at h_T = 1.05:** about 3,120 lb, flat within about 10 lb over W/S 15 to 18, A 6
  to 8. That is about 120 lb (4 %) above Stage 1.
  - W/S 15, A 6: 3,120 lb, fuel 958 lb, L 8.66 h, R5 guarantee 1.051, cliff h 1.21, R7 h 1.66,
    unchoked share 63.2 %.
  - W/S 17, A 8: 3,127 lb, fuel 949 lb, L 8.88 h, R5 guarantee 1.053, cliff h 1.16, R7 h 1.56,
    unchoked share 76.6 %.
- **TP100 records:** unchanged.

# Review: W0 against power at fixed robustness targets (2026-11-23)

Independent read-only review (Fable) of commits 82ec2d1 and 8507aba. The run is
`runs/task12/stage3/2026-11-23/curve_targets/` and the report is
`docs/validation/2026-11-23_task12_robustness_curve_targets.md`. The reviewer's run of
`pytest tests/task12` gave 243 passed, 1 xfailed. The probe scripts were kept in the session
scratchpad and are not committed.

## What holds

- `per_design_vc_kt` applies the ruling's rule and rounding correctly.
- Moving the mission before the loads changes nothing for the fixed rule. The old records
  rebuild to every digit.
- Every record's ledger copy fixes V_C at 110 or 115 kt. The effective-rule fix in 8507aba
  changes no recorded result.
- The scaled corners are the worst points found at h_T:
  - The mode searches added a violating point only at 450 hp, h = 1.00 (+8 lb).
  - 220 random members of U(1.05) at 420 and 435 hp found nothing worse.
  - The R5 guarantee h is 1.051 to 1.054 at all five powers.
- The report matches the records byte for byte. The dirty-tree statement is accurate.

## Findings

| ID | Severity | Finding | Fix |
|---|---|---|---|
| FT-1 | major | The 5 kt V_C step inside the weight iteration makes the iteration limit-cycle. In 23 of 358 bisected rows, "did not converge" was read as "heavy". Two recorded cells are wrong: 480 hp at h 1.10 should be 4,794 lb (recorded 4,856), and 435 hp at h 1.00 should be 4,333 lb (recorded 4,348). The h = 1.05 column is unchanged (+1 lb at most). | Size at a fixed V_C, then step it up by 5 kt until the rule holds. Report "did not converge" as unresolved, never as heavy. Re-run the h 1.00 and 1.10 columns. |
| FT-2 | medium | The dip at 435 hp is grid granularity. 420 and 435 hp are equal to within about 20-30 lb (off-grid probes reach 4,472-4,473 lb). 400 hp is about 30 lb heavier, 450 hp about 70-85 lb heavier and 480 hp about 150 lb heavier. | State the resolution in the report. Refine the grid if the ranking matters. |
| FT-3 | medium | The 360-370 hp no-design cells are real. 380 hp has a design that meets both corners (W/S 10, A 8, L 9.28 h, 4,673 lb) but fails the R9 negative-gust row (-1.788 against -1.70). The boundary lies between 390 and 400 hp. The 400 hp design sits on the cliff, gust and endurance limits at once. | Name the R9 row in the report. Extend the grid down to W/S 10. |
| FT-4 | medium, latent | After 8507aba, `sized_aircraft` and `write_record` can write a record ledger that still says `vc_placard_rule: per_design`. An info-gap study of such a record would let each member pick its own V_C. No existing record is affected. | Route these paths through `built_ledger_values`. `info_gap.Built` refuses a ledger that still carries the rule. |
| FT-5 | low | Ledger and report text say "the file keeps fixed". The inputs line does not name commit 82ec2d1. The heavy and unflyable labels depend on the order of the trace. The ruling says "cruise sub-step" where the code says "mission sub-step". | Edit the text. |

## Owner questions raised

1. Should V_C use a 5 kt lattice or a continuous rule? The lattice costs up to about 21 lb.
2. Should the 0.1 g gust margin stay a hard row? It decides the 380 hp cell.
3. Still open: no real engine is shown to have the TP100-like SFC assumed.

## Verdict

The h = 1.05 column can be relied on, with the actions above. The h 1.00 and 1.10 columns
cannot be used until FT-1 is fixed and the run repeated.

Class to quote at h = 1.05:

- 420-450 hp, W0 about 4,470-4,560 lb.
- 420-435 hp: about 4,470-4,490 lb, equal within resolution. Cliff h is 1.05 at 420 hp and
  1.07 at 435 hp.
- 450 hp: about 4,540-4,560 lb, cliff h 1.10.
- 400 hp is the minimum power: 4,504 lb with no margin.

# Take-off distance against the propeller factor f, W/S 13 A 8 baseline (ruling B-9b, review W-2)

Record: `runs/task12/stage3/2026-11-27/takeoff_f_sweep_ws13a8/sweep.json`, made by `python -m measurement.takeoff_f_sweep`
(`measurement/takeoff_f_sweep.py`) from commit `0807120` with a clean tree (`git_dirty` false). Input record:
`runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8` (design sha256 `a82647354c6d...`, ledger sha256 `b11165a332bed...`).
Tests: `tests/task12/test_takeoff_f_sweep.py` (now also run on this record).

## What was run

Same method as the earlier sweep (`docs/validation/2026-11-26_task12_takeoff_f_sweep.md`). The tool already takes any
record directory through `--record`, so no `--design` option was added. The record's aircraft is rebuilt with Stage 1's
code (the rebuild is checked against the record). Take-off weight (3,517.3 lb), wing, drag, CL_max, engine power
(450 hp) and propeller diameter (6.91 ft) are held fixed; only `prop_real_to_ideal` (f) changes. **This is not a re-size.**
At f = 0.85 the sweep gives the record's take-off distance (711.0 ft) and landing distance (1,348.6 ft) to 1e-9 (tested).

## Result (from the record)

| f | Static thrust, V = 0 (lb) | Thrust at 0.707 V_TO (lb) | Ground roll (ft) | Take-off over 50 ft (ft) | Margin to 2,500 ft (ft) | Landing over 50 ft (ft) | Climb segment (ft) |
|---|---|---|---|---|---|---|---|
| 0.60 | 1,572 | 1,247 | 374 | 855 | 1,645 | 1,349 | 187 |
| 0.65 | 1,659 | 1,324 | 348 | 811 | 1,689 | 1,349 | 142 |
| 0.70 | 1,743 | 1,400 | 327 | 776 | 1,724 | 1,349 | 105 |
| 0.75 | 1,825 | 1,474 | 308 | 749 | 1,751 | 1,349 | 72 |
| 0.80 | 1,906 | 1,546 | 292 | 728 | 1,772 | 1,349 | 43 |
| 0.85 | 1,984 | 1,617 | 277 | 711 | 1,789 | 1,349 | 17 |
| 0.90 | 2,061 | 1,687 | 264 | 698 | 1,802 | 1,349 | 0 |

V_TO is 85.3 ft/s; the ground roll takes thrust at 0.707 V_TO (60.3 ft/s). Landing does not depend on f.
At f = 0.90 the climb segment is 0 ft in the record: the 50 ft obstacle is reached within the transition arc.
The static thrust column equals the earlier sweep's (same engine and propeller); the distances differ because
weight and wing differ.

## Against R7

R7 (`field_length_ft`): 2,500 ft, take-off and landing each over 50 ft, sea level ISA, unfactored (ruling G-1).
Take-off falls monotonically with f. **R7 take-off is met at every f from 0.60 to 0.90.** The worst case, f = 0.60,
gives 855 ft, a margin of 1,645 ft. R7 landing (1,349 ft, margin 1,151 ft) does not depend on f.

## Limits of the result

- f at static and take-off conditions is a judgement beyond App. L (see the earlier report); the sweep range is wider
  than the ledger band (0.80 to 0.90) on purpose.
- Only f changes. Static C_T/C_P was not varied; which thrust term sets the thrust at each f was not recorded.
- Not run: other sites, weights, temperatures or engine-lapse cases; this is sea level ISA at the record's weight.

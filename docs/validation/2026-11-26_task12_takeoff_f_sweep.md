# Take-off distance against the propeller factor f, App. L baseline (APL-5, ruling G-9)

Record: `runs/task12/stage1/2026-11-26/takeoff_f_sweep/sweep.json`, made by `python -m measurement.takeoff_f_sweep`
(`measurement/takeoff_f_sweep.py`) from commit `ea0abb1` with a clean tree (`git_dirty` false, no dirty
files under `conceptual/`, `measurement/`, `data/`). Input: `runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05` (ledger sha256 `d656d2043541...`).
Test: `tests/task12/test_takeoff_f_sweep.py`.

## What was run

The record's aircraft is rebuilt with Stage 1's code (`measurement.stage3_perf.rebuild`, which checks the rebuild against
the record). Take-off weight (3,160.3 lb), wing, drag, CL_max, engine power (450 hp) and propeller diameter
(6.91 ft) are held fixed. Only `prop_real_to_ideal` (f) changes, in a copy of the ledger
values, and Stage 1's own take-off (Raymer 17.8, `uav._takeoff`) and landing (`perf.landing_distance`) are called again.
**This is not a re-size**: weight, fuel and engine do not move with f, so a lower f here shows what the same aircraft
does, not what a redesigned aircraft would be.

At f = 0.85 the sweep gives the record's take-off distance (793.5 ft) and landing distance
(1,419.2 ft) to 1e-9 (tested).

## Result (from the record)

| f | Static thrust, V = 0 (lb) | Thrust at 0.707 V_TO (lb) | Ground roll (ft) | Take-off over 50 ft (ft) | Margin to 2,500 ft (ft) | Landing over 50 ft (ft) |
|---|---|---|---|---|---|---|
| 0.60 | 1,572 | 1,212 | 421 | 929 | 1,571 | 1,419 |
| 0.65 | 1,659 | 1,289 | 392 | 886 | 1,614 | 1,419 |
| 0.70 | 1,743 | 1,363 | 368 | 853 | 1,647 | 1,419 |
| 0.75 | 1,825 | 1,436 | 347 | 829 | 1,671 | 1,419 |
| 0.80 | 1,906 | 1,508 | 328 | 810 | 1,690 | 1,419 |
| 0.85 | 1,984 | 1,578 | 312 | 793 | 1,707 | 1,419 |
| 0.90 | 2,061 | 1,647 | 297 | 779 | 1,721 | 1,419 |

Static thrust is the thrust function at V = 0 (the code holds speed at 1 ft/s there). The ground roll takes thrust at
0.707 V_TO (66.9 ft/s, V_TO = 94.7 ft/s), which Stage 1's Raymer route uses; it is not 0.7 V_TO. Landing does not depend on f
and is unchanged at every f, as expected.

## Against R7

R7 (ledger `field_length_ft`): 2,500 ft, take-off and landing each over 50 ft at sea level ISA, unfactored
(ruling G-1, no FAR 1.666 or 1.15 factor). The take-off over 50 ft is the quantity compared; the margin column is
2,500 ft minus it. Take-off distance falls monotonically with f, and R7 take-off is met at every f from 0.60 to 0.90.
At f = 0.60 the take-off distance is 929 ft, a margin of 1,571 ft. R7 landing (1,419 ft, margin
1,081 ft) does not depend on f.

## Limits of the result

- f at static and take-off conditions is a judgement beyond App. L. App. L (Mattingly p. 612) speaks of efficiency in
  flight, about 85 % of the ideal. Taken to zero speed, f acts as a static figure of merit; the book does not give that number.
- The sweep range 0.60 to 0.90 is wider than the ledger band (0.80 to 0.90, itself a judgement) on purpose; it shows how
  far f can fall before R7 take-off is lost, which it does not do within the range run.
- Only f changes. Static C_T/C_P (2.5, ledger band 2.0 to 2.8) also enters the thrust function (the smaller of three terms) and was not varied; which term sets the thrust at each f was not recorded.
- Not run: any other site, weight, temperature or engine-lapse case; this is sea level ISA at the record's weight.

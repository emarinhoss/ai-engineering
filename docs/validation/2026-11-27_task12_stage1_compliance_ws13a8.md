# Task 12: Stage 1 compliance table of the design record (ruling B-7)

Design `runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/design_pusher.json` (sha256 a82647354c6d), ledger copy `runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/ledger.yaml`. Record `runs/task12/stage3/2026-11-27/compliance_ws13a8/compliance.json`; commit e506e25, git_dirty False. Command: `python -m measurement.stage1_compliance --design runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/design_pusher.json --out runs/task12/stage3/2026-11-27/compliance_ws13a8/compliance.json --report docs/validation/2026-11-27_task12_stage1_compliance_ws13a8.md`.

The table is `conceptual/stage1.py` `compliance()`, the function behind every Stage 1 table, applied to the design rebuilt through Stage 1's own path from the record (not re-sized). The rebuild reproduces the record:

| Quantity | Record | Rebuilt | Relative difference |
|---|---|---|---|
| W0_lb | 3517.2502 | 3517.2419 | -2.4e-06 |
| We_lb | 1918.561 | 1918.5577 | -1.7e-06 |
| fuel_lb | 1098.6876 | 1098.6859 | -1.6e-06 |
| bhp_sl | 450 | 450 | 0.0e+00 |
| ht_volume_scale | 1.5936712 | 1.5936712 | 1.9e-08 |
| n_gust | 3.5035348 | 3.5035354 | 1.9e-07 |
| n_negative_gust | -1.5035348 | -1.5035354 | 4.4e-07 |
| performance.takeoff_ft | 710.95743 | 710.95663 | -1.1e-06 |
| performance.landing_ft | 1348.6318 | 1348.6318 | -1.3e-09 |
| performance.roc_sl_fpm | 2325.8185 | 2325.8253 | 3.0e-06 |
| performance.service_ceiling_ft | 31738.18 | 31738.332 | 4.8e-06 |
| performance.V_stall_clean_kt | 53.331283 | 53.331283 | 0.0e+00 |

Tolerance 0.0001. Verdicts: 19 pass, 0 fail, 11 not tested (by construction, notes and flags the function does not test numerically).

| # | Requirement | Units | Value | Limit | Rule | Verdict |
|---|---|---|---|---|---|---|
| 1 | R1/R2 single turboprop, one engine | - | RR_M250_B17F |  | by construction | not tested |
| 2 | R4 payload | lb | 500 | 500 | by construction | not tested |
| 3 | R5 mission 200 nm + 11 h + 200 nm | fuel lb | 1099 | 1099 | sized to it | not tested |
| 4 | R6 note: no starting (relight) envelope in our sources for this engine; an in-flight relight is not assessed (the TP100's envelope is not reused) | ft |  | 20,000 | note | not tested |
| 5 | R6 mission altitude 20,000 ft: no maximum operating altitude in our sources for this engine (not checked, none invented) | ft | 20,000 |  | note | not tested |
| 6 | R7 take-off over 50 ft | ft | 711 | 2500 | <= | pass |
| 7 | R7 landing over 50 ft | ft | 1349 | 2500 | <= | pass |
| 8 | R7 clean stall at W0, sea level | kt | 53.33 | 70 | <= | pass |
| 9 | R8 retractable tricycle gear | - | yes |  | by construction | not tested |
| 10 | R9 positive limit load (manoeuvre or gust, both weights) | - | 3.8 | 3.8 | >= | pass |
| 11 | R9 negative gust within the negative limit, with the round-4 margin | - | -1.504 | -1.7 | >= | pass |
| 12 | R10 6 % reserve and trapped fuel | - | 1.06 | 1.06 | by construction | not tested |
| 13 | R12 sea-level rate of climb | ft/min | 2326 | 1000 | >= | pass |
| 14 | R12 service ceiling (last altitude with 100 ft/min), with the round-4 margin | ft | 31,738 | 23,500 | ceiling | pass |
| 15 | R13 static margin, full fuel | MAC | 0.1126 | 0.05-0.15 | in band | pass |
| 16 | R13 static margin, empty fuel | MAC | 0.08744 | 0.05-0.15 | in band | pass |
| 17 | R14 no crew items in the weights | - | yes |  | by construction | not tested |
| 18 | R15 flight avionics 60 lb uninstalled | lb | 60 | 60 | by construction | not tested |
| 19 | R18 V_C placard covers the fastest cruise sub-step with 10 % margin (study margin) | kt EAS | 104.5 | 110 | <= | pass |
| 20 | R17 every mission sub-step at or above 1.3 V_stall (enforced in the speed choice) | - | yes |  | by construction | not tested |
| 21 | R19 both transit legs flown against a 25 kt headwind (air distance V/(V - V_w)) | kt | 25 | 25 | by construction | not tested |
| 22 | R16 sustained 30 deg bank at loiter (power) | hp | 243.5 | 450 | <= | pass |
| 23 | engine power meets every requirement (achieved margin 37.5%) | hp | 281.1 | 450 | <= | pass |
| 24 | fuel fits integral wing tanks | ft^3 | 21.92 | 73.17 | <= | pass |
| 25 | nose-wheel load, full fuel (p. 232-233; optimum 0.08-0.15) | - | 0.1633 | 0.05-0.20 | nose | pass |
| 26 | nose-wheel load, empty fuel | - | 0.1515 | 0.05-0.20 | nose | pass |
| 27 | main gear stows: sponsons at the 63 deg overturn track (p. 232; ruling round 3) | ft | 4.731 |  | stow | pass |
| 28 | propeller clearance at rotation (p. 222) | in | 14.44 | 8.95 | >= | pass |
| 29 | trim within tail CL limit, all mission legs | - | yes |  | flag | pass |
| 30 | nose rotation at 0.8 V_TO (p. 432-433), tail download | tail CL | 0.9677 | 1 | <= | pass |

Failed rows: none.

Limits are the record's ledger values with their Gate A margins (negative gust -1.8 plus 0.1 g, ceiling +500 ft, power margin 0). The R9 positive row compares n_limit, which Stage 1 sets to the larger of 3.8 and the gust load factor; the gust value itself is in the V-n check of the same design. Row 25 passes the 5-20 % limits but its value 0.1633 is above the 0.08-0.15 optimum named in its label. Row 26 passes the 5-20 % limits but its value 0.1515 is above the 0.08-0.15 optimum named in its label. Row 14: the Stage 1 service ceiling (31,738 ft) is above the engine table's top altitude (30,000 ft), where the lookup clamps and holds the table's power constant, so it leans on that clamp. The cycle's own power keeps falling; the Stage 3 engine report gives the ceiling with it. Quote this row with that caveat. The Gate A items A1 to A12 are not re-checked here (a review task).

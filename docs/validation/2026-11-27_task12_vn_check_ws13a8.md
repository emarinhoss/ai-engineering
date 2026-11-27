# Task 12: V-n check of the design record (ruling B-4)

Record: `runs/task12/stage3/2026-11-27/vn_check_ws13a8/vn.json`; design `runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/design_pusher.json` (sha256 a82647354c6d); commit 897b5e9, git_dirty False. Command: `python -m measurement.vn_check --design runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/design_pusher.json --out runs/task12/stage3/2026-11-27/vn_check_ws13a8/vn.json --report docs/validation/2026-11-27_task12_vn_check_ws13a8.md`.

Stage 1's own loads code (`conceptual/raymer_loads.py`), the design rebuilt from its record, not re-sized. W0 3517.3 lb, fuel 1098.7 lb, W/S 13, clean CL_max 1.35.

## Speeds and limits

- V_C 110.0 kt EAS, V_D 165.0 kt EAS (1.5 V_C), corner speed 104.0 kt EAS.
- Level top speed: 185.2 kt EAS at sea level, 120.9 kt EAS at 20,000 ft.
- Limits (ledger): positive 3.8; negative -1.8 with a 0.1 g margin, so the negative gust must stay at or above -1.7.

Reproduction of the record: at V_C and V_D the check reproduces the record's `vn` and `gusts` entries; worst relative difference 1.2e-07 (test `tests/task12/test_vn_check.py`, limit 1e-5).

## Load factors

Gust load factor with the lift slope at the speed's own Mach number (the value the structure was sized with, the record's `gusts`); the record's `vn` entries use the slope at the sizing Mach and differ slightly (both are in the record). U_de 30 ft/s up to V_C, falling to 15 ft/s at V_D and 15 ft/s above (Raymer p. 339). Manoeuvre: aerodynamic limit q CL_max/(W/S), capped at the structural limit 3.8. The last two columns are a sensitivity, not the rule: U_de held at 30 ft/s at every speed.

| Altitude | Speed | V EAS (kt) | U_de (ft/s) | Weight | n gust + | n gust - | n manoeuvre (aero) | n manoeuvre (capped) | exceeds | n gust + (U_de 30) | n gust - (U_de 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sea_level | V_C | 110.0 | 30.0 | takeoff | 2.577 | -0.577 | 4.254 | 3.800 | no | 2.577 | -0.577 |
| sea_level | V_C | 110.0 | 30.0 | zero_fuel | 2.991 | -0.991 | 6.187 | 3.800 | no | 2.991 | -0.991 |
| sea_level | V_D | 165.0 | 15.0 | takeoff | 2.194 | -0.194 | 9.572 | 3.800 | no | 3.388 | -1.388 |
| sea_level | V_D | 165.0 | 15.0 | zero_fuel | 2.505 | -0.505 | 13.920 | 3.800 | no | 4.011 | -2.011 |
| sea_level | level_top_speed | 185.2 | 15.0 | takeoff | 2.346 | -0.346 | 12.063 | 3.800 | no | 3.692 | -1.692 |
| sea_level | level_top_speed | 185.2 | 15.0 | zero_fuel | 2.696 | -0.696 | 17.542 | 3.800 | no | 4.393 | -2.393 |
| mission_altitude | V_C | 110.0 | 30.0 | takeoff | 2.888 | -0.888 | 4.254 | 3.800 | no | 2.888 | -0.888 |
| mission_altitude | V_C | 110.0 | 30.0 | zero_fuel | 3.504 | -1.504 | 6.187 | 3.800 | no | 3.504 | -1.504 |
| mission_altitude | V_D | 165.0 | 15.0 | takeoff | 2.452 | -0.452 | 9.572 | 3.800 | no | 3.904 | -1.904 |
| mission_altitude | V_D | 165.0 | 15.0 | zero_fuel | 2.920 | -0.920 | 13.920 | 3.800 | no | 4.841 | -2.841 |
| mission_altitude | level_top_speed | 120.9 | 27.0 | takeoff | 2.877 | -0.877 | 5.137 | 3.800 | no | 3.084 | -1.084 |
| mission_altitude | level_top_speed | 120.9 | 27.0 | zero_fuel | 3.488 | -1.488 | 7.471 | 3.800 | no | 3.761 | -1.761 |

## Result

Points that exceed a limit under the design gust rule: none (every gust load factor above is inside +3.8 and the negative limit with margin).

Points that would exceed a limit if U_de stayed at 30 ft/s at every speed (sensitivity, not the rule; positive / negative): sea_level, V_D, zero_fuel_weight (4.011 / -2.011); sea_level, level_top_speed, zero_fuel_weight (4.393 / -2.393); mission_altitude, V_D, takeoff_weight (3.904 / -1.904); mission_altitude, V_D, zero_fuel_weight (4.841 / -2.841); mission_altitude, level_top_speed, zero_fuel_weight (3.761 / -1.761).

The structure is sized at V_C 110 kt EAS (the per-design rule, ruling B-4) and V_D 165 kt EAS. The sea-level level top speed (185.2 kt EAS) is above V_D: the structure is not cleared to it. Envelope protection (the autopilot holding the aircraft at or below V_C, and below V_D at sea level) is a preliminary-design requirement per ruling B-4. No negative manoeuvre load factor is computed: the record has no negative CL_max.

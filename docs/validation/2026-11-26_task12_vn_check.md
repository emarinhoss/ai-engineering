# Task 12: V-n check of the frozen design (ruling B-4)

Record: `runs/task12/stage3/2026-11-26/vn_check/vn.json`; design `runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json` (sha256 550334ac4436); commit f6918fa, git_dirty False. Command: `python -m measurement.vn_check --design runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json --out runs/task12/stage3/2026-11-26/vn_check/vn.json --report docs/validation/2026-11-26_task12_vn_check.md`.

Stage 1's own loads code (`conceptual/raymer_loads.py`), the design rebuilt from its record, not re-sized. W0 3160.3 lb, fuel 977.3 lb, W/S 16, clean CL_max 1.35.

## Speeds and limits

- V_C 115.0 kt EAS, V_D 172.5 kt EAS (1.5 V_C), corner speed 115.3 kt EAS.
- Level top speed: 198.5 kt EAS at sea level, 129.8 kt EAS at 20,000 ft.
- Limits (ledger): positive 3.8; negative -1.8 with a 0.1 g margin, so the negative gust must stay at or above -1.7.

Reproduction of the record: at V_C and V_D the check reproduces the record's `vn` and `gusts` entries; worst relative difference 1.1e-07 (test `tests/task12/test_vn_check.py`, limit 1e-5).

## Load factors

Gust load factor with the lift slope at the speed's own Mach number (the value the structure was sized with, the record's `gusts`); the record's `vn` entries use the slope at the sizing Mach and differ slightly (both are in the record). U_de 30 ft/s up to V_C, falling to 15 ft/s at V_D and 15 ft/s above (Raymer p. 339). Manoeuvre: aerodynamic limit q CL_max/(W/S), capped at the structural limit 3.8. The last two columns are a sensitivity, not the rule: U_de held at 30 ft/s at every speed.

| Altitude | Speed | V EAS (kt) | U_de (ft/s) | Weight | n gust + | n gust - | n manoeuvre (aero) | n manoeuvre (capped) | exceeds | n gust + (U_de 30) | n gust - (U_de 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sea_level | V_C | 115.0 | 30.0 | takeoff | 2.437 | -0.437 | 3.778 | 3.778 | no | 2.437 | -0.437 |
| sea_level | V_C | 115.0 | 30.0 | zero_fuel | 2.859 | -0.859 | 5.469 | 3.800 | no | 2.859 | -0.859 |
| sea_level | V_D | 172.5 | 15.0 | takeoff | 2.089 | -0.089 | 8.500 | 3.800 | no | 3.179 | -1.179 |
| sea_level | V_D | 172.5 | 15.0 | zero_fuel | 2.407 | -0.407 | 12.305 | 3.800 | no | 3.815 | -1.815 |
| sea_level | level_top_speed | 198.5 | 15.0 | takeoff | 2.262 | -0.262 | 11.256 | 3.800 | no | 3.523 | -1.523 |
| sea_level | level_top_speed | 198.5 | 15.0 | zero_fuel | 2.629 | -0.629 | 16.295 | 3.800 | no | 4.258 | -2.258 |
| mission_altitude | V_C | 115.0 | 30.0 | takeoff | 2.660 | -0.660 | 3.778 | 3.778 | no | 2.660 | -0.660 |
| mission_altitude | V_C | 115.0 | 30.0 | zero_fuel | 3.239 | -1.239 | 5.469 | 3.800 | no | 3.239 | -1.239 |
| mission_altitude | V_D | 172.5 | 15.0 | takeoff | 2.280 | -0.280 | 8.500 | 3.800 | no | 3.560 | -1.560 |
| mission_altitude | V_D | 172.5 | 15.0 | zero_fuel | 2.723 | -0.723 | 12.305 | 3.800 | no | 4.446 | -2.446 |
| mission_altitude | level_top_speed | 129.8 | 26.1 | takeoff | 2.642 | -0.642 | 4.814 | 3.800 | no | 2.885 | -0.885 |
| mission_altitude | level_top_speed | 129.8 | 26.1 | zero_fuel | 3.214 | -1.214 | 6.969 | 3.800 | no | 3.541 | -1.541 |

## Result

Points that exceed a limit under the design gust rule: none (every gust load factor above is inside +3.8 and the negative limit with margin).

Points that would exceed a limit if U_de stayed at 30 ft/s at every speed (sensitivity, not the rule; positive / negative): sea_level, V_D, zero_fuel_weight (3.815 / -1.815); sea_level, level_top_speed, zero_fuel_weight (4.258 / -2.258); mission_altitude, V_D, zero_fuel_weight (4.446 / -2.446).

The structure is sized at V_C 115 kt EAS (the per-design rule, ruling B-4) and V_D 172.5 kt EAS. The sea-level level top speed (198.5 kt EAS) is above V_D: the structure is not cleared to it. Envelope protection (the autopilot holding the aircraft at or below V_C, and below V_D at sea level) is a preliminary-design requirement per ruling B-4. No negative manoeuvre load factor is computed: the record has no negative CL_max.

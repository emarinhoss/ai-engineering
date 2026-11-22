# Task 12 Stage 3: info-gap robustness of the built design (R5, R7)

Generated from `runs/task12/stage1/2026-11-21f/design_pusher.json` by `python -m measurement.info_gap`; the numbers below are read from the run record `info_gap.json` (inputs, versions, seed there).

## Method

Ben-Haim's info-gap as in Marchau et al., DMDU, ch. 10. Uncertainty model (10.7), p. 213: theta_k in [theta_k0 - h W_k_lower, theta_k0 + h W_k_upper], weights W set so that h = 1 gives the ledger band ends (W_lower = nominal - band_lo, W_upper = band_hi - nominal; one-sided where the nominal is a band end). Robustness (10.8), p. 214: h_hat is the largest h at which the worst case over U(h) still meets the requirement, found by bisection on h in [0, 3]. Uncertain quantities: 53, the ledger assumptions that carry a band plus two engine multipliers (SFC and full-throttle power of the TP100 table, +-10 % at h = 1). The SFC multiplier is applied on top of the ledger's 1.05 SFC allowance (`engine_sfc_allowance`), which stays in.

The aircraft is built: W0, wing loading, aspect ratio, tail scale and fuel load are the record's and are not re-sized, so weight assumptions (composite factor, avionics weight, gear length) act only through geometry and drag, not through a change of W0 or of fuel load. R5: hours on station with the record's fuel, the loiter time at which the rebuilt mission fuel (including the 6 % reserve factor) equals the record's fuel. R7: take-off and landing distance over 50 ft against the ledger field length. The engine power multiplier scales the take-off shaft power as well as the table's lapse.

## Nominal (h = 0)

| Quantity | Record | Rebuilt here |
|---|---|---|
| Hours on station | 8 (requirement; the record's fuel was sized for it) | 8.0000 |
| Take-off over 50 ft (ft) | 736.30 | 736.30 |
| Landing over 50 ft (ft) | 1360.52 | 1360.52 |

## Robustness against the Gate B threshold (h = 1)

| Requirement | h_hat | Status | Meets Gate B (>= 1) |
|---|---|---|---|
| R5, 8 h on station | 0.0000 | zero margin: fails at the first step above h = 0 | no |
| R7 take-off | 1.6972 | bracketed | yes |
| R7 landing | 1.9431 | bracketed | yes |
| R7 combined (min) | 1.6972 | min of take-off and landing | yes |

Secondary, not the requirement: R5 if the 6 % reserve could be burned as well (target fuel = 1.06 x the record's): h_hat = 0.2139 (bracketed). Reported to show how far the design is from the threshold, not as a pass.

## Worst case against h

| h | Hours on station | Take-off (ft) | Landing (ft) |
|---|---|---|---|
| 0 | 8.000 | 736.3 | 1360.5 |
| 0.25 | 6.904 | 810.3 | 1416.5 |
| 0.5 | 5.833 | 905.2 | 1481.5 |
| 0.75 | 4.782 | 1030.7 | 1558.8 |
| 1 | 3.751 | 1204.0 | 1653.8 |
| 1.5 | 0.000 | 1880.4 | 1942.6 |
| 2 | 0.000 | 8019.4 | 2625.3 |
| 3 | 0.000 | inf | inf |

## What drives each requirement (one at a time at h = 1)

Effect = change at the harmful end of the variable's band from the nominal value. Direction -1 means the lower band end is harmful, +1 the upper end, 0 neither. The corner used in the worst case takes every variable at its harmful end.

### R5 hours on station

| Variable | Nominal | Lower end | Upper end | Harmful end | Effect (h) |
|---|---|---|---|---|---|
| engine_sfc_mult | 1 | 0.9 | 1.1 | +1 | -1.329 |
| eta_p | 0.8 | 0.75 | 0.85 | -1 | -0.6338 |
| sponson_depth_per_tyre | 1.2 | 1.1 | 1.4 | +1 | -0.5961 |
| engine_power_mult | 1 | 0.9 | 1.1 | +1 | -0.4583 |
| sensor_drag_area_ft2 | 0.4 | 0.2 | 0.8 | +1 | -0.3523 |
| fuselage_fineness | 8 | 6 | 10 | -1 | -0.3339 |
| airfoil_cl_max | 1.5 | 1.3 | 1.7 | -1 | -0.3049 |
| sponson_length_per_tyre | 3.6 | 3 | 4.8 | -1 | -0.2782 |
| wing_t_c | 0.15 | 0.12 | 0.18 | +1 | -0.1588 |
| laminar_fraction_wing | 0.15 | 0.1 | 0.5 | -1 | -0.1265 |

42 of 53 variables have no harmful effect on this requirement (not shown; all are in the JSON).

### R7 take-off

| Variable | Nominal | Lower end | Upper end | Harmful end | Effect (ft) |
|---|---|---|---|---|---|
| static_ct_over_cp | 2.5 | 2 | 2.8 | -1 | +82.76 |
| airfoil_cl_max | 1.5 | 1.3 | 1.7 | -1 | +59.55 |
| engine_power_mult | 1 | 0.9 | 1.1 | -1 | +56.76 |
| takeoff_flap_fraction | 0.6 | 0.4 | 0.8 | -1 | +50.87 |
| flap_span_fraction | 0.6 | 0.5 | 0.7 | -1 | +20.41 |
| rolling_mu | 0.03 | 0.03 | 0.05 | +1 | +13.97 |
| eta_p | 0.8 | 0.75 | 0.85 | -1 | +11.11 |
| flap_deflection_takeoff_deg | 30 | 20 | 40 | +1 | +7.805 |
| sponson_depth_per_tyre | 1.2 | 1.1 | 1.4 | +1 | +1.37 |
| sensor_drag_area_ft2 | 0.4 | 0.2 | 0.8 | +1 | +0.8953 |

34 of 53 variables have no harmful effect on this requirement (not shown; all are in the JSON).

### R7 landing

| Variable | Nominal | Lower end | Upper end | Harmful end | Effect (ft) |
|---|---|---|---|---|---|
| braking_mu | 0.5 | 0.3 | 0.5 | -1 | +124 |
| free_roll_s | 2 | 1 | 3 | +1 | +83.98 |
| airfoil_cl_max | 1.5 | 1.3 | 1.7 | -1 | +28.35 |
| flap_span_fraction | 0.6 | 0.5 | 0.7 | -1 | +21.82 |
| laminar_fraction_wing | 0.15 | 0.1 | 0.5 | +1 | +0.4617 |
| sponson_length_per_tyre | 3.6 | 3 | 4.8 | +1 | +0.108 |
| sponson_depth_per_tyre | 1.2 | 1.1 | 1.4 | -1 | +0.1058 |
| sensor_drag_area_ft2 | 0.4 | 0.2 | 0.8 | -1 | +0.09719 |
| laminar_fraction_fuselage | 0 | 0 | 0.2 | +1 | +0.06805 |
| fuselage_fineness | 8 | 6 | 10 | +1 | +0.0633 |

36 of 53 variables have no harmful effect on this requirement (not shown; all are in the JSON).

## Check of the monotone corner by sampling

Seed 20261122, 200 points uniform in U(h) plus the corners of the 5 most influential variables of each requirement (others at nominal).

At h = 1.0000: 200 random and 96 corner points.

| Quantity | Monotone corner | Worst sampled | Worst random | Points worse than the corner |
|---|---|---|---|---|
| R5_hours | 3.7514 | 4.9319 (corner of top 5 for R5_hours) | 6.1816 | 0 |
| takeoff_ft | 1204.0168 | 1072.5088 (corner of top 5 for takeoff_ft) | 957.6797 | 0 |
| landing_ft | 1653.8216 | 1651.6697 (corner of top 5 for landing_ft) | 1581.5642 | 0 |

## Clipping

At h = 1: 0 variables clipped. At h = 3: 13: takeoff_flap_fraction (upper), laminar_fraction_wing (upper), sensor_drag_area_ft2 (lower), fuselage_kf (lower), tail_height_over_df (lower/upper), composite_factor (upper), braking_mu (lower), free_roll_s (lower), tail_cl_max_trim (upper), station_payload_pusher (lower), station_nose_gear (lower), nose_down_deg (lower), nose_tyre_scale (upper). Limits: non-negative, and at most 1 for a dimensionless fraction or efficiency.

## Record

Design sha256 `1b416bf8f552478c...`, ledger sha256 `cd522f2fa3c6d4dd...`, git commit `d2f0c7e34fcd678c4976b2a42453b2e770c77c64`, Python 3.13.18, numpy 2.5.3, 4 CPUs, runtime 67 s.

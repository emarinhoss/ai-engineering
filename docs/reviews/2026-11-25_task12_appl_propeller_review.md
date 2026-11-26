# Review: Task 12 App. L propeller (commits 3884969 and 8295fa0)

Read-only review; nothing edited, stashed or committed (`git status` clean at the end). Numbers marked "computed" come from my own script, which re-implements (L.8), the solve by bisection, the momentum limit and Raymer's take-off segments without the repo's propeller code. Numbers marked "record" are read from the repo. Scratch scripts are in `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/` (`hand.py`, `chk.py`, `chk2.py`, `chk3.py`, `chk4.py`).

## Verdict

The Stage 1 code and the 2026-11-25 record are correct as an implementation of G-4. There are no blocking findings against the two commits themselves. One finding (APL-1) blocks any info-gap or Stage 3 re-run on the new baseline until it is fixed.

## What holds (checked)

1. **Actuator disk and solve.** `ActuatorDisk.efficiency_for_thrust` (`conceptual/raymer_propulsion.py:33-37`) solves C_T eta*^2 + 4 eta* - 4 = 0, which is (L.8) as given in the library notes (Mattingly App. L p. 612), and takes the positive root.
   - Hand case: C_T = 1.25 gives eta* = 0.8.
   - The map eta -> f eta*(T(eta)) is decreasing in eta, so the fixed point is unique.
   - At low speed its slope tends to -1/2, so it converges linearly. Computed iteration counts to 1e-12: 36 at 1 ft/s, 31 at 0.01 ft/s, 17 at 119.4 ft/s, 6 at 400 ft/s; the 200-pass limit is never near.
   - My bisection and the repo's fixed point agree to 1e-12 at every speed tried.
2. **Static limit.** Computed: A = 37.487 ft^2 and T = (2 rho A)^(1/3) (550 x 450)^(2/3) = 2,218.3 lb, with rho 0.0023769 and D 6.90867 ft. The 2,218 lb claim is confirmed.
3. **Mission-point efficiencies.** All four recomputed from the record's V, shaft power, density and diameter:

   | Point | Computed | Record |
   |---|---|---|
   | climb (175.84 ft/s, 450 hp, sea level) | 0.73209 | 0.732090 |
   | cruise_out (rho 0.00126727 at 20,000 ft) | 0.818930 | 0.818930 |
   | loiter | 0.802991 | 0.802991 |
   | cruise_back | 0.820340 | 0.820340 |

   - The climb value matches only with `isa(0)["rho"]` = 0.00237700; with `RHO0` = 0.0023769 it is 0.732087 (see APL-8).
   - At 119.4 ft/s and 450 hp I get 0.6206, the "0.62" of the ruling. The record's 0.732 is at the new best-climb speed of 104 kt, so the two are consistent.
4. **Take-off.** My segment calculation reproduces the records:

   | Case | Thrust at 0.707 V_TO (lb) | T/W | Ground roll (ft) | Total (ft) |
   |---|---|---|---|---|
   | 2026-11-23, flat | 2,582 | 0.860 | 226.8 | 779.4 |
   | 2026-11-25, app_l | 1,510 | 0.503 | 428.0 | 993.7 |

   - The old flat thrust at 78 ft/s was still above the 2,218 lb static limit.
   - Ground roll scales roughly as 1/(T/W - mu): 0.830/0.473 = 1.76, times the V_TO^2 ratio 1.048, gives about 418 ft against 428 ft. The change is physically plausible.
   - Rotation and transition are geometric in both runs (h_tr above 50 ft), so only the ground roll moves.
5. **Flat rebuild.** `sp.rebuild` on the three records in the test plus `2026-11-23/design_tractor.json`: largest relative difference 2.2e-16, and no `propeller_model` in their ledger copies. `tests/task12/test_propeller_app_l.py` gives 17 passed (run by me, cache and bytecode writes disabled).
6. **Coverage in `conceptual/uav.py`.** Every former `L["eta_p"]` now goes through `_propeller`: `_min_power_for`, `_leg_speed`, `_vmax_consistent`, `_thrust_fn`, `_mission` (climb, legs), `_build` (climb, ceiling, turn, cruise), `ceiling`, `performance`, `propeller_points`. The report's sensitivity table lists `eta_p` under "No effect at this design", which agrees.

## Findings

**APL-1 (blocking for any info-gap or Stage 3 re-run on the app_l baseline; should-fix otherwise). The transit-cliff score still uses the flat `eta_p`.**
- Evidence: `measurement/info_gap.py:347` divides by `L["eta_p"]`, while `uav._leg_speed` (`conceptual/uav.py:251-254`) now uses the disk.
- Computed on the 2026-11-25 pusher at the cruise_out start weight of 2,941 lb, design diameter held:

  | Quantity | Low end | Nominal | High end |
  |---|---|---|---|
  | Score from `leg_power_ratio`, `eta_p` 0.75 / 0.80 / 0.85 | 0.5605 | 0.5255 | 0.4946 |
  | True ratio from the disk, f 0.80 / 0.85 / 0.90 | 0.5534 | 0.5208 | 0.4919 |

- The binding speed is 122.2 kt, where the disk efficiency is 0.807.
- The score responds to `eta_p`, which is inert in the model, by about +6.7 % / -5.9 %. It does not respond at all to `prop_real_to_ideal`, which is the real uncertainty (true ratio +6.3 % / -5.5 %).
- So the worst-case point will name `eta_p`, a variable the aircraft does not read. A point with `eta_p` low and f nominal scores a cliff the mission does not have; f low is invisible to the score.
- At this design the errors are small (+0.9 % nominal, +1.3 % at the low ends) only because the two bands have nearly the same relative width and eta at the binding speed is near 0.80. That is a coincidence.
- The drift test `tests/task12/test_vc_targets.py:109-124` does not catch this: it runs on the TP100 helper, which `tests/task12/conftest.py` pins to flat.
- Fix: in `leg_power_ratio` use `eta_p = uav._propeller(L, atm, uav._prop_diameter_ft(bhp, L))` and `prop.shaft_hp(drag * Vi, Vi, eta_p)`, exactly as `_leg_speed` does.
  - The diameter must come from the same `bhp` argument. When I bisected on `bhp` in `_leg_speed` the cliff came at 0.5300 rather than 0.5208, because the statistical diameter shrinks with `bhp`.
  - Add an M250/app_l case to the drift test.
  - Drop `eta_p` from the uncertain variables when `propeller_model` is app_l, or have `uncertain_variables` skip it.

**APL-2 (should-fix). The TP100 pin lives only in the test set-up.**
- Evidence: `measurement/rubber_tp100.py:31` has `TP100_LEDGER = {"engine_sfc_allowance": 1.05, "propeller_rpm": 2158.0}`. Outside pytest, `tp100_ledger_values()` returns `propeller_model` app_l (run by me).
- Any TP100 comparison or `robust_sizing` run with the TP100 engine started from the command line would use the new propeller, while the tests say flat.
- Fix: add `"propeller_model": "flat"` to `TP100_LEDGER` and `TP100_LEDGER_LINES`, then delete `tests/task12/conftest.py`.

**APL-3 (should-fix before the Stage 3 redo). Stage 3 still assumes Stage 1 is flat.**
- `measurement/stage3_perf.py:151, 235, 305, 370, 408` use `L["eta_p"]` in the Anderson and Mattingly rows.
- `stage3_perf.py:536` reports Stage 1's efficiency as "ledger eta_p (Raymer Table 3.4)". For an app_l record that is false; the Stage 1 value is `propeller_points[...]["eta_p"]`.
- `measurement/stage3_engine.py:56` and `:252` compute shaft power as D V/(550 `eta_p`).
- `_prop_eta_fixed_point` (`stage3_perf.py:509`) is the same relation with the same 0.85 as `ActuatorDisk`. Against an app_l record the three propeller rows become coding checks, not `INDEPENDENT`.
- Fix: read the record's per-point eta, reclassify the propeller rows, and state in the Gate B list that there is now no independent propeller check (G-5 waived the blade-element one).

**APL-4 (should-fix: wording). The momentum cap never binds, and "capped" misdescribes what limits the thrust.**
- With eta = f eta*, the low-speed limit is f x 550 P = T^(3/2)/sqrt(2 rho A), so T tends to f^(2/3) times the limit.
- Computed: f^(2/3) = 0.8973, so 1,990.5 lb as V tends to 0, and 1,984.3 lb at 1 ft/s (where the code evaluates, `max(V, 1.0)`). The "1,984 lb" claim is the 1 ft/s value, 0.3 % below f^(2/3) of the limit; the test allows 1 %.
- For any f at or below 1 the disk thrust is below the cap at every speed, so the `cap` term in `_thrust_fn` (`conceptual/uav.py:291-296`) is dead code under app_l.
- `static_ct_over_cp` is also inert: 2,647 lb nominal, and still above the disk thrust at its band low end of 2.0.
- Fix: keep the cap as a guard if wanted, but say in the docstring, ledger line and report line 9 that static thrust is f^(2/3) of the momentum limit and that the cap is a guard that does not bind. Either remove `static_ct_over_cp` from the uncertain set under app_l or note it as inert.

**APL-5 (should-fix: flag as judgement). Using f = 0.85 at static and low speed is an extrapolation of App. L.**
- The library notes for p. 612 say real propellers reach about 85 % of ideal efficiency, mainly from blade friction drag, plus swirl and non-uniform wake. That is a statement about efficiency in forward flight.
- Applied as V tends to 0, the code's f is a static figure of merit of 0.85 (ideal induced power over shaft power). App. L does not give that number.
- My judgement, not from the repo or the library: 0.85 is optimistic for a static propeller, so the 1,984 lb is probably high.
- It does not decide R7. Computed take-off for the 2026-11-25 design:

  | f | Static thrust (lb) | Ground roll (ft) | Total over 50 ft (ft) |
  |---|---|---|---|
  | 0.60 | 1,578 | 583 | 1,161 |
  | 0.70 | 1,749 | 507 | 1,073 |
  | 0.80 | 1,912 | 451 | 1,017 |
  | 0.85 | 1,991 | 428 | 994 |
  | 0.90 | 2,068 | 408 | 973 |

  All are far inside the 2,500 ft field length.
- Fix: one sentence in the report and ledger that the take-off use of f is a judgement beyond the source, with the sweep recorded as a run if the numbers are to be quoted.

**APL-6 (should-fix: label). The 0.80-0.90 band on f is judgement, and the entry's confidence reads "published".**
- Evidence: `data/task12/ledger.yaml`, `prop_real_to_ideal`. The source text is honest: "The book gives no range; the band ... is a judgement".
- The library notes confirm that the book gives a single "about 85 %" with no range.
- The band is defensible as a placeholder; it cannot be defended from the source. The value is published, the band is not.
- Computed effect of the band: climb efficiency 0.694 / 0.732 / 0.770; cruise-speed efficiency at the binding point 0.760 / 0.807 / 0.855. Record: W0 +74 / -64 lb.
- The same f is applied to every point, so the band cannot represent a propeller that is good in cruise and poor in climb.
- Fix: mark the band as judgement where the report lists bands (as `cbhp_cruise` does), and list it with the open items for the owner.

**APL-7 (note). The new model is more favourable than the old one in cruise and at V_max.**
- f eta* rises toward 0.85 with speed and has no tip-Mach or off-design loss.
- Record: cruise 0.819 and 0.820 against the old 0.80; V_max at 20,000 ft 185.6 to 189.3 kt; carpet W0 at the old cell 2,912.6 to 2,904.1 lb.
- The report gives these numbers but does not say that the change loosens the cruise side while tightening climb and take-off. Worth one sentence.

**APL-8 (note). The take-off comparison mixes two changes, and two densities are in use.**
- The selected cell moved from W/S 21 to 22. Computed: the propeller change alone at the old cell takes 779 ft to 957 ft (ground roll 227 to 405 ft); the cell move adds the rest, to 994 ft.
- The report's comparison table shows the W/S change but credits the difference to the propeller in the text.
- `_thrust_fn` builds the disk with `isa(0.0)["rho"]` = 0.00237700 and the cap with `RHO0` = 0.0023769. The effect is at the 4e-8 level in density and about 3e-6 in efficiency. Use one.

**APL-9 (note). Items outside the propeller model, and test coverage.**
- `stage1.first_pass` (`conceptual/stage1.py:76-77`) still uses `L["eta_p"]`, as the agent stated; the report (line 9) and the ledger say so. Acceptable for a sketch.
- `conceptual/constraints.py:39, 69` take a flat `eta_p` but nothing calls them in `conceptual/` or `measurement/` (grep).
- The disk area is the full disk; there is no hub, spinner or pusher-fuselage blockage.
- The 1e-9 rebuild test checks fuel and the five power rows only. Take-off distance, climb rate and ceiling of the old records are not in `check`. The flat arithmetic there is unchanged by inspection (the `min` gains an infinite third term), but a `performance()` comparison would close it.

## Answers to the six questions

1. (L.8) and the solve are correct; the root is unique and stable at low speed.
2. 2,218 lb is confirmed. 1,984 lb is the 1 ft/s value; f^(2/3) of the limit is 1,990.5 lb. Applying f this way is algebraically consistent with eta = f eta* but goes beyond what App. L states (APL-5). The take-off change is plausible and reproduced.
3. All four efficiencies are reproduced.
4. `uav.py` is fully converted. Still flat: `first_pass`, `info_gap.leg_power_ratio` (wrong under app_l, and perturbed by the inert `eta_p` band: APL-1), `stage3_perf`, `stage3_engine`, and the TP100 helper outside pytest (APL-2, APL-3).
5. The band is judgement (APL-6).
6. Old records rebuild to 2.2e-16 on the checked quantities.

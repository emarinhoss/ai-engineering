# Review of the info-gap robustness study (2026-11-22)

**Outcome: the R5 guarantee result (h_hat 1.06, "meets Gate B") is withdrawn.** A member of U(1)
(the recorded R5 corner with engine power at its low end) makes the 20,000 ft transit unflyable,
which the study counts as 0 h; reproduced by the author (power 0.93 at the h = 1 corner: 0.0 h,
"no speed on the leg within the engine's power"). The reviewer's corrected search gives about
0.86 for the 3.5 h guarantee, below Gate B's 1. R7 stands (take-off about 1.59, landing 1.94).
Record `runs/task12/stage3/2026-11-22/info_gap.json` and its report are superseded on these points
and will be regenerated after the corrected search (IG-1, IG-3) and the owner's rulings.

## Owner rulings

To be recorded as given.

## Independent review (verbatim)

# Review: info-gap robustness of the Task 12 aircraft

Read-only review; no repo files were changed. `python -m pytest -q tests/task12` gives 197 passed, 1 xfailed (81 s). A re-run of `python -m measurement.info_gap` into the scratchpad reproduces `info_gap.json` exactly, apart from `runtime_s` and `git_commit`.

**Verdict in one line:** the R7 result can be relied on with actions; the R5 guarantee result (h_hat 1.06, "meets Gate B") cannot, because a point inside U(1) gives 0 h under the module's own definition.

## Findings

### IG-1 (critical): the monotone corner is not the worst case for R5; the guarantee's h_hat is about 0.86, not 1.06

- **Counterexample inside U(1):** take the record's R5 corner at h = 1 and set `engine_power_mult` anywhere from 0.90 to 0.96 instead of 1.10. `uav._mission` raises `ValueError: no speed on the leg within the engine's power` on `cruise_out` (W about 3,250 lb at 20,000 ft). `hours_on_station` returns 0 h by the module's own rule, against 3.75 h at the recorded corner.
- **Why it was missed:** one-at-a-time at h = 1 marks high engine power as harmful (lower part-power fraction, worse SFC, -0.46 h). Low power alone is beneficial (8.49 h). Low power combined with the high-drag, low-eta_p, low-CLmax corner makes the transit unflyable. This is a sign reversal through interaction, which fixed one-at-a-time directions cannot see.
- **Corrected h_hat:** with `engine_power_mult` at its lower end and the other directions unchanged, bisection gives 0.879. A coordinate search over all 53 directions in {-1, 0, +1} also flips `engine_sfc_mult` to its lower end (less fuel burned before the transit, so heavier) and gives **0.862**. No further flip lowers it, and a 9-point scan of each variable at h = 0.80 and 0.85 from that corner found nothing unflyable.
- **It is a cliff:** hours at that corner are 6.96 at h = 0.86 and 0 at h = 0.865.
- **Which variables matter:** at h = 1 the point becomes flyable again if any one of low power, low `airfoil_cl_max` (the 1.3 V_stall floor of R17) or high `sponson_depth_per_tyre` is put back to nominal. The design has about 3 % power margin (ceiling needs 233.7 of 241 hp).
- **The sampling check could not have caught it:**
  - The 200 uniform points in 53 dimensions sit far from any corner (worst random 6.18 h against the corner's 3.75 h).
  - The top-5 corners hold the other 48 variables at nominal.
  - Sampling ran only at h = 1; the `check_h` branch keys on the 8 h h_hat (0), so nothing was checked near 1.06.
- **Endurance alone is fine:** among flyable points, scanning every variable over its interval from the record's corner at h = 1 and 1.0615 found nothing worse than the corner.
- **Related cliff in the record:** the recorded corner itself becomes unflyable between h = 1.3 and 1.4. The report's curve shows "0.000 h" at h = 1.5 with no explanation.
- **Fix:**
  1. Treat "mission not flyable" as its own failure mode with its own direction set (power deficit on the transit), and take h_hat as the minimum over failure modes.
  2. Replace the fixed-direction corner with a search at each h: coordinate flips over all variables from the corner, repeated until no flip worsens, plus a per-variable interior scan. DMDU p. 214-218 uses a global optimisation for the inner maximum.
  3. Run the check at each h_hat, not only at h = 1.
  4. Record why a point returned 0 h and how many did.
  5. Add a test that the corner with low power at h = 1 is found.
  6. Correct the report, the commit claim and the ledger source text ("measured worst case 3.75 h").

### IG-2 (major): empty-weight uncertainty has no effect on R5 or R7, and the R5 margin does not survive it

- **What the code does:** W0 and fuel are held fixed, so a heavier build-up changes nothing. The report says so, but spec 7.2 names composite factor, empty-weight fit and avionics weight among the quantities to propagate.
- **Size of the ignored effect:** the model's own We moves by +524 lb at the weight-harmful corner of U(1). The largest one-at-a-time contributions are `gust_ude_fps` +144, `avionics_uninstalled_lb` +86, `fuselage_fineness` +67, `rotation_angle_deg_pusher` +48 and `wing_t_c` +32 lb.
- **Effect on R5 (probe: W0 raised by dW at fixed wing area and fuel):** the recorded corner at h = 1 gives 3.61 h at +50 lb, 3.47 h at +100 lb, 3.20 h at +200 lb and is unflyable at +300 lb. About +90 lb (5 % of We) removes the guarantee, before IG-1.
- **Effect on R7:** small. At +400 lb the h = 1 corners give take-off 1,584 ft and landing 1,720 ft against 2,500 ft.
- **Zero-effect variables:** 27 of the 53 have exactly no effect on any of the three outputs. These are the weight items, all `station_*`, both tractor entries, `tail_height_over_df`, the `tail_cl_max_*` pair, the tank fractions, and `cbhp_cruise`/`cbhp_loiter` (overridden by the engine table). 42 of 53 have no harmful effect on R5. "53 uncertain quantities" overstates the study.
- **Fix:** add an empty-weight uncertainty that acts on performance. Either a direct band on We with W0 = We + payload + fuel, or the build-up's We(theta) fed into W0. State in the report which variables are inert.

### IG-3 (major): R7 take-off h_hat is 1.59, not 1.70, because a direction reverses above h = 1

- The same coordinate search on the take-off h_hat flips `flap_span_fraction` from lower-end harmful to upper-end harmful (flap drag in the climb-out outweighs CLmax at large h). h_hat falls from 1.697 to **1.592**.
- Landing stays at 1.943. `main_gear_length_in` at its lower end adds 0.2 ft, which is negligible.
- 400 random full corners and a per-variable interior scan found nothing worse for either.
- R7 still passes Gate B, but the recorded number is not the worst case.
- **Fix:** as IG-1 items 2 and 3.

### IG-4 (medium): important uncertainties are outside the model

- **Headwind (R19, 25 kt):** fixed as a requirement. At 35 kt the recorded h = 1 corner gives 3.05 h; at 50 kt, 1.61 h.
- **Oswald e / induced drag:** not banded, though spec 7.2 lists L/D and the loiter sits on the 1.3 V_stall floor where induced drag matters. With e reduced by 0.05 (the 7.1a tolerance) the corner gives 3.59 h and nominal 7.73 h.
- **Not varied, not probed here:** ISA temperature deviation, the engine control law and the shape of the part-power SFC curve (loiter SFC is 1.14 from the table against the brochure's 0.901), `leakage_fraction`, `tail_interference_q`. Trim drag from downwash and tail height is not modelled at all.
- **Engine ±10 %:** defensible as the 7.1a tolerance. Note that high power harms R5 only through a lower table fraction, which is a modelling choice.
- **Fix:** list these as exclusions in the report, or band e and add a headwind sensitivity row.

### IG-5 (low): the R7 mission patch is sound; small inconsistencies in the power multiplier

- **Soundness:** `_build` uses the mission only for the returned `fuel` and `mission` rows. Geometry, CD0, CLmax, D_prop and We do not depend on it, and `fuel_guess` is the record's.
- **Safety:** the context manager restores `_mission` on exceptions, workers are forked single-threaded processes, and hours and fields are evaluated sequentially.
- **Style:** patching a private function with `mock` in production code is fragile. A `mission=False` argument to `_build` would be clearer.
- **Take-off multiplier:** scaling rated bhp in `_takeoff` matches `power_scale` (which multiplies available power everywhere), and D_prop correctly stays at the unscaled value.
- **Inside `_mission` the multiplier is only partly applied:** take-off fuel, `best_rate_of_climb` and the sea-level term of the climb D/T use unscaled bhp. The effect is small.
- **Pre-existing:** `_takeoff` uses flat 241 hp while the table gives 0.985-0.997 of rated at 0-60 kt.

### IG-6 (low): fidelity, loiter computation, reproducibility

- **(10.7):** correct. Weights recover the bands at h = 1, one-sided cases have W = 0, sets are nested, and clipping is an addition that is reported (none at h = 1).
- **(10.8) and bisection:** correct given a correct inner maximum (see IG-1). The test against (5.5) is good, but no test exercises the worst-case search.
- **Loiter hours:** the bisection plus interpolation is correct. Nominal is 8.0000 h and the rebuild matches the record to machine precision.
- **Blanket ValueError handling:** every `ValueError` becomes 0 h or inf silently, which would also hide a genuine bug.
- **Record gaps:**
  - No dirty-tree flag.
  - No hash of the engine table (it matches the run's copy today).
  - No hash of the current `data/task12/ledger.yaml`, which is where the 3.5 h comes from (the record's ledger copy lacks it).
  - `git_commit` is the parent (06a9ab4) of the commit that holds the record (a6a633d); the code is identical between them.
- **Report against record:** the report is generated from the JSON and all its numbers match. It omits the unflyable cliff and the inert variables.

## Owner questions

1. **A member of U(h) that cannot hold 20,000 ft at 1.3 V_stall or faster on the transit: is that a mission failure?**
   - (a) Yes, 0 h, as the code defines it. The R5 guarantee then has h_hat of about 0.86 and fails Gate B. The design returns to Stage 1 for power margin, or the bands for power, eta_p and CLmax are narrowed by measurement.
   - (b) Allow a lower or slower transit. This needs a fallback mission model and a re-run; the endurance-only figure of 1.06 would be an upper bound.
   - (c) Restate R5 again. Note that the 3.5 h was set after seeing 3.75 h (ledger source text), so the guarantee had 0.25 h of margin by construction.
2. **Is the built aircraft's empty weight known or uncertain?**
   - If uncertain, about +90 lb removes the guarantee. Either band We or accept a weighed-aircraft assumption explicitly at Gate B.
   - If weighed, say so, and drop the inert weight variables from the count.
3. **Should headwind (25 kt) and Oswald e stay outside the horizon?** Both move the h = 1 corner by more than the 0.25 h margin.

## Verdict

- **R7 (field length):** yes with actions. h_hat is about 1.59 for take-off (not 1.70) and 1.94 for landing; both are well above 1 and robust to weight growth. Correct the number and the search.
- **R5 guarantee (3.5 h at h = 1):** no. Under the module's own definition h_hat is about 0.86 (IG-1). Independently, the 0.06 margin does not survive empty-weight growth of about 90 lb (IG-2), a 0.05 loss in e, or 10 kt more headwind (IG-4).
- **R5 at 8 h, h_hat 0:** correct by construction.

Probe scripts are in `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/`:

- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/common.py` (shared setup)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/p2.py` (scan from the record's R5 corner)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/p3.py` (counterexample)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/p4.py` (R5 direction search)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/p6.py` (failing leg, interior scan)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/p7.py` (R7 search)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/p8.py` (weight and headwind)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/p9.py` (inert variables, e)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/ig_rerun.json` (reproduction run)

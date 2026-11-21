# Gate A, round 4: Task 12 Stage 1 re-sized around the TP100 App. K engine (2026-11-21)

**Outcome (reviewer's recommendation): PASS WITH ACTIONS for the configuration only** (pusher,
conventional tail, sponson gear, TP100). The sizes (W/S 9, A 9, 3,520 lb) are **not frozen** and
Stage 3 does not start on them. Package reviewed: `docs/validation/2026-11-20_task12_conceptual_engine.md`
(records `runs/task12/stage1/2026-11-20f/`). Spot check by the author: the TP100 table gives 244.9 hp at
104 kt and 249.6 hp at 137 kt at sea level, confirming R4-1's premise.

## 1. Owner rulings at round 4

To be recorded as they are given (questions asked one at a time).

| Question | Ruling |
|---|---|
| 1. Altitude rating and R12 ceiling | **Relax the ceiling**: keep the conservative engine law (pi_c held at the sea-level rating) and replace R12's 25,000 ft service ceiling by a lower ceiling or a climb-rate requirement at 20,000 ft, sized by a run |
| 2. V_C | **One low placard**: a single V_C in EAS at every altitude, enforced by the autopilot; structure and gusts sized at it; value set from a run with a margin over the fastest mission leg |
| 4. Robustness | **Stated margins**: installed power at most 95 % of the engine's, service ceiling at least 500 ft above R12, negative gust at least 0.1 g inside the limit; every trade and band end (with the engine table's SFC and power at +-10 %) run through the full compliance check and reported |
| 3. Ceiling and V_C values (from option runs: lightest compliant pusher for ceilings 25,000 / 23,000 / 22,000 ft and 300 ft/min at 20,000 ft, each at 100 and 110 kt EAS) | **Service ceiling 23,000 ft; V_C 100 kt EAS.** Probe result at that setting: W/S 15, A 9, W0 3,054 lb, span 42.8 ft (to be confirmed by the recorded Stage 1 run) |

## 2. Actions

| Finding | Status |
|---|---|
| R4-1 to R4-12 | open |

## 3. Independent review (verbatim)

# Gate A round 4 review: Task 12 Stage 1 around the TP100 App. K engine (2026-11-20f)

Read-only review; no repository file was modified.

**Inputs checked**
- Package `docs/validation/2026-11-20_task12_conceptual_engine.md`, records `runs/task12/stage1/2026-11-20f/`, code at HEAD `13572a7`.
- `python -m pytest -q tests/task12`: **135 passed** (8.05 s), matching the recorded `135 passed in 8.47s`.
- Ledger, engines and table hashes match `inputs.json`.
- `python -m measurement.tp100_engine` regenerates `data/task12/tp100_table.json` bit-identically (sha256 `03edd546…`).
- `stage1.analyse("pusher", 9, 9)` reproduces the record exactly (W0 3,519.99 lb, fuel 962.27 lb, ceiling 25,333.6 ft, negative gust -1.7771).
- Sizing code is unchanged since the recorded commit `2da97e9`; only `conceptual/report.py` changed afterwards (+8/-2 lines).

Probe scripts are `p1.py` to `p12.py` in `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/`, run with `PYTHONPATH=. python <script>` from the repo root. Every probe number below comes from those scripts; none is a repo record.

## Summary

The App. K table is wired into the TP100 design path consistently enough that no old piston lapse or flat SFC leaks into the mission, ceiling, turn or cruise rows. The design point itself is not robust:

- The R9 negative-gust row passes only because V_C is computed with engine power taken at the wrong speed (R4-1).
- The compliant window is narrower than every engine and aero uncertainty the package carries (R4-2).
- The wing loading of 9 lb/ft^2 follows from one unverified control-law assumption; the other bound gives W/S 21 and 433 lb less (R4-3).
- The part-power SFC behind the +1,147 lb is produced outside App. K's stated validity for this low-pressure-ratio engine (R4-4), and the "MSH" burner is coded as constant specific heat (R4-5).

## Findings

### R4-1 (blocker for freezing sizes): R9 negative-gust compliance comes from an inconsistent engine speed argument

- **Evidence.** `conceptual/uav.py:370-371` finds the sea-level maximum level speed with `bhp * _lapse(model, h, atm, V_cr)`. `V_cr` is the best-range speed at 20,000 ft (104 kt), not the speed being solved for. The table gives 245.6 hp there and 249.8 hp at V_max.
- **Probe p3, self-consistent V_max.**

| Treatment | V_max (kt EAS) | n_gust, zero-fuel, sea level | Negative gust | R9 (-1.8) |
|---|---|---|---|---|
| As recorded | 137.1 | 3.777 | -1.777 | met |
| Table power at V_max | 138.5 | 3.805 | -1.805 | fails |
| Also CD0 at V_max (code uses CD0 at 180 ft/s, `uav.py:337`) | 139.0 | 3.815 | -1.815 | fails |
| Table capped at rated 241 hp | - | - | -1.770 | met |

- The table exceeds the rated 241 shp above 70 kt at sea level (up to 270 hp at 230 kt). The brochure calls 241 hp "max. output", so a cap is plausible, but neither treatment is stated. The row's pass or fail turns on a 2 % power detail.
- **Fix.** Solve V_max with power evaluated at V_max (fixed point) and CD0 at that speed. Decide and record whether sea-level power is capped at the rating (gearbox limit). Then re-select.

### R4-2 (major): the chosen point sits between two knife-edges, so the stated margins are not usable

- **Evidence (probe p4, W/S 9, A 9, tail re-sized each time).** Anything that worsens the aircraft fails R12; anything that improves it raises V_max, hence V_C and the gust, and fails R9.

| Change | W0 (lb) | Ceiling (ft) | Negative gust | Fails |
|---|---|---|---|---|
| Base | 3,520 | 25,334 | -1.777 | none |
| Table SFC +5 % | 3,643 | 24,811 | -1.739 | R12, power |
| Table SFC +10 % | 3,771 | 24,302 | -1.701 | R12, power |
| Table SFC -10 % | 3,299 | 26,316 | -1.844 | R9 |
| Table power -5 % | 3,466 | 24,740 | -1.744 | R12, power |
| Table power +7 % | 3,601 | 26,085 | -1.817 | R9 |
| eta_p 0.78 | 3,555 | 24,777 | -1.742 | R12, power |
| eta_p 0.85 (band top) | 3,460 | 26,566 | -1.852 | R9 |
| Sensor drag 0.2 ft^2 (band low) | 3,510 | 25,504 | -1.809 | R9 |
| Wing laminar fraction 0.5 (band top) | 3,493 | 26,491 | -2.019 | R9 |
| Section CL_max 1.3 (band low) | 3,510 | 25,121 | -1.806 | R9 |

- Spec 7.1a tolerances (power ±10 %, SFC ±10 %, ceiling ±1,000 ft, gust ±5 %) are all wider than this window. Lift slope +5 % alone gives n = 3.84 (p3).
- **Ceiling margin.** The ceiling uses CD0 at 250 ft/s (`uav.py:350`, `:717`) while the climb is at about 135 ft/s. With CD0 at the climb speed (0.0201 against 0.0195) the ceiling is 25,193 ft: the margin is 193 ft, not 334 ft (p2).
- **Package section 9 hides this.** The sensitivity table reports only "Power OK". `trades.csv` shows `eta_p=0.85 (hi)`, `sensor_drag_area_ft2=0.2 (lo)`, `laminar_fraction_wing=0.5 (hi)` and `airfoil_cl_max=1.7 (hi)` as "True", although three of them fail R9 once the tail is re-sized. It has no engine-table rows at all.
- **Fix.** Run every trade and band end through `compliance()` and print the failed rows. Add table SFC ±10 %, table power ±10 % and the control-law bound as rows. Select a point that keeps the compliance rows at stated margins (for example ceiling at least +500 ft, gust at least 0.1 g), or record the owner's acceptance of zero robustness. Evaluate ceiling CD0 at the climb speed.

### R4-3 (major): the 9 lb/ft^2 wing loading is produced by one unverified assumption, and the package has no run of the alternative

- **Evidence.** The control law holds pi_c at its sea-level rating (`measurement/tp100_engine.py:19-22`), which makes shaft power scale as delta·sqrt(theta): 103.6 hp at 20,000 ft, 82 hp at 25,000 ft. That is below the piston lapse (13.9) the previous design used (113.6 hp at 20,000 ft).
- **Probe p5/p6, same cycle with the Tt4 limit only.** 164 hp at 20,000 ft and 147 hp at 25,000 ft. The full `carpet` + `first_compliant` pusher selection gives:

| Control law | W/S | A | W0 (lb) | Fuel (lb) | Ceiling (ft) | Negative gust |
|---|---|---|---|---|---|---|
| pi_c held (package) | 9 | 9 | 3,520 | 962 | 25,334 | -1.777 |
| Tt4 limit only (probe) | 21 | 9 | 3,087 | 1,044 | about 33,000 (table clamps above 30,000) | -1.34 |

- Wing area moves from 391 ft^2 to 147 ft^2 and span from 59 ft to 36 ft. The brochure does not say which law applies.
- **Physical sense of W/S 9.** Stall 44 kt, take-off 549 ft against a 2,500 ft limit, loiter on the 1.3 V_stall floor for all 16 sub-steps (CL 0.86, 53 kt EAS), gust n 3.78 at only 137 kt. The wing is sized solely to reach 25,000 ft on 82 hp. It lies below the wing loadings Raymer's (15.46) wing-weight fit was built on: the equation gives 1.56 lb/ft^2 where Table 15.2 gives 2.5.
- **Stale risk text.** Section 11 says a flat-rated engine gives "about 50 % more power at altitude". That is hard-coded (`report.py:709`). The Stage 3 record gives +51 to +63 % at 20,000 ft and +70 to +85 % at 25,000 ft, the altitude that binds.
- **Fix.** Add both control-law bounds to the Stage 1 records (a second table, hash in `inputs.json`) and report both designs. Do not freeze sizes until the maker's altitude rating is in hand or the owner chooses a bound.

### R4-4 (major): the part-power SFC is produced outside App. K's stated assumptions for this engine

- **Evidence.** `off_design` holds tau_tH and pi_tH constant because stations 4 and 4.5 are choked (module docstring; library notes for p. 597-601, book example pi_c = 30). For the calibrated TP100 (pi_c 4.11), probe p11 gives:

| Condition | Tt4 (R) | pi_c | LP turbine pressure ratio 1/pi_tL | Choked (critical 1.832 at gamma_t 1.3) |
|---|---|---|---|---|
| Rated, sea level | 2,200 | 4.11 | 2.02 | yes |
| Cruise out | 1,790 | 3.81 | 1.90 | marginal |
| Loiter start | 1,601 | 3.38 | 1.67 | no |
| Loiter end | 1,536 | 3.24 | 1.60 | no |

- The HP turbine ratio is 1.88 at design. Five of the eleven family members have 1/pi_tH between 1.55 and 1.70, so they are unchoked at their own design point.
- The whole 8 h loiter (52 % of mission fuel, mean SFC 1.219) is therefore computed with a compressor-turbine match the method does not justify. The direction of the error is unknown.
- The family spread quoted in section 11 ("under 0.2 % in power and 2 % in SFC") is a spread among models sharing this assumption, so it is not an uncertainty. It is also hard-coded (`report.py:703`), and the Stage 3 cruise-back row is 1.234 to 1.265, which is 2.5 %.
- The exit nozzle is designed at M9 = 0.088 (Pt9/P0 = 1.005), which makes (K.21) very sensitive.
- **Fix.** Have `table()` record the turbine pressure ratios and flag cells where 4 or 4.5 is unchoked. State the validity limit in the package. Carry a part-power SFC band (at least ±10 %, probe: W0 3,299 to 3,771 lb at this point) until a maker's part-power point exists. Reword the family-spread row.

### R4-5 (major): the "MSH" gas model in the code is constant-specific-heat at the burner; probable cause of the offset reported as "cause not found"

- **Evidence.** The library notes for Mattingly 4.2.8 (p. 115-118) define MSH as constant specific heats everywhere except the fuel flow, which is computed from (4.10a) with variable-specific-heat enthalpies. `turboprop_cycle.py:106` and `:167` compute f with cp_c·Tt3 and cp_t·Tt4 (the 4.10a-CPG form), while the module docstring calls the model MSH.
- The observed mismatch has the matching signature: design-point S is high by 2.5 % at pi_c 5 and 7.5 % at pi_c 35, growing with Tt3; part-throttle S is high by 11-14 %.
- A hand estimate from standard air-table enthalpies (not a run, not from the repo) suggests constant cp_t = 0.295 overstates f more at Tt4 near 1,600 R than at 2,200 R, by about 5 to 7 %. If so, the loiter SFC in the table is pessimistic by that order, even after calibration at the rated point.
- `test_optimum_envelope_figs_k2_k3` accepts S within 8 % where the measured gap is 7.5 %. The Stage 3 engine report prints the envelope table with no tolerance or verdict column.
- **Confirmed correct.** gamma_t = 1.3 is well supported: with cp_t = 0.295 it gives R_t = 53.0 ft·lbf/(lbm·R) against R_c = 53.4, while the printed 1.4 gives 65.6. The three flagged misprints (K.18-CPG exponent, unchoked nozzle line, F = m0 C h0 / V0) are read sensibly. I checked (K.6), (K.7), (K.8), (K.15), (K.16), (K.17), (K.20) and (K.21) line by line against the notes and found no other deviation.
- **Fix.** Implement the burner enthalpy with an open variable-cp property set, re-run the K.2/K.3/K.9 comparisons with stated tolerances fixed beforehand, regenerate the table, and re-size. Until then state the design-point S mismatch as a failed validation with its numbers.

### R4-6 (major): R18 (V_C placard 150 kt EAS) no longer acts; the structure is sized at an implicit, altitude-dependent V_C

- **Evidence.** `uav.py:373-375` takes min(V_max level, placard) at each altitude: 137.1 kt EAS at sea level and 84.1 kt EAS at 20,000 ft. Design q is 63.7 psf; at round 3 it was 76.2 psf at the placard. The ledger's R18 text says the structure and gust loads are sized at 150 kt.
- **Probe p9, one V_C (EAS) at all altitudes, tail re-sized.** The 20,000 ft zero-fuel case governs.

| Single V_C (kt EAS) | W0 at (9, 9) (lb) | n at altitude, zero-fuel | Fails |
|---|---|---|---|
| 150 (R18 as worded) | 3,981 | 4.91 | R9, R12, power |
| 137 | 3,806 | 4.62 | R9, R12, power |
| 120 | 3,594 | 4.22 | R9 |
| 110 | 3,475 | 3.98 | R9 |
| 100 | 3,381 | 3.73 | none |
| 90 | 3,340 | 3.47 | none |

- As coded, the airframe is cleared only to 84 kt EAS at 20,000 ft, 8 kt EAS above the outbound cruise (104 kt TAS). An idle descent exceeds that unless the autopilot enforces a schedule nobody has stated. This reopens round-2 finding N5 (V_C from surplus power).
- **Related stale text.** The summary says "with the V_C placard the design q and gusts are the same for both engines" (`report.py:359-361`, selected by the ledger flag, not the result). Probe p10: rubber q 55.7 psf and n_limit 3.80; TP100 at Table 3.4 q 76.2 psf and n_limit 4.09; PT6A-42 n_limit 4.46. The +298 lb "engine itself" split therefore includes gust and q effects, and both comparison rows exceed the -1.8 limit while shown without a flag.
- **Fix.** Owner ruling on V_C (question 2). Then record V_C and V_D as EAS values in the ledger, size gust and q at them at every altitude, and generate the summary sentence from the computed q and n.

### R4-7 (major): the 1 x 1 grid hides lighter compliant designs; the tractor optimum on the grid corner is an artefact

- **Evidence (probe p4, off-grid points through `analyse` + `compliance`).**

| Concept | Point (W/S, A) | W0 (lb) | Ceiling (ft) | Negative gust | Status |
|---|---|---|---|---|---|
| Tractor | 8, 6 (recorded) | 3,135 | 25,440 | -1.620 | compliant |
| Tractor | 8.5, 6 | 3,087 | 25,226 | -1.669 | compliant |
| Tractor | 9, 6.5 | 3,055 | 25,604 | -1.785 | compliant, 80 lb lighter |
| Tractor | 8, 5.5 and 8, 5 (below the A grid) | - | - | - | fail the ceiling |
| Pusher | 9, 9 (recorded) | 3,520 | 25,334 | -1.777 | compliant |
| Pusher | 9, 8.5 | 3,492 | 25,098 | -1.739 | compliant, 28 lb lighter |

- The tractor grid edges themselves are not hiding anything: W/S 7 and 6 are heavier (3,255+ lb).
- The compliant pusher region is a wedge about 1 lb/ft^2 by 1.5 in A, closing near W/S 9.3. Every pusher point from W/S 9.5 up fails R9 or R12.
- On-grid, (9, 9) is the lightest compliant pusher. I checked the six carpet points whose carpet W0 lies between 3,448 and 3,520 lb; all fail (p12).
- `first_compliant` stops at the first compliant candidate in carpet order, which is not guaranteed lightest after the tail resize (`stage1.py:326-339`). It is harmless here.
- With R4-1 and the ceiling CD0 correction applied, neither (9, 9) nor (9, 8.5) would pass. My estimate from the probes, not a run, is a point near W/S 8.5, A 9 at about 3,560 to 3,600 lb.
- **Concept score.** With the off-grid values (3,055 against 3,492) the pusher scores 4.05 against 3.95, so the order holds. If the R9 negative row were dropped (question 2), the on-grid values are tractor 2,880 at (16, 11) and pusher 3,494 at (10, 10): the score is 3.95 each, a tie.
- **Fix.** Refine the grid to 0.5 or finer around the lightest compliant point for both concepts, or continue the candidate loop until carpet W0 exceeds the best final W0. Record the refinement in `selection_<concept>.json`.

### R4-8 (major, process): with App. K inside Stage 1, the Stage 3 engine rows are no longer independent

- **Evidence.** Spec section 1 item 3 and section 7 require the measuring source to differ from the design source. Power at altitude, SFC, ceiling and mission fuel now come from the same cycle table in both stages.
- Spec 7.1a still names `2026-11-20d/design_pusher.json` and compares against "the piston lapse (13.9)" and "the datasheet value". Its status line still says Gate A has not been held, and R16 to R18 are not in the spec.
- `measurement/stage3_engine.py:111` and `:131` read `ledger_used["cbhp_*"]`, which is 0.901 for this design. `design_pusher.json` itself records `cbhp_used: {cruise 0.901, loiter 0.901}` although the mission used 0.973 and 1.219. A Stage 3 re-run would compare against values Stage 1 did not use.
- **Fix.** Revise spec 7.1 and 7.1a before Stage 3: name what now measures the engine (maker data, or a different open part-load method), update the reference record, and fix the `cbhp_used` field.

### R4-9 (minor): stale or hard-coded text in the package

- Second status paragraph: "Gate A record of the previous design … Gate A: passed with actions" runs straight into "Generated … from runs/task12/stage1/2026-11-20f", so it reads as if this package passed (`report.py:337`).
- Section 7: downwash 0.381 "(far-wake value in place of Raymer's chart, conservative)" (`report.py:612`). Section 9 of the same package says it is not conservative.
- Section 11: sponsons "about 12 % of W0 at the current size" (`report.py:695`). The records give 213 lb, which is 6.1 % of 3,520.
- Section 9: three `engine_cbhp=…` trade rows all give 3,520 lb because the table overrides them (`stage1.py:196-197`). They read as "SFC has no effect".
- Section 5: engine table prints `0.49999999999999994 / 0.5999999999999999`. The PT6A-42 and TP-R90 rows use Table 3.4 and the piston lapse beside the TP100's App. K row; the note says so but the W0 column invites a comparison (3,551 against 3,520) that is not like for like. `engines.yaml` holds 0.601 for the PT6A-42, unused.
- Section 10 lists no test for `engine_model`, `turboprop_cycle`, `_leg_speed` or `first_compliant`.
- `engines.yaml` header still says the maker's pages could not be retrieved, although the TP100 entry is now from the brochure.
- **Fix.** Generate each of these from the records or delete it.

### R4-10 (minor): brochure limits that bear on requirements are missing from this package

- The starting envelope ends at 19,685 ft, below the 20,000 ft loiter (R6). It appears only in the Stage 3 engine report. The R6 row checks only the 29,528 ft operating limit.
- The output shaft turns at 2,158 rpm; the ledger still carries an assumed 2,000 rpm ("not from the library"). There is no weight effect at this design.
- **Fix.** Add a relight note to the R6 row and the risk list; set `propeller_rpm` from the brochure.

### R4-11 (minor): small inconsistencies in the engine treatment, none changing a result on its own

- Sea-level climb and take-off use 241 hp flat (`uav.py:348`, `:743`, `_thrust_fn`); the table gives 239.4 hp at the 53 kt climb speed. Margins are large (1,478 against 1,000 ft/min).
- The climb segment holds the sea-level best-climb TAS (53.2 kt) to 20,000 ft, where the stall TAS at W0 is 60.8 kt (`uav.py:277-279`). Drag at altitude is evaluated at CL 1.75 against CL_max 1.35. Climb fuel is 67 lb; the effect is small and conservative.
- `_leg_speed` computes shaft power with CD0 at 250 ft/s while the Breguet step uses CD0 at the chosen speed (`uav.py:296-303`). The effect is under 1 %.
- V_max at altitude takes the lapse at a fixed 150 kt (`uav.py:747`), although V_max is 119 kt.
- Below 10 % power the SFC is clamped (optimistic). It is never reached: the lowest throttle in the mission is about 0.46.

**Checked and found correct**
- Units: every `model.lapse` and `model.bsfc` call passes knots.
- Table interpolation agrees with the direct cycle to 0.15 % at the mission points (p2).
- `_leg_speed` objective is correct (fuel per distance or per time). The 2 % grid picks 104.6 kt where a 0.1 % scan gives 104.7 kt.
- Minimum-fuel cruise above the max-L/D speed (87 kt) is right physics for a falling SFC. The floor sets the loiter because fuel flow rises monotonically with power.
- Quadrupling the Breguet sub-steps changes W0 by +2 lb (p7).
- `rg piston_power_lapse|cbhp_` finds no leak of (13.9) or a flat SFC into the TP100 path.

### R4-12 (minor): reproducibility and tests

- `inputs.json` records the commit and three hashes but no dirty-tree flag, no Python or numpy version, and no generator commit for the table. The package was rendered by a `report.py` one commit later than the recorded commit.
- No test exercises `_mission` or `_leg_speed` with a `TableEngine`, `first_compliant`, or the V_C path.
- No non-public material was found in the diff; the brochure is cited, not committed.
- **Fix.** Add the fields and the tests.

## Checklist (spec section 6)

| # | Verdict | Note |
|---|---|---|
| A1 | no | R9 negative gust margin is negative under consistent power (R4-1) |
| A2, A3 | yes | weight and fuel close; reproduced |
| A4 | yes | static margin 0.106 / 0.094; rotation tail CL 0.978 of 1.0; downwash caveat (R4-9) |
| A5 | partly | larger of manoeuvre and gust is used, but at an unstated V_C schedule (R4-6) |
| A6 | partly | power met by 5 hp under one control law (R4-3); the TP100 is 1.84 times the rubber power, and the rubber baseline uses Table 3.4 and the piston lapse |
| A7 | partly | engine table has no band in the sizing (R4-2, R4-4) |
| A8 | yes for Raymer; no for the new engine path (R4-12) |
| A9, A10 | yes | score margin thin (R4-7) |
| A11 | partly | engine risks now point to "maker's data" only (R4-8) |
| A12 | open | R12 ceiling default and R18 need re-confirmation (questions 1, 2) |

## Questions for the owner

1. **Which altitude rating to design to, and is R12's 25,000 ft ceiling kept?** The ceiling default combined with the pi_c-held law sets the whole wing.
   - (a) Keep both: W/S 9, about 3,520 to 3,600 lb, 59 ft span, no robustness.
   - (b) Wait for the maker's altitude rating and part-power curve before sizing.
   - (c) Carry both bounds as two designs (W/S 9 at 3,520 lb and W/S 21 at 3,087 lb) into Stage 3.
   - (d) Replace the ceiling by a climb-rate requirement at 20,000 ft. This needs a run; I did not probe it.
2. **V_C and the negative limit.**
   - (a) One low placard, for example 100 kt EAS at all altitudes: (9, 9) meets every row at 3,381 lb with gust n 3.73, and the autopilot limit is explicit.
   - (b) Keep V_C = level-flight maximum per altitude (137 and 84 kt EAS) and state it as the placard schedule.
   - (c) Keep 150 kt EAS as written: n 4.9, about 3,980 lb, and power fails at this point.
   - (d) Drop the "negative gust within -1.8" row and size the structure to the gust case, as the positive side already does. The pusher then gains about 26 lb on-grid, and the concept score ties (R4-7).
3. **Robustness margin at Gate A.** Should the chosen point hold stated margins (ceiling in feet, gust in g, power in percent) under the engine and aero bands, at a weight cost, or is a nominal-only pass acceptable knowing Stage 3 tolerances are wider than the window?
4. **What measures the engine in Stage 3 now?** Maker data only (blocking), a second open part-load method, or accept the engine rows as not independent and say so in the spec.
5. **Concept.** Confirm the pusher stays frozen given the thinner score margin: 4.05 to 4.08 against 3.95, and 3.95 each under option 2(d).
6. **Wind.** Cruise is about 100 kt TAS and loiter 73 kt TAS, with R11 setting no minimum speed. Is a headwind allowance wanted at 20,000 ft?

## Outcome recommendation

**PASS WITH ACTIONS**, limited to the configuration: pusher, conventional tail, sponson gear and the TP100 stay frozen. **The sizes (W/S 9, A 9, 3,520 lb) should not be frozen and Stage 3 should not start on them.**

Closing conditions, to be re-checked by this reviewer:
- R4-1: self-consistent V_C and re-selection.
- R4-2: compliance on every trade and band end; engine bands in the sizing.
- R4-6: owner ruling on V_C, then loads sized at it.
- R4-7: grid refinement for both concepts.
- R4-3 to R4-5 dispositioned: both control-law bounds recorded, validity flags in the table, burner model corrected or the failed validation stated.
- R4-8: spec 7.1 and 7.1a revised.
- R4-9: stale text removed.

On a strict reading of A1, a compliance row that fails under the package's own stated engine treatment makes this a FAIL back to Stage 1. The remedy is the same list.

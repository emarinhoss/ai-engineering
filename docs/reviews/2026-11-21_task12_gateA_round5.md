# Gate A, round 5: check after the Stage 3 return (2026-11-21)

**Outcome: PASS WITH ACTIONS** (independent reviewer). Design: pusher W/S 15, A 11, W0 3,198 lb;
record `runs/task12/stage1/2026-11-21e/`, package `docs/validation/2026-11-21_task12_conceptual_stage3return.md`.
Required before the package is final: G-1 (engine text) and G-2 (tail-height band and its trade row).

## Owner rulings

| Question | Ruling |
|---|---|
| 1. Rotation sizes the tail | **Measure it first**: keep the rule and sizes; the ground-effect rotation check is the next Stage 3 item |
| 2. Engine model bias | **5 % SFC allowance** in sizing (ledger `engine_sfc_allowance` 1.05) |

## Author's disposition

- G-2: the tail-height band's low end becomes 0.1 D_f (a tail in the wing plane cannot be evaluated by the planar-wake lattice); an input gate refuses heights below one trailing-leg spacing.

## Independent review (verbatim)

# Gate A check after the Stage 3 return

Read-only check; no repository file was changed. **Outcome: PASS WITH ACTIONS.** The sizes (pusher, W/S 15, A 11, W0 3,198 lb) hold under independent probes. The package text does not yet describe the engine it was sized with, and that must be fixed before it is called final.

## Verification summary

- **Tests:** `python -m pytest -q tests/task12` gives 167 passed (55.5 s), matching `runs/task12/stage1/2026-11-21e/test_report.txt`.
- **Provenance:** ledger, engines and engine-table hashes in `inputs.json` match both the run-folder copies and the current `data/task12/` files. Since the recorded commit `311d891`, only `conceptual/report.py` has changed.
- **Reproduction:** `stage1.analyse("pusher", 15, 11, L, engine)` with the run's ledger and table reproduces the record to the last digit.
  - W0 3,197.781 lb, fuel 1,003.944 lb, ceiling 23,521.34 ft, negative gust -1.53247.
  - Static margins 0.129527 / 0.070473, downwash 0.368535, tail scale 1.910723.
  - All 30 compliance rows match `compliance_pusher.csv`; none fails.
- **Margins are real:**
  - Power: 233.55 hp needed of 241, which is 3.09 %; the ceiling row binds.
  - Ceiling: 23,521 ft against 23,500 ft, so 21 ft of the 500 ft margin is left.
  - Negative gust: -1.532 against -1.700.
- **Selection:** on a 132-point 0.5 lattice (W/S 12 to 17.5, A 8.5 to 13.5), each point through `analyse` and `compliance`, (15, 11) is the lightest compliant point.
  - Next are (14.5, 10.5) at 3,199.4 lb, (14, 10) at 3,202.3 lb and (13.5, 9.5) at 3,202.8 lb.
  - Six quarter-step neighbours give nothing lighter that complies: (15.25, 11.25) is 3,197.4 lb but fails the ceiling margin by 21 ft.
- **Engine table:** `tp100_engine.table()` regenerates the table bit-identically (sha256 `3f422ba6…`).
  - Member: Tt4 2,200 R, e_c 0.80, e_t 0.85, pi_c 3.414, burner `msh`.
  - Family: 17 of the 27 grid members; 5 do not calibrate and 5 fall below pi_c 3.0. The range is pi_c 3.08 to 4.52 and the nominal is inside it.
  - Nothing in the Stage 1 path reads a constant-cp table or the old nominal.
- **Engine trades reproduce:**

| Case | W0 (lb) | Ceiling (ft) | Power margin | Fails |
|---|---|---|---|---|
| SFC x1.1 | 3,428.5 | 22,476 | -3.2 % | ceiling, power |
| SFC x0.9 | 2,982.1 | 24,529 | 9.0 % | none |
| power x0.9 | 3,125.4 | 22,118 | -5.5 % | ceiling, power |
| power x1.1 | 3,270.8 | 24,729 | 10.1 % | none |

- **Lattice downwash geometry is correct.**
  - The planform passed to the lattice is Stage 1's wing: same span, A, taper, root and tip chords, unswept leading edge, and reference point at 0.25 MAC.
  - The tail station is the wing quarter-MAC plus the tail arm, which is where `layout` puts the tail's aerodynamic centre.
  - Height is 0.4 x 3.495 = 1.40 ft; five stations span the tail semi-span.
  - Twenty stations give 0.3684 and chord weighting gives 0.374, against the record's 0.3685.
- **Stage 1 and Stage 3 agree on this design.** `stage3_aero.measure` on the new record gives 0.3692 (fine lattice) against Stage 1's 0.3685 (medium). Static margins differ by 0.0004 MAC.
- **Cache and loops are safe.** The cache key holds every geometric input, rounded to 0.001, and the rounding is applied on every call, so results do not depend on cache state. The downwash depends on the arm, tail span and wing, not on the wing position that `layout` bisects, so there is no hidden loop. The tail-resize loop recomputes it on each pass.
- **Spec 7.1c figures match the records:** 0.389 against 0.338, empty-fuel margin 0.045, fuel -3.6 % and W0 -3.0 %.

Probe scripts, run with `PYTHONPATH=. python <script>` from the repo root (probe numbers are not repo records):
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/g1.py` (reproduction)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/g2.py` (downwash geometry and sensitivities)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/g3.py` (tail drivers, downwash alternatives)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/g4.py` (selection lattice; output in `g4.out` beside it)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/g5.py` (engine table and family)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/g6.py` (quarter-step neighbours, engine band ends, family extremes)

### What drives the 1.91x horizontal tail

- **The tail did not grow.** Its area fell from 115.6 ft^2 (`2026-11-21d`) to 99.0 ft^2, and S_h/S is unchanged at 0.467 against 0.465. The scale rose from 1.76 to 1.91 because the Table 6.4 baseline shrinks with the smaller wing and chord.
- **Rotation sizes it, not stability.** At 0.8 V_TO (43 kt, q 6.4 psf) the main-wheel reaction supplies -0.99 of the -1.08 moment coefficient the tail must balance.
- **The cause is the pusher's gear.** The 60 in gear puts the CG 6.72 ft above the ground, so the 15 deg tipback rule places the wheels 2.07 ft behind the forward CG.
- **It rests on assumed ledger values.** Probes at (15, 11), one value changed each:

| Change | Tail scale | W0 (lb) | Power margin |
|---|---|---|---|
| Record | 1.91 | 3,198 | 3.1 % |
| `tail_cl_max_rotation` 1.2 (was 1.0) | 1.51 | 3,143 | 5.7 % |
| `tipback_angle_deg` 12 (was 15) | 1.47 | 3,138 | 5.9 % |
| `cl_ground` 0.5 (was 0.1) | 1.37 | 3,123 | 6.6 % |
| `rolling_mu` 0 (was 0.03) | 1.63 | 3,159 | 4.9 % |

- **Verdict:** the arithmetic is right and follows Raymer's rule, but a tail at 46 % of wing area is the product of that rule and those assumptions. Round-4 item C-3 (rotation with ground effect) is still open and is now the largest lever on the design. Take-off uses 773 ft of the 2,500 ft allowed, so a later rotation is affordable.

## Findings

### G-1 (major, documentation): the package describes the old engine and omits the 7.1c rulings

Evidence is in `docs/validation/2026-11-21_task12_conceptual_stage3return.md`; the text is hard-coded in `conceptual/report.py:798-799` and nearby.

- **Risk row, section 11:** "part-throttle trend unvalidated (11-14 % offset), constant-cp burner (design-point S 2.5-7.5 % high…)". The table is built with the MSH burner. `runs/task12/stage3/2026-11-21/appk_validation.json` shows the bias now has the opposite sign:
  - design-point S is 4.6 to 5.8 % below the book;
  - part-throttle S is 6.8 to 8.6 % below the book;
  - 16 of 18 rows pass.
- **Section 9, out-of-calibration list:** repeats the "11-14 % offset" claim.
- **Nowhere stated:** the burner, the widened family, the pi_c 3.0 cut-off or the nominal member. The words "MSH" and "variable-cp" appear only in action 2, as work still to do.
- **Validity statement incomplete.** The package says the choked-turbine assumption fails in 100 % of cruise_out, loiter and cruise_back sub-steps. It also fails at take-off and climb:
  - LP turbine ratio 1.779 at sea-level full power against the critical 1.832;
  - HP turbine ratio 1.767 at the design point.
  - The record prints `turbine_unchoked_fraction` 0.0 for take-off and climb because `uav._mission` writes a placeholder there, not a check.
  - Spec 7.1c item 2 says "everywhere"; the package does not.
- **Status and section 0:** no row for the Stage 3 return, and the "rulings in force" bullet lists round 4 only. The status says "round 4 reviews this design", but round 4 reviewed `2026-11-21d`. The previous gate design (3,342 lb, W/S 13.5, A 10.5) and the -144 lb change are not stated.
- **Section 12:** action 2 (variable-cp burner, re-validation, regenerated table) and the downwash half of action 3 are listed as open, though both are done.
- **Section 5:** "At full throttle (99 % or more…): climb_sea_level. The minimum-fuel speed against the headwind sits on the power limit there, so the transit has no power margin". The fixed sentence now attaches to the climb; cruise_out is at throttle 0.977 in this record.

Every other number I checked matches the records:
- weights 3,198 / 1,694 / 1,004 lb and span 48.4 ft;
- tractor 2,838 lb and scores 4.07 / 3.95;
- rubber 2,076 lb at 148 shp, with the +148 / +973 lb split;
- 2,902 lb for the Gate A treatment, and sponsons 75 lb / +313 lb;
- empty fractions 0.530 / 0.525 and first pass 2,110 lb;
- wind limits 25 / 51 / 67 kt;
- 96 band ends, of which 25 use a margin and 15 break a requirement;
- downwash 0.369 and the section 7 rows.

**Fix:** generate the engine text from the table's `member` and `burner` fields and the validation record. State validity for every segment, with the take-off and climb ratios. Add a 7.1c row to section 0 and to the rulings bullet. Correct the status and the action list, and make the full-throttle sentence conditional on which legs are listed.

### G-2 (moderate): the low band end of `tail_height_over_df` is evaluated inside the wake sheet

- **Evidence:** the band is [0.0, 0.9]. At z = 0 the tail points lie in the lattice's planar wake and the result is mesh noise. For the record geometry it is 1.03 on the medium lattice and 0.74 on the fine one. From 0.1 D_f upward the two lattices agree within 0.008.
- **Effect:** the trade row `tail_height_over_df=0 (lo)` (3,187 lb, no failure) used 0.503 and is not a meaningful number. Had the points landed where the lattice gives 1.03, the tail would have had no stabilising effect. `lattice_downwash` has no input gate.
- **Fix:** set the band's low end to about 0.1 D_f, or refuse |z| below one trailing-leg spacing (half-span / 30 on the medium lattice). Re-run the trade row.

### G-3 (minor): the downwash and the wing lift slope in the neutral point belong to different wings

- **Evidence:** the lattice downwash is per unit angle of attack of a bare wing with slope 5.115 per rad. `neutral_point` uses the installed slope 5.633, which adds the fuselage factor, exposed-area ratio, airfoil efficiency and Mach. The far-wake formula it replaced scaled with the installed slope.
- **Effect:** scaling the lattice value by 5.633 / 5.115 gives 0.406. Re-sized at (15, 11): W0 3,194 lb, static margins 0.125 / 0.075, ceiling 23,549 ft, all rows met. No verdict changes.
- **Fix:** state it beside the downwash sentence, or scale by the slope ratio.

### G-4 (minor): no test covers the new downwash path

- **Evidence:** no file under `tests/` mentions `lattice_downwash` or `tail_height_over_df`.
- **Fix:** add three tests:
  - the lattice value approaches the far-wake value for a distant tail on a high-aspect-ratio wing;
  - Stage 1 and `stage3_aero` agree on a fixed geometry;
  - the z gate from G-2.

### G-5 (minor): leftovers outside the Stage 1 path

- `tp100_engine._gas` still defaults to `burner="csh"`; only `calibrated` passes the MSH default.
- `measurement/stage3_engine.py:139-144` still uses the constant-cp book example. Its rework is already an open action.
- `measurement/stage3_aero.py:104` hard-codes `runs/task12/stage3/2026-11-20/aero.json`, so the 2026-11-21 aero report cites the wrong record path.
- `size_tail_for_rotation` returns a scale it has not evaluated if eight passes do not converge. This predates the change, and the rotation row would catch it.

### G-6 (information): the ceiling margin at this point depends on the downwash being at least about 0.36

In this model more downwash gives a lighter aircraft: the layout re-centres the static margin, the CG travel shrinks and the rotation tail gets smaller. Probes at (15, 11):

| Downwash model | d(eps)/d(alpha) | W0 (lb) | Ceiling (ft) | Margined ceiling row |
|---|---|---|---|---|
| Record (lattice, 0.4 D_f) | 0.369 | 3,198 | 23,521 | met |
| Tail height 0.9 D_f (band high) | 0.336 | 3,206 | 23,452 | fails by 48 ft |
| Far-wake formula | 0.326 | 3,208 | 23,440 | fails by 60 ft |

The bare 23,000 ft requirement holds in all three. The band-high row is in `trades.csv`; a sentence in the package would make the dependence visible.

## Owner questions

1. **Keep the lightest point or take a more robust one?** The optimum is flat.
   - (a) Keep (15, 11): 3,198 lb, power margin 3.1 %, 21 ft over the ceiling margin, negative gust -1.53.
   - (b) (13.5, 9.5): 3,203 lb (+5 lb), power margin 4.1 %, 188 ft over, but negative gust -1.61, which is closer to the -1.70 limit.
   - (c) (14, 10.5): 3,218 lb (+20 lb), power margin 4.8 %, 311 ft over, negative gust -1.61.
   - Rulings 4 and 8 make (a) the rule-following choice; (b) and (c) buy engine margin cheaply at the cost of gust slack.

2. **Is the engine model's remaining bias acceptable without an allowance?** With the MSH burner the model reads below the book, by 1 to 4 points more at part throttle than at the design point. Calibration to the brochure absorbs only the design-point offset. At this point:
   - SFC x1.03 leaves the ceiling at 23,212 ft; SFC x1.05 leaves 23,003 ft, the bare requirement.
   - Power x0.97 leaves 23,118 ft; power x0.95 breaks the bare requirement.
   - The family extremes move W0 only from 3,176 to 3,205 lb; the pi_c 4.52 member misses the ceiling margin by 37 ft.
   - (a) Accept as carried: the ±10 % band ends are already reported as failing, and the maker's curve closes it.
   - (b) Size with an SFC allowance of 3 to 5 %: about +70 to +115 lb at this point, and a new selection is needed.

3. **Should the rotation rule keep sizing the tail before Stage 3 measures it?**
   - (a) Keep, and make the ground-effect rotation check the next Stage 3 row. Sizes may then move by 55 to 75 lb and 2 to 3.5 points of power margin, as in the driver table.
   - (b) Revisit an assumption now, such as rotation speed, tipback angle or tail CL limit. This is a new ruling and a new run.

4. **Tail-height band (G-2):** confirm a low end of about 0.1 D_f. A tail in the wing plane is not something this lattice can evaluate.

## Outcome

**PASS WITH ACTIONS.** The record reproduces, the lattice downwash is implemented with the right geometry and agrees with Stage 3 for the same design, the point is the lightest compliant on a 0.5 lattice, and the three margins are real.

- **Before the package is called final:** G-1 and G-2, including the re-run of the tail-height trade row.
- **Can be carried into Stage 3 as recorded actions:** G-3, G-4 and G-5.
- **Still open from round 4:** item C-3. The near-limit rows are rotation tail CL 0.994 of 1.0, nose-wheel load 0.188 of 0.20 and empty-fuel static margin 0.070.

None of the findings changes a compliance verdict in my probes.

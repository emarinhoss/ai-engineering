# Independent review: Gate B performance report `docs/validation/2026-11-26_task12_performance.md` (d3ecb12)

Read-only. Nothing edited, stashed, checked out or committed; `git status` is clean at the end and no bytecode was written. "Read" means taken from a repo record or report. "Computed" means my own inline Python (`python3 -B`, calling `measurement.info_gap.Built` on the frozen record); computed numbers are not recorded runs and must not be quoted in a report.

## Verdict

- **The numbers are sound.** I traced about 150 numbers across every table to their records. None disagrees with its source.
- **The report is honest about 7.4.** Its statement that parts 1 and 2 are "not met as written" and part 3 is "met on the record" is fair.
- **Nothing blocks the report as a document.** Six should-fix items remain, and one of them (GB-1, composite band) bears directly on the R5 horizon the gate rests on.
- **No recorded value is on the wrong side of a requirement.** Gate B is an owner decision about evidence class, not about a failed margin.

## 1. Number trace

Sources checked, all under `/home/user/ai-engineering/`:

- `runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/{design_pusher,target_result,info_gap}.json`, its `ledger.yaml`, and `../../run.log`
- `runs/task12/stage3/2026-11-26/m250_baseline_appl_measure/{perf,engine,aero,rotation,ground_effect_validation}.json`
- `runs/task12/stage3/2026-11-26/appl_decomposition/decomposition.json`
- `runs/task12/stage1/2026-11-26/takeoff_f_sweep/sweep.json`
- `runs/task12/openvsp/2026-11-26_m250_baseline_appl_vspaero/results.json`
- `runs/task12/stage1/2026-11-25/design_pusher.json`

What matched (read):

- **Section 1:** all 12 design values.
- **Section 3.1:** all 22 perf rows and the counts 12 / 3 / 6 / 1.
- **Section 3.2:** all 9 engine rows, the 18 cycle-model rows (16 of 18), the constant-SFC figures, 71.8 %, 557.8 lb and 95.8 of 137.2 lb.
- **Sections 3.3 to 3.5:** all 9 aero rows, the rotation row, the 4 ground-effect rows, and the VSPAERO table with its differences.
- **Section 4:** every margin recomputes from the two quoted numbers.
- **Section 5:** all horizons (1.0514, 1.1782, 1.5059, 1.6057, 0.1976, 0.3680), the 8-row worst-case curve, the one-at-a-time table, the sampling statement (`n_beating_search` 0 in all 10 entries, 952.0 lb), the decomposition numbers and all 7 sweep rows.
- **Sections 6 and 10:** every diagnosis number and every "differs between sources" entry.

Items that do not match, lack a source, or are rounded or labelled differently (all minor):

| # | Report line | Issue | Evidence (read) |
|---|---|---|---|
| a | 537 (open item 14) | Says the engine record carries no dirty-tree flag. It does. Aero, rotation and ground-effect records have none, as stated. | `engine.json` `inputs.uncommitted_code_changes: false` |
| b | 231 (R12 ceiling) | Margin 6,746.6 ft is taken from 23,000 ft although the row names the ledger's 500 ft margin. Against 23,500 ft it is 6,246.6 ft (5,850.1 ft at the lower bracket). | `ledger.yaml:19,22` |
| c | 227 (R9) | Requirement column prints "-1.5", the stale spec value. No negative margin is given. | see GB-2 |
| d | 237 (R18) | Requirement column omits the spec's "110 kt EAS" and "enforced by the autopilot". The record's 115 kt is not listed in section 10 as a spec/record difference. | see GB-3 |
| e | 373 | "lattice at the nominal tail height: 0.457" is Stage 1's value (0.4571). The Stage 3 fine-lattice row is 0.4579 (0.458 in table 3.3). | `aero.json` |
| f | 238 (R19) | Pairs leg-mean ground speeds (116.22, 103.62 kt) with leg-start true airspeeds (141.24, 128.66 kt). The differences are 25.02 and 25.04 kt, not 25. | `design_pusher.json` `mission` |
| g | 7-8 | The stated rounding rule ("three or four significant decimals") is not what the tables do (9.03125, 3,160.3, 104.27, 196.713). | cosmetic |
| h | 268 | "Seed 20261122" is the base seed. The ten sampling entries use 20261122 to 20261163. | `info_gap.json` `h_hat/*/sampling` |

## 2. Requirement status against the spec wording

Correct as stated: R1 to R4, R5 (8 h nominal; 3.5 h at h = 1), R7 (three clauses, with the stall clause outside the horizon), R8, R10, R12 (both clauses at W0), R13 (range and 0.034 from each end), R14 to R17, R19.

Deviations:

- **R9:** see GB-2.
- **R18:** see GB-3.
- **R6:** the report's status "not checked" is harsher than the wording. R6 as written (cruise and loiter at 20,000 ft, ISA) is met by construction. What is unchecked is engine operability, which is assumption R-f and not part of R6's text.
- **R11:** "by construction" is fair, and the caveat that no row checks the speed choice (141.2 and 128.7 kt against the still-air 114.6 kt) is needed and present.
- **Propeller row of 7.1a:** the spec defines it as "App. L against 0.80, ±0.05". On that definition the climb row is 0.7202 against 0.80, which is -0.080 and outside. The report shows "within" because G-4 moved Stage 1 onto App. L. That is correct after G-4, but the 7.1a text was never updated; say so in one line.

## 3. Findings

### GB-1 (should-fix; owner ruling before an unconditional pass). The composite band never reaches the built aircraft, and its size is comparable to the R5 horizon margin.

Evidence (read):
- `conceptual/uav.py:528-541` applies the hard-coded `wts.COMPOSITE_FUDGE` (`conceptual/raymer_weights.py:7`: wing 0.85, tails 0.83, fuselage 0.90, gear 0.95) to the build-up. These have no ledger entry and no band.
- `L["composite_factor"]` is read only at `conceptual/uav.py:618,621` (the Table 3.1 and Table 6.2 comparison lines) and `conceptual/stage1.py:84,89` (first-pass sketch). The author's statement missed the `stage1.py` use.
- `conceptual/stage1.py:221` skips `composite_factor` in the trades, so the spec step 8 trade "composite factor across its band" was never run on the refined design.
- `info_gap.json`: `composite_factor` is one of the 54 variables with band 0.90 to 1.00, and is in `inert_variables`.
- Spec 7.2 (`task12_drone_conceptual_design.md:317-319`) names "composite factor" and "empty-weight fit against build-up" among the bands to propagate jointly. R9 carries the band.
- Review IG-2 (`docs/reviews/2026-11-22_task12_info_gap_review.md:50-56`) asked for exactly this. The `band_weight` fix propagated We(theta) but left the material factors constant.

Is it a defect or intended? It is a defect against spec 7.2, not a documented choice. Replacing the flat 0.95 by Table 15.4 component factors is a sound Stage 1 method. But no ruling says the band lapses, and the "empty-weight fit against build-up" band has no variable at all. The record's own alternatives span empty fractions of 0.508 to 0.581 (read, `empty_fraction_comparison`).

Size (computed; I scaled every Table 15.4 factor by c/0.95, which is my mapping of the band and not a ruling):

| Case | Composite 0.95 (as built) | Composite 1.00 (band high) |
|---|---|---|
| Nominal hours on station | 9.031 | 8.759 |
| Nominal W0 (lb) | 3,160.3 | 3,224.9 |
| Recorded worst R5 point at h = 1, hours | 3.768 (reproduces the record) | 3.554 |
| Recorded worst R5 point at h = 1, take-off (ft) | 1,098 | 1,141 |
| R5 horizon along the recorded worst direction | 1.0514 (reproduces the record) | about 1.010 |

- The factored components are 968.8 lb, 57.6 % of empty weight (computed from read values).
- The 3.5 h guarantee probably still holds at h = 1, by 0.05 h instead of 0.27 h.
- The baseline rule R-d (h_T = 1.05) would no longer be met. This was a probe along one direction, not a new search, so the true horizon can only be at or below 1.010.
- R7 is not at risk.

Fix:
- In the report, add the inert composite band and the missing fit-against-build-up band to section 5.7 and to the limits under section 7.3. Correct the R9 note to include the `stage1.py` use.
- For the gate: owner question Q2.

### GB-2 (should-fix: spec text). R9 negative limit: the ledger's -1.8 governs, and the record meets both.

Evidence (read):
- The owner ruled "Raise the negative limit" at Gate A round 1 (`docs/reviews/2026-11-20_task12_gateA_round1.md:13`).
- `ledger.yaml:17` has `negative_load_factor -1.8`; `ledger.yaml:20` has `margin_gust_g 0.1` (round 4 ruling 4).
- The compliance row tests `n_negative_gust >= -1.8 + 0.1` (`conceptual/stage1.py:306-307`).
- The spec status line acknowledges the 0.1 g margin, but the R9 row (`task12_drone_conceptual_design.md:75`) still reads -1.5.

Result:
- The record's -1.239 is inside -1.7 (ledger with margin) by 0.461, and inside the stale -1.5 by 0.261, or 0.161 if the 0.1 g margin is applied to it. These are subtractions of read values.
- Note (read): the record holds two values for the same worst gust point, `gusts` 3.2386 and `vn.n_cruise` 3.2179. The report quotes the first, which is the sizing value.

Fix: print -1.8 with the 0.1 g margin in the R9 row and give the negative margin. The owner should update spec section 3 (Q3).

### GB-3 (should-fix: disclosure). R18 is consistent with the spec and the rulings, but the report understates the exceedance and misses a spec/record difference.

Evidence (read):
- Spec R18 (`:90`) reads "one V_C placard of 110 kt EAS at every altitude, enforced by the autopilot; structure and gusts sized at it". Autopilot enforcement is part of the requirement, chosen at Gate A round 4 (`docs/reviews/2026-11-21_task12_gateA_round4.md:261-262`, option a). "Holds only with autopilot enforcement" is therefore the requirement as written, not a breach.
- The record's 115 kt comes from the per-design rule (1.10 × 104.27 = 114.7, rounded up to 115; `conceptual/uav.py:41-45`), an owner ruling of 2026-11-23. That ruling exists only in the ledger source text (`ledger.yaml:126`), code comments and the baseline reports. It is not in spec R18 and not in `00_decisions.md` section 9.
- `design_pusher.json` `vn`: V_D is 172.5 kt EAS. The sea-level level top speed is 198.5 kt EAS, which is above V_D and not only above V_C. At 20,000 ft, 129.8 kt lies between V_C and V_D.
- The baseline report's own exclusion ("loads were not re-checked against a V-n diagram beyond the Stage 1 rows") is not carried into the performance report.

Further checks:
- Computed (linear scaling of the recorded gust increment with speed, full U_de): about 4.9 g at 198.5 kt against the 3.8 limit.
- Computed: the info-gap members at the worst points fly their fastest step at 96.8 and 97.7 kt EAS, below V_C. The fixed placard is not exceeded inside the study.

Fix:
- State the V_D exceedance.
- Add "110 (spec) against 115 (per-design ruling 2026-11-23)" to section 10.
- List the per-design ruling among the rulings used.
- Owner question Q4. No new requirement ruling is needed unless the owner wants the structure cleared to level top speed.

### GB-4 (should-fix). The list of rulings is incomplete.

Section 11 cites "R-a to R-f, G-1 to G-9". The report also depends on these (read):
- the per-design V_C ruling (2026-11-23);
- the R5 restatement and the headwind and Oswald exclusions (2026-11-22);
- the Gate A margins (500 ft, 0.1 g, power margin 0);
- the baseline-cell ruling and edits A and B (`00_decisions.md` section 9).

Also, spec 7.1a still names `runs/task12/stage1/2026-11-20d/design_pusher.json` as "the Stage 1 value", and spec 7.1c item 4 requires a Gate A re-check after a return to Stage 1. The frozen design has no Stage 1 compliance table and no recorded Gate A re-check. The report discloses the missing table (section 8) but not what it means for checklist item A1 and for 7.1a.

Fix: add these, and ask Q9.

### GB-5 (should-fix). Open items and "Not run" miss points from the three reviews.

- **APL-7 and APL-9:** the disk model is favourable in cruise (0.814 against the old 0.80, read). It has no tip-Mach or off-design loss, uses the full disk area, and has no hub, spinner or pusher-fuselage blockage. The nominal 9.03 h benefits from this.
- **APL-6 and S3A-8:** the single f is applied at every point, so the band cannot represent a propeller good in cruise and poor in climb. The ledger still labels `prop_real_to_ideal` as `confidence: published` (`ledger.yaml:42`) although the band is a judgement.
- **APL-4:** section 8 says "Static C_T/C_P ... not varied". Under App. L it is inert (in `inert_variables`), so varying it would change nothing. Say inert.
- **S3A-1:** at the worst endurance corner the two-point climb flies at 87.7 kt (read, `decomposition.json`), which the review computed to be about the 20,000 ft stall speed. Open item 9 does not mention it. It can be stated without the computed number.
- **S3A-5:** Anderson's 0.62 route is not self-consistent with the disk (efficiencies held at the record weight). Section 6 does not say so.
- **S3A-4:** table 3.1 still classes the closed-form climb rows as "coding check" (the record's class). The review asked for "not judged (closed form assumes constant power available)". The verdict column is right.
- **Span efficiency and ground-effect validation:** both are in section 6 but absent from section 9, although the S3A disclose list names both.
- **S3M-11(b):** `_prop_eta_fixed_point` returns without a flag if it does not converge. It is not mentioned.

### GB-6 (note). The 7.4 section is fair, with two additions needed.

- **7.3 limits:** add GB-1. It is the only listed 7.2 quantity that is banded in name but inert, and it is of the size of the margin.
- **Section 6 closing paragraph:** the statement that no outside row moves a margin below zero holds for every recorded value I traced. The Anderson build-up row (+9.12 %, not judged) deserves one more sentence. An empty weight at Raymer's Table 15.2 level (fraction 0.581 against 0.533, read) is an empty-weight uncertainty that no band carries. Review IG-2 found, on the earlier design, that about +90 lb removed the guarantee.

### GB-7 (note). Robustness curves.

Spec 7.3 asks for "the robustness curves". The report gives the table and says no figure exists. That is acceptable and disclosed; a figure from `worst_case_curve` would be cheap.

## 4. Framing the Gate B decision

What the records support:
- Every requirement value is on the right side of its limit.
- Both horizons are at least 1 (1.051 and 1.506).
- 7.4 parts 1 and 2 cannot be met as written. The engine has no public altitude or part-power data. The propeller, C_L,max and gust second sources were waived (G-5). R13 is met by construction.

A return to Stage 1 "with the measured values in place of the estimates" would change almost nothing today:
- The measured values that differ are CD0 (-18.6 %, favourable, method good to ±20 %), lift slope (-3.4 %), field distances (+1.2 % and +0.5 %), and the engine family's SFC (0.1 to 3.1 % below Stage 1).
- None of these moves a margin toward its limit.
- The values that would change a re-size are ones not yet measured or banded: the composite and empty-weight band (GB-1), C_L,max, f at low speed, SFC at altitude, and the neutral point with fuselage.

Realistic options:

- **A. Pass with the open items accepted.** The owner rules that the declared evidence classes stand in for "independent measurement", and that the three outside rows are explained.
- **B. Pass conditional on cheap closures (recommended).**
  - Run the composite and empty-weight band in the info-gap study (GB-1).
  - Generate the Stage 1 compliance table for the frozen design.
  - Update the spec text for R9, R18 and 7.1a.
  - Make the report fixes above.
  - Carry SU2 C_L,max, the fuselage neutral point, blade-element f and engine data to preliminary design as named risks.
- **C. Back to Stage 1.** This is justified only if the owner requires the R-d target (h_T 1.05) to hold with the composite band acting. W0, fuel and sized loiter would then rise; nothing else changes.
- **D. Hold the gate** until SU2 C_L,max and a fuselage-inclusive neutral point exist. Engine altitude data cannot be obtained, so 7.4 part 1 would still need a ruling.

## 5. Owner questions

1. **7.4 part 1: do the declared evidence classes stand in for "independent measurement"?**
   - (a) Yes, for all requirements.
   - (b) Yes where no independent source can exist (engine SFC, R6, ceiling, propeller); the feasible ones (C_L,max, neutral point) are carried as named preliminary-design entry items.
   - (c) No: hold the gate.
   - Recommend (b). It matches what G-5, G-6 and R-f already decided, and it keeps the two closable gaps visible.

2. **Composite band (GB-1).**
   - (a) Rule that the band applies to the first pass only, and strike it from 7.2.
   - (b) Record an info-gap run with the band acting on the Table 15.4 factors, plus an empty-weight band; pass if the R5 horizon is at least 1.
   - (c) As (b), and re-size to h_T 1.05.
   - Recommend (b), then decide (c) from the result. Spec 7.2 names the band, the computed effect is the size of the margin, and the run takes minutes.

3. **R9 negative limit.**
   - (a) -1.8 with the 0.1 g margin governs; update spec section 3.
   - (b) Revert to -1.5.
   - Recommend (a). It is the standing Gate A ruling, and the record meets both.

4. **R18 and V_C.**
   - (a) Confirm the per-design 115 kt, record the ruling in spec R18 and section 9, and carry envelope protection (level top speed above V_D at sea level) as a preliminary-design requirement.
   - (b) As (a), plus a recorded V-n check at V_D and at level top speed.
   - (c) Size the structure to level top speed.
   - Recommend (b). It costs one small run. Option (c) was priced at Gate A round 4 (about 3,980 lb at 150 kt, read) and rejected.

5. **R13 neutral point.**
   - (a) Accept layout construction plus G-8, and carry the fuselage-inclusive neutral point to preliminary design.
   - (b) Require a second fuselage-inclusive estimate before the pass.
   - Recommend (a). A neutral-point error moves the wing station, which is still free. The CG travel is 0.032 MAC inside a 0.10 band.

6. **Take-off power row (-10.89 %).**
   - (a) Rule it explained: R7 is judged on distance at installed power, which is within tolerance.
   - (b) Replace the row in 7.1a by the distance row.
   - (c) Leave it as failed.
   - Recommend (a) with (b) as a spec edit. Reviews S3M-7 and S3A-6 both reached this diagnosis.

7. **CD0 (-18.63 %) and the Fig. K.3 rows.**
   - (a) Rule both explained and carried: CD0 is favourable and unresolved to ±10 %; K.3 is covered by the ±10 % SFC band.
   - (b) Require a second CD0 route (OpenVSP wetted area) before the pass.
   - (c) Require a run translating the K.3 low reading into fuel.
   - Recommend (a). Neither can move a margin below zero on the records. Note that the SFC band is then doing two jobs.

8. **G-5 waived rows (SU2 C_L,max, gust second source, blade element).**
   - (a) Keep waived and list them as preliminary-design entry items.
   - (b) Run SU2 C_L,max before the pass.
   - Recommend (a). The stall clause has 10.83 kt of margin, and the low C_L,max band end is already inside the horizon for the distances.

9. **Stage 1 package and Gate A re-check for the frozen design.**
   - (a) Generate the compliance table and re-check A1 to A12 before the pass.
   - (b) Accept `failed: []`.
   - Recommend (a). Spec 7.1c item 4 asks for it, and it is a regeneration, not new work.

10. **8 h nominal robustness (h = 0.198; 7.702 h with SFC +10 % alone).**
    - (a) Acknowledge it as what the restated R5 allows.
    - (b) Add a nominal-robustness target.
    - Recommend (a). It is the 2026-11-22 ruling, and it should be minuted at the gate.

Files most relevant:
- `/home/user/ai-engineering/docs/validation/2026-11-26_task12_performance.md`
- `/home/user/ai-engineering/conceptual/uav.py` (lines 41-45, 523-541, 618-621)
- `/home/user/ai-engineering/conceptual/raymer_weights.py` (line 7)
- `/home/user/ai-engineering/conceptual/stage1.py` (lines 84-89, 221, 306-307)
- `/home/user/ai-engineering/runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/` (`ledger.yaml` lines 17-20, 42, 79, 126)
- `/home/user/ai-engineering/docs/specs/task12_drone_conceptual_design.md` (lines 75, 90, 241-242, 317-319, 333-336)
- `/home/user/ai-engineering/docs/specs/00_decisions.md` (section 9)

# Gate A, round 2: Task 12 conceptual design review (2026-11-20)

**Outcome: FAIL (short loop) — round 3 limited to the reviewer's action list.** Package reviewed:
`docs/validation/2026-11-20_task12_conceptual_r2.md`, records `runs/task12/stage1/2026-11-20b/`,
code at `d3b792f`.

## 1. Éder's ruling at round 2, and why it is asked again

Asked: "which concept do we freeze?", shown the tractor at 2,307 lb against the pusher at 2,630 lb,
a 1.8x tail for the pusher to rotate, and a re-scored 3.80 against 3.47. Ruling: **switch to the
tractor**. The reviewer then found (N1) that the rotation check had the main-wheel moment with the
wrong sign, which made the pusher's tail figure wrong, and that the re-scoring changed the round-1
weights and counted one cause three times (section 4 below). The ruling was given on those
distorted figures, so the concept question is put to Éder again at round 3 with corrected numbers.

## 2. Independent review (verbatim, round 2)

# Gate A round 2 review: Task 12 Stage 1 resubmission (2026-11-20b)

I am the same independent reviewer as round 1, and this review is read-only. Inputs:
- the package `docs/validation/2026-11-20_task12_conceptual_r2.md` and its figures;
- the records in `runs/task12/stage1/2026-11-20b/`;
- the code at d3b792f (`conceptual/uav.py`, `stage1.py`, `report.py`);
- `data/task12/engines.yaml`, the ledger, and the round 1 record.

`pytest -q tests/task12`: 82 passed. Probes were run with `uav.size_tail_for_rotation` and `uav.evaluate` using the TP100 from `stage1.engine_options()`.

## 1. Round 1 findings

| # | Status | Evidence |
|---|---|---|
| F1 main gear | **partly** | The main gear is placed by tipback and is in the CG. The weight table sums to 2,306.8 lb. Nose load and propeller clearance are computed. However, the rotation check added to close it has a sign error (N1), and the lateral gear position and overturn angle are not checked (N3). |
| F2 gust at one weight | closed | Four cases (`gusts` in `_build`, uav.py 312-319). The zero-fuel weight case at sea level governs: +4.28 / -2.28. |
| F3 q vs V-n | closed | `q_design` is 0.5 ρ0 V_C,EAS² = 128 psf at 195 kt EAS (uav.py 325). New consequence: see N5. |
| F4 crew items | closed | The decomposition is in section 4. The last sentence ("differ for more than the crew deduction") does not match its own table. Fit x 0.95 (0.556) minus build-up (0.524) = 0.032, and crew items alone are 0.030. At this size the crew items explain almost all of the gap. |
| F5 ceiling | closed | Bisection with CD0 at altitude (`ceiling()`, uav.py 552-573). 28,909 ft is reported. The limit column shows 24,999 (`ceiling_ft - 1`), which is cosmetic. |
| F6 speed text | closed | The mission rows carry the floor fraction. Probe: loiter 1.0, both cruise legs 0.0, which matches the text. |
| F7 constraint diagram | closed | Landing limit 66.3 lb/ft² with `landing_binding: true`. Best-range W/S 17.2 and best-loiter W/S 23.3 are present, and the R16 turn line is present. |
| F8 tests | partly | The equation-to-test table exists. The new tests are identities and limits, which is acceptable and explained. The new layout functions (rotation, tipback, gear length) have only presence tests, and the sign error in N1 passed all 82 tests. |
| F9 constants | partly | About 30 entries were moved to the ledger. However, the tyre D/q of 0.13 is the faired-wheel value. For a retractable gear with open wells, Raymer Table 12.5 (p. 287) gives 0.25 for a regular wheel and tyre. DR-1 used 0.13 for its own case. Several constants remain in code: 0.45 W0 per main wheel, nose tyre at 80 %, three struts, and the 1.02 resize step. The effect is small, because take-off and landing are not binding. |
| F10 calibration list, polar, propeller | closed | Section 9 has the list, and the polar and J/C_P points are present. η_p is still a constant, and that is stated. |
| F11 trim and rotation | partly | Trim is computed on every leg at its fuel state, so that part is closed. The rotation check is wrong (N1), and it omits the flap pitching moment and ground effect. Raymer p. 432-433 says ground-effect changes to slope and downwash must be included. |
| F12 checks | closed | The (10.23)/(10.24) docstring is fixed. |

## 2. Checklist A1-A12 (recommended concept as submitted: tractor)

| # | Answer | Evidence |
|---|---|---|
| A1 | yes | The matrix covers R1-R16. R3 traces through `engines_compared.csv` and R11 through the "speed set by" column. R13 still shows only the lower bound. |
| A2 | yes | We/W0 0.524 + Wf/W0 0.259 = 0.783, so the payload fraction is 0.217. The table sums. The decomposition is reported (with the wording issue under F4). |
| A3 | yes | 1.06 x (2,306.8 - 1,742.1) = 598.6 lb, which matches. |
| A4 | **no** | Static margin is 0.095 / 0.105 and trim is fine. The corrected rotation needs a tail CL of 1.01 against 1.0 available (N1), before any flap moment is counted. |
| A5 | partly | The positive cases at both weights and both altitudes set Nz 6.42. The negative case of -2.28 against -1.8 is open with Éder. |
| A6 | partly | 241 shp against 186 needed. Climb and ceiling are met using the piston lapse. The fixed-engine re-size is recorded. But the TP100 figures are unverified search extracts, and the engine's own dimensions are not in `engines.yaml`, so the installation is drawn with Table 10.4 sizes. |
| A7 | yes, with N6 | Ledger with bands, and an out-of-calibration list. |
| A8 | partly | See F8. |
| A9 | partly | Both concepts are kept, with three-views. The re-scoring is not neutral (section 4). |
| A10 | partly | Fuel fits (11.9 vs 20.7 ft³). The tractor's nose load is 15.7-16.2 %. Not checked: overturn/track, gear retraction volume, the payload bay, and the real engine envelope (N3). |
| A11 | **no** | This package has no risk list. Section 11 lists open items, and only some name a Stage 3 measurement. The round 1 risk list (lapse, empty weight, CL_max, span efficiency, downwash) was dropped. |
| A12 | partly | Éder accepted R10-R15 at round 1. The 1.3 V_stall floor and R16 are pending. |

## 3. New errors and issues

**N1. The rotation check has the main-gear moment with the wrong sign (most severe).** In `layout()` (uav.py 544-547):

`gear = (N_main*(x_main - cg_fwd) - mu*N_main*h_cg)/(q S c)`

This is added to the nose-up numerator of `tail_cl`. The upward main-wheel reaction acts aft of the CG, so it is nose-down. Raymer p. 432-433 treats both gear terms as moments the elevator must overcome. The friction term has the right sign; the reaction term does not. As a result the reported "tail CL needed" is positive, meaning an upward tail lift is needed to rotate, which is physically wrong.

Probe at the submitted designs:

| Concept | Reported | Corrected (both gear terms nose-down) | Main-gear term G | Friction term F |
|---|---|---|---|---|
| Tractor | +0.759 | **-1.012** | 0.543 | 0.059 |
| Pusher (tail scale 1.80) | +0.991 | **-1.067** | 1.072 | 0.111 |

Consequences:
- The tractor fails rotation (limit 1.0) and needs a tail resize too.
- The pusher's 1.80 tail scale is wrong; it would need a larger scale.
- Both W0 values and the concept comparison move.
- The flap pitching moment (nose-down) and ground effect are omitted, so even the corrected values understate the need.

*Fix:* sum moments with explicit signs, add the flap ΔCm and ground effect (or a stated band), and add a unit test asserting a download (CL_tail < 0) for a tricycle with the mains aft of the CG.

**N2. The nose-load rule and its display do not agree.** `compliance` rule "nose" passes 0.05 ≤ n ≤ 0.20 (stage1.py 297), but the limit column prints 0.15. The tractor's 0.157 and 0.162 are within Raymer's limits (p. 232-233) and above his 8-15 % optimum. That is acceptable for a pass, but the row must show the 0.05-0.20 limits and say "above optimum". The pusher's 0.251 and 0.233 **violate** the 20 % limit. Its layout is therefore infeasible as drawn, not merely low-graded.

**N3. Overturn and track are not checked.** The three-view draws the main wheels at ±0.6 d_f (report.py 78), a drawing choice and not a sized track. For the tractor (CG height 4.12 ft, mains at 9.65 ft, nose at 2.59 ft), Raymer's 63° overturn limit (p. 232) needs a half-track of about 2.7 ft, or a track of about 5.3 ft. That is wider than the 3.24 ft fuselage, so the mains must retract into the wing or sponsons. That volume is neither shown nor checked. The pusher, with an 8.1 ft CG height, would need a far wider track.

**N4. Gear length sizing for the pusher.**
- `_gear_length_in` uses `main_gear_station_guess` 0.40 while the layout places the mains elsewhere. The layout's clearance (13.2 in) shows the guess is conservative, so the gear is about 4 in longer than needed, a small effect.
- The pusher is evaluated at `rotation_angle_deg` 15, the top of its 10-15° band. That is the end that maximises its gear length (my estimate: about 78 → 59 in at 10°).
- The CG is assumed on the fuselage centreline at height gear + d_f/2.
- For the tractor, clearance is checked only in the level attitude. Raymer p. 222 asks for all attitudes, including nose-strut compression.

**N5. q and the gust are set by surplus power.** V_C is the sea-level maximum level speed with the full 241 shp, which gives 195 kt EAS. That speed drives q_design (128 psf) and the governing gust (n 4.28). The mission flies at 104-118 kt TAS. A placarded V_C/V_NO would reduce both. This is a requirement choice for Éder, and the package does not raise it.

**N6. The engine attribution is overstated.** The summary credits the full +578 lb (rubber 1,729 → TP100 2,307) to the 0.901 consumption. My probe of the tractor at 18/10 with the TP100 at Table 3.4 SFC gives 1,905 lb. So SFC accounts for about 400 lb, and about 175 lb comes from the larger engine: weight, V_C, q and gust. Also:
- `engine_options()` copies the cruise SFC to loiter (stage1.py 43-44); this is stated. The part-power penalty at about 45 % throttle (section 5) is unbounded, as the trade only spans 0.8-1.2.
- The loiter sits at 45 % of the lapsed rating, and the piston lapse sets that rating.

**N7. The rationale for the choice changes.** The headline now recommends the tractor while Éder's round-1 freeze stands. The compliance matrix, weight statement and layout are rendered for the tractor only. The frozen concept's compliance (with two failed rows) exists only in `compliance_pusher.csv`.

## 4. Is the re-scoring fair?

No, not as presented.
- The criterion weights changed from round 1 to round 2: W0 0.40→0.35, sensor 0.25→0.20 and exhaust 0.10→0.05, and a new 0.15 nose-load row was added. This was done after Éder froze the pusher, which mixes new evidence with new preferences.
- One root cause is counted three times. The tall pusher gear raises W0 (gear weight and drag, plus the 1.8x tail), scores again in the gear-length row, and scores again in the nose-load row.
- The pusher is evaluated at the penalising band ends (15° rotation, no tail bumper, no raised thrust line).
- The rotation inputs behind its tail scale are wrong (N1).

With the round-1 weights and the submitted grades, I get tractor 3.95 against pusher 3.89, a margin that is within the judgement grades.

Fair handling would be:
1. Keep the round-1 weights.
2. Replace computed rows with constraints: a layout either meets the nose-load and overturn limits or is redesigned until it does.
3. Correct N1.
4. Show the pusher at the favourable end of the rotation band and with a tail bumper.

The evidence that the pusher pays for propeller clearance is real and worth putting to Éder, but as a corrected weight and layout comparison, not a re-weighted score.

## 5. Items needing Éder's ruling, beyond those already being asked

1. V_C/V_NO placard versus sizing the structure at the full-power maximum speed (N5).
2. Accept a nose load above Raymer's 8-15 % optimum (tractor 15.7-16.2 %) or require it.
3. Whether the concept question should be put with the round-1 weights (section 4).
4. Accept Gate A on an engine whose data is unverified, or require the datasheet first.

## 6. Recommendation: **fail (short loop, round 3 limited to the items below)**

Most findings are closed. A4 fails on a code error that changes the tail size and the concept comparison, which is the thing Gate A freezes. Actions:
1. Fix the rotation moment sign. Add the flap moment and ground effect. Re-run the tail resize for both concepts. Add a sign test (N1).
2. Add overturn and track sizing, and show where the gear retracts (N3).
3. Show the nose-load limits correctly. Treat the pusher's >20 % as a constraint to design out (N2).
4. Re-present the concept comparison as in section 4, with the pusher rendered in full (N7).
5. Correct the engine attribution (N6) and the F4 wording. Restore a risk list in which each risk names a Stage 3 measure (A11). Use the unfaired tyre D/q or justify 0.13.
6. Obtain Éder's rulings listed in section 5, plus the pending ones (concept, -2.28, the 1.3 V_stall floor, R16).

Once these are done, I expect pass with actions, the actions being the TP100 datasheet check before Gate B and the Stage 3 lapse and SFC measurements.

# Gate A, round 3: Task 12 conceptual design review (2026-11-20)

**Outcome: PASS WITH ACTIONS.** Package reviewed: `docs/validation/2026-11-20_task12_conceptual_final.md`
(records `runs/task12/stage1/2026-11-20d/`). The configuration is frozen: single-turboprop
(PBS TP100) pusher UAV, conventional tail, retractable tricycle gear in sponsons.

## 1. Éder's rulings at round 3 (asked one at a time, with corrected figures)

| Question | Ruling |
|---|---|
| Concept (asked again after the round-2 sign error) | **Pusher**, on the round-1 criteria and weights |
| V_C | **Placard at 150 kt EAS** (R18) |
| Loiter speed floor | **Keep 1.3 V_stall** (R17) |
| Main-gear stowage | **Sponsons**, with drag and weight penalties |
| Engine data and R16 | **Pass with actions**; R16 accepted; read the TP100 datasheet before Gate B |

## 2. Actions from this review and their status

| Action | Status |
|---|---|
| Tail download in the main-wheel load at rotation; forward CG for the overturn track; tests; re-run | done: `runs/task12/stage1/2026-11-20e/`, package `docs/validation/2026-11-20_task12_conceptual_gateA.md` |
| Text: engine attribution, empty-weight sentence, stale sponson risk row, sponson cost in the summary, tractor's negative gust disclosed | done (generated from the records) |
| Sponsons drawn; stowage checked against sponson length and depth | done |
| Constants still in code (main-wheel share, nose-tyre size) | moved to the ledger |
| Read the PBS TP100 datasheet before Gate B | **open (owner)** |
| Éder to accept the pusher's nose-wheel load above Raymer's 8-15 % optimum | asked at gate close |
| Stage 3 measurements listed in the package's risk table | carried into Stage 3 |

## 3. Independent review (verbatim, round 3)

# Gate A round 3 review: Task 12 Stage 1 (2026-11-20d)

This review is read-only and limited in scope. Inputs:
- the package `docs/validation/2026-11-20_task12_conceptual_final.md` and its figures;
- the records in `runs/task12/stage1/2026-11-20d/`;
- the code at HEAD 03e6ebc. The code has not changed since 45d5218, the commit recorded in `inputs.json`, and the ledger and engines files match the hashes there.

`pytest -q tests/task12`: 84 passed. Probe scripts are in the scratchpad (`probe1.py`, `probe2.py`), using `from conceptual import uav, stage1`.

## 1. Round-2 actions and findings

| Item | Status | Evidence |
|---|---|---|
| N1 rotation sign (action 1) | **partly** | Signs are now correct (uav.py 629-630). The main reaction (-0.751) and friction (-0.079) are nose-down. The flap term (16.17) at x_le + 0.44 MAC gives +0.016 (pusher; the flap centre of pressure is ahead of the CG) and -0.034 (tractor). There is a sign test (test_uav.py 81). Ground effect is stated as not modelled, with a risk row. **New error:** `N_main = W - q S CL_w` (uav.py 628) leaves out the tail download. Raymer p. 432-433 takes the main-wheel load as weight minus *total* lift. Probe with the tail lift included: the pusher needs tail CL **-1.19** at scale 1.51 (limit 1.0), and the tractor needs -1.04. Re-running `size_tail_for_rotation` with that correction gives pusher scale 1.90, W0 **2,806 lb** (+57), and tractor scale 1.06, W0 2,462 (+6). The pusher's empty-fuel static margin becomes 0.074 and its nose load 0.188, both still within limits. Minor: Fig. 16.9 gives x_cp as a fraction of the flapped chord c′, but the code uses the clean MAC. |
| N2 nose-load display (action 3) | closed | The limits show as 0.05-0.20 with the optimum labelled (compliance_pusher.csv). The pusher is at 0.177/0.166, within limits and above the optimum. Éder has not explicitly accepted the above-optimum value (round-2 §5 item 2). |
| N3 overturn/track (action 2) | partly | `overturn_track` is geometrically correct (I checked the construction by hand: 4.37 ft for the pusher, 2.60 ft for the tractor). Three gaps: (a) it uses the aft CG (uav.py 564), but the forward CG is the critical one; the probe gives 4.44 / 2.62 ft, a small change. (b) `fits = True` is hard-coded (uav.py 581-582), so the "stows" row is set by the ruling and not checked: nobody checks that the 59 in leg fits a 65 in × 22 in sponson. (c) Neither three-view draws the sponsons. The side view hangs the mains from the fuselage belly, and the front view shows no gear. |
| N4 gear length / attitude | closed | The pusher uses 10° with a bumper (ledger `rotation_angle_deg_pusher`). The tractor is checked at 2° nose-down. Clearance is 11.0 in for the pusher and 10.1 in for the tractor. |
| N5 V_C from surplus power | closed | Ruling R18 is implemented (uav.py 330-331): V_C is 150 kt EAS at sea level, q_design is 76.2 psf, and V_D is 225 (vn.png). |
| N6 engine attribution (action 5) | partly | The split is +111 / +570 lb, which matches engines_compared.csv (2,068.8 → 2,179.6 → 2,749.2). The generated text is now wrong, though (report.py 333-334). It credits the +111 lb partly to the engine's "higher top speed, design q and gust loads". With the placard, the rubber engine (153 kt unplaced) and the TP100 are both capped at 150 kt with Nz 5.7, so q and gust are identical. The +111 lb comes from the engine's weight and drag. |
| N7 rationale/rendering (action 4) | closed | The pusher is rendered in full: compliance, weights and layout. Both three-views are present. `recommended = FROZEN_CONCEPT` (stage1.py 397, 402), and `highest_score` is kept separately. |
| §4 re-scoring (action 4) | closed | The weights are 0.40/0.25/0.10/0.10/0.15 with grades identical to `runs/.../2026-11-20/concept_scores.json`. Pusher 4.086 vs tractor 3.95, which I recomputed. Layout limits are now constraints, not scored rows. With the N1 correction: pusher 4.05 vs tractor 3.95, so the order does not change. |
| Tyre D/q (action 5) | closed | 0.25 (Table 12.5), in the ledger. |
| Risk list / A11 (action 5) | closed | §11: each risk names a Stage 3 measure. One row is stale ("sponsons … not modelled"; report.py 633); they are now modelled. |
| F4 wording (action 5) | **partly** | The package says the "build-up is -0.012 below the fit ×0.95 … crew items explain most of that gap". The build-up (0.551) is 0.012 *above* 0.539, so adding crew items widens the gap; they do not explain it. The like-for-like sentence (+0.059) is correct. |
| Rulings (action 6) | closed | Pusher frozen; R17 (`speed_over_stall`); R16 (`turn_bank_deg`); R18 (`vc_placard_kt_eas`); sponsons; PBS datasheet action §12.1. The negative gust is -1.748 vs -1.8 for the pusher. |
| F1 | closed | Main gear in the CG and table (176.4 lb at 11.75 ft); the sum is 2,749.2. |
| F8 | partly | There are sign and overturn tests. None covers the placard path, the sponsons, or which CG feeds overturn and rotation. |
| F9 | partly | The remaining in-code constants are unchanged: 0.45 W0 per main wheel (now also sizing the sponsons), the 0.8 nose tyre, three struts, and the 1.02 resize step. The effect is small. |
| F11 | partly | Trim is closed. Rotation remains open per N1. |

## 2. Checklist A1-A12 (pusher)

- A1: yes. 26 rows: 19 met, 7 by construction or by fiat ("stow").
- A2: yes. The weights sum. There is the F4 sentence error.
- A3: yes. Fuel is 733 lb including the 1.06 factor.
- A4: **no as submitted.** The static margin of 0.113/0.087 and the trim (tail CL ≤ 0.151) are fine. Rotation needs a tail CL of 1.19 against the 1.0 available until the tail download is in N_main. It becomes yes after the resize to scale 1.90 (probe).
- A5: yes. Manoeuvre 3.8 governs; the gust is 3.75 / -1.75 at 150 kt EAS.
- A6: yes, with an action. 241 shp against 218 needed, ceiling binding. The engine figures are unverified search extracts.
- A7: yes.
- A8: partly (F8).
- A9: yes.
- A10: partly. Fuel 14.6/36.3 ft³ is fine. Still unchecked: gear stowage volume, payload-bay fit, and nose-wheel packaging. The nose wheel at 1.08 ft is ahead of a sensor turret at 2.70 ft.
- A11: yes.
- A12: yes.

## 3. New errors and issues from the round-3 changes

1. **Rotation main-wheel load omits the tail download** (N1 above). This is the one material error. It is unconservative, changes the tail by +26 % in volume and the pusher's W0 by about 2 %, and leaves the concept order unchanged. The trades list `tail_cl_max_rotation` under "no effect" only because `trades()` holds the tail scale fixed. That is misleading: at 0.8 the resize grows the tail.
2. **Sponsons.**
   - Geometry: length 3.6 and depth 1.2 tyre diameters, so fineness 3.0. Wetted area by (7.12) is 53.6 ft². Weight is 1.4 × S_wet × 0.90 = 67.5 lb, which I checked.
   - Form factor: (12.31) at f = 3 gives FF 3.23. Raymer p. 283-284 allows (12.31) for gear pods, so the formula is defensible. Combined with Q 1.5 at the top of its band, the sponson CD0 is 0.0047, more than the fuselage's 0.0040 and 19 % of the total.
   - Cost: the no-sponson trade gives 2,428 lb, so the sponsons cost **+321 lb (12 %)**. The summary does not state this number.
   - Fineness choice: the p. 110 "least drag at fineness 3" result is for fixed volume. With (12.31) at fixed tyre depth, the drag minimum is near f ≈ 5. The band trades (3.0 and 4.8 tyre diameters both give 2,768 lb) show the choice costs at most about 20 lb.
   - The tractor carries sponsons too, so the comparison is fair.
3. **V_C placard path**: correct. It caps each altitude's V_C at 150 kt EAS. The pusher's mission-altitude V_C is 103 kt EAS (the lapsed maximum speed). The Table 6.2 cross-check now takes the placard as "Vmax" (uav.py 422; cosmetic).
4. **Nose-wheel loop** (uav.py 552-560): it terminates correctly at the 0.04 floor, re-places the wing each step, and reports the pusher above the optimum. The tractor's nose wheel moves to 0.08 L, beside the engine at 0.07 L. That packaging is not checked.
5. **Tractor R9**: the negative gust is -1.802 against -1.8, and compliance_tractor.csv row 11 reads False. The concept table prints "3.80" and does not mention it. This is not the frozen concept, but it should be disclosed.
6. **Summary numbers**: every summary and section number I checked matches the records (W0, We, fuel, span, the engine rows and split, the scores, layout, CD0, gusts, trim, performance, the propeller points, the trades and the 19/0 count). The exceptions are the two text errors above (N6 wording, F4 sign).

## 4. Outcome: **pass with actions**

The concept, engine, placard and requirements that Gate A freezes are unaffected. The one material error moves the tail and W0 within 2 % and keeps the ranking. Actions:

1. **Before Stage 2 uses any number**:
   - put the tail lift in N_main (`uav.layout`) and use the forward CG for overturn;
   - add tests for both, plus the placard;
   - re-run 2026-11-20e and re-issue the package;
   - reviewer check of the diff only (expect pusher W0 ≈ 2,806 lb, tail scale ≈ 1.9).
2. Fix the generated text:
   - the N6 attribution (drop "higher top speed, q and gust");
   - the F4 sentence (the build-up is above the fit);
   - the stale sponson risk row;
   - state the sponson cost (+321 lb) in the summary;
   - disclose the tractor's -1.802.
3. Draw the sponsons and the stowed gear in the three-views. Replace the hard-coded `fits = True` with a leg-length and depth check against the sponson.
4. Read the PBS TP100 datasheet before Gate B and update engines.yaml (owner's action).
5. Ask Éder to note that the pusher's 17.7 % nose load is accepted above Raymer's 8-15 % optimum.
6. Carry the Stage 3 measurements already in §11: turboprop lapse, loiter part-power consumption, the empty-weight check, sponson drag, and rotation in ground effect.

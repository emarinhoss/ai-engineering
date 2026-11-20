# Gate A, round 1: Task 12 conceptual design review (2026-11-20)

**Outcome: FAIL, back to Stage 1 with the actions below** (independent reviewer's recommendation;
Éder's rulings on the four gate questions are recorded in section 1 and are carried into the
resubmission). Package reviewed: `docs/validation/2026-11-20_task12_conceptual.md`, records
`runs/task12/stage1/2026-11-20/`, code at commit `ab69840`.

## 1. Éder's rulings (2026-11-20, asked one at a time with options and implications)

| Question | Options shown | Ruling |
|---|---|---|
| Engine: the rubber engine is 110 shp, below Raymer's turboprop statistics (400-5,000 bhp) and below the library's real turboprops (PT6A-42, 850 shp) | find a small turboprop / use the PT6A-42 / enlarge the mission / switch to a piston engine | **Find a small production turboprop** and re-size around it |
| Negative gust: -1.65 at sea level against R9's -1.5 | limit speed in turbulence / raise the negative limit / size for the full envelope | **Raise the negative limit** (ledger now -1.8, Raymer Table 14.2 utility) |
| Concept | pusher as scored / tractor / change the weights | **Pusher, as scored** (frozen) |
| Defaults R10-R15 | accept all / lower the ceiling to 22,000 ft / change rows | **Accept all six** |

Not yet ruled: the 1.3 V_stall speed floor (ledger `speed_over_stall`), which the reviewer notes
binds the loiter speed and sits uneasily with R11; and the sustained-turn requirement the spec's
step 4 names but section 3 never set. Both are asked at the resubmission.

## 2. Independent review (verbatim from the reviewer, round 1)

# Gate A review: Task 12 Stage 1 conceptual package (2026-11-20)

Independent reviewer. Inputs: spec sections 3-6, `docs/validation/2026-11-20_task12_conceptual.md`, `runs/task12/stage1/2026-11-20/`, `conceptual/*.py`, `tests/task12/`. `pytest tests/task12`: 53 passed. Probes: `uav.evaluate('pusher',12,10,L)`, `layout`, `performance`. No repository files were changed.

## 1. Checklist

| # | Answer | Evidence |
|---|---|---|
| A1 | partly | The compliance matrix has 13 rows. R1, R2, R3, R6, R8, R10, R11, R14 and R15 have no rows. The R13 rows show only the 0.05 lower bound. The R9 row (3.80 >= 3.80) restates the input and is wrong at light weight (F2). |
| A2 | partly | We/W0 0.540 + Wf/W0 0.155 = 0.695 < 1, but no margin is stated. The weight table does not sum: items plus fuel come to 1,539 lb against 1,640 lb, because main gear is missing (F1). The explanation of the fit vs build-up gap is only partly right (F4). |
| A3 | yes | The segment table runs W0 1,640 -> 1,400.5 lb. Fuel = 1.06 x 239.5 = 253.9 lb. Breguet units check (C_bhp/3600 per s, R in ft, 550 eta L/D). Inferred L/D is 17.3 in cruise and 17.0 in loiter. Descent is lumped into the 0.995 landing fraction. |
| A4 | partly | Static margin is 0.098 full and 0.102 empty, but computed without the main gear (F1). Trim is checked only at loiter. There is no best-range cruise trim, no elevator authority and no take-off rotation check. |
| A5 | no | Gust is evaluated only at W0. At zero-fuel weight the sea-level gust gives +3.99 / -1.99, above the 3.8 limit (F2). The negative case is not sized. |
| A6 | no | Climb is met (1,403 ft/min) and the ceiling is met with about 100 ft margin (F5). No production engine is in the band (PT6A-42 is 7.7x the power). The fixed-engine re-size is recorded (`fixed_engine.csv`). |
| A7 | partly | The ledger carries bands. Several binding constants are hard-coded without a source or band (F9). The package has no rendered assumption ledger and no list of out-of-calibration uses (F10). |
| A8 | partly | The tests pass, but many equations used have no printed-value test (F8). `test_report.txt` is pytest output, not the equation-to-test table required as package item 10. |
| A9 | partly | A scoring table exists and the tractor optimum is kept in `concept_scores.json`. There is no tractor three-view. The grades are unconfirmed judgements, and two criteria both count the sensor nose. |
| A10 | partly | Fuel fits (5.1 vs 23.3 ft^3). The payload bay volume, gear retraction volume and engine fit are not checked, and the three-view shows no gear, tanks or bay. The CG is computed without the main gear. |
| A11 | partly | Risks 1-6 name a Stage 3 measurement. Risks 7 (scoring) and 8 (negative gust) do not. |
| A12 | no | No record of Éder confirming R10-R15. A further default, `speed_over_stall` 1.3 (ledger, "Not from the library"), binds the loiter speed and conflicts with R11 ("no minimum speed"). |

## 2. Findings (most severe first)

**F1. The main gear is missing from the CG, the layout and the weight statement.** `layout()` builds its items only from keys in the `fixed` dict (`uav.py` 366-391). `main_gear` (101.1 lb, 6 % of W0) is not in that dict, so it is silently dropped. The probe shows layout items plus fuel = 1,538.9 lb. As a result the CG, the static margins, the wing placement and the package table (section 3) all exclude 101 lb. The main gear position is never defined, so tip-back, rotation and pusher propeller clearance cannot be checked. *Fix:* place the main gear (ch. 11 tip-back and overturn criteria), add it to the table and the CG, re-place the wing, and add a rotation and prop-clearance check.

**F2. The gust case is checked only at take-off weight.** Raymer p. 340 notes that a lighter aircraft takes a larger gust load factor. The probe at zero-fuel weight (1,386 lb) with (14.4)-(14.8), U_de 30 ft/s, sea-level V_C 147 kt EAS gives n = +3.99 and -1.99. The package states "manoeuvre limit governs" and reports R9 as met, which is wrong. Re-sizing with n_limit 3.985 gives W0 1,655 lb (+15 lb). The negative miss grows from -1.65 to -1.99. *Fix:* run the gust check across the weight range (at least zero-fuel and end of mission), carry the governing n into Nz, and have Gate decide on the negative case.

**F3. The q in the weight equations does not match the V-n speeds.** Weights use q = 17.6 psf, the slow cruise at 20,000 ft (about 72 kt EAS). The V-n diagram uses V_C 147 kt EAS (73 psf) and V_D 221 kt EAS. Raymer defines q as the cruise q (symbol list, p. 405-407), but the structure is designed to V_C. With q = 73 psf in (15.46)-(15.49), the probe gives W0 1,756 lb (+116 lb, +7 %) and We 986 lb. *Fix:* either placard V_C/V_D to the operating speeds (and redraw the V-n) or use a q consistent with V_C, and state the choice.

**F4. The claim that the build-up is lower because crew items are removed is only partly supported.** In the GA set the crew items are furnishings (15.59), 30 lb (0.019 W0) at 1,640 lb, and air conditioning (15.58), which is zero for N_p = 0. The gap to Table 3.1 x 0.95 is 0.052. Probe decomposition:
- crew items: 0.019;
- component fudge factors (Table 15.4) against the flat 0.95: about 0.006;
- the remaining 0.027: the metal build-up plus furnishings is 0.596 against the metal fit of 0.623, so Raymer's GA equations simply sit below the fit at this size.

The package summary and risk 3 attribute the whole gap to crew items. *Fix:* report this decomposition. Add Table 15.2 "all-else empty" (0.10 TOGW, GA) as a cross-check.

**F5. The ceiling margin is a grid artefact.** `performance()` returns the first altitude that fails, stepping in 250 ft (`uav.py` 447-455). The reported 25,250 ft therefore fails. The probe gives 100.3 ft/min at 25,100 ft and 98.2 at 25,150. The engine is sized to the ceiling, so the real margin is about 0.4 %, using a piston lapse (13.9) applied to a turbine. The CD0 also differs: sizing uses the 25,000 ft value, while the performance check uses the 20,000 ft value. *Fix:* report the last passing altitude, state zero margin, and treat the lapse risk (risk 2) as binding the engine size.

**F6. An unsupported claim on speeds.** `report.py` line 321 hard-codes "the 1.3 V_stall floor sets both speeds". The probe at the cruise weights gives V_L/Dmax 98.1, 97.0 and 92.5 kt against floors of 90.6, 89.6 and 85.5 kt. Cruise flies at L/D max; only the loiter speed is set by the floor (V_minP is about 74 kt). Generated text must come from computed values. The floor itself is an unconfirmed default (A12).

**F7. Constraint diagram.**
- The landing W/S limit of 60.0 (`constraint_limits.json`) is the bisection upper bound (`stage1.py` 64), not a computed limit.
- The best-range and best-loiter wing loadings ((5.13), (5.16)) are absent.
- The sustained turn at loiter, required by spec step 4, is absent.

*Fix:* widen the bracket or report the limit as "not binding below 60", and add the missing lines.

**F8. Test coverage (A8).**
- No printed-value test exists for: the gust (14.4)-(14.8), the take-off transition and climb (17.102)-(17.109), the landing segments, nose gear (15.51), hydraulics (15.55), the Table 10.4 turboprop, Table 3.1, flapped CL_max (12.21), F (12.9), max level speed and best rate of climb. The ground-roll test is only an analytic limit.
- The spec lists the DR-1 as-drawn performance (p. 584-585) as a test source; it is not used.
- The DR-1 weight tests reproduce book slips. (15.54) passes with span 26.6/12. (15.49) passes with L_t = 140 (inches). The UAV correctly uses feet per the symbol list, but this discrepancy is not stated.

*Fix:* add the tests and produce the equation -> test -> result table.

**F9. Hard-coded, unsourced constants (A7).** None of these is in the ledger:
- CD0 increments of +0.02 at take-off and +0.05 at landing (`uav.py` 243, 440-441), not from Raymer's flap/gear drag;
- braking mu 0.5 (the favourable end), rolling mu 0.03, CL_ground 0.1, free roll 2 s;
- climb speed 1.2 V_s;
- component station fractions (`layout` `fixed`);
- the 10 in pusher gear extension.

The field lengths are far from binding (649 and 1,329 ft against 2,500), so the numerical consequence is small, but the rule is broken. *Fix:* move them to the ledger with sources and bands.

**F10. Out-of-calibration uses are under-listed, and the package lacks items 4, 6 and 8.** Missing from the list:
- Table 3.4 C_bhp, derived from large turboprops, applied to a 110 shp engine at part power. By my estimate from the segment table, the loiter needs about 30 of the roughly 52 shp available at 20,000 ft. In my judgement (not from a library source) small turbines run well above 0.5-0.6, so the 0.75 band top may not bracket the true value. An open datasheet is needed.
- The GA group equations and Table 6.3 fuselage length, both fitted to crewed aircraft. The fuselage length sets the tail arm and the wetted area.
- Table 10.4 dimensions extrapolated below 400 bhp. The engine diameter (16.7 in) is about the boattail depth at the 21.1 ft station, and the engine fit is not checked. A PT6A, if chosen, is not checked at all.

The package also lacks a drag-polar plot, the propeller operating points (J, C_P, eta) at sea level and 20,000 ft, and a rendered assumption ledger.

**F11. Trim and stability scope.**
- The trim case "loiter_end_empty_cg" pairs the end-of-loiter weight with the zero-fuel CG.
- There is no cruise trim, no elevator sizing and no rotation check.
- The far-wake downwash is stated and is conservative. My estimate is that Raymer's chart ratio would raise the margin by about 0.03 MAC, still inside R13.
- Other code checked and found correct against the notes: the neutral point (16.9) and the fuselage moment (16.22) in per-radian form.

**F12. Equations checked and found correct.** I checked these against the notes and found no error:
- (12.6), (12.9), (12.15), (12.24)-(12.31) and (12.49) (e = 0.757 at A = 10);
- (13.9), (13.16) and (13.19);
- (10.24): three-blade, 18 Hp^0.25. The docstring of `propeller_diameter_statistical_in` wrongly says only (10.23) is in the notes.
- (15.46)-(15.57), with q in psf and L_t, L and B_w in ft;
- Table 15.4, and Table 15.2 (installed engine factor 1.4);
- (19.8) and (3.10), with units checked;
- the take-off segment structure (17.99)-(17.109) and the landing segment structure.

## 3. Recommended outcome: **Fail (back to Stage 1)**

Reasons:
- A5 and A6 are "no".
- The engine installation, which Gate A is meant to freeze, has no real engine and no fit check.
- The CG omits 6 % of W0.
- Required package items (4, 8, 10) are incomplete.

Most fixes are short. The probes suggest W0 moves by about +15 to +130 lb.

Actions before resubmission:
1. Main gear in the layout, CG and table; rotation, tip-back and prop-clearance check (F1).
2. Gust across the weight range; Gate decision on the negative limit (F2).
3. Consistent q / V_C for the weights and the V-n (F3).
4. Corrected crew-item explanation with the decomposition (F4).
5. Report the ceiling as the last passing altitude with its true margin (F5); remove the hard-coded speed text (F6).
6. Complete the constraint diagram (F7); add the missing tests and the equation table (F8).
7. Move the constants to the ledger (F9); list the out-of-calibration uses and add the polar and propeller points (F10); add cruise trim and elevator checks (F11).
8. Choose the engine route, or get an open small-turboprop datasheet (power, weight, SFC, dimensions), and check its fit.
9. Get Éder's confirmation of R10-R15 and of the 1.3 V_stall floor.

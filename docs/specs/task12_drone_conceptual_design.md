# Task 12 spec: a single-turboprop endurance UAV, designed with Raymer, reviewed, then measured independently

**Status: spec, revision 3 (2026-11-21).** Revision 3 records the Gate A round 4 rulings: R12 ceiling 23,000 ft, R18 one V_C placard (110 kt EAS after the round 4 close), R19 a 25 kt headwind on both transit legs, R16-R18 in the requirement table, Gate A margins (ceiling 500 ft, negative gust 0.1 g; the 5 % power margin was relaxed at the round 4 close with the 110 kt EAS placard), and section 7.1b (the engine rows in Stage 3 are no longer independent). Earlier status: **revision 2 (2026-11-20).** Stage 1 has run since: package `docs/validation/2026-11-20_task12_conceptual.md`, records `runs/task12/stage1/2026-11-20/`. Gate A has not been held. The text below is the spec as written before the run. Revision 1 (same day)
sized a 1 to 4 kg battery drone. Éder then changed the aircraft so that Raymer's weight statistics
apply and the engine is a turbine, and answered eight requirement questions. Section 3 records
each answer with the options he was shown. The figures quoted in section 3 come from a rough sizing
done by hand while the questions were being asked. They are not records, they are used nowhere
else, and Stage 1 replaces them.

Scope: one new aircraft. The inlet line and the Task 10 drone records are not changed.

Rules of `CLAUDE.md` apply unchanged: open data only, every number from a recorded run,
validation before use, a failed check reported and not tuned away, inputs gated, every run
reproducible. Library citations follow `docs/roadmap/2026-11-20_long_term_roadmap.md` section 0.
Raymer is the **2nd edition (1992)** held in the library. Mattingly is *Aircraft Engine Design*,
2nd ed. Anderson APD is *Aircraft Performance and Design*. **[Lib]** marks a method or test target
from a library book. **[Not lib]** marks what the library does not provide; its open source is
recorded before use.

## 1. What the task is

Design a single-engine turboprop unmanned aircraft to a stated surveillance mission. Then answer
one question: **does the design still meet its requirements when other sources measure it?**

1. **Requirements first.** The aircraft is sized to a mission, following Raymer's process
   (section 4), not chosen as the best point of a surrogate.
2. **Inside the statistics.** The take-off weight (about 2,000 to 4,000 lb, section 3) falls
   inside the range of Raymer's single-engine general-aviation data. His weight, drag and
   propeller methods are therefore used near the conditions they were fitted to, which the 1 to
   4 kg drone could not do.
3. **The design source and the measuring source differ.** Stage 1 uses Raymer throughout. Stage 3
   measures the same aircraft with Mattingly, Anderson and the study's own tools, quantity by
   quantity, against tolerances fixed beforehand. If both routes came from the same book, a shared
   error would pass unseen.
4. **A review sits between them.** The configuration is frozen and reviewed before it is measured,
   so the measurement cannot reshape the design to fit.

The low-Reynolds-number problem of Task 10 does not arise. At 20,000 ft the wing's Reynolds number
is a few million, inside Raymer's correlations. The price is that the E387 validation of Task 10
does not apply either: a validation at the new Reynolds number is needed (section 7.1).

## 2. Stages and gates

```
Stage 0  requirements (fixed: section 3)
Stage 1  conceptual design with Raymer  ──►  conceptual design package
Gate A   design review  ──► pass: configuration frozen │ actions: close, re-review │ fail: back to Stage 1
Stage 2  close Gate A actions (if any)
Stage 3  independent measurement with Mattingly, Anderson and the study's tools
Gate B   performance review ──► meets requirements with margin: preliminary design
                               (lofted 3D geometry, roadmap tracks E and F) │ does not: back to Stage 1
```

**About the name of Gate A.** Raymer splits design into conceptual, preliminary and detail phases
and puts the configuration freeze late in preliminary design (**[Lib]** Raymer 2.2, p. 4-7,
Fig. 2.2). He describes no review procedure. In systems-engineering practice a Preliminary Design
Review closes the preliminary phase (**[Not lib]**; NASA Systems Engineering Handbook,
NASA/SP-2016-6105 Rev. 2, is the open source to record). Gate A reviews the Raymer design before
it is measured, so it is run as a design review with PDR-style entry and exit criteria (section 6).
Its outcome freezes the configuration, which in Raymer's terms opens preliminary design. Gate B
decides whether preliminary design proper is worth starting.

## 3. Requirements (fixed by Éder, 2026-11-20)

| ID | Requirement | Value | Éder's choice (options shown) |
|---|---|---|---|
| R1 | Class | single-engine turboprop endurance UAV | Q1 (turboprop endurance / jet-trainer turbofan / high-altitude turbofan / fighter-class jet) |
| R2 | Engines | one | Q2 (one / two) |
| R3 | Engine selection | rubber-engine sizing first, then the nearest real turboprop and a fixed-engine re-size | Q3 (rubber then real / fixed PT6A-42 / own cycle design) |
| R4 | Payload | 500 lb, mission equipment only (flight avionics are part of the empty weight) | Q4 (200 / 500 / 1,000 lb) |
| R5 | Mission | take-off; climb to 20,000 ft; cruise 200 nm out; loiter 8 h on station; cruise 200 nm back; descend; land | Q5 (200 nm + 8 h / 12 h loiter / 16 h loiter / 200 nm + 10 h) |
| R6 | Cruise and loiter altitude | 20,000 ft, ISA | Q6 (20,000 / 25,000 / 10,000 ft) |
| R7 | Take-off and landing | paved runway, at most 2,500 ft over a 50 ft obstacle, sea level ISA; stall at most 70 kt clean | Q7 (runway with retractable gear / runway with fixed gear / catapult) |
| R8 | Landing gear | retractable tricycle | Q7 |
| R9 | Structure | advanced composite (Raymer's empty-weight factor 0.95, carried as a band 0.90 to 1.00); limit load factor +3.8 / -1.5, factor of safety 1.5; gust loads checked and the larger case used | Q8 (composite normal / metal normal / composite utility) |

Requirements Éder was not asked about. These are defaults, each with its reason, and Gate A
confirms them:

| ID | Requirement | Default | Reason |
|---|---|---|---|
| R10 | Fuel reserve and trapped fuel | Raymer's 6 % allowance | **[Lib]** Raymer (3.11), p. 23 |
| R11 | Cruise legs | flown at the best-range speed; no minimum speed | the requirement is time on station, not transit time |
| R12 | Climb | sea-level rate of climb at least 1,000 ft/min; service ceiling (100 ft/min) at least 23,000 ft (revised from 25,000 ft at Gate A round 4, Éder 2026-11-21) | reach 20,000 ft with margin after the power lapse |
| R13 | Static margin | 5 to 15 % mean chord over the centre-of-gravity range, full to empty fuel | stable, not over-stable; the fuel burn moves the centre of gravity |
| R14 | Technology | production turboprop; composite airframe; no crew systems (no cockpit, seats, pressurisation, crew oxygen) | Raymer 2.3 asks for a technology decision first (p. 7) |
| R15 | Flight avionics | autopilot, datalink, navigation: an uninstalled weight fixed in the ledger, installed by Raymer's general-aviation avionics relation | **[Lib]** Raymer (15.57), as DR-1 uses it, p. 576 |
| R16 | Manoeuvre at loiter | sustained 30 deg banked turn (n = 1.155) at loiter speed and 20,000 ft | accepted at Gate A round 3 |
| R17 | Speed floor | every mission leg at least 1.3 V_stall | Gate A round 3 ruling |
| R18 | Design cruise speed | one V_C placard of 110 kt EAS at every altitude, enforced by the autopilot; structure and gusts sized at it (150 kt EAS at round 3, 100 kt EAS at round 4 before the headwind) | Gate A round 4 rulings, Éder 2026-11-21 |
| R19 | Wind | both 200 nm transit legs against a 25 kt headwind at 20,000 ft; the loiter is sized in still air | Gate A round 4 ruling, Éder 2026-11-21 |

**The figures Éder was shown** (hand arithmetic during the questions, not a record): Raymer (3.4)
with the single-engine fit and Table 3.4 turboprop values, an assumed L/D of 18 in cruise at 200 kt
and 15.6 at loiter at 150 kt, gave a take-off weight of about 2,750 lb for R5. Stage 1 computes it
properly.

## 4. Stage 1: conceptual design with Raymer

Template: Raymer's DR-1 (ch. 21.2, p. 559-602), a single-engine propeller aircraft, step for step.
Its printed numbers become unit tests that show each method is coded correctly before it touches
the UAV. Raymer's second example, the supercruise fighter (21.3, p. 603-655), supplies extra tests
for the rubber-engine steps that DR-1 does not exercise.

**Turboprop specifics.**
- Fuel fractions by Breguet: cruise (3.5)-(3.6) and loiter (3.7)-(3.8), p. 16-17, with the
  equivalent specific fuel consumption of a propeller engine (3.9)-(3.10), p. 18. First-pass values
  from Table 3.4, p. 19 (turboprop C_bhp 0.5 cruise and 0.6 loiter, propeller efficiency 0.8).
- Take-off weight from (3.4), p. 12, with no crew. The empty-weight fit (Table 3.1, p. 13, general
  aviation single engine, A = 2.36, C = -0.18) is fitted to crewed aircraft. The first pass uses it
  as printed, times 0.95 for composite. The refined pass (step 7) builds the empty weight up from
  Raymer's general-aviation component equations (ch. 15) with the crew items left out, and reports
  how far that build-up sits from the fit. **This is the main assumption of the task and is stated
  in every report.**
- Rubber engine: power from the constraint analysis; engine weight and dimensions from Raymer's
  turboprop scaling laws (**[Lib]** Tables 10.3-10.4, p. 224, flagged in the notes for a length
  exponent that disagrees between the two tables).
- Fixed engine: the nearest production turboprop to the rubber engine's power, from an open
  source. Mattingly Table C.1 (p. 519) lists the PT6A-42 (850 eshp, 391 lb) and PT6A-45R
  (1,197 eshp, 434 lb). If the rubber engine is much smaller, another open datasheet is needed
  (**[Not lib]**). Then re-size as DR-1 does (6.3, p. 108-109; DR-1 p. 568).

| Step | Work | Raymer source | Output | Unit test (printed value) |
|---|---|---|---|---|
| 1 | Mission profile R5 with segment fractions | 3.4, p. 14-17; Table 3.2 historical segment fractions | mission table | none (inputs) |
| 2 | Two concept sketches as code-drawn three-views: (a) nose tractor, aft tail; (b) pusher with the sensor in the nose and an aft or twin-boom tail. Scored on stated criteria (sensor field of view, centre-of-gravity range, propeller and exhaust installation, drag, structure) | 2.3, Fig. 2.3; wing geometry 4.3, p. 47-65; tail arrangement 4.5, p. 67-76; pusher exhaust note, ch. 10, p. 547 | three-views, scoring table, chosen concept | none (decision) |
| 3 | First-pass sizing: W0 from (3.4); fuel fraction from (3.5)-(3.11); L/D from the wetted aspect ratio of the sketch | (3.4), p. 12; L/D 3.4, p. 19-23 | W0, fuel fraction, empty fraction, L/D | DR-1 initial sizing, p. 566-567 |
| 4 | Power loading and wing loading from each requirement: stall (R7), take-off and landing (R7), best prop loiter and range wing loadings, climb and ceiling (R12) with power lapse, sustained turn at loiter | ch. 5: stall (5.6), p. 85-86; take-off p. 87-89; landing p. 90-91; prop range (5.13), p. 92-93; prop loiter (5.16), p. 93-94; climb p. 97-99; ceiling p. 99; selection 5.4, p. 99-100 | constraint table, chosen W/S and P/W | DR-1, p. 564-565 |
| 5 | Refined sizing with the rubber engine; geometry sizing: fuselage, wing, tails by volume coefficients, control surfaces | 6.2, p. 102-108; 6.4, p. 109-113; Table 6.4, p. 112; 6.5, p. 113-116 | sized geometry, rubber engine | DR-1 refined sizing, p. 566-567; fighter rubber-engine steps, p. 610-614 |
| 6 | Configuration layout: three-view with internal arrangement (engine, fuel tanks, payload bay, retracted gear, avionics); centre of gravity full and empty; fit checks | ch. 7-11 (layout and loft; special considerations; payload; propulsion and fuel system p. 193-224; landing gear and subsystems) | layout drawing, mass and CG table | DR-1 layout data, p. 569; fighter fuel tanks and fuel CG, p. 618 |
| 7 | Analysis of the layout: aerodynamics (drag build-up with retracted gear, span efficiency, maximum lift with flaps), propeller and installed power at altitude, structures (V-n with gust at 20,000 ft and sea level), component weights without crew items, stability and trim (full and empty fuel), performance | ch. 12: p. 280-290, (12.48)-(12.49), p. 298-299, (12.15), p. 270; ch. 13: (13.10)-(13.16), p. 327; ch. 14: (14.2)-(14.8), p. 339, Figs. 14.7-14.8, p. 341; ch. 15 general-aviation equations; ch. 16: 16.3, p. 414-432; ch. 17 | drag polar, propeller operating points, V-n diagram, weight statement, stability summary, as-drawn performance | DR-1 aero p. 571-573 (fuselage cf 0.0026, FF 1.25, CD0 0.0250, e 0.87); propulsion p. 574-575; weights p. 576-578 (installed avionics 9.5 lb); stability p. 579-580 (neutral point 1.188 mean chords, downwash 0.38); as-drawn performance p. 584-585 |
| 8 | Fixed-engine re-size with the chosen production engine; sizing matrix and carpet plot over wing loading and aspect ratio with constraint lines; trades (loiter time against payload, composite factor across its band, altitude 15,000 to 25,000 ft) | 6.3, p. 108-109; ch. 19, p. 519-535; DR-1 p. 568 and p. 586-602 | final sizes, carpet plot, trade table | DR-1 fixed-engine sizing p. 568; refined sizing p. 586-587 |

**What Raymer does not cover here**, and what is used instead. Each goes into the package's
assumption ledger with a band.

| Gap | What is used |
|---|---|
| No unmanned category in Table 3.1 | single-engine fit as printed for the first pass; component build-up without crew items for the refined pass; the difference is reported |
| Turboprop off-design performance (power lapse, SFC at part power) | Raymer's methods in Stage 1; Mattingly Appendix K in Stage 3 (section 7) |
| Production engine below 850 eshp | an open manufacturer datasheet **[Not lib]** |
| Airfoil data at the design Reynolds number | Raymer's charts in Stage 1; SU2 polars and an open NACA data report in Stage 3 **[Not lib]** |
| UAV flight avionics weight | ledger value with a band, installed by (15.57) |

**Stage 1 output: the conceptual design package**, in `runs/task12/stage1/<date>/` and rendered by
a script to `docs/validation/<date>_task12_conceptual.md`:

1. Requirements compliance matrix: each requirement, value achieved, margin, producing step.
2. Three-view and internal layout, drawn by code from the sized geometry.
3. Weight statement by component, with the centre of gravity full and empty, and the fit
   against build-up comparison.
4. Drag polar; propeller and installed-power points at sea level and 20,000 ft; fuel by mission
   segment.
5. Constraint diagram (P/W against W/S) and carpet plot, chosen point marked.
6. V-n diagram with gust lines at both altitudes.
7. Stability and trim summary.
8. Assumption ledger with sources and bands; correlations used outside their calibration.
9. Risk list, each risk with how Stage 3 will measure it.
10. Test report: every Raymer equation used, its printed-value test, pass or fail.

## 5. Code and records (Stage 1)

- New package `conceptual/` (numpy only), one file per step: `mission.py` (step 1), `sizing.py`
  (steps 3, 5, 8), `constraints.py` (step 4), `geometry_sizing.py` (step 5), `layout.py`
  (step 6), `raymer_aero.py`, `raymer_propulsion.py`, `raymer_loads.py`, `raymer_weights.py`,
  `raymer_stability.py`, `raymer_performance.py` (step 7). Each function's docstring names its
  equation and page.
- Units: Raymer works in foot-pound-second units. Computation stays in his units inside
  `conceptual/` so the printed tests compare like with like; `conceptual/units.py` converts at
  the boundary; records carry both.
- Reuse, do not copy: `physics/atmosphere.py` (ISA), `drone/naca.py` (sections), `drone/vlm.py`
  (Stage 3 only).
- Tests in `tests/task12/`, one per printed value in section 4, written **before** the function is
  applied to the UAV. A test that fails stops that step. It is reported, and the equation is checked
  against the page, not adjusted to pass.
- Records: `runs/task12/stage1/<date>/` with inputs, commit, ledger hashes and every output table.

## 6. Gate A: design review

**Entry criteria.** The package of section 4 is complete. Every printed-value test passes, or its
failure is explained against the page. The compliance matrix has no blank row.

**Reviewers.** An independent review agent, given the package and this spec but not the
designer's working notes or conclusions. Éder decides the outcome.

**Checklist** (each answered yes or no, with evidence, in `docs/reviews/<date>_task12_gateA.md`):

| # | Item |
|---|---|
| A1 | Every requirement traces to a number in the package, with its margin. |
| A2 | Weight closes. Empty and fuel fractions sum below 1 with a stated margin. The fit against build-up difference is reported and explained. |
| A3 | Fuel closes for every mission segment, including the 6 % allowance. |
| A4 | Static margin inside R13 at full and empty fuel. Trim at loiter and at best-range cruise with elevator authority to spare; take-off rotation possible. |
| A5 | Structure sized for the larger of the manoeuvre and gust cases at both altitudes. |
| A6 | Engine: installed power at 20,000 ft meets climb and ceiling. The chosen production engine is within the rubber engine's power band, and the fixed-engine re-size is recorded. |
| A7 | Every assumption has a source and a band. Out-of-calibration uses are listed. |
| A8 | Every Raymer equation used has a passing printed-value test or an explained failure. |
| A9 | Concept choice justified by its scoring table; the rejected concept is kept. |
| A10 | Layout fits: tanks hold the fuel, the payload bay holds the payload, the gear retracts into the volume shown, and the centre of gravity stays in range as fuel burns. |
| A11 | Every risk names how Stage 3 will measure it. |
| A12 | The defaults R10 to R15 are confirmed or changed by Éder. |

**Outcomes.** Pass: configuration frozen (layout type, tail type, planform family, engine
installation); only sizes may change afterwards (Raymer: preliminary design starts when major
changes stop, p. 4). Pass with actions: closed in Stage 2 and re-checked by the same reviewer.
Fail: back to Stage 1, reasons recorded.

## 7. Stage 3: measure the frozen design with other sources

Principle: **each quantity is measured by a route that does not share the design route's source.**
A tolerance for agreement is fixed here, per quantity, before any measurement runs (to be filled in
at Gate A, with Éder). A disagreement outside tolerance is explained, not averaged away, and decides
whether the design goes back to Stage 1.

### 7.1 Measurement table

| Quantity | Raymer (Stage 1) | Independent measurement | Source |
|---|---|---|---|
| Engine fuel burn and power lapse | Table 3.4 and ch. 13 | turboprop parametric and off-design cycle analysis at the design point (20,000 ft, loiter and cruise speeds) and at sea level | **[Lib]** Mattingly App. K, p. 589-608; printed design-point results at Mach 0.8, 25,000 ft (p. 597-599) as tests |
| Propeller efficiency at loiter, cruise and climb | (13.10)-(13.16), Fig. 13.10 | actuator disk with a real-to-ideal factor; blade-element estimate | **[Lib]** Mattingly App. L, (L.7)-(L.9), p. 612; (L.14)-(L.15), p. 615 |
| Constraint diagram | ch. 5 | Mattingly's master equation with turboprop lapse | **[Lib]** Mattingly (2.11)-(2.17), p. 24-33; (2.22) take-off |
| Mission fuel | Breguet fractions, (3.5)-(3.11) | Mattingly's segment-by-segment mission analysis with the App. K fuel burn | **[Lib]** Mattingly ch. 3 |
| Take-off weight (whole sizing) | Raymer (3.4) with Table 3.1 and ch. 15 | Anderson's propeller-aircraft design procedure, a separate sizing route with its own weight estimate | **[Lib]** Anderson APD ch. 8 (8.1-8.12), weight estimate (8.83)-(8.84), p. 449-452; printed W0 = 4,434 lb as test |
| Lift slope and span efficiency | (12.6)-(12.9), (12.49) | the study's vortex lattice (validated by V6a to V6c), with a compressibility correction for Mach about 0.3; Anderson's lifting-line forms | study tools; **[Lib]** Anderson APD (2.15), p. 81; (2.18a), p. 86; Examples 2.5 and 2.8 as tests |
| Zero-lift drag and drag due to lift | build-up, p. 280-290 | Anderson's drag-polar method | **[Lib]** Anderson APD 2.8-2.9, (2.27)-(2.47), p. 107-130 |
| Section polars at the design Reynolds number | ch. 4 and 12 | SU2 RANS polars of the chosen section at its Reynolds and Mach numbers, after a new validation row on an open NACA dataset at Re of a few million | study tools; NACA data **[Not lib]** |
| Best-range and best-endurance speeds; power curves | ch. 17 | power required and available curves; closed-form optima | **[Lib]** Anderson APD ch. 5, (5.30)-(5.46), p. 219-222; Example 5.4 as test |
| Range and endurance | Breguet, ch. 3 and 17 | Anderson's propeller range and endurance relations | **[Lib]** Anderson APD (5.153), p. 296; (5.169), p. 304 |
| Climb rate and ceiling | ch. 17, p. 463-467 | Anderson's propeller climb relations with the App. K lapse | **[Lib]** Anderson APD (5.122), p. 415 |
| Take-off and landing distances | ch. 5 and 17 (17.99)-(17.101), p. 487 | Anderson's ground roll and landing relations | **[Lib]** Anderson APD (6.95), p. 393 |
| Static margin and trim | ch. 16 | Anderson's static-stability relations; downwash from the vortex lattice | **[Lib]** Anderson APD 8.6.7, (8.76)-(8.78), p. 444 |
| V-n and corner speed | ch. 14 | Anderson's V-n treatment | **[Lib]** Anderson APD (6.54), p. 343; Example 6.3 as test |

The take-off-weight row is a partly independent check: Anderson's chapter 8 sizes a propeller
aircraft by its own route and first estimates the empty fraction from his own historical data
(0.62, (8.5) p. 400), but his refined build-up (8.83a-g, p. 449) is Raymer's Table 15.2
approximate method. Both are run and reported separately (corrected at Gate A close).

### 7.1a Agreement tolerances (accepted by Éder at Gate A close, 2026-11-20)

Fixed before any Stage 3 measurement runs. "Raymer" is the Stage 1 value in
`runs/task12/stage1/2026-11-20d/design_pusher.json` (from revision 3: the Stage 1 record that passes Gate A round 4); the independent value is Stage 3's. A row
outside tolerance is diagnosed and reported, and if it moves a requirement margin below zero the
design returns to Stage 1.

| Quantity | Tolerance | Reason for the size |
|---|---|---|
| Shaft power available at 20,000 and 25,000 ft (App. K against the piston lapse (13.9)) | ±10 % | the ceiling binds the engine; 10 % is about the engine's present power margin |
| Fuel consumption at cruise and loiter power (App. K against the datasheet value) | ±10 % | fuel is 27 % of W0; 10 % of fuel is about 3 % of W0 |
| Propeller efficiency at climb, cruise, loiter (App. L against 0.80) | ±0.05 absolute | Raymer's Table 3.4 value is itself rounded to 0.05 |
| Installed power required by each constraint (Mattingly (2.11)-(2.17) against Raymer ch. 5) | ±5 % | same physics by a second route; larger differences mean a coding error |
| Mission fuel (Mattingly ch. 3 against Raymer's Breguet fractions) | ±5 % | same physics, different bookkeeping |
| Take-off weight (Anderson ch. 8 sizing against Raymer) | ±10 % | Anderson's first estimate (empty fraction 0.62 from his own historical data, (8.5)) is independent; his refined build-up (8.83) is Raymer's Table 15.2 approximate method, so it is a same-author cross-check, reported as such |
| Lift slope (vortex lattice against (12.6)) | ±5 % | the lattice passed its own analytic checks to 2 % (Task 10 V6a) |
| Span efficiency, inviscid part (lattice against (12.49)'s implied value) | ±0.05 absolute | (12.49) includes viscous drag due to lift; the lattice does not, so the comparison is of the inviscid share only, stated with the result |
| Zero-lift drag (Anderson drag polar against Raymer's build-up) | ±10 % | different form-factor and friction treatments |
| Section CL_max at the design Reynolds number (SU2, after a NACA-data validation row) | inside the ledger band 1.3-1.7 | the band is what Stage 1 carried |
| Best-range and best-endurance speeds, climb rate | ±3 % | closed forms on the same polar; checks the arithmetic |
| Service ceiling | ±1,000 ft | sets the engine; 1,000 ft is about 3 % of the lapse |
| Take-off and landing distances | ±15 % | both are far from binding (under 1,500 ft against 2,500) |
| Static margin | ±0.03 MAC | the R13 band is 0.10 wide |
| V-n points and gust load factors | ±5 % | same relations by a second source |

Gate B robustness threshold (section 7.4): info-gap horizon at least 1 (the ledger's own bands)
at R5 and R7.

### 7.1b Engine rows after the return to Stage 1 (Gate A round 4 ruling 5, Éder 2026-11-21)

From the Gate A round 4 design on, Stage 1 sizes with the TP100's Mattingly App. K table
(`data/task12/tp100_table.json`), so the rows above that compare App. K power, SFC, ceiling and
mission fuel with Stage 1 would compare the table with itself. **They are declared not independent
and are not used as agreement checks.** In their place:

1. **Model check.** Mattingly's burner fuel/air ratio with variable specific heats (the book's MSH
   model, ch. 4) replaces the constant-cp burner; the App. K validation against Figs. K.2-K.4,
   K.7 and K.9 is re-run with tolerances fixed before the run; the table is regenerated and the
   change in mission fuel and W0 at the frozen point is reported against the ±10 % SFC tolerance.
   **Tolerances for the re-validation, fixed 2026-11-21 before the variable-cp code exists**
   (book values are figure read-offs in the library notes):

   | Comparison (MSH with the variable-cp burner) | Tolerance |
   |---|---|
   | Fig. K.4 optimum turbine ratio tau_t* at pi_c 5, 10, 20, 35 | ±0.015 absolute |
   | Figs. K.2-K.3 envelope: F/m0 at pi_c 5, 17; S at pi_c 5, 17, 35 | ±5 % |
   | Fig. K.7 full-throttle thrust lapse F/F_SL at 5-30 kft | ±0.015 absolute |
   | Fig. K.9 part-throttle minimum S at 15 kft, M0 0.3, 0.5, 0.8 (eta_prop,max 0.9) | within ±10 % of the book |

   A row outside its tolerance is reported as failed, with its numbers, and not tuned. The
   constant-cp results (S 2.5-7.5 % high, part throttle 11-14 % high) are the baseline.

2. **Validity.** The share of mission sub-steps where App. K's choked-turbine assumption fails is
   reported with the result.
3. **Closing check when available.** The maker's part-power SFC curve and altitude rating; until
   then the engine rows rest on the model, stated as such.

### 7.1c Rulings from the first Stage 3 pass (Éder, 2026-11-21)

1. **Engine family (review B-3).** The TP100 cycle family is widened toward lower component
   efficiencies (e_c 0.75-0.85, e_t 0.80-0.90); members calibrating below pi_c 3.0 are set aside
   (study judgement); the variable-cp (MSH) burner is the default. Recorded result: at the frozen
   point the corrected table changes mission fuel by -3.6 % and the re-sized W0 by -3.0 %
   (`runs/task12/stage3/2026-11-21/engine_change.json`).
2. **Engine validity.** With pi_c about 3.4 the turbines are below the choking ratio at every
   operating point, so App. K's off-design assumption fails for this engine everywhere. The table
   is used with that stated; the engine SFC and power +-10 % band ends remain the carried
   uncertainty; the maker's part-power curve is the closing check.
3. **Downwash.** The vortex-lattice downwash replaces the far-wake formula in Stage 1's layout
   (the lattice gave 0.389 against 0.338 and the empty-fuel static margin fell to 0.045, below
   R13). The Stage 3 downwash and static-margin rows therefore become checks of the same model,
   declared not independent, like the engine rows in 7.1b. Tail height above the wing plane is a
   ledger assumption (0.4 D_f, banded).
4. The design returns to Stage 1 with items 1 and 3; Gate A is re-checked on the result.

### 7.2 Uncertainty of the measured performance

- The banded assumptions (composite factor, empty-weight fit against build-up, fuel burn, propeller
  efficiency, L/D, avionics weight) are propagated through the Stage 3 model jointly, not only
  one at a time.
- **Info-gap robustness** of the frozen design against R5 (8 h on station) and R7 (field length):
  the largest error horizon over the banded quantities at which both still hold. **[Lib]** DMDU
  ch. 5, (5.3)-(5.5), p. 104-105, and ch. 10, (10.4)-(10.8), p. 212-214. The library's tested
  scalar-linear implementation is the starting point; the multi-quantity worst case is new code.

### 7.3 Stage 3 output

`docs/validation/<date>_task12_performance.md`: the measurement table with Raymer's value, the
independent value, the difference, the tolerance and the verdict per row; performance against each
requirement with margins; the robustness curves; the disagreements and their diagnosis.

### 7.4 Gate B: performance review

Pass when every requirement is met by the independent measurement with its margin, every row is
inside tolerance or explained, and the robustness horizon at the requirements is at least the
value fixed at Gate A (default: horizon 1, the ledger's own bands). Otherwise back to Stage 1 with
the measured values in place of the estimates (Raymer's design wheel, Fig. 2.1, p. 3).

## 8. Model allocation

Per `CLAUDE.md`. The top model: the mission and requirement interpretation, step 2's scoring, the
crew-less weight treatment, stability, loads, engine and propeller physics, every tolerance, both
gate reviews, and review of any diff that can change a number. The implementing model: the
`conceptual/` modules and their printed-value tests from this spec. The documentation model:
three-view drawings, the package rendering, plots and tables, with review of anything that prints
a number.

## 9. Cost (estimates, not measured)

| Stage | Compute | Effort |
|---|---|---|
| 1 | container only, seconds per evaluation | the bulk: about eleven modules with their tests |
| Gate A | none | one review pass and Éder's ruling |
| 3 | container for the analytic routes and the vortex lattice; Colab for the SU2 validation row and the chosen section's polars (about 15 to 20 cases) | about six modules |
| Gate B | none | one review |

## 10. What the library does not cover for this task

An unmanned-aircraft weight category; production turboprop data below 850 eshp; airfoil data at
the design Reynolds number; UAV flight-avionics weights; a formal design-review procedure. Each
appears as **[Not lib]** above with what is used instead.

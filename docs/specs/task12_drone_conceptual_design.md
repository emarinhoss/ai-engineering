# Task 12 spec (draft): design the drone with Raymer, review it, then measure it independently

**Status: draft, written 2026-11-20 at Éder's request. Nothing in this note has been run.** It
fixes how the work is done before any code or any number exists, as Task 0 did for the inlet. The
requirements in section 3 are proposals and have to be confirmed by Éder before Stage 1 starts.

Scope: the drone only. The inlet line is not touched.

Rules of `CLAUDE.md` apply unchanged: open data only, every number from a recorded run,
validation before use, a failed check reported and not tuned away, inputs gated, every run
reproducible. Library citations follow the conventions of
`docs/roadmap/2026-11-20_long_term_roadmap.md` section 0. Raymer means the **2nd edition (1992)**
held in the library. **[Lib]** marks a method or test target taken from a library book; **[Not
lib]** marks something the library does not provide, whose open source must be recorded before use.

## 1. What changes from Task 10, and why

Task 10 asked an optimisation question: over a box of six inputs, where is the endurance-mass
front? Task 12 asks a design question: **given stated requirements, what aircraft meets them, and
does it still meet them when someone else measures it?** The two give different answers.

1. **Requirements first.** The aircraft is sized to a mission (Raymer's process, section 4), not
   chosen as the argmax of a surrogate. "Maximise endurance" becomes "meet at least E_req with a
   stated margin, then take the lightest or most robust design that does".
2. **The configuration is a decision, not fixed.** Task 10 fixed a conventional tractor layout
   with a straight tapered wing and an aft tail. Stage 1 compares two or three concepts and
   records why one was chosen.
3. **The design source and the measuring source are different.** Stage 1 uses Raymer for
   everything. Stage 3 measures the same aircraft with other books and with the study's own
   validated tools, and compares quantity by quantity. Agreement between two independent routes
   is the evidence. If both came from the same book, the same error would pass silently.
4. **A review sits between them.** The design is frozen and reviewed before it is measured, so
   the measurement cannot quietly reshape the design to fit.

Task 10's records and code are not changed. Its inverse answer is used at the end as one more
reference point (section 7.5), never as the starting point, so the new design is not anchored on it.

## 2. Stages and gates

```
Stage 0  requirements confirmed by Éder
Stage 1  conceptual design with Raymer  ──►  Conceptual design package
Gate A   design review  ──► pass: configuration frozen │ actions: close and re-review │ fail: back to Stage 1
Stage 2  close Gate A actions (if any)
Stage 3  independent performance measurement with other library books and the study's tools
Gate B   performance review ──► meets requirements with margin: go to preliminary design
                               (lofted 3D geometry, roadmap tracks E and F) │ does not: back to Stage 1
```

**About the name of Gate A.** Raymer splits design into conceptual, preliminary and detail phases
and puts the configuration freeze late in preliminary design (**[Lib]** Raymer 2.2, p. 4-7,
Fig. 2.2). He describes no review procedure. In the usual systems-engineering life cycle a
Preliminary Design Review closes the preliminary phase, and the review that follows conceptual
design is a conceptual or system design review (**[Not lib]**; NASA Systems Engineering Handbook,
NASA/SP-2016-6105 Rev. 2, is the open source to record). What is asked here is a review of the
Raymer design before performance is measured, so **Gate A is run as a design review with
PDR-style entry and exit criteria** (section 6). Its outcome freezes the configuration, which is
the step that, in Raymer's terms, opens preliminary design. Gate B then decides whether
preliminary design proper (the lofted geometry and the 3D CFD ladder of the roadmap) is worth
starting.

## 3. Requirements (proposed; Éder to confirm or change each row)

The defaults carry over from Task 10 where Task 10 had a value, so the two studies stay
comparable.

| ID | Requirement | Proposed value | Origin of the default |
|---|---|---|---|
| R1 | Payload mass | 0.5 kg | Task 10 spec section 2 |
| R2 | Payload volume | to be stated (a box, in mm) | new; Task 10 had none |
| R3 | Maximum take-off mass | at most 4.0 kg | EASA open category class C2, Task 10 |
| R4 | Endurance at loiter, still air, sea-level ISA | **E_req to be set** (for example 2 h) | new; Task 10 maximised instead |
| R5 | Reserve | 10 % of usable energy at landing | new; Raymer's reserves are fuel-based (p. 14-16) |
| R6 | Dash or cruise speed | V_max at least 20 m/s (penetrate a 10 m/s wind) | new |
| R7 | Stall speed | at most 10 m/s clean | new; sets wing loading for hand launch |
| R8 | Launch | hand launch (no runway) | new |
| R9 | Recovery | belly landing | new |
| R10 | Climb rate | at least 2 m/s at sea level | Task 10 sizing rule |
| R11 | Load factors | limit +3.8 / -1.5, factor of safety 1.5, gust per section 4 step 7 | Task 10 ledger; gust new |
| R12 | Static margin | 5 to 15 % mean chord over the whole centre-of-gravity range | new |
| R13 | Span | at most 3.0 m (transport) | Task 10 box upper bound |
| R14 | Technology | components purchasable today: Li-ion or LiPo pack, brushless motor, fixed-pitch propeller, foam or composite airframe | Raymer 2.3 asks for a technology decision first (p. 7) |

R4 is the one value the design hinges on. Everything else has a usable default.

## 4. Stage 1: conceptual design with Raymer

Template: Raymer's worked example DR-1 (ch. 21.2, p. 559-602), step for step. It is the only
complete conceptual design in the library, and its printed numbers become the unit tests that
show each method is coded correctly before it touches the drone.

**The electric adaptation.** Raymer (1992) sizes fuel-burning aircraft. Batteries do not get
lighter in flight, so the Breguet weight-fraction forms (3.5)-(3.8) do not apply. The sizing
equation keeps its form, **[Lib]** Raymer (3.4), p. 12, with the battery in place of the fuel:

    W0 = W_payload / (1 - f_b - We/W0)

The battery fraction comes from an energy balance over the mission segments. For a level loiter
segment of duration t at speed V with lift-to-drag ratio L/D:

    f_b = g t V / (e_spec DoD eta_p (L/D))

This relation is **[Not lib]**. It is derived from the same energy balance as
`drone/mission.endurance_h`, and a unit test makes the two agree. It has a consequence that shapes
the design: at fixed V and L/D the battery fraction does not depend on W0, so a solution exists
only if f_b + We/W0 < 1. Raymer's "does the aircraft close" question becomes "is there a speed,
L/D and empty fraction for which the fractions sum below one with margin".

| Step | Work | Raymer source | Output | Unit test (DR-1 or printed value) |
|---|---|---|---|---|
| 1 | Requirements and mission profile: launch, climb, cruise out, loiter, cruise back, reserve, land; one energy per segment | 2.3, p. 7-10; mission profiles 3.4, p. 14-16; DR-1 requirements p. 560 | `requirements.yaml`, mission table | none (inputs) |
| 2 | Two or three concept sketches as code-drawn three-views: (a) conventional tractor with aft tail, (b) pusher with twin booms or a V-tail, (c) one alternative Éder names. Selection by a stated scoring table | 2.3, Fig. 2.3; wing geometry 4.3, p. 47-65; tail arrangement 4.5, p. 67-76; DR-1 sketches p. 561-563 | three-views, scoring table, chosen concept | none (decision) |
| 3 | First-pass sizing: W0 from (3.4) with f_b from the energy balance; L/D from the wetted aspect ratio of the sketch; We/W0 from a stated source | (3.4), p. 12; L/D estimation 3.4, p. 19-23; empty-weight fractions Table 3.1, p. 13 | W0, f_b, We/W0, first L/D | DR-1 initial sizing, p. 566-567 |
| 4 | Power loading and wing loading from each requirement: stall (R7), loiter (best prop loiter wing loading), climb (R10), turn, launch speed (R8); selection | ch. 5: stall (5.6), p. 85-86; prop loiter (5.16), p. 93-94; turn (5.17)-(5.20), p. 94-96; sustained turn (5.21), p. 96-97; climb, p. 97-99; catapult form (5.10), p. 89, as the launch analogue; selection 5.4, p. 99-100 | constraint table, chosen W/S and P/W | DR-1 power and wing loading, p. 564-565 |
| 5 | Refined sizing (Raymer's rubber engine, here rubber battery and motor) and geometry sizing: fuselage, wing, tails by volume coefficients, control surfaces | 6.2, p. 102-108; geometry 6.4, p. 109-113; tail volumes Table 6.4, p. 112; control surfaces 6.5, p. 113-116 | sized geometry | DR-1 refined and fixed-engine sizing, p. 566-568 |
| 6 | Configuration layout: three-view with internal arrangement (battery, payload, motor, servos, avionics), centre-of-gravity table, fit check | ch. 7-11 (layout and loft, special considerations, payload, propulsion integration, subsystems including the electrical system, p. 253) | layout drawing, mass and CG table | DR-1 layout data, p. 569 |
| 7 | Analysis of the layout: aerodynamics (drag build-up, span efficiency, maximum lift), propulsion (propeller), structures (V-n with gust), weights (component build-up), stability and control (neutral point, static margin, trim, tail and control sizing), performance | ch. 12: build-up p. 280-290, (12.48)-(12.49), p. 298-299, (12.15), p. 270; ch. 13: (13.10)-(13.16), p. 327; ch. 14: (14.2)-(14.8), p. 339, Figs. 14.7-14.8, p. 341; ch. 15; ch. 16: 16.3, p. 414-432; ch. 17 | drag polar, propeller map, V-n diagram, weight statement, stability summary, as-drawn performance | DR-1 aero p. 571-573 (cf 0.0026, FF 1.25, CD0 total 0.0250, e 0.87); propulsion p. 574-575; weights p. 576-578; stability p. 579-580 (neutral point 1.188 mean chords, downwash 0.38); as-drawn performance p. 584-585 |
| 8 | Refined sizing of the as-drawn aircraft; sizing matrix and carpet plot over wing loading and aspect ratio with the constraint lines; trade studies (battery chemistry, payload, endurance requirement) | ch. 19, p. 519-535; DR-1 W/S-aspect ratio optimisation and constraint lines, p. 586-602 | carpet plot, final sizes, trade table | DR-1 refined sizing p. 586-587 |

**Where Raymer does not reach this aircraft, and what is used instead.** Each is written into the
package's assumption ledger with its band, as `data/drone/` already does.

| Gap | Raymer's tool | Why it does not fit | What Stage 1 uses |
|---|---|---|---|
| Empty-weight fraction | Table 3.1, p. 13 (powered sailplane 0.91 W0^-0.05, composite homebuilt 0.99 W0^-0.09, W0 in lb) | fitted to aircraft of hundreds to thousands of pounds | the Task 10 component closure (`data/drone/structure.yaml`) as the primary estimate; Table 3.1 evaluated and reported, flagged as outside its range; a small-UAV mass statistic **[Not lib]** if an open one is found |
| Component weights | ch. 15 equations | same calibration problem, about ten times too heavy for this class | component closure; Raymer's exponents only as trend checks |
| Section data at Re 1e5 to 5e5 | ch. 4 and 12 | high-Reynolds data; Raymer warns about the low-Re regime (p. 45) | the study's SU2 polars with the V6e bias recorded, and the UIUC tunnel data already in `data/validation/` **[Not lib]** |
| Battery, motor, controller | none | not in a 1992 book | ledger values from datasheets, banded **[Not lib]** |
| Propeller at low Re | ch. 13 charts | large metal propellers | Raymer's method with a banded efficiency; UIUC propeller data **[Not lib]** if retrieved |
| Hand launch | catapult (5.10), p. 89 | different mechanism | launch speed against stall with a margin, a stated assumption |
| Gust environment | (14.2)-(14.8), U_de of 30 ft/s | manned-aircraft statistics | Raymer's form with a banded gust velocity, stated |

**Stage 1 output: the conceptual design package**, in `runs/task12/stage1/<date>/` and rendered
to `docs/validation/<date>_task12_conceptual.md` by a script:

1. Requirements compliance matrix: each R-row, the value achieved, the margin, the step that
   produced it.
2. Three-view drawing and internal layout, drawn by code from the sized geometry.
3. Weight statement with centre of gravity, by component.
4. Drag polar, propeller operating points, power and energy budget per mission segment.
5. Constraint diagram (P/W against W/S) and carpet plot, the chosen point marked.
6. V-n diagram with the gust lines.
7. Stability and trim summary.
8. Assumption ledger with sources and bands; list of out-of-calibration correlations.
9. Risk list: each risk with its likelihood, its consequence and how Stage 3 will measure it.
10. Test report: every Raymer equation used, its DR-1 test, pass or fail.

## 5. Code and records (Stage 1)

- New package `conceptual/` (numpy only), one file per Raymer step: `sizing.py` (steps 3 and 8),
  `constraints.py` (step 4), `geometry_sizing.py` (step 5), `layout.py` (step 6),
  `raymer_aero.py`, `raymer_propulsion.py`, `raymer_loads.py`, `raymer_stability.py`,
  `raymer_performance.py` (step 7). Each function's docstring names its equation and page. Unit
  conversions in one place (`conceptual/units.py`), because Raymer works in fps.
- Reuse, do not copy: `drone/naca.py`, `drone/geometry.py` and the ledger loader.
- Tests in `tests/task12/`: one test per DR-1 printed value in the table above, written **before**
  the function is applied to the drone. A DR-1 test that fails stops that step. It is reported, and
  the equation is checked against the page, not adjusted to pass.
- Records: `runs/task12/stage1/<date>/` with inputs, commit, ledger hashes and every output table,
  as every other run in `runs/`.

## 6. Gate A: design review

**Entry criteria.** The package of section 4 is complete. Every DR-1 test passes, or its failure is
explained against the page. The requirements compliance matrix has no blank row.

**Reviewers.**
1. An independent review agent. It is given the package and this spec, not the designer's working
   notes or conclusions, and it checks the items below.
2. Éder, who decides the outcome.

**Checklist** (each item answered yes or no, with evidence, in `docs/reviews/<date>_task12_gateA.md`):

| # | Item |
|---|---|
| A1 | Every requirement traces to a number in the package, with its margin. |
| A2 | The mass closes, with a stated growth allowance. The battery fraction and empty fraction sum below 1 with a stated margin. |
| A3 | The power and energy budget closes for every mission segment, including the reserve. |
| A4 | Static margin is inside R12 at both ends of the centre-of-gravity range. The aircraft trims at the loiter speed and at V_max with elevator authority to spare. |
| A5 | The structure is sized for the larger of the manoeuvre and gust loads. |
| A6 | Every assumption has a source and a band. Correlations used outside their calibration are listed. |
| A7 | Every Raymer equation used has a passing DR-1 test or an explained failure. |
| A8 | The concept choice is justified by its scoring table, and the rejected concepts are kept. |
| A9 | Every risk names how Stage 3 will measure it. |
| A10 | The layout fits: battery and payload inside the fuselage, centre of gravity reachable by moving the battery alone. |

**Outcomes.** Pass: the configuration is frozen. After Gate A only sizes may change, not the
layout type, tail type or planform family (Raymer: preliminary design starts when major changes
stop, p. 4). Pass with actions: the actions are closed in Stage 2 and re-checked by the same
reviewer. Fail: back to Stage 1, with the reasons recorded.

## 7. Stage 3: measure the frozen design with other sources

Principle: **each quantity is measured by a route that does not share the design route's source.**
Before any measurement runs, a tolerance for agreement is fixed in this spec for each quantity. A
disagreement outside it is explained, not averaged away, and it decides whether the design goes
back to Stage 1.

### 7.1 Measurement table

| Quantity | Raymer's estimate (Stage 1) | Independent measurement | Source of the measurement |
|---|---|---|---|
| Lift slope and span efficiency | ch. 12, (12.6)-(12.9), (12.49) | the study's vortex lattice (`drone/vlm.py`, validated by V6a to V6c); Anderson's lifting-line forms | **[Lib]** Anderson APD (2.15), p. 81; (2.18a), p. 86; Examples 2.5 and 2.8, p. 84-89 as tests |
| Zero-lift drag | component build-up, p. 280-290 | Anderson's drag-polar method: skin friction (2.27)/(2.29), drag-due-to-lift split K = k1 + k2 + k3 | **[Lib]** Anderson APD 2.8-2.9, (2.27)-(2.47), p. 107-130 |
| Section polars | ch. 4 and 12 charts | SU2 polars of the chosen section at its Reynolds numbers, with the V6e bias carried | study tools, Task 10 high level |
| Propeller efficiency at loiter, dash and climb | ch. 13, (13.10)-(13.16), Fig. 13.10 | actuator disk with a real-to-ideal factor; blade-element estimate | **[Lib]** Mattingly App. L, (L.7)-(L.9), p. 612; (L.14)-(L.15), p. 615 |
| Speeds for best endurance and best range, power curves | ch. 17 | power required and available curves; closed-form optima | **[Lib]** Anderson APD ch. 5, (5.30)-(5.46), p. 219-222; Example 5.4 as test |
| Climb rate and ceiling | ch. 17, p. 463-467 | Anderson's propeller climb relations | **[Lib]** Anderson APD (5.122), p. 415 |
| Turn performance | ch. 5 and 17 | Anderson's accelerated-flight relations | **[Lib]** Anderson APD (6.33), (6.36), p. 331-332; Examples 6.1-6.2 as tests |
| Constraint diagram | ch. 5 | Mattingly's master equation with lapse and weight fraction set to 1 | **[Lib]** Mattingly (2.11)-(2.17), p. 24-33 |
| Mission energy | step 1 energy budget | Mattingly's segment-by-segment mission analysis, rewritten in energy | **[Lib]** Mattingly ch. 3 (the energy form is the study's adaptation, **[Not lib]**) |
| Static margin and trim | ch. 16 | Anderson's static-stability relations; tail downwash from the vortex lattice | **[Lib]** Anderson APD 8.6.7, (8.76)-(8.78), p. 444 |
| V-n and corner speed | ch. 14 | Anderson's V-n treatment | **[Lib]** Anderson APD (6.54), p. 343; Example 6.3 as test |
| Mass | Stage 1 weight statement | none independent in the library; the component closure is shared | stated as a shared-source quantity; carried with its band |

### 7.2 Uncertainty of the measured performance

- The banded assumptions are propagated through the Stage 3 model, not only swept one at a time.
- **Info-gap robustness** of the frozen design against R3 (mass cap) and R4 (endurance): the largest
  error horizon over the banded quantities at which both still hold. **[Lib]** DMDU ch. 5,
  (5.3)-(5.5), p. 104-105, and ch. 10, (10.4)-(10.8), p. 212-214. The library's tested
  scalar-linear implementation is the starting point; the multi-quantity worst case is new code.
- Robustness curves are drawn for the frozen design and for the Task 10 answer, on the same axes.

### 7.3 Stage 3 output

`docs/validation/<date>_task12_performance.md`: the measurement table with Raymer's value, the
independent value, the difference, the tolerance and the verdict per row; the performance against
each requirement with margins; the robustness curves; and the list of disagreements with their
diagnosis.

### 7.4 Gate B: performance review

The design passes when every requirement is met by the independent measurement with its margin,
every measurement row is inside tolerance or explained, and the robustness horizon at the
requirements is above a value fixed here before Stage 3 runs (to be set with Éder; for example,
the ledger's bands, horizon 1). Otherwise: back to Stage 1, which is Raymer's design wheel
(Fig. 2.1, p. 3), with the measured values in place of the estimates.

### 7.5 Comparison with Task 10

Last, and for information only: the frozen design is evaluated with Task 10's low and high levels,
and placed on Task 10's front. The report states where it sits and why, without changing either.

## 8. Model allocation

Per `CLAUDE.md`. The top model: requirements wording, the electric adaptation, step 2's scoring,
the stability, loads and propulsion physics, every tolerance, both gate reviews, and review of any
diff that can change a number. The implementing model: the `conceptual/` modules and their DR-1
tests from this spec. The documentation model: the three-view drawings, the package rendering,
plots and tables, with review of anything that prints a number.

## 9. Cost (estimates, not measured)

| Stage | Compute | Effort |
|---|---|---|
| 1 | container only, seconds per evaluation | the bulk: about eight modules with their tests |
| Gate A | none | one review pass and Éder's ruling |
| 3 | container for the analytic routes and the vortex lattice; Colab for SU2 polars of the chosen section only (five to ten cases, about 23 minutes each on the medium mesh, per the Task 10 records) | about four modules |
| Gate B | none | one review |

## 10. Decisions for Éder before Stage 1

1. **R4**: the endurance requirement, and whether it is at loiter or includes a cruise-out leg.
2. The other requirements in section 3: accept the defaults or change rows.
3. The third concept for step 2, if any (for example a flying wing, which removes the tail and its
   trim drag but needs reflex and has a small centre-of-gravity range).
4. The Gate B robustness threshold (section 7.4).
5. Whether the empty-weight estimate may use the Task 10 component closure as primary (section 4,
   gap table), or whether an open small-UAV mass statistic must be found first.

## 11. What the library does not cover for this task

Electric propulsion (batteries, motors, controllers, the energy form of the sizing equation);
small-UAV mass statistics; low-Reynolds section data; small-propeller data; hand launch and belly
landing; small-UAV gust environment; a formal design-review procedure. Each appears as **[Not lib]**
above with what is used instead.

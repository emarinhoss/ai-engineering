# Task 12 spec: preliminary design of the W/S 13, A 8 baseline

**Status: spec and plan, 2026-11-27. Nothing in this file was run and no code exists for it yet.**
Gate B passed on 2026-11-27 (ruling B-11, `docs/specs/00_decisions.md` section 9). Spec
`docs/specs/task12_drone_conceptual_design.md` section 2 says a Gate B pass leads to "preliminary design
(lofted 3D geometry, roadmap tracks E and F)". This file says what preliminary design means in this
repository, in what order the work is done, how each piece is accepted, and what ends it (Gate C).

The owner's instruction (Éder, 2026-11-27): "Continue with the design. Make common sense assumptions
and document your choices. Only prompt for my input if absolutely necessary." Section 2 therefore
records each assumption as a numbered decision PD-1, PD-2, ... with its reason. **They stand in for
owner rulings until the owner overrides them**, and Gate C asks him to confirm or change them (C13).

How to read the numbers in this file:

- A number of the aircraft is copied from a committed record and the record is named. The baseline
  record is `runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/` (`design_pusher.json`,
  `ledger.yaml`, `info_gap.json`); the Gate B report is
  `docs/validation/2026-11-27_task12_performance.md` ("the report" below).
- A number marked "arithmetic" is a subtraction, product or ratio of record values done by hand here.
  It is not a result and must not be quoted elsewhere.
- A tolerance or threshold in an acceptance test is a decision of this spec, fixed before any run.
- "Item n" is item n of the report's section 8 (1 to 34). "NR-n" is item n of its section 9 list
  ("Not run on this design", 1 to 23).

Rules of `CLAUDE.md` apply unchanged. Library citations follow
`docs/roadmap/2026-11-20_long_term_roadmap.md` section 0: **[Lib]** is a method or test target from a
library book (Raymer is the **2nd edition, 1992**; Mattingly is *Aircraft Engine Design*, 2nd ed.;
Anderson APD is *Aircraft Performance and Design*); **[Not lib]** is what the library does not provide,
and its open source is opened and recorded before use. Citations were taken from the chapter notes.
Before a printed number becomes a test target the page is opened once (`uv run alex page <slug> <page>`
in the library repository), and the roadmap's Appendix A list of misprints applies.

## 1. What preliminary design is, and what it is here

**[Lib]** Raymer 2.2, p. 4-5 (Fig. 2.2): preliminary design begins when major changes stop. Specialists
in structures, landing gear and controls design and analyse their portions; testing starts in
aerodynamics, propulsion, structures and stability and control; lofting, the mathematical definition of
the outer skin, is a key activity; the configuration is frozen late in the phase, which ends in a
full-scale development proposal. **[Lib]** Anderson APD 7.2.2, p. 383-386, agrees: only minor
configuration changes, serious structural and control analysis, wind-tunnel testing and CFD of the full
configuration, and a frozen, lofted configuration at the end.

Neither book gives a procedure for the phase; both confine themselves to conceptual design (Anderson
APD 7.2.4, p. 386-387). Raymer's later chapters still supply methods one level below the statistics
that Stage 1 used, and those are what this spec draws on:

| Preliminary-design activity (Raymer p. 4-5) | What this repository can do | Where |
|---|---|---|
| Lofting | lofted wing, tails and fuselage with geometry gates | P3 |
| Aerodynamics testing | measured open section data; 2D SU2 polars on Colab; vortex lattice. No tunnel, no 3D CFD (PD-1) | P2, P4 |
| Propulsion testing | blade-element propeller check; engine table extended in altitude. No maker's data (G-6) | P0, P6 |
| Structures | loads from a second source; preliminary sizing of the wing spar only (PD-9) | P5, P7 |
| Stability and control | fuselage-inclusive neutral point, centre-of-gravity envelope; envelope protection stated as a requirement. No control law (PD-11) | P4, P8 |
| Landing gear | fit and ground-angle checks on the loft. No gear design | P3 |
| Mock-up | none. The loft and its renders are the only drawing | P3 |
| Development proposal, cost and schedule | out of scope | - |

So "preliminary design" here is narrower than Raymer's: **it closes the entry items that Gate B
carried, replaces the conceptual body of revolution with a gated loft, and re-checks the baseline with
one more independent source per open quantity.** What it cannot do is listed in section 2 and again at
Gate C, so that the pass is not read as more than it is.

## 2. Scope: decisions PD-1 to PD-17

Each decision is an assumption made under the owner's instruction. "Override" says what changes if he
decides otherwise.

| ID | Decision | Reason | Override |
|---|---|---|---|
| **PD-1** | **No rented compute and no 3D CFD.** Roadmap Track F (F0 to F6) is out of preliminary design. Three-dimensional aerodynamic evidence stays the vortex lattice (the study's own and VSPAERO). Only cheap 2D SU2 section polars are queued for Colab, and no package waits for them. | Roadmap F0: the Colab CPU worker will not carry a RANS wing, and the roadmap puts 3D flow in its horizon 4, after the geometry exists. Colab needs the owner to start the notebook. | Renting a node opens F1 (timing) as a new task after Gate C; nothing here depends on it. |
| **PD-2** | **Rendering with matplotlib only.** No PyVista or VTK. | The repository avoids heavy frameworks; `conceptual/render3d.py` and `conceptual/stl_view.py` already draw flat-shaded triangles. No field data needs drawing while PD-1 holds. Roadmap rendering rules 1, 4 and 5 are applied (sidecar record, made by code, unsolved designs labelled). | A lit render or a flow field needs the optional dependency of roadmap decision 3. |
| **PD-3** | **The configuration stays frozen**: pusher with the sensor in the nose, aft tail, retractable tricycle gear in sponsons, one M250-B17F at 450 shp, W/S 13, A 8, taper 0.45, advanced composite. Only sizes and details may change: the wing's fore-and-aft position, tail area and arm, fuselage lines, section, structure, tank and bay arrangement. | Gate A outcome (spec section 6) and rulings B-2c, B-11. Raymer p. 4: preliminary design starts when major changes stop. | A change of engine, concept, W/S or A is a return to Stage 1, not a preliminary-design change. |
| **PD-4** | **No full study of the W/S 13, A 7 cell now.** It is the named fallback. | It is 3,493 lb in the re-size grid against 3,517 lb (report 1.2), 24 lb lighter (arithmetic), and has no info-gap study (NR-12). The owner chose the cell for its cliff and R7 margin (B-2c), not for weight. A study now would re-open a ruled choice without a new fact. | If P4, P5 or P7 forces a re-size, the full study of W/S 13, A 7 is run with it, because a lower aspect ratio lowers the lift slope and with it the gust load factor (Raymer (14.4), p. 339). |
| **PD-5** | **The wing section is fixed in P2: NACA 4415, unless P2's test rejects it. Tails NACA 0012.** | Stage 1 carries "a 15 % thick cambered section" without a shape; the OpenVSP model and the render already draw the 4415 and 0012 for display. Measured data for NACA four-digit sections at Reynolds numbers of a few million are open **[Not lib]** (candidate: NACA Report 824), which is what item 1 lacks. | A laminar-flow or modern section needs its own open data set and a new P2. |
| **PD-6** | **Order of evidence for section data:** measured open data first; SU2 RANS polars on Colab second, non-blocking, after their own validation row; XFOIL (open, GPL, available to the container as a Debian package) third and optional, labelled as such. No viscous panel code is written here. | A measured polar at the design Reynolds number outranks any computed one for maximum lift (Raymer p. 270: it is the least reliable estimate in conceptual design). A hand-written viscous code would not be explainable line by line. | - |
| **PD-7** | **A preliminary-design baseline record, revision r0, is made first (P0) and every package reads it.** Gate B records are not edited. A package that changes a size produces a finding, not a new aircraft; all findings are applied together in one closing re-record, r1 (P9). | Otherwise packages would measure different aircraft. Ruling B-9c already makes the engine-table extension a re-record. | - |
| **PD-8** | **The gust design rule stays as ruled** (B-4, B-9d: Raymer's 30 ft/s to V_C falling to 15 ft/s at V_D, p. 339). The second source's own gust speeds are reported next to it as a finding, with the weight cost of covering them. | The rule is an owner ruling. The ledger already bands `gust_ude_fps` 30 to 50 ft/s and the info-gap study already pays for 50 ft/s at the worst points (report 5.2). | Adopting a higher gust speed as the rule raises the limit load factor at every speed (Raymer p. 340) and is a re-size. See O-2. |
| **PD-9** | **Structures: the wing spar only.** Caps in bending, web in shear, static, at limit load times 1.5. No fuselage, tail, gear or joint sizing; no torsion box, flutter, divergence, fatigue or finite elements. | The library supports exactly this (section 3, P7). The wing is the heaviest structural component in the record (429.4 lb) and the one the gust margin loads. Flutter and vibration are beyond Raymer (14.4, p. 347). | - |
| **PD-10** | **The blade-element propeller is one representative constant-speed three-blade design** at the record's diameter (6.91 ft) and 2,030 rpm. It checks the real-to-ideal factor f and the App. L efficiencies. It is not a propeller for manufacture and no product is selected. | Items 3, 13, 15 and 16 ask for an independent check of f, not for a propeller. The record fixes no blade count; three is what the OpenVSP model draws. Raymer p. 330: a serious design effort obtains the real propeller's charts, which are not open. | A maker's propeller map replaces the check (O-3). |
| **PD-11** | **Envelope protection is a stated requirement with numbers, not a control law.** No autopilot design, no simulation, no dynamic stability, no lateral-directional analysis. | Rulings B-4 and B-9d ask for a requirement. The requirement table R1 to R19 has no handling or lateral clause. Raymer calls his own stability methods crude (p. 418), and pages 436-437 of his lateral section are missing from the library's scan. | A lateral or dynamic requirement is a new R-row for the owner. |
| **PD-12** | **Payload-bay volume: the 500 lb of R4 is packaged at 30 lb/ft^3**, the low end of Raymer's 30 to 45 lb/ft^3 for avionics (**[Lib]** p. 256), carried as a ledger assumption with that band. That is 16.7 ft^3 (arithmetic). The sensor turret is outside the bay, as drawn. | No row has ever checked the payload-bay volume (item 30) and R4 gives a weight only. The low density asks for the larger bay. | A real payload's dimensions replace the density. |
| **PD-13** | **The lightest weight for loads is the zero-fuel weight with the payload on** (2,418.6 lb in the record). Flight with the payload off is computed in P5 and stated as an operating limit, not sized for. | R4's payload is installed mission equipment. Raymer p. 340: a lighter aircraft sees a larger gust load factor from the same lift increment, so the wing stress does not rise but the rest of the airframe is loaded more. | Sizing for payload-off flight is a re-size. |
| **PD-14** | **Tools: numpy, scipy and matplotlib only for new code.** OpenVSP 3.57.1 and VSPAERO are used as an independent cross-check when their interpreter is available, and never as a dependency: a row that needs them and cannot run is recorded "not run". Units inside the new code are foot-pound-second, as in `conceptual/`. | The OpenVSP interpreter lives in a session scratchpad and does not survive the container. | - |
| **PD-15** | **Tolerances.** Spec 7.1a's tolerances carry over unchanged for the rows they cover. New rows have their tolerance in section 3 of this file. | Fixed before any run, as at Gate A. | - |
| **PD-16** | **Requirements R1 to R19 and the standing rulings are unchanged**: FAR field-length factors are not applied (G-1); the engine's altitude and relight limits stay assumptions (R-f); the engine rows rest on the model (G-6); the evidence classes of B-1 are kept and every new row declares its class. | Preliminary design measures the ruled aircraft against the ruled requirements. | - |
| **PD-17** | **Work continues on branch `claude/dazzling-edison-2q0tb7`**, one commit per package with its record, and model allocation per `CLAUDE.md` (section 3). | As Stages 1 and 3. | - |

**Out of scope, in one place:** 3D CFD; tunnel data; a second route for CD0 (item 14 stays carried under
G-3 and B-5; P3 only checks the areas the build-up uses); the engine closing check (items 10, 11: no
maker's data exists in the sources); FAR field factors (item 12, NR-20); a rubber-engine or tractor
re-design (NR-4: the concept record is regenerated in P1 for the file, the choice is not re-opened);
info-gap studies of other cells (NR-12, PD-4); slipstream, turret and sponsons on the lattice (NR-15,
NR-16 beyond what P4 runs); the flap's own ground effect (NR-17); take-off at another site or
temperature (NR-19, R7 is sea level ISA); detail design.

## 3. Work packages, in order

Rules for every package:

- **Tests first.** Fable 5.1 writes the acceptance tests in `tests/task12_pd/` from this section before
  the module exists. A package may add tests and may not weaken one.
- **A failed acceptance test is reported with its numbers and not tuned.** If it moves a requirement
  margin, it becomes a finding for P9.
- **Every run writes a record** in `runs/task12/pd/<date>/<package>/` with inputs, commit, dirty-tree
  flag with the file list, seed, tool versions and log, and a generated report
  `docs/validation/<date>_task12_pd_<package>.md`. No number is typed into a report by hand.
- **Evidence class** (ruling B-1) is declared per row: independent, partly independent, coding check,
  assumption or layout construction.
- New code goes in `prelim/` (analysis) and `geometry3d/` (loft, gates, export, renders). Each function's
  docstring names its equation and page.

Model allocation, as `CLAUDE.md`: **Fable 5.1** for physics, tolerances, acceptance tests, verdicts and
review of any diff that can change a number; **Sonnet 5.5** for modules and their tests from this spec;
**Haiku 5.5** for data transcription with sources, plots, tables and report rendering, with Fable review
of anything that prints a number.

Order and dependencies:

```
P0 baseline r0 ──► P1 Stage 1 package
              ├──► P2 section ──► P3 loft ──► P4 balance and stability ─┐
              │              └──► P5 loads ──► P7 spar ◄── P3            ├──► P9 closing re-record r1 ──► P10 report, Gate C
              ├──► P6 propeller ──────────────► P8 envelope protection ──┘
              └──► (Colab, non-blocking) SU2 polars of P2
```

P1, P2 and P6 can run side by side after P0. The order below is the order of review.

| # | Package | Closes | Runs in the container now? | Fable 5.1 | Sonnet 5.5 | Haiku 5.5 |
|---|---|---|---|---|---|---|
| P0 | Baseline r0: engine table to 35,000 ft, re-record, record hygiene | items 6, 20, 22, 23, 33; NR-7, NR-8 | yes | tests, verdict on the ceiling row, diff review | table extension, record writer, climb integration | report |
| P1 | Stage 1 package for r0 | items 5, 8 (as a risk), 18, 27, 28, 30 (first check), 31 (stated); NR-1, NR-3, NR-4, NR-21 (first check) | yes | risk list, out-of-calibration list, band audit, review | package script, trades, decomposition run | three-view, plots, tables |
| P2 | Wing section and section data | item 1; NR-5 (polars) | measured data: yes. SU2 polars: Colab, owner starts the notebook, non-blocking | section test, tolerances, verdicts | data loader, C_L,max routes, SU2 case files | transcription of the open data with sources |
| P3 | Lofted geometry and geometry gates | item 30; NR-21; item 5 (three-view from the loft); feeds item 14 | yes (OpenVSP cross-check if its interpreter is available) | gate tolerances, review | `geometry3d/` and its tests | renders with sidecar records |
| P4 | Balance and longitudinal stability: weight and balance, CG envelope, fuselage-inclusive neutral point, R13 | items 4, 25, 31; NR-6, NR-14, NR-15 (in part) | yes (VSPAERO rows if available) | method choice, tolerances, verdict on R13 | modules and tests | envelope plot, tables |
| P5 | Loads: gust second source, negative manoeuvre, V-n diagram | items 2, 26; NR-5 (gust), NR-18 | yes | gust model, tolerances, verdict | modules and tests | V-n figure, tables |
| P6 | Blade-element propeller | items 3, 13, 15, 16, 17; NR-5 (propeller), NR-19 (f for climb alone) | yes | blade physics, validation verdict, review | `prelim/bem.py` and tests | transcription of validation data, plots |
| P7 | Wing spar preliminary sizing | item 8 (wing weight from the bottom up), item 26 (the ultimate cases) | yes | load cases, allowables, verdict | module and tests | loads-on-wing figure, tables |
| P8 | Envelope protection requirement | item 7 | yes | the requirement table and its numbers | the runs behind each number | document |
| P9 | Closing re-record r1 and robustness | items 34 (restated), 28 (bands applied); NR-13 | yes | what goes into r1, verdicts | re-record, info-gap run | report |
| P10 | Preliminary-design report and Gate C | every item's disposition | yes | narrative, Gate C review brief | - | report rendering |

Items with no package: 9, 10, 11, 12, 14, 19, 21, 24 stay carried under their rulings (PD-16); 29 and 32 are
closed (report section 13). Section 5 lists every item with its disposition.

### P0. Baseline r0: engine table to 35,000 ft, the re-record, record hygiene

Reorders the task list's (f) to first place, because ruling B-9c makes the table extension a re-record
and PD-7 needs one record for every later package.

- **Method.** Regenerate the M250 table with the existing cycle model (`measurement/m250_engine.py`,
  **[Lib]** Mattingly App. K, p. 589-608, as validated in `measurement/appk_validation.py`) on an
  altitude grid that keeps every existing row and adds rows to 35,000 ft. Re-run the Stage 1 design of
  W/S 13, A 8 at the record's L_sized with the same ledger and seed. Record the rate of climb against
  altitude from sea level to the ceiling in 1,000 ft steps, and the climb leg integrated over those
  steps next to Stage 1's two-point estimate (item 23; **[Lib]** Raymer ch. 17, p. 463-467; Anderson APD
  (5.122)).
- **Hygiene, no number changes.** The record writer stores the dirty-tree flag with its file list
  (item 33). The propeller fixed point raises if it does not converge (item 22). The closed-form climb
  rows take the class the report gives them (item 20).
- **Acceptance, fixed now.**
  1. Every table cell at or below 30,000 ft equals the cell of the record's `m250_table.json` to 1e-12
     relative. The new rows carry the choked/unchoked flag.
  2. Every field of r0's `design_pusher.json` other than `performance.service_ceiling_ft` equals the
     Gate B record to 1e-9 relative. A field that differs stops the package and is reported.
  3. No table read above the table top remains (the flag of B-9c is stored and is false everywhere).
  4. Service ceiling: Stage 1 on the extended table against the engine-cycle value (30,407 to 30,432 ft,
     report 4.7) inside ±1,000 ft (spec 7.1a). This row was "not judged" at Gate B and is judged here.
     R12 needs 23,000 ft plus the 500 ft margin under either value.
  5. Integrated climb fuel against the two-point estimate: if total mission fuel changes by more than
     1 %, the integrated climb goes into r1 as a finding.
  6. The info-gap study of r0 (seed 20261122) reproduces the Gate B horizons, R5 guarantee 1.0501 and
     R7 1.2845, to 1e-4.
- **Evidence class.** Coding check (same model, extended range). The unchoked-share caveat of item 11
  is restated with r0's share.

### P1. Stage 1 package for r0

- **Method.** The ten outputs of spec section 4 ("Stage 1 output"), generated by script from r0
  (`conceptual/report.py` and `conceptual/stage1.py` exist): compliance matrix, three-view and internal
  layout, weight statement with the CG full and empty and the fit-against-build-up comparison, drag
  polar and propeller points, constraint diagram and carpet plot, V-n diagram, stability and trim
  summary, ledger with the out-of-calibration list, risk list, test report. **[Lib]** Raymer ch. 19,
  p. 519-535 for the trades and the carpet plot; DR-1, p. 559-602 as the template.
- **Added for the Gate B items.**
  - Trades: loiter time against payload, the composite factor across its band, altitude 15,000 to
    25,000 ft (NR-3). The carpet plot uses the committed re-size grid
    (`runs/task12/stage3/2026-11-26/m250_bands_resize/curve.json`); no new sizing.
  - The App. L decomposition on r0 with `measurement/appl_decomposition.py` (NR-1), and from it the
    climb speed at the worst endurance corner against the 20,000 ft stall (item 18).
  - The concept record at these sizes: the tractor and the rubber-engine designs at W/S 13, A 8 with the
    same ledger, and the scoring table (NR-4, Gate A item A9). The choice is not re-opened (PD-3); if
    the scoring reverses, that is reported to the owner.
  - Empty weight: the difference between the build-up (0.5455), the Table 3.1 fit (0.5156) and Table
    15.2 (0.6220) explained component by component (items 8, 27; record `empty_fraction_comparison`).
  - Band audit: each of the 58 ledger entries without a band (item 28) is classed as requirement,
    definition, or "needs a band". A proposed band is listed for Gate C and not applied silently.
  - Risk list: every risk names the package of this spec that measures it (Gate A item A11).
  - Payload bay, first check: the PD-12 volume against the free fuselage volume of the Stage 1 body of
    revolution (**[Lib]** Raymer (7.13), p. 153). P3 repeats it on the loft.
- **Acceptance.** Every number in the package is read from r0 by the script (a test compares sampled
  fields with the record). The compliance matrix has no blank row. The weight statement sums to the
  record's empty weight within 0.1 lb. The V-n diagram's points equal r0's `vn` entries to 1e-6. The
  out-of-calibration list and the risk list are not empty by construction: a test fails if a
  correlation flagged in the 2026-11-25 package is missing without a stated reason.
- **Evidence class.** A package, not a measurement. It closes B-9a's entry item.

### P2. Wing section and section data

Moved ahead of the loft because the loft, the negative manoeuvre and the spar depth all need the
section.

- **Method.**
  1. Design Reynolds and Mach numbers at root, mean and tip chord for stall at sea level, loiter and
     cruise at 20,000 ft, computed from r0.
  2. Measured section data for the NACA 4415 and 0012 from an open report **[Not lib]** (candidate:
     NACA Report 824, opened and recorded before use): lift curve, positive and negative maximum lift,
     zero-lift angle, moment about the quarter chord, minimum drag, smooth and with standard roughness,
     at the tabulated Reynolds numbers that bracket step 1. Transcribed to `data/task12/` with page,
     figure and reading uncertainty; every transcribed point is read twice.
  3. Wing maximum lift from the section value: **[Lib]** Raymer (12.15), p. 270, and (12.16) with
     Fig. 12.8, p. 271-272. Flapped increments by (12.21) and Table 12.2, p. 279, as Stage 1.
  4. Queued for Colab, non-blocking: SU2 RANS polars of the same section at the same Reynolds numbers
     (spec 7.1), after a validation row against step 2.
- **Acceptance.**
  1. Section maximum lift at the Reynolds number nearest stall, smooth: inside the ledger band 1.3 to
     1.7 (spec 7.1a). Outside rejects the section (PD-5) and is reported.
  2. Wing C_L,max clean from step 3 against the record's 1.35: if the measured route is lower, the
     lower value goes to r1 as a finding, with R17's 1.3 V_stall legs re-flown. For orientation only:
     the 70 kt clause of R7 holds down to a clean C_L,max of 0.78 (arithmetic: 1.35 times the square of
     53.33/70, record values), so the stall clause is not what a lower value threatens; R17 and the
     loiter speed are.
  3. Section moment against the ledger's `airfoil_cm0` band (-0.10 to -0.04): outside is a finding for
     P4's trim check.
  4. The roughness values are reported as a sensitivity with no verdict.
  5. SU2 validation row, when it runs: lift-curve slope within ±5 %, lift at zero angle within ±0.05,
     maximum lift within ±0.10 of the measured smooth value. Drag is reported without a verdict (a
     fully turbulent solution against a tunnel with natural transition). A failed row is reported and
     the SU2 polars are then not used.
- **What can be done without SU2.** Everything except step 4. Item 1 asks for "SU2 section polars and
  C_L,max"; this package answers the C_L,max part from measurement, which is the stronger source
  (PD-6), and leaves the SU2 polars as a labelled open row if the notebook is not started.
- **Evidence class.** Independent (measured data from outside the library and outside Stage 1).

### P3. Lofted geometry and geometry gates

Roadmap Track E, items E1 to E5, adapted from the Task 10 drone to this aircraft. E6 is reduced to
matplotlib renders (PD-2). E7, E9 and E10 are not used (no front to browse, no flow field).

- **Method** (`geometry3d/`, numpy only).
  - **E1, wing and tails.** P2's sections placed along the span of r0's planform, linear between
    sections at constant percent chord, closed tips, a structured quad surface and its triangulation.
    **[Lib]** Raymer 7.8, p. 142-147; reference wing (7.5)-(7.9), p. 139-140.
  - **E2, fuselage.** Control stations, each a conic, joined by smooth longitudinal lines; the body of
    revolution of Stage 1 is the starting shape, with the nose, payload bay, engine bay and pusher
    closure given real cross-sections. **[Lib]** Raymer 7.3-7.4, p. 123-134, (7.1)-(7.4). Sponsons,
    turret and spinner as simple bodies. No wing-body fairing.
  - **E4, internal arrangement.** Boxes for the engine (the TCDS envelope in the record's
    `engine_source`), payload bay (PD-12), avionics, nose gear bay, retracted main gear, and the wing
    tanks between the ledger's spar fractions (`wing_tank_chord_fraction`, `wing_tank_span_fraction`).
  - **E5, export.** A triangle surface (STL) written by the package's own writer.
- **Geometry gates (E3), each refusing with the offending value.**
  1. Each component is watertight: every edge is shared by exactly two triangles, normals outward.
  2. Printed targets: a conic with shape parameter 0.4142 and equal tangents is a circular arc, 0.5 a
     parabola (**[Lib]** Raymer (7.4), p. 132). Mean chord and its span station equal r0's `wing.mac`
     and `wing.mac_y` to 1e-9.
  3. **Wetted area against the drag build-up.** Per component, the loft's wetted area against the area
     Stage 1's build-up uses, within ±5 %; and against Raymer's forms ((7.10)-(7.12), p. 150-152) as a
     second reading. Outside: the build-up is re-run with the loft's areas, the change in CD0 and in
     hours on station is reported, and the loft's areas go into r1. (For scale: OpenVSP's fuselage area
     is 267.08 ft^2 against Stage 1's 277.78 ft^2, `runs/task12/openvsp/2026-11-27_m250_ws13a8/model.json`;
     -3.9 %, arithmetic.)
  4. **Volumes.** Tank volume from the loft times the ledger's usable fraction at least the fuel volume
     needed (21.92 ft^3 in the record, which also claims 73.17 ft^3 available; the loft checks that
     claim). Fuselage volume by integrating section area over length (**[Lib]** Raymer 7.11,
     p. 152-153). Every box inside the skin with the ledger's clearance, and no two boxes overlapping.
     The payload bay holds the PD-12 volume. This is the first payload-bay row the task has had.
  5. Smoothness: section perimeter and area against station have no kink (a bound on the second
     difference, fixed in the test). Aft-body angle reported against **[Lib]** Raymer 8.2, p. 155-156
     (10 to 12 deg without a propeller behind; more is tolerated ahead of a pusher propeller).
  6. Ground angles on the loft: propeller clearance at rotation (14.44 in in the record), tipback and
     overturn angles (**[Lib]** Raymer 11.2, Fig. 11.4, p. 232).
  7. Export round trip: area and volume of the re-read file equal to 1e-9.
  8. Cross-check, if the OpenVSP interpreter is available (PD-14): the loft's wetted areas against
     OpenVSP's CompGeom on the same parameters, within ±2 %. Otherwise "not run".
- **Renders.** Three orthographic views and one perspective view, with a sidecar record each, labelled
  "geometry only, no flow solution". The three-view of P1 is redrawn from the loft.
- **Evidence class.** Geometry is construction. The area and volume rows are independent of Stage 1's
  formulas in the sense that they integrate a surface instead of using a factor.

### P4. Balance and longitudinal stability

Merges the task list's (c) and (j). The aft limit of the CG envelope is the neutral point less the R13
floor, and R13 is a statement about both, so neither can be accepted alone.

- **Method.**
  1. **Weight and balance.** The group weight statement of r0 with each item at its station in the P3
     arrangement (**[Lib]** Raymer 15.1, Table 15.1 and Fig. 15.1, p. 395-398; Anderson APD 8.6.4,
     p. 433-435). CG against weight for: fuel from full to empty in steps, with the tanks emptied in a
     stated order; payload on and off; gear up and down. The same at both ends of the empty-weight band
     with the extra weight placed in proportion to the component weights (NR-14).
  2. **Fuselage-inclusive neutral point, independent of Stage 1's (16.22).** Stage 1 uses Raymer's
     single-factor fuselage term ((16.22) with Fig. 16.14, p. 427). The independent route integrates
     the fuselage's moment slope strip by strip over the loft's width distribution with the wing's
     upwash and downwash field **[Not lib]** (candidate: Multhopp's method, NACA TM 1036, opened and
     recorded before use), and adds the pusher propeller's normal-force term, which Stage 1 leaves out
     (**[Lib]** Raymer (16.26) with Figs. 16.15-16.16, p. 427-430; (16.8)-(16.9), p. 417, with the
     misprint of (16.9) noted in the roadmap's Appendix A). Reported power off and power on.
  3. **Lattice support.** VSPAERO with the lofted fuselage as a body and a mesh one level finer than L2
     (NR-6, NR-15), if its interpreter is available. The 2026-11-24 fuselage-plate run was not
     mesh-robust; a run whose neutral point moves by more than 0.01 MAC between its two finest meshes is
     reported as not converged and gives no verdict.
  4. **Trim and rotation** re-checked at the CG ends with P2's section moment (item 25: the tail's lift
     coefficient at rotation is 0.968 of 1.00 in the report).
- **Acceptance.**
  1. Static margin at the full-fuel and empty-fuel CG, with the independent neutral point, power off:
     inside R13's 0.05 to 0.15 MAC. Power on is reported next to it.
  2. Independent neutral point against Stage 1's: within ±0.03 MAC (spec 7.1a). Outside is diagnosed.
  3. CG envelope: every loading of step 1 lies between the forward limit (trim and rotation with the
     ledger's tail lift limits) and the aft limit (independent neutral point less 0.05 MAC).
  4. Nose-wheel load at every loading inside 5 to 20 %; the 8 to 15 % optimum is reported (item 31).
  5. If 1, 3 or 4 fails, the wing's fore-and-aft position that restores them is computed (a size
     change, PD-3) and goes to r1 with the re-run of this package. It is not applied inside P4.
- **Evidence class.** Step 2 is independent of Stage 1 in the fuselage term and partly independent
  overall (same wing and tail lift slopes and lattice downwash, spec 7.1c item 3). This is stated with
  the verdict. Step 3 is support, as under G-8.

### P5. Loads: gust second source, negative manoeuvre, V-n diagram

- **Method.**
  1. **Second source for the gust formula and speeds** **[Not lib]**: the airworthiness rule that
     Raymer's method summarises (candidate: 14 CFR Part 23, the gust-envelope and gust-load-factor
     paragraphs at a stated amendment, opened and recorded before use). The library has no second
     gust method: Anderson APD 6.5, p. 341-344, gives the manoeuvre diagram only.
  2. **An independent alleviation factor.** The rule's formula has the same form as Raymer's
     (14.5)-(14.8), p. 339, so agreement of the two formulas shows little. The independent check
     integrates the aircraft's plunge response through a one-minus-cosine gust in time, with unsteady
     lift build-up, and reads the alleviation factor from the peak acceleration **[Not lib]**
     (candidate: NACA Report 1206, the origin of the factor, opened and recorded before use). Raymer
     p. 338-339 describes the physics in words: a gust that builds up like a cosine cuts the
     acceleration by up to 40 %.
  3. **Negative manoeuvre.** The negative stall line from P2's negative maximum lift through (12.15),
     and the negative structural limit -1.8, drawn as **[Lib]** Raymer Fig. 14.3, p. 337, and Anderson
     APD Fig. 6.7, p. 341-344 (corner speed (6.54), Example 6.3 as the printed test, 492.4 ft/s).
  4. **V-n diagram** at sea level and 20,000 ft, at take-off, zero-fuel and payload-off weight, manoeuvre
     and gust combined (**[Lib]** Raymer Figs. 14.7-14.8, p. 341), at V_C, V_D and the level top speed.
- **Acceptance.**
  1. Gust load factors by the second source's formula at Raymer's gust speeds against r0's `gusts`:
     within ±5 % (spec 7.1a).
  2. Alleviation factor from the time integration against (14.6) at the record's four mass ratios:
     within ±5 %. Outside is reported, with the load factors by both.
  3. Under the ruled rule (PD-8) at take-off and zero-fuel weight: every point at or below 3.8 and at
     or above -1.7. This repeats the Gate B check on r0 with the negative manoeuvre added.
  4. Under the second source's own gust speeds, and with the gust held at 30 ft/s above V_C: load
     factors reported against limit and ultimate, positive and negative, and the structure weight that
     would cover them taken from a Stage 1 run with the limit raised. No verdict; a finding for O-2.
  5. Payload-off weight (NR-18): reported, and the speed and altitude at which it stays inside the
     limits stated as the operating limit of PD-13. From Raymer (14.4) the gust increment grows as the
     weight falls, so this case is expected to be the worst one; that expectation is not a result.
- **Evidence class.** Row 1 partly independent (same physics, second text). Row 2 independent.

### P6. Blade-element propeller

- **Method.**
  1. **Blade.** Three blades, the record's diameter and 2,030 rpm, constant speed (pitch set per flight
     condition). Chord distribution from an activity factor in Raymer's range and a design lift
     coefficient of about 0.5 (**[Lib]** Raymer p. 325-327, (13.14)); twist set so that each station
     works at the design lift coefficient at the loiter point. Section lift and drag from P2's kind of
     source for a thin propeller section **[Not lib]**. These choices are ledger entries with bands.
  2. **Strip theory.** Element thrust, torque and efficiency by **[Lib]** Mattingly App. L,
     (L.10)-(L.15), p. 613-616, with the relative Mach number (L.16) reported along the blade. The
     induction factors come from a momentum balance on each annulus with a tip-loss factor **[Not lib]**
     (Mattingly's Ref. 1, Glauert, names the theory; an open statement of it is recorded before use).
     Solved by bracketing with scipy; a station that does not converge raises.
  3. **Operating points.** The record's `propeller_points` (climb at sea level, cruise out, loiter,
     cruise back) and the take-off speeds of the f sweep.
- **Validation before use on the aircraft, with printed targets from the library.**
  1. With zero drag angle, zero rotational interference and the axial interference of the disk
     ((L.5), p. 611), the element efficiency equals the ideal efficiency of (L.7) (stated on
     p. 613-616). Test to 1e-12.
  2. The maximum of the element efficiency over the inflow angle is at 45 deg less half the drag angle
     and equals (L.15). Fig. L.5, p. 616, gives the shape for an interference ratio of 0.8 and
     lift-to-drag ratios of 50 and 10; the test evaluates (L.14) and (L.15) and compares the plateau
     with the figure reading within the reading's uncertainty.
  3. Coefficient definitions: (L.18) and (L.20) reproduce the J and C_P of Table L.1, p. 619, from its
     flight conditions with D = 14 ft and N = 663.4 rpm. The table's row D is flagged in the notes as
     a possible misprint and is not used.
  4. Static-thrust correlation: (L.19) reproduces the two printed diameters of the example on p. 617,
     15.0 ft and 10.6 ft.
  5. A measured full propeller **[Not lib]** (candidate: an open NACA full-scale propeller report,
     recorded before use): efficiency against advance ratio at two blade angles within ±0.03 absolute
     over the range where the measured efficiency is above 0.5. This is the hard row. If it fails, the
     package's numbers are reported as failed-validation numbers and are not used in r1.
- **Acceptance on the aircraft.**
  1. Efficiency at climb, cruise and loiter against r0's App. L values (0.7041, 0.8073 and 0.7733 in
     the report's section 10): within ±0.05 absolute (spec 7.1a).
  2. The implied factor f (blade-element efficiency over the ideal efficiency of the same disk) at each
     point: inside the ledger band 0.80 to 0.90. Outside, at any point, is a finding: the band is
     re-proposed per flight condition (item 16) and the info-gap study of P9 runs with it.
  3. Take-off: thrust at 0.707 V_TO at or above the f = 0.60 row of the recorded sweep (1,247 lb), the
     lowest f at which R7 was shown to hold. Static thrust is also compared with (L.19) and with
     Raymer Fig. 13.8, p. 328 (a three-blade, activity factor 100 chart; a class check, not a
     validation). Strip theory near zero speed is weak and this row says so.
  4. Reported without a verdict: tip relative Mach number at each point (item 15), and the sensitivity
     to the blade choices of step 1.
- **Not covered, and carried.** Hub, spinner and pusher-fuselage blockage, and the wake of the wing and
  tail entering the disk (item 15). Mattingly p. 619-620 names the pusher's cyclic loads; they are a
  structural matter for the propeller maker.
- **Evidence class.** Independent of App. L's disk in the profile losses; it shares the momentum theory.

### P7. Wing spar preliminary sizing

The library supports it: Raymer chapter 14 gives the load distribution, the beam method, the spar
idealisation and typical material properties.

- **Method.**
  1. **Spanwise airload** by Schrenk's approximation (**[Lib]** Raymer (14.9)-(14.11), p. 342-343),
     scaled to the wing lift that the load factor needs after the tail's trim load, and checked against
     the vortex lattice's span loading of the same wing.
  2. **Inertia relief.** Wing weight spread in proportion to chord (Raymer p. 382), fuel in the P3
     tanks, sponsons and main gear as point weights, each times the load factor.
  3. **Shear and bending moment** by Raymer's station method: about twenty spanwise stations, the
     trapezoid rule of Fig. 14.39, shear summed from the tip inward, moment as the area under the shear
     curve (**[Lib]** p. 381-383).
  4. **Sizing.** Caps carry all the bending, the web all the shear at a uniform stress (**[Lib]**
     p. 384-385, Fig. 14.41). Cap area from (14.35) with the spar depth taken from the loft at the
     spar's chord station; web thickness from the shear stress and from shear buckling (14.37) with
     Fig. 14.42. Material: high-strength graphite/epoxy, 0 deg for the caps and ±45 deg for the web,
     typical values of **[Lib]** Raymer Table 14.4, p. 368-369, with a knock-down factor in the ledger
     as a banded judgement **[Not lib]** (Raymer p. 368 calls the table typical values only).
  5. **Load cases.** Limit times 1.5: +3.8 at take-off weight and at zero-fuel weight; the worst gust of
     P5 under the ruled rule; -1.8; and, as a sensitivity, the P5 row 4 cases.
- **Acceptance.**
  1. Coding checks before use: the airload integrates to the required lift to 1e-9; shear and moment of
     a uniformly loaded cantilever and of an elliptic loading equal their closed forms to 1e-6.
  2. Schrenk's root bending moment against the lattice's: within ±5 %. Outside is reported and the
     larger is used.
  3. A positive margin at ultimate load in caps and web at every station for every case of step 5
     other than the sensitivity.
  4. The caps fit inside the section at every station with the skin thickness assumed.
  5. Spar weight reported as a share of r0's wing weight (429.4 lb). No tolerance is set, because the
     library gives no spar share; a spar heavier than the whole statistical wing is a failure of the
     wing weight estimate and a finding for item 8.
- **Figure.** Span loading, shear and bending moment drawn on the wing (roadmap E8), values equal to the
  record.
- **Evidence class.** Independent of the statistical wing weight. A preliminary sizing, not a stress
  report.

### P8. Envelope protection as a stated requirement

Rulings B-4 and B-9d: R18 holds only if the autopilot holds the aircraft at or below V_C, in level
flight at every altitude, and a gust criterion above V_C is set. This package writes the requirement,
`docs/specs/task12_envelope_protection.md`, with one table. Each row has a number and the record it
comes from.

| Row | Requirement to be stated | Number comes from |
|---|---|---|
| EP-1 | Speed hold: at or below V_C 110 kt EAS at every altitude and weight, climb, level and descent | R18; r0 |
| EP-2 | Power limit schedule: the largest shaft power against altitude at which level flight stays at V_C, and the excess the engine has above it (level top speed is 185.2 kt EAS at sea level and 120.9 kt EAS at 20,000 ft in the record) | a recorded run on r0's polar and P0's table, with P6's thrust as a second reading |
| EP-3 | Overspeed margin: the speed excursion above V_C the protection may allow, set so that the P5 load factors stay inside the limits with the gust speed of the ruled rule at that speed | P5 |
| EP-4 | Dive margin: height lost and time from V_C to V_D at idle and at full power, for stated descent angles (Raymer p. 338: V_D is 50 % above cruise) | a recorded point-mass run |
| EP-5 | Load-factor command limits inside +3.8 and -1.8 with stated margins; the turn of R16 (n = 1.155) stays available | R9, R16 |
| EP-6 | Low-speed protection: no commanded speed below 1.3 V_stall clean at the current weight (R17), with P2's C_L,max | R17; P2 |
| EP-7 | Gust criterion above V_C: the gust speed applied between V_C and V_D, and what the structure is cleared to at V_D | PD-8; P5 |
| EP-8 | Altitude limits: the 23,000 ft ceiling requirement, and the engine's operating and relight altitude as declared assumptions (R-f) | R12; R-f |
| EP-9 | Payload-off operating limit (PD-13) | P5 row 5 |

- **Acceptance.** No row is blank; every number is read from a record by the generating script; EP-3
  and EP-7 are consistent with P5 (a test recomputes the load factor at V_C plus the allowed
  excursion). The document says in its first lines that it is a requirement on a system that this
  repository does not design (PD-11).
- **Evidence class.** A requirement, not a verification.

### P9. Closing re-record r1 and robustness

- **Method.** Every finding of P0 to P8 that changes an input of the design is listed with its record.
  They are applied together in one Stage 1 re-record, r1, at W/S 13, A 8: the loft's wetted areas, the
  measured C_L,max and section moment, the wing position, the integrated climb, any band changed by P6
  or by the band audit that the owner has accepted. Then the checks that made Gate B are repeated on
  r1: the compliance table, the Gate A re-check, the V-n check, the Stage 3 rows and the full info-gap
  study (**[Lib]** DMDU ch. 5, (5.3)-(5.5), p. 104-105), with the sub-step doubling check on this cell
  (NR-13). P3 to P7 are re-run on r1 only where r1 changed their inputs; each such re-run is listed.
- **Acceptance.**
  1. The Gate B threshold again: R5 guarantee horizon and R7 horizon each at least 1 on r1 (spec 7.4).
  2. No compliance row fails.
  3. The difference r1 minus r0 is tabulated field by field with the finding that caused it.
  4. Step doubling changes W0 by less than 0.5 %.
- **If 1 or 2 fails.** The design returns to Stage 1 with the measured values in place of the estimates
  (**[Lib]** Raymer's design wheel, Fig. 2.1, p. 3). The re-size runs the grid again with the full study
  of W/S 13, A 7 (PD-4), and the owner chooses the cell as at B-2c. This is the one foreseeable point at
  which the owner must be asked.
- **If nothing changed.** r1 is r0 and the package records that.

### P10. Preliminary-design report and Gate C

`docs/validation/<date>_task12_preliminary_design.md`, generated from the records: the aircraft of r1
with its loft and renders; one section per package with its acceptance rows and verdicts; the
disposition of every item 1 to 34 and NR-1 to NR-23; the PD decisions with what each one cost in
evidence; what is still not known. The report does not decide Gate C.

## 4. Gate C: preliminary design review

In the style of Gates A and B (spec sections 6 and 7.4).

**Entry criteria.** P0 to P9 each have a record and a generated report. Every acceptance row has a
verdict: pass, fail with its numbers, or not run with its reason. A recorded pytest report exists at the
gate commit.

**Reviewers.** An independent review agent, given the report, this spec and the records, and not the
working notes. Éder decides the outcome.

**Checklist** (each answered yes or no with evidence, in `docs/reviews/<date>_task12_gateC.md`):

| # | Item |
|---|---|
| C1 | Every requirement R1 to R19 traces to a number in r1 with its margin and its evidence class. |
| C2 | The loft is watertight and passes its gates. The wetted areas agree with the drag build-up within tolerance, or the build-up was re-run with the loft's areas. The tanks hold the fuel, the bay holds the payload volume of PD-12, the engine and the retracted gear fit. |
| C3 | The CG stays inside its envelope for every loading. R13 holds with a fuselage-inclusive neutral point from a route independent of (16.22), or the wing was moved and the check repeated. |
| C4 | The V-n diagram includes the negative manoeuvre and a gust check by a second source. Under the ruled rule no point passes a limit. The second source's own gust speeds are reported with their weight cost. |
| C5 | The wing spar has a positive margin at ultimate load in every ruled case and fits the section. |
| C6 | The blade-element propeller passed its validation rows before it was used. The efficiencies agree within tolerance and the implied f is inside its band, or the band was changed and the robustness re-run. |
| C7 | The section is fixed, its maximum lift comes from measured data inside the ledger band, and the wing C_L,max in r1 is not above what that data supports. |
| C8 | The engine table reaches 35,000 ft, no value is read above the table top, and the ceiling row has a verdict. |
| C9 | The envelope-protection requirement has a number in every row, each from a record. |
| C10 | Robustness on r1: R5 guarantee horizon and R7 horizon each at least 1, with every band changed in preliminary design acting. |
| C11 | Every item 1 to 34 and NR-1 to NR-23 has a disposition: closed with its record, carried under a named ruling, or out of scope under a named PD decision. |
| C12 | Every method added has a passing printed-value or closed-form test, or an explained failure. Every **[Not lib]** source is open, cited and recorded. |
| C13 | Decisions PD-1 to PD-17 are confirmed or changed by Éder, and the owner items of section 6 are answered. |
| C14 | Every record carries its inputs, commit, dirty-tree flag, seed, versions and log. |

**Pass criterion.** Gate C passes when every requirement is met on r1 with its margin, every acceptance
row of P0 to P9 is inside its tolerance or explained and carried by a ruling, the robustness horizons at
R5 and R7 are at least 1 on r1, and the loft is the single source of the areas and volumes the analysis
uses.

**Outcomes.** Pass: r1 with its loft is the design of record, and the report states what it is not (no
3D flow solution, no structure beyond the spar, no control law, no maker's engine or propeller data).
What follows is the owner's choice: roadmap Track F from F1 if compute is found, or stop. Pass with
actions: closed and re-checked by the same reviewer. Fail: back to Stage 1 with the measured values, as
in P9.

## 5. Where each carried item goes

| Item | Disposition |
|---|---|
| 1 SU2 polars and C_L,max | P2: C_L,max from measured data; SU2 polars queued, non-blocking |
| 2 gust second source | P5 |
| 3 blade-element propeller | P6 |
| 4 fuselage-inclusive neutral point | P4 |
| 5 Stage 1 package | P1; three-view redrawn from the loft in P3 |
| 6 engine table to 35,000 ft | P0 |
| 7 envelope protection | P8 |
| 8 empty-weight gap | P1 explains it; P7 sizes the spar from the bottom up; it stays a named risk (B-9g) |
| 9 engine altitude and relight | carried (R-f); restated in P8 row EP-8 |
| 10, 11 engine closing check, unchoked share | carried (G-6, B-5); P0 restates the share on r0; O-3 |
| 12 FAR field factors | carried (G-1) |
| 13 f at low speed | P6 take-off row |
| 14 CD0 second route | carried (G-3, B-5); P3 checks the areas only |
| 15, 16, 17 disk model limits | P6; blockage and wake carried |
| 19 Anderson's 0.62 route holds the disk efficiencies | carried as stated in the report; not re-run |
| 18 climb speed at the worst corner | P1 (decomposition on r0) |
| 20, 22, 33 labels, convergence flag, record hygiene | P0 |
| 21 span efficiency not comparable | carried as stated in the report |
| 23 two-point climb | P0 |
| 24 coding checks are not verifications | carried (B-1); every new row declares its class |
| 25 rotation margin | P4 |
| 26 gust sensitivity, negative manoeuvre | P5, P7 |
| 27, 28 fit against build-up, bands | P1; accepted bands act in P9 |
| 29, 32 | closed (report section 13) |
| 30 payload-bay volume | P1 first check, P3 on the loft |
| 31 nose-wheel load | P4 |
| 34 info-gap exclusions | restated on r1 in P9; R13 at the band ends moves to P4 |
| NR-1, NR-3, NR-4 | P1 |
| NR-2, NR-22, NR-23 | closed (report section 13) |
| NR-5 | P2, P5, P6 |
| NR-6, NR-14, NR-15 | P4 (lattice rows only if VSPAERO is available) |
| NR-7, NR-8 | P0 |
| NR-9, NR-10, NR-11 | not planned: covered by the ±10 % SFC band (B-5); no maker's data (G-6) |
| NR-12 | PD-4 |
| NR-13 | P9 |
| NR-16, NR-17, NR-19 (site, temperature), NR-20 | out of scope (section 2) |
| NR-18 | P5 |
| NR-21 | P1, P3 |

## 6. Owner decisions

**None blocks the work.** Every choice above has a default, and Gate C asks for the PD list as a whole
(C13). Three things only the owner can supply or decide, each with the default the work proceeds on:

| ID | What | Default |
|---|---|---|
| O-1 | Start the Colab notebook so the queued 2D SU2 polars of P2 run. | Not started: P2 closes on measured data, and the SU2 row is recorded "not run". |
| O-2 | If P5 shows that the second source's gust speeds pass the limit load factor: keep the ruled rule (B-9d) or adopt the higher speeds and re-size. | Keep the ruled rule (PD-8); the finding and its weight cost are reported at Gate C. |
| O-3 | A maker's part-power engine curve or a propeller map, if he has one that may be used in a public repository. | None: items 10 and 11 stay carried, and P6 stands as the propeller check. |

The one point at which the owner will be asked before Gate C is a failure of P9 (robustness below 1 or
a failed compliance row on r1), because the answer is a new cell, as at B-2c.

## 7. Cost (estimates, not measured)

| Package | Compute | Effort |
|---|---|---|
| P0 | container; the info-gap study is the long run, as in the cells study | small |
| P1 | container, seconds per evaluation | medium: mostly existing scripts on r0 |
| P2 | container; Colab for about 15 to 20 SU2 cases if started (spec section 9) | small, plus careful transcription |
| P3 | container | the largest: a new package with its gates |
| P4, P5, P6, P7 | container | one module each with its tests |
| P8 | container | small |
| P9 | container; one full info-gap study | small, unless a finding forces a re-size |
| P10, Gate C | none | one report, one review |

## 8. What the library does not cover for this task

Marked **[Not lib]** above; each source is opened and recorded before use, and none is quoted from
memory in this file beyond its name as a candidate.

- Measured section data at the design Reynolds number (P2).
- A fuselage moment method other than Raymer's single factor (P4).
- A second gust method and the derivation of the alleviation factor (P5).
- The annulus momentum balance and tip-loss factor of blade-element theory, propeller section data,
  and a measured full propeller (P6).
- Composite design allowables and knock-down factors (P7).
- A procedure for preliminary design or for its review; an unmanned-aircraft envelope-protection
  standard (P8, Gate C).

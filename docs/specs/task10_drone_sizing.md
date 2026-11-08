# Task 10 spec: sizing a small electric fixed-wing drone with the inlet pipeline (2026-11-08)

Requested by Éder on 2026-11-08 after reading `emarinhoss/tanker_comparison`: can the inlet study's
loop (validated simulator, gates before the solver, queue, GP surrogate, acquisition, Pareto front,
inverse query, confirmation, thin agent layer) be applied to sizing a new aircraft or drone, as an
alternative presentation? This spec fixes the study before any code. What is reused from the tanker
repository is its discipline (one ledger of quantities with sources, bands recorded rather than
narrowed, gates that fail loudly) and nothing of its code or its Z4 reconstruction: that comparison
has a failing anchor (gate G1) and a contested geometry, and its tool chain runs only on macOS.

Rules of `CLAUDE.md` apply unchanged: open data only, every number from a recorded run, validation
before any ML, a failed validation is reported and not tuned away, the language model never chooses a
sampling point, inputs are gated before submission, every run is reproducible.

## 1. Questions

1. For a fixed 0.5 kg payload, what is the Pareto front of endurance against take-off mass over the
   design box, and which design variables drive it? (Reported with the GP's uncertainty band and the
   model's named biases.)
2. Does active learning (EHVI) beat Latin hypercube and random sampling in six dimensions, measured
   two ways: by the pool replay of Task 4, and, new, against the exact front of the low-fidelity model
   over the whole box, which this study can compute because the low level costs under a second?
3. Does the two-level model (low-fidelity section data, then SU2 airfoil polars) reach a given
   held-out error with fewer SU2 polars than SU2 alone? (Task 9's question 2, on a new problem.)
4. Which design gives the longest endurance with take-off mass at most 4.0 kg, the EASA open-category
   class C2 limit, with P(mass <= cap) >= 0.9, and does one SU2 polar at that design confirm it?

Every answer is reported whichever way it goes, including a null result on question 2 or 3.

## 2. Inputs (all six are surrogate inputs; family `drone`)

| Input | Range | Notes |
|---|---|---|
| span_m | 1.2 to 3.0 | wing span b |
| aspect_ratio | 6 to 16 | AR = b^2 / S; sets the wing area |
| taper_ratio | 0.3 to 1.0 | tip chord over root chord, straight taper, no sweep |
| battery_fraction | 0.20 to 0.45 | battery mass over take-off mass |
| camber_pct | 0 to 6 | NACA four-digit maximum camber, percent of chord; camber position fixed at 40 % |
| thickness_pct | 8 to 15 | NACA four-digit maximum thickness, percent of chord |

Fixed, not inputs (recorded in `data/drone/` with a source for each, before any run): payload mass
0.5 kg; sea-level ISA air (rho 1.225 kg/m^3, mu 1.789e-5 Pa s); battery pack specific energy
(assumed, banded; sourced to a cell datasheet and a pack-factor source), volumetric energy density,
usable depth of discharge 0.8; propulsive efficiency motor-to-air 0.60 (assumed, banded 0.50 to
0.70); motor-plus-ESC-plus-propeller specific power (assumed, banded); wing skin areal density and
spar allowable stress (assumed, banded); limit load factor 3.8 with a factor of safety 1.5; tail
volume coefficients V_H = 0.50 and V_V = 0.04 with the tail arm 2.5 mean chords; fuselage fineness
ratio 6. The bands of the fixed quantities are not surrogate inputs; their effect on the front is
reported once by a one-at-a-time sweep of the low-fidelity model (section 10.5), as the tanker
repository reports its bands.

Cruise speed is not an input. Each design flies at V_cruise = max(V_minpower, 1.3 V_stall), where
V_minpower is the speed of least power required on the design's own drag polar and V_stall uses the
design's own CL_max. This removes a dimension an optimizer would always drive to the same place.

## 3. Model (`drone/`, pure Python, numpy only; one file per block, each explainable line by line)

- **Geometry** (`drone/geometry.py`): straight-tapered wing with span b, area S = b^2/AR, root and tip
  chords from the taper ratio, no sweep, no dihedral, no twist, section NACA four-digit from
  (camber_pct, 40, thickness_pct) by the published NACA formulas (analytic, no data file). Tail
  surfaces sized by the volume coefficients; fuselage a body of revolution whose volume holds the
  payload and the battery at the fixed volumetric energy density, with fineness ratio 6.
- **Lifting-surface aerodynamics** (`drone/vlm.py`): a vortex-lattice method, horseshoe vortices on
  the mean camber surface, Trefftz-plane induced drag, spanwise section lift distribution. Lattice
  levels coarse, medium, fine (8 x 20, 12 x 30, 16 x 40 chordwise by semispan panels, cosine
  spacing), the medium lattice for the pools. Output: CL_alpha, alpha_L0, span efficiency e, and the
  section cl distribution at the wing CL.
- **Section data** (the one block that differs between fidelity levels, section 6): cl_max,
  profile drag cd_p(cl) and the zero-lift angle of the section at the design's cruise Reynolds
  number Re_c = rho V_cruise c_mean / mu.
- **Drag build-up** (`drone/drag.py`): wing profile drag from the section polar integrated over the
  span with the VLM's cl distribution; fuselage, tail and boom drag by flat-plate skin friction
  (Prandtl-Schlichting turbulent, Blasius laminar below Re 5e5) with Raymer form factors and
  wetted areas from the geometry; induced drag from the VLM's e. No trim drag (stated bias:
  flatters every design equally to first order); no compressibility (Mach below 0.1).
- **Mass closure** (`drone/mass.py`): m_TO = m_payload + m_battery + m_wing + m_fuselage + m_tail
  + m_propulsion, with m_battery = f_b m_TO, wing mass = skin areal density times wetted area plus a
  spar mass from the root bending moment of an elliptic lift distribution at the limit load factor
  times the factor of safety, carried by caps of the allowable stress at a depth equal to the section
  thickness at the root; propulsion mass = installed power over the specific power, with installed
  power = max(2 P_cruise, W RoC / eta_p + P_cruise) for a required rate of climb RoC = 2 m/s. The
  closure is a fixed-point iteration on m_TO; it must converge to 1e-9 relative in at most 100
  iterations (gate 3).
- **Mission** (`drone/mission.py`): level flight at V_cruise, power P = D V / eta_p, endurance
  E = DoD E_batt m_battery / P with a 60 s take-off and climb allowance at installed power subtracted
  from the usable energy. Recorded, not optimized: range at the speed of best L/D, stall speed, wing
  loading, cruise Reynolds number, cruise throttle fraction, static margin.

## 4. Gates (`physics/gates.py`, family `drone`; pure functions of the parameters, run before any
solver, by the MCP layer and again by the worker)

1. Reynolds range: Re_c inside [8e4, 5e5], the range where the section data are validated
   (section 9). Evaluated with the low-fidelity closure.
2. Stall margin by construction (V_cruise >= 1.3 V_stall) and cruise CL <= 0.7 CL_max.
3. Mass closure converges, every component mass positive, and the structure plus propulsion
   fraction 1 - f_b - m_payload/m_TO at least 0.15.
4. Manufacturing floor: tip chord at least 0.08 m and root section thickness at least 8 mm (the spar
   depth); wing loading inside [20, 150] N/m^2 (a design-space definition, trimmed on evidence if a
   corner does not close, as the inlet's gate 4 was).
5. Lattice quality for the VLM (panel aspect ratio at most 20, at least four chordwise panels on the
   tip chord) and, for the SU2 cases, the airfoil mesh-quality gate of `worker/make_case.py`
   (inverted cells, minimum angle, first-cell height, growth, aspect ratio) with the first cell set
   for y+ below 1 at the design's Reynolds number.

Not gated, recorded as a diagnostic: tip-stall indicator, the ratio of the section cl at 90 percent
semispan to cl_max when the wing is at CL_max.

## 5. Outputs and objectives

- endurance_h (maximize) and mtow_kg (minimize): the two objectives, f1 = -endurance, f2 = log mtow,
  with the GPs on endurance and log mtow as in Task 4.
- Recorded: range_km, v_cruise, v_stall, wing_loading, re_cruise, throttle_cruise, static_margin,
  cl_max, e_span, cd0, and the per-component masses.

## 6. Fidelity levels

- **Low** (seconds, on the container, family `drone`): section data from closed forms: cl_max from
  the empirical camber and Reynolds correlation recorded in the ledger (Raymer's for low Re, with its
  source), profile drag from flat-plate skin friction times the four-digit form factor, zero-lift
  angle from thin-airfoil theory of the NACA camber line. Everything else identical to the high
  level.
- **High** (minutes per angle on Colab through the queue, family `airfoil2d`): SU2 incompressible
  RANS with the Spalart-Allmaras model and its Bas-Cakmakcioglu transition option, on a structured
  C-mesh around the design's NACA section at its own cruise Reynolds number, five angles of attack
  (-2, 2, 6, 10, 14 deg), one SU2 case per angle. cl(alpha), cd(cl) and cl_max (from the highest
  converged angle, flagged if the polar has not peaked) replace the closed forms; the VLM, drag
  build-up, mass closure and mission are shared.
- **Multi-fidelity model**: linear autoregressive y_H = rho y_L + d, as Task 9 (`surrogate/mf_gp.py`),
  on both objectives.

## 7. Data ledger (`data/drone/`, open sources only)

One YAML per block with value, unit, source and band, in the form of the tanker repository's
`docs/assumptions.md`: `air.yaml` (ISA), `battery.yaml`, `propulsion.yaml`, `structure.yaml`,
`rules.yaml` (tail volumes, fineness, load factors, RoC, DoD, payload). Validation data under
`data/validation/`: the Warren-12 wing reference derivatives (CL_alpha 2.743 /rad, Cm_alpha -3.10
/rad, the standard vortex-lattice benchmark), and the UIUC Low-Speed Airfoil Tests wind-tunnel polars
of the Eppler E387 at Re 1e5, 2e5 and 3e5 (Selig et al., *Summary of Low-Speed Airfoil Data*, open
at the UIUC airfoil data site), transcribed with their source and retrieval date. No vendor
performance claims enter the ledger.

## 8. Data and runs

- Low-fidelity ground truth: the full box on a 9^6 grid (531 441 designs) with the medium lattice,
  gate-checked; at under a second per design this is a few hours on the container, run as one
  recorded job with its seed, commit and timing. Its exact Pareto front is the reference for
  question 2's second measurement.
- High-fidelity pool: 96 scrambled Sobol points (seed 0) in the six inputs, gate-checked; 5 SU2
  cases each, 480 cases, tag `pool_af`. Cost measured first on one design at the nominal point
  (section 9) and the pool cut to what fits the budget below, with the cut reported.
- Low-fidelity pool: the same 96 points plus 96 more (seed 1), for the two-level model.
- Every SU2 case is a job of the existing queue (params, mesh fingerprint, config hash, digest); the
  aircraft evaluation that combines a design's five cases is a pure function of their result records
  and is itself recorded under `runs/drone/<design_id>/`.

## 9. Validation before any ML (gate for the whole task)

Nominal design: b = 2.0 m, AR = 10, taper 0.6, f_b = 0.30, camber 4 %, thickness 12 %.

- V6a (hard, analytic): VLM on an elliptic planform of AR 8: e within 1 percent of 1 and CL_alpha
  within 2 percent of Helmbold's formula 2 pi AR / (2 + sqrt(AR^2 + 4)); on an AR 100 rectangular
  wing CL_alpha within 1 percent of 2 pi.
- V6b (hard, benchmark): VLM on the Warren-12 wing: CL_alpha and Cm_alpha within 2 percent of the
  reference values.
- V6c (hard, lattice study): nominal design, medium against fine lattice: e and CL_alpha within
  1 percent, endurance within 2 percent; the coarse-to-medium change reported.
- V6d (hard, bookkeeping): the mass closure's residual below 1e-9 relative; the mission's energy
  balance closes to 1e-9; the endurance at constant CL equals the closed form DoD E_batt m_b eta_p /
  (D V) to 1e-6 relative.
- V6e (hard, solver gate for the high level): SU2 on the E387 at Re 2e5 and 3e5 against the UIUC
  wind-tunnel polars: cl_alpha over the linear range within 5 percent; mean |cd/cd_UIUC - 1| over
  cl 0.3 to 0.9 at most 20 percent; cl_max within 10 percent (report). Mesh check medium against
  fine at Re 2e5: cd at cl 0.6 within 5 percent. If SA-BCM fails, SST with the Langtry-Menter
  transition model is tried once, as a recorded second attempt; if both fail, the high level is
  cut, the study runs single-level on the low model, and the deck says so.
- V6f (report): the low-fidelity closed forms against the same E387 data at the three Reynolds
  numbers, to size the discrepancy the two-level model has to learn.
- V6g (report, whole aircraft): CL_alpha and CD0 of the University of Minnesota Ultra Stick 25e
  from its published wind-tunnel data against the model built at its geometry, if its geometry and
  data are retrievable with an open licence; otherwise the row says "not run" with the reason.

Go/no-go: a hard failure of V6a to V6d that is not fixed stops the task. A failure of V6e cuts the
high level only.

## 10. Analyses (after the gate)

1. Pareto front from the GPs fitted on the high-fidelity pool (`analysis/pareto.py` with the drone
   bounds), observed, predicted and the band; the design map over the two most sensitive inputs; the
   low-fidelity exact front drawn beside it.
2. Replay on the high-fidelity pool as Task 4 and Task 9: random, LHS, max-variance, EHVI, 10 seeds,
   budgets 12 to 96; held-out error and hypervolume regret. Second measurement: the same four
   strategies run online on the low-fidelity model with unrestricted candidates (not pool-bound),
   regret against the exact front of the 9^6 grid, which removes the replay's pool limitation
   stated in the inlet talk.
3. Two-level against single-level: held-out error against the number of SU2 designs, the whole
   low-fidelity pool available to the two-level model.
4. Inverse query: maximize predicted endurance subject to P(mtow <= 4.0 kg) >= 0.9 on a 21^6 grid
   inside the gates; cap fixed here, before any run; one confirmation at the answer (five SU2 cases,
   C2 tolerance: both objectives inside their 90 percent intervals). If no design meets the cap,
   the report says so with the best probability reached, as Task 9 did.
5. Bias sweep: one-at-a-time sweep of the fixed quantities' bands (battery specific energy,
   propulsive efficiency, areal density, specific power) on the low-fidelity model at the inverse
   query's answer, reported as a ranked table, as the tanker repository's figure 4.

## 11. Schedule and cut-off

No fixed date. Order and cut-offs by gates, with the inlet study as the calibration: its pipeline
took seven days with the tools built along the way.

- Days 1 to 2: ledger, geometry, VLM, drag build-up, mass closure, mission, gates, schema for the
  two families, airfoil mesh and config template, tests.
- Day 3: validation V6a to V6g. **Go/no-go** at the end of the day.
- Days 4 to 6: low-fidelity grid on the container; SU2 pool on Colab through the queue (480 cases;
  at the inlet pool's 3 to 10 minutes per case this is 24 to 80 hours of worker time on 4 ranks, so
  the pool may be cut to 64 designs, reported).
- Day 7: analyses, confirmation run, report `docs/validation/<date>_task10_report.md`, and a talk
  section or an alternative deck.

## 12. Acceptance

Gate V6 recorded with every verdict; the low-fidelity grid and the SU2 pool recorded with every
failure kept; the four questions answered from records, comparisons stated as measured, including a
null result; tests for the NACA section generator against the published formula, the VLM on the
elliptic and Warren-12 wings, the mass closure's fixed point, the mission's closed form, the gates on
the box corners, the airfoil mesh builder's quality gate, and the two families' schemas.

## 13. Out of scope and stated biases

Out of scope: stability and control beyond the static margin, structural analysis beyond the spar
rule, propeller design (a fixed efficiency), take-off and landing distances, wind and altitude
envelopes (a candidate Task 11, in the form of Task 9's envelope), cost, and certification beyond
the class C2 mass cap. Biases that travel with every figure: no trim drag; fully turbulent skin
friction on the non-wing parts above Re 5e5; the fixed propulsive efficiency; the closed-form
structure; the section polar at one Reynolds number per design (the cruise one) while the wing's
chord varies along the span.

## Addendum 1 (2026-11-08): two corrections found while writing the acceptance tests

- V6a, the AR 100 rectangular wing: "CL_alpha within 1 percent of 2 pi" cannot hold, because the
  lifting-line slope at AR 100 is 2 pi AR / (AR + 2) = 6.160 per radian, 2 percent below 2 pi. The
  row now reads: within 1 percent of the lifting-line value 2 pi AR / (AR + 2) at AR 100. The
  Helmbold row at AR 8 is unchanged.
- The vortex-lattice method must take a swept planform, because the Warren-12 benchmark (V6b) has a
  leading-edge sweep of 53.54 degrees. The drone's own wing stays unswept; sweep enters only through
  the `Planform` leading-edge coordinates, so the solver has one code path for both.

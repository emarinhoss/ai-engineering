# Task 10 work breakdown: drone sizing with the inlet pipeline (2026-11-08)

Companion to `docs/specs/task10_drone_sizing.md` (the spec, read it first). This file turns the spec
into tasks and subtasks, assigns each to a model, fixes the interfaces the tests are written against,
and names the acceptance test that closes each one. Nothing here changes a decision of the spec; two
corrections found while writing the tests are recorded in the spec's addendum 1.

## Roles

| Model | Does | Does not |
|---|---|---|
| **Fable 5.1** | Writes the acceptance tests before the code (`tests/task10/`), reviews every diff against the spec, gives the verdict on each validation row, decides what a failed V6 row means, writes the report narrative | Implement modules |
| **Opus** | The numerics: the vortex-lattice method, the airfoil C-mesh, the closure and evaluation loop, the adaptation of the multi-fidelity and online-replay code | Choose constants or tolerances (they are in the spec and the ledger) |
| **Sonnet** | Everything else that is code: geometry, section closed forms, drag build-up, mission, schemas, gates, config template, metrics, polar aggregation, pool and grid scripts, the analysis adaptations, the notebooks' code cells | Numerics judgement; if a test fails for a reason that looks physical, stop and report |
| **Haiku** | The data ledger YAMLs and the validation-data transcriptions with their sources and retrieval dates, docstrings, notebook prose, figures, report tables, lint | Any number that is not copied from a named source |

Rules for every task: the test named under "Closes" must pass and nothing else may break; `ruff check .`
clean; a module that reads a constant reads it from `data/drone/` through the ledger loader, never
a literal; a run writes a record under `runs/` with params, commit, seed and timing. Fable's tests are
in `tests/task10/` and skip while the `drone` package does not exist; once it exists they run and
must pass. A task may add tests but may not weaken one of Fable's.

## The interfaces the tests assume

All angles in radians inside `drone/`, degrees at the schema. SI everywhere.

```
drone/ledger.py
  load(name) -> dict            # data/drone/<name>.yaml -> {quantity: value}; raises on a missing source
  quantity(name, key) -> Quantity(value, units, confidence, band, source)

drone/naca.py                   # NACA four-digit, closed trailing edge (last coefficient -0.1036)
  thickness(x, t)               # x in [0, 1] (array ok), t = thickness/chord; half thickness y_t
  camber_line(x, m, p)          # m = max camber/chord, p = its position/chord; returns (y_c, dyc_dx)
  coordinates(camber_pct, thickness_pct, n=101, position_pct=40.0) -> (x, y)
                                # closed loop, trailing edge to trailing edge over the upper surface
                                # first, cosine-spaced in x; y[0] == y[-1] == 0
  zero_lift_angle(camber_pct, position_pct=40.0) -> float   # thin-airfoil theory, radians

drone/geometry.py
  Planform(span, eta, chord, x_le, x_ref)   # dataclass; eta = y/(b/2) nodes from 0 to 1 (root to tip),
                                # chord and x_le at the nodes (x_le = leading-edge x), x_ref = moment
                                # reference x; a straight-tapered wing has two nodes
  tapered(span, aspect_ratio, taper_ratio, sweep_le_rad=0.0) -> Planform
  elliptic(span, aspect_ratio, n_nodes=41) -> Planform
  wing_dict(planform) -> dict(S, b, AR, c_root, c_tip, c_mean, c_mac, x_mac_le)
  tail(wing, fixed) -> dict(S_h, S_v, arm)
  fuselage(volume_m3, fineness) -> dict(length, diameter, wetted_area, volume)
  build(params, fixed) -> dict  # everything above for a design, plus wetted areas per component

drone/vlm.py
  LEVELS = {"coarse": (8, 20), "medium": (12, 30), "fine": (16, 40)}   # chordwise x semispan panels
  solve(planform, alpha, level="medium", camber=None) -> dict
       # keys: CL, CDi, e, Cm (about planform.x_ref, reference chord = c_mac, positive nose up),
       # eta (panel-strip centres, root to tip), cl (section lift coefficient per strip)
       # camber: optional callable x/c -> dyc/dx applied to every strip (same section everywhere)
  derivatives(planform, level="medium", camber=None) -> dict(CL_alpha, alpha_L0, Cm_alpha)
       # central difference over +-2 deg about alpha = 0

drone/section.py
  SectionData(cl_max, alpha_L0, cd_of_cl, source)    # cd_of_cl: callable cl -> cd_p
  low_fidelity(camber_pct, thickness_pct, reynolds, fixed) -> SectionData
  from_polar(alpha_deg, cl, cd, source) -> SectionData  # the high level, from five SU2 cases

drone/drag.py
  parasite(geometry, V, fixed) -> dict(component -> CD contribution on S_wing), with "total"
  total(geometry, section, vlm_result, CL, V, fixed) -> dict(CD, CD_induced, CD_profile, CD_parasite)

drone/mission.py
  v_min_power(...) and v_stall(m, S, cl_max, rho)
  endurance_h(m_batt, E_spec_Wh_kg, dod, eta_p, P_cruise_W, P_installed_W, t_climb_s) -> float
       # (dod * E_spec * 3600 * m_batt - P_installed * t_climb_s) / P_cruise / 3600
  power_required(D, V, eta_p) -> float

drone/evaluate.py
  evaluate(params, fixed, section=None, level="medium") -> dict
       # section None -> low fidelity; else a SectionData from the SU2 polar
       # keys: endurance_h, mtow_kg, range_km, v_cruise, v_stall, wing_loading, re_cruise,
       # throttle_cruise, static_margin, cl_max, e_span, cd0, masses (dict), closure_iterations,
       # closure_residual, gates (list of messages, empty when clean), diagnostics (dict)
       # The mass closure is a fixed-point iteration on mtow; evaluate raises ValueError if it does
       # not converge to 1e-9 relative in 100 iterations.

physics/gates.py        family "drone": _check_drone(params) -> gate messages in the inlet form
                        ("gate 1 (reynolds range): ...", "gate 2 (stall margin): ...", ...)
mcp_server/schemas.py   family "drone" (span_m, aspect_ratio, taper_ratio, battery_fraction,
                        camber_pct, thickness_pct, fidelity in {"low", "high"}, tag) and
                        family "airfoil2d" (camber_pct, thickness_pct, reynolds [8e4, 5e5],
                        alpha_deg [-4, 16], transition in {"BCM", "LM", "NONE"}, mesh_level, tag,
                        max_iter); bounds as the spec's section 2 and 4
geometry/airfoil2d.py   build(params) -> (geometry, Mesh): structured C-mesh, markers "airfoil" and
                        "farfield" only; first cell from y+ = 0.5 at the chord Reynolds number with
                        Cf = 0.074 Re^-0.2; farfield at 30 chords; levels coarse/medium/fine by 1.4
cases/templates/inc_rans_airfoil.cfg   SOLVER= INC_RANS, SA, SA_OPTIONS= BCM (or the LM template),
                        REF_AREA = chord (1 m), density and viscosity from fixed, velocity from Re
postprocess/metrics.py  family "airfoil2d": cl, cd, cm (last 10 percent of history, mean and drift)
analysis/drone_polar.py polar(records) -> SectionData: cl_alpha by least squares over the angles
                        with cl below 0.85 cl_max, cl_max = max cl with flag "not_peaked" when the
                        last angle is the maximum, cd(cl) by linear interpolation in cl
```

## Tasks

Effort is in model-sessions of about two hours. "Closes" names the acceptance test file. Order is
the dependency order; tasks in the same group can run in parallel.

### T10.1 Data ledger and validation data (Haiku, Sonnet reviews sources; no numerics)

| Sub | What | Output | Closes |
|---|---|---|---|
| 1a | `data/drone/air.yaml`, `battery.yaml`, `propulsion.yaml`, `structure.yaml`, `rules.yaml` in the ledger form of `tanker_comparison/docs/assumptions.md`: name, value, units, confidence (published, derived, assumed), band for every assumed value, source with retrieval date | five YAML files | `test_ledger.py` |
| 1b | `data/validation/warren12.yaml`: planform (root chord 1.5, tip chord 0.5, semispan 1.414, leading-edge sweep 53.54 deg, reference area 2.83, reference chord 1.0), the moment reference point, CL_alpha 2.743 /rad and Cm_alpha -3.10 /rad with the source (the AVL or Tornado documentation that states them) | one YAML | `test_vlm.py` |
| 1c | `data/validation/e387_uiuc.yaml`: the E387 polars at Re 1e5, 2e5, 3e5 from the UIUC Low-Speed Airfoil Tests, alpha, cl, cd per point, with volume, page, retrieval date | one YAML | `test_ledger.py` |
| 1d | `drone/ledger.py` loader and `scripts/make_drone_assumptions.py` that renders `docs/drone_assumptions.md` (a byte-compare staleness test as in the tanker repository) | loader, script, doc | `test_ledger.py` |

Sonnet checks every source string resolves to a public document and refuses a vendor claim.
Effort: 2 sessions.

### T10.2 Section and planform geometry (Sonnet)

| Sub | What | Closes |
|---|---|---|
| 2a | `drone/naca.py` with the published four-digit formulas, closed trailing edge, thin-airfoil zero-lift angle by numerical quadrature | `test_naca.py` |
| 2b | `drone/geometry.py`: `Planform`, `tapered`, `elliptic`, `wing_dict`, `tail`, `fuselage`, `build` | `test_geometry.py` |

Effort: 1 session.

### T10.3 Vortex-lattice method (Opus)

| Sub | What | Closes |
|---|---|---|
| 3a | `drone/vlm.py`: horseshoe vortices on the mean surface, cosine spacing in both directions, Biot-Savart influence matrix, Trefftz-plane induced drag, section cl per strip, Cm about `x_ref`; sweep and taper through `Planform`; at most about 250 lines, numpy only | `test_vlm.py` (elliptic, Helmbold, lifting-line at AR 100, Warren-12, lattice convergence, symmetry) |
| 3b | `derivatives` by central difference; a short docstring that states the sign conventions | same |

Effort: 2 sessions. The Warren-12 row is the one most likely to fail first; if it does, Opus reports
the measured values and stops, and Fable decides (the reference point or the spacing is the usual
cause, not the solver).

### T10.4 Section closed forms and drag build-up (Sonnet)

| Sub | What | Closes |
|---|---|---|
| 4a | `drone/section.py`: `low_fidelity` from the ledger's correlations (cl_max from the camber and Reynolds correlation in `rules.yaml`, profile drag = flat-plate Cf times the four-digit form factor, alpha_L0 from `naca.zero_lift_angle`); `from_polar` | `test_section.py` |
| 4b | `drone/drag.py`: Prandtl-Schlichting and Blasius skin friction with the Re 5e5 switch, Raymer form factors, wetted areas from `geometry.build`, induced drag from the VLM's e, profile drag integrated over the strips | `test_drag.py` |

Effort: 1 session.

### T10.5 Mass closure, mission and the evaluation loop (Opus)

| Sub | What | Closes |
|---|---|---|
| 5a | `drone/mission.py`: cruise speed rule, power, endurance, range at best L/D | `test_mass_mission.py` |
| 5b | `drone/evaluate.py`: the fixed-point closure on take-off mass with the aero evaluated at each iterate; the spar rule; installed power; all recorded diagnostics; raises on non-convergence | `test_mass_mission.py`, `test_evaluate_nominal.py` |

Effort: 2 sessions.

### T10.6 Schema and gates for the two families (Sonnet)

| Sub | What | Closes |
|---|---|---|
| 6a | `mcp_server/schemas.py`: families `drone` and `airfoil2d` with the bounds of the spec; `to_params` unchanged in form | `test_gates_schema.py` |
| 6b | `physics/gates.py`: `_check_drone` with gates 1 to 5 of the spec, messages in the inlet form; `airfoil2d` has only the mesh gate (no physics gate) | `test_gates_schema.py` |
| 6c | `designs/make_pool_drone.py` with `LOW`, `HIGH` and a 96-point scrambled Sobol design (seed 0) plus 96 more (seed 1), gate-checked, committed as `designs/pool_drone96.csv` and `designs/pool_drone_lf192.csv` | `test_gates_schema.py` |

Effort: 1 session.

### T10.7 The airfoil2d SU2 family (Opus for the mesh, Sonnet for the rest)

| Sub | Model | What | Closes |
|---|---|---|---|
| 7a | Opus | `geometry/airfoil2d.py`: structured C-mesh from `naca.coordinates`, wake cut, farfield at 30 chords, first cell from the y+ rule, growth at most 1.2, passes `worker/make_case.quality_failures`; `requested_first_cell` entry in `worker/make_case.py` | `test_airfoil_mesh.py` |
| 7b | Sonnet | `cases/templates/inc_rans_airfoil.cfg` (SA-BCM) and `inc_sst_lm_airfoil.cfg` (the recorded second attempt), rendered by `cases/config.py` for family `airfoil2d`; every key passes `cases/check_keys.py` against the pinned SU2 v8.2.0 template | `test_airfoil_mesh.py` |
| 7c | Sonnet | `postprocess/metrics.py` family `airfoil2d`: cl, cd, cm from the history's lift and drag coefficient columns; `postprocess/history.py` drift on cl and cd | `test_polar_aggregation.py` |
| 7d | Sonnet | `analysis/drone_polar.py`: five case records to one `SectionData`; `analysis/drone_design.py`: the design-level record `runs/drone/<design_id>/result.json` from a params file and its five case records | `test_polar_aggregation.py` |
| 7e | Sonnet | Smoke run of one airfoil2d case on the container (fake SU2 and, if the binary is present, real SU2 at Re 2e5 for 200 iterations); `tests/test_faults.py` extended with one airfoil2d fault (unknown transition option) | `test_faults.py` |

Effort: 3 sessions.

### T10.8 Validation V6 (Sonnet runs, Fable verdicts)

| Sub | What | Output |
|---|---|---|
| 8a | V6a to V6d from `tests/task10/` on the container; the V6c lattice study and the V6d closure checks recorded under `runs/drone/validation/<date>/` | records and `docs/validation/<date>_task10_v6.md` rows |
| 8b | V6e: E387 at Re 2e5 and 3e5, five angles each, medium and fine mesh, SA-BCM first, through the queue on Colab (`notebooks/01_worker_colab.ipynb` unchanged) or on the container; the UIUC comparison table; SST-LM as the recorded second attempt only if BCM fails | records, table |
| 8c | V6f: the low-fidelity closed forms against the same data; V6g if the Ultra Stick data are retrievable | rows |
| 8d | **Fable: the verdict per row and the go/no-go.** A hard failure of V6a to V6d stops the task until fixed; a V6e failure cuts the high level | the verdict block in the validation document |

**Verdict 2026-11-08 (Fable), from `runs/drone/validation/2026-11-08/v6.json` at commit faaf7f3:** V6a pass (elliptic AR 8 e within 0.26 percent of 1, CL_alpha 1.95 percent below Helmbold, AR 100 limit within 0.1 percent); V6b CL_alpha pass (+1.0 percent), Cm_alpha pending on the source of the reference point (+1.2 percent about the root leading edge); V6c pass (medium to fine: 0.18 percent in CL_alpha, 0.26 percent in e, 0.13 percent in endurance); V6d pass (closure residual 5.6e-10, energy balance and masses closed to machine precision). **Go for the low-fidelity grid and pools (T10.9a, 9b).** V6e to V6g not run: V6e needs the SU2 cases, V6f the E387 polars, V6g the Ultra Stick data.

Effort: 2 sessions plus solver time.

### T10.9 Pools (Sonnet, Colab)

| Sub | What |
|---|---|
| 9a | Low-fidelity grid: `analysis/drone_grid.py` evaluates the 9^6 grid with `multiprocessing`, gate-checked, writes `runs/drone_grid/<date>/grid.csv` (one row per design with every output and the gate messages) and `front.csv` (the exact Pareto front); runs on Colab CPU (`notebooks/10_drone_lowfi_grid_colab.ipynb`) or the container |
| 9b | Low-fidelity pool at the 192 design points (same script, `--design` option) |
| 9c | High-fidelity pool: `queue_batch` on `designs/pool_drone96.csv` expanded to 5 cases per design (tag `pool_af`); cost measured on the first design; the cut to 64 designs if the first costs more than 15 minutes, reported |
| 9d | Ingest and the per-design records; `runs/pool_af/results.csv` |

Effort: 2 sessions plus worker time (24 to 80 hours on Colab).

### T10.10 Analyses (Opus adapts, Sonnet runs)

| Sub | Model | What |
|---|---|---|
| 10a | Sonnet | `analysis/pareto.py` and `analysis/inverse.py` take bounds and a family from `designs.make_pool_drone` (a `--family drone` option; the inlet defaults unchanged); the 21^6 inverse grid predicted in chunks |
| 10b | Opus | `analysis/replay_drone_online.py`: the four strategies run online on the low-fidelity model with unrestricted candidates (candidates from a fresh 4096-point Sobol set per step; the acquisition picks among them), regret against `front.csv`; the pool replay is `surrogate/replay.py` with the drone bounds |
| 10c | Opus | `analysis/mf_drone.py` from `analysis/mf3r.py` with the drone inputs and the 192-point low pool |
| 10d | Sonnet | The bias sweep of section 10.5 of the spec; the confirmation run of the inverse query's answer through the queue; `analysis/confirm.py` with the drone family |
| 10e | Haiku | Figures: front with band and the exact low-fidelity front; replay error and regret; online regret; multi-fidelity error against SU2 designs; ranked bias table |

Effort: 3 sessions plus compute.

### T10.11 Report and presentation (Haiku drafts, Fable narrative)

| Sub | What |
|---|---|
| 11a | `docs/validation/<date>_task10_report.md`: V6 verdicts, the four questions answered from records, biases, every number with its file |
| 11b | A deck or a section (Éder's choice, question 4 below); built by a `docs/talk/build_deck_drone.py` that reuses `build_deck.py`'s helpers and reads an outline |
| 11c | Study-guide entries for the new physics (VLM, mass closure, electric endurance, airfoil RANS at low Reynolds) in the form of the existing entries |

Effort: 2 sessions.

## Dependency graph

```
T10.1 ---> T10.4 ---> T10.5 ---> T10.6 ---> T10.8 ---> T10.9 ---> T10.10 ---> T10.11
T10.2 ---> T10.3 ---'            T10.7 ---'
```

T10.1, T10.2 and T10.3 can start together (T10.3 needs only `Planform` from T10.2, which is a
dataclass Sonnet writes first). T10.7 can run in parallel with T10.4 to T10.6.

## Colab notebooks

- `notebooks/01_worker_colab.ipynb` (exists): serves the airfoil2d SU2 cases unchanged, because the
  worker rebuilds a case from its params by family. Pin `COMMIT` to the commit that holds T10.7.
- `notebooks/10_drone_lowfi_grid_colab.ipynb` (written with this plan, code cells complete against
  the interfaces above, runnable once T10.5 and T10.6 are merged): the 9^6 low-fidelity grid on a
  CPU runtime with all cores, written to Drive under `su2queue/drone_grid/<stamp>/`, with the exact
  front and a timing record.
- `notebooks/11_drone_surrogate_colab.ipynb` (written with this plan, runnable once T10.10 is
  merged): the pool replay, the online replay against the exact front, the two-level comparison and
  the inverse query on a GPU runtime. The GPs are small, so the GPU matters only for the 21^6 inverse
  grid and the online replay's candidate scoring; the notebook measures both and prints whether the
  GPU helped, so the claim is recorded rather than assumed.

## Decisions (Éder, 2026-11-08)

Questions 1 to 4 below: the defaults stand (NACA four-digit per design; 0.5 kg payload and the 4.0 kg
cap; measure the first SU2 design and cut the pool to 64 if it costs more than 15 minutes; a separate
deck decided after the results). Question 5: work starts on 2026-11-08, before the talk, with T10.1,
T10.2, T10.3 and T10.7a/7b in parallel. The sandbox cannot reach the UIUC airfoil data site or MIT
(the AVL source): the E387 transcription (T10.1c) and the Warren-12 moment reference are recorded as
`retrieval: pending` until the files are fetched from a machine with open internet (Colab or Éder's),
and their tests skip with that reason rather than fail. Nothing is typed from memory into the ledger.

### Decision 6 (Éder, 2026-11-08 06:50 UTC): the SU2 rerun after the first smoke case

The first airfoil2d case, `runs/smoke/airfoil2d-96a9dd0f51/` (NACA 4412-type, Re 2e5, alpha 6 deg,
SA-BCM, medium mesh of 43 008 cells), ran its full 3000 iterations in 785.7 s on 4 Colab ranks and
had not converged: over the last tenth of the iterations cl drifted 5.6 percent and cd 17.4 percent
(cl 0.918, cd 0.0208, cm 0.071 as the tail means). At that cost one five-angle design is about 65
minutes, far over question 3's 15-minute line, so the 96-design pool is cut before it is submitted.
Éder chose the recommendation: rerun the same case once with `max_iter` 6000 and a Cauchy stopping
criterion on the lift and drag coefficients (both templates: `CONV_FIELD= ( LIFT, DRAG )`,
`CONV_CAUCHY_ELEMS= 200`, `CONV_CAUCHY_EPS= 1E-5`, `CONV_STARTITER= 500`), read the drift and the
iteration at which it stopped, and only then fix the iteration budget and cut the pool to 64 designs
at 3 angles. The rerun is the case staged from this commit with tag `smoke2`; nothing else in the
template changed, and `postprocess/history.summarize` still classifies the run from the pressure
residual drop and the coefficient drifts (it reads `rms[P]` since the same day's fix, the first
case having failed at postprocess on the compressible column name). The worker notebook pulls the
repository only when its kernel starts, so the rerun needs the worker restarted on `main`.

### Decision 6, the rerun's result and what it fixes (Fable, 2026-11-08 07:30 UTC)

`runs/smoke2/airfoil2d-51d551f2cc/` (same case, `max_iter` 6000, Cauchy stop on CL and CD): SU2
stopped itself at **4,867 iterations after 1,385 s** on 4 ranks (0.285 s per iteration), exit 0,
digest verified. Tail means cl 1.0260, cd 0.016710, cm 0.08358, against the 3,000-iteration run's
0.9178 / 0.020830 / 0.07126, so the first run was far from its own solution: cl was still 10.5 %
low and cd 24.7 % high when its budget ran out. The pressure residual fell 4.78 orders (−3.94 to
−8.72). The classifier still says `not_converged`: its drift is (max − min) over the LAST 20 % of
iterations (973 here) divided by the final value, 2.15 % in cl and 5.34 % in cd, while SU2's Cauchy
rule averages the per-iteration relative change over the last 200. The two measure different
things and both are kept; a 973-iteration window on a slowly settling case reports its approach,
not its scatter. The record carries both numbers and no rule is loosened.

What this fixes. (1) The airfoil2d iteration budget is **6,000 with the Cauchy stop** (schema
default `MAX_ITER_DEFAULT` 3000 → 6000; the stop fires first on this case). (2) The cost is
**23 min per angle on 4 Colab ranks at the medium mesh**, so a design at the spec's 5 angles is
about 115 min and at 3 angles about 70 min: question 3's 15-minute line is exceeded by a factor
of 4.6 even at 3 angles, and the default answer, **64 designs at 3 angles, is about 74 worker
hours** — more than a Colab session. (3) The next measurement is therefore the mesh pair the spec's
V6e asks for anyway: the same case at `coarse` and at `fine`, staged as `airfoil2d` jobs with tag
`smoke2`, to put a number on what the medium mesh buys and whether the pool can run coarse with
medium and fine kept for the validation rows. Until that pair is in, no pool is staged. The
pool size is Éder's call once the pair gives the cost of each level.

### The mesh pair, first half: coarse against medium (Fable, 2026-11-08 15:45 UTC)

`runs/mesh/airfoil2d-59cd4287e9/` (coarse, 21,760 cells, same case and budget): SU2 stopped at
**3,595 iterations after 498 s** on 4 ranks, pressure residual down 4.89 orders, drifts 1.46 % in cl
and 3.95 % in cd over the last fifth (`not_converged` by the classifier's rule, as the medium run).
Against the medium run (`runs/smoke2/airfoil2d-51d551f2cc`): **cl −0.47 %, cd +3.82 %, cm −0.93 %**.
Cost per iteration per cell is the same on both meshes (6.37e-6 against 6.62e-6 s), so the coarse
run is 2.8× cheaper by cells and iterations together: **8.3 min per angle against 23**. The fine
half (`airfoil2d-e161fb7e6b`, 84,152 cells, timeout 5,013 s) is staged and waits for the worker's
cap to rise to 7,200 s (worker restart). No verdict on which level the pool runs at until the fine
half is in: a 3.8 % drag shift coarse-to-medium is the size of the effect the pool is meant to
resolve, and the medium-to-fine shift says whether medium itself is converged.

### V6f recorded (Fable, 2026-11-08 17:00 UTC): the low-fidelity section against the E387 tunnel data

`runs/drone/validation/2026-11-08/v6.json` now carries twelve V6f rows (report only, by the spec),
the closed forms of `drone/section.py::low_fidelity` at the E387's measured camber 3.8 % at 40 %
chord and thickness 9.1 % against Volume 1 runs 211, 213 and 215. Three findings, all the size of
what the two-level model has to learn and none tuned away: (1) the lift slope is **19 to 23 % low**
(0.0822 per degree against 0.1017 to 0.1063), which says the tunnel's lift effectiveness is 0.93 to
0.97 where `rules:section_lift_effectiveness` is `assumed` 0.75 with band [0.6, 0.9] — the band does
not contain the measured value, which is a ledger finding to rule on, not a number to move here;
(2) the constant profile drag misses the tunnel polar by a mean of **43 to 52 %** over cl 0.3 to 0.9
(the Reynolds trend is right: the miss falls with Re); (3) cl_max is 12 to 13 % high and alpha_L0
0.8 to 0.9 deg too negative. V6a to V6d reproduce their recorded values. V6e waits for the ten E387
SU2 cases in the queue; its rules are fixed in `tests/task10/test_validation_e387.py` before any
result exists (point-to-point at the tunnel's own angles, no interpolation).

### V6e at Re 203,800 recorded (Fable, 2026-11-08 22:00 UTC): SU2 against the E387 tunnel — FAIL on the lift slope, by 0.5 points

`runs/e387/` holds the five Re 203,800 cases (alpha 1.27, 2.67, 4.23, 5.59, 7.23 deg; medium mesh,
SA-BCM, Cauchy-stopped at 4,146 to 5,020 iterations, cl drift 1.1 to 2.0 %, cd drift 4.1 to 6.9 %,
all status `not_converged` by the drift rule and all kept by the aggregator's Cauchy rule). Against
Volume 1 run 213 at the same five angles, no interpolation:

| row | SU2 | tunnel | deviation | tolerance | verdict |
|---|---|---|---|---|---|
| cl_alpha (per deg, fit over the five angles) | 0.10445 | 0.09901 | +5.49 % | 5 % | **fail** |
| cd ratio (mean of \|SU2/tunnel − 1\|, tunnel cl in [0.3, 0.9], 4 points) | — | — | 8.0 % | 20 % | pass |
| cl_max (highest matched angle) | 1.129 | 1.164 | −3.0 % | report | report |

Point by point SU2 lifts **8.0 to 11.6 % high** at every angle (+11.6, +10.0, +8.1, +8.0, +8.4 %
from 1.27 to 7.23 deg) and its drag runs **10.3 % low to 1.6 % high** (−9.8, −10.3, −8.3, −3.5,
+1.6 %), so the lift-slope miss is a uniform offset plus a slightly steeper slope, not a stall-onset
effect, and the drag miss shrinks with angle and changes sign at the highest one. **CORRECTED
2026-11-08 23:10 UTC: this block first said "drags 3 to 10 % low" and gave the cd ratio as "−8.0 %";
the ratio row is a mean ABSOLUTE deviation (unsigned, 4 of the 5 points fall in the cl band) and the
per-point drag is not low at every angle. Found by the deck builder reading `runs/e387` directly
rather than this block — which is what reading from records is for.** **Not tuned.** The miss is 0.49 points over a 5 % tolerance fixed
before any case ran, and it is reported as a fail; the spec's consequence (8d) is that a V6e failure
cuts the high level, so the ruling put to Éder was whether the medium-mesh SA-BCM polar is accepted
as the high level WITH this 8 to 11 % lift bias recorded beside every number it produces, or whether
the Re 305,200 set (queued) and a fine-mesh pair must land first. **Ruled: decision 8 below.** The tunnel slope here (0.0990) is
the five-angle fit; V6f's 0.1017 is the fit over the whole run-213 polar, which is why the two rows
quote different tunnel slopes for the same data. The medium-versus-fine row is `not run` until a fine
E387 case exists at this Re; the fine E387 mesh currently fails the inversion gate (8 cells, strict
xfail in `tests/task10/test_airfoil_file.py`), so that row is blocked on the mesher.

### T10.9b and T10.10b, first half recorded (Fable, 2026-11-08 17:55 UTC): the low pool and its replay

`runs/drone_pool_lf/2026-11-08/` is the 192-point low pool (`designs/pool_drone_lf192.csv`, two
Sobol seeds, gate-checked at creation) through the real low model: 192 clean, 0 gated, 0 failed,
exact pool front of 15 designs, 669 s on two sandbox workers. `runs/replay_drone_pool/2026-11-08/`
is `surrogate.replay --family drone` on it, 10 seeds, 8 initial points, 40 evaluations. Mean
hypervolume regret against the pool's own front (same 8 initial points for every strategy of a
seed, hence equal at n = 8):

| n | random | lhs | al_ehvi | al_maxvar |
|---|---|---|---|---|
| 8 | 0.285 | 0.285 | 0.285 | 0.285 |
| 16 | 0.210 | 0.210 | 0.034 | 0.171 |
| 24 | 0.170 | 0.152 | 0.012 | 0.114 |
| 32 | 0.133 | 0.148 | 0.000 | 0.085 |
| 40 | 0.118 | 0.107 | 0.000 | 0.062 |

On the low pool EHVI recovers the whole 15-point front by 32 evaluations where random and LHS are
still at 0.11 to 0.13 after 40; max-variance sits between. This is the cheap, smooth, gate-free
level, so it is the easy case for a GP; the online replay (unrestricted candidates, gates live)
and the two-level model are where the claim is tested, and the online run is in progress.

### T10.10b, second half recorded (Fable, 2026-11-08 18:20 UTC): the online replay, and active learning LOSES

`runs/replay_drone_online/2026-11-08/` (online.csv, record.json; commit 83c7676, 2,496 s on one
sandbox core): the four strategies run online on the real low-fidelity model, 10 seeds, 8 initial
points, 40 evaluations, 4,096 fresh Sobol candidates per step, regret against the exact 9^6 front.
Mean hypervolume regret and mean number of gated picks (of the 32 after the initial design):

| n | random | lhs | al_ehvi | al_maxvar |
|---|---|---|---|---|
| 8 | 0.409 | 0.409 | 0.409 | 0.409 |
| 16 | 0.344 | 0.365 | 0.347 | 0.382 |
| 24 | 0.321 | 0.312 | 0.323 | 0.368 |
| 40 | **0.294** | **0.271** | 0.317 | 0.353 |
| gated picks at 40 | 1.9 | 4.0 | **29.7** | **25.4** |

**Active learning loses to random and LHS on the unrestricted box, and the mechanism is in the
table: EHVI spends 30 of its 32 picks on candidates that fail a gate** (tip-chord floor, structure
fraction, stall margin), because the front lies against the gated edge of the box (long span, high
aspect ratio, low taper) and the two GPs know nothing about the gates; max-variance does the same
for a different reason (variance is largest where nothing has been observed, which is the gated
region). Random and LHS lose only 2 to 4 picks to gates. This is the honest result the plan asked
for and it is published as such. It is also the measured case for a feasibility model in the
acquisition (the inlet study has one, `surrogate/feasibility.py`): a fifth strategy that weights
the acquisition by P(feasible) is the next experiment, run beside these four and not instead of
them, so the comparison stays on the record.

### T10.10b, third half recorded (Fable, 2026-11-08 18:55 UTC): with a feasibility model, active learning wins

`runs/replay_drone_online/2026-11-08_feas/` (commit edd6c84, 851 s): the two weighted strategies
on the same seeds, budgets, candidate sets and initial designs as the first online run, so the
rows are directly comparable (identical regret 0.409 at n = 8). Mean regret and gated picks:

| n | random | lhs | al_ehvi | al_ehvi_feas | al_maxvar | al_maxvar_feas |
|---|---|---|---|---|---|---|
| 8 | 0.409 | 0.409 | 0.409 | 0.409 | 0.409 | 0.409 |
| 16 | 0.344 | 0.365 | 0.347 | **0.246** | 0.382 | 0.365 |
| 24 | 0.321 | 0.312 | 0.323 | **0.158** | 0.368 | 0.326 |
| 40 | 0.294 | 0.271 | 0.317 | **0.092** | 0.353 | 0.268 |
| gated picks of 32 | 1.9 | 4.0 | 29.7 | **7.5** | 25.4 | 7.6 |

The feasibility model (logistic regression on the scaled inputs, fitted on every evaluated point
of that run, rejected initial draws included, factor 1 until both labels exist) takes EHVI's gated
picks from 29.7 to 7.5 and its regret at 40 from 0.317 to **0.092, a third of LHS's 0.271**; the
same weighting lifts max-variance only to parity with LHS, because variance is still largest in
the unexplored gated corner. The mean p(feasible) the model assigned to its own picks falls from
0.95 to 0.85 as the search presses on the gated edge where the front lies. **The two tables
together are the method's answer on this problem: active learning beats space-filling sampling
only when the acquisition knows where the design is buildable, and loses to it otherwise.** Both
runs are published; neither replaces the other.

### The mesh pair completed, and the pool options (Fable, 2026-11-08 20:00 UTC)

`runs/mesh/airfoil2d-e161fb7e6b/` (fine, 84,152 cells; its first attempt, refused on the 1 nm
fingerprint, is kept beside it as `.first_attempt`): **budget exhausted at 6,000 iterations after
3,162 s** on 4 ranks, pressure residual down 4.38 orders, drifts 4.4 % in cl and **10.3 % in cd**
over the last fifth. The three levels of the same case (NACA 4412, Re 2e5, alpha 6 deg, SA-BCM):

| level | cells | iterations | wall | cl | cd | cm | cd drift |
|---|---|---|---|---|---|---|---|
| coarse | 21,760 | 3,595 (Cauchy) | 498 s | 1.02115 | 0.017348 | 0.08280 | 3.9 % |
| medium | 43,008 | 4,867 (Cauchy) | 1,385 s | 1.02599 | 0.016710 | 0.08358 | 5.3 % |
| fine | 84,152 | 6,000 (budget) | 3,162 s | 1.01381 | 0.017157 | 0.08230 | 10.3 % |

Against fine: medium cl +1.2 %, cd −2.6 %, cm +1.6 %; coarse cl +0.7 %, cd +1.1 %, cm +0.6 %.
**The medium-to-fine drag shift (2.6 %) is inside the spec's 5 % mesh criterion, but it is also
smaller than the fine run's own drift (10 %), and the three drags are not monotone in cell count,
so what the table resolves is the drift band and not the mesh.** The steady solution at this
Reynolds number does not settle (the nominal polar shows the same: drift rising from 0.6 % at
0 deg to 16 % at 12 deg), which is a property of the flow (a moving laminar separation bubble
under the BCM transition model) and not of the budget. The cost per iteration per cell is the
same at all three levels (6.3 to 6.6 µs on 4 Colab ranks).

**Pool options, from measured costs (one worker, 4 ranks; two workers halve the wall time):**

| designs × angles | coarse (~10 min/angle, budget-limited at 14) | medium (~23 min/angle) |
|---|---|---|
| 64 × 3 (question 3's default) | 32 h | 74 h |
| 48 × 3 | 24 h | 55 h |
| 32 × 3 | 16 h | 37 h |
| 24 × 3 | 12 h | 28 h |

Fable's recommendation, for Éder to rule on: run the pool on the **coarse** mesh (its drag is
within 1.1 % of fine on this case, inside every drift band, at 2.8× less cost), keep the E387
validation cases and a 6-design coarse/medium pair on **medium** as the recorded bias check, and
take **48 designs × 3 angles (2, 6, 10 deg)** so the pool finishes in a day on one worker. Nothing
is staged until the ruling; the ten E387 medium cases are already in the queue.

### Decision 7 (Éder, 2026-11-08 20:45 UTC, "Colab is running now"): the SU2 pool is staged

Taken as approval of Fable's recommendation with one change Fable made for a measured reason:
**32 designs, not 48, at the spec's five angles (−2, 2, 6, 10, 14 deg), coarse mesh**, because the
nominal polar showed the budget running out at 0 and 10 deg, and a three-angle polar that loses
one angle cannot form (the aggregator needs three); five angles keep the section's cl_max in reach
and the cost the same as 48 × 3. Each design's section is its own NACA four-digit at its cruise
Reynolds number from the low model (87,400 to 269,000 across the 32; all inside the airfoil2d
bounds, none gated). `designs/make_pool_af.py` is the staging script and
`designs/pool_af_cases.csv` the case table: 160 cases, tag `pool_af`, plus the recorded bias
check, the first 4 designs at 2, 6, 10 deg on the medium mesh, 12 cases, tag `pool_af_bias`
(172 cases, batches at commit 9d0289a, ~29 + 5 worker-hours on one 4-rank worker). Queued behind
the eight remaining E387 cases. The acceptance rule for budget-exhausted runs is still open and
applies to this pool when it is ruled.

### V6e at Re 305,200 recorded (Fable, 2026-11-08 23:45 UTC): the same miss, slightly larger

`runs/e387/` now holds the five Re 305,200 cases too (alpha 1.04, 2.53, 4.07, 5.93, 6.93 deg; medium
mesh, SA-BCM, Cauchy-stopped at 4,238 to 5,034 iterations, cl drift 0.5 to 1.3 %, cd drift 4.6 to
7.9 %). Against Volume 1 run 215 at the same five angles (`runs/drone/validation/2026-11-08/v6.json`):

| row | SU2 | tunnel | deviation | tolerance | verdict |
|---|---|---|---|---|---|
| cl_alpha (per deg, fit over the five angles) | 0.10621 | 0.09979 | +6.44 % | 5 % | **fail** |
| cd ratio (mean of \|SU2/tunnel − 1\|, tunnel cl in [0.3, 0.9]) | — | — | 5.7 % | 20 % | pass |
| cl_max (highest matched angle) | 1.111 | 1.156 | −3.9 % | report | report |

Point by point: cl +12.7, +10.4, +8.9, +8.0, +9.6 % from 1.04 to 6.93 deg; cd −7.5, −3.8, −5.9, +2.3,
−0.6 %. So the lift offset is the same 8 to 13 % at both Reynolds numbers and the slope miss is
1 point larger here, while the drag agreement is better (mean 5.7 % against 8.0 %) and again changes
sign at the top of the range. The bias flags of decision 8 now carry both Reynolds numbers
automatically (`v6e:cl_alpha:Re305200=+6.4%:fail`, `v6e:cd_ratio:Re305200=+5.7%:pass`), because they
are read from the record and not typed. Decision 8 stands as ruled: the high level is accepted WITH
the bias, and nothing here changes a tolerance or a model parameter. The ten E387 cases are the whole
V6e set the spec asked for except the medium-against-fine row, which stays blocked on the mesher.

### Decision 8 (Éder, 2026-11-08 22:35 UTC): "accept the medium mesh as the high level with the bias recorded"

The medium-mesh SA-BCM SU2 polar is the high level of the two-level study, accepted WITH the V6e
miss and not instead of it. The V6e row stays a **fail** in `runs/drone/validation/2026-11-08/v6.json`
and in the validation document; nothing is re-tolerated and no model parameter moves. What changes
is how the bias travels: `analysis/high_level_bias.py` reads the toleranced V6e rows out of the
recorded validation run (never a typed literal) and `analysis/drone_polar.polar` appends them to
the flags of EVERY SU2 section polar it returns, as `v6e:cl_alpha:Re203800=+5.5%:fail`,
`v6e:cd_ratio:Re203800=+8.0%:pass` and `v6e_ruling=decision8_accepted_with_bias`, so every design
evaluated through `analysis/drone_design.py` carries the miss in its own record. When the Re 305,200
rows land (queued) they join the same flags automatically. Two tests pin it
(`tests/task10/test_validation_e387.py`, decision-8 block): the flag text must equal the record's own
deviation and verdict, and a record with no toleranced V6e row is refused rather than silently
flagged clean. The consequence for the deliverable: every high-level number in the report and the
deck is quoted with "SU2 lifts 8.0 to 11.6 % high and its drag runs 10.3 % low to 1.6 % high against
the E387 tunnel at Re 203,800", and the two-level model's correction term absorbs a KNOWN bias rather than an unknown
one — which is the measurable thing the multi-fidelity analysis (T10.10c) now has to show. Also
recorded: the fine-mesh row of V6e stays `not run` and is blocked on the mesher (8 inverted cells),
not on Colab time.

### T10.10a and T10.10d on the LOW pool, recorded as diagnostics (Fable, 2026-11-09 00:40 UTC)

Three low-fidelity records, run so that the analyses exist end to end before the SU2 pool lands;
none of them is a study answer, because the questions are asked of the high level.

- `runs/drone_pareto_lf/2026-11-09/`: `analysis.pareto --family drone` on the 192-point low pool —
  4,096 gate-checked Sobol candidates (420 of 4,544 failed the closed-form gates, 4 the full gates),
  observed front of 15 designs from 3.47 h at 0.953 kg to 11.71 h at 2.283 kg, a 57-point predicted
  front and a 25-level band; the two most sensitive inputs by GP lengthscale are `aspect_ratio` and
  `span_m`, which is the design map's pair.
- `runs/drone_inverse_lf/2026-11-09/`: `analysis.inverse --family drone`, 21^6 = 85,766,121 grid
  points walked in chunks, 76,587,147 passing the closed-form gates, cap 4.0 kg at P ≥ 0.9. **The
  answer is a box corner**: span 3.0 m, aspect ratio 16, taper 0.3, battery fraction 0.45, camber
  6 %, thickness 8 % — ALL SIX inputs at a bound (this first said five; corrected 2026-11-09, caught by the deck builder reading inverse.json) — predicted 13.307 h (90 % interval
  [13.228, 13.386]) at a median 2.435 kg, P(mtow ≤ 4) = 1.000, closure gates passed. Evaluated
  directly on the low model the design gives **13.245 h and 2.438 kg**, both inside the intervals.
  Two facts travel with it: **the 4 kg cap never binds on the low model** (every one of the 192 pool
  designs is under 2.5 kg; the lightest is 0.953 kg), so the low-fidelity answer is simply the
  longest-endurance buildable corner and question 4 is only tested by the high level; and the GP is
  **extrapolating to the box edge**, since the Sobol pool has no point at the bounds.
- `runs/drone_bias_lf/2026-11-09/`: the one-at-a-time sweep of all 21 banded ledger quantities at
  that design, ranked by max |% endurance|: skin areal density (+13.0 / −17.2 % endurance,
  −27.2 / +62.0 % mtow), propulsive efficiency (±17.0 %), pack specific energy (±16.7 %), payload
  mass (+7.3 / −12.7 %), depth of discharge (±12.6 %), section lift effectiveness (−8.6 / +4.7 %),
  tail arm (−4.1 / +5.3 %), section stall angle (−4.1 / +3.0 %); everything else under 2 %, and four
  quantities have no effect at this design (installed power margin, cruise cl fraction, static
  margin target, turbulence intensity — read but not binding). Spec section 10 item 5 asks for this
  sweep at the inverse answer, which is this corner on the low model; it is re-run at the SU2 answer
  when that exists.

## Questions for Éder (answered above; kept as the record)

1. **Airfoil family.** The spec varies the NACA four-digit section per design, which is what makes
   the SU2 polar a per-design cost and gives active learning something to save. The alternative is
   one fixed catalogue airfoil (E387 or SD7037) with its UIUC polar interpolated in Reynolds number:
   no CFD per design, a cheaper study, and the high level becomes one SU2 validation table rather
   than a pool. Default: NACA per design, as specified.
2. **Payload and cap.** 0.5 kg payload and the 4.0 kg class C2 cap. The 25 kg class C3 limit would
   make a larger aircraft and change the bounds. Default: as specified.
3. **Colab budget.** The SU2 pool is 480 cases, 24 to 80 worker-hours at inlet-pool speeds. Is a
   worker running for three days acceptable, or should the pool be cut to 64 designs from the start?
   Default: measure the first design, cut to 64 if it costs more than 15 minutes.
4. **Deliverable.** A separate deck for a different audience, or a section added to the inlet deck?
   Default: a separate deck, decided after the results exist.
5. **Start date.** Nothing starts before the talk on 2026-11-13. Default: T10.1 to T10.3 start on
   2026-11-14.

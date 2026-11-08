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

## Questions for Éder (defaults assumed until answered)

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

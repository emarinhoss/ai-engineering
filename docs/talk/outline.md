# Talk outline: aero-thermal inlet design, surrogate and automation

Slide-by-slide outline for the 40-minute talk (plus 20 minutes of discussion), following the seven
sections of `PLAN.md`, Task 7. Status as of 2026-11-02 (first written 2026-11-01). every
quantitative claim is either backed by a record named in the Source line or marked PENDING.

## Conventions

- **Source** is an existing file under `runs/` or `docs/validation/`, or `PENDING:` followed by the Colab
  batch that will produce it: `validation batch` (Task 2 official records), `pool batch` (Task 3 pool, 92
  runnable points, and the replay and surrogate outputs built on it), or `confirmation run` (the SU2 check of
  the inverse-query answer, Task 5). A slide with no number says `none (no number)`.
- **Analytic reference values** (two-shock, Eckert, Fay-Riddell, flight condition) are formulas in
  `docs/specs/00_decisions.md`. A slide shows one only with the run record that compares it, or PENDING.
- **Deviations (flagged in place):** S12 cites `docs/transcripts/`, because no `runs/` record of an agent
  call exists. B1 and S22 point to the Spalart-Allmaras sensitivity run, which is not yet assigned to a batch
  (marked `validation batch (to add)`). The fault-injection runs of Task 6 have no batch yet (marked
  `PENDING: no batch yet`).
- **Speaker notes** are at most three sentences each.
- **Spelling** is standard US English on every slide, caption, figure label and speaker note.

## Timing

`PLAN.md` Task 7 first gave six talk sections of 5, 10, 8, 12, 8 and 5 minutes, 48 in all. On 2026-11-02 Éder fixed the talk at **40 minutes** (4, 9, 6, 9, 7, 5) with 20 minutes of discussion. Later the same day Éder asked for a background slide with the questions the study answers (S1a); to keep 40 minutes, section 1 went to 5 minutes and section 3 to 5 (5, 9, 5, 9, 7, 5). On 2026-11-04 the Task 9 section (5b, the three-ramp inlet over a flight envelope, 5 minutes) was added as its spec fixed: the time comes from section 5 (S17 and S20 moved to backup, 7 to 4 minutes) and section 6 (S23 moved to backup and S21 shortened, 5 to 3 minutes), so the talk stays at 40 minutes (5, 9, 5, 9, 4, 5, 3). On 2026-11-07 Éder asked for slides on the benefits of the gated process and on why MCP (S1b to S1d, 2.5 minutes, right after the title slide); the time comes from section 3 (5 to 3 minutes, because S1b to S1d now carry the motivation and S9 to S12 are shortened) and from S1a (1.5 to 1 minute), so the talk stays at 40 minutes (0.5 title, 2.5, 4, 9, 3, 9, 4, 5, 3). `PLAN.md` carries the same minutes and the slide times below are the ones to rehearse.

| Section | Talk | PLAN.md minutes | Outline minutes | Slides |
|---|---|---|---|---|
| Title | - | - | 0.5 | S1 |
| 1a. Why a gated, automated process | - | - | 2.5 | S1b to S1d |
| 1. Problem and why it matters | 1 | 5 | 4 | S1a, S2, S3 |
| 2. Physics setup and validation | 2 | 10 | 9 | S4 to S8 |
| 3. Automation layer: MCP tools, gates, queue | 3 | 8 | 3 | S9 to S12 |
| 4. Surrogate, active learning, UQ | 4 | 12 | 9 | S13 to S16 |
| 5. Results, Pareto front, inverse query | 5 | 8 | 4 | S18, S19 |
| 5b. Six inputs over a flight envelope (Task 9) | - | 5 | 5 | S20a to S20d |
| 6. What failed, limits, next steps | 6 | 5 | 3 | S21, S22 |
| 7. Discussion (outside the 40 minutes) | - | about 20 | 20 | S24 |

Backup slides B1 to B9, then S17, S20 and S23 (moved there on 2026-11-04), follow S24 and are not timed.

---

## Title (0.5 minutes)

### S1. Title (0:00, 0.5 min)

- **Message:** A physics-ML engineer who automates his own workflow.
- **Figure or table:** Title card only.
- **Source:** none (no number)
- **Speaker notes:** The talk covers a supersonic inlet, an active-learning surrogate and a thin agent layer, in that order of importance. The agent layer is convenience; the physics and the statistics are the substance.

## Section 1a: Why a gated, automated process (2.5 minutes)

### S1b. A clean exit is not a correct result (0:30, 1 min)

- **Message:** A tangled mesh cell ran to convergence in SU2 with exit code 0 and a body heat load 3.6 percent too high, so the checks have to sit before the solver.
- **Figure or table:** Bar chart of the change in body heat load against the clean control for R1, R7 and R7b, and a four-box flow: tangled cell, mesh-quality gate, SU2, heat load.
- **Source:** `docs/faults/README.md` (findings R1, R7 and R7b); `runs/faults/2026-11-03/R0/observed.json`, `R7/observed.json` and `R7b/observed.json` (body heat load 4718.25 and 4887.01 W/m; 1078 iterations against 672).
- **Speaker notes:** SU2 printed one line about re-orienting an element, converged, exited with code 0, and the heat load was 3.6 percent high. Only the mesh-quality gate stops this, and the worker never runs a mesh it did not build and check itself. That is why the checks sit before the solver and not after it.

### S1c. What stopped each injected fault (1:30, 1 min)

- **Message:** Each injected fault was stopped by the earliest layer that could see it; the orange rows reached the solver because a layer was missing or bypassed.
- **Figure or table:** Matrix of 17 faults against seven layers (schema, physics gates, mesh quality, config keys, worker checks, ingest checks, SU2 itself), one marker per fault, with a note on what happened.
- **Source:** `docs/faults/fault_matrix.md` (fake solver); `docs/faults/real_fault_matrix.md` (SU2 v8.2.0); `docs/faults/README.md` (6 of 84 retyped results wrong at the first attempt and caught by the digest; R9 diverged after 449.5 s and R9g was refused in 0.0 s).
- **Speaker notes:** Every row comes from a test or a run in the repository, and the two orange rows are the honest part. R9 shows a gap that the faults found: a hand-made job skipped the gates and diverged after 449.5 s, and the worker now refuses it in 0.0 s. R7b is the case where only the mesh gate helps.

### S1d. Why MCP, and what it does not add (2:30, 0.5 min)

- **Message:** MCP is one guarded door to checks that the worker repeats; the gates and checksums are plain code, and the agent never chooses a point.
- **Figure or table:** Two-row schematic (the MCP tools, and a hand-made job through the worker) sharing one gate function, and a two-column table of what MCP adds and what does not depend on it.
- **Source:** `docs/faults/real_fault_matrix.md` (R9, R9g); `docs/transcripts/2026-11-03_mcp_input_faults.md` (the first three calls refused for a missing tag); `docs/transcripts/2026-11-01_first_mcp_call.md` (ten rows, nothing chosen).
- **Speaker notes:** A script with the same validation would give the same gates and checksums, so MCP is a convenience layer: one entry point, typed arguments and a log of every call. The schema did catch the agent's own mistake, three calls without the required tag. The evidence is small, because we injected the faults and the live call listed ten rows and chose nothing.

---

## Section 1: Problem and why it matters (4 minutes)

### S1a. The questions this study answers (3:00, 1 min)

- **Message:** Five questions drive the study, each answered on a later slide, and the same loop applies to any validated simulator with a few inputs and competing outputs.
- **Figure or table:** Left: table of the five questions (design trade, inverse design, sampling cost, trust, automation) with the slide that answers each. Right: where the same loop applies, labeled "not run in this study", and what transfers and what does not.
- **Source:** none (no number). Questions from `PLAN.md` (Framing, Problem) and `docs/specs/00_decisions.md`, section 3; the application examples are illustrations of the method, not results.
- **Speaker notes:** Pressure recovery sets how much useful air the engine gets, and wall heating sets the cooling and thermal-protection load, so the designer needs the trade between them, not one number. Each CFD run is expensive, so the real question is how few runs answer these questions with an uncertainty you can check. The physics is specific to this inlet, but the loop of validated solver, gates, surrogate with uncertainty and acquisition is not.

### S2. The design question (4:00, 1.5 min)

- **Message:** The inlet trades total pressure recovery against peak wall heating, and neither objective alone is a design.
- **Figure or table:** Schematic of the two-ramp inlet with cowl, throat plane and the two objectives marked (to draw from `geometry/inlet.py`; no data).
- **Source:** schematic: none (no number), definitions in `docs/specs/00_decisions.md`, sections 2 and 3. Schlieren: `runs/dev/2026-11-02_flow_fields/figures/inlet_8_8_schlieren.png` from the development run `runs/dev/2026-11-02_flow_fields/inlet2r-92352faad1` (laminar 8/8, medium mesh, volume output; same metrics as the Colab record `runs/val/inlet2r-d4d29884be`).
- **Speaker notes:** Recovery includes the terminal normal shock, which is what makes external compression worth anything. Peak heating is taken on ramp 2 including the duct wall, not on the sharp leading edge, where the computed peak is a mesh artifact.

### S3. The design box (5:30, 1.5 min)

- **Message:** Two ramp angles, theta1 and theta2, set the geometry, and the box is trimmed to 24 deg total turning on evidence.
- **Figure or table:** Design-box diagram in the (theta1, theta2) plane, with the trimmed corner shaded and the 4 excluded pool points marked (to draw from `designs/pool_sobol96.csv`).
- **Source:** `runs/dev/2026-11-01_inlet_box_diagnostics/README.md` (trim and the four excluded indices). Box bounds are inputs from `docs/specs/00_decisions.md`, section 2.1.
- **Speaker notes:** The cowl position is not a design variable, because with these two objectives the Pareto set would sit on its bound. Wall temperature is a boundary condition, not a design choice, and the reasons are in the decisions file.

---

## Section 2: Physics setup and validation (9 minutes)

### S4. Flight condition and why laminar (7:00, 1.5 min)

- **Message:** Mach 4 at 30 km for a sub-scale body keeps the flow laminar, and we state that as an argument, not a measurement.
- **Figure or table:** Table of inputs: Mach 4.0, freestream temperature 226.509 K, isothermal 300 K wall, sub-scale body of about 0.3 m.
- **Source:** `runs/dev/2026-11-01_numerics/wedge-381c48d17f/case.cfg` (Mach, freestream temperature and wall temperature). The 30 km and 0.3 m values are from `docs/specs/00_decisions.md`, section 1. The transition argument has no run record: `PENDING: no run record`. It is an analytic estimate from `docs/specs/00_decisions.md`, section 1.1, and no number from it is quoted here.
- **Speaker notes:** Mach 5 was rejected on analytic grounds, not by a run. The laminar choice is a sub-scale, high-altitude condition; a full-scale vehicle would need RANS, and B1 covers the one sensitivity run planned for that.

### S5. The validation ladder (8:30, 1.5 min)

- **Message:** Analytic checks run before any machine learning; hard checks must pass, soft and report checks are reported.
- **Figure or table:** The tolerance table (hard, soft, report) with the verdict column filled from the report.
- **Source:** `docs/validation/2026-11-01_report.md` (verdict column; development runs unless a row says official). The V3 Billig stand-off row, "not run" in the report, was run on 2026-11-02 with volume output: +5.6 percent (`runs/dev/2026-11-02_flow_fields/cylinder-04b6b912c5/standoff.json`).
- **Speaker notes:** A hard failure means a bug in mesh, boundary condition, units or scheme, so we fix the cause and do not change the tolerance. The verdicts are shown as the report gives them, including the one that failed.

### S6. Oblique shock and laminar heating (10:00, 2 min)

- **Message:** The Euler wedge matches the oblique-shock relation within the hard tolerances, and the laminar wedge heating matches the Eckert flat-plate reference within the window.
- **Figure or table:** `docs/validation/2026-11-01_wedge_heat_flux.png`, with a V1 table beside it.
- **Source:** `runs/task1/README.md` and `runs/task1/v1_oblique_shock.json` (V1 and V2a, official). `docs/validation/2026-11-01_report.md` (V2b, development, final numerics).
- **Speaker notes:** The V1 check is the official Colab record, so it is the one to quote for the solver setup. The V2b check is a development run with the final numerics; the entropy-fix change moved its deviation, and B4 shows the comparison.

### S7. The cylinder: the hard check failed first (12:00, 2 min)

- **Message:** With the first numerics (Roe, entropy fix 0.1) the stagnation heating failed Fay-Riddell on the fine mesh; with entropy fix 0.3 it passes on that mesh.
- **Figure or table:** `docs/validation/2026-11-01_cylinder_heat_flux.png` (heat flux by mesh level) and `runs/dev/2026-11-02_flow_fields/figures/cylinder.png` (bow shock, Mach contours, measured stand-off against Billig; the grid-study figure moved to B3).
- **Source:** `docs/validation/2026-11-01_report.md` (V3 rows and grid study); `runs/dev/2026-11-01_cylinder_v3_attempt1/README.md` (the failure); `runs/dev/2026-11-01_cylinder_v3_attempt3/README.md` (the final numerics); `runs/dev/2026-11-02_flow_fields/cylinder-04b6b912c5/standoff.json` (stand-off delta/R = 0.546 against Billig 0.517, +5.6 percent, report tolerance 15 percent; development run 2026-11-02).
- **Speaker notes:** The failure was kept and not tuned away, and the fix was chosen from a six-scheme comparison and a split test. The grid study passes on two levels only, so no order of convergence is claimed.

### S8. Inlet design point at 8/8 (14:00, 2 min)

- **Message:** At the design point the inviscid throat matches the two-shock relations within the hard tolerance, and the laminar core is within the soft band.
- **Figure or table:** `docs/validation/2026-11-01_inlet_throat_p0.png` with the V4e and V4v rows.
- **Source:** `runs/dev/2026-11-01_inlet_design_point/README.md` (development run); `docs/validation/2026-11-01_report.md` (V4e and V4v rows).
- **Speaker notes:** This is a development run, not the official Task 2 record, which comes from the validation batch. The laminar core is a soft check, and the boundary-layer loss is shown beside it rather than hidden.

---

## Section 3: Automation layer: MCP tools, gates, queue (3 minutes)

### S9. The pipeline on one slide (16:00, 1 min)

- **Message:** A design passes the schema, the physics gates and the mesh gate before SU2 sees it, and the LLM sits outside this chain.
- **Figure or table:** Flow diagram: parameters, schema, gates, mesh quality, config, Drive queue, Colab worker, SU2, result or error, metrics, surrogate, acquisition.
- **Source:** none (no number). Interfaces are in `docs/specs/01_interfaces.md`.
- **Speaker notes:** Each step is a function a person can read, and each gate fails with the offending value. The language model calls typed tools and never picks a sampling point.

### S10. Gates reject before any CFD (17:00, 0.5 min)

- **Message:** The gates stop a design that would not converge, and the design box was trimmed on that evidence.
- **Figure or table:** Table of the box diagnostics: 12/12, 8/14 and 5/14 converged; 12/14 diverged on both meshes and with both CFL caps.
- **Source:** `runs/dev/2026-11-01_inlet_box_diagnostics/README.md`; `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md` (12/14 diverged on both meshes).
- **Speaker notes:** The 26 deg corner diverged, so the gate rejects total turning above 24 deg, and four of the 96 pool points are excluded. The 25 deg band was not tested, and any pool point near the limit that fails is recorded as a failure.

### S11. Queue over Google Drive and a restart-safe worker (17:30, 1 min)

- **Message:** Colab cannot take inbound connections, so jobs go through a Drive folder, and a restarted worker resumes without losing or repeating finished runs.
- **Figure or table:** Queue folder diagram: `jobs/`, `runs/<id>/status/` flags, `result.json` and `error.json`.
- **Source:** `docs/transcripts/2026-11-02_worker_restart_and_retry.md` (the worker on Colab restarted with `--retry-reason config_mismatch` on 2026-11-02 and re-ran the 63 refused pool jobs without repeating the 29 finished ones; all 92 pool points converged, `docs/validation/2026-11-01_colab_records.md`); `docs/faults/fault_matrix.md` row F8 (killed worker, local test with the fake solver).
- **Speaker notes:** The worker never decides physics; it rebuilds the mesh from the uploaded parameters and checks a fingerprint before it runs SU2. Failure reasons come from a fixed list, so a failed job always says why.

### S12. The first live agent call (18:30, 0.5 min)

- **Message:** The agent reads the queue through a typed tool and answers from flag files and result records; it chose no sampling point.
- **Figure or table:** The `list_results` output from the first live call, reproduced from the transcript (ten rows, all pending at that time).
- **Source:** `docs/transcripts/2026-11-01_first_mcp_call.md`. **Deviation:** a transcript, not a `runs/` record; the claim is limited to what the tool returned.
- **Speaker notes:** This is a convenience layer over validated tools, and the transcript shows what the tool read and what it did not choose. The faults injected through real SU2 (B9) found two gaps in the worker, both now guarded.

---

## Section 4: Surrogate, active learning, UQ (9 minutes)

### S13. One exact Gaussian process per objective (19:00, 2 min)

- **Message:** With two inputs and a small number of runs, an exact Gaussian process gives calibrated intervals from its posterior, and it needs no GPU.
- **Figure or table:** Diagram: two inputs, one GP per objective, predicted mean and interval for each output.
- **Source:** none (no number). Specification: `docs/specs/task4_surrogate_active_learning.md`.
- **Speaker notes:** The model is pure PyTorch with a Matern 5/2 kernel with automatic relevance lengths, fitted by marginal likelihood. The Colab GPU is not needed, and we say so rather than suggest otherwise; deep ensembles are the alternative for high-dimensional inputs.

### S14. Acquisition, and who chooses (21:00, 2 min)

- **Message:** Expected hypervolume improvement picks the next run, a max-variance rule is the control, and the LLM chooses nothing.
- **Figure or table:** Schematic of candidate scores over the box, with the selected point marked (no data).
- **Source:** none (no number). Specification: `docs/specs/task4_surrogate_active_learning.md`.
- **Speaker notes:** Both rules are deterministic given a seed, so every run can be reproduced from its record. The max-variance rule is in the comparison so that the audience can see what the hypervolume term adds.

### S15. Active learning against random and Latin hypercube (23:00, 2.5 min)

- **Message:** On the same pool, EHVI finds the Pareto front fastest and max-variance learns the whole box fastest; active learning beats random and Latin hypercube on the objective it targets, not on global error, and both are shown.
- **Figure or table:** Held-out error against number of runs for al_ehvi, al_maxvar, random and LHS, with bands over 10 seeds.
- **Source:** `docs/validation/2026-11-02_replay_full_error_vs_n.png`, `docs/validation/2026-11-02_replay_full_summary.md`, `docs/validation/2026-11-02_replay.md` (final replay on all 92 pool points, 10 seeds, n = 8 to 48). EHVI has the lowest hypervolume regret at every budget after the shared 8-point start and 0 regret in 10 of 10 seeds from n = 32 (the 26-point true front is contained), while no other strategy reaches 0 by n = 48; on held-out error it is the worst strategy from n = 12 to 32 and overtakes random and LHS only at n = 40; max-variance has the lowest held-out error from n = 16 on (LHS at n = 12).
- **Speaker notes:** Every strategy uses the same pool, so the ground truth is shared and no extra CFD is needed. If active learning does not beat the baselines, the slide says so and the next step is to investigate, not to retune.

### S16. Calibration (25:30, 2.5 min)

- **Message:** The 90 percent intervals should cover about 90 percent of held-out points, and coverage outside 80 to 97 percent is flagged.
- **Figure or table:** Calibration plot: nominal against observed coverage on held-out points.
- **Source:** `docs/validation/2026-11-02_replay_full_calibration.png`, `docs/validation/2026-11-02_replay.md` (final, 92 pool points, n = 48, 44 held-out points). q_peak coverage is inside the band (0.84 to 0.91 at the 90 percent level); recovery is over-covered (1.0 at the 90 percent level for every strategy), which is flagged and explained, not refitted. The 80 to 97 percent flag band is the report tolerance C1 in `docs/specs/00_decisions.md`, section 5.
- **Speaker notes:** Coverage is the check that the uncertainty means something, and it is reported whatever it shows. A flagged result gets an explanation, not a refit.

---

## Section 5: Results, Pareto front, inverse query (4 minutes)

### S18. Pareto front with uncertainty (28:00, 2 min)

- **Message:** Observed points, the predicted front, the posterior band and the discretization error bar, shown together, say how far the front can be trusted.
- **Figure or table:** Front plot from `analysis/pareto.py`: observed points, predicted front, posterior band, discretization error bar.
- **Source:** `runs/analysis/2026-11-02/pareto_front.png`, `runs/analysis/2026-11-02/pareto.csv`, `docs/validation/2026-11-02_pareto_inverse.md`, section 2: 26 observed front points of 92; posterior band 1.2e-4 to 1.8e-3 wide in recovery; discretization bar 3.1e-4 in recovery and 530 W/m2 in q_peak (V4m grid study), 25 times the posterior uncertainty in heat flux.
- **Speaker notes:** The band is posterior uncertainty and the error bar is discretization error from the grid study, and both are shown separately. The front is only as good as the mesh levels behind it (B3).

### S19. Inverse query: maximum recovery under a heat-flux cap (30:00, 2 min)

- **Message:** The surrogate answers "highest recovery with peak heat flux under the 40th percentile of pool heating", and one real SU2 run checks the answer.
- **Figure or table:** Table: query, surrogate answer with interval, confirmation run result, and whether it falls inside the interval; schlieren of the confirmed design from `runs/dev/2026-11-02_flow_fields/figures/inlet_confirm_schlieren.png` (development run `runs/dev/2026-11-02_flow_fields/inlet2r-ef324f2106`, same metrics as the Colab confirmation run).
- **Source:** `runs/analysis/2026-11-02/inverse_q40/result.json`, `runs/analysis/2026-11-02/confirm/confirm.json`, `runs/confirm/inlet2r-374dad241f/result.json`, `docs/validation/2026-11-02_pareto_inverse.md`, section 3 (cap 31493 W/m2; answer theta1 = 11.965, theta2 = 7.115; predicted recovery 0.34515, interval 0.34506 to 0.34523, SU2 0.34513, inside; predicted q_peak 31470, interval 31450 to 31490 W/m2, SU2 31462, inside; C2 pass; refit shrinks the predictive std by 10 and 8 percent).
- **Speaker notes:** The cap is set from the pool before the answer is known. The check passes if the confirmation run falls inside the predicted interval; a miss is documented and explained.

---

## Section 5b: Six inputs over a flight envelope (Task 9, 5 minutes)

### S20a. The three-ramp inlet over a flight envelope (32:00, 1 min)

- **Message:** The same workflow, run on a harder case: three ramp angles plus Mach, altitude and wall temperature, 159 laminar NS runs and 316 Euler runs, with the validation gate passed first.
- **Figure or table:** Table of the six inputs and their ranges; pool counts; the V5 verdicts in one line each.
- **Source:** `docs/specs/task9_inlet3r_envelope.md`; `docs/validation/2026-11-03_inlet3r_v5.md` (gate as first specified FAIL: wall-Mach plateaus and the first fine-mesh run; PASS after two recorded changes: plateaus measured off the wall, pressure outlet on the duct); `docs/validation/2026-11-04_task9_report.md` (NS pool 159 points, 152 converged, 7 failed with solver errors; Euler pool 316 points, all converged; 15 NS runs on Colab, 144 on the container).
- **Speaker notes:** The gate failed first, and both failures are in the report with their causes; the two changes were made on that evidence, not to pass. Mach, altitude and wall temperature are inputs the designer does not choose, so this is a design question over an envelope. Seven of 159 NS runs failed; all seven are one numerical start-up failure at the duct outlet, and each converges when the back pressure is applied after 500 iterations at freestream (`runs/dev/2026-11-04_pool3r_startup_diag/README.md`). The pool records stay failed.

### S20b. Active learning in six dimensions (33:00, 1.5 min)

- **Message:** EHVI finds the pool's best trade-offs by 24 runs, where random and LHS are still well short at 96; on surrogate accuracy the active strategies win only from about 80 runs, by a factor of 1.5 to 1.8.
- **Figure or table:** `docs/validation/2026-11-04_task9_replay.png` (held-out error and hypervolume regret against the number of NS runs, five strategies, median and quartiles over 10 seeds).
- **Source:** `runs/pool3r/analysis/replay_s*.csv`, `docs/validation/2026-11-04_task9_tables.md` (section 1), `docs/validation/2026-11-04_task9_report.md` (question 1): hypervolume regret at 24 runs 0.000 (EHVI), 0.047 (max-variance), 0.246 (random), 0.292 (LHS); at 96 runs 0.057 (random), 0.113 (LHS); RMSE recovery at 96 runs 0.0008 (active) against 0.0013 to 0.0014; relative q error 0.007 to 0.008 against 0.013 to 0.014; the pool front has 7 points, all at Mach 3.50 to 3.71.
- **Speaker notes:** The large win has a plain reason that I state with it: the front has only seven points and all sit at the low-Mach end, so it is mostly a front over flight conditions, which a targeted search finds fast. A failed pick costs a run in this replay, and every strategy made about four failed picks by 96 runs. The feasibility factor on EHVI changed nothing measurable, for the reason on S20d.

### S20c. Cheap physics as a first level (34:30, 1.5 min)

- **Message:** A two-level model that starts from Euler plus Eckert reaches with 12 NS runs the heat-flux error that NS alone needs 48 for; for recovery it helps only below about 24 runs, because Euler is already close.
- **Figure or table:** `docs/validation/2026-11-04_task9_mf.png` (held-out error against the number of NS runs, NS only against the two-level model, with the raw low-fidelity error as a line).
- **Source:** `runs/pool3r/analysis/mf.csv`, `docs/validation/2026-11-04_task9_tables.md` (section 2), `docs/validation/2026-11-04_task9_report.md` (question 2): relative q error 0.025 (two-level, 12 runs) against 0.026 (NS only, 48 runs); recovery RMSE 0.0032 (two-level, 12 runs) against 0.0064 (NS only, 12 runs) and 0.0029 (NS only, 24 runs); raw Eckert q off by 0.295, raw Euler recovery off by 0.0047; fitted rho 1.00 to 1.07; 90 percent intervals of the two-level model cover 0.52 to 0.58 at 12 runs.
- **Speaker notes:** Eckert on the Euler wall state is about 30 percent off in level but tracks the NS heating closely, which is exactly what the linear two-level form uses. The model is Kennedy and O'Hagan's autoregressive form: one GP for the cheap level and one for the discrepancy. Its intervals are too narrow at small budgets, so I trust its means there, not its error bars.

### S20d. What did not work: learned feasibility and the robust query (36:00, 1 min)

- **Message:** The convergence classifier does not beat "always converges", and the robust heat-flux query has no feasible design; both are reported as they came out.
- **Figure or table:** Two-row table: classifier (accuracy, baseline, AUC, skipped failures, lost good runs); robust query (cap, envelope points that no design can meet, the worst point).
- **Source:** `runs/pool3r/analysis/feasibility.json`, `runs/pool3r/analysis/inverse/result.json`, `docs/validation/2026-11-04_task9_report.md` (questions 3 and 4): cross-validated accuracy 0.950 against 0.956 for always converges, AUC 0.63, at threshold 0.5 no failure skipped and 1 good run lost; cap 16,081 W/m2 (40th percentile of pool q_peak), no design meets P(q <= cap) >= 0.9 at all 125 envelope points, 22 points cannot be met by any design, worst Mach 4.5, 28 km, 300 K with lowest predicted q 27,202 W/m2.
- **Speaker notes:** Seven failures in 159 runs are too few to learn six inputs, and all seven failures are outflow-boundary start-up numerics (each converges under a two-stage start, to values the surrogate already predicts), so the classifier would learn the solver set-up, not the inlet. The robust query combined a pool-wide cap with a worst case over the envelope, and flight condition moves the heating far more than the ramp angles do. I kept the query as specified and report the null result; no confirmation run was made because there is no design to confirm.

---

## Section 6: What failed, limits, next steps (3 minutes)

### S21. What failed, in order (37:00, 1.5 min)

- **Message:** Five things failed on the way, each was recorded, and each change was made on that evidence.
- **Figure or table:** Table with columns: what failed, what the record shows, what changed.
  Rows: (1) cylinder carbuncle with Roe at entropy fix 0.1; (2) Euler wedge with AUSM+-up2 diverged or stalled; (3) 12/14 corner diverged; (4) the diverged 12/14 surface file was reported as a unit error ("check the units") until a divergence check was put before the cross-check; (5) a pool job was refused by the worker as a config mismatch because one geometry number in a comment line differed in its last digit between the container and Colab (h_duct, 3e-18), so the config hash now covers only the lines SU2 reads.
- **Source:** `runs/dev/2026-11-01_cylinder_v3_attempt1/README.md`; `runs/dev/2026-11-01_numerics/README.md`; `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md`; `docs/faults/README.md` (the "check the units" fix); the config-mismatch failure record of pool job inlet2r-db92dcf68d (`runs/pool/inlet2r-db92dcf68d/error.json` at commit 915f5f8, reason and both hashes; the retried job later converged and its result replaced the record) and `docs/transcripts/2026-11-02_worker_restart_and_retry.md`.
- **Speaker notes:** Failures 4 and 5 are failures of the tooling, not of the physics, and they are the ones an agent layer must surface rather than hide: a wrong message and an over-strict guard. Both are closed with a test.

### S22. Limits of the model (38:30, 1.5 min)

- **Message:** The model is laminar, sub-scale and two-dimensional with two variables, and the corner of the box that does not converge limits what the front means.
- **Figure or table:** List of limits, each with its consequence for the Pareto front.
- **Source:** `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md` (12/14 divergence); `runs/dev/2026-11-01_numerics/README.md` (leading-edge wall temperature); turbulence sensitivity: `runs/sensitivity/` and `docs/validation/2026-11-02_sa_sensitivity.md` (Spalart-Allmaras at 8/8 and 12/12 on Colab, a sensitivity bound).
- **Speaker notes:** A full-scale vehicle at lower altitude would be turbulent, and the talk does not claim a turbulent result. Objective values near sharp leading edges are excluded by construction, not because they were checked.

---

## Section 7: Discussion (about 20 minutes, outside the 40)

### S24. Questions, and where the answers are (40:00 onward, about 20 min)

- **Message:** The discussion is open, and the backup slides answer the fidelity questions.
- **Figure or table:** Index of B1 to B9 and of S17, S20 and S23 (moved to backup on 2026-11-04).
- **Source:** none (no number).
- **Speaker notes:** Start with the limit that matters to the person asking, then open the matching backup slide. Do not quote a number that is not on a slide.

---

## Backup slides (not timed)

### B1. Turbulence model (fidelity question: why laminar?)

- **Message:** Laminar is the model for this sub-scale condition; a Spalart-Allmaras sensitivity run shows what a turbulent layer would change and is labeled as a bound, not a result.
- **Figure or table:** Bar chart of both objectives at 8/8 and 12/12, laminar against Spalart-Allmaras (numbers in the record's table).
- **Source:** `runs/sensitivity/` (Colab, tag sensitivity, solver RANS_SA: 8/8 medium inlet2r-1731bdea74, 8/8 fine inlet2r-8a09596911, 12/12 medium inlet2r-d7e3815b57) and `docs/validation/2026-11-02_sa_sensitivity.md`; the development runs in `runs/dev/2026-11-01_turbulence_sensitivity_SA/README.md` give the same values to every printed digit. Peak heating 2.5 to 2.6 times laminar, throat recovery 0.857 against 0.909 at 8/8, wall y+ median 2.3 (medium) and 1.7 (fine) from the development runs; a sensitivity bound, not a validated turbulent prediction.
- **Speaker notes:** The SA run has no transition model and y+ above 1, so it bounds the effect rather than predicting it. The trade-off keeps its direction; the heating level does not.

### B2. Wall boundary condition (fidelity question: is the wall really at 300 K?)

- **Message:** The isothermal 300 K wall is imposed weakly near a sharp leading edge, and both objectives are placed away from that region.
- **Figure or table:** Wall temperature along the body near the leading edge, from the Tecplot surface output of the wedge run (to plot from `runs/dev/2026-11-01_numerics/wedge-381c48d17f-tecplot/`).
- **Source:** `runs/dev/2026-11-01_numerics/README.md` (wall temperature of 750 K at the tip, 459 K at 0.1 mm, 335 K at 1.3 mm, below 301 K beyond about 30 mm).
- **Speaker notes:** The wall-node temperature departs from 300 K within about 30 mm of the sharp edge, and the heat-flux objective starts at x of 0.1 m on ramp 2, outside that region. The Eckert window agrees within tolerance, which is the evidence that matters for the objective.

### B3. Mesh convergence (fidelity question: is the mesh converged?)

- **Message:** On the 8/8 design, medium-to-fine changes are small for recovery and peak heating; the 12/14 corner has no converged grid study.
- **Figure or table:** `docs/validation/2026-11-01_grid_study.png`, with the three-level table of recovery and peak heat flux.
- **Source:** `docs/validation/2026-11-01_report.md` (grid study section); `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md` (cell counts 19 620, 30 600 and 55 640; values).
- **Speaker notes:** The report leaves the observed order undefined because the changes are too small for a Richardson estimate at this ratio, so no order is quoted. The cylinder grid study at the earlier numerics fails, which is why the final numerics are part of the record.

### B4. The numerics story (fidelity question: why this scheme?)

- **Message:** The numerics were chosen on recorded comparisons: four Euler-wedge variants (A to D), a six-scheme cylinder comparison, and the entropy-fix split.
- **Figure or table:** Table of variants A to D (change, outcome), then the six-scheme table from the cylinder comparison.
- **Source:** `runs/dev/2026-11-01_numerics/README.md` (variants A to D); `runs/dev/2026-11-01_cylinder_v3_attempt2/README.md` (six schemes); `runs/dev/2026-11-01_cylinder_v3_attempt3/README.md` (split and wedge sensitivity).
- **Speaker notes:** Only the entropy fix cured the carbuncle; the CFL cap did not. The entropy fix costs a little on flat-plate heating, and that cost is stated with its number in the attempt 3 record.

### B5. Design-box trim (fidelity question: why 24 degrees?)

- **Message:** The 12/14 corner diverges on two meshes with both entropy fixes and two CFL caps, so total turning is capped at 24 deg.
- **Figure or table:** Design box with converged and diverged points from the box diagnostics, and the four excluded pool indices marked.
- **Source:** `runs/dev/2026-11-01_inlet_box_diagnostics/README.md`; `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md`.
- **Speaker notes:** The trim was made on evidence, and the gate records it; the 25 deg band was never tested. A pool point near the limit that fails is a recorded failure, not a retuned one.

### B6. Full validation table (fidelity question: what did not run?)

- **Message:** Every check in the report is shown, including the ones not run and why.
- **Figure or table:** The verdict table from the report, condensed to the check, type, verdict and records column.
- **Source:** `docs/validation/2026-11-01_report.md`.
- **Speaker notes:** The not-run rows are shown, not hidden: the stand-off check, the 12/14 grid study and the pressure cross-check on some runs. Official and development rows are labeled, and the report says which are which.

### B7. A neural-network ensemble against the GP (question: why a GP and not a neural net?)

- **Message:** On the same replay, an ensemble of five neural networks is 2 to 10 times less accurate than the GP on held-out designs, but EHVI driven by it still finds the whole front by 32 runs.
- **Figure or table:** `docs/validation/2026-11-02_replay_gp_vs_mlp.png` (GP solid, ensemble dashed: held-out error of both objectives and hypervolume regret against n), with a short table at n = 48.
- **Source:** `runs/replay/2026-11-02_mlp/replay.csv`, `docs/validation/2026-11-02_replay_mlp.md`, `docs/validation/2026-11-02_replay_gp_vs_mlp.md`; settings fixed in `docs/specs/task4b_mlp_ensemble.md` before the run. Recovery RMSE at n = 48: 1.27e-4 against 2.26e-5 (lhs); zero regret for EHVI in 10 of 10 seeds from n = 32 with both models; EHVI step 6.2 s against 1.7 s.
- **Speaker notes:** The ensemble was not tuned, by rule, so this answers the question for this problem only: with two inputs and under fifty smooth samples, the GP's prior wins on accuracy and cost. The front-finding result does not depend on the surrogate, which is the stronger statement. B8 tests a neural operator on the 92 wall heat-flux profiles, where the output is a function.

### B8. A neural operator for the heat-flux profile (question: why not predict the whole profile?)

- **Message:** A Fourier neural operator predicts the whole ramp-2 heat-flux profile about 3 times more accurately than PCA plus GP, but the scalar GP still predicts the peak 7 times better than the operator.
- **Figure or table:** `docs/validation/2026-11-02_operator.png` (four held-out profiles with both models, and the error distributions), with a short table of medians.
- **Source:** `runs/profiles/2026-11-02/operator_compare.csv`, `docs/validation/2026-11-02_operator_profiles.md`, `runs/profiles/2026-11-02/pca_floor.csv`; settings fixed in `docs/specs/task4c_operator_profiles.md` before the run. Median relative L2 error with all data: 0.11 percent (FNO) against 0.32 percent (PCA plus GP); peak error 0.013 percent (scalar GP), 0.092 percent (FNO), 0.18 percent (PCA plus GP); fit 1030 s against 4.7 s.
- **Speaker notes:** All 92 pool cases were re-run on the container to recover the wall profiles, and every one matched its Colab record. The PCA plus GP error equals its three-component truncation floor, so the FNO margin comes from the 99.9 percent rule fixed in the spec; more components were not run. For the design objective the scalar GP remains the right tool; the operator adds where the peak sits and the shape of the whole load.

### B9. Faults through real SU2 (question: what happens when the solver fails?)

- **Message:** With the real SU2 binary the worker recorded every solver failure; the injected faults also found two gaps in the worker, both now guarded, and showed that SU2 silently accepts a tangled mesh.
- **Figure or table:** Table of the real-SU2 faults R1 to R9: what was injected, what happened, what was done.
- **Source:** `docs/faults/real_fault_matrix.md` (generated from `runs/faults/2026-11-03/*/observed.json`), `docs/faults/README.md`, spec `docs/specs/task6b_real_su2_faults.md`, guards tested in `tests/test_worker_guards.py`. R9: 4347 iterations, 450 s, last history line equal to `runs/dev/2026-11-01_inlet_grid_study_ef03/12_14_medium`; R7b heat load 4887.01 against 4718.25 W/m.
- **Speaker notes:** The solver failures we planned for were all recorded with a reason, including a kill and a timeout. The useful results were the ones nobody planned: a hand-made job skipped the gates and burned a solver slot, and a dead worker left its solver running so a restart put two in one folder; both are now guarded and tested. The tangled-mesh run shows why the mesh gate exists: SU2 converged to a wrong answer without a warning.

### S17. The pool across the box (moved to backup on 2026-11-04)

- **Message:** The 92 runnable points span the trimmed box, and their objective values are the ground truth for every comparison.
- **Figure or table:** Scatter of theta1 against theta2, colored by recovery and by peak heat flux (design map).
- **Source:** `runs/analysis/2026-11-02/design_map.png` (panel "observed runs", 92 points), `runs/pool/results.csv` (92 converged, 0 failed), `docs/validation/2026-11-01_colab_records.md`. The 4 of the 96 Sobol points in `designs/pool_sobol96.csv` with theta1 + theta2 > 24 deg were refused by gate 4 and never staged.
- **Speaker notes:** Only converged and stationary runs enter the surrogate, and each point keeps its status. Points rejected by a gate are listed as excluded, not dropped.


### S20. Design maps over the box (moved to backup on 2026-11-04)

- **Message:** Design maps show recovery and heat flux over the trimmed box, with the surrogate and the observed points on top.
- **Figure or table:** Map output from `analysis/design_map.py`.
- **Source:** `runs/analysis/2026-11-02/design_map.png`, `runs/analysis/2026-11-02/oswatitsch_cut.png`, `runs/analysis/2026-11-02/grid.csv`, `docs/validation/2026-11-02_pareto_inverse.md`, section 4 (recovery std 1.8e-5 to 1.1e-4 over the box; GP mean 0.0008 to 0.0022 above the inviscid analytic curve along the Oswatitsch cut, explained from the recorded throat Mach).
- **Speaker notes:** The maps show where the trade-off bends for an aerodynamics audience. They are interpolations between runs and are labeled that way.


### S23. What is still to be recorded (moved to backup on 2026-11-04)

- **Message:** The official validation batch, the fault matrix, the turbulence sensitivity on Colab, the 92-point pool, the replay, the Pareto analysis, the confirmation run and the faults through real SU2 are all recorded; nothing on the talk's list is pending.
- **Figure or table:** Status table: done, running, pending, each with its record.
- **Source:** `docs/validation/2026-11-01_report.md` (development runs); `docs/validation/2026-11-01_colab_records.md` (official validation batch: V3, V4m, V4e metrics form, X1, and the two 12/14 failures); `docs/faults/fault_matrix.md` (fault injection, run without SU2); `docs/faults/real_fault_matrix.md` (faults through real SU2, 2026-11-03). Done rows added on 2026-11-02: `docs/validation/2026-11-01_colab_records.md` (92 of 92 pool points converged, 0 failures), `docs/validation/2026-11-02_replay.md`, `docs/validation/2026-11-02_pareto_inverse.md`. Confirmation run: `runs/confirm/inlet2r-374dad241f/`, `runs/analysis/2026-11-02/confirm/confirm.json` (C2 pass). Spalart-Allmaras on Colab: `runs/sensitivity/`, `docs/validation/2026-11-02_sa_sensitivity.md`.
- **Speaker notes:** Every item on the list has a record in the repository. The talk claims nothing beyond what those records show.


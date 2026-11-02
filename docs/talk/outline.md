# Talk outline: aero-thermal inlet design, surrogate and automation

Slide-by-slide outline for the 40-minute talk (plus 20 minutes of discussion), following the seven
sections of `PLAN.md`, Task 7. Status as of 2026-11-01. Nothing here is a result yet; every
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

## Timing

`PLAN.md` Task 7 gives six talk sections of 5, 10, 8, 12, 8 and 5 minutes. Those add to **48 minutes**, not the
"about 40 talk" the same section states. This outline uses **40 minutes** (4, 9, 6, 9, 7, 5) and keeps the
discussion at 20 minutes. Which sections to shorten is a decision for Éder and Fable 5.1 before rehearsal (Task 8).

| Section | Talk | PLAN.md minutes | Outline minutes | Slides |
|---|---|---|---|---|
| 1. Problem and why it matters | 1 | 5 | 4 | S1 to S3 |
| 2. Physics setup and validation | 2 | 10 | 9 | S4 to S8 |
| 3. Automation layer: MCP tools, gates, queue | 3 | 8 | 6 | S9 to S12 |
| 4. Surrogate, active learning, UQ | 4 | 12 | 9 | S13 to S16 |
| 5. Results, Pareto front, inverse query | 5 | 8 | 7 | S17 to S20 |
| 6. What failed, limits, next steps | 6 | 5 | 5 | S21 to S23 |
| 7. Discussion (outside the 40 minutes) | - | about 20 | 20 | S24 |

Backup slides B1 to B6 follow S24 and are not timed.

---

## Section 1: Problem and why it matters (4 minutes)

### S1. Title (0:00, 0.5 min)

- **Message:** A physics-ML engineer who automates his own workflow.
- **Figure or table:** Title card only.
- **Source:** none (no number)
- **Speaker notes:** The talk covers a supersonic inlet, an active-learning surrogate and a thin agent layer, in that order of importance. The agent layer is convenience; the physics and the statistics are the substance.

### S2. The design question (0:30, 1.5 min)

- **Message:** The inlet trades total pressure recovery against peak wall heating, and neither objective alone is a design.
- **Figure or table:** Schematic of the two-ramp inlet with cowl, throat plane and the two objectives marked (to draw from `geometry/inlet.py`; no data).
- **Source:** none (no number). Definitions are in `docs/specs/00_decisions.md`, sections 2 and 3.
- **Speaker notes:** Recovery includes the terminal normal shock, which is what makes external compression worth anything. Peak heating is taken on ramp 2 including the duct wall, not on the sharp leading edge, where the computed peak is a mesh artefact.

### S3. The design box (2:00, 2 min)

- **Message:** Two ramp angles, theta1 and theta2, set the geometry, and the box is trimmed to 24 deg total turning on evidence.
- **Figure or table:** Design-box diagram in the (theta1, theta2) plane, with the trimmed corner shaded and the 4 excluded pool points marked (to draw from `designs/pool_sobol96.csv`).
- **Source:** `runs/dev/2026-11-01_inlet_box_diagnostics/README.md` (trim and the four excluded indices). Box bounds are inputs from `docs/specs/00_decisions.md`, section 2.1.
- **Speaker notes:** The cowl position is not a design variable, because with these two objectives the Pareto set would sit on its bound. Wall temperature is a boundary condition, not a design choice, and the reasons are in the decisions file.

---

## Section 2: Physics setup and validation (9 minutes)

### S4. Flight condition and why laminar (4:00, 1.5 min)

- **Message:** Mach 4 at 30 km for a sub-scale body keeps the flow laminar, and we state that as an argument, not a measurement.
- **Figure or table:** Table of inputs: Mach 4.0, freestream temperature 226.509 K, isothermal 300 K wall, sub-scale body of about 0.3 m.
- **Source:** `runs/dev/2026-11-01_numerics/wedge-381c48d17f/case.cfg` (Mach, freestream temperature and wall temperature). The 30 km and 0.3 m values are from `docs/specs/00_decisions.md`, section 1. The transition argument has no run record: `PENDING: no run record`. It is an analytic estimate from `docs/specs/00_decisions.md`, section 1.1, and no number from it is quoted here.
- **Speaker notes:** Mach 5 was rejected on analytic grounds, not by a run. The laminar choice is a sub-scale, high-altitude condition; a full-scale vehicle would need RANS, and B1 covers the one sensitivity run planned for that.

### S5. The validation ladder (5:30, 1.5 min)

- **Message:** Analytic checks run before any machine learning; hard checks must pass, soft and report checks are reported.
- **Figure or table:** The tolerance table (hard, soft, report) with the verdict column filled from the report.
- **Source:** `docs/validation/2026-11-01_report.md` (verdict column; development runs unless a row says official).
- **Speaker notes:** A hard failure means a bug in mesh, boundary condition, units or scheme, so we fix the cause and do not change the tolerance. The verdicts are shown as the report gives them, including the one that failed.

### S6. Oblique shock and laminar heating (7:00, 2 min)

- **Message:** The Euler wedge matches the oblique-shock relation within the hard tolerances, and the laminar wedge heating matches the Eckert flat-plate reference within the window.
- **Figure or table:** `docs/validation/2026-11-01_wedge_heat_flux.png`, with a V1 table beside it.
- **Source:** `runs/task1/README.md` and `runs/task1/v1_oblique_shock.json` (V1 and V2a, official). `docs/validation/2026-11-01_report.md` (V2b, development, final numerics).
- **Speaker notes:** The V1 check is the official Colab record, so it is the one to quote for the solver setup. The V2b check is a development run with the final numerics; the entropy-fix change moved its deviation, and B4 shows the comparison.

### S7. The cylinder: the hard check failed first (9:00, 2 min)

- **Message:** With the first numerics (Roe, entropy fix 0.1) the stagnation heating failed Fay-Riddell on the fine mesh; with entropy fix 0.3 it passes on that mesh.
- **Figure or table:** `docs/validation/2026-11-01_cylinder_heat_flux.png` (heat flux by mesh level) and `docs/validation/2026-11-01_grid_study.png`.
- **Source:** `docs/validation/2026-11-01_report.md` (V3 rows and grid study); `runs/dev/2026-11-01_cylinder_v3_attempt1/README.md` (the failure); `runs/dev/2026-11-01_cylinder_v3_attempt3/README.md` (the final numerics).
- **Speaker notes:** The failure was kept and not tuned away, and the fix was chosen from a six-scheme comparison and a split test. The grid study passes on two levels only, so no order of convergence is claimed.

### S8. Inlet design point at 8/8 (11:00, 2 min)

- **Message:** At the design point the inviscid throat matches the two-shock relations within the hard tolerance, and the laminar core is within the soft band.
- **Figure or table:** `docs/validation/2026-11-01_inlet_throat_p0.png` with the V4e and V4v rows.
- **Source:** `runs/dev/2026-11-01_inlet_design_point/README.md` (development run); `docs/validation/2026-11-01_report.md` (V4e and V4v rows).
- **Speaker notes:** This is a development run, not the official Task 2 record, which comes from the validation batch. The laminar core is a soft check, and the boundary-layer loss is shown beside it rather than hidden.

---

## Section 3: Automation layer: MCP tools, gates, queue (6 minutes)

### S9. The pipeline on one slide (13:00, 1.5 min)

- **Message:** A design passes the schema, the physics gates and the mesh gate before SU2 sees it, and the LLM sits outside this chain.
- **Figure or table:** Flow diagram: parameters, schema, gates, mesh quality, config, Drive queue, Colab worker, SU2, result or error, metrics, surrogate, acquisition.
- **Source:** none (no number). Interfaces are in `docs/specs/01_interfaces.md`.
- **Speaker notes:** Each step is a function a person can read, and each gate fails with the offending value. The language model calls typed tools and never picks a sampling point.

### S10. Gates reject before any CFD (14:30, 1.5 min)

- **Message:** The gates stop a design that would not converge, and the design box was trimmed on that evidence.
- **Figure or table:** Table of the box diagnostics: 12/12, 8/14 and 5/14 converged; 12/14 diverged on both meshes and with both CFL caps.
- **Source:** `runs/dev/2026-11-01_inlet_box_diagnostics/README.md`; `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md` (12/14 diverged on both meshes).
- **Speaker notes:** The 26 deg corner diverged, so the gate rejects total turning above 24 deg, and four of the 96 pool points are excluded. The 25 deg band was not tested, and any pool point near the limit that fails is recorded as a failure.

### S11. Queue over Google Drive and a restart-safe worker (16:00, 1.5 min)

- **Message:** Colab cannot take inbound connections, so jobs go through a Drive folder, and a restarted worker resumes without losing or repeating finished runs.
- **Figure or table:** Queue folder diagram: `jobs/`, `runs/<id>/status/` flags, `result.json` and `error.json`.
- **Source:** `PENDING: validation batch` (a restart on Colab has not been recorded yet; the local tests use a fake solver).
- **Speaker notes:** The worker never decides physics; it rebuilds the mesh from the uploaded parameters and checks a fingerprint before it runs SU2. Failure reasons come from a fixed list, so a failed job always says why.

### S12. The first live agent call (17:30, 1.5 min)

- **Message:** The agent reads the queue through a typed tool and answers from flag files and result records; it chose no sampling point.
- **Figure or table:** The `list_results` output from the first live call, reproduced from the transcript (ten rows, all pending at that time).
- **Source:** `docs/transcripts/2026-11-01_first_mcp_call.md`. **Deviation:** a transcript, not a `runs/` record; the claim is limited to what the tool returned.
- **Speaker notes:** This is a convenience layer over validated tools, and the transcript shows what the tool read and what it did not choose. Anything stronger rests on the Task 6 transcripts and injected faults, which have not been run yet.

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

- **Message:** The curves decide whether active learning beats random and Latin hypercube sampling on the same pool; this slide makes no claim before they exist.
- **Figure or table:** Held-out error against number of runs for al_ehvi, al_maxvar, random and LHS, with bands over 10 seeds.
- **Source:** `docs/validation/2026-11-02_replay_error_vs_n.png`, `docs/validation/2026-11-02_replay_summary.md`, `docs/validation/2026-11-02_replay.md` (interim replay on the 67 converged pool points of 92; to be rerun on the complete pool). EHVI has the lowest hypervolume regret at every budget (0 in 10 of 10 seeds from n = 32); on held-out error it is behind LHS and max-variance until n = 32 and level with max-variance at n = 40 and 48.
- **Speaker notes:** Every strategy uses the same pool, so the ground truth is shared and no extra CFD is needed. If active learning does not beat the baselines, the slide says so and the next step is to investigate, not to retune.

### S16. Calibration (25:30, 2.5 min)

- **Message:** The 90 percent intervals should cover about 90 percent of held-out points, and coverage outside 80 to 97 percent is flagged.
- **Figure or table:** Calibration plot: nominal against observed coverage on held-out points.
- **Source:** `docs/validation/2026-11-02_replay_calibration.png`, `docs/validation/2026-11-02_replay.md` (interim, 67 pool points, n = 48, 19 held-out points). q_peak coverage is inside the band (0.89 to 0.95 at the 90 percent level); recovery is over-covered (0.95 to 1.0 at the 90 percent level), which is flagged and explained, not refitted. The 80 to 97 percent flag band is the report tolerance C1 in `docs/specs/00_decisions.md`, section 5.
- **Speaker notes:** Coverage is the check that the uncertainty means something, and it is reported whatever it shows. A flagged result gets an explanation, not a refit.

---

## Section 5: Results, Pareto front, inverse query (7 minutes)

### S17. The pool across the box (28:00, 1.5 min)

- **Message:** The 92 runnable points span the trimmed box, and their objective values are the ground truth for every comparison.
- **Figure or table:** Scatter of theta1 against theta2, coloured by recovery and by peak heat flux (design map).
- **Source:** `runs/analysis/2026-11-02/design_map.png` (panel "observed runs", 92 points), `runs/pool/results.csv` (92 converged, 0 failed), `docs/validation/2026-11-01_colab_records.md`. The 4 of the 96 Sobol points in `designs/pool_sobol96.csv` with theta1 + theta2 > 24 deg were refused by gate 4 and never staged.
- **Speaker notes:** Only converged and stationary runs enter the surrogate, and each point keeps its status. Points rejected by a gate are listed as excluded, not dropped.

### S18. Pareto front with uncertainty (29:30, 2 min)

- **Message:** Observed points, the predicted front, the posterior band and the discretisation error bar, shown together, say how far the front can be trusted.
- **Figure or table:** Front plot from `analysis/pareto.py`: observed points, predicted front, posterior band, discretisation error bar.
- **Source:** `runs/analysis/2026-11-02/pareto_front.png`, `runs/analysis/2026-11-02/pareto.csv`, `docs/validation/2026-11-02_pareto_inverse.md`, section 2: 26 observed front points of 92; posterior band 1.2e-4 to 1.8e-3 wide in recovery; discretisation bar 3.1e-4 in recovery and 530 W/m2 in q_peak (V4m grid study), 25 times the posterior uncertainty in heat flux.
- **Speaker notes:** The band is posterior uncertainty and the error bar is discretisation error from the grid study, and both are shown separately. The front is only as good as the mesh levels behind it (B3).

### S19. Inverse query: maximum recovery under a heat-flux cap (31:30, 2 min)

- **Message:** The surrogate answers "highest recovery with peak heat flux under the 40th percentile of pool heating", and one real SU2 run checks the answer.
- **Figure or table:** Table: query, surrogate answer with interval, confirmation run result, and whether it falls inside the interval.
- **Source:** `runs/analysis/2026-11-02/inverse_q40/result.json`, `docs/validation/2026-11-02_pareto_inverse.md`, section 3 (cap 31493 W/m2; answer theta1 = 11.965, theta2 = 7.115; recovery 0.34515, interval 0.34506 to 0.34523; q_peak 31470, interval 31450 to 31490 W/m2; P(q <= cap) 0.972). `PENDING: confirmation run` `inlet2r-374dad241f` (submitted 2026-11-02 11:52 UTC; result and C2 verdict from `analysis.confirm`).
- **Speaker notes:** The cap is set from the pool before the answer is known. The check passes if the confirmation run falls inside the predicted interval; a miss is documented and explained.

### S20. Design maps over the box (33:30, 1.5 min)

- **Message:** Design maps show recovery and heat flux over the trimmed box, with the surrogate and the observed points on top.
- **Figure or table:** Map output from `analysis/design_map.py`.
- **Source:** `runs/analysis/2026-11-02/design_map.png`, `runs/analysis/2026-11-02/oswatitsch_cut.png`, `runs/analysis/2026-11-02/grid.csv`, `docs/validation/2026-11-02_pareto_inverse.md`, section 4 (recovery std 1.8e-5 to 1.1e-4 over the box; GP mean 0.0008 to 0.0022 above the inviscid analytic curve along the Oswatitsch cut, explained from the recorded throat Mach).
- **Speaker notes:** The maps show where the trade-off bends for an aerodynamics audience. They are interpolations between runs and are labelled that way.

---

## Section 6: What failed, limits, next steps (5 minutes)

### S21. What failed, in order (35:00, 2 min)

- **Message:** Five things failed on the way, each was recorded, and each change was made on that evidence.
- **Figure or table:** Table with columns: what failed, what the record shows, what changed.
  Rows: (1) cylinder carbuncle with Roe at entropy fix 0.1; (2) Euler wedge with AUSM+-up2 diverged or stalled; (3) 12/14 corner diverged; (4) the diverged 12/14 surface file was reported as a unit error ("check the units") until a divergence check was put before the cross-check; (5) a pool job was refused by the worker as a config mismatch because one geometry number in a comment line differed in its last digit between the container and Colab (h_duct, 3e-18), so the config hash now covers only the lines SU2 reads.
- **Source:** `runs/dev/2026-11-01_cylinder_v3_attempt1/README.md`; `runs/dev/2026-11-01_numerics/README.md`; `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md`; `docs/faults/README.md` (the "check the units" fix); the config-mismatch failure record of pool job inlet2r-db92dcf68d (`runs/pool/inlet2r-db92dcf68d/error.json` at commit 915f5f8, reason and both hashes; the retried job later converged and its result replaced the record) and `docs/transcripts/2026-11-02_worker_restart_and_retry.md`.
- **Speaker notes:** Failures 4 and 5 are failures of the tooling, not of the physics, and they are the ones an agent layer must surface rather than hide: a wrong message and an over-strict guard. Both are closed with a test.

### S22. Limits of the model (37:00, 1.5 min)

- **Message:** The model is laminar, sub-scale and two-dimensional with two variables, and the corner of the box that does not converge limits what the front means.
- **Figure or table:** List of limits, each with its consequence for the Pareto front.
- **Source:** `runs/dev/2026-11-01_inlet_grid_study_ef03/README.md` (12/14 divergence); `runs/dev/2026-11-01_numerics/README.md` (leading-edge wall temperature); turbulence sensitivity: `runs/dev/2026-11-01_turbulence_sensitivity_SA/README.md` (Spalart-Allmaras at 8/8 and 12/12, development runs, labelled a sensitivity bound).
- **Speaker notes:** A full-scale vehicle at lower altitude would be turbulent, and the talk does not claim a turbulent result. Objective values near sharp leading edges are excluded by construction, not because they were checked.

### S23. What is still to be recorded (38:30, 1.5 min)

- **Message:** The official validation batch, the fault matrix and the turbulence sensitivity are recorded; the 92-point pool and the confirmation run are what remains.
- **Figure or table:** Status table: done, running, pending, each with its record.
- **Source:** `docs/validation/2026-11-01_report.md` (development runs); `docs/validation/2026-11-01_colab_records.md` (official validation batch: V3, V4m, V4e metrics form, X1, and the two 12/14 failures); `docs/faults/fault_matrix.md` (fault injection, run without SU2). Pending rows: `PENDING: pool batch`, `PENDING: confirmation run`.
- **Speaker notes:** Each pending item has a named batch or an explicit note that none is assigned yet. The talk claims nothing beyond what the records show on the day.

---

## Section 7: Discussion (about 20 minutes, outside the 40)

### S24. Questions, and where the answers are (40:00 onward, about 20 min)

- **Message:** The discussion is open, and the backup slides answer the fidelity questions.
- **Figure or table:** Index of B1 to B6.
- **Source:** none (no number).
- **Speaker notes:** Start with the limit that matters to the person asking, then open the matching backup slide. Do not quote a number that is not on a slide.

---

## Backup slides (not timed)

### B1. Turbulence model (fidelity question: why laminar?)

- **Message:** Laminar is the model for this sub-scale condition; a Spalart-Allmaras sensitivity run shows what a turbulent layer would change and is labelled as a bound, not a result.
- **Figure or table:** Bar chart of both objectives at 8/8 and 12/12, laminar against Spalart-Allmaras (numbers in the record's table).
- **Source:** `runs/dev/2026-11-01_turbulence_sensitivity_SA/README.md`: Spalart-Allmaras at 8/8 (medium and fine) and 12/12 (medium), development runs on the container. Peak heating 2.5 to 2.6 times laminar, throat recovery 0.857 against 0.909 at 8/8, wall y+ median 2.3 (medium) and 1.7 (fine); a sensitivity bound, not a validated turbulent prediction.
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
- **Speaker notes:** The not-run rows are shown, not hidden: the stand-off check, the 12/14 grid study and the pressure cross-check on some runs. Official and development rows are labelled, and the report says which are which.

# Deck outline, version 2: a gated, automated pipeline that speeds up design exploration

Version 2 of the drone talk. The main focus is the pipeline and how it shortens the engineering loop;
the aircraft is the test problem it was built for. Version 1 (`outline_drone.md`, `deck_drone.pptx`)
stays as it is.

## Conventions

- Main body: V1 to V25, at most 25 slides, about 30 minutes; no section dividers inside it. Backup
  slides B1 onward follow one "Backup" divider and are opened only on a question.
- No source footers and no repository file paths on any slide or in any note. No mention of any
  earlier study: the pipeline is presented as built for this problem.
- Every number is a `{placeholder}` filled at build time from the records, exactly as in version 1;
  a placeholder whose record does not exist yet renders as PENDING with no number.
- Each slide: **Message** (the subtitle, one sentence), **Body** (what the slide shows: the version-1
  body it reuses, or a new one), **Speaker notes**.

## Main body (30 minutes)

### V1. Title (0:00, 0.5 min)

- **Message:** An automated, gated simulation pipeline that sizes a small electric aircraft: what it does, what it caught, and how much engineering time it saves.
- **Body:** Title slide: "A gated, automated design pipeline", subtitle "Version 2", one status line computed from the records (pool designs complete, confirmation status).
- **Speaker notes:** I built a pipeline that takes design questions to a CFD solver and back without a person in the loop for the routine steps, and that refuses to pass on a result it cannot check. I will show it on one aircraft, end to end.

### V2. The engineering problem (0:30, 1 min)

- **Message:** High-fidelity simulation is slow, its setup is manual, and its failures are often silent; a design study needs many runs and every one of them has to be trusted.
- **Body:** New. Three columns, "slow", "manual", "silent", each with one line from the records: one SU2 angle costs a median {hf_coarse_min} min on the coarse mesh and a design needs five angles; a low-fidelity design costs {lf_s_core} s of one core; the first SU2 case exited with code {smoke_exit} and was wrong (V3).
- **Speaker notes:** Engineering design is a loop of propose, simulate, check, decide. The simulate step dominates the clock, and the check step is where people quietly lose days. The pipeline attacks both: it runs the loop unattended, and it checks every result before anyone sees it.

### V3. A clean exit is not a correct result (1:30, 1 min)

- **Message:** The first SU2 airfoil case exited with code {smoke_exit} after its whole {smoke_budget}-iteration budget, with lift {smoke_cl_off} and drag {smoke_cd_off} against its own properly stopped rerun; only checks after the solver could see it.
- **Body:** Reuse version-1 D2 (clean exit figure).
- **Speaker notes:** This is the design principle of the whole pipeline. The solver said success. The numbers were wrong by double digits. So the pipeline treats the solver's exit code as a hint and decides convergence itself, from the history.

### V4. The test problem (2:30, 1 min)

- **Message:** Endurance against take-off mass at a fixed {payload_kg} kg payload, under the {cap_kg} kg cap of the EASA open-category class C2, over six design inputs.
- **Body:** Reuse version-1 D6 (the trade under the cap) with the six inputs listed beside it (span, aspect ratio, taper, battery fraction, camber, thickness).
- **Speaker notes:** The aircraft is deliberately small so that every step can be run end to end. Six inputs span the box; everything else is fixed in a graded ledger, {n_ledger} quantities, {n_assumed} of them assumptions with a band.

### V5. The pipeline at a glance (3:30, 1.5 min)

- **Message:** Requests enter through typed tools and gates, run on cloud workers through a shared queue, and come back through checks into versioned records that the surrogate learns from; the language model never chooses a design point.
- **Body:** New drawing: agent -> MCP tools -> gates -> queue -> sharded cloud workers (started and restarted from the session) -> checks after the run -> hashed ingest -> run records -> surrogate and acquisition -> next batch, with the human touch points marked (rulings, sign-ins).
- **Speaker notes:** Read it left to right. Every arrow has a check on it. The two places a person is needed are marked: a ruling when the data force a judgment, and a sign-in when a cloud runtime has to be authorised. Everything else runs unattended.

### V6. The agent's interface: typed tools, not free text (5:00, 1 min)

- **Message:** The agent reaches the solver only through {n_tools} typed tools with strict schemas; the tools never run the solver, and every call is logged.
- **Body:** Reuse version-1 D4 (why MCP), without file references.
- **Speaker notes:** A typed interface is what lets an agent drive engineering software safely: a malformed request is rejected with a message, not executed. The tools stage, submit, ingest and report; the solver runs elsewhere.

### V7. Gates before any solver (6:00, 1 min)

- **Message:** A design passes {n_gates} gates before any solver runs, and an airfoil case passes a mesh-quality gate; a gated design costs nothing.
- **Body:** New table, one row per gate: 1 Reynolds range; 2 stall margin; 3 mass closure; 4 manufacturing floor and wing loading (one gate, two checks); 5 lattice quality; plus the airfoil mesh-quality gate (inverted cells, minimum angle, first cell, growth, aspect ratio). In the low-fidelity grid, {gated_n} of {grid_n} designs were stopped here.
- **Speaker notes:** Gates are cheap pure functions. They turn an expensive failure into an instant refusal with the offending value in the message.

### V8. Two fidelity levels (7:00, 1 min)

- **Message:** A low-fidelity design costs {lf_s_core} s of one core; one SU2 angle costs a median {hf_coarse_min} min on the coarse mesh and {hf_medium_min} min on the medium mesh, and a design needs five angles.
- **Body:** Reuse version-1 D8 (costs) or D9 (model in one picture).
- **Speaker notes:** The two levels share everything except the section data, so the expensive level corrects the cheap one rather than replacing it. That is what makes the two-level model on V17 possible.

### V9. Validation before any machine learning (8:00, 1 min)

- **Message:** The solver's own checks pass ({n_pass} rows pass, {n_fail} fail); against the wind tunnel SU2's lift slope misses by {v6e_dev} against a {v6e_tol} tolerance, a fail that is kept and travels with every result.
- **Body:** New compact table: the V6 rows grouped as pass, fail, pending, with the decision to accept the medium mesh with the bias recorded.
- **Speaker notes:** Tolerances were fixed before the runs. The miss was not tuned away: every SU2 result carries it as a flag in its own record.

### V10. Queue, workers and shards (9:00, 1 min)

- **Message:** Workers split the queue by a hash of the case id, so they never race for a case; a worker that dies leaves a heartbeat that goes stale, and its case is re-run.
- **Body:** Reuse version-1 D26 queue figure and D27 shards, combined.
- **Speaker notes:** The queue is a shared folder of job files with status flags. Sharding by hash means adding a worker is a configuration change, not a coordination problem.

### V11. Version 2: the session runs the compute (10:00, 1.5 min)

- **Message:** The session starts, deploys, watches, rebalances and restarts the cloud runtimes itself; a person is needed only to authorise a runtime's storage and to rule on the data.
- **Body:** New. A timeline of the pool day from the run records: cases finished per hour, the number of live workers over time, the points where a runtime ended and was restarted, and the shard splits that moved idle capacity onto the longest queue.
- **Speaker notes:** Before, a person restarted workers by hand: when both runtimes ended at 14:10 UTC nothing ran until 15:50. Now the session starts and restarts runtimes through a command-line interface, sees a dead worker from its heartbeat, and re-splits the shards when one runtime drains, so neither idles while the other has a queue. The runtime log in the task record lists every action.

### V12. What the checks caught (11:30, 1 min)

- **Message:** Each of these was found by a check or a recorded run before it reached a result.
- **Body:** Reuse version-1 D28, extended with the corrupt volume files found by a structure check and the rank-count claim corrected from the records.
- **Speaker notes:** None of these would have shown up as a solver error. They were caught because every result is checked and every claim is computed from the records.

### V13. Surrogate and acquisition (12:30, 1 min)

- **Message:** One Gaussian process on endurance and one on log take-off mass give a mean and an interval everywhere; an acquisition function picks the next design, and the language model chooses nothing.
- **Body:** Reuse version-1 D29.
- **Speaker notes:** The surrogate is what turns a few hundred expensive runs into a map of the whole design space.

### V14. Active learning on a fixed pool (13:30, 1 min)

- **Message:** On a 192-point pool, expected hypervolume improvement reaches regret {ehvi_32} at 32 evaluations, while random sampling is still at {rand_40} after 40.
- **Body:** Reuse version-1 D31.
- **Speaker notes:** Regret is how much of the true front is still missing. Active learning has the whole front at 32 evaluations; random sampling is still missing part of it after 40.

### V15. Active learning on the open box, honestly (14:30, 1.5 min)

- **Message:** On the open box plain expected improvement loses to random ({ehvi_on_40} against {rand_on_40}) because it keeps picking designs the gates reject; weighted by the probability of passing the gates it reaches {feas_on_40}.
- **Body:** Reuse version-1 D32.
- **Speaker notes:** This is the result I lead with, because it includes a loss. The fix is a small feasibility model. Without it, the clever method is worse than chance.

### V16. Two levels: fewer expensive runs (16:00, 1.5 min)

- **Message:** {mf_answer}
- **Body:** Reuse version-1 D33 (table with error and coverage).
- **Speaker notes:** The cheap model runs everywhere; SU2 only has to learn the scale and a correction. The saving is large at small SU2 budgets and reverses by 24 designs, where SU2 alone is slightly better; neither model's interval is calibrated, so I quote the mean.

### V17. How much engineering time this saves (17:30, 1.5 min)

- **Message:** {grid_n} low-fidelity designs ran in {grid_hours} h; {su2_cases} SU2 cases ran in {su2_worker_h} worker-hours over {pool_wall_h} h of elapsed time; the two-level model reaches with 8 SU2 designs the error SU2 alone needs {mf_n_match} for.
- **Body:** New. One table: what was run, how many, how long, and what a person had to do (rulings and sign-ins counted from the records).
- **Speaker notes:** The point is not that the computer is fast. The point is that the loop runs overnight, checks itself, and hands a person only the decisions that need judgment.

### V18. The expensive level against the cheap one (19:00, 1 min)

- **Message:** Of the {pool_designs} SU2 designs, {pool_complete} are complete; on every one the SU2 endurance is {hf_lf_end_range} against the low model's.
- **Body:** Reuse version-1 D35 as a figure (SU2 against low endurance per design), not a long table.
- **Speaker notes:** The direction is the same on every design, which is exactly what a two-level model can learn.

### V19. The front (20:00, 1 min)

- **Message:** {hf_front_answer}
- **Body:** Reuse version-1 D36, with the exact low-fidelity front from D34 beside it.
- **Speaker notes:** The low-fidelity front is exact because the cheap model ran on the whole grid; the SU2 front comes from the surrogate with its band.

### V20. The inverse query under the 4 kg cap (21:00, 1.5 min)

- **Message:** On the low model the answer is a box corner and the cap never binds; {hf_inverse_answer}
- **Body:** Reuse version-1 D37.
- **Speaker notes:** The expensive level moves the answer off the corner and brings the cap into play, which the cheap model never showed. That is the value of the second level in one slide.

### V21. Confirmation: does the prediction hold? (22:30, 1.5 min)

- **Message:** {confirm_v2_answer}
- **Body:** New. The predicted interval and the SU2 result for endurance and mass, for each confirmation run that has landed; PENDING for one that has not.
- **Speaker notes:** The pass condition was fixed before the run: both endurance and mass inside their ninety-percent intervals. A miss would be reported with its direction.

### V22. What the flow looks like at stall (24:00, 0.5 min)

- **Message:** At 14 degrees the upper surface of pool design 0 is separated over most of the chord; this is the stall the cheap section model cannot show.
- **Body:** Reuse version-1 D24 figure (14 degree case only), without case ids.
- **Speaker notes:** The picture is a sanity check on what the numbers say: lift falls and drag rises past 10 degrees.

### V23. Limits that travel with every number (24:30, 1.5 min)

- **Message:** One cruise point at sea level, a fixed propeller efficiency, a closed-form structure, and an SU2 lift-slope bias of {v6e_dev}: these bound what the front and the answer mean.
- **Body:** Reuse version-1 D41 and D43, merged.
- **Speaker notes:** Every number in this talk is conditional on these. They are written into the records, not just said here.

### V24. Conclusions (26:00, 2 min)

- **Message:** The pipeline runs the design loop unattended, refuses what it cannot check, and asks a person only for rulings; on this problem it cut the expensive runs at small budgets, answered the capped design question, and its first confirmation run passed.
- **Body:** New. Four questions, one line each with its answer and status from the records; one line on what version 2 changed.
- **Speaker notes:** If I had to keep one idea: put the checks after the solver, not just before it, and make every claim computable from the records.

### V25. Questions (28:00 onward)

- **Message:** Discussion; the backup slides hold the detail behind every number.
- **Body:** A short list of likely questions and the backup slide that answers each.
- **Speaker notes:** Open the backup that answers the question rather than describing it.

## Backup slides (not timed)

Each reuses a version-1 body, without source footers, file paths or case ids, and without any
mention of an earlier study. Version-1 DB14 (study guide) and DB15 (carried over) are not included.

### B1. The nominal design in one top view
- **Body:** version-1 D10.
### B2. The vortex lattice and its checks
- **Body:** version-1 D11.
### B3. Validation table, solver checks
- **Body:** version-1 D12 and DB1.
### B4. Mass closure and the endurance balance
- **Body:** version-1 D13.
### B5. The airfoil mesh
- **Body:** version-1 D14.
### B6. Two stopping rules: Cauchy stop and drift
- **Body:** version-1 D15.
### B7. A solver history
- **Body:** version-1 D16.
### B8. What the mesh does to the pressure distribution
- **Body:** version-1 D17.
### B9. The low-fidelity section against the tunnel
- **Body:** version-1 D18.
### B10. SU2 against the tunnel, and the decision to accept the bias
- **Body:** version-1 D19 and DB2.
### B11. Tunnel pressure distributions
- **Body:** version-1 D20.
### B12. Where the wall shear reverses
- **Body:** version-1 D21.
### B13. Section polars
- **Body:** version-1 D22.
### B14. The stall at 14 degrees, pressure
- **Body:** version-1 D23.
### B15. What the surrogate learned about the box
- **Body:** version-1 D30.
### B16. The exact low-fidelity front
- **Body:** version-1 D34.
### B17. Bias sweep at the answer
- **Body:** version-1 D39 and DB8.
### B18. Coarse against medium on the pool
- **Body:** version-1 D40 and DB4.
### B19. What the record keeps that was wrong first
- **Body:** version-1 D42.
### B20. Tunnel points at both Reynolds numbers
- **Body:** version-1 DB3.
### B21. Budget-exhausted runs and the ruling on them
- **Body:** version-1 DB5.
### B22. The low-fidelity Pareto record
- **Body:** version-1 DB6.
### B23. The inverse query record
- **Body:** version-1 DB7.
### B24. Online replays, full tables
- **Body:** version-1 DB9.
### B25. The decision log
- **Body:** version-1 DB10.
### B26. Ledger provenance
- **Body:** version-1 DB11.
### B27. Cost ledger
- **Body:** version-1 DB12.
### B28. Equations
- **Body:** version-1 DB13, without module paths.
### B29. Open rulings
- **Body:** version-1 DB16.

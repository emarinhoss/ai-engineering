# Deck outline, version 3: a gated, automated pipeline that speeds up design exploration

Version 3 of the drone talk: version 2 with the changes Éder asked for on 2026-11-12. Version 2
(`outline_drone_v2.md`, `deck_drone_v2.pptx`) stays as it is.

## Conventions

- Slides are numbered 1 onward and named only by that number, on the slide and in any text that
  points to another slide. The main body ends with the questions slide; one "Backup" divider
  follows, then the backups, which are opened only on a question.
- No source footers and no repository file paths on any slide or in any note. No mention of any
  earlier study: the pipeline is presented as built for this problem.
- Every number is a `{placeholder}` filled at build time from the records, exactly as in versions 1
  and 2; a placeholder whose record does not exist yet renders as PENDING with no number.
- Each slide: **Message** (the subtitle, one sentence), **Body** (what the slide shows) and
  **Presenter notes** (what to say, written in ASD-STE100 Simplified Technical English; one
  paragraph per indented line). "From version 2" names the version-2 slide whose body is reused.
- The build puts the presenter notes into each slide's notes and writes them, filled, as
  `transcript_drone_v3.md`.

## Changes from version 2

1. Slides are named by number only.
2. The nominal design (version-2 backup 1) is in the main body, after the test problem.
3. Slide 2 sets up the problem and the motivation together.
4. The validation slide no longer shows the medium-against-fine mesh row, and its decision footnote
   is gone.
5. The queue, workers and shards slide moved to the backups.
6. New backup slide 40: why a Gaussian process, with every model compared on this study's data.
12. The endurance calculation is a new backup slide (46), with the steps for one low-pool design. The
   confirmation and the stall slides move to the backups (26 and 27), so the main body is 24 slides.
7. New backup: what hypervolume regret is.
8. Version-1 D26 (what runs in Claude Code, on Drive and on Colab) is in the main body, with its
   original labels.
9. The first smoke case is described as not converged (see the note on slide 13).
10. Slide 14 explains each sampling strategy in more detail.
11. Version-2 backups 11, 12, 14, 17, 18, 19, 21, 22, 23, 25, 26, 28, 29 and 30 are left out.

## Main body (about 27.5 minutes)

### 1. Title (0:00, 0.5 min)

- **Message:** An automated, gated simulation pipeline that sizes a small electric aircraft: what it does, what it caught, and how much engineering time it saves.
- **Body:** From version 2, slide 1 (status line computed from the records).
- **Presenter notes:** I made a pipeline that sends design questions to a CFD solver and brings the answers back. A person does not do the routine steps. The pipeline does not give a result that it cannot check.
  I show it on one small electric aircraft, from start to end. The status line at the bottom comes from the records.

### 2. The problem, and why it needs a pipeline (0:30, 1.5 min)

- **Message:** Size a small electric aircraft for endurance at a fixed {payload_kg} kg payload under the {cap_kg} kg cap of the EASA open-category class C2; every high-fidelity answer is slow, set up by hand, and can fail silently.
- **Body:** New. Top: the design question and the six inputs. Below: three columns, "slow", "manual", "silent", each with one line from the records.
- **Presenter notes:** This is the problem. The aircraft carries a payload of {payload_kg} kg. The C2 class of the EASA open category limits the take-off mass to {cap_kg} kg. We want the longest endurance in that limit.
  Six inputs define the design: span, aspect ratio, taper, battery fraction, camber and thickness. A graded ledger of {n_ledger} quantities fixes all other values.
  Design work is a loop: propose, simulate, check, decide. The simulation takes the most time. One SU2 angle takes a median of {hf_coarse_min} minutes on the coarse mesh, and a design needs five angles.
  Each case also needs a mesh, a configuration and a check. A person usually writes these by hand.
  The third problem is the worst. A solver can stop correctly and still give incorrect numbers. Slide 3 shows an example.
  Thus the loop must run without a person, and it must check each result before a person sees it.

### 3. A clean exit is not a correct result (2:00, 1 min)

- **Message:** The first SU2 airfoil case exited with code {smoke_exit} after its whole {smoke_budget}-iteration budget, with lift {smoke_cl_off} and drag {smoke_cd_off} against its own properly stopped rerun; only checks after the solver could see it.
- **Body:** From version 2, slide 3.
- **Presenter notes:** This is the design principle of the pipeline, so I show it early.
  The first SU2 airfoil case stopped with exit code {smoke_exit}. It used all of its {smoke_budget} iterations and wrote all of its files. The solver reported success.
  But we compared it with a rerun that stopped correctly. The lift error was {smoke_cl_off}. The drag error was {smoke_cd_off}.
  Follow the chain on the right. The drift rule read the history. Lift still moved {smoke_cl_drift} and drag moved {smoke_cd_drift} in the last fifth of the run.
  The ruling set a budget of {smoke2_budget} iterations with a Cauchy stop. The rerun stopped at iteration {smoke2_iters}.
  Thus the pipeline does not trust the exit code. It decides convergence from the history.

### 4. The test problem (3:00, 1 min)

- **Message:** Endurance against take-off mass at a fixed {payload_kg} kg payload, under the {cap_kg} kg cap of the EASA open-category class C2, over six design inputs.
- **Body:** From version 2, slide 4.
- **Presenter notes:** This is the test problem. The trade is endurance against take-off mass, at a fixed payload of {payload_kg} kg.
  The vertical line is the C2 limit of {cap_kg} kg. The requirement is a probability of 0.9 or more to stay below the limit. We set this requirement before the first run.
  The table gives the range of each of the six inputs.
  The ledger has {n_ledger} quantities. {n_assumed} of them are assumptions, and each assumption has a band.
  Note one point: the heaviest design in the low-fidelity pool is {lowpool_max} kg. Thus only SU2 tests the limit.

### 5. The nominal design in one top view (4:00, 0.5 min)

- **Message:** The nominal design has a {nom_span} m span, aspect ratio {nom_ar} and taper {nom_taper}: {nom_area} m^2 of wing and a closed take-off mass of {nom_mtow} kg; tail and fuselage follow from the wing by rule.
- **Body:** From version 2, backup 1 (the top view with the six inputs labelled).
- **Presenter notes:** This is the nominal design, in one top view. It is at the middle of the design box.
  The span is {nom_span} m, the aspect ratio is {nom_ar} and the taper is {nom_taper}. The wing area is {nom_area} square meters. The closed take-off mass is {nom_mtow} kg.
  The span and the aspect ratio set the wing area. The taper sets the chords.
  Rules set the tail and the fuselage from the wing. The tail size comes from volume coefficients with a fixed arm. The fuselage holds the payload and the battery.
  The inset shows the wing section. Camber and thickness are the two section inputs.

### 6. The pipeline at a glance (4:30, 1.5 min)

- **Message:** Requests enter through typed tools and gates, run on cloud workers through a shared queue, and come back through checks into versioned records that the surrogate learns from; the language model never chooses a design point.
- **Body:** From version 2, slide 5.
- **Presenter notes:** This drawing shows the full pipeline. Read it from left to right.
  The agent does not touch the solver. It calls typed tools. Each request goes through the gates first. A design that fails a gate stops here, with a message.
  A request that passes becomes a job file in a shared queue. Cloud workers take the jobs from the queue.
  A result does not go directly into the study. Checks after the run decide if it converged. Then a hash goes with it into a run record.
  The surrogate learns from the records. An acquisition function selects the next batch. The language model never selects a design point.
  A person must act at two marked points only: a ruling on the data, and a sign-in for a cloud runtime.

### 7. The agent's interface, and what runs behind it (6:00, 1 min)

- **Message:** The agent reaches the pipeline only through {n_tools} typed tools; the session starts the Colab runtimes and moves the files, and each worker checks every job again before SU2 runs.
- **Body:** New, three columns. The typed tools, grouped by task, with the schema, the refusal and the audit line. What the session does outside the tools. What each Colab worker does with a job.
- **Presenter notes:** The agent reaches the pipeline only through {n_tools} typed tools. Each tool has a strict schema, and an unknown field or a wrong type gets a refusal.
  The left column groups the tools by task: check, stage, move and log, bring back, and look. None of them runs the solver.
  The tools only stage, submit, ingest and report. The session does the rest. It starts and restarts the Colab runtimes with the Colab command-line tool, and it moves the files to and from the Drive folder.
  Each Colab worker checks every job again. It takes only the jobs in its own shard, and it makes the mesh and the configuration again from the job parameters.
  It runs the physics gates again before SU2 starts. After SU2, it checks the exit code, NaN values and the time limit. A heartbeat shows that the worker is alive, and an old heartbeat means that the job runs again.
  The language model never selects a design point. Design tables and acquisition code select them.

### 8. Gates before any solver (7:00, 1 min)

- **Message:** A design passes {n_gates} gates before any solver runs, and an airfoil case passes a mesh-quality gate; a gated design costs nothing.
- **Body:** From version 2, slide 7.
- **Presenter notes:** A design must pass {n_gates} gates before a solver runs.
  Read the table from top to bottom. Gate 1 checks the cruise Reynolds number. Gate 2 checks the stall margin. Gate 3 closes the mass. Gate 4 checks the manufacturing floor, which is a study rule, and the wing loading. Gate 5 checks the quality of the lattice.
  An airfoil case also passes a mesh-quality gate.
  The gates are fast functions. In the low-fidelity grid, the gates stopped {gated_n} of {grid_n} designs.
  Each refusal gives the value that caused it. A gated design costs no solver time.

### 9. What runs where: Claude Code, Drive, Colab (8:00, 1 min)

- **Message:** Every request passes the same ordered checks before SU2 starts, and every result passes more before it becomes a record; the numbered marks show where.
- **Body:** Version-1 D26 drawing with its original labels (Claude Code and the MCP tools, the Drive queue folder, the Colab worker), file names replaced by plain words.
- **Presenter notes:** This drawing shows what runs where.
  The top band is the session: Claude Code and the typed tools. The tools validate the request, apply the gates, stage the job and later ingest the result.
  The middle band is a folder on Google Drive. Colab cannot accept inbound connections. Thus the jobs and the results move through this folder as files.
  The bottom band is the Colab worker. It makes the mesh and the configuration again from the job parameters. It refuses a job if the fingerprint or the hash does not agree.
  Then SU2 runs, and the worker checks for a timeout, a bad exit code and NaN values.
  Each result comes back with a SHA-256 digest. The ingest step checks the digest and the record. The numbered marks show where each check is.

### 10. Two fidelity levels (9:00, 1 min)

- **Message:** A low-fidelity design costs {lf_s_core} s of one core; one SU2 angle costs a median {hf_coarse_min} min on the coarse mesh, {hf_medium_min} min on the medium mesh and {hf_fine_min} min on the fine mesh, and a design needs five angles.
- **Body:** From version 2, slide 8.
- **Presenter notes:** There are two fidelity levels.
  The low level uses closed-form section data. It costs {lf_s_core} seconds of one core for each design.
  The high level runs SU2 on the design's own section, at its cruise Reynolds number. One angle costs a median of {hf_coarse_min} minutes on the coarse mesh, {hf_medium_min} minutes on the medium mesh and {hf_fine_min} minutes on the fine mesh. A design needs five angles.
  The pool runs on the coarse mesh. The fine mesh is for the tunnel and mesh checks, and its median cost is {fine_x} times the coarse mesh.
  Look at the last line of the table. The two levels use the same geometry, lattice, closure and mission. Only the section data are different.
  Thus the expensive level corrects the cheap level. It does not replace it. Slide 17 uses this fact.

### 11. Validation before any machine learning (10:00, 1 min)

- **Message:** The solver's own checks pass ({n_pass} rows pass, {n_fail} fail); against the wind tunnel SU2's lift slope misses by {v6e_dev} against a {v6e_tol} tolerance, a fail that is kept and travels with every result.
- **Body:** From version 2, slide 9, without the medium-against-fine mesh row and without the decision footnote.
- **Presenter notes:** We did the validation before any machine learning. We set the tolerances before the runs.
  The top group is the checks of the method itself. {n_pass} rows pass and {n_fail} fail. {n_pending} row is pending, because its reference point has no source yet.
  The next group is SU2 against the wind tunnel. The drag ratio passes at both Reynolds numbers, {v6e_cd_lo} and {v6e_cd_hi} against 20 %.
  The lift slope fails at both Reynolds numbers, {v6e_dev} and {v6e_cla_hi} against {v6e_tol}.
  The fail stays a fail. Each SU2 result carries it as a flag.

### 12. The session runs the compute (11:00, 1.5 min)

- **Message:** The session starts, deploys, watches, rebalances and restarts the cloud runtimes itself; a person is needed only to authorise a runtime's storage and to rule on the data.
- **Body:** From version 2, slide 11.
- **Presenter notes:** This slide shows what version 2 changed. The figure is a timeline of the pool day, from the run records.
  The top shows the cases that finished in each hour. The bottom shows the live workers. A gap is where a runtime stopped.
  Before, a person restarted the workers by hand. Both runtimes stopped at 14:10 UTC, and no case ran until 15:50.
  Now the session does this work. It starts the cloud runtimes through a command-line interface. It reads the heartbeats and finds a dead worker. It restarts the runtime.
  When one runtime finishes its shard, the session divides the queue again. Thus no runtime waits while the other has jobs.
  A person must still do two things: sign in to give a runtime access to storage, and make the rulings.

### 13. What the checks caught (12:30, 1 min)

- **Message:** Each of these was found by a check or a recorded run before it reached a result.
- **Body:** From version 2, slide 12, with the first smoke case described as not converged.
- **Presenter notes:** Each row here is a problem. A check or a recorded run found it before it got into a result.
  The postprocess step read the incorrect residual. The first case also did not converge. Its lift moved {smoke_cl_drift} and its drag moved {smoke_cd_drift} at the end of the run.
  That first case did not diverge. It used its full budget and did not settle. Thus "not converged" is the correct term.
  A fine mesh did not agree with its fingerprint, and the worker refused it. Another fine mesh had inverted cells, and the inversion gate stopped it.
  The last row is my own error. I said that the pool ran on 4 ranks. The records show 2 ranks for some cases and 4 for others.
  The solver reported none of these problems as an error.

### 14. How each strategy picks the next design (13:30, 1.5 min)

- **Message:** One Gaussian process on endurance and one on log take-off mass give a mean and an interval everywhere; five strategies use them differently to pick the next design, and the language model chooses nothing.
- **Body:** New, extending version-2 slide 13: a table of the five strategies (how each picks a point, and what it uses), the hypervolume and acquisition relations below it.
- **Presenter notes:** The checks decide which results count. Now we decide which design to run next, using only those results.
  Two Gaussian processes make the surrogate. One models endurance. The other models the logarithm of take-off mass.
  Each process gives a mean and an interval at each design in the box. Five strategies use them in different ways.
  Random selects a design that has not run yet. The Latin hypercube spreads the full budget over the range of each input. These two use no model. They are the baselines.
  Maximum variance runs the design where the model is least sure. It does not ask if the design is good.
  Expected hypervolume improvement draws 128 samples at each candidate. It measures how much each sample increases the area of the current front. Good designs and uncertain designs both get a high score.
  The last strategy multiplies that score by the probability to pass the gates. Slide 16 shows why we need it.
  The language model calls tools. It never selects a point.

### 15. Active learning on a fixed pool (15:00, 1 min)

- **Message:** On a 192-point pool, expected hypervolume improvement reaches regret {ehvi_32} at 32 evaluations, while random sampling is still at {rand_40} after 40.
- **Body:** From version 2, slide 14.
- **Presenter notes:** First, the easy case: a fixed pool of {n_lowpool} points. The response is smooth, and no design fails a gate.
  The figure shows the hypervolume regret against the number of evaluations. Regret is the part of the true front that is still missing. Backup slide 41 defines it.
  Each curve is a mean of 10 seeds. Each strategy of a seed starts from the same 8 points.
  Follow the EHVI line. At 16 evaluations it is {reg_ehvi_16}. At 32 evaluations it is {ehvi_32}: it has found the full front.
  Random is at {rand_40} after 40 evaluations. The Latin hypercube is at {lhs_40}, and maximum variance at {maxvar_40}.
  On a smooth pool, active learning is clearly better. But this is the easy case.

### 16. Active learning on the open box, honestly (16:00, 1.5 min)

- **Message:** On the open box plain expected improvement loses to random ({ehvi_on_40} against {rand_on_40}) because it keeps picking designs the gates reject; weighted by the probability of passing the gates it reaches {feas_on_40}.
- **Body:** From version 2, slide 15.
- **Presenter notes:** This is the result that I show first, because it includes a loss.
  On the open box, the full space with its gates, plain EHVI is worse than random. At 40 evaluations its regret is {ehvi_on_40}. Random has {rand_on_40}.
  The reason is in the column of gated picks. EHVI selected a mean of {ehvi_gated} designs that the gates rejected. Random selected {rand_gated}.
  The front is near the gated edge, and the Gaussian processes do not know the gates. Thus EHVI goes to the edge again and again.
  The correction is a small feasibility model. It gives the probability to pass the gates, and the acquisition multiplies by it. Then EHVI gets a regret of {feas_on_40}, with {feas_gated} gated picks.
  We keep both results on the record. Without the feasibility model, the method is worse than chance.

### 17. Two levels: fewer expensive runs (17:30, 1.5 min)

- **Message:** {mf_answer}
- **Body:** From version 2, slide 16.
- **Presenter notes:** This is the two-level model. The cheap model runs at each design. SU2 must learn only a scale and a correction.
  Read the first row of the table. With {gp_n_lo} SU2 designs, the endurance error is {gp_two_lo} hours for the two-level model and {gp_single_lo} hours for SU2 alone. SU2 alone needs {mf_n_match} designs to get the same error.
  Go down the rows. The benefit decreases when SU2 has more designs. At {gp_n_hi} designs, SU2 alone is slightly better.
  Thus the benefit is real at small budgets. That is where it is important.
  Look at the coverage columns. Coverage is the part of the held-out designs inside the 90 % interval. It is below 0.9 for both models. Thus I use the mean, not the interval.

### 18. How much engineering time this saves (19:00, 1.5 min)

- **Message:** {grid_n} low-fidelity designs ran in {grid_hours} h; {su2_cases} SU2 cases ran in {su2_worker_h} worker-hours over {pool_wall_h} h of elapsed time; the two-level model reaches with 8 SU2 designs the error SU2 alone needs {mf_n_match} for.
- **Body:** From version 2, slide 17.
- **Presenter notes:** This slide shows the engineering time that the pipeline saves. Read the last column: what a person had to do.
  The low-fidelity grid ran {grid_n} designs in {grid_hours} hours on {grid_workers} workers. A person typed one command.
  The SU2 pool ran {su2_cases} cases in {su2_worker_h} worker-hours, over {pool_wall_h} hours of elapsed time. A person signed in to {n_runtimes} cloud runtimes. That was all the manual work.
  With {mf_n0} SU2 designs, the two-level model gets the error that SU2 alone needs {mf_n_match} designs for.
  We recorded {n_rulings} rulings. A person made each ruling when the data needed a judgment.
  The important point is not the speed of the computer. The loop runs at night, checks itself, and gives a person only the decisions that need judgment.

### 19. The expensive level against the cheap one (20:30, 1 min)

- **Message:** Of the {pool_designs} SU2 designs, {pool_complete} are complete; on every one the SU2 endurance is {hf_lf_end_range} against the low model's.
- **Body:** From version 2, slide 18.
- **Presenter notes:** This slide compares the expensive level with the cheap level on the SU2 pool. All {pool_complete} of {pool_designs} designs are complete.
  Each point is one design: SU2 endurance against low-fidelity endurance. The diagonal is agreement.
  All points are below the line. The SU2 endurance is {hf_lf_end_range} against the low model.
  That is a large difference, and I do not hide it. But the difference has the same sign on each design.
  A difference with one sign is easy for a scale and a correction to learn. That is why the two-level model works.

### 20. The front (21:30, 1 min)

- **Message:** {hf_front_answer}
- **Body:** From version 2, slide 19.
- **Presenter notes:** This is the front on the SU2 pool: endurance against take-off mass. Up and to the left is better.
  {hf_front_answer}
  The band comes from the Gaussian processes. It is a model band, not a measurement. Backup slide 40 shows that these intervals are too narrow.
  Beside it is the low-fidelity front. That front is exact, because the cheap model ran on the full grid of {grid_n} points.
  Each point on the SU2 front carries the lift-slope error against the tunnel.

### 21. The inverse query under the 4 kg cap (22:30, 1.5 min)

- **Message:** On the low model the answer is a box corner and the cap never binds; {hf_inverse_answer}
- **Body:** From version 2, slide 20.
- **Presenter notes:** The inverse query asks for the longest endurance below the {cap_kg} kg limit, with a high probability to stay below it.
  On the low model, the answer is a corner of the box. It predicts {inv_end} hours at a median mass of {inv_mtow} kg. The probability to stay below the limit is {inv_p}. The limit does not bind.
  On the SU2 pool, the answer moves away from the corner, and the cap now binds. The table gives the numbers.
  Thus the limit now binds. The cheap model never showed that.
  This is the value of the second level, in one slide.

### 22. Limits that travel with every number (24:00, 1.5 min)

- **Message:** One cruise point at sea level, a fixed propeller efficiency, a closed-form structure, and an SU2 lift-slope bias of {v6e_dev}: these bound what the front and the answer mean.
- **Body:** From version 2, slide 23.
- **Presenter notes:** Each number in this talk depends on these limits.
  The model has one cruise point, at sea level. It has no trim drag. The propulsive efficiency is fixed. The structure is a closed form.
  The section polar uses one Reynolds number for each design, at cruise. But the chord changes along the span.
  The kept pool cases drift by {pool_cl_drift} in lift and {pool_cd_drift} in drag.
  The most important limit is on the right. The SU2 lift slope has a bias of {v6e_dev} against the tunnel. Each SU2 polar carries this flag.
  The records contain these limits. I do not only say them here.

### 23. Conclusions (25:30, 2 min)

- **Message:** The pipeline runs the design loop unattended, refuses what it cannot check, and asks a person only for rulings; on this problem it cut the expensive runs at small budgets and answered the capped design question; one confirmation run passed and the final one found the endurance below its predicted interval, which is the honest limit of the surrogate.
- **Body:** From version 2, slide 24.
- **Presenter notes:** Four questions, and the records answer each one.
  First, the front. The exact low-fidelity front has {front_n} designs from {grid_n} points. The SU2 front is also complete, with its band and its bias.
  Second, active learning. On the pool, EHVI gets a regret of {ehvi_32} at 32 evaluations. Random is at {rand_40}. On the open box, plain EHVI is worse than random, and the feasibility weight makes it better, at {feas_on_40}.
  Third, the two-level model. With {mf_n0} SU2 designs, its endurance error is {gp_two_lo} hours against {gp_single_lo} for SU2 alone.
  Fourth, the inverse query. One confirmation passed. The final confirmation failed on endurance, and the mass stayed inside its interval. That is the honest limit of the surrogate.
  Thus the pipeline runs the loop without a person, refuses what it cannot check, and asks a person only for rulings.
  One idea to keep: put the checks after the solver, not only before it. And make each claim calculable from the records.

### 24. Questions (27:30 onward)

- **Message:** Discussion; the backup slides hold the detail behind every number.
- **Body:** New: likely questions and the slide that answers each, by number.
- **Presenter notes:** Thank you. I am glad to answer your questions.
  This table gives the questions that I expect, and the slide number that answers each one.
  When you ask a question, I open that slide. I do not describe it from memory.

## Backup slides (not timed)

### 26. Confirmation: does the prediction hold?

- **Message:** {confirm_v2_answer}
- **Body:** From version 2, slide 21.
- **Presenter notes:** A prediction has value only when we test it. Each confirmation run is one SU2 polar of five angles, at the answer of the inverse query. It goes through the same queue and checks as the pool.
  We set the pass condition before the run. Endurance and mass must both be inside their 90 % intervals, and the mass must be below the limit.
  There are two runs, because we calculated the answer twice. {confirm_v2_answer}
  Thus the final confirmation failed on endurance. The design flies for less time than the surrogate predicted.
  This agrees with the coverage results: the intervals are too narrow. I report it as a fail, with its direction.

### 27. What the flow looks like at stall

- **Message:** At 14 degrees the upper surface of pool design 0 is separated over most of the chord; this is the stall the cheap section model cannot show.
- **Body:** From version 2, slide 22.
- **Presenter notes:** This picture shows the flow: pressure contours and streamlines.
  At 14 degrees, the flow on the upper surface of pool design 0 is separated over most of the chord. Look at the streamlines behind the leading edge.
  The cheap section model cannot show this stall.
  The picture agrees with the numbers: after 10 degrees, lift decreases and drag increases.

Slide 25 is the "Backup" divider.

### 28. The vortex lattice and its checks
- **Body:** From version 2, backup 2.
- **Presenter notes:** This slide shows how we calculate the low-fidelity aerodynamics: a vortex lattice.
  Each panel has one horseshoe vortex. The bound vortex is on the quarter chord. The control point is on the three-quarter chord.
  The Biot-Savart law gives the velocity of each segment. The condition of no flow through the control points gives the circulations.
  We calculate the induced drag in the Trefftz plane. An earlier method under-counted it, and the elliptic-wing checks found the error.

### 29. Validation table, solver checks
- **Body:** From version 2, backup 3.
- **Presenter notes:** This table gives each validation row of the method itself.
  For the elliptic wing of aspect ratio 8, the span-efficiency error is {v6a_e_dev}, and the lift-slope error is {v6a_cla_dev}. Both are inside their tolerances.
  The moment row of the benchmark wing stays pending. Its reference point has no source yet.

### 30. Mass closure and the endurance balance
- **Body:** From version 2, backup 4.
- **Presenter notes:** Two parts give the endurance number.
  The first part is the mass closure. The battery mass is the battery fraction times the take-off mass. Thus the mass sum depends on itself. We solve it as a fixed point.
  The second part is the energy balance. The usable battery energy, less the climb energy, divided by the cruise power, gives the endurance.
  The nominal design closes in {nom_iters} iterations, at {nom_endurance} hours.

### 31. The airfoil mesh
- **Body:** From version 2, backup 5.
- **Presenter notes:** This is the airfoil mesh. It is a structured C-mesh around the section.
  The coarse mesh has {mesh_coarse_cells} cells, the medium mesh {mesh_medium_cells} and the fine mesh {mesh_fine_cells}.
  The first cell height comes from the chord Reynolds number. On this mesh it is {mesh_first_cell} m.
  Each mesh passes the quality gate before we stage a case. The worker checks its fingerprint before the run.

### 32. Two stopping rules: Cauchy stop and drift
- **Body:** From version 2, backup 6.
- **Presenter notes:** How do we know that a run converged? We use two rules, and they measure different things.
  The SU2 Cauchy stop examines lift and drag over a window of iterations, from iteration 500.
  My drift rule reads the history after the run. It measures how much lift and drag change in the last fifth.
  The first smoke case drifted {smoke_cl_drift} in lift and {smoke_cd_drift} in drag. The rerun stopped at iteration {smoke2_iters}.
  A run that stops at its budget gets a flag.

### 33. A solver history
- **Body:** From version 2, backup 7.
- **Presenter notes:** This is one solver history.
  The residual decreases by many orders of magnitude. If you look only at the residual, the run seems converged.
  But look at the shaded window, the last fifth of the run. Lift and drag still change there. The drift rule reads that window.
  A run that still changes gets a flag, also when the solver stopped correctly.

### 34. What the mesh does to the pressure distribution
- **Body:** From version 2, backup 8.
- **Presenter notes:** This figure shows three meshes on one axis, on the nominal section: coarse, medium and fine.
  The curves agree away from the leading edge. The differences are at the suction peak.
  The peak pressure coefficient is {mesh_coarse_peak} on the coarse mesh, {mesh_medium_peak} on the medium mesh and {mesh_fine_peak} on the fine mesh.
  One caution: the drift rule flags all three runs. Thus these differences include a convergence effect, not only a mesh effect.

### 35. The low-fidelity section against the tunnel
- **Body:** From version 2, backup 9.
- **Presenter notes:** How good is the cheap section model? Against the tunnel it is not good, and I say so.
  Its lift slope is {f_clalpha_range} low. Its profile drag is {f_cd_range} high. Its maximum lift is {f_clmax_range} high.
  The ledger lift effectiveness does not contain the tunnel value. That is a ruling. It is not a number to change here.

### 36. SU2 against the tunnel, and the decision to accept the bias
- **Body:** From version 2, backup 10.
- **Presenter notes:** Why did we accept a failed validation? Because the other option was to tune the error away.
  The lift slope fails at both Reynolds numbers: {v6e_dev} and {v6e_cla_hi}, against {v6e_tol}.
  The drag ratio passes at both: {v6e_cd_lo} and {v6e_cd_hi}, against 20 %.
  Decision 8 accepted the medium mesh with the bias recorded. The fail stays a fail.

### 37. Tunnel points at both Reynolds numbers
- **Body:** From version 2, backup 20.
- **Presenter notes:** This table compares the tunnel and SU2 at each point.
  At a Reynolds number of {e387_re}, the SU2 lift is {su2_cl_range}. The SU2 drag is from {su2_cd_range}.
  The second table gives the same comparison at the higher Reynolds number.

### 38. Section polars
- **Body:** From version 2, backup 13.
- **Presenter notes:** These are the section polars. The left plot is lift against angle. The right plot is drag against lift.
  The closed form is a straight line to a limit, with constant drag. It has no stall and no drag increase.
  SU2 shows the stall at the top of the angle range.
  Open circles are cases that the pool did not keep.

### 39. What the surrogate learned about the box
- **Body:** From version 2, backup 15.
- **Presenter notes:** Which inputs does the surrogate think are important?
  The left plot ranks the six inputs by the length scale of the endurance model. A short length scale means that endurance changes quickly along that input. Aspect ratio and span are first.
  The right map shows the region that passes the gates, over those two inputs, with the observed front.
  The map is a projection: it holds the other four inputs at one point. In this view, {n_front_edge} of the {n_front} front designs are within one cell of a gated cell.

### 40. Why a Gaussian process, and against what

- **Message:** With {mf_usable_high} SU2 designs a model must give an interval, not only a mean; on this data the GP corrected by the low model has the lowest endurance error {mf_two_best}.
- **Body:** New. Left: the reasons, each tied to how the study uses the model. Right: the GP relations. Below: every model compared on this study's data, from the two-level record, means over ten seeds.
- **Presenter notes:** Why a Gaussian process? There are four reasons, and each comes from how the study uses the model.
  First, the SU2 data are small. We have {mf_usable_high} SU2 designs. An exact Gaussian process fits this quantity in seconds.
  Second, the acquisition and the confirmation test need an interval, not only a mean. A Gaussian process gives an interval at each design.
  Third, each process has nine numbers: six length scales, two variances and a mean. The marginal likelihood sets them. Nobody tunes them by hand.
  Fourth, the length scales show which inputs are important. Backup slide 39 shows them.
  The table shows each model that we fitted on this data. The low model alone has an endurance error of {gp_lf} hours.
  With {gp_n_lo} SU2 designs, the Gaussian process on SU2 alone has an error of {gp_single_lo} hours. The two-level model has {gp_two_lo} hours.
  At {gp_n_hi} designs, the order changes: {gp_single_hi} hours for SU2 alone and {gp_two_hi} for the two-level model.
  We did not fit a neural network or a tree model on this data. This table is the full comparison in the record.
  The intervals cover less than 90 % of the held-out designs. Thus I use the mean, not the interval.

### 41. Hypervolume regret: what the replay slides measure
- **Message:** Regret is the share of the true front's hypervolume that the designs found so far do not cover: 0 when the whole front has been found, 1 when nothing of it has.
- **Body:** New. The true front of the 192-point pool with the area it dominates up to the reference point; the hypervolume and regret relations; mean regret by budget for each strategy, from the pool replay.
- **Presenter notes:** Regret measures how much of the true front a strategy has not found.
  Hypervolume is the area between a front and a reference point. The reference point is a little beyond the worst design. We measure endurance and the logarithm of mass.
  The figure shows the true front of the pool and its hypervolume, shaded.
  Regret is the true hypervolume, less the hypervolume of the designs found, divided by the true hypervolume. It is 1 when the strategy has found nothing of the front. It is 0 when it has found all of it.
  The table gives the mean regret for each strategy and budget. For example, at 16 evaluations EHVI has {reg_ehvi_16} and random has {reg_rand_16}.

### 42. The exact low-fidelity front
- **Body:** From version 2, backup 16.
- **Presenter notes:** How do we know that the low-fidelity front is exact? The cheap model ran at each grid point.
  The grid has {grid_n} points. The gates stopped {gated_n} of them.
  The exact front has {front_n} designs. The run took {grid_hours} hours on {grid_workers} workers.

### 43. Online replays, full tables
- **Body:** From version 2, backup 24.
- **Presenter notes:** These are the full tables of the open-box replay, at each budget.
  Plain EHVI ends at {ehvi_on_40} against {rand_on_40} for random. The feasibility-weighted version ends at {feas_on_40}.
  The lower table explains why. By 40 evaluations, plain EHVI has {ehvi_gated} gated picks. The weighted version has {feas_gated}.

### 44. Queue, workers and shards
- **Message:** Workers split the queue by a hash of the case id, so they never race for a case; a worker that dies leaves a heartbeat that goes stale, and its case is re-run.
- **Body:** From version 2, slide 10.
- **Presenter notes:** The queue is a shared folder of job files with status flags. Cloud machines cannot accept inbound connections. Thus the workers read the folder at intervals.
  Each worker takes only the cases whose identifier hash is in its own shard. Each case is in exactly one shard. The {pool_cases} pool cases divided into {shard_split} over two shards.
  Thus two workers never take the same case, and there is no lock.
  Each worker writes a heartbeat. When a worker stops, its heartbeat gets old, and the case runs again.
  To add a worker, change the number of shards. Nothing else changes.

### 45. Cost ledger
- **Body:** From version 2, backup 27.
- **Presenter notes:** What did it cost? The table gives the wall time of each mesh level, from the run records.
  The SU2 pool used {su2_worker_h} worker-hours. The low-fidelity grid took {grid_hours} hours on {grid_workers} workers.
  The run records give the wall time of each SU2 case. The table does not use estimates.

### 46. The endurance calculation, step by step

- **Message:** Endurance is the usable battery energy divided by the cruise power; for one low-pool design the model finds the take-off mass, the cruise point and the installed power, then divides.
- **Body:** New. The endurance relation at the top. A table with one row per step: the mass, the cruise point, the installed power, the usable energy and the endurance. The values are computed by the model's own code at build time, for design 48 of the low pool, and checked against its recorded endurance.
- **Presenter notes:** This slide shows how the model works out endurance for one design. The design is number 48 of the low pool. Read the table from top to bottom. Each row uses the result of the row above it.
  The model first finds the take-off mass. It adds the masses of the parts until the total no longer changes. The battery is a fixed fraction of that total.
  Next the model finds the cruise point. It tries many lift values and keeps the one that needs the least power. The power is drag times speed, divided by the propulsive efficiency.
  The installed power is the larger of two values: twice the cruise power, or the power to climb. The climb takes one minute, and that energy is taken away from the battery first.
  The endurance is the usable energy divided by the cruise power. The last row matches the recorded value of the design. The model has no reserve and no descent, so the value is an upper bound.

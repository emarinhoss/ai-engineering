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
- Each slide: **Message** (the subtitle, one sentence), **Body** (what the slide shows), **Speaker
  notes**. "From version 2" names the version-2 slide whose body is reused.

## Changes from version 2

1. Slides are named by number only.
2. The nominal design (version-2 backup 1) is in the main body, after the test problem.
3. Slide 2 sets up the problem and the motivation together.
4. The validation slide already carries the fine-mesh row (medium against fine, cd at cl 0.6); no
   other fine-mesh validation row is in the record, so the slide body is unchanged.
5. The queue, workers and shards slide moved to the backups.
6. New slide 15: why a Gaussian process, with every model compared on this study's data.
7. New backup: what hypervolume regret is.
8. Version-1 D26 (what runs in Claude Code, on Drive and on Colab) is in the main body, with its
   original labels.
9. The first smoke case is described as not converged (see the note on slide 13).
10. Slide 14 explains each sampling strategy in more detail.
11. Version-2 backups 11, 12, 14, 17, 18, 19, 21, 22, 23, 25, 26, 28, 29 and 30 are left out.

## Main body (about 32 minutes)

### 1. Title (0:00, 0.5 min)

- **Message:** An automated, gated simulation pipeline that sizes a small electric aircraft: what it does, what it caught, and how much engineering time it saves.
- **Body:** From version 2, slide 1 (status line computed from the records).
- **Speaker notes:** I built a pipeline that takes design questions to a CFD solver and back without a person in the loop for the routine steps, and that refuses to pass on a result it cannot check. I will show it on one aircraft, end to end.

### 2. The problem, and why it needs a pipeline (0:30, 1.5 min)

- **Message:** Size a small electric aircraft for endurance at a fixed {payload_kg} kg payload under the {cap_kg} kg cap of the EASA open-category class C2; every high-fidelity answer is slow, set up by hand, and can fail silently.
- **Body:** New. Top: the design question and the six inputs. Below: three columns, "slow", "manual", "silent", each with one line from the records.
- **Speaker notes:** Engineering design is a loop of propose, simulate, check, decide. The simulate step dominates the clock, and the check step is where people quietly lose days. The pipeline runs the loop unattended and checks every result before anyone sees it; slide 3 shows why the checking matters.

### 3. A clean exit is not a correct result (2:00, 1 min)

- **Message:** The first SU2 airfoil case exited with code {smoke_exit} after its whole {smoke_budget}-iteration budget, with lift {smoke_cl_off} and drag {smoke_cd_off} against its own properly stopped rerun; only checks after the solver could see it.
- **Body:** From version 2, slide 3.
- **Speaker notes:** This is the design principle of the whole pipeline. The solver said success. The numbers were wrong by double digits. So the pipeline treats the solver's exit code as a hint and decides convergence itself, from the history.

### 4. The test problem (3:00, 1 min)

- **Message:** Endurance against take-off mass at a fixed {payload_kg} kg payload, under the {cap_kg} kg cap of the EASA open-category class C2, over six design inputs.
- **Body:** From version 2, slide 4.
- **Speaker notes:** The aircraft is deliberately small so that every step can be run end to end. Six inputs span the box; everything else is fixed in a graded ledger, {n_ledger} quantities, {n_assumed} of them assumptions with a band.

### 5. The nominal design in one top view (4:00, 0.5 min)

- **Message:** The nominal design has a {nom_span} m span, aspect ratio {nom_ar} and taper {nom_taper}: {nom_area} m^2 of wing and a closed take-off mass of {nom_mtow} kg; tail and fuselage follow from the wing by rule.
- **Body:** From version 2, backup 1 (the top view with the six inputs labelled).
- **Speaker notes:** Span and aspect ratio fix the wing area, taper fixes the chords, and the tail is sized by volume coefficients with a fixed arm. The fuselage holds the payload and the battery; its position along the wing is schematic.

### 6. The pipeline at a glance (4:30, 1.5 min)

- **Message:** Requests enter through typed tools and gates, run on cloud workers through a shared queue, and come back through checks into versioned records that the surrogate learns from; the language model never chooses a design point.
- **Body:** From version 2, slide 5.
- **Speaker notes:** Read it left to right. Every arrow has a check on it. The two places a person is needed are marked: a ruling when the data force a judgment, and a sign-in when a cloud runtime has to be authorised.

### 7. The agent's interface: typed tools, not free text (6:00, 1 min)

- **Message:** The agent reaches the solver only through {n_tools} typed tools with strict schemas; the tools never run the solver, and every call is logged.
- **Body:** From version 2, slide 6.
- **Speaker notes:** A typed interface is what lets an agent drive engineering software safely: a malformed request is rejected with a message, not executed. The tools stage, submit, ingest and report; the solver runs elsewhere.

### 8. Gates before any solver (7:00, 1 min)

- **Message:** A design passes {n_gates} gates before any solver runs, and an airfoil case passes a mesh-quality gate; a gated design costs nothing.
- **Body:** From version 2, slide 7.
- **Speaker notes:** Gates are cheap pure functions. They turn an expensive failure into an instant refusal with the offending value in the message.

### 9. What runs where: Claude Code, Drive, Colab (8:00, 1 min)

- **Message:** Every request passes the same ordered checks before SU2 starts, and every result passes more before it becomes a record; the numbered marks show where.
- **Body:** Version-1 D26 drawing with its original labels (Claude Code and the MCP tools, the Drive queue folder, the Colab worker), file names replaced by plain words.
- **Speaker notes:** Claude Code and the typed tools run in the session; the solver runs on Colab, which cannot take inbound connections, so jobs go through a Drive folder and come back as files with a digest. The worker rebuilds the mesh and the configuration from the job's parameters and refuses a mismatch.

### 10. Two fidelity levels (9:00, 1 min)

- **Message:** A low-fidelity design costs {lf_s_core} s of one core; one SU2 angle costs a median {hf_coarse_min} min on the coarse mesh and {hf_medium_min} min on the medium mesh, and a design needs five angles.
- **Body:** From version 2, slide 8.
- **Speaker notes:** The two levels share everything except the section data, so the expensive level corrects the cheap one rather than replacing it. That is what makes the two-level model on slide 18 possible.

### 11. Validation before any machine learning (10:00, 1 min)

- **Message:** The solver's own checks pass ({n_pass} rows pass, {n_fail} fail); against the wind tunnel SU2's lift slope misses by {v6e_dev} against a {v6e_tol} tolerance, a fail that is kept and travels with every result.
- **Body:** From version 2, slide 9, which already carries the fine-mesh row.
- **Speaker notes:** Tolerances were fixed before the runs. The medium mesh is within a fraction of a percent of the fine mesh on drag, so the lift-slope miss is not a mesh effect. The miss was not tuned away: every SU2 result carries it as a flag in its own record.

### 12. The session runs the compute (11:00, 1.5 min)

- **Message:** The session starts, deploys, watches, rebalances and restarts the cloud runtimes itself; a person is needed only to authorise a runtime's storage and to rule on the data.
- **Body:** From version 2, slide 11.
- **Speaker notes:** Before, a person restarted workers by hand: when both runtimes ended at 14:10 UTC nothing ran until 15:50. Now the session starts and restarts runtimes through a command-line interface, sees a dead worker from its heartbeat, and re-splits the queue when one runtime drains.

### 13. What the checks caught (12:30, 1 min)

- **Message:** Each of these was found by a check or a recorded run before it reached a result.
- **Body:** From version 2, slide 12, with the first smoke case described as not converged.
- **Speaker notes:** None of these would have shown up as a solver error. The first case did not diverge: it ran its whole budget without settling, which is why it reads not converged here. They were caught because every result is checked and every claim is computed from the records.

### 14. How each strategy picks the next design (13:30, 1.5 min)

- **Message:** One Gaussian process on endurance and one on log take-off mass give a mean and an interval everywhere; five strategies use them differently to pick the next design, and the language model chooses nothing.
- **Body:** New, extending version-2 slide 13: a table of the five strategies (how each picks a point, and what it uses), the hypervolume and acquisition relations below it.
- **Speaker notes:** Random and the Latin hypercube use no model and are the baselines. Maximum variance explores where the model is least sure without asking whether a design is good. Expected hypervolume improvement weighs both, and the weighted version also asks whether the design will pass the gates.

### 15. Why a Gaussian process, and against what (15:00, 1.5 min)

- **Message:** With {mf_usable_high} SU2 designs a model must give an interval, not only a mean; on this data the GP corrected by the low model has the lowest endurance error {mf_two_best}.
- **Body:** New. Left: the reasons, each tied to how the study uses the model. Right: the GP relations. Below: every model compared on this study's data, from the two-level record, means over ten seeds.
- **Speaker notes:** The acquisition and the confirmation test both need an interval, which a GP gives at every point. The table is the whole comparison in the record: no neural network or tree model was fitted on this data. The intervals cover less than ninety percent of held-out designs, so I quote means.

### 16. Active learning on a fixed pool (16:30, 1 min)

- **Message:** On a 192-point pool, expected hypervolume improvement reaches regret {ehvi_32} at 32 evaluations, while random sampling is still at {rand_40} after 40.
- **Body:** From version 2, slide 14.
- **Speaker notes:** Regret is how much of the true front is still missing; backup slide 41 defines it. Active learning has the whole front at 32 evaluations; random sampling is still missing part of it after 40.

### 17. Active learning on the open box, honestly (17:30, 1.5 min)

- **Message:** On the open box plain expected improvement loses to random ({ehvi_on_40} against {rand_on_40}) because it keeps picking designs the gates reject; weighted by the probability of passing the gates it reaches {feas_on_40}.
- **Body:** From version 2, slide 15.
- **Speaker notes:** This is the result I lead with, because it includes a loss. The fix is a small feasibility model. Without it, the clever method is worse than chance.

### 18. Two levels: fewer expensive runs (19:00, 1.5 min)

- **Message:** {mf_answer}
- **Body:** From version 2, slide 16.
- **Speaker notes:** The cheap model runs everywhere; SU2 only has to learn the scale and a correction. The saving is large at small SU2 budgets and reverses by 24 designs, where SU2 alone is slightly better; neither model's interval is calibrated, so I quote the mean.

### 19. How much engineering time this saves (20:30, 1.5 min)

- **Message:** {grid_n} low-fidelity designs ran in {grid_hours} h; {su2_cases} SU2 cases ran in {su2_worker_h} worker-hours over {pool_wall_h} h of elapsed time; the two-level model reaches with 8 SU2 designs the error SU2 alone needs {mf_n_match} for.
- **Body:** From version 2, slide 17.
- **Speaker notes:** The point is not that the computer is fast. The point is that the loop runs overnight, checks itself, and hands a person only the decisions that need judgment.

### 20. The expensive level against the cheap one (22:00, 1 min)

- **Message:** Of the {pool_designs} SU2 designs, {pool_complete} are complete; on every one the SU2 endurance is {hf_lf_end_range} against the low model's.
- **Body:** From version 2, slide 18.
- **Speaker notes:** The direction is the same on every design, which is exactly what a two-level model can learn.

### 21. The front (23:00, 1 min)

- **Message:** {hf_front_answer}
- **Body:** From version 2, slide 19.
- **Speaker notes:** The low-fidelity front is exact because the cheap model ran on the whole grid; the SU2 front comes from the surrogate with its band.

### 22. The inverse query under the 4 kg cap (24:00, 1.5 min)

- **Message:** On the low model the answer is a box corner and the cap never binds; {hf_inverse_answer}
- **Body:** From version 2, slide 20.
- **Speaker notes:** The expensive level moves the answer off the corner and brings the cap into play, which the cheap model never showed. That is the value of the second level in one slide.

### 23. Confirmation: does the prediction hold? (25:30, 1.5 min)

- **Message:** {confirm_v2_answer}
- **Body:** From version 2, slide 21.
- **Speaker notes:** The pass condition was fixed before the run: both endurance and mass inside their ninety-percent intervals. A miss would be reported with its direction.

### 24. What the flow looks like at stall (27:00, 0.5 min)

- **Message:** At 14 degrees the upper surface of pool design 0 is separated over most of the chord; this is the stall the cheap section model cannot show.
- **Body:** From version 2, slide 22.
- **Speaker notes:** The picture is a sanity check on what the numbers say: lift falls and drag rises past 10 degrees.

### 25. Limits that travel with every number (27:30, 1.5 min)

- **Message:** One cruise point at sea level, a fixed propeller efficiency, a closed-form structure, and an SU2 lift-slope bias of {v6e_dev}: these bound what the front and the answer mean.
- **Body:** From version 2, slide 23.
- **Speaker notes:** Every number in this talk is conditional on these. They are written into the records, not just said here.

### 26. Conclusions (29:00, 2 min)

- **Message:** The pipeline runs the design loop unattended, refuses what it cannot check, and asks a person only for rulings; on this problem it cut the expensive runs at small budgets and answered the capped design question; one confirmation run passed and the final one found the endurance below its predicted interval, which is the honest limit of the surrogate.
- **Body:** From version 2, slide 24.
- **Speaker notes:** If I had to keep one idea: put the checks after the solver, not just before it, and make every claim computable from the records.

### 27. Questions (31:00 onward)

- **Message:** Discussion; the backup slides hold the detail behind every number.
- **Body:** New: likely questions and the slide that answers each, by number.
- **Speaker notes:** Open the slide that answers the question rather than describing it.

## Backup slides (not timed)

Slide 28 is the "Backup" divider.

### 29. The vortex lattice and its checks
- **Body:** From version 2, backup 2.
### 30. Validation table, solver checks
- **Body:** From version 2, backup 3.
### 31. Mass closure and the endurance balance
- **Body:** From version 2, backup 4.
### 32. The airfoil mesh
- **Body:** From version 2, backup 5.
### 33. Two stopping rules: Cauchy stop and drift
- **Body:** From version 2, backup 6.
### 34. A solver history
- **Body:** From version 2, backup 7.
### 35. What the mesh does to the pressure distribution
- **Body:** From version 2, backup 8.
### 36. The low-fidelity section against the tunnel
- **Body:** From version 2, backup 9.
### 37. SU2 against the tunnel, and the decision to accept the bias
- **Body:** From version 2, backup 10.
### 38. Tunnel points at both Reynolds numbers
- **Body:** From version 2, backup 20.
### 39. Section polars
- **Body:** From version 2, backup 13.
### 40. What the surrogate learned about the box
- **Body:** From version 2, backup 15.
### 41. Hypervolume regret: what the replay slides measure
- **Message:** Regret is the share of the true front's hypervolume that the designs found so far do not cover: 0 when the whole front has been found, 1 when nothing of it has.
- **Body:** New. The true front of the 192-point pool with the area it dominates up to the reference point; the hypervolume and regret relations; mean regret by budget for each strategy, from the pool replay.
- **Speaker notes:** Hypervolume is the area between the front and a reference point just beyond the worst design, measured with endurance and the logarithm of mass. Regret compares the area covered by the designs a strategy has run with the area of the true front, so it falls to zero exactly when the front has been found.
### 42. The exact low-fidelity front
- **Body:** From version 2, backup 16.
### 43. Online replays, full tables
- **Body:** From version 2, backup 24.
### 44. Queue, workers and shards
- **Message:** Workers split the queue by a hash of the case id, so they never race for a case; a worker that dies leaves a heartbeat that goes stale, and its case is re-run.
- **Body:** From version 2, slide 10.
- **Speaker notes:** The queue is a shared folder of job files with status flags. Sharding by hash means adding a worker is a configuration change, not a coordination problem.
### 45. Cost ledger
- **Body:** From version 2, backup 27.

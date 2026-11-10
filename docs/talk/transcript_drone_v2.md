# Transcript: the drone deck, version 2

This is a transcript of the 30-minute talk on version 2 of the drone deck, written as I would say it on Friday 13 November 2026, with the records as they stood on 2026-11-10: the SU2 pool is complete and both confirmation runs have landed. The main body runs to about 28 minutes, which leaves room for questions; the backup slides are opened only when a question asks for one.

## Slide 1 — V1: A gated, automated design pipeline

*0:00, 0.5 min*

I built a pipeline that takes design questions to a CFD solver and back, without a person in the loop for the routine steps. And it refuses to pass on a result it cannot check. I will show it on one small electric aircraft, end to end. The status line at the bottom is computed from the records: the SU2 pool is 32 of 32 designs complete. One confirmation passed. The final one failed. I will show you both.

## Slide 2 — V2: The engineering problem

*0:30, 1 min*

Engineering design is a loop. Propose, simulate, check, decide. The simulate step dominates the clock, and the check step is where people quietly lose days.

Look at the three columns. Slow: one SU2 angle costs a median of 11.8 minutes on the coarse mesh, and a design needs five angles. Manual: every case needs a mesh, a configuration and a check written for it. In this pipeline, a low-fidelity design costs 0.25 seconds of one core, and an SU2 case is staged by a typed tool call, one of 11 tools. Silent: a solver that stops cleanly can still hand back the wrong numbers. The first SU2 case exited with code 0, and its lift and drag were 10.5 percent and 24.7 percent off.

The pipeline attacks both problems. It runs the loop unattended, and it checks every result before anyone sees it.

## Slide 3 — V3: A clean exit is not a correct result

*1:30, 1 min*

This is the design principle of the whole pipeline, so I show it early.

The first SU2 airfoil case exited with code 0. It ran its whole budget of 3,000 iterations and wrote all its files. The solver said success. But against its own properly stopped rerun, its lift was 10.5 percent low and its drag 24.7 percent high.

Follow the chain on the right. The postprocess step looked for the compressible residual, rms of rho, and recorded an error. Then the drift rule on the history showed lift moving 5.6 percent and drag 17.4 percent over the last fifth of the run. The ruling was a budget of 6,000 iterations with a Cauchy stop, and the rerun stopped itself at 4,867.

So the pipeline treats the solver's exit code as a hint. It decides convergence itself, from the history.

## Slide 4 — V4: The test problem

*2:30, 1 min*

The test problem is a small electric aircraft. The trade is endurance against take-off mass, at a fixed payload of 0.5 kilograms. The vertical line on the figure is the cap of the EASA open-category class C2: 4 kilograms. The requirement is a probability of at least 0.9 of being under it, and that was fixed before any run.

Six inputs span the box, in the table: span from 1.2 to 3 meters, aspect ratio from 6 to 16, taper from 0.3 to 1, battery fraction from 0.2 to 0.45, camber from 0 to 6 percent, and thickness from 8 to 15 percent.

Everything else is fixed in a graded ledger: 46 quantities, 21 of them assumptions with a band. And notice one thing: the heaviest low-pool design is 3.57 kilograms. So only SU2 tests the cap.

## Slide 5 — V5: The pipeline at a glance

*3:30, 1.5 min*

This is the whole pipeline in one drawing. Read it left to right.

On the left is the agent. It does not touch the solver. It calls typed tools, and every request goes through gates first. A design that fails a gate stops here, with a message, and costs nothing.

A request that passes becomes a job file in a shared queue. Cloud workers pick jobs off that queue. They are sharded, so two workers never take the same case, and the session itself starts and restarts them.

When a worker finishes, the result does not go straight into the study. It goes through checks after the run: did it converge, by my rule and not the solver's, and is the file what it claims to be. Then it is ingested with a hash into a versioned run record.

The surrogate learns from those records, and an acquisition function proposes the next batch. That closes the loop. Note that the language model never chooses a design point.

Every arrow has a check on it. The two places a person is needed are marked. A ruling, when the data force a judgment. And a sign-in, when a cloud runtime has to be authorised. Everything else runs unattended.

## Slide 6 — V6: The agent's interface: typed tools, not free text

*5:00, 1 min*

The agent reaches the solver only through 11 typed tools with strict schemas. They are listed on the left: validate a configuration, create a case, submit, status, list results, queue and export a batch, record a transfer, ingest a result or an error, and postprocess. The tools stage, submit, ingest and report. They never run the solver; that happens elsewhere.

A typed interface is what lets an agent drive engineering software safely. A malformed request, with an unknown field or a wrong type, is rejected with a message, not executed. Nothing is staged when a check fails. And every call writes an audit line.

The right column is honest about what does not depend on this interface. The worker reruns the physics gates and re-checks the mesh fingerprint and the configuration hash. The digest is checked at ingest. And the sampling points come from design tables and acquisition code, never from the language model.

## Slide 7 — V7: Gates before any solver

*6:00, 1 min*

A design passes 5 gates before any solver runs. Read down the table. One, the cruise Reynolds number must be between 80,000 and 500,000, where the section data are validated. Two, stall margin: cruise speed at least 1.3 times stall speed, and cruise lift coefficient at most 0.7 of the maximum. Three, mass closure: structure and propulsion at least 0.15 of take-off mass, solved as a fixed point in at most 100 iterations. Four, a manufacturing floor, tip chord at least 0.08 meters, and a wing loading between 20 and 150 newtons per square meter. Five, lattice panels with an aspect ratio of at most 20.

An airfoil case also passes a mesh-quality gate: no inverted cells, a minimum angle of 40 degrees, growth at most 1.25.

These are cheap pure functions. In the low-fidelity grid, 72,009 of 531,441 designs were stopped here, each with the offending value in its message.

## Slide 8 — V8: Two fidelity levels

*7:00, 1 min*

There are two fidelity levels. The low level uses closed-form section data: thin-airfoil lift and flat-plate drag. It costs 0.25 seconds per design per core. The whole 531,441-point grid ran in 4.7 hours on 8 workers, and the 192-point pool in 669 seconds.

The high level runs SU2 on the design's own section, at its cruise Reynolds number, on a cloud machine with 2 or 4 ranks. Per angle, the median is 11.8 minutes on the coarse mesh, over 173 cases, and 22.9 minutes on the medium mesh, over 30 cases. A design needs five angles. The SU2 pool itself is 172 cases.

The point of the table is the last line. Both levels share the geometry, the lattice, the closure and the mission. Only the section data differ. So the expensive level corrects the cheap one rather than replacing it. That is what makes the two-level model possible later in the talk.

## Slide 9 — V9: Validation before any machine learning

*8:00, 1 min*

Validation came before any machine learning, and the tolerances were fixed before the runs.

Look at the top group. The solver's own checks: 12 rows pass and 0 fail. That is the vortex lattice against closed forms, a benchmark wing, lattice refinement, and the mass closure and energy balance. One row is pending, because its reference point is not yet sourced.

Now the bottom group, SU2 against the wind tunnel. The drag ratio passes at both Reynolds numbers: 7.99 percent and 5.74 percent, against 20. The lift slope fails at both: 5.49 percent and 6.44 percent, against a 5 percent tolerance. Two rows were not run.

Decision 8 accepted the medium mesh as the high level, with the bias recorded. That is not a pass. The fail stays a fail. The miss was not tuned away: every SU2 result carries it as a flag in its own record.

## Slide 10 — V10: Queue, workers and shards

*9:00, 1 min*

The queue is a shared folder of job files with status flags. Cloud machines cannot take inbound connections, so the workers poll it.

The figure shows how the workers avoid racing. Each worker takes only the cases whose id hashes into its own shard. Every case id lands in exactly one shard. In the pool, the 172 cases split 85 and 87 over two shards. So no two workers ever pick up the same case, and there is no lock to get wrong.

Each worker also writes a heartbeat. A worker that dies stops writing, its heartbeat goes stale, and its case is re-run.

Sharding by hash means that adding a worker is a configuration change, not a coordination problem. Adding one changes N, the number of shards, and nothing else.

## Slide 11 — V11: Version 2: the session runs the compute

*10:00, 1.5 min*

This is what version 2 changed. The figure is a timeline of the pool day, read from the run records. Across the top, cases finished over time. Below, the live workers. The breaks are where a runtime ended and was restarted.

Before, a person restarted workers by hand. When both runtimes ended at 14:10 UTC, nothing ran until 15:50. That gap is pure waste: no solver, no checks, just a queue waiting for someone to notice.

Now the session does that work. It starts and deploys the cloud runtimes through a command-line interface. It watches the heartbeats, so it sees a dead worker without anyone looking. It restarts the runtime. And when one runtime drains its shard while the other still has a queue, it re-splits the shards so that neither sits idle.

You can read those re-splits on the figure. A worker id is a runtime and its shard, for example one of two. A new shard suffix on the same runtime marks a re-split of the queue.

A person is still needed in two places: to authorise a runtime's storage with a sign-in, and to rule on the data. The runtime log lists every action the session took.

## Slide 12 — V12: What the checks caught

*11:30, 1 min*

Each row here was found by a check or a recorded run before it reached a result.

The postprocess looked for the wrong residual, and the first case failed there. It was also unconverged, with lift drift 5.6 percent and drag drift 17.4 percent, which led to the budget of 6,000 with a Cauchy stop. A fine mesh did not reproduce at the 1 nanometer fingerprint, and the worker refused it. A fine mesh had 8 inverted cells, caught by the inversion gate. The point-vortex induced drag under-counted, caught by the elliptic-wing rows. A volume file declared 22,102 nodes and held more rows; one case is still unreadable, and nothing is drawn from it.

The last row is my own claim: the pool was planned on one 4-rank worker. The records say 72 pool cases ran on 2 ranks and 100 on 4. None of these would have shown up as a solver error.

## Slide 13 — V13: Surrogate and acquisition

*12:30, 1 min*

The surrogate is what turns a few hundred expensive runs into a map of the whole design space.

There are two Gaussian processes. One models endurance. The other models the log of take-off mass. The six inputs are scaled to the unit interval, from zero to one. Each process gives a mean and an interval everywhere in the box.

The table lists the strategies that pick the next design. Random takes a uniform draw. Latin hypercube follows an order fixed by the seed. Max-variance takes the design with the largest summed scaled variance. EHVI takes the largest expected hypervolume improvement: how much a new point is expected to add to the area dominated by the front. And the last row multiplies that by the probability of being feasible. You will see why that row exists in two slides.

The language model calls tools. It never picks a point.

## Slide 14 — V14: Active learning on a fixed pool

*13:30, 1 min*

First the easy case: a fixed pool of 192 points, smooth, with no gates.

The figure shows hypervolume regret, the share of the true front that is still missing, against the number of evaluations. It is a mean over 10 seeds, and every strategy of a seed starts from the same 8 points, so all four start at 0.285.

Follow the EHVI line. At 16 evaluations it is at 0.034, at 24 at 0.012, and at 32 it reaches 0.000: it has the whole front. Random is still at 0.118 after 40. Latin hypercube is at 0.107 after 40, and max-variance at 0.062.

So on a smooth pool active learning wins clearly. But this is the easy case, and I would not lead with it.

## Slide 15 — V15: Active learning on the open box, honestly

*14:30, 1.5 min*

This is the result I lead with, because it includes a loss.

On the open box, the whole six-input space with its gates, plain EHVI loses to random. Regret at 40 evaluations is 0.317 for EHVI against 0.294 for random. The clever method is worse than chance.

The reason is in the last column of the table, gated picks. EHVI made 29.7 picks on average that the gates rejected. Random made 1.9. The front lies against the gated edge, and the Gaussian processes do not know the gates. So EHVI keeps reaching for the edge and keeps landing on designs that cannot be built. Max-variance has the same problem: 0.353 regret, 25.4 gated picks.

The fix is a small feasibility model: a classifier for the probability of passing the gates, multiplied into the acquisition. Weighted that way, EHVI reaches 0.092 with only 7.5 gated picks. That is the best line on the figure.

Both runs are published. Neither replaces the other. The loss stays on the slide, because without the feasibility model this is what the method does.

## Slide 16 — V16: Two levels: fewer expensive runs

*16:00, 1.5 min*

This is the two-level model. The cheap model runs everywhere. SU2 only has to learn a scale and a correction surface on top of it.

Read the first row of the table. With 8 SU2 designs, the endurance error is 0.824 hours for the two-level model against 1.525 hours for SU2 alone. SU2 alone needs 24 designs to reach that. On take-off mass the gap is larger still: a relative error of 0.0022 against 0.0869.

Now go down the rows. The saving shrinks as SU2 gets more designs, and by 24 it reverses: SU2 alone is at 0.704 hours and the two-level model at 0.726. So SU2 alone is slightly better there. The saving is real at small budgets, which is where it matters.

The coverage columns are the honest part. Coverage is the share of held-out designs inside the 90 percent interval. With 8 designs it is 0.43 for SU2 alone and 0.61 for the two-level model; at 24 it is 0.78 and 0.69. It is below 0.9 for both models. Neither interval is calibrated, so I quote the mean, not the interval. These are means over ten seeds.

## Slide 17 — V17: How much engineering time this saves

*17:30, 1.5 min*

This is what the pipeline buys in engineering time. Read the table by its last column, what a person had to do.

The low-fidelity grid: 531,441 designs in 4.7 hours on 8 workers. A person ran one command.

The SU2 pool and its bias check: 172 cases, 37.0 worker-hours, over 24.9 hours of elapsed time. A person signed in to 6 cloud runtimes. That was the whole manual part.

The two-level model: with 8 SU2 designs it reaches the endurance error that SU2 alone needs 24 designs for. Nothing manual; it is computed from the records.

And the rulings: 10 recorded, each made when the data forced a judgment. A person read the evidence and decided.

The runtimes are counted from the worker ids in the SU2 records, and the rulings from the decision headings of the task ledger, so this table is computed, not remembered.

The point is not that the computer is fast. The point is that the loop runs overnight, checks itself, and hands a person only the decisions that need judgment.

## Slide 18 — V18: The expensive level against the cheap one

*19:00, 1 min*

Now the expensive level against the cheap one, on the SU2 pool. Of the 32 SU2 designs, 32 are complete.

On the figure, each point is one design: SU2 endurance against low-fidelity endurance. The diagonal is agreement. Every point sits below the line. SU2 endurance is 15.8 to 65.5 percent low against the low model's. The largest gaps are design 30 at 65.5 percent low, design 19 at 59.5, and design 17 at 58.0.

That is a large disagreement, and I do not hide it. But look at its shape: the direction is the same on every design. A gap of one sign is exactly what a scale and a correction surface can learn. That is why the two-level model works.

## Slide 19 — V19: The front

*20:00, 1 min*

This is the front on the SU2 pool: endurance against take-off mass, and you want to be up and to the left.

The observed front has 13 designs. It runs from 2.95 hours at 1.09 kilograms up to 8.40 hours at 3.14 kilograms. The shaded band is the posterior of the Gaussian processes. It is a model band, not a measurement, and the coverage results showed that these intervals run narrow.

Beside it is the low-fidelity front. That one is exact, because the cheap model ran on the whole grid. The SU2 front comes from the surrogate, with its band.

And every point on this front carries the decision-8 bias: the lift-slope miss against the tunnel.

## Slide 20 — V20: The inverse query under the 4 kg cap

*21:00, 1.5 min*

The inverse query asks for the longest endurance under the 4 kilogram cap, with a high required probability of meeting it.

The top half of the table is the low model. Its answer is a box corner: span 3 meters, aspect ratio 16, taper 0.3, battery fraction 0.45, camber 6 percent, thickness 8 percent. It predicts 13.307 hours, with a 90 percent interval from 13.228 to 13.386, at a median mass of 2.435 kilograms. The probability of being under the cap is 1.000. Evaluated directly, the low model gives 13.245 hours and 2.438 kilograms, inside both intervals. The cap never binds.

The bottom half is the SU2 pool. The answer moves off the corner. The span stays at 3 meters, taper at 0.3 and battery fraction at 0.45, but the aspect ratio drops to 7, camber to 3.9 percent, and thickness rises to 10.8 percent. It predicts 10.139 hours, with an interval from 9.116 to 11.163, at a median mass of 3.918 kilograms, interval 3.862 to 3.975. The probability of being under 4 kilograms is 0.991.

So the cap now binds. The cheap model never showed that. That is the value of the second level in one slide.

## Slide 21 — V21: Confirmation: does the prediction hold?

*22:30, 1.5 min*

A prediction is only worth something if you test it. Each confirmation run is one SU2 polar, five angles, at the answer of the inverse query, sent through the same queue and checks as the pool. The pass condition was fixed before the run: endurance and mass both inside their ninety-percent intervals, and the mass under the cap.

There are two runs, because the answer was computed twice. The first answer came from the pool at 30 designs. It predicted 9.334 hours, with an interval from 8.596 to 10.073. SU2 gave 9.951 hours: inside. Mass was predicted at 2.953 kilograms, interval 2.919 to 2.988, and SU2 gave 2.963: inside. That run passed.

The second is the final answer, on all 32 designs, the one from the last slide. It predicted 10.139 hours, interval 9.116 to 11.163. SU2 gave 8.955 hours. That is below the interval. The mass held: predicted 3.918, interval 3.862 to 3.975, and SU2 gave 3.936, inside and under the cap.

So the final confirmation failed, on endurance, and the miss is low: the design flies for less time than the surrogate promised. That is consistent with the coverage results. The intervals are over-confident. I report this as a fail, with its direction.

## Slide 22 — V22: What the flow looks like at stall

*24:00, 0.5 min*

One picture of the flow, pressure contours and streamlines. At 14 degrees, the upper surface of pool design 0 is separated over most of the chord. Look at the streamlines leaving the surface behind the leading edge. This is the stall that the cheap section model cannot show. It is a sanity check on what the numbers say: past 10 degrees, lift falls and drag rises.

## Slide 23 — V23: Limits that travel with every number

*24:30, 1.5 min*

Every number in this talk is conditional on these limits.

The model has one cruise point, at sea level. It has no trim drag. Skin friction on the non-wing parts is fully turbulent above a Reynolds number of five hundred thousand. The propulsive efficiency is fixed. The structure is closed-form. And the section polar is computed at one Reynolds number per design, the cruise one, while the wing's chord varies along the span.

Two more come from the data. The kept pool cases drift by 0.4 to 12.6 percent in lift and 0.0 to 7.5 percent in drag. And the ledger's section lift effectiveness is 0.75, with a band from 0.6 to 0.9; the tunnel value lies outside that band, and that ruling is still open.

On the right is the most important one. SU2's lift slope is biased by 5.49 percent against the tunnel. The flags at the bottom are carried by every SU2 section polar: the lift-slope fail and the drag-ratio pass, at both Reynolds numbers, and the ruling that accepted it.

These are written into the records, not just said here.

## Slide 24 — V24: Conclusions

*26:00, 2 min*

Four questions, each answered from the records.

One, the front. The exact low-fidelity front has 249 designs over 531,441 points. The SU2-level front is done too, with its band and its bias.

Two, active learning. On the pool, EHVI reaches regret 0.000 at 32 evaluations, while random is at 0.118 at 40. On the open box, plain EHVI loses, 0.317 against 0.294, and weighted by the probability of being feasible it wins, at 0.092. That is answered on the low level.

Three, the two-level model. With 8 SU2 designs the endurance error is 0.824 hours against 1.525 for SU2 alone, which needs 24 designs to match it. Both intervals under-cover.

Four, the inverse query. On the low level the answer is a box corner at 13.31 hours, and the cap does not bind. On the SU2 pool it is 10.14 hours at 3.92 kilograms, with a probability of 0.991. The answer on 30 designs passed its confirmation. The answer on 32 designs failed: its endurance came in below the predicted interval, while its mass held. That is the honest limit of the surrogate.

What version 2 changed: the cloud runtimes are managed from the session. The records show 13 worker ids on 6 runtimes.

So the pipeline runs the loop unattended, refuses what it cannot check, and asks a person only for rulings.

If I had to keep one idea: put the checks after the solver, not just before it. And make every claim computable from the records.

## Slide 25 — V25: Questions

*28:00 onward*

Thank you. I am happy to take questions. This table lists the questions I expect, and the backup slide that answers each: how the solver was validated, how I know a run converged, what the mesh does, how good the low-fidelity model is, which assumptions move the answer, what went wrong first and who decided, what it cost, and where the equations come from. When you ask, I will open the backup rather than describe it.

## Slide 26 — Section divider: Backup

These are the backup slides. I open one only when a question asks for it.

# Backup slides (only if asked)

## Slide 27 — B1: The nominal design in one top view

"What does the aircraft actually look like?" This is the nominal design in one top view. It sits in the middle of the box: a straight, tapered wing with no sweep, a fuselage carrying the battery and the payload, and a tail. Everything the pipeline varies is the wing and the battery fraction; the rest is fixed by the ledger.

## Slide 28 — B2: The vortex lattice and its checks

"How is the low-fidelity aerodynamics computed?" With a vortex lattice. Each panel carries one horseshoe vortex, with the bound vortex on the quarter chord and the control point on the three-quarter chord. The Biot-Savart law gives each segment's velocity, and the no-flow condition at the control points gives the circulations. The induced drag comes from the Trefftz plane, not from a sum at the panel midpoints, because the midpoint version under-counted, and the elliptic-wing checks caught it.

## Slide 29 — B3: Validation table, solver checks

"How was the solver validated, row by row?" Here are the rows. The elliptic wing of aspect ratio 8 has a span efficiency of 0.9974 against 1, a deviation of 0.26 percent against a 1 percent tolerance. Its lift slope is 4.81 against Helmbold's 4.906, 1.95 percent off against 3. The benchmark wing's lift slope is 1.01 percent off against 2. Its moment row stays pending.

## Slide 30 — B4: Mass closure and the endurance balance

"Where does the endurance number come from?" From two pieces. First, the mass closure. Battery mass is the battery fraction times take-off mass, so the mass sum feeds back on itself and is solved as a fixed point. Second, the energy balance: the usable battery energy, minus the climb, divided by the cruise power, gives the endurance. Both are checked to close.

## Slide 31 — B5: The airfoil mesh

"What does the SU2 mesh look like?" This is the airfoil mesh, around the section and close in at the leading and trailing edges. The first cell height is set for a target y plus from the chord Reynolds number. Every mesh passes the quality gate before a case is staged, and the worker checks its fingerprint before it runs.

## Slide 32 — B6: Two stopping rules: Cauchy stop and drift

"How do you know a run converged?" Two rules, and they measure different things. SU2's Cauchy stop watches lift and drag over 200 iterations, to a tolerance of one in a hundred thousand, starting at 500. My drift rule reads the history afterwards. The first smoke case drifted 5.62 percent in lift and 17.38 in drag; the rerun stopped at 4867. A run that ends on its budget is flagged.

## Slide 33 — B7: A solver history

"What does a solver history look like?" This is one history. On the residual alone it looks converged: the residual drops by orders of magnitude. But look at the shaded window, the last fifth of the run. Lift and drag are still moving there, and that is exactly what the drift rule reads. A run that is still moving is flagged, even when the solver exited cleanly and the residual looks fine.

## Slide 34 — B8: What the mesh does to the pressure distribution

"Does the mesh change the answer?" This figure puts three meshes on one axis, on the nominal section: coarse, medium and fine. The curves agree away from the leading edge, and the differences sit at the suction peak. One caution: all three runs were flagged as not converged by the drift rule, so these differences mix mesh and convergence, and I would not read them as mesh error alone.

## Slide 35 — B9: The low-fidelity section against the tunnel

"How good is the cheap section model?" Against the tunnel it is poor, and I say so. Its lift slope is 22.6, 19.1 and 20.2 percent low at the three Reynolds numbers. Profile drag is 52.0, 47.5 and 43.4 percent high. Its maximum lift is about 12.2 to 13.5 percent high. The ledger's lift effectiveness does not contain the tunnel value; that is a ruling, not a number to move here.

## Slide 36 — B10: SU2 against the tunnel, and the decision to accept the bias

"Why did you accept a failed validation?" Because the alternative was to tune it away. The lift slope fails at both Reynolds numbers, 5.49 and 6.44 percent against 5. The drag ratio passes, 7.99 and 5.74 against 20. Per point, lift is 8.0 to 11.6 percent high. Decision 8 accepted the medium mesh with the bias recorded. The fail stays a fail.

## Slide 37 — B11: Tunnel pressure distributions

"What does the validation section look like in pressure?" These panels are the tunnel airfoil at one Reynolds number, one panel per angle, with the upper surface solid. The suction peak deepens as the angle rises. Look for the kink in the upper-surface curve: it moves forward with angle. All of these cases are flagged not converged by the drift rule, and each panel title says so.

## Slide 38 — B12: Where the wall shear reverses

"Does SU2 see a separation bubble?" This figure shows the skin friction along the chord. Where it goes negative, the wall shear points upstream, which marks reversed flow. That stretch sits where the pressure panels showed the kink, and it moves forward as the angle rises.

## Slide 39 — B13: Section polars

"What do the polars look like across the pool?" On the left is lift against angle, on the right drag against lift, for SU2, the closed form and the tunnel. The closed form is a straight line to a cap with a constant drag: no stall and no drag rise. Now look at the pool designs at the top of the angle range: SU2 shows the stall there. Open circles are cases the pool did not keep.

## Slide 40 — B14: The stall at 14 degrees, pressure

"What does the stall look like in pressure?" This is the 14 degree case. The suction peak at the leading edge has collapsed, and the pressure is nearly flat over most of the upper surface. That flat region is the separated flow from the main talk. The cheap section model has no way to produce it.

## Slide 41 — B15: What the surrogate learned about the box

"Which inputs does the surrogate think matter?" On the left, the six inputs ranked by the length scale of the endurance model. A short length scale means endurance changes fast along that input, and aspect ratio and span come first. The map on the right shows the region that passes the gates over those two inputs, with the observed front on top. It is a projection: the other four inputs are held at one point.

## Slide 42 — B16: The exact low-fidelity front

"How do you know the low-fidelity front is exact?" Because the cheap model ran on every grid point: 531,441 points, 459,432 clean, 72,009 gated, 0 failed. The exact front is 249 designs. That took 16747 seconds on 8 workers. The low pool is 192 designs, 0 gated, with a front of 15, in 669 seconds.

## Slide 43 — B17: Bias sweep at the answer

"Which assumptions move the answer most?" This is a sweep, one quantity at a time, to each end of its ledger band. At the low-fidelity answer, the largest are skin areal density at 17.2 percent, propulsive efficiency at 17.0 and pack specific energy at 16.7. At the SU2-pool answer, skin areal density rises to 22.0 percent. Structure, propulsion and battery dominate, not aerodynamics.

## Slide 44 — B18: Coarse against medium on the pool

"Is the coarse mesh good enough for the pool?" On the pool designs run on both meshes, lift ratios lie between 0.9948 and 1.0280, and drag ratios between 0.9454 and 1.0157. On the nominal section, coarse is 0.7 percent and 1.1 percent off the fine mesh in lift and drag, at 498 seconds against 3,162. That is why the pool runs coarse.

## Slide 45 — B19: What the record keeps that was wrong first

"What did you get wrong?" Several things, and the record keeps them. My ledger said SU2 drags were 3 to 10 percent low; per point they are 10.3 percent low to 1.6 percent high. A lattice check compared a rectangular wing to the elliptic slope. The fingerprint was too tight at 1 nanometer. The first budget was 3,000. Each is corrected, not overwritten.

## Slide 46 — B20: Tunnel points at both Reynolds numbers

"Can I see the tunnel comparison point by point?" Here it is, at 203,800 and 305,200. At the lower Reynolds number, SU2's lift is 8.0 to 11.6 percent high, and its drag goes from 10.3 percent low to 1.6 percent high. At the higher one, lift is 8.0 to 12.7 percent high, and drag 7.5 percent low to 2.3 percent high.

## Slide 47 — B21: Budget-exhausted runs and the ruling on them

"What happened to runs that hit their budget?" They are listed here, and almost all were not kept. Drifts of tens of percent at angles near zero lift are the division by a small lift in the drift rule. A ruling kept the budget-exhausted runs for pool designs 8 and 28, and one confirmation case. The rule for every other run is unchanged.

## Slide 48 — B22: The low-fidelity Pareto record

"What went into the low-fidelity front record?" All 192 of 192 training rows. 4,096 candidates kept of 4,544 drawn: 420 failed the closed-form gates and 4 the full gates. The observed front is 15 designs, from 3.47 hours at 0.953 kilograms to 11.71 hours at 2.283. The length scales show aspect ratio, at 5.49, as the input the surrogate finds most active.

## Slide 49 — B23: The inverse query record

"How was the inverse query searched?" On a grid of 21 to the sixth, 85,766,121 points; 76,587,147 pass the closed-form gates. The query is a probability of at least 0.9 of being under 4 kilograms. On the low pool the answer is 13.307 hours, at a median of 2.435 kilograms, and the closure gates pass at the answer. The interval is predictive and includes noise.

## Slide 50 — B24: Online replays, full tables

"Can I see the open-box replay at every budget?" These are the full tables. Plain EHVI never beats random by much and ends at 0.317 against 0.294. The feasibility-weighted version pulls ahead from 12 evaluations, at 0.314, and ends at 0.092. The lower table explains it: plain EHVI accumulates 29.7 gated picks by 40, against 7.5 for the weighted one.

## Slide 51 — B25: The decision log

"Who decided what, and when?" Every ruling is mine, and each is recorded with its time. Decision 6 set the budget to 6,000 with a Cauchy stop. Decision 7 staged the SU2 pool, 32 designs at five angles. Decision 8 accepted the medium mesh with the bias recorded. Decision 9 accepted the budget-exhausted runs for designs 8 and 28. Decision 10 admitted the 14 degree run; the confirmation result was unchanged.

## Slide 52 — B26: Ledger provenance

"Where do the fixed numbers come from?" From a graded ledger of 46 quantities: 17 published, 8 derived, 21 assumed, and all 21 assumed ones carry a band. The loader refuses a quantity without a source, and an assumed one without a band that contains its value. The validation data are kept apart and not counted.

## Slide 53 — B27: Cost ledger

"What did it cost?" The coarse mesh: 173 cases, a median of 705 seconds, 35.7 worker-hours. The medium mesh: 30 cases, a median of 1,372 seconds, 11.5 worker-hours. One fine case took 3,162 seconds. The pool cases alone used 31.9 worker-hours. The low-fidelity grid took 4.65 hours on 8 workers, and the low pool 669 seconds.

## Slide 54 — B28: Equations

"Where do the equations come from?" This is an index: each relation in the talk and the slide that uses it. The lattice relations, Biot-Savart and the Trefftz-plane drag, are on B2. The mass closure and energy balance are on B4. The Gaussian process, the kernel and the acquisition functions are on V13 to V15, and the two-level model on V16.

## Slide 55 — B29: Open rulings

"What is still undecided?" Three rulings. The first, on budget-exhausted runs, was decided for designs 8 and 28 only. The second is open: the section lift-effectiveness band, 0.75 in a band from 0.6 to 0.9, while the closed-form lift slope is 19 to 23 percent low against the tunnel. Re-centring it means a full re-run. The third is a moment reference point still to be sourced.

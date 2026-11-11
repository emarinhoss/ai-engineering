# Transcript: the drone deck

This is a transcript of the 40-minute talk on the drone deck (`docs/talk/deck_drone.pptx`), written as I would say it, with the records as they stood on 2026-11-10. The deck rebuilds from the records every time it is built. The SU2 pool is complete, and the SU2-level front, inverse query, confirmation run and bias sweep have landed. Where a slide still says PENDING, the transcript says so and names what will close it.

## Slide 1 — D1: Sizing a small electric aircraft with the inlet pipeline

*0:00, 0.5 min*

The inlet study built a pipeline. This talk asks whether it carries over to a different physics problem, a small electric aircraft. The answer is partly in. Validation V6a to V6f is recorded, the low-fidelity studies are complete, and the SU2 pool is complete: 32 of 32 designs. Every number is read from a record, and every slide says which part is answered and which is not.

## Slide 2 — Section divider: 1a. Why a gated, automated process

I want to start with why the process is gated at all, because the first SU2 case of this study made the argument for me.

## Slide 3 — D2: A clean exit is not a correct result

*0:30, 1 min*

Here is the first SU2 airfoil case of the study. It exited with code 0. It ran its whole budget of 3,000 iterations, it wrote all its files, and nothing in the exit status said anything was wrong. But when the same case was later allowed to stop itself, the first run's lift coefficient turned out to be 10.5 percent low and its drag 24.7 percent high.

What made anybody look? On the right you see the chain. The postprocess step failed first. It was looking for the compressible residual, rms of rho, and the incompressible solver writes rms of P. That failure produced an error file instead of a result. Then the drift rule on the history showed lift moving 5.6 percent and drag 17.4 percent over the last fifth of the run.

Decision 6 set the budget to 6,000 with a Cauchy stop, and the rerun stopped itself at 4,867 iterations. Only checks after the solver could see this.

## Slide 4 — D3: What caught each problem, and when

*1:30, 1 min*

Six problems, each stopped by the earliest check that could see it. Two were found by reading the records, not by a gate.

Read down the first column. The residual name, caught at postprocess. The 3,000-iteration budget, caught by the drift rule and the rerun. The fine mesh that did not reproduce at the 1 nanometer fingerprint: the worker refused to run it, even though the bounding boxes differed by 0 meters. A 29 degree kink at the E387 nose from two half-splines, caught by a geometry test and the inverted-cell gate.

The fifth row is a sentence in my own task ledger: SU2 "drags 3 to 10 percent low". The deck builder read the E387 records and found drag 10.3 percent low to 1.6 percent high. And the last row: SU2's lift slope 5.5 percent off the tunnel against a 5 percent tolerance fixed before any run. Decision 8 kept that a fail.

## Slide 5 — D4: Why MCP tools, and what they do not add

*2:30, 0.5 min*

The agent reaches the queue only through 11 typed MCP tools, with a strict schema and an audit line per call. On the right is what does not depend on MCP: the worker reruns the gates and checks the fingerprint and the sha256. A script would do the same. The sampling points come from Sobol tables and code, never from the language model. No agent transcript was recorded, so this rests on the code.

## Slide 6 — Section divider: 1. Problem and why it matters

Now the problem itself: what we are sizing, and what the study asks.

## Slide 7 — D5: The questions of the study

*3:00, 1 min*

This table gives the status of the four questions at build time.

Question 1 is the front of endurance against take-off mass. On the low-fidelity model the exact front exists: 249 designs. The front on the SU2 pool is now recorded too.

Question 2 is active learning against Latin hypercube and random. On the low-fidelity model, plain EHVI loses online and weighted EHVI wins. The SU2-pool replay is still pending.

Question 3 asks whether the two-level model reaches a given error with fewer SU2 polars. That is recorded, with 32 of 32 SU2 designs complete.

Question 4 is the longest endurance under the 4.0 kilogram cap, with at least 0.9 probability of meeting it, plus one SU2 confirmation. On the low model the answer is a box corner and the cap never binds. At the SU2 level the confirmation is recorded, and you will see on D38 that it failed. A null result is reported as one.

## Slide 8 — D6: Endurance against take-off mass, under the C2 cap

*4:00, 1 min*

This is the trade. On the horizontal axis, take-off mass. On the vertical, endurance. The payload is fixed at 0.5 kilograms. A longer wing and a bigger battery buy endurance and cost mass, so the answer is a front and not a point.

The vertical line is the EASA open-category class C2 limit: 4 kilograms of take-off mass. The spec fixed that cap, and the requirement that the probability of being under it is at least 0.9, before any run.

Now look where the points are. None of the 192 low-pool designs comes near the cap. The heaviest is 3.57 kilograms. That is a finding in itself: on the low model the cap never binds, so question 4 is really only tested at the SU2 level, which comes back on D37.

## Slide 9 — D7: Six inputs, and what is fixed

*5:00, 1 min*

Six inputs span the box. The span runs from 1.2 to 3 meters, nominal 2. Aspect ratio from 6 to 16, nominal 10, which with the span fixes the wing area. Taper from 0.3 to 1, nominal 0.6, with no sweep. Battery fraction, the battery mass over take-off mass, from 0.2 to 0.45, nominal 0.3. Camber from 0 to 6 percent, nominal 4, placed at 40 percent chord. And thickness from 8 to 15 percent, nominal 12.

Everything else is fixed: 46 quantities from the ledger, 21 of them assumed with a band.

Cruise speed is set by a rule: the larger of the speed of least power and the stall margin times the stall speed. As an input, an optimizer would always drive it to the same place. Sea-level standard air is the only condition, and the bands are swept once, on D39.

## Slide 10 — D8: Two fidelity levels, and what each costs

*6:00, 1 min*

There are two fidelity levels, and the cost difference between them shapes the whole study.

The low level runs in the container from closed-form section data. It costs 0.25 seconds per design on one core. That is why the full 531,441-point grid ran in 4.7 hours on 8 workers, and the 192-point pool in 669 seconds on 2.

The high level runs on Colab, on 2 or 4 ranks. It takes an SU2 polar of the design's own section at its own cruise Reynolds number. One angle costs a median of 11.8 minutes on the coarse mesh, over 173 cases, and 22.9 minutes on the medium mesh, over 30 cases. A design needs five angles. The SU2 pool is 172 cases in the case table.

These are medians over every SU2 record at build time. The ratio between the levels is what makes the exact low-fidelity front possible and keeps the high-fidelity pool small.

## Slide 11 — Section divider: 2. Physics and validation

Next, the physics: the model, the section solver, and what validated and what did not.

## Slide 12 — D9: The model in one picture

*7:00, 0.75 min*

Read this left to right. Six inputs go into the geometry: wing, tail and fuselage. The vortex lattice gives the lift slope, the span efficiency and the strip lift. Then a drag build-up, a mass closure, which is a fixed point on take-off mass converged to one part in ten to the nine, and a mission. Power is drag times speed over the propulsive efficiency. Out come endurance and take-off mass.

Above the drag block are the two fidelity levels. That is the only block that differs: closed forms at the low level, an SU2 polar at the high level. And before any solver, five gates of the spec run.

## Slide 13 — D10: The nominal design in one top view

*7:45, 0.5 min*

This is the nominal design seen from above. A 2 meter span, aspect ratio 10 and taper 0.6. That gives 0.40 square meters of wing and a closed take-off mass of 1.51 kilograms. Span and aspect ratio fix the area, and taper fixes the chords. The tail is sized by volume coefficients with a fixed arm. The fuselage holds the payload and the battery; where it sits along the wing in this drawing is schematic.

## Slide 14 — D11: What V6a checks: the vortex lattice

*8:15, 0.75 min*

The lattice puts one horseshoe vortex on each panel. You see one highlighted. The bound vortex sits on the quarter chord, and the control point on the three-quarter chord. Each segment's velocity comes from the Biot-Savart law, and the no-flow condition at the control points gives the circulations. Induced drag comes from the Trefftz plane.

V6a checks this on an elliptic wing of aspect ratio 8. The span efficiency is 0.26 percent below the exact value of 1, and the lift slope is 1.95 percent below Helmbold's. The nominal wing's own values are in the figure beside them.

## Slide 15 — D12: Validation V6a to V6d

*9:00, 0.75 min*

These are the solver's own checks. 12 toleranced rows pass, 1 is pending a source, and 0 fail.

A few to point at. The elliptic wing of aspect ratio 100 matches the high-aspect-ratio slope to minus 0.09 percent. The Warren-12 benchmark lift slope is plus 1.01 percent against a 2 percent tolerance. The V6c rows show the lattice converged: endurance moves 0.13 percent from medium to fine. And V6d shows the mass closure and the energy balance closing below one in ten to the nine.

The pending row is the Warren-12 moment slope, at plus 1.19 percent. It waits for the source of the benchmark's moment reference point. It is not tuned to agree.

## Slide 16 — D13: Mass closure and the endurance balance

*9:45, 0.5 min*

Battery mass is the battery fraction times take-off mass, so the mass sum feeds back on itself and must be iterated. At the nominal design the closure takes 18 iterations. Endurance is then an energy balance: usable battery energy, minus the climb, divided by cruise power. At the nominal design that gives 6.75 hours. V6d checks that both close to one in ten to the nine.

## Slide 17 — D14: The airfoil RANS family: the mesh

*10:15, 0.5 min*

The high level is a new case family. SU2 runs incompressible RANS with Spalart-Allmaras and its BCM transition option, on a structured C-mesh. At the coarse level that is 21,760 cells, with a first cell of 6.17 times ten to the minus five meters, set for a y-plus of 0.5 at the design's Reynolds number. The drawing is rebuilt from the recorded parameters and checked against the recorded cell count.

## Slide 18 — D15: Two stopping rules: SU2's Cauchy stop and the drift rule

*10:45, 0.75 min*

There are two stopping rules, and they measure different things. SU2's Cauchy rule averages the per-iteration change in lift and drag over the last 200 iterations, starting at iteration 500, and stops below one in ten to the five. The drift rule takes the range over the last fifth of the run, divided by the final value.

In the table: the first smoke case, with a budget of 3000, drifted 5.62 percent in lift and 17.38 in drag. The rerun, with a budget of 6000, stopped itself at 4867, and still drifts 2.15 and 5.34 percent. So the drift rule calls both runs still moving. Both rules are kept on every record, and neither was loosened.

## Slide 19 — D16: What the solver history looks like

*11:30, 0.5 min*

This is the medium-mesh nominal case. It ran 4867 of 6000 iterations, and the pressure residual dropped by 4.8 orders. On the residual alone, that looks converged. But over the last 20 percent of the history, the shaded window, lift still drifts 2.15 percent and drag 5.34. That is why the drift rule exists. This is the only history file downloaded so far.

## Slide 20 — D17: What the mesh does to the pressure distribution

*12:00, 0.5 min*

Three meshes on one axis, on the nominal section. The peak suction is Cp minus 1.726 on the coarse mesh of 21,760 cells, minus 1.731 on the medium of 43,008, and minus 1.708 on the fine of 84,152. The lift coefficient is 1.0212, 1.0260 and 1.0138. The curves agree away from the leading edge. But all three runs were flagged not converged, so these differences mix mesh and convergence.

## Slide 21 — D18: V6f: the low-fidelity section against the E387 tunnel

*12:30, 0.75 min*

V6f puts the closed-form section, at the E387's measured camber and thickness, against the tunnel at three Reynolds numbers: 101,800, 203,800 and 305,200.

The closed form is 19 to 23 percent low in lift slope. It misses profile drag by 43 to 52 percent. It overpredicts the maximum lift by 12 to 13 percent. These are report rows by the spec, and nothing was tuned.

These are the sizes of the errors the two-level model has to learn. And the lift effectiveness the ledger assumes does not contain the value the tunnel implies. That is a ledger ruling, not a number to move here.

## Slide 22 — D19: V6e: SU2 against the tunnel, and decision 8

*13:15, 1 min*

This is the hard check, and it failed. SU2's lift slope misses the tunnel by 5.49 percent at Reynolds 203,800, against a 5 percent tolerance fixed before any case ran. At 305,200 it misses by 6.44 percent. Both are fails.

The drag ratio passes at both: 7.99 and 5.74 percent against a 20 percent tolerance. And the maximum lift comes out 3.00 and 3.92 percent low, as report rows.

In the figure, at the five angles of Reynolds 203,800, SU2's lift is 8.0 to 11.6 percent high, and its drag 10.3 percent low to 1.6 percent high.

So what did I do with a fail? Decision 8: I accepted the medium-mesh polar as the high level, with the miss recorded beside every number it produces. It stays a fail. The tolerance did not move. And the medium-against-fine row now has its answer: after the mesher fix of decision 11, the fine mesh's drag at a lift coefficient of 0.6 is 0.35 percent above the medium's, against a 5 percent tolerance. It passes.

## Slide 23 — D20: The E387 pressure distributions

*14:15, 0.5 min*

These five panels are E387 at Reynolds 203,800, one per angle, upper surface solid. The suction peak deepens from Cp minus 0.71 at 1.27 degrees to minus 3.18 at 7.23 degrees. Look for the kink in the upper-surface curve: it moves forward as the angle rises. All five cases are flagged not converged by the drift rule, and each panel title says so.

## Slide 24 — D21: Where the wall shear reverses

*14:45, 0.5 min*

This is the skin friction along the chord. Where it goes negative, the wall shear points upstream, which marks reversed flow. At 1.27 degrees that stretch runs from x over c of 0.48 to 0.68. At 7.23 degrees it runs from 0.30 to 0.49. It sits where the pressure panels showed the kink, and it moves forward with angle.

## Slide 25 — D22: Section polars: SU2, the closed form and the tunnel

*15:15, 0.75 min*

On the left, lift against angle. On the right, drag against lift. For E387, SU2's lift is 8.0 to 11.6 percent high and its drag 10.3 percent low to 1.6 percent high against the tunnel.

The closed form is a straight line to a cap, with a constant drag. It has no stall and no drag rise. Now look at the pool designs at the top of the angle range. On the 32 complete pool designs, the 32 cases at 14 degrees have lift from 0.48 to 1.39 and drag from 0.067 to 0.188. That is the stall the closed form cannot show. Open circles are cases the pool did not keep.

## Slide 26 — D23: The stall at 14 degrees

*16:00, 0.5 min*

Here is one design, pool design 0, on the coarse mesh. Between 10 and 14 degrees the section stalls. Lift falls from 0.952 to 0.563. Drag rises from 0.0357 to 0.1763. And the suction peak collapses from Cp minus 3.53 to minus 0.98. That flat upper-surface pressure at 14 degrees is separated flow over most of the chord.

## Slide 27 — D24: Pressure contours and streamlines

*16:30, 0.5 min*

This is pool design 0 at 14 degrees: pressure contours and streamlines. The upper surface is separated, with reversed flow at the wall from x over c of 0.013, just behind the leading edge, to 0.96. That is the stall the closed form cannot show. The 6 degree case is not shown: its volume file came back unreadable twice, so the cause is in the writer, not yet established.

## Slide 28 — Section divider: 3. Automation layer: MCP tools, gates, queue

Now the automation layer: the tools, the gates, and the queue that connects them to Colab.

## Slide 29 — D25: The tools and the gates

*17:00, 1 min*

The MCP server exposes 11 tools. On the left you see each one with the first line of its docstring. Two things to notice. The server never runs SU2: export batch bundles jobs for upload, and that is as close as it gets. And create case refuses bad input; nothing is staged when a check fails.

On the right are the drone gates, as the code names them: the Reynolds range, the stall margin, the mass closure, the manufacturing floor and wing loading, and the lattice quality. A drone design passes the 5 gates of the spec before any solver. An airfoil case also passes a mesh-quality gate: inverted cells, minimum angle, first cell, growth and aspect ratio.

Each gate fails with the offending value in its message, in the same form as the inlet. And the same gate function runs twice: when a case is created, and again on the worker before SU2 starts.

## Slide 30 — D26: Where each gate sits: the Drive queue and the Colab worker

*18:00, 1 min*

This diagram follows a request from left to right. It enters through the MCP tools, goes through the schema and the physics gates, and is staged. It then goes to a Google Drive queue folder. Why Drive? Because Colab cannot take inbound connections. The worker on Colab polls the folder.

The numbered marks show where each check sits. Before SU2 starts, the worker rebuilds the mesh and the config from the uploaded parameters and refuses any mismatch. After SU2 finishes, the result comes back to Drive as a file with a digest, and it passes more checks before it becomes a record: the digest, the history, and the polar aggregation.

The stage and step names in the drawing are checked against the code when the deck is built, so the picture cannot quietly drift from what the code does.

## Slide 31 — D27: Two workers on one queue, and ingestion with sha256

*19:00, 1 min*

One thing that is new in this study is two workers on one queue. With the shard flag, K over N, a worker takes only the cases whose id hash is K modulo N. On the left you see the split: two Colab sessions take the 172 pool cases as 85 and 87. Every case lands in exactly one shard, so no two workers claim the same job. Before this flag, two workers on one queue would both have started the same job, so only one ran. Without the flag a worker takes every job, and two unsharded workers on one queue are not allowed. The pool records carry 11 worker ids.

On the right is ingestion. Each result comes back with its sha256 and is checked before it goes under runs. The aggregator forms a design polar only when at least 3 angles are kept. The results table stands at 32 designs: 32 complete, 0 incomplete, 0 failed. And the table's own hash matches its record: yes.

## Slide 32 — D28: What the gated process caught

*20:00, 1 min*

This list holds only items recorded in the task file, each found by a check or a recorded run before it reached a result.

The postprocess looked for the compressible residual; it now reads rms of P, under decision 6. The first case drifted 5.6 percent in lift and 17.4 in drag; the budget became 6000 with a Cauchy stop. The fine-mesh case was refused at the 1 nanometer fingerprint, and the refused attempt is kept beside the rerun. The fine E387 mesh had 8 inverted cells. Under decision 11 the mesher now smooths the wall tangents on every mesh, the fine cases ran, and the V6e fine row passes at 0.35 percent.

The last two are in the lattice. The point-vortex induced drag under-counted by about one over N, which the elliptic-wing rows showed, so it was replaced with a Trefftz-plane Glauert series. And the V6a reference for the aspect-ratio-100 rectangular wing was wrong, not the solver. The reference was corrected before any formal verdict.

## Slide 33 — Section divider: 4. Surrogate and active learning

Now the surrogate and the active learning, which is where the inlet result either carries over or does not.

## Slide 34 — D29: One Gaussian process per objective, and who chooses

*21:00, 1.5 min*

There is one exact Gaussian process on endurance and one on the log of take-off mass. The six inputs are scaled to the unit interval. This is the inlet's GP code with the drone bounds: a Matern five-halves kernel with one length scale per input, fitted by marginal likelihood. At every candidate it gives a mean and a variance.

The table lists the five strategies on the next slides. Random draws uniformly. LHS follows a Latin hypercube order fixed by the seed. Max-variance picks the largest summed scaled variance. EHVI picks the largest expected hypervolume improvement. And the fifth, EHVI times the probability of being feasible, is used online only, on D32.

In words: the hypervolume improvement of a point is how much area it adds to the current front. EHVI averages that over samples drawn from the GP at the candidate. Max-variance is there so you can see what the hypervolume term adds on top of plain exploration.

Every strategy is deterministic given a seed, so every run reproduces from its record. And to say it again: the language model calls tools. It never picks a point.

## Slide 35 — D30: What the GP learned about the box

*22:30, 1 min*

On the left, the six inputs ranked by the GP's length scale for endurance. A short length scale means endurance changes fast along that input. Aspect ratio and span come first, and that is why the design map on the right uses them as its axes.

The map shows the region that passes the gates, over aspect ratio and span, with the observed front overlaid. In this projection, 2 of the 15 observed front designs lie within one cell of a gated cell.

I want to be careful with what that count means. The map holds the other four inputs at one base point, while each front design has its own values for them. So the overlay is a projection. The count says how close the front comes to the cheap gates in this view, and no more.

## Slide 36 — D31: The pool replay

*23:30, 1.5 min*

The first test is the pool replay. All strategies draw from the same 192-point low pool, so the ground truth is shared and no extra runs are needed. The measure is hypervolume regret: one minus the hypervolume of what has been observed over the hypervolume of the true front. Lower is better, and zero means the front has been found.

The table gives the mean over 10 seeds. At 8 evaluations every strategy is at 0.285, because every strategy of a seed starts from the same 8 initial points. By 16, EHVI is already at 0.034 while random and LHS are at 0.210. EHVI reaches regret 0.000 at 32 evaluations. Random is still at 0.118 after 40, LHS at 0.107, and max-variance at 0.062.

So on the pool, EHVI wins clearly. But this is the easy case: the pool is smooth and gate-free. The test that matters is the next one.

## Slide 37 — D32: Online replay: plain EHVI loses, weighted EHVI wins

*25:00, 2 min*

This is the online replay, on the unrestricted box, measured against the exact front. Now the acquisition can pick any point, including points that fail the gates.

And plain EHVI loses. Look at the table. At 40 evaluations EHVI ends at regret 0.317, while random ends at 0.294 and LHS at 0.271. Plain active learning is worse than random sampling. The column on the right says why: EHVI wasted 29.7 of its 32 picks on gated designs. Max-variance is the same story: 0.353, with 25.4 gated picks.

The reason is in the geometry of the problem. The front lies against the gated edge of the box, and the two GPs know nothing about the gates. So the acquisition keeps proposing designs just past the edge, where the GP predicts the best trade, and those designs are not buildable.

The fix is to weight EHVI by a probability of being feasible, from a logistic model fitted on the gate outcomes. In words: the score is the expected hypervolume improvement times the probability that the design passes. With that weighting EHVI ends at 0.092, the best of the six, with 7.5 gated picks. Max-variance weighted the same way gets to 0.268.

So the honest answer to question 2 is this: active learning beats space-filling sampling here only when the acquisition knows where the design is buildable. Both runs are published. The weighted run does not replace the loss; it sits beside it. The full tables are in backup DB9.

## Slide 38 — D33: The two-level model

*27:00, 2 min*

The third question. Does a two-level model reach a given held-out error with fewer SU2 designs than SU2 alone?

The model is the one in the sketch: the high-level output equals a scale factor rho times the low-level output, plus a discrepancy d that is itself a Gaussian process. Rho and a constant are fitted by generalized least squares. The discrepancy has to absorb the gap between the levels, and we know that gap is real, from V6e and V6f.

The table is the mean over ten seeds, on the complete SU2 pool. Read the endurance error first. With 8 SU2 designs, the two-level model's error is 0.824 hours against 1.525 for SU2 alone. At 12 it is 0.808 against 1.112. At 16, 0.747 against 0.865. At 24 the order flips: SU2 alone at 0.704, the two-level model at 0.726. So the gain is at small budgets. On mass the gap is larger: at 8 designs the relative error is 0.0022 against 0.0869.

Now the intervals. A 90 percent interval should contain about 90 percent of the held-out designs. The two-level coverage is 0.61 at 8 and 12 designs, 0.68 at 16 and 0.69 at 24. SU2 alone goes from 0.43 to 0.78. Both are short of 90 percent. So the two-level model is more accurate at small budgets, but its intervals are over-confident, and that is recorded as it stands, not adjusted.

The inlet's Task 9 found that a cheap level helps most at small budgets. This is the same measurement on a new problem, and on accuracy it points the same way.

## Slide 39 — Section divider: 5. Results and the inverse query

Now the results: the fronts, the SU2 pool as it stands, and the inverse query under the cap.

## Slide 40 — D34: The low-fidelity grid and its exact front

*29:00, 1 min*

Because the low level is cheap, the exact front over the whole box exists. The grid has 531,441 points: 459,432 clean, 72,009 gated, and 0 failed. It took 16747 seconds on 8 workers. The exact front is 249 designs, the dark line in the figure.

The lighter points are the 192-design low pool. None of it was gated, its front has 15 designs, and it ran in 669 seconds. Both runs are at the medium lattice level.

This exact front is the reference against which both replays measured regret. And it is a low-fidelity front, so it carries every low-fidelity bias on the limitations slide.

## Slide 41 — D35: The SU2 pool as it stands

*30:00, 1.5 min*

This is the SU2 pool as it stood when the deck was built, read from the ingested results, and it is now complete. Of the 32 pool designs, 32 are complete and 0 incomplete. 172 of the 172 cases have landed, counting the coarse pool and the medium bias check.

Each row is one complete design: the angles kept, then endurance and mass at both levels and their ratio. The low column is the same design through the low model, with the same lattice, closure and mission. Only the section data differ.

Look at the endurance ratio column. On the complete designs the SU2-level endurance is 15.8 to 65.5 percent lower than the low level's. Design 21, for example, is 8.31 hours against 11.11. The worst are designs 30, 19 and 17, at ratios of 0.345, 0.405 and 0.420. The mass ratio, by contrast, stays between 1.001 and 1.011.

That design-by-design difference is exactly the discrepancy the two-level model has to learn. A design with fewer than three kept angles is not evaluated, and every SU2 row carries the decision-8 flags.

## Slide 42 — D36: The high-fidelity front with its band

*31:30, 1 min*

This is the front on the SU2 pool. The observed front has 13 designs, from 2.95 hours at 1.09 kilograms to 8.40 hours at 3.14 kilograms.

Around it is the band. The band is the posterior uncertainty of the two GPs, sampled jointly, and it is drawn beside the observed designs, not instead of them. The exact low-fidelity front from D34 goes beside it, so you can see the endurance gap of the pool table, now at the level of the front.

Every point of this front carries the V6e bias of decision 8. So this is the SU2-level answer to question 1, with the lift-slope fail recorded beside it, not removed from it.

## Slide 43 — D37: The inverse query under the 4 kg cap

*32:30, 1 min*

The inverse query asks: what is the longest expected endurance, subject to a high enough probability that take-off mass stays under the 4 kilogram cap? It is computed on the fitted surrogate, never chosen by the language model.

On the low model the answer is a box corner, with 6 of the six inputs at a bound. The GPs predict 13.307 hours and a median mass of 2.435 kilograms, and the probability of being under 4 kilograms is 1.000. So the cap never binds there. The GP extrapolates there, so I evaluated the corner directly: 13.245 hours and 2.438 kilograms, inside both intervals.

On the SU2 pool the answer moves. Span 3, taper 0.3 and battery fraction 0.45 stay at their bounds, but aspect ratio comes down to 7, camber to 3.9 and thickness to 10.8 percent. The GPs predict 10.139 hours, with a 90 percent interval from 9.116 to 11.163. The median mass is 3.918 kilograms, close to the cap, with a probability of 0.991 of staying under it.

## Slide 44 — D38: The confirmation run

*33:30, 0.5 min*

This is the confirmation: one SU2 polar at the answer. It passes the C2 check only if both objectives fall inside their predicted 90 percent intervals. There are two rows, because there were two answers. The earlier answer, on 30 designs, passed: endurance 9.951 hours inside 8.596 to 10.073, and mass 2.963 kilograms inside its interval. The final answer, on 32 designs, failed. Mass came out at 3.936 kilograms, inside its interval and under the cap. Endurance came out at 8.955 hours against a predicted 10.139, below the interval. The final verdict is C2 FAIL, and it stays a fail, documented as in the inlet study.

## Slide 45 — D39: Which fixed quantities move the answer

*34:00, 0.5 min*

Each of the 21 banded quantities is moved alone to each end of its band. At the low-fidelity answer the largest are skin areal density at 17.2 percent, propulsive efficiency at 17.0, and pack specific energy at 16.7. At the SU2 answer the same three lead: skin areal density at 22.0, propulsive efficiency at 17.1, and pack specific energy at 16.8. Each ranking is for one design, not a global sensitivity. The full table is backup DB8.

## Slide 46 — D40: Coarse against medium on the pool

*34:30, 0.5 min*

Decision 7 put the pool on the coarse mesh for cost and kept the first four designs at three angles on the medium mesh as a check. On the 10 pool cases with both meshes, medium over coarse is 0.5 percent low to 2.8 percent high in lift, and 5.5 percent low to 1.6 percent high in drag. So the coarse mesh is checked case by case.

## Slide 47 — Section divider: 6. Limitations and conclusions

Finally, the limitations, what was wrong first, and the conclusions as far as the records go.

## Slide 48 — D41: Biases that travel with every number

*35:00, 1.5 min*

On the left are the named biases from section 13 of the spec. No trim drag. Fully turbulent skin friction on the non-wing parts above a Reynolds number of five times ten to the five. A fixed propulsive efficiency. A closed-form structure. And the section polar at one Reynolds number per design, the cruise one, while the chord varies along the span.

Two more come from the records. The kept pool cases have a drift band of 0.4 to 12.6 percent in lift and 0.0 to 7.5 percent in drag. That is the movement the stopping rule tolerates, so it is the floor of what the pool can resolve. And the section lift effectiveness is 0.75 with a band from 0.6 to 0.9; V6f's tunnel value lies outside it, which is an open ruling.

On the right are the decision-8 flags every SU2 polar carries. At Reynolds 203,800 the lift slope is plus 5.5 percent, a fail, and the drag ratio plus 8.0 percent, a pass. At 305,200 it is plus 6.4, a fail, and plus 5.7, a pass. Behind that, SU2's lift is 8.0 to 11.6 percent high at Reynolds 203,800, and its drag 10.3 percent low to 1.6 percent high. The flags are generated from the validation record, so they cannot drift from it.

## Slide 49 — D42: What the record keeps that was wrong first

*36:30, 1 min*

Each row here was wrong when first recorded, and is kept beside its correction. None moved a tolerance after a verdict.

The drag sentence in the task ledger, 3 to 10 percent low, is corrected in place: per point, drag is 10.3 percent low to 1.6 percent high. The aspect-ratio-100 row tested a rectangular wing against the elliptic slope; the rectangular wing sits 1.44 percent below it, so the row now tests an elliptic wing. The point-vortex induced drag became the Trefftz-plane Glauert series. The fine-mesh fingerprint went from 1 nanometer to 1 micrometer, with the refused attempt kept. The 3,000-iteration budget became 6,000 with a Cauchy stop.

The most useful entry is the online replay. Plain EHVI at 0.317 against random's 0.294 is kept as published, with the weighted run at 0.092 beside it. That is the result the plan said to publish if active learning lost.

## Slide 50 — D43: Limits of the model

*37:30, 1 min*

The study sizes one cruise point, at sea level, with a fixed propeller efficiency and a closed-form structure. On the left is what the spec puts out of scope: stability beyond the static margin, structure beyond the spar rule, propeller design, take-off and landing, wind and altitude, cost, and certification beyond the C2 cap. Wind and altitude come first; a candidate Task 11 would add them in the form of Task 9's envelope.

On the right are the open items. V6g, the Ultra Stick 25e check, is not run, because the data were not retrieved. The Warren-12 moment row is pending its reference point. And the rulings. Decision 9, on 2026-11-10, accepted the budget-exhausted runs of designs 8 and 28, with a flag; every other one is still dropped. Still open is the lift-effectiveness band, where re-centring means a 4.6-hour re-run. Nothing here claims more than one cruise point.

## Slide 51 — D44: Conclusions: the four questions as far as the records go

*38:30, 1.5 min*

Here are the four questions, as far as the records go.

Question 1, the front. The exact low-fidelity front is 249 designs over 531,441 points, and aspect ratio and span drive endurance. The front on the SU2 pool is now recorded as well.

Question 2, active learning. This is the result I would lead with, because it includes a loss. Plain EHVI loses online, 0.317 against random's 0.294. With the probability of feasibility it wins, at 0.092. The SU2-pool replay is still pending.

Question 3, the two-level model. With 8 SU2 designs the two-level endurance error is 0.824 hours against 1.525 for SU2 alone, and SU2 alone reaches it only at 24 designs. It wins on the mean at small budgets, and its intervals are over-confident.

Question 4, the inverse query. On the low model the answer is a corner at 13.31 hours and 2.43 kilograms, and the 4 kilogram cap does not bind there. On the SU2 pool the answer moves to aspect ratio 7, at 10.14 hours and 3.92 kilograms. The confirmation kept the mass under the cap, at 3.94 kilograms, but found the endurance at 8.95 hours, below its predicted interval. That is a failed confirmation, reported as one.

The pipeline carried over with its gates, queue and replay unchanged. What is new is the airfoil family, the two-level model and the sharded workers. Anything still pending on this slide is a run in progress, not an estimate.

## Slide 52 — Section divider: Discussion

That is the end of the talk. I would like to use the rest of the time for discussion.

## Slide 53 — D45: Questions, and where the answers are

*40:00 onward, about 20 min*

On the left are the questions I think the study invites. Where would you trust the low level alone? Is a fixed propulsive efficiency acceptable for sizing? Was accepting the budget-exhausted runs of two designs and one confirmation angle right? What would a feasibility model need to beat a hard gate? How would wind and altitude change the front? And what would make the two-level model worth its SU2 cost? On the right is the index of backup slides DB1 to DB17. Tell me which limit matters most to you, and I will open the matching one.

# Backup slides (only if asked)

## Slide 54 — Section divider: Backup

These are the backup slides. I open them only when a question needs them.

## Slide 55 — DB1: Backup: the V6 table, part 1 (V6a to V6d)

If you ask how converged the lattice is, or what the report rows show: this is every V6a to V6d row. The report rows have no tolerance; they show the convergence the toleranced rows rest on. For example, on the elliptic wing of aspect ratio 8 the lift slope goes from minus 1.56 percent on the coarse lattice to minus 1.82 on the medium and minus 1.95 on the fine. The Warren-12 moment row, at minus 3.137 against minus 3.1, stays pending until the reference point is sourced.

## Slide 56 — DB2: Backup: the V6 table, part 2 (V6e to V6g)

If you ask to see every SU2 and closed-form row against the tunnel: here they are. V6f gives the closed form's lift slope of 0.08225 against the tunnel's 0.1063 to 0.1017. V6e gives SU2's lift slope of 0.1044 against 0.09901 at Reynolds 203800, a fail, and 0.1062 against 0.09979 at 305200, also a fail, both kept as fails under decision 8. The V6e mesh row passes: the fine mesh's drag at a lift coefficient of 0.6 is 0.35 percent above the medium's, against 5. Beside it, the mesher fix moved the medium answer by 0.0002 percent. The one row not run, V6g, is shown, not hidden.

## Slide 57 — DB3: Backup: E387 point by point at both Reynolds numbers

If you ask whether the lift-slope miss is a slope or an offset: this compares SU2 and the tunnel at the tunnel's own angles, with no interpolation. At every matched angle SU2 lifts more, from plus 8.0 to plus 12.7 percent. Drag runs from 10.3 percent below to 2.3 percent above. The lift offset is nearly uniform, so most of the slope miss is an offset plus a slightly steeper line.

## Slide 58 — DB4: Backup: the mesh table (coarse, medium, fine)

If you ask whether the coarse mesh is good enough: on the nominal section the three meshes differ by less than the fine run's own drift. The fine run drifts 4.4 percent in lift and 10.3 in drag, while coarse sits within 0.7 and 1.1 percent of fine. So the table resolves the drift band, not the mesh. The cost per iteration per cell is 6.26 to 6.62 microseconds at all three levels, so cost scales with cells and iterations together.

## Slide 59 — DB5: Backup: the budget-exhausted runs

If you ask what happens to runs that hit the budget: this lists every one, with its drift. The aggregator drops them by its default rule and the record keeps them. The Kept column marks the ones a ruling accepted. Decision 9, on D43, accepted the runs of designs 8 and 28 with a flag. Decision 10 accepted the 14 degree case of the 30-design answer's confirmation. The final answer's 14 degree case is not accepted, and the rule for the rest is unchanged. Be careful with the largest drifts. Design 2 at minus 2 degrees shows 98.2 percent lift drift, but its lift is minus 0.0020. The rule divides the range by the final value, so near zero lift a tiny absolute movement looks huge.

## Slide 60 — DB6: Backup: the low-pool Pareto record

If you ask whether the Pareto analysis actually works end to end: this run on the low pool proves it before the SU2 pool lands. It trained on 192 of 192 rows, kept 4,096 of 4,544 candidates, found an observed front of 15 designs from 3.47 hours at 0.953 kilograms to 11.71 hours at 2.283, and a predicted front of 57 points. Aspect ratio has the shortest length scale, 5.49. It is a diagnostic, not a study answer.

## Slide 61 — DB7: Backup: the 21^6 inverse record

If you ask how the inverse query searches: it walks the whole grid of 21 to the sixth, 85,766,121 points, in chunks. 76,587,147 pass the closed-form gates, and the closure gates run on the best candidates. The answer is the box corner, at 13.307 hours and a median 2.435 kilograms. The interval is a 90 percent predictive one, including noise. The GP extrapolates to that corner, which is why I showed the direct evaluation on D37.

## Slide 62 — DB8: Backup: the bias sweep, full table

If you ask which assumptions matter most: this is every banded quantity, moved one at a time to its band ends at the low-fidelity answer. Skin areal density moves endurance from plus 13.0 to minus 17.2 percent and mass by up to plus 62.0 percent. Propulsive efficiency and pack specific energy move endurance about 17 percent each way. The ones marked no effect at this design are different: the model reads them, but they do not bind here. The sweep at the SU2 answer is the second ranking on D39.

## Slide 63 — DB9: Backup: the online replays, full tables

If you ask to see the online loss in full: these are mean regret and gated picks at every budget, on the same seeds and candidate sets. Every strategy starts at 0.409 at 8 evaluations, the shared initial design. Plain EHVI stalls near 0.317 from 32 on, while the feasibility-weighted version falls steadily to 0.092. Gated picks for plain EHVI climb to 29.7 by 40. The loss and the win are both on the record.

## Slide 64 — DB10: Backup: the decision log

If you ask who made the calls on the SU2 level: I did, and these are the three rulings with their times. Decision 6, on 2026-11-08 at 06:50 UTC, set the budget to 6,000 with a Cauchy stop. Decision 7, at 20:45 UTC, staged the pool: 32 designs at five angles on the coarse mesh, plus the medium bias check. Decision 8, at 22:35 UTC, accepted the medium mesh as the high level with the bias recorded, which is also why no SST with Langtry-Menter was attempted.

## Slide 65 — DB11: Backup: the ledger provenance

If you ask where the fixed numbers come from: every one of the 46 fixed quantities carries a source and a grade. 17 are published, 8 derived and 21 assumed, and all 21 assumed ones carry a band. The loader refuses a quantity without a source, and an assumed one without a band that contains its value. These bands are what the bias sweep moves. The E387 and Warren-12 validation data are kept separately and not counted.

## Slide 66 — DB12: Backup: the cost ledger

If you ask what this cost in compute: SU2 cases took a median of 705 seconds on the coarse mesh over 173 cases, and 1,372 on the medium over 30. The single fine case took 3,162. The pool used 31.9 worker-hours, and the confirmation 3.4. The low-fidelity grid took 4.65 hours on 8 workers, and the low pool 669 seconds on 2.

## Slide 67 — DB13: Backup: the equations index

If you ask where a formula on a slide lives in the code: this index gives every equation on the talk slides with the module that implements it. For example, the Matern kernel and the GP posterior are in the GP module, the expected hypervolume improvement in the acquisition module, and the two-level model in its own module. It is generated from the same constants the slides render, so a relation the code does not implement cannot appear on a slide.

## Slide 68 — DB14: Backup: the study guide

If you ask how I prepared the physics behind each slide: the drone study guide has 31 entries in four blocks, in the same form as the inlet guide. The blocks are the problem and the low-fidelity model, airfoil RANS at low Reynolds number, the surrogates and the study's answers, and the automation layer. Each entry has the definition, the relations, a worked example from the records, and a self-check, and every number names its source file.

## Slide 69 — DB15: Backup: carried over from the inlet study, and new

If you ask how much of this was reused: the queue, the gates, the GP, EHVI, the replay and the feasibility model carried over unchanged. New here are the airfoil family, the Cauchy stop, the per-design polar aggregation, the online replay against an exact front, the two-level model and the sharded workers. The inlet study took seven days with its tools built along the way; this one reused them from the first day. The feasibility model did not help in the inlet's Task 9, and here it decided the result.

## Slide 70 — DB16: Backup: the rulings, one ruled and two open

If you ask what is still undecided: of three rulings, one is ruled and two are open. First, whether budget-exhausted SU2 runs enter the pool; 36 pool cases used their whole budget. That one is ruled: decision 9 accepts designs 8 and 28, and decision 10 the 30-design answer's 14 degree case, which left its C2 pass unchanged. Second, still open, the lift-effectiveness band, 0.75 within 0.6 to 0.9, while V6f's slope is 19 to 23 percent low; re-centring means a full re-run. Third, still open, the Warren-12 moment reference point. None is decided by the deck, and the record keeps both states.

## Slide 71 — DB17: Backup: record status, what exists and what is pending

If you ask exactly what has run and what has not: this table lists every file the deck reads or waits for, and its status is computed when the deck is built. The validation record, the grid, the online replay, the low-fidelity inverse and bias sweep, the pool results, the multi-fidelity analysis, the SU2-pool front and inverse, the confirmation run, the SU2 bias sweep and one of the two viz files all exist. The other viz file is pending, and D24 says why. The talk claims nothing beyond the existing files.

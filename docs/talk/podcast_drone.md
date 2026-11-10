# Podcast script: an automated, gated pipeline for aircraft design

Two voices, about eight minutes. HOST asks; ÉDER explains. Rewritten 2026-11-10 from the final
records (all 32 SU2 pool designs, both confirmation runs, the SU2-level front, decisions 9 and 10), with the pipeline as
the subject and the aircraft as the problem it was built for. Every number comes from the records
named in the source table at the end. For text-to-speech each line is voiced sentence by sentence,
because the Chatterbox Space takes at most 300 characters per call.

---

**HOST:** Welcome to Design Loop. Today's guest built a pipeline that runs engineering simulations with almost no one in the loop, and that refuses to hand over a result it cannot check. Éder, what problem does it solve?

**ÉDER:** Design studies are slow for three reasons. High-fidelity simulation takes minutes to hours per run, setting each run up is manual, and failures are often silent. The pipeline attacks all three: it runs the loop unattended, and it checks every result before anyone sees it.

**HOST:** What did you test it on?

**ÉDER:** A small electric aircraft. It carries a half-kilogram payload, European rules for its class cap take-off mass at four kilograms, and I want the longest endurance. Six inputs define the design: span, aspect ratio, taper, battery share, and the camber and thickness of the wing section.

**HOST:** Walk me through the pipeline.

**ÉDER:** An agent asks for runs through eleven typed tools with strict schemas. Every request passes five physics gates before any solver starts. Jobs go into a shared queue, cloud workers run the CFD solver, and every result comes back through checks and a SHA-256 hash before it becomes a record. The language model never chooses a design point. A surrogate model does.

**HOST:** Why so many checks?

**ÉDER:** Because a clean exit is not a correct result. The first solver case exited with code zero after its whole iteration budget. It looked fine. Against a properly stopped rerun, its lift was 10.5 percent off and its drag 24.7 percent off. Only a check after the solver could see that.

**HOST:** And the solver itself, is it right?

**ÉDER:** Mostly, and the miss is on the record. Against wind-tunnel data, its lift slope is 5.5 percent high where I allowed five, so that check fails. Its drag is within eight percent on average against a twenty-percent tolerance. I kept the fail, accepted the solver with the bias written into every result, and moved no tolerance.

**HOST:** You have two models of the aircraft?

**ÉDER:** Yes. A cheap one costs a quarter of a second per design, so it can cover the whole space. The expensive one runs the CFD solver on the wing section: about twelve minutes per angle, five angles per design. They share everything except the section data, so the expensive model corrects the cheap one rather than replacing it.

**HOST:** How does the pipeline decide what to run next?

**ÉDER:** Two Gaussian processes, one for endurance and one for mass, give a prediction and an uncertainty everywhere. An acquisition function picks the next design. On a fixed pool of 192 designs, it finds the whole optimal front in 32 evaluations, where random sampling still misses part of it after 40.

**HOST:** So active learning always wins?

**ÉDER:** No, and that's the result I lead with. On the open design space, the plain method ended at a regret of 0.32, worse than random's 0.29, because it kept choosing designs the gates reject. Weighting it by the probability of passing the gates brought it to 0.09. It wins only with a feasibility model.

**HOST:** Tell me about running the expensive cases.

**ÉDER:** 172 solver cases, on cloud workers that pull from the shared queue. Workers split the queue by a hash of the case name, so they never fight over a case. In this version the session itself starts the cloud runtimes, restarts them when they die, and re-splits the work when one runtime runs dry, so none sits idle while another has a queue.

**HOST:** Did that matter?

**ÉDER:** It did. Before, when both runtimes ended, nothing ran for an hour and forty minutes until someone restarted them by hand. Now the person only signs in to cloud storage and makes rulings when the data force a judgment.

**HOST:** How much time does all this save?

**ÉDER:** The cheap model ran 531,441 designs in under five hours. The 172 solver cases took 37 worker-hours, done in 25 hours of elapsed time, overnight. And the two-level model gets, from eight expensive designs, the accuracy that the expensive model alone needs twenty-four designs to reach.

**HOST:** Three times fewer expensive runs. Does that hold everywhere?

**ÉDER:** No. The saving is large at small budgets and gone by twenty-four designs, where the expensive model alone is slightly better. And neither model's ninety-percent interval really covers ninety percent of new designs. I quote the mean, not the interval.

**HOST:** What did the expensive level change?

**ÉDER:** On every one of the 32 designs, the solver's endurance is below the cheap model's, by 16 to 66 percent. The cheap model's best design was in a corner of the space and nowhere near the mass cap. The expensive level moved the answer off the corner, to aspect ratio seven, and brought the cap into play: about ten hours at 3.92 kilograms.

**HOST:** And you checked that answer?

**ÉDER:** I ran it through the solver. The pass condition was fixed in advance: endurance and mass both inside their predicted ranges. An earlier answer, on 30 designs, passed. The final answer kept its mass at 3.94 kilograms, under the cap. But its endurance came out at 8.96 hours, below the predicted range. That's a fail, and I report it as one.

**HOST:** That's an unusual thing to say in an interview.

**ÉDER:** It's the point. The uncertainty was too narrow, which the held-out tests had already shown. The pipeline caught that with one confirmation run, before anyone built anything.

**HOST:** Did you ever overrule the checks?

**ÉDER:** Twice, by name, and on the record. Thirty-six pool cases ran out of iterations, and the pipeline drops those by default. I accepted the runs of two designs, and later one angle of the 30-design confirmation, each carrying its drift as a flag. That angle didn't change the confirmation's pass. Everything else stays dropped, and two other questions I was asked to rule on are still open.

**HOST:** If you had to sum it up?

**ÉDER:** Put the checks after the solver, not just before it. Let the agent drive tools, never choose the data. Make every number on a slide computable from a record. And report the losses, because that's what makes the wins believable.

**HOST:** Éder, thanks for coming on.

**ÉDER:** Thanks for having me.

---

## Sources

| Claim | Record |
|---|---|
| 0.5 kg payload, 4 kg cap, six inputs | `data/drone/rules.yaml`, `mcp_server/schemas.py` |
| Eleven typed tools, five gates | `mcp_server/server.py`, `drone/evaluate.py` |
| First case: exit 0, lift −10.5 %, drag +24.7 % against its rerun | `runs/smoke/`, `runs/smoke2/` result records |
| SU2 lift slope +5.49 % against 5 % (fail), drag ratio 8.0 % against 20 % (pass), decision 8 | `runs/drone/validation/2026-11-08/v6.json`; `docs/specs/task10_tasks.md` |
| Cheap model 0.25 s per design; SU2 median 11.6 min per coarse angle | `runs/drone_grid/2026-11-08/record.json`; SU2 run records (deck D8) |
| Pool replay: whole front at 32 evaluations; random 0.118 at 40 | `runs/replay_drone_pool/2026-11-08/replay.csv` |
| Online replay at 40: plain 0.317, random 0.294, feasibility-weighted 0.092 | `runs/replay_drone_online/2026-11-08/online.csv`, `2026-11-08_feas/online.csv` |
| 172 SU2 cases, 37.0 worker-hours over 24.9 h elapsed; 531,441 designs in 4.7 h | SU2 run records; `runs/drone_grid/2026-11-08/record.json` (deck version 2, V17) |
| Both runtimes ended 14:10 UTC, nothing ran until 15:50 | runtime operations log, `docs/specs/task10_tasks.md` |
| Two-level: 0.824 h against 1.525 h at n = 8; SU2 alone reaches it at 24; at 24 SU2 alone 0.704 against 0.726 | `runs/drone_mf/2026-11-09/mf.csv` (32 designs) |
| SU2 endurance 15.8 to 65.5 % below the low model on all 32 designs | `runs/pool_af/2026-11-09/results.csv` against `runs/drone_pool_lf/2026-11-08/grid.csv` |
| Inverse at SU2 level: aspect ratio 7, 10.139 h at 3.918 kg | `runs/drone_inverse_hf/2026-11-09/inverse.json` |
| 36 budget-exhausted pool cases; decision 9 accepts designs 8 and 28, decision 10 the 30-design confirmation's 14° case, C2 pass unchanged; two rulings open | `runs/pool_af/2026-11-09/record.json`; `docs/specs/task10_tasks.md` (decisions 9 and 10); deck version 1, DB5 and DB16 |
| Confirmations: 30-design answer pass; final answer 8.955 h below [9.116, 11.163], mass 3.936 kg inside | `runs/drone_confirm/2026-11-09_30designs/confirm.json`, `runs/drone_confirm/2026-11-09/confirm.json` |

Rounded for speech: 12 min (11.6), 5.5 % (5.49), 0.32 / 0.29 / 0.09, "under five hours" (4.7),
25 hours (24.9), 16 to 66 % (15.8 to 65.5), about ten hours (10.139), 3.94 kg (3.936), 8.96 hours
(8.955), "an hour and forty minutes" (14:10 to 15:50 UTC). "Three times fewer" is 8 against 24.

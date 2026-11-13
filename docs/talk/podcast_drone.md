# Podcast script: an automated, gated pipeline for aircraft design

Two voices, about nine minutes. HOST asks; ÉDER explains. Rewritten 2026-11-12 in ASD-STE100
Simplified Technical English (short sentences, active voice, one topic in each sentence), to agree
with version 3 of the drone deck. Every number comes from the records in the source table at the
end. For text-to-speech, voice each line one sentence at a time, because the Chatterbox Space
accepts a maximum of 300 characters in each call.

---

**HOST:** Welcome to Design Loop. Today's guest made a pipeline that runs engineering simulations almost without people. It also refuses to give a result that it cannot check. Éder, what problem does it solve?

**ÉDER:** A design study is slow for three reasons. Each high-fidelity simulation takes minutes or hours. A person sets up each run by hand. And a run can fail without a warning. The pipeline runs the design loop without a person, and it checks each result before a person sees it.

**HOST:** What did you test it on?

**ÉDER:** A small electric aircraft. It carries a payload of half a kilogram. The European rules for its class limit the take-off mass to four kilograms. I want the longest endurance in that limit. Six inputs define the design: span, aspect ratio, taper, battery fraction, and the camber and thickness of the wing section.

**HOST:** How does the pipeline work?

**ÉDER:** An agent, Claude Code, asks for runs through eleven typed tools. Each tool has a strict schema. Each request must pass five physics gates before a solver starts. Then the job goes into a folder on Google Drive. A worker on Colab takes the job and runs the CFD solver. Each result comes back with a SHA-256 digest, and checks examine it before it becomes a record.

**HOST:** Why a Drive folder?

**ÉDER:** Colab cannot accept inbound connections. Thus the jobs and the results move as files. The worker makes the mesh again from the job parameters. If the mesh fingerprint does not agree, the worker refuses the job.

**HOST:** And who selects the designs?

**ÉDER:** A surrogate model and an acquisition function. The language model never selects a design point.

**HOST:** Why so many checks?

**ÉDER:** Because a clean exit is not a correct result. The first solver case stopped with exit code zero. It used all of its iterations. But we compared it with a rerun that stopped correctly. Its lift was 10.5 percent low, and its drag was 24.7 percent high. Only a check after the solver could see that.

**HOST:** Did that run diverge?

**ÉDER:** No. It did not converge. It used its full budget and did not settle. That is a different failure, and the record uses the correct term.

**HOST:** Is the solver itself correct?

**ÉDER:** Mostly, and the error is on the record. Against wind-tunnel data, its lift slope is 5.5 percent high. I set a tolerance of five percent before the runs, so that check fails. Its drag is within eight percent, against a tolerance of twenty. I kept the fail. I accepted the solver with the bias written into each result. I did not change a tolerance.

**HOST:** You have two models of the aircraft?

**ÉDER:** Yes. A cheap model costs a quarter of a second for each design, so it can cover the full design space. The expensive model runs the CFD solver on the wing section. That takes about twelve minutes for each angle, and five angles for each design. The two models share all data except the section data. Thus the expensive model corrects the cheap model. It does not replace it.

**HOST:** Why a Gaussian process for the surrogate?

**ÉDER:** For three reasons. First, the expensive data are small: 32 designs. An exact Gaussian process fits them in seconds. Second, the acquisition and the confirmation need an interval, not only a mean. A Gaussian process gives an interval at each design. Third, the marginal likelihood sets its nine numbers. Nobody tunes them by hand.

**HOST:** Did you compare it with other models?

**ÉDER:** With the models in the record, yes. The cheap model alone has an endurance error of 2.3 hours. With eight expensive designs, a Gaussian process on the expensive data alone has 1.5 hours. The two-level Gaussian process has 0.82 hours. I did not fit a neural network or a tree model on this data. I say that clearly, because it is the full comparison.

**HOST:** How does the pipeline select the next design?

**ÉDER:** Two Gaussian processes, one for endurance and one for mass, give a prediction and an uncertainty at each design. An acquisition function selects the next design. On a fixed pool of 192 designs, it finds the full optimal front in 32 evaluations. After 40 evaluations, random selection still has a regret of 0.12.

**HOST:** What is regret?

**ÉDER:** Regret is the part of the true front that a strategy has not found. We measure the area that a front covers up to a reference point. Regret is the missing part of that area. Zero means the strategy found the full front. One means it found nothing of it.

**HOST:** So active learning always wins?

**ÉDER:** No, and I show that result first. On the open design space, the plain method ended at a regret of 0.32. Random selection ended at 0.29. The plain method selected designs that the gates reject, again and again. When I multiplied it by the probability to pass the gates, it got 0.09. It wins only with that feasibility model.

**HOST:** Tell me about the expensive cases.

**ÉDER:** We ran 172 solver cases on cloud workers that take jobs from the shared queue. The workers divide the queue by a hash of the case name. Thus two workers never take the same case. In this version, the session starts the cloud runtimes and restarts them when they stop. When one runtime has no more jobs, the session divides the queue again.

**HOST:** Did that matter?

**ÉDER:** Yes. Before, when both runtimes stopped, no case ran for one hour and forty minutes. A person had to restart them by hand. Now a person only signs in to cloud storage and makes the rulings that need judgment.

**HOST:** How much time does all this save?

**ÉDER:** The cheap model ran 531,441 designs in less than five hours. The 172 solver cases took 37 worker-hours, in 25 hours of elapsed time. And with eight expensive designs, the two-level model gets the accuracy that the expensive model alone needs twenty-four designs for.

**HOST:** Three times fewer expensive runs. Is that always true?

**ÉDER:** No. The benefit is large at small budgets. At twenty-four designs it is gone, and the expensive model alone is slightly better. Also, neither model's ninety-percent interval covers ninety percent of new designs. Thus I use the mean, not the interval.

**HOST:** What did the expensive level change?

**ÉDER:** On each of the 32 designs, the solver gives a lower endurance than the cheap model, by 16 to 66 percent. The best design of the cheap model was in a corner of the space, far from the mass limit. The expensive level moved the answer away from the corner, to aspect ratio seven. The mass limit then became important: about ten hours at 3.92 kilograms.

**HOST:** And you checked that answer?

**ÉDER:** I ran it through the solver. I set the pass condition before the run: endurance and mass both inside their predicted ranges. An earlier answer, on 30 designs, passed. The final answer kept its mass at 3.94 kilograms, below the limit. But its endurance was 8.96 hours, below the predicted range. That is a fail, and I report it as a fail.

**HOST:** That is an unusual thing to say in an interview.

**ÉDER:** It is the important point. The uncertainty was too narrow, and the held-out tests had already shown that. The pipeline found it with one confirmation run, before anyone built an aircraft.

**HOST:** Did you ever overrule the checks?

**ÉDER:** Two times, by name, and on the record. Thirty-six pool cases used all of their iterations, and the pipeline does not keep those runs. I accepted the runs of two designs, and later one angle of the 30-design confirmation. Each one carries its drift as a flag. That angle did not change the pass of the confirmation. The pipeline still drops all other such runs. Two other rulings are still open.

**HOST:** Give us a summary.

**ÉDER:** Put the checks after the solver, not only before it. Let the agent operate tools, but never select the data. Make each number on a slide calculable from a record. And report the losses, because the losses make the wins believable.

**HOST:** Éder, thank you for coming.

**ÉDER:** Thank you for the invitation.

---

## Sources

| Claim | Record |
|---|---|
| 0.5 kg payload, 4 kg cap, six inputs | `data/drone/rules.yaml`, `mcp_server/schemas.py` |
| Eleven typed tools, five gates | `mcp_server/server.py`, `drone/evaluate.py` |
| Drive queue, Colab worker, fingerprint check, SHA-256 digest | `worker/run_worker.py`, `mcp_server/queue.py` (deck version 3, slide 9) |
| First case: exit 0, lift −10.5 %, drag +24.7 % against its rerun; drift 5.6 % and 17.4 %, not converged | `runs/smoke/`, `runs/smoke2/` result records |
| SU2 lift slope +5.49 % against 5 % (fail), drag ratio 7.99 % against 20 % (pass), decision 8 | `runs/drone/validation/2026-11-10/v6.json`; `docs/specs/task10_tasks.md` |
| Cheap model 0.25 s per design; SU2 median 11.8 min per coarse angle | `runs/drone_grid/2026-11-08/record.json`; SU2 run records (deck version 3, slide 10) |
| 32 usable SU2 designs; endurance RMSE at n = 8: low model alone 2.299 h, GP on SU2 alone 1.525 h, two-level 0.824 h; no other model family fitted | `runs/drone_mf/2026-11-09/mf.json`, `mf.csv` (deck version 3, backup slide 40) |
| Pool replay: whole front at 32 evaluations; random 0.118 at 40 | `runs/replay_drone_pool/2026-11-08/replay.csv` |
| Regret definition | `surrogate/replay.py`, `analysis/replay_drone_online.py` (deck version 3, slide 41) |
| Online replay at 40: plain 0.317, random 0.294, feasibility-weighted 0.092 | `runs/replay_drone_online/2026-11-08/online.csv`, `2026-11-08_feas/online.csv` |
| 172 SU2 cases, 37.0 worker-hours over 24.9 h elapsed; 531,441 designs in 4.7 h | SU2 run records; `runs/drone_grid/2026-11-08/record.json` (deck version 3, slide 18) |
| Both runtimes ended 14:10 UTC, nothing ran until 15:50 | runtime operations log, `docs/specs/task10_tasks.md` |
| Two-level: SU2 alone reaches the n = 8 error at 24; at 24 SU2 alone 0.704 against 0.726 | `runs/drone_mf/2026-11-09/mf.csv` (32 designs) |
| SU2 endurance 15.8 to 65.5 % below the low model on all 32 designs | `runs/pool_af/2026-11-09/results.csv` against `runs/drone_pool_lf/2026-11-08/grid.csv` |
| Inverse at SU2 level: aspect ratio 7, 10.139 h at 3.918 kg | `runs/drone_inverse_hf/2026-11-09/inverse.json` |
| 36 budget-exhausted pool cases; decision 9 accepts designs 8 and 28, decision 10 the 30-design confirmation's 14° case, C2 pass unchanged; two rulings open | `runs/pool_af/2026-11-09/record.json`; `docs/specs/task10_tasks.md` (decisions 9 and 10) |
| Confirmations: 30-design answer pass; final answer 8.955 h below [9.116, 11.163], mass 3.936 kg inside | `runs/drone_confirm/2026-11-09_30designs/confirm.json`, `runs/drone_confirm/2026-11-09/confirm.json` |

Rounded for speech: twelve minutes (11.8), 5.5 % (5.49), eight percent (7.99), 2.3 / 1.5 / 0.82 h
(2.299 / 1.525 / 0.824), 0.12 (0.118), 0.32 / 0.29 / 0.09, "less than five hours" (4.7), 25 hours
(24.9), 16 to 66 % (15.8 to 65.5), about ten hours (10.139), 3.94 kg (3.936), 8.96 hours (8.955),
"one hour and forty minutes" (14:10 to 15:50 UTC). "Three times fewer" is 8 against 24.

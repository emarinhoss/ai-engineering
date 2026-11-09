# Podcast script: sizing a small drone with an automated CFD pipeline

Two voices, about eight minutes. HOST asks; ÉDER explains. Written 2026-11-09 from the records named
in the source table at the end, with the SU2 pool at 25 of 32 designs; every number is quoted as it
stood then. For text-to-speech each line is voiced sentence by sentence, because the Chatterbox Space
takes at most 300 characters per call.

---

**HOST:** Welcome to Design Loop. Today's guest built an automated pipeline for a supersonic inlet, then pointed the same pipeline at a completely different problem: a small electric drone. Éder, what's the question?

**ÉDER:** How long can a small electric aircraft stay up, and what does it weigh? It carries a fixed half-kilogram payload, and European rules for this class cap take-off mass at four kilograms. So the trade is endurance against mass, under a hard cap.

**HOST:** And what can you change?

**ÉDER:** Six things: span, aspect ratio, taper, the share of the mass that is battery, and the camber and thickness of the wing section. Everything else is fixed in a ledger, and every fixed number carries a source and a grade. If it's an assumption, it carries a band.

**HOST:** How do you turn six numbers into an endurance?

**ÉDER:** A vortex lattice for the wing, a drag build-up, a mass closure and an energy balance. The mass appears on both sides of its own equation, so I iterate it to a fixed point. The nominal design, two metres of span at aspect ratio ten, closes at 1.51 kilograms in 18 iterations and flies 6.75 hours.

**HOST:** That's the cheap model. Is it any good?

**ÉDER:** On the wing itself, yes. On an elliptic wing the lattice gets the span efficiency within 0.26 percent of the exact value, and it matches a published benchmark wing to about one percent. The weak part is the section. Against wind-tunnel data for the Eppler 387 airfoil, the closed-form section's lift slope is 19 to 23 percent low, and its profile drag is off by 43 to 52 percent.

**HOST:** So you need something better for the section.

**ÉDER:** That's the high level. SU2 solves the airfoil with incompressible RANS, the Spalart-Allmaras model with a transition option, on a structured C-mesh. The same lattice, closure and mission then turn that polar into endurance and mass. The two levels differ only in the section data.

**HOST:** And is SU2 right?

**ÉDER:** Not quite, and I kept that. Against the same tunnel, SU2's lift slope is 5.5 percent high at a Reynolds number of about two hundred thousand. The tolerance was five percent, set before the run. So it's a fail. I didn't move the tolerance.

**HOST:** Then why use it?

**ÉDER:** Because the drag is good, within eight percent on average against a twenty percent tolerance, and the bias is known. The decision was to accept the medium mesh as the high level with the miss recorded. Every design evaluated through SU2 carries that miss as a flag in its own record.

**HOST:** Let's talk about the pipeline. Why not just run SU2 and read the answer?

**ÉDER:** Because a clean exit is not a correct result. The first SU2 airfoil case exited with code zero after its whole iteration budget. It looked fine. Against its own properly stopped rerun, its lift was 10.5 percent off and its drag 24.7 percent off. Only checks after the solver could see that.

**HOST:** So what's in the pipeline?

**ÉDER:** An agent reaches the queue only through eleven typed tools with strict schemas and physics gates. Jobs go into a Google Drive folder, a Colab worker runs SU2, and every result comes back with a SHA-256 hash that's checked before it becomes a record. The language model never chooses a design point. The surrogate does.

**HOST:** Tell me about the surrogate.

**ÉDER:** One Gaussian process on endurance, one on log mass. Each gives a mean and an interval everywhere in the box. An acquisition function, expected hypervolume improvement, picks the next design to run. Random and Latin hypercube sampling are the baselines.

**HOST:** Does active learning win?

**ÉDER:** It depends, and that's the honest answer. On a fixed pool of 192 cheap designs, it finds the whole front by 32 evaluations in all ten seeds, where random sampling is still at a regret of 0.13. But on the open design box, plain expected improvement loses. It ends at 0.32 against random's 0.29, because it keeps picking designs the gates reject.

**HOST:** So how do you fix that?

**ÉDER:** Weight the acquisition by a model of the probability that a design passes the gates. With that, it ends at a regret of 0.09, a third of random's. So active learning wins here only with a feasibility model, and I report both results.

**HOST:** Now, the expensive runs. How many?

**ÉDER:** A pool of 32 designs, five angles each on the coarse mesh, about ten minutes per angle. Today two Colab runtimes have been working through it, and 25 designs are complete. On every one, SU2 endurance is below the cheap model's, by 16 to 60 percent.

**HOST:** That's a big range.

**ÉDER:** It is, and the top of it needs care. The two largest gaps come from designs whose SU2 polar is missing angles and never reaches the stall peak. Without those two, the range is 16 to 44 percent. Either way, the direction is consistent, which is exactly what a two-level model can use.

**HOST:** Explain the two-level model.

**ÉDER:** The expensive answer is modelled as a scaled copy of the cheap one plus a correction: high equals rho times low, plus delta. The cheap model runs everywhere, so you only need SU2 to learn the scale and the correction. The question is whether that needs fewer SU2 designs.

**HOST:** Does it?

**ÉDER:** For the mean, yes. With eight SU2 designs, the two-level model's held-out endurance error is 0.64 hours, against 1.27 for a model trained on SU2 alone. SU2 alone doesn't reach that error even with sixteen designs.

**HOST:** And the catch?

**ÉDER:** The intervals. Neither model's ninety-percent interval covers ninety percent of the held-out designs. The best is about sixty percent. So I can use the two-level mean, but I can't quote either interval as a ninety-percent interval. Which model is less over-confident has changed as the pool grew, so that's not settled.

**HOST:** And the inverse question, the longest endurance under the four-kilogram cap?

**ÉDER:** On the cheap model the answer sits in a corner of the box, with all six inputs at a bound: about 13.3 hours at 2.4 kilograms. The cap never binds there, because no design in the cheap pool comes near four kilograms. The real test is on the SU2 level, and that run is still pending.

**HOST:** If you had to sum it up?

**ÉDER:** A gated, automated pipeline carried over from a supersonic inlet to a low-speed drone with almost no changes. The physics checks were set before the runs, and the failures are on the record. Active learning works here only with a feasibility model. The two-level model saves SU2 runs on the mean, but not yet on the interval.

**HOST:** Éder, thanks for coming on.

**ÉDER:** Thanks for having me.

---

## Sources

| Claim | Record |
|---|---|
| 0.5 kg payload, 4 kg cap, six inputs and their box | `data/drone/rules.yaml`, `mcp_server/schemas.py` |
| Nominal design: 1.511 kg, 18 iterations, 6.748 h | `drone.evaluate.evaluate` on `runs/drone/validation/2026-11-08/v6.json` `nominal_params` |
| Span efficiency within 0.26 %, Warren-12 +1.01 % | `runs/drone/validation/2026-11-08/v6.json` (V6a, V6b) |
| Low-level section: lift slope 19–23 % low, profile drag 43–52 % off | `v6.json` (V6f); `docs/specs/task10_tasks.md` |
| SU2 lift slope +5.49 % vs 5 % (fail), drag ratio 8.0 % vs 20 % (pass), decision 8 | `v6.json` (V6e); `docs/specs/task10_tasks.md` |
| Smoke case: exit 0, cl −10.5 %, cd +24.7 % against its rerun | `runs/smoke/`, `runs/smoke2/` result records |
| Eleven MCP tools | `mcp_server/server.py` |
| Pool replay: EHVI regret 0.000 at 32 (10 of 10 seeds), random 0.133 | `runs/replay_drone_pool/2026-11-08/replay.csv` |
| Online replay at 40: EHVI 0.317, random 0.294, feasibility-weighted EHVI 0.092 | `runs/replay_drone_online/2026-11-08/online.csv`, `2026-11-08_feas/online.csv` |
| 25 of 32 designs complete; SU2 endurance 15.8 to 59.5 % below the low model; 15.8 to 44.2 % without designs 17 and 19 | `runs/pool_af/2026-11-09/results.csv` against `runs/drone_pool_lf/2026-11-08/grid.csv` (commit `bbbf15f`) |
| Two-level: 0.638 h vs 1.269 h at n = 8; SU2 alone 0.742 h at n = 16; coverage 0.42 to 0.62 | `runs/drone_mf/2026-11-09/mf.csv` (commit `26ae9bc`) |
| Inverse on the low model: all six inputs at a bound, 13.307 h at 2.435 kg; heaviest low-pool design 3.574 kg | `runs/drone_inverse_lf/2026-11-09/inverse.json`, `runs/drone_pool_lf/2026-11-08/grid.csv` |

Rounded for speech: 1.51 kg, 6.75 h, 5.5 %, 0.32 / 0.29 / 0.09, 0.64 / 1.27 h, 13.3 h, 2.4 kg,
16 to 60 % (and 16 to 44 %). The SU2 pool, the two-level reading and the SU2-level inverse query
move as results land; re-check them against the records before using the script after 2026-11-09.

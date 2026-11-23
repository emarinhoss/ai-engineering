# Review of the robust-endurance sizing (2026-11-23)

**Outcome: "only the 400 hp design passes Gate B" is withdrawn.** The 1.002 pass is inside the
mission model's step error (reproduced by the author: worst-corner endurance 3.5085 h as run,
3.4998 h with twice the sub-steps, 3.4953 h with four times), the design sits between two failure
modes (endurance at high engine power, transit cliff at low power), and a 380 hp design passes the
same unmodified study (reviewer). The evidence supports a 380-450 hp class engine with TP100-like
consumption, with 400 hp on the Gate B boundary. Records: `runs/task12/stage3/2026-11-23/robust/`
and `docs/validation/2026-11-23_task12_robust_sizing.md`, superseded on these points.

## Owner rulings

To be recorded as given.

## Independent review (verbatim)

# Review: robust-endurance sizing (2026-11-23)

Read-only review; no repo files were changed and `git status` is clean. `python -m pytest -q tests/task12` gives 212 passed, 1 xfailed (101 s).

**Verdict in one line:** "400 hp passes Gate B" cannot be relied on as a pass, and "only 400 hp passes" is wrong. The recorded number reproduces, but its margin is smaller than the mission model's own step error, and a 380 hp design passes the same unmodified study.

## What holds

- **The P400 record reproduces exactly.** The h = 1 worst R5 point rebuilds to 3.50846 h, with W0 4,853.6 lb at that corner and fuel at 3.5 h of 1,540.76 lb against the 1,542.00 lb limit.
- **A stronger search at h = 1 finds nothing worse.** Twelve starts (the one-at-a-time corner plus 11 random full corners), pair flips over all 29 active variables and 9 interior points per variable all converge to the recorded point. None of about 28,000 evaluated points was unflyable.
- **No member of U(1) is unflyable, as far as a direct search shows.** I maximised the transit power ratio (shaft power required over available on the worst mission sub-step). The maximum is 0.987, at the recorded corner with `engine_power_mult` 0.9 and `engine_sfc_mult` 0.9, where the aircraft still flies 6.18 h.
- **Rerate logic is correct everywhere it is used** (Stage 1 `scaled_engine`, `record_engine`/`rebuild_record`, `Built.build`, take-off in `field_detail`):
  - For the 400 hp record `power_scale` = `rating_scale` = 1.6598.
  - `lapse(20000, 120)` equals the base table's (0.4515).
  - Part-power SFC equals base × 1.05.
  - The band multiplier is applied separately, without rerate.
- **Weight law is applied as stated.** 135.8 (P/241)^0.803 gives 174.8, 187.4 and 204.0 lb.
- **Dirty-tree flag is benign.** The two dirty entries are untracked output folders (`P360/`, `P400/`). `git diff 21d9bfc a660d2e -- measurement conceptual data tests` is empty, so the code that ran is the committed code.
- **Every number in the report matches `sweep.json`** (tables, candidate counts, times, h_hat values, spans, power margins, engine weights).

## Findings

### RS-1 (critical): the 1.002 pass is inside the mission model's discretisation error

- The pass margin at h = 1 is 0.008 h (3.508 against 3.5 h), or 1.2 lb of fuel.
- Refining the mission integration removes it. At the recorded worst corner:

| Mission sub-steps (cruise, loiter) | Nominal (h) | Worst corner at h = 1 (h) |
|---|---|---|
| 5, 8 | 8.559 | 3.526 |
| 10, 16 (as run) | 8.531 | 3.508 |
| 20, 32 | 8.517 | 3.4998 |
| 40, 64 | 8.510 | 3.4953 |

- The margin exists by construction: the design is bisected (0.05 h tolerance) until theta* gives just 3.5 h, so h_hat ≈ 1.00 is the method's target, not a finding.
- **Fix:** require a stated margin (h_hat ≥ 1 + δ, with δ covering the step-refinement and search error), or size to 3.5 h plus a margin. Add a step-refinement check to the record.

### RS-2 (critical): the 400 hp design is squeezed between two failure modes

- **Endurance mode** (high power, high SFC corner) gives h_hat 1.002.
- **Transit cliff** (low power, low SFC corner) becomes unflyable at h = 1.018; hours there go from 6.14 at h = 1.01 to 0 at h = 1.02. The full study does not report this second number.
- More sized loiter raises the first and lowers the second. For 400 hp, W/S 13, A 8 (two-corner proxy):

| L_sized (h) | Endurance-mode h | Cliff h |
|---|---|---|
| 8.0 | 0.931 | 1.049 |
| 8.5 | 0.997 | 1.019 |
| 9.0 | 1.059 | 0.989 |

- The best this design can reach is about 1.01. The proxy agrees with the full studies (0.997 at 8.5 h against 1.002 at 8.53 h; 1.007 against 1.008 for the 380 hp case in RS-3).
- **Excluded uncertainties flip it.** At the recorded corner:
  - Oswald e reduced by 0.03 gives a cliff ratio of 1.002 (unflyable, 0 h) and 3.42 h in endurance mode.
  - Headwind 30 kt gives 3.25 h; 35 kt gives 2.96 h.
- **Fix:** report h_hat per failure mode, and size against both corners at once.

### RS-3 (critical): "only 400 hp passes" is a grid and method artefact; a 380 hp design passes

- I ran the repo's unmodified `robust_sizing.run_study` (full `info_gap.study`) on 380 hp, W/S 12, A 8, L_sized 8.75 h. It has W0 4,268 lb, fuel 1,525 lb and no failed compliance row.
- Result: **R5 guarantee h_hat 1.008, R7 1.418, Gate B passed.** The first failing point is the transit cliff at h = 1.0085.
- By the two-corner proxy:
  - 370 hp, W/S 11.5, A 8, 8.75 h reaches about 1.001.
  - 360 hp tops out at about 0.98 with compliance; it reaches 1.00 only at W/S 11, where R9 negative gust fails.
  - 400 hp, W/S 12, A 8, 8.9 h reaches about 1.04 (W0 4,416 lb).
  - 420 hp, W/S 12, A 8, 9.0 h reaches about 1.06.
  - 450 hp, W/S 13, A 8, 9.0 h reaches about 1.08 (W0 4,624 lb).
- The slope is about 0.0015 in h per hp, so the 400 hp pass margin is worth a few hp.
- **Why the sweep missed it:**
  - 380 hp is not on the power grid.
  - Refinement happens only around each power's lightest compliant point.
  - The 330 and 360 hp designs in the final table were sized only against the high-power corner, so they fail on the cliff they were never sized for. Their "fail" describes those designs, not the power.
- **Fix:** withdraw "only the 400 hp passes"; replace it with a robustness-against-power curve.

### RS-4 (major): "sized at one theta*, checked by search" does not converge here

- The two failure modes have different worst corners (power 0.9 against 1.1), and the iteration flips between them:
  - Iteration 1 used power 0.9 (cliff). At 330 and 360 hp the transit is unflyable at every L for W/S ≥ 13, hence "no compliant candidate".
  - Iteration 2 used power 1.1 (endurance). No cliff at that corner, so 330 and 360 hp get designs that then fail on the cliff.
  - A third iteration would return to power 0.9.
- The 400 hp result is self-consistent only because its theta* came from a 400 hp study.
- **Iteration 1 false negative:** 360 hp, W/S 12, A 8, L 8.0 has no failed row, W0 3,988 lb, and flies 5.6 h at iteration 1's corner. It was never evaluated (W/S 12 is off-grid, and no refinement runs without a compliant grid point). It is lighter than iteration 1's 400 hp winner (4,079 lb).
- **Bisection assumes endurance rises with L.** At the cliff corner it does not: 400 hp, W/S 13, A 8 gives 5.78, 6.16 and 0 h at L = 8, 8.5 and 9. `bisect_sized` treats a 0 h (unflyable) midpoint as "L too small" and moves the lower bound up, the wrong direction. I did not find a recorded row changed by this, but it is latent.
- **Fix:**
  1. Keep a set of corners (endurance and cliff) and require 3.5 h at all of them, adding each study's worst point to the set.
  2. Iterate per power, not only for the overall lightest.
  3. Treat unflyable as "too heavy" in the bisection.
  4. Add a test with a non-monotone endurance function.

### RS-5 (major): "does not close" is raised at the 3,000 lb first guess, discarding designs that close

- `sizing.solve_takeoff_weight` raises when the fractions sum to 1 or more at the initial guess (`uav.evaluate` default `W0_guess=3000.0`). `robust_sizing` reads that as "too large".
- Examples that raise at 3,000 lb but close from a 4,000 lb guess:
  - 450 hp, W/S 11, A 8, 8 h: W0 4,409 lb.
  - 450 hp, W/S 11, A 12, 8 h: W0 4,746 lb.
  - 360 hp, W/S 13, A 8, 11 h: W0 4,443 lb.
  - 400 hp, W/S 14, A 7, 10 h: W0 4,377 lb.
- Through `stage1.analyse` (tail re-sizing) it also hits 450 hp, W/S 13, A 8, 8 h and 400 hp, W/S 11, A 8, 8.7 h.
- **Consequences:**
  - Most 450 hp rows marked "not reached at 8.03 h" are this artefact; the remaining 450 hp rows fail only the R18 placard study margin. With a 4,500 lb guess, 450 hp at W/S 12 and 13 has no failed row. "450 hp: no compliant candidate" is therefore false.
  - The upper end of the L bisection is set by the artefact.
  - The row's `status` loses the real reason.
- The per-power winners at 330 to 400 hp are not affected: the discarded cases are heavier.
- **Fix:** start the weight iteration from a guess that scales with the engine and fuel, or retry upward before declaring non-closure; record the reason per row; re-run 450 hp.

### RS-6 (medium): report wording and record gaps

- The "Overall" section says "Lightest compliant design: 330 hp ... NOT passed" and never names the design that passes; the headline lives only in the commit message.
- "No compliant candidate" carries no reason: 300 hp is R9 negative gust at W/S 11, 450 hp is RS-5 plus R18.
- The per-design `info_gap.json` files have no `inputs` block (commit, seed, hashes, dirty flag), because `run_study` writes `study()` directly. IG-6 asked for these.
- `sweep.json` records the commit at the end of the run (48c4850, created mid-run), not at the start. The code is identical, so this is a record-keeping point only.
- Tests cover the bisection on toy functions and nominal theta only. Nothing tests the cliff corner, the first-guess non-closure or the two-corner behaviour.

### RS-7 (medium): what the engine model implies for the power figure

- The table gives 393.9 hp static at sea level for the "400 hp" engine (0.985 of rated; pre-existing).
- Loiter runs at about 30 % power on the 1.3 V_stall floor, at SFC 1.17 to 1.23 lb/hp/h. More power worsens loiter SFC, which is why power 1.1 is the endurance-mode worst case. A larger engine is penalised on one side and needed on the other.
- The cliff is driven by weight growth: W0 at the corner is 4,854 lb against 4,240 lb (We +614 lb, +28 %), with eta_p 0.75 and CLmax 1.3.
- At that corner the model's own `power_req` exceeds the rated 400 hp for ceiling (430 hp) and is 389 hp for the 30° turn at loiter. R12 and R16 are not part of Gate B's horizon; the owner should know they fail inside U(1).
- A real engine of this class would have its own SFC curve and weight; the photo-scaled TP100 curve is the main unverified assumption behind any power figure.

## Owner questions

1. **Should Gate B require a margin above h = 1?**
   - (a) Keep h_hat ≥ 1. Then 380 hp already "passes", and the result flips with step count.
   - (b) Require h_hat ≥ 1 + δ (for example 1.05 or 1.10). That points to roughly 420 to 450 hp in this model; it needs the RS-5 fix and a re-run.
   - (c) Replace pass/fail with a curve of h_hat against power, per failure mode, and choose the power from it.
2. **Should the transit cliff be a separate Gate B line?** It is currently hidden inside the R5 guarantee. A separate line would show power margin on the transit directly and make the trade against fuel visible.
3. **Photo-scaled TP100 or a real engine?** The spec's R3 calls for the nearest real turboprop from an open datasheet. The current result says "about 380 to 450 hp with TP100-like SFC", which no engine is shown to have.
4. **Narrow the weight bands instead of adding power?** The corner stacks 13 weight-moving variables at their harmful ends. IG-2 listed the largest contributors (gust velocity, avionics weight, fuselage fineness). Measuring or fixing two or three of these may be cheaper than 40 hp.
5. **Should R12 and R16 hold inside U(1)?** They do not at the 400 hp corner.

## Verdict

- **Can "400 hp passes Gate B" be relied on? No.** The number reproduces and survives a stronger search, but the margin (0.008 h) is below the mission step error (0.013 h), the cliff is at h = 1.018, and e − 0.03 or headwind + 5 kt removes the pass.
- **Power class the evidence supports:** the Gate B boundary in this model lies at about 370 to 400 hp (380 hp passes at 1.008; 360 hp does not with compliance). A pass with visible margin needs about 420 to 450 hp, and 450 hp has not been properly evaluated (RS-5). The honest statement is "a 380 to 450 hp class engine with TP100-like consumption; 400 hp sits on the boundary".
- **R7:** passes at every power studied (1.28 to 1.44); no concern.

Probe scripts and outputs are in `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/`:

- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/c.py` (shared setup, transit power ratio)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/a1.py` (reproduction, engine multiplier scan)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/a2.py` (maximum transit power ratio in U(1))
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/a3.py` and `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/a3_P400.out` (12-start search at h = 1)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/a4.py` (cliff horizon)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/a5.py` (rerate check, headwind, Oswald e, mission rows)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/a6.py` (mission step refinement)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b1.py` and `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b1.out` (endurance against L at both corners)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b2.py` and `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b3.py` (first-guess non-closure)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b4.py`, `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b4.out` and `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b4b.out` (two-corner proxy over power, W/S and L)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b5.py`, `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/b5_380.out` and the record folder `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rs/P380` (full study of the 380 hp design)

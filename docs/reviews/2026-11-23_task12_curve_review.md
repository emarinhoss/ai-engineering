# Review of the robustness-against-power curve (2026-11-23)

**Outcome: relied on with actions.** Records reproduce, corner sets converged, method sound. The
curve shows W0 needed for the R5 guarantee at h = 1 per power (endurance h is 1.00 by
construction); the step-refinement "flip" is a check artefact (consistent sizing costs 3-6 lb);
the gust margin row decides 360 hp (370 hp passes at 4,263 lb); the fixed 110 kt placard adds
50-230 lb at 420-480 hp. Reviewer's proxy: h 1.05 needs at least 420 hp (about +100-200 lb),
h 1.10 about 450 hp.

## Owner rulings

| Question | Ruling (Éder, 2026-11-23) |
|---|---|
| Robustness margin above h = 1 | **h = 1.05**, pointing to a 420-450 hp class engine with TP100-like consumption (about 4,500 lb); re-run the curve at fixed targets (1.00 / 1.05 / 1.10) with the report fixes, then search for real engines in that class |
| V_C placard (R18) for that class | **Raise with the engine**: V_C set per design at 10 % above its fastest cruise sub-step (EAS), rounded up to 5 kt, never below the round-4 110 kt (author's reading: the floor keeps the earlier ruling as the minimum); gusts and structure sized at it |

## Independent review (verbatim)

# Review: robustness-against-power curve (2026-11-23)

Read-only review; no repo files changed, `git status` clean. `python -m pytest -q tests/task12` gives 223 passed, 1 xfailed (129 s).

**Verdict in one line:** the records are correct and reproducible, but the report is not yet the curve the ruling asked for. It can be relied on, with actions, as "W0 needed to meet the 3.5 h guarantee at h = 1, per power", not as a robustness curve.

## What holds

- **Every number in the report matches `curve.json`:** the curve table, the step table, the candidate counts and the inputs block.
- **The designs rebuild exactly.** For example 380 hp, W/S 12, A 8, L 8.6875 h gives W0 4,253 lb, 3.5160 h at the endurance corner and cliff ratio 0.9914.
- **The corner sets are converged.**
  - The mode searches and the full studies return the seed corners as the h = 1 worst points at 380, 400, 420 and 480 hp.
  - At 450 hp the worst endurance point differs in one variable (`wing_t_c` 0.18 instead of 0.12): 3.5013 h against 3.5020 h. It is not a violation, so it is correctly not added.
  - My own check (500 random perturbations of each corner per mode, at 380, 420 and 450 hp) found nothing worse than the recorded points and no unflyable member.
- **The full study agrees with the mode split.** Its `R5_guarantee` equals the minimum of the two modes to within 0.0001 in h at all five powers.
- **`robustness_scan` is sound for this use.** The scan from h = 0.5 in steps of 0.25 stops at the first failure, so the vacuous region at large h is never reached. It would only miss a failing window narrower than 0.25 in h that then closes again, which does not occur here.
- **The W0_guess pass-throughs are harmless.** Defaults are unchanged; W0 for 400 hp, W/S 13, A 8 from guesses of 3,800, 4,300 and 5,200 lb agrees to 0.012 lb.
- **`bisect_two_corner` moves the right bound on an unflyable point.** The traces in `power_result.json` confirm it.

## Findings

### RC2-1 (major): the curve does not show robustness against power

- **Endurance h is about 1.00 by construction.** The fuel is sized until the worst case at h = 1 gives 3.5 h. The spread 1.000 to 1.003 is the bisection residue (L sits on a 1/32 h lattice), not physics.
- **Cliff h is the cliff of the lightest design, not the best that power can do.** The kink between 420 and 450 hp comes from the selected W/S changing from 14 to 13 (see RC2-3).
- **The minimum of the two, the plot's flat line and "binding: endurance" in every row carry no information.**
- **What the run does establish:** W0 at the h = 1 guarantee per power, the cliff margin left at that design, and where no design exists.
- **What the owner needs is the cost of margin.** I sized against both seed corners scaled to a target h with the repo's `evaluate_candidate_sets`. This is a proxy: W/S 12 to 14 and A 8 to 9 only, same corner directions, no full studies.

| P (hp) | W0 at h = 1.00 (record) | lightest compliant W0 at h = 1.05 | at h = 1.10 |
|---|---|---|---|
| 380 | 4,253 | none | none |
| 400 | 4,240 | none | none |
| 420 | 4,298 | 4,491 (W/S 13, A 9; cliff ratio 0.9985) | none |
| 450 | 4,451 | 4,558 (W/S 13, A 8; cliff ratio 0.965) | 4,774 (W/S 12, A 8; 0.989) |
| 480 | 4,655 | 4,758 (W/S 13, A 9) | 4,794 (W/S 13, A 8; 0.978) |

- **Reading:** margin above h = 1 cannot be bought at 380 to 400 hp. An h of 1.05 costs about 100 to 200 lb and needs at least 420 hp; 1.10 needs about 450 hp.
- **Fix:** report W0 against power at fixed h targets (1.00, 1.05, 1.10), or the largest achievable min(h_E, h_C) per power. Drop the flat endurance line or label it "sized to 1 by construction". Show the no-design powers on the plot.

### RC2-2 (major): the step-refinement "flip" at 400 to 450 hp is a check artefact

- **The check is inconsistent.** It keeps the fuel sized on the coarse mission and judges the corner on the fine one.
- **Sizing and judging both with refined steps changes almost nothing.** Same L_sized at all three powers checked; the fuel grows 2 to 3.5 lb.

| Design | W0 as run (lb) | W0, steps x2 | W0, steps x4 | worst endurance, steps x4 (h) |
|---|---|---|---|---|
| 380 hp, W/S 12, A 8 | 4,253.4 | 4,256.9 | 4,258.6 | 3.5164 |
| 400 hp, W/S 13, A 8 | 4,240.2 | 4,243.6 | 4,245.3 | 3.5081 |
| 450 hp, W/S 13, A 8 | 4,450.9 | 4,454.9 | 4,456.9 | 3.5021 |

- **Which powers flip is luck of the bisection lattice.** The refinement shift is 0.009 h. Designs with a residue above that (380 hp at 0.016, 480 hp at 0.0094) "hold"; the others (0.0085, 0.003, 0.001) "flip".
- **The step error is a W0 bias of about +3 to +6 lb (0.1 %), not a verdict question.**
- **A real margin costs more.** Sizing to 3.6 h instead of 3.5 h adds 37 to 42 lb. At 380 hp that pushes the cliff ratio to 0.997: only 3.50 to about 3.64 h of worst-case endurance is available there before the cliff.
- **Fix:** replace the "verdict depends on refinement" column with the W0 and fuel bias, or size against 3.5 h plus a stated margin.

### RC2-3 (major): W0 at 450 and 480 hp is inflated by the fixed V_C placard row (R18)

- R18 requires the fastest mission sub-step plus 10 % to stay under the ledger's fixed 110 kt EAS placard (a "study margin").
- A stronger engine flies faster, so the light high-W/S candidates fail R18 (112 to 116 kt against 110). The curve takes heavier ones.

| P (hp) | W0 in the curve | lightest that satisfies both corners but fails R18 only | difference |
|---|---|---|---|
| 420 | 4,298 | 4,247 (W/S 14, A 8) | 51 |
| 450 | 4,451 | 4,310 (W/S 15, A 8) | 141 |
| 480 | 4,655 | 4,428 (W/S 15, A 8) | 227 |

- About half of the W0 growth from 400 to 480 hp is this row, not the engine. The report does not mention it.
- **Fix:** state it beside the table and give both W0 columns, or let the owner rule on the placard (question 4).

### RC2-4 (major): "no design" is real at 300 and 340 hp, but at 360 hp it is decided by the R9 gust margin

- **300 hp:** every candidate is beyond the cliff already at 8 h. My probes at W/S 8, 9, 10 with A 6 and 8 give ratios 1.015 to 1.098. Real in this model.
- **340 hp:** no L satisfies both corners. Probes at W/S 9 and 10 with A 6, 7, 8 also fail. Real in this model.
- **360 hp:** W/S 11, A 8, L 8.84 h (W0 4,285 lb) satisfies both corners, with 3.503 h and cliff ratio 0.9995.
  - It is rejected only by R9 negative gust: n = -1.732 against -1.70. The limit is -1.80 plus the 0.1 g round-4 margin.
  - Probes at W/S 11.25, 11.5 and 12 with A 6 to 8 give no design, so this is not a grid artefact.
  - Even if admitted, the design has zero cliff margin.
- **370 hp (off grid):** W/S 11.5, A 8, L 8.75 h is compliant, at W0 4,263 lb, 3.503 h and ratio 0.994. The boundary is therefore between 360 and 370 hp, not between 360 and 380 hp.
- **Not a first-guess or bounds artefact.** Every 300 to 360 hp row closed, and the L lattice could only hide a window narrower than 0.03 h.
- **Fix:** name the R9 row and the 370 hp result in the report. Add W/S 11.5 or 370 hp to the grid.

### RC2-5 (medium): report text

- **"At or above 1 at every power studied" appears three times and misleads.**
  - 300 to 360 hp were studied and have no design.
  - The endurance line is true by construction.
  - The step table immediately above says the verdict flips at 400 to 450 hp.
- **The "Powers with no design" reasons are garbled.**
  - Digits are replaced by "#" ("Stage # compliance failed: R# negative gust ... round# margin").
  - The 140-character cut splits one reason into two near-duplicates ending "clif".
- **The convergence table says "1 + 1, True"** without noting that 450 hp's worst point differs from the seed.
- **The "refined, search repeated" columns equal the "recorded point" columns in every row.** One sentence would do.
- **"Dirty tree: True" is only the untracked output folder;** the report should say so.
- **The module docstring still describes the old single-corner sweep.**
- **Three-decimal h values are printed finer than they are meaningful** (420 hp shows 1.001 against 1.000, from 1.0006 and 1.0005).

### RC2-6 (low): code notes

- `transit_power_ratio` copies the speed grid of `uav._leg_speed` (76 points, 2 % steps). A test that fails if the two drift apart would protect it.
- `close_with_retry` also retries on "did not converge" (400 hp, W/S 14, A 12), where a larger guess cannot help. The row is recorded and is not a contender.
- The bisection can miss an ok-window narrower than the L lattice. Acceptable, but the status text should say "no L on the lattice".

## Owner questions

1. **Which curve should Gate B use?**
   - (a) The present table, relabelled "W0 at the h = 1 guarantee". Cheap, but it cannot rank engines on robustness.
   - (b) W0 against power at h = 1.00, 1.05 and 1.10. This shows the price of margin directly; it needs about one more run of the same size.
   - (c) The largest achievable h per power. This is the closest reading of the ruling, but W0 is then unbounded unless capped.
2. **What margin above h = 1 do you want?** With none, 370 to 400 hp is enough, but the design sits on both failure modes at once. An h of 1.05 points to 420 to 450 hp; 1.10 to 450 to 480 hp.
3. **Does the 0.1 g gust margin stay as a hard row?** It is what excludes 360 hp, and it also excludes W/S 11 at 380 hp.
4. **Is the 110 kt V_C placard fixed, or does it move with the engine?** Fixed, 450 to 480 hp pay 140 to 230 lb. Raised, the gust loads and structure weight need re-checking.
5. **Still open from the first review:** no real engine is shown to have the TP100-like consumption all of this assumes.

## Verdict

- **Relied on, with actions.** The records, sizing, corner sets and scan are sound. The presentation (RC2-1, RC2-2, RC2-5) and two unstated drivers (RC2-3, RC2-4) need fixing before the owner chooses an engine from it.
- **Supported engine class: 420 to 450 hp with TP100-like consumption.**
  - W0 is about 4,300 to 4,450 lb at h = 1.00 (records) and about 4,490 to 4,560 lb at h = 1.05 (proxy).
  - 370 to 400 hp meets the guarantee at W0 4,240 to 4,260 lb, but with no obtainable margin: cliff h is 1.01 to 1.02.
  - 480 hp buys h of about 1.10 at about 4,800 lb.
  - Nothing at or below 360 hp meets it under the current rows.
- **R7:** 1.42 to 1.54 at every power with a design; no concern.

Probe scripts and outputs are in `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/`:

- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/c.py` (shared setup, scaled corners)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p1.py` (reproduction, R9 values)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p2.py` with `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p2a.out` (off-grid probes at 300 to 360 hp) and `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p2b.out` (370 hp; h targets 1.05 and 1.10)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p3.py` and `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p3.out` (sizing with refined steps; 3.6 h margin)
- `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p4.py` and `/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/rc2/p4.out` (random perturbation of the corners)

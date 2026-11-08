# Deck outline: low-speed aircraft sizing with the inlet pipeline (Task 10)

Slide-by-slide outline for `docs/talk/deck_drone.pptx`, built by `docs/talk/build_deck_drone.py`. First
written 2026-11-08. This is a separate deck from the inlet talk (question 4 of
`docs/specs/task10_tasks.md`, default: a separate deck). Every quantitative claim is read from a
record at build time or marked PENDING.

## Conventions

- **Source** is one or more existing files under `runs/`, `docs/`, `designs/`, `data/` or `drone/` in
  backticks, or `PENDING:` followed by the batch that will produce it: `pool batch` (the 172 SU2 cases
  of `designs/pool_af_cases.csv`), `multi-fidelity analysis` (T10.10c) or `confirmation run` (T10.10d).
  A slide with no number says `none (no number)`.
- **Placeholders.** A message or speaker note may contain `{name}`. The build script replaces it with a
  value it reads from the record named in that slide's Source line; the build fails on a name it cannot
  fill. So no number in this file is typed: they are all computed from files.
- **Speaker notes** are at most three sentences each.
- **Spelling** is standard US English on every slide, caption, figure label and speaker note.
- **Frozen files.** `docs/talk/build_deck.py`, `docs/talk/outline.md` and `docs/talk/deck.pptx` (the inlet
  deck) are not touched; the build script imports their helpers.

## Slides

### D1. Title

- **Message:** A small electric aircraft sized by the same gated, queued, active-learning pipeline as the supersonic inlet, with the validation verdicts and the pending SU2 results stated as they stand.
- **Figure or table:** Title card only.
- **Source:** none (no number)
- **Speaker notes:** The inlet study built a pipeline; this study asks whether it carries over to a different physics problem. The answer so far is partly in, and every slide says which part.

### D2. The questions of the study

- **Message:** Four questions: the front, active learning against sampling, the two-level model, and the inverse query under a mass cap.
- **Figure or table:** Table of the four questions of section 1 of the spec with the status of each answer.
- **Source:** `docs/specs/task10_drone_sizing.md` (section 1); `docs/specs/task10_tasks.md`
- **Speaker notes:** Questions 1 and 2 have answers on the low-fidelity model. Questions 3 and 4 wait for the SU2 pool. A null result on any of them is reported as such.

### D3. The model in one picture

- **Message:** Six inputs go through a vortex lattice, a drag build-up, a mass closure and a mission to endurance and take-off mass, at two fidelity levels that differ only in the section data.
- **Figure or table:** Pipeline: six inputs, vortex-lattice method, drag build-up, mass closure, mission, two outputs; below it the two section-data levels.
- **Source:** `docs/specs/task10_drone_sizing.md` (sections 2, 3 and 6); `drone/evaluate.py`
- **Speaker notes:** The lattice, the drag build-up and the closure are the same at both levels. The low level takes the section from closed forms; the high level takes it from an SU2 airfoil polar at the design's own Reynolds number.

### D4. Gates and the queue: what is new

- **Message:** The airfoil2d family stops on a Cauchy criterion because the first smoke case ran its whole {smoke_budget}-iteration budget unconverged; the rerun stopped itself at {smoke2_iters}.
- **Figure or table:** Table: the two smoke runs (budget, iterations, lift and drag drift, status) and the Cauchy settings read from the case template.
- **Source:** `runs/smoke/airfoil2d-96a9dd0f51/result.json`; `runs/smoke2/airfoil2d-51d551f2cc/result.json`; `cases/templates/inc_rans_airfoil.cfg`; `docs/specs/task10_tasks.md` (decision 6)
- **Speaker notes:** Everything else in the queue, the worker and the gates is the inlet machinery unchanged. The new parts are the airfoil family, its mesh checks and the convergence rule.

### D5. Validation V6a to V6d

- **Message:** The solver's own checks pass: {n_pass} toleranced rows pass, {n_pending} is pending a source, {n_fail} fails.
- **Figure or table:** Table of V6a to V6d: row group, rows by verdict, and the worst deviation among the toleranced rows.
- **Source:** `runs/drone/validation/2026-11-08/v6.json`
- **Speaker notes:** These rows check the vortex lattice against Helmbold's slope and lifting-line theory, the Warren-12 benchmark, the lattice convergence and the mass and energy closure. The one pending row waits on the source of the benchmark's moment reference point; it is not tuned to agree.

### D6. V6f: the low-fidelity section against the E387 tunnel

- **Message:** The closed-form section is {f_clalpha_range} low in lift slope, misses profile drag by {f_cd_range} and overpredicts cl_max by {f_clmax_range}; nothing was tuned.
- **Figure or table:** Table of the twelve V6f rows by Reynolds number.
- **Source:** `runs/drone/validation/2026-11-08/v6.json`; `data/validation/e387_uiuc.yaml`
- **Speaker notes:** These are the sizes of the errors the two-level model has to learn. The lift effectiveness the ledger assumes does not contain the value the tunnel implies; that is a ledger ruling and not a number to move here.

### D7. V6e: SU2 against the tunnel, and decision 8

- **Message:** SU2's lift slope misses the tunnel by {v6e_dev} against a {v6e_tol} tolerance: a fail, kept as a fail, and accepted as the high level with the bias recorded.
- **Figure or table:** Figure d (SU2 cl and cd against the UIUC E387 data at the same angles) and the V6e rows.
- **Source:** `docs/validation/figures/task10/d_e387_comparison.png`; `runs/drone/validation/2026-11-08/v6.json`; `runs/e387/airfoil2d-498b156761/result.json`; `docs/specs/task10_tasks.md` (V6e and decision 8)
- **Speaker notes:** The tolerance was fixed before any case ran, and the miss is reported as a fail. Decision 8 accepts the medium-mesh polar as the high level and attaches the miss to every record it produces. The figure draws whatever E387 points exist at build time.

### D8. The low-fidelity grid and its exact front

- **Message:** Because the low level is cheap, the exact front over the whole box exists: {front_n} designs out of {grid_n} grid points, {gated_n} of which were gated.
- **Figure or table:** Figure a: the exact front and the 192-point pool's front, endurance against take-off mass.
- **Source:** `docs/validation/figures/task10/a_front_lowfi.png`; `runs/drone_grid/2026-11-08/record.json`; `runs/drone_grid/2026-11-08/front.csv`; `runs/drone_pool_lf/2026-11-08/front.csv`
- **Speaker notes:** The exact front is the reference against which both replays measure regret. The pool's front has {pool_front_n} designs.

### D9. The pool replay

- **Message:** On the 192-point low pool, EHVI reaches regret {ehvi_32} at 32 evaluations while random is at {rand_40} after 40.
- **Figure or table:** Figure b and a table of mean regret at five budgets for four strategies.
- **Source:** `docs/validation/figures/task10/b_pool_replay.png`; `runs/replay_drone_pool/2026-11-08/replay.csv`
- **Speaker notes:** This is the easy case: a smooth, gate-free pool. The online replay is the test that matters.

### D10. Online replay: plain EHVI loses, weighted EHVI wins

- **Message:** On the unrestricted box plain EHVI ends at regret {ehvi_on_40} against random's {rand_on_40} and wastes {ehvi_gated} of 32 picks on gated designs; weighted by P(feasible) it ends at {feas_on_40}.
- **Figure or table:** Figure c and a table of regret and gated picks at the last budget for six strategies.
- **Source:** `docs/validation/figures/task10/c_online_regret.png`; `runs/replay_drone_online/2026-11-08/online.csv`; `runs/replay_drone_online/2026-11-08_feas/online.csv`; `runs/replay_drone_online/2026-11-08/record.json`
- **Speaker notes:** The front lies against the gated edge of the box, and the two GPs know nothing about the gates. Active learning beats space-filling sampling only when the acquisition knows where the design is buildable. Both runs are published.

### D11. The SU2 pool

- **Message:** PENDING: the {pool_cases} SU2 airfoil cases are staged and not yet ingested.
- **Figure or table:** Placeholder box naming the pool batch; the front with its GP band will go here (figure not drawn).
- **Source:** PENDING: pool batch (`designs/pool_af_cases.csv`)
- **Speaker notes:** The case table is committed and the cases are queued. No SU2 pool number appears in this deck until `runs/pool_af/results.csv` exists.

### D12. Multi-fidelity

- **Message:** PENDING: whether the two-level model reaches a given held-out error with fewer SU2 designs than SU2 alone.
- **Figure or table:** Placeholder box; the error-against-designs figure will go here (figure not drawn).
- **Source:** PENDING: multi-fidelity analysis (T10.10c)
- **Speaker notes:** The known bias of the high level is recorded beside every SU2 number, so the correction term absorbs a known offset. Whether that pays is the measurement still to come.

### D13. The inverse query and its confirmation

- **Message:** PENDING: the longest-endurance design under the 4.0 kg cap with P(mass at most cap) of at least 0.9, and one SU2 polar at that design.
- **Figure or table:** Placeholder box.
- **Source:** PENDING: confirmation run (T10.10d)
- **Speaker notes:** Nothing here is answered yet. The query is a computation on the fitted surrogate; the confirmation is one real solver run.

### D14. Biases that travel with every number

- **Message:** The model's named biases stay beside every figure, and the high level carries the V6e miss: at Re {e387_re} SU2's cl is {su2_cl_range} and its cd is {su2_cd_range}, point by point against the tunnel.
- **Figure or table:** Two lists: section 13 of the spec, and the decision-8 flags read from the validation record.
- **Source:** `docs/specs/task10_drone_sizing.md` (section 13); `runs/drone/validation/2026-11-08/v6.json`; `runs/e387/airfoil2d-498b156761/result.json`; `analysis/high_level_bias.py`
- **Speaker notes:** The flags are generated from the validation record, so they cannot drift from it. A reader of any single design record sees the miss without opening this deck.

### D15. What the gated process caught

- **Message:** Each of these was found by a check or a recorded run before it could reach a result.
- **Figure or table:** Table of six items from the task record: what was caught, by what, and the fix.
- **Source:** `docs/specs/task10_tasks.md`; `runs/smoke/airfoil2d-96a9dd0f51/error.json`; `drone/vlm.py`
- **Speaker notes:** The list holds only items recorded in the task file. Fix and cause are in the record each row names.


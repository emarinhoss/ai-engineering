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
- **Equations.** A slide that states a formula lists its LaTeX source in one line,
  `- **Equations:** $...$; $...$`, under its Figure line. The build renders each with matplotlib mathtext
  (`docs/talk/equations.py`) and places it as a picture whose alt text is the source; the relation is the
  one the repo's code implements, with the module named beside the constant in `build_deck_drone.py`.
- **Speaker notes** are at most three sentences each.
- **Spelling** is standard US English on every slide, caption, figure label and speaker note.
- **Shared files.** `docs/talk/build_deck.py`, `docs/talk/outline.md` and `docs/talk/deck.pptx` (the inlet
  deck) changed only to add rendered equations (the same `**Equations:**` convention); the build script
  imports their helpers.

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
- **Figure or table:** Pipeline drawn with boxes and arrows: six inputs with their ranges, geometry, vortex lattice, drag build-up, mass closure with its loop, mission, outputs; above the drag block the two section-data levels, the only block that differs.
- **Equations:** $m_{k{+}1}=\sum_i m_i(m_k),\quad |m_{k{+}1}-m_k|/m_k<10^{-9}$; $V=\sqrt{\dfrac{2W}{\rho\,S\,C_L}},\quad P=\dfrac{D\,V}{\eta_p}$
- **Source:** `docs/specs/task10_drone_sizing.md` (sections 2, 3 and 6); `drone/evaluate.py`; `mcp_server/schemas.py` (DRONE_BOUNDS); `docs/talk/build_deck_drone.py`
- **Speaker notes:** The lattice, the drag build-up and the closure are the same at both levels. The low level takes the section from closed forms; the high level takes it from an SU2 airfoil polar at the design's own Reynolds number.

### D3a. The nominal design in one top view

- **Message:** The nominal design has a {nom_span} m span, aspect ratio {nom_ar} and taper {nom_taper}: {nom_area} m^2 of wing and a closed take-off mass of {nom_mtow} kg; tail and fuselage follow from the wing by rule.
- **Figure or table:** Top view drawn by `drone.geometry.build`, with the six inputs labeled and the NACA section inset.
- **Source:** `drone/geometry.py`; `drone/naca.py`; `drone/evaluate.py`; `runs/drone/validation/2026-11-08/v6.json`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** Span and aspect ratio fix the wing area, taper fixes the chords, and the tail is sized by volume coefficients with a fixed arm. The fuselage is a body of revolution holding the payload and the battery; its position along the wing is schematic.

### D3b. Mass closure and the endurance balance

- **Message:** Take-off mass is a fixed point and endurance is an energy balance: at the nominal design the closure takes {nom_iters} iterations and the balance gives {nom_endurance} h.
- **Figure or table:** The closure loop, the nominal mass breakdown and the energy chain with its nominal values.
- **Equations:** $m_{k{+}1}=m_{\mathrm{pay}}+f_b\,m_k+m_{\mathrm{skin}}+m_{\mathrm{spar}}+m_{\mathrm{tail}}+m_{\mathrm{fus}}+P_{\mathrm{inst}}/\sigma_P$; $P_{\mathrm{cr}}=\dfrac{D\,V}{\eta_p}$; $P_{\mathrm{inst}}=\max\!\left(k_P\,P_{\mathrm{cr}},\ \dfrac{W\,\dot h}{\eta_p}+P_{\mathrm{cr}}\right)$; $t=\dfrac{\mathrm{DoD}\,E_{\mathrm{spec}}\,3600\,m_b-P_{\mathrm{inst}}\,t_{\mathrm{climb}}}{3600\,P_{\mathrm{cr}}}$
- **Source:** `drone/evaluate.py`; `drone/mission.py`; `runs/drone/validation/2026-11-08/v6.json`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** Battery mass is the battery fraction times take-off mass, so the loop has to be iterated. V6d checks that the loop and the energy balance close to 1e-9.

### D4. Gates and the queue: what is new

- **Message:** The airfoil2d family stops on a Cauchy criterion because the first smoke case ran its whole {smoke_budget}-iteration budget unconverged; the rerun stopped itself at {smoke2_iters}.
- **Figure or table:** Table: the two smoke runs (budget, iterations, lift and drag drift, status) and the Cauchy settings read from the case template.
- **Equations:** $\mathrm{drift}=\dfrac{\max_{k\in W}f_k-\min_{k\in W}f_k}{|f_n|}\times100\,\%$; $W=\{\,n-\lceil 0.2\,n\rceil+1,\ \ldots,\ n\,\}$; $\dfrac{1}{N}\sum_{k=n-N+1}^{n}\dfrac{|f_k-f_{k-1}|}{|f_k|}<\varepsilon,\quad f\in\{C_L,C_D\}$
- **Source:** `runs/smoke/airfoil2d-96a9dd0f51/result.json`; `runs/smoke2/airfoil2d-51d551f2cc/result.json`; `cases/templates/inc_rans_airfoil.cfg`; `docs/specs/task10_tasks.md` (decision 6)
- **Speaker notes:** Everything else in the queue, the worker and the gates is the inlet machinery unchanged. The new parts are the airfoil family, its mesh checks and the convergence rule.

### D4a. Where each gate sits

- **Message:** Every request passes the same ordered checks before SU2 starts, and every result passes more before it becomes a record; the numbered marks show where.
- **Figure or table:** Diagram from the request through the MCP tools, the Drive queue folder and the Colab worker to the ingested record, with the gates numbered.
- **Source:** `mcp_server/queue.py`; `mcp_server/schemas.py`; `worker/run_worker.py`; `analysis/drone_polar.py`; `postprocess/history.py`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** This is the inlet pipeline unchanged, drawn once for both studies. Stage and step names in the drawing are checked against the code at build time.

### D4b. The airfoil2d mesh

- **Message:** The SU2 section runs on a structured C-mesh of {mesh_cells} cells with a first cell of {mesh_first_cell} m, drawn here from the mesh builder at the coarse level.
- **Figure or table:** The coarse mesh around the nominal section: whole domain, near field and a zoom at the leading edge.
- **Equations:** $Re=\dfrac{\rho\,V\,c}{\mu}$; $C_f=0.074\,Re^{-0.2},\quad \dfrac{u_\tau}{V}=\sqrt{\dfrac{C_f}{2}},\quad d_0=\dfrac{y^{+}\,c}{Re\,(u_\tau/V)}$
- **Source:** `geometry/airfoil2d.py`; `runs/mesh/airfoil2d-59cd4287e9/geometry.json`; `runs/mesh/airfoil2d-59cd4287e9/mesh_quality.json`; `runs/mesh/airfoil2d-59cd4287e9/params.json`
- **Speaker notes:** The mesh is rebuilt from the recorded parameters and checked against the recorded cell count before it is drawn. The first cell is set for y+ of 0.5 at the design's Reynolds number.

### D5. Validation V6a to V6d

- **Message:** The solver's own checks pass: {n_pass} toleranced rows pass, {n_pending} is pending a source, {n_fail} fails.
- **Figure or table:** Table of V6a to V6d: row group, rows by verdict, and the worst deviation among the toleranced rows.
- **Equations:** $C_{L\alpha}=\dfrac{2\pi\,AR}{2+\sqrt{AR^{2}+4}}$; $C_{Di}=\dfrac{C_L^{2}}{\pi\,AR\,e}$; $\mathrm{dev}=\dfrac{M}{R}-1\quad\mathrm{or}\quad\mathrm{dev}=M-R$
- **Source:** `runs/drone/validation/2026-11-08/v6.json`
- **Speaker notes:** These rows check the vortex lattice against Helmbold's slope and lifting-line theory, the Warren-12 benchmark, the lattice convergence and the mass and energy closure. The one pending row waits on the source of the benchmark's moment reference point; it is not tuned to agree.

### D5a. What V6a checks

- **Message:** The lattice puts one horseshoe vortex on each panel; V6a checks its span efficiency ({v6a_e_dev} against 1) and lift slope ({v6a_cla_dev} against Helmbold) on an elliptic wing of aspect ratio 8.
- **Figure or table:** The medium lattice on the nominal planform with one horseshoe highlighted, and the spanwise cl at 4 degrees.
- **Equations:** $\vec v_{\mathrm{seg}}=\dfrac{\Gamma}{4\pi}\ \dfrac{\vec r_1\times\vec r_2}{|\vec r_1\times\vec r_2|^{2}}\ \vec r_0\cdot\left(\dfrac{\vec r_1}{|\vec r_1|}-\dfrac{\vec r_2}{|\vec r_2|}\right)$; $\left(\vec V_\infty+\sum_j A_{ij}\,\Gamma_j\right)\cdot\hat n_i=0$; $C_{Di}=\pi\,AR\sum_{n\ \mathrm{odd}}n\,A_n^{2},\quad e=\dfrac{C_L^{2}}{\pi\,AR\,C_{Di}}$
- **Source:** `drone/vlm.py`; `drone/geometry.py`; `runs/drone/validation/2026-11-08/v6.json`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** Bound vortices sit on the quarter chord and control points on the three-quarter chord of each panel. The nominal wing's own span efficiency and lift slope are in the figure beside the V6a values.

### D6. V6f: the low-fidelity section against the E387 tunnel

- **Message:** The closed-form section is {f_clalpha_range} low in lift slope, misses profile drag by {f_cd_range} and overpredicts cl_max by {f_clmax_range}; nothing was tuned.
- **Figure or table:** Table of the twelve V6f rows by Reynolds number.
- **Equations:** $c_{l,\max}=k_{\mathrm{eff}}\,2\pi\,(\alpha_{\mathrm{stall}}-\alpha_{L0})$; $c_{d0}=2\,C_f\,FF,\quad FF=1+k_1\,(t/c)+k_2\,(t/c)^{4}$; $\mathrm{mean}_{\,0.3\leq c_{l,\mathrm{tun}}\leq0.9}\left|\dfrac{c_d}{c_{d,\mathrm{tun}}}-1\right|$
- **Source:** `runs/drone/validation/2026-11-08/v6.json`; `data/validation/e387_uiuc.yaml`
- **Speaker notes:** These are the sizes of the errors the two-level model has to learn. The lift effectiveness the ledger assumes does not contain the value the tunnel implies; that is a ledger ruling and not a number to move here.

### D7. V6e: SU2 against the tunnel, and decision 8

- **Message:** SU2's lift slope misses the tunnel by {v6e_dev} against a {v6e_tol} tolerance: a fail, kept as a fail, and accepted as the high level with the bias recorded.
- **Figure or table:** Figure d (SU2 cl and cd against the UIUC E387 data at the same angles) and the V6e rows.
- **Equations:** $a_{\mathrm{fit}}=\dfrac{\sum(\alpha_i-\bar\alpha)(c_{l,i}-\bar c_l)}{\sum(\alpha_i-\bar\alpha)^{2}},\quad \mathrm{dev}=\dfrac{a_{\mathrm{SU2}}}{a_{\mathrm{tun}}}-1$; $\mathrm{mean}_{\,0.3\leq c_{l,\mathrm{tun}}\leq0.9}\left|\dfrac{c_d}{c_{d,\mathrm{tun}}}-1\right|$
- **Source:** `docs/validation/figures/task10/d_e387_comparison.png`; `runs/drone/validation/2026-11-08/v6.json`; `runs/e387/airfoil2d-498b156761/result.json`; `docs/specs/task10_tasks.md` (V6e and decision 8)
- **Speaker notes:** The tolerance was fixed before any case ran, and the miss is reported as a fail. Decision 8 accepts the medium-mesh polar as the high level and attaches the miss to every record it produces. The figure draws whatever E387 points exist at build time.

### D8. The low-fidelity grid and its exact front

- **Message:** Because the low level is cheap, the exact front over the whole box exists: {front_n} designs out of {grid_n} grid points, {gated_n} of which were gated.
- **Figure or table:** Figure a: the exact front and the 192-point pool's front, endurance against take-off mass.
- **Source:** `docs/validation/figures/task10/a_front_lowfi.png`; `runs/drone_grid/2026-11-08/record.json`; `runs/drone_grid/2026-11-08/front.csv`; `runs/drone_pool_lf/2026-11-08/front.csv`
- **Speaker notes:** The exact front is the reference against which both replays measure regret. The pool's front has {pool_front_n} designs.

### D8a. The box, the gates and the observed front

- **Message:** Endurance changes fastest with aspect ratio and span, which is why the design map uses them; in this projection {n_front_edge} of the {n_front} observed front designs lie within one cell of a gated cell.
- **Figure or table:** The six inputs ranked by the GP length scale of endurance, and the gate-feasible region over aspect ratio and span with the observed front overlaid.
- **Source:** `runs/drone_pareto_lf/2026-11-09/design_map.csv`; `runs/drone_pareto_lf/2026-11-09/notes.json`; `runs/drone_pool_lf/2026-11-08/front.csv`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** The map holds the other four inputs at one base point while the front designs have their own values, so the overlay is a projection. The count says how close the front comes to the cheap gates in this view, and no more.

### D9. The pool replay

- **Message:** On the 192-point low pool, EHVI reaches regret {ehvi_32} at 32 evaluations while random is at {rand_40} after 40.
- **Figure or table:** Figure b and a table of mean regret at five budgets for four strategies.
- **Equations:** $\mu(x)=c+k_{*}^{T}(K+\sigma_n^{2}I)^{-1}(y-c)$; $\sigma^{2}(x)=k_{**}-k_{*}^{T}(K+\sigma_n^{2}I)^{-1}k_{*}$; $\mathrm{regret}=1-\dfrac{HV(\mathrm{observed})}{HV(\mathrm{front})}$; $\mathrm{HVI}(y)=HV(P\cup\{y\})-HV(P)$; $\mathrm{EHVI}(x)\approx\dfrac{1}{S}\sum_{s=1}^{S}\mathrm{HVI}(y_s),\quad y_s\sim\mathcal{N}(\mu,\mathrm{diag}\,\sigma^{2})$
- **Source:** `docs/validation/figures/task10/b_pool_replay.png`; `runs/replay_drone_pool/2026-11-08/replay.csv`
- **Speaker notes:** This is the easy case: a smooth, gate-free pool. The online replay is the test that matters.

### D10. Online replay: plain EHVI loses, weighted EHVI wins

- **Message:** On the unrestricted box plain EHVI ends at regret {ehvi_on_40} against random's {rand_on_40} and wastes {ehvi_gated} of 32 picks on gated designs; weighted by P(feasible) it ends at {feas_on_40}.
- **Figure or table:** Figure c and a table of regret and gated picks at the last budget for six strategies.
- **Equations:** $\mathrm{EHVI}_{\mathrm{feas}}(x)=\mathrm{EHVI}(x)\cdot p(\mathrm{feasible}\mid x)$; $p(x)=\dfrac{1}{1+e^{-(w\cdot z(x)+b)}}$
- **Source:** `docs/validation/figures/task10/c_online_regret.png`; `runs/replay_drone_online/2026-11-08/online.csv`; `runs/replay_drone_online/2026-11-08_feas/online.csv`; `runs/replay_drone_online/2026-11-08/record.json`
- **Speaker notes:** The front lies against the gated edge of the box, and the two GPs know nothing about the gates. Active learning beats space-filling sampling only when the acquisition knows where the design is buildable. Both runs are published.

### D11. The SU2 pool

- **Message:** PENDING: the {pool_cases} SU2 airfoil cases are staged and not yet ingested.
- **Figure or table:** Placeholder box naming the pool batch; the front with its GP band will go here (figure not drawn).
- **Source:** PENDING: pool batch (`designs/pool_af_cases.csv`)
- **Speaker notes:** The case table is committed and the cases are queued. No SU2 pool number appears in this deck until `runs/pool_af/results.csv` exists.

### D12. Multi-fidelity

- **Message:** PENDING: whether the two-level model reaches a given held-out error with fewer SU2 designs than SU2 alone.
- **Figure or table:** Sketch of y_H = rho y_L + d beside the E387 lift-slope values at Re 203,800 that d has to absorb; the error-against-designs figure is not drawn.
- **Equations:** $y_H(x)=\rho\,y_L(x)+d(x),\quad d\sim\mathcal{GP}$; $\mu_H=\rho\,\mu_L+\mu_d,\quad \sigma_H^{2}=\rho^{2}\sigma_L^{2}+\sigma_d^{2}$; $(\rho,c)^{T}=(A^{T}K^{-1}A)^{-1}A^{T}K^{-1}y_H$
- **Source:** PENDING: multi-fidelity analysis (T10.10c); the sketch is drawn from `runs/drone/validation/2026-11-08/v6.json` by `docs/talk/build_deck_drone.py`
- **Speaker notes:** The known bias of the high level is recorded beside every SU2 number, so the correction term absorbs a known offset. Whether that pays is the measurement still to come.

### D13. The inverse query and its confirmation

- **Message:** PENDING: the longest-endurance design under the 4.0 kg cap with P(mass at most cap) of at least 0.9, and one SU2 polar at that design.
- **Figure or table:** Placeholder box.
- **Equations:** $x^{*}=\arg\max_{x}\ \mathrm{E}\left[t(x)\right]\quad\mathrm{subject\ to}\quad P\left(m_{TO}(x)\leq m_{\mathrm{cap}}\right)\geq p_{\min}$; $P\left(m_{TO}\leq m_{\mathrm{cap}}\right)=\Phi\!\left(\dfrac{\ln m_{\mathrm{cap}}-\mu_{\ln m}(x)}{\sigma_{\ln m}(x)}\right)$
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


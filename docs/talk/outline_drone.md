# Deck outline: low-speed aircraft sizing with the inlet pipeline (Task 10)

Slide-by-slide outline for `docs/talk/deck_drone.pptx`, built by `docs/talk/build_deck_drone.py`. First
written 2026-11-08; restructured 2026-11-09 into a complete 40-minute talk (plus 20 minutes of
discussion) with the same sections, timing discipline and backup set as the inlet talk
(`docs/talk/outline.md`), so that either deck can be presented. Every quantitative claim is read from
a record at build time or marked PENDING.

## Conventions

- **Source** is a list of parts separated by semicolons. Each part names one or more existing files
  under `runs/`, `docs/`, `designs/`, `data/`, `drone/` or the code in backticks, or starts with
  `PENDING:` followed by the file that will exist when the run lands and the run that writes it, or
  says `none (no number)`.
- **PENDING files** (written by runs that have not landed on 2026-11-09):
  `runs/drone_mf/2026-11-09/mf.csv` (multi-fidelity analysis, T10.10c),
  `runs/drone_pareto_hf/2026-11-09/pareto.csv` (front on the SU2 pool, T10.10a),
  `runs/drone_inverse_hf/2026-11-09/inverse.json` (inverse query on the SU2 pool, T10.10a),
  `runs/drone_confirm/2026-11-09/confirm.json` (confirmation run, T10.10d),
  `runs/drone_bias_hf/2026-11-09/bias_sweep.csv` (bias sweep at the SU2 answer, T10.10d) and the two
  viz cases under `runs/viz/`. The last four paths are this outline's naming (the scripts take
  `--out`); the run that lands must write there, or this list changes. The builder checks each path
  at build time: when the file exists the slide is filled from it and the footer names the file;
  when it does not, the slide says PENDING and names it. Nothing is estimated in between.
- **Live records.** `runs/pool_af/2026-11-09/results.csv`, `bias.csv` and `record.json` are rewritten
  hourly by the pool ingestion job; the pool slides read them at build time, so a rebuild shows the
  pool as it stands.
- **Placeholders.** A message or speaker note may contain `{name}`. The build script replaces it with a
  value it reads from the record named in that slide's Source line; the build fails on a name it cannot
  fill. So no number in this file is typed: they are all computed from files.
- **Equations.** A slide that states a formula lists its LaTeX source in one line,
  `- **Equations:** $...$; $...$`, under its Figure line. The build renders each with matplotlib mathtext
  (`docs/talk/equations.py`) and places it as a picture whose alt text is the source; the relation is the
  one the repo's code implements, with the module named beside the constant in `build_deck_drone.py`
  and on the equations index (DB13).
- **Slide ids.** D1 to D45 are the timed talk and the discussion slide, DB1 to DB17 the backup slides.
  Section dividers are built from the `##` section headings below and carry no id.
- **Speaker notes** are at most three sentences each.
- **Spelling** is standard US English on every slide, caption, figure label and speaker note.
- **Shared files.** `docs/talk/build_deck.py`, `docs/talk/outline.md` and `docs/talk/deck.pptx` (the inlet
  deck) are the template and are not changed by this deck; the build script imports their helpers.

## Timing

The talk is 40 minutes plus about 20 minutes of discussion, in the inlet talk's section order. The
minutes follow the inlet deck's split where the sections match (title 0.5, motivation 2.5, problem 4);
the inlet's section 5b (Task 9) has no counterpart here, so its five minutes went to physics and
validation (one more than the inlet's nine, for the airfoil RANS family), automation (one more, for the
sharded workers and the per-design aggregator), results (two more, for the live SU2 pool) and
limitations and conclusions (two more, for the conclusions slide), while surrogate and active learning
lost one (no calibration slide yet). The slide times below are the ones to rehearse.

| Section | Minutes | Slides |
|---|---|---|
| Title | 0.5 | D1 |
| 1a. Why a gated, automated process | 2.5 | D2 to D4 |
| 1. Problem and why it matters | 4 | D5 to D8 |
| 2. Physics and validation | 10 | D9 to D24 |
| 3. Automation layer: MCP tools, gates, queue | 4 | D25 to D28 |
| 4. Surrogate and active learning | 8 | D29 to D33 |
| 5. Results and the inverse query | 6 | D34 to D40 |
| 6. Limitations and conclusions | 5 | D41 to D44 |
| Discussion (outside the 40) | about 20 | D45 |

Backup slides DB1 to DB17 follow D45 and are not timed.

---

## Title (0.5 minutes)

### D1. Title (0:00, 0.5 min)

- **Message:** A small electric aircraft sized by the same gated, queued, active-learning pipeline as the supersonic inlet, with the validation verdicts and the pending SU2 results stated as they stand.
- **Figure or table:** Title card only.
- **Source:** none (no number)
- **Speaker notes:** The inlet study built a pipeline; this study asks whether it carries over to a different physics problem. The answer so far is partly in, and every slide says which part.

## Section 1a: Why a gated, automated process (2.5 minutes)

### D2. A clean exit is not a correct result (0:30, 1 min)

- **Message:** The first SU2 airfoil case exited with code {smoke_exit} after its whole {smoke_budget}-iteration budget, with cl {smoke_cl_off} and cd {smoke_cd_off} against its own Cauchy-stopped rerun; only checks after the solver could see it.
- **Figure or table:** Bars of cl and cd of the first run and of its rerun, with the iteration count of each, beside a four-box flow: SU2 exits 0, postprocess, drift rule, decision 6.
- **Source:** `runs/smoke/airfoil2d-96a9dd0f51/result.json`; `runs/smoke/airfoil2d-96a9dd0f51/error.json`; `runs/smoke2/airfoil2d-51d551f2cc/result.json`; `docs/specs/task10_tasks.md` (decision 6)
- **Speaker notes:** SU2 ran its budget, wrote its files and exited cleanly, and the numbers were far from the solution the same case reaches when it is allowed to stop itself. The postprocess step failed first, looking for the compressible residual {rms_col}, and the incompressible solver writes {rms_used}; that failure is what made anybody look. The budget became {smoke2_budget} with a Cauchy stop, and the rerun stopped itself at {smoke2_iters} iterations.

### D3. What caught each problem, and when (1:30, 1 min)

- **Message:** Six problems were stopped by the earliest check that could see them; two of them were found by reading the records rather than by a gate.
- **Figure or table:** Table: the problem, the check that caught it, what would have reached a result without it, and the record.
- **Source:** `runs/smoke/airfoil2d-96a9dd0f51/error.json`; `runs/mesh/airfoil2d-e161fb7e6b.first_attempt/error.json`; `docs/validation/2026-11-08_task10_report.md`; `runs/e387/airfoil2d-498b156761/result.json`; `runs/drone/validation/2026-11-08/v6.json`; `docs/specs/task10_tasks.md` (decision 8)
- **Speaker notes:** The fingerprint refusal is the worker declining to run a mesh it could not reproduce bit for bit, even though the bounding boxes agreed to {fp_bbox_diff} m. The drag claim was a sentence in the task ledger that the deck builder contradicted when it read the E387 records directly. The lift-slope miss was caught by a tolerance fixed before any case ran, and decision 8 kept it a fail.

### D4. Why MCP tools, and what they do not add (2:30, 0.5 min)

- **Message:** The agent reaches the queue only through {n_tools} typed MCP tools with a strict schema and the physics gates; the worker repeats the gates, and every call is logged.
- **Figure or table:** The tool list read from the server, and a two-column table: what the MCP layer adds, and what does not depend on it.
- **Source:** `mcp_server/server.py`; `mcp_server/schemas.py`; `mcp_server/queue.py`; `worker/run_worker.py`
- **Speaker notes:** A script with the same validation would give the same gates and checksums, so MCP is a convenience layer with one entry point, typed arguments and an audit log. The language model never chose a sampling point in this study: the pools are Sobol tables and the acquisitions are code. No transcript of an agent call was recorded for this study, so the claim rests on the code and not on a session.

## Section 1: Problem and why it matters (4 minutes)

### D5. The questions of the study (3:00, 1 min)

- **Message:** Four questions: the front, active learning against sampling, the two-level model, and the inverse query under a mass cap; the status of each answer is read from the records at build time.
- **Figure or table:** Table of the four questions of section 1 of the spec with the status of each answer and the slide that gives it.
- **Source:** `docs/specs/task10_drone_sizing.md` (section 1); `docs/specs/task10_tasks.md`
- **Speaker notes:** Questions 1 and 2 have answers on the low-fidelity model, and the SU2 pool is what tests them at the high level. A null result on any of them is reported as such. The same loop applies to any validated simulator with a few inputs and two competing outputs.

### D6. Endurance against take-off mass, under the C2 cap (4:00, 1 min)

- **Message:** The trade is endurance against take-off mass at a fixed {payload_kg} kg payload, and the EASA open-category class C2 caps take-off mass at {cap_kg} kg; on the low model none of the {n_lowpool} pool designs comes near the cap (the heaviest is {lowpool_max} kg).
- **Figure or table:** Endurance against take-off mass for the 192 low-pool designs and the exact low-fidelity front, with the cap drawn.
- **Source:** `runs/drone_pool_lf/2026-11-08/grid.csv`; `runs/drone_grid/2026-11-08/front.csv`; `runs/drone_inverse_lf/2026-11-09/inverse.json`; `data/drone/rules.yaml`
- **Speaker notes:** A longer wing and a bigger battery buy endurance and cost mass, so the answer is a front and not a point. The cap is a regulatory line fixed in the spec before any run. That it never binds on the low model is itself a finding: question 4 is only tested at the high level.

### D7. Six inputs, and what is fixed (5:00, 1 min)

- **Message:** Six inputs span the box; {n_ledger} fixed quantities come from the ledger, {n_assumed} of them assumed with a band, and the cruise speed is set by a rule rather than chosen.
- **Figure or table:** Table of the six inputs with their ranges and the nominal design; the ledger counts by set and grade; the cruise-speed rule.
- **Equations:** $V_{\mathrm{cr}}=\max\left(V_{\mathrm{minP}},\ k_s\,V_{\mathrm{stall}}\right),\quad V_{\mathrm{stall}}=\sqrt{\dfrac{2W}{\rho\,S\,C_{L,\max}}}$
- **Source:** `mcp_server/schemas.py` (DRONE_BOUNDS); `runs/drone/validation/2026-11-08/v6.json`; `data/drone/air.yaml`; `data/drone/battery.yaml`; `data/drone/propulsion.yaml`; `data/drone/structure.yaml`; `data/drone/rules.yaml`; `drone/mission.py`
- **Speaker notes:** Cruise speed is not an input because an optimizer would always drive it to the same place. The fixed quantities' bands are not surrogate inputs; their effect is measured once by the one-at-a-time sweep on the results section. Sea-level ISA air is the only flight condition.

### D8. Two fidelity levels, and what each costs (6:00, 1 min)

- **Message:** A low-fidelity design costs {lf_s_core} s of one core; one SU2 angle costs a median {hf_coarse_min} min on the coarse mesh and {hf_medium_min} min on the medium mesh, and a design needs five angles.
- **Figure or table:** Table of the two levels: what differs, cost per design from the recorded runs, and what each level is used for.
- **Source:** `runs/drone_grid/2026-11-08/record.json`; `runs/drone_pool_lf/2026-11-08/record.json`; `runs/pool_af/airfoil2d-2862718ac9/result.json`; `runs/e387/airfoil2d-498b156761/result.json`; `designs/pool_af_cases.csv`
- **Speaker notes:** The costs are medians over every SU2 record in the repository at build time, by mesh level. The ratio between the levels is what makes the exact low-fidelity front possible and the high-fidelity pool small. The two levels differ only in where the section data come from.

## Section 2: Physics and validation (10 minutes)

### D9. The model in one picture (7:00, 0.75 min)

- **Message:** Six inputs go through a vortex lattice, a drag build-up, a mass closure and a mission to endurance and take-off mass, at two fidelity levels that differ only in the section data.
- **Figure or table:** Pipeline drawn with boxes and arrows: six inputs with their ranges, geometry, vortex lattice, drag build-up, mass closure with its loop, mission, outputs; above the drag block the two section-data levels, the only block that differs.
- **Equations:** $m_{k{+}1}=\sum_i m_i(m_k),\quad |m_{k{+}1}-m_k|/m_k<10^{-9}$; $V=\sqrt{\dfrac{2W}{\rho\,S\,C_L}},\quad P=\dfrac{D\,V}{\eta_p}$
- **Source:** `docs/specs/task10_drone_sizing.md` (sections 2, 3 and 6); `drone/evaluate.py`; `mcp_server/schemas.py` (DRONE_BOUNDS); `docs/talk/build_deck_drone.py`
- **Speaker notes:** The lattice, the drag build-up and the closure are the same at both levels. The low level takes the section from closed forms; the high level takes it from an SU2 airfoil polar at the design's own Reynolds number.

### D10. The nominal design in one top view (7:45, 0.5 min)

- **Message:** The nominal design has a {nom_span} m span, aspect ratio {nom_ar} and taper {nom_taper}: {nom_area} m^2 of wing and a closed take-off mass of {nom_mtow} kg; tail and fuselage follow from the wing by rule.
- **Figure or table:** Top view drawn by `drone.geometry.build`, with the six inputs labeled and the NACA section inset.
- **Source:** `drone/geometry.py`; `drone/naca.py`; `drone/evaluate.py`; `runs/drone/validation/2026-11-08/v6.json`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** Span and aspect ratio fix the wing area, taper fixes the chords, and the tail is sized by volume coefficients with a fixed arm. The fuselage is a body of revolution holding the payload and the battery; its position along the wing is schematic.

### D11. What V6a checks: the vortex lattice (8:15, 0.75 min)

- **Message:** The lattice puts one horseshoe vortex on each panel; V6a checks its span efficiency ({v6a_e_dev} against 1) and lift slope ({v6a_cla_dev} against Helmbold) on an elliptic wing of aspect ratio 8.
- **Figure or table:** The medium lattice on the nominal planform with one horseshoe highlighted, and the spanwise cl at 4 degrees.
- **Equations:** $\vec v_{\mathrm{seg}}=\dfrac{\Gamma}{4\pi}\ \dfrac{\vec r_1\times\vec r_2}{|\vec r_1\times\vec r_2|^{2}}\ \vec r_0\cdot\left(\dfrac{\vec r_1}{|\vec r_1|}-\dfrac{\vec r_2}{|\vec r_2|}\right)$; $\left(\vec V_\infty+\sum_j A_{ij}\,\Gamma_j\right)\cdot\hat n_i=0$; $C_{Di}=\pi\,AR\sum_{n\ \mathrm{odd}}n\,A_n^{2},\quad e=\dfrac{C_L^{2}}{\pi\,AR\,C_{Di}}$
- **Source:** `drone/vlm.py`; `drone/geometry.py`; `runs/drone/validation/2026-11-08/v6.json`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** Bound vortices sit on the quarter chord and control points on the three-quarter chord of each panel. The nominal wing's own span efficiency and lift slope are in the figure beside the V6a values.

### D12. Validation V6a to V6d (9:00, 0.75 min)

- **Message:** The solver's own checks pass: {n_pass} toleranced rows pass, {n_pending} is pending a source, {n_fail} fails.
- **Figure or table:** Table of V6a to V6d: row, deviation, tolerance and verdict for every toleranced row.
- **Equations:** $C_{L\alpha}=\dfrac{2\pi\,AR}{2+\sqrt{AR^{2}+4}}$; $C_{Di}=\dfrac{C_L^{2}}{\pi\,AR\,e}$; $\mathrm{dev}=\dfrac{M}{R}-1\quad\mathrm{or}\quad\mathrm{dev}=M-R$
- **Source:** `runs/drone/validation/2026-11-08/v6.json`
- **Speaker notes:** These rows check the vortex lattice against Helmbold's slope and lifting-line theory, the Warren-12 benchmark, the lattice convergence and the mass and energy closure. The one pending row waits on the source of the benchmark's moment reference point; it is not tuned to agree.

### D13. Mass closure and the endurance balance (9:45, 0.5 min)

- **Message:** Take-off mass is a fixed point and endurance is an energy balance: at the nominal design the closure takes {nom_iters} iterations and the balance gives {nom_endurance} h.
- **Figure or table:** The closure loop, the nominal mass breakdown and the energy chain with its nominal values.
- **Equations:** $m_{k{+}1}=m_{\mathrm{pay}}+f_b\,m_k+m_{\mathrm{skin}}+m_{\mathrm{spar}}+m_{\mathrm{tail}}+m_{\mathrm{fus}}+P_{\mathrm{inst}}/\sigma_P$; $P_{\mathrm{cr}}=\dfrac{D\,V}{\eta_p}$; $P_{\mathrm{inst}}=\max\!\left(k_P\,P_{\mathrm{cr}},\ \dfrac{W\,\dot h}{\eta_p}+P_{\mathrm{cr}}\right)$; $t=\dfrac{\mathrm{DoD}\,E_{\mathrm{spec}}\,3600\,m_b-P_{\mathrm{inst}}\,t_{\mathrm{climb}}}{3600\,P_{\mathrm{cr}}}$
- **Source:** `drone/evaluate.py`; `drone/mission.py`; `runs/drone/validation/2026-11-08/v6.json`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** Battery mass is the battery fraction times take-off mass, so the loop has to be iterated. V6d checks that the loop and the energy balance close to 1e-9.

### D14. The airfoil RANS family: the mesh (10:15, 0.5 min)

- **Message:** The SU2 section runs incompressible RANS with Spalart-Allmaras and its BCM transition option on a structured C-mesh of {mesh_cells} cells with a first cell of {mesh_first_cell} m, drawn here from the mesh builder at the coarse level.
- **Figure or table:** The coarse mesh around the nominal section: whole domain, near field and a zoom at the leading edge.
- **Equations:** $Re=\dfrac{\rho\,V\,c}{\mu}$; $C_f=0.074\,Re^{-0.2},\quad \dfrac{u_\tau}{V}=\sqrt{\dfrac{C_f}{2}},\quad d_0=\dfrac{y^{+}\,c}{Re\,(u_\tau/V)}$
- **Source:** `geometry/airfoil2d.py`; `runs/mesh/airfoil2d-59cd4287e9/geometry.json`; `runs/mesh/airfoil2d-59cd4287e9/mesh_quality.json`; `runs/mesh/airfoil2d-59cd4287e9/params.json`; `cases/templates/inc_rans_airfoil.cfg`
- **Speaker notes:** The mesh is rebuilt from the recorded parameters and checked against the recorded cell count before it is drawn. The first cell is set for y+ of 0.5 at the design's Reynolds number.

### D15. Two stopping rules: SU2's Cauchy stop and the drift rule (10:45, 0.75 min)

- **Message:** The airfoil2d family stops on a Cauchy criterion because the first smoke case ran its whole {smoke_budget}-iteration budget unconverged; the rerun stopped itself at {smoke2_iters}, and the drift rule still reports both runs as moving.
- **Figure or table:** Table: the two smoke runs (budget, iterations, lift and drag drift, status) and the Cauchy settings read from the case template.
- **Equations:** $\mathrm{drift}=\dfrac{\max_{k\in W}f_k-\min_{k\in W}f_k}{|f_n|}\times100\,\%$; $W=\{\,n-\lceil 0.2\,n\rceil+1,\ \ldots,\ n\,\}$; $\dfrac{1}{N}\sum_{k=n-N+1}^{n}\dfrac{|f_k-f_{k-1}|}{|f_k|}<\varepsilon,\quad f\in\{C_L,C_D\}$
- **Source:** `runs/smoke/airfoil2d-96a9dd0f51/result.json`; `runs/smoke2/airfoil2d-51d551f2cc/result.json`; `cases/templates/inc_rans_airfoil.cfg`; `docs/specs/task10_tasks.md` (decision 6)
- **Speaker notes:** The two rules measure different things: SU2's averages the per-iteration change over the last 200 iterations, the drift rule takes the range over the last fifth of the run. Both are kept on every record and no rule was loosened. Everything else in the queue, the worker and the gates is the inlet machinery unchanged.

### D16. What the solver history looks like (11:30, 0.5 min)

- **Message:** The medium-mesh nominal case ran {conv_iters} of {conv_budget} iterations and dropped rms[P] by {conv_drop} orders, yet over the last 20 % of its history CL still drifts {conv_cl_drift} and CD {conv_cd_drift}.
- **Figure or table:** rms[P], CL and CD against iteration with the last-20 % window and the end of the run marked.
- **Source:** `docs/validation/figures/task10/flow/convergence_smoke2.png`; `docs/validation/figures/task10/flow/captions.md`; `runs/smoke2/airfoil2d-51d551f2cc/history.csv.gz`; `runs/smoke2/airfoil2d-51d551f2cc/result.json`
- **Speaker notes:** The residual alone looks converged while the force coefficients are still moving, which is why the drift rule exists. This is the only history file downloaded so far; the others are not drawn.

### D17. What the mesh does to the pressure distribution (12:00, 0.5 min)

- **Message:** On the nominal section the peak suction is Cp {mesh_coarse_peak} on the coarse mesh ({mesh_coarse_cells} cells), {mesh_medium_peak} on the medium ({mesh_medium_cells}) and {mesh_fine_peak} on the fine ({mesh_fine_cells}); cl is {mesh_coarse_cl}, {mesh_medium_cl} and {mesh_fine_cl}.
- **Figure or table:** Cp of the three meshes on one axis with a leading-edge zoom.
- **Source:** `docs/validation/figures/task10/flow/cp_mesh_pair.png`; `docs/validation/figures/task10/flow/captions.md`; `runs/mesh/airfoil2d-59cd4287e9/surface_flow.dat.gz`; `runs/smoke2/airfoil2d-51d551f2cc/surface_flow.dat.gz`; `runs/mesh/airfoil2d-e161fb7e6b/surface_flow.dat.gz`
- **Speaker notes:** This is the picture behind the mesh table in backup DB4: the curves agree away from the leading edge and differ in the peak. Every run of the three was flagged not converged, so the differences mix mesh and convergence effects.

### D18. V6f: the low-fidelity section against the E387 tunnel (12:30, 0.75 min)

- **Message:** The closed-form section is {f_clalpha_range} low in lift slope, misses profile drag by {f_cd_range} and overpredicts cl_max by {f_clmax_range}; nothing was tuned.
- **Figure or table:** Table of the twelve V6f rows by Reynolds number.
- **Equations:** $c_{l,\max}=k_{\mathrm{eff}}\,2\pi\,(\alpha_{\mathrm{stall}}-\alpha_{L0})$; $c_{d0}=2\,C_f\,FF,\quad FF=1+k_1\,(t/c)+k_2\,(t/c)^{4}$; $\mathrm{mean}_{\,0.3\leq c_{l,\mathrm{tun}}\leq0.9}\left|\dfrac{c_d}{c_{d,\mathrm{tun}}}-1\right|$
- **Source:** `runs/drone/validation/2026-11-08/v6.json`; `data/validation/e387_uiuc.yaml`
- **Speaker notes:** These are the sizes of the errors the two-level model has to learn. The lift effectiveness the ledger assumes does not contain the value the tunnel implies; that is a ledger ruling and not a number to move here.

### D19. V6e: SU2 against the tunnel, and decision 8 (13:15, 1 min)

- **Message:** SU2's lift slope misses the tunnel by {v6e_dev} against a {v6e_tol} tolerance: a fail, kept as a fail, and accepted as the high level with the bias recorded.
- **Figure or table:** Figure d (SU2 cl and cd against the UIUC E387 data at the same angles) and the V6e rows.
- **Equations:** $a_{\mathrm{fit}}=\dfrac{\sum(\alpha_i-\bar\alpha)(c_{l,i}-\bar c_l)}{\sum(\alpha_i-\bar\alpha)^{2}},\quad \mathrm{dev}=\dfrac{a_{\mathrm{SU2}}}{a_{\mathrm{tun}}}-1$; $\mathrm{mean}_{\,0.3\leq c_{l,\mathrm{tun}}\leq0.9}\left|\dfrac{c_d}{c_{d,\mathrm{tun}}}-1\right|$
- **Source:** `docs/validation/figures/task10/d_e387_comparison.png`; `runs/drone/validation/2026-11-08/v6.json`; `runs/e387/airfoil2d-498b156761/result.json`; `docs/specs/task10_tasks.md` (V6e and decision 8)
- **Speaker notes:** The tolerance was fixed before any case ran, and the miss is reported as a fail. Decision 8 accepts the medium-mesh polar as the high level and attaches the miss to every record it produces. The figure draws whatever E387 points exist at build time.

### D20. The E387 pressure distributions (14:15, 0.5 min)

- **Message:** On E387 at Re {e387_re} the suction peak on the upper surface deepens from Cp {e387_peak_lo} at {e387_a_lo} deg to {e387_peak_hi} at {e387_a_hi} deg, and a kink in the upper-surface Cp moves forward as the angle rises.
- **Figure or table:** Five Cp panels against x/c, one per angle, upper surface solid and lower surface dashed, with cl, cd and the convergence status of each case.
- **Source:** `docs/validation/figures/task10/flow/cp_e387.png`; `docs/validation/figures/task10/flow/captions.md`; `runs/e387/airfoil2d-498b156761/surface_flow.dat.gz`; `postprocess/plot_airfoil.py`
- **Speaker notes:** Every curve is the Pressure_Coefficient column SU2 wrote at the surface nodes, read from the committed files. All five cases are flagged not converged by the drift rule, which each panel title states.

### D21. Where the wall shear reverses (14:45, 0.5 min)

- **Message:** On the E387 upper surface the skin friction changes sign, which marks reversed flow at the wall: from x/c {e387_rev_lo} at {e387_a_lo} deg and from {e387_rev_hi} at {e387_a_hi} deg.
- **Figure or table:** Skin friction Cf_x against x/c on the upper and lower surface, one curve per angle.
- **Source:** `docs/validation/figures/task10/flow/cf_e387.png`; `docs/validation/figures/task10/flow/captions.md`; `runs/e387/airfoil2d-498b156761/surface_flow.dat.gz`; `postprocess/plot_airfoil.py`
- **Speaker notes:** Cf_x is the x component of SU2's Skin_Friction_Coefficient, so a negative value means the wall shear points upstream. The negative stretch sits where the Cp panels show their kink, and it moves forward with angle.

### D22. Section polars: SU2, the closed form and the tunnel (15:15, 0.75 min)

- **Message:** On E387 SU2's cl is {su2_cl_range} and cd is {su2_cd_range} against the tunnel; on the {n_designs} complete pool designs the {n_stall} cases at 14 degrees (cl {stall_cl}, cd {stall_cd}) are the stall the closed form cannot show.
- **Figure or table:** cl against alpha and cd against cl for E387 and each complete pool design: SU2 points, the closed-form section and, for E387, the UIUC tunnel.
- **Source:** `docs/validation/figures/task10/flow/section_polars.png`; `docs/validation/figures/task10/flow/captions.md`; `runs/pool_af/2026-11-09/results.csv`; `data/validation/e387_uiuc.yaml`; `drone/section.py`
- **Speaker notes:** The closed form is a straight line to a cap and a constant drag, so it has no stall and no drag rise. Open circles are cases the pool did not keep for the polar. The figure is redrawn from the pool records at every build.

### D23. The stall at 14 degrees (16:00, 0.5 min)

- **Message:** On pool design 0 the section stalls between 10 and 14 degrees: cl falls from {d0_cl10} to {d0_cl14}, cd rises from {d0_cd10} to {d0_cd14}, and the suction peak collapses from Cp {d0_peak10} to {d0_peak14}.
- **Figure or table:** Five Cp panels for design 0 on the coarse mesh at -2, 2, 6, 10 and 14 degrees.
- **Source:** `docs/validation/figures/task10/flow/cp_design0.png`; `docs/validation/figures/task10/flow/captions.md`; `runs/pool_af/airfoil2d-2862718ac9/surface_flow.dat.gz`; `postprocess/plot_airfoil.py`
- **Speaker notes:** The flat upper-surface Cp at 14 degrees is the signature of separated flow over most of the chord. Cases a pool design leaves out of its polar are drawn as open circles on the polar slide.

### D24. Pressure contours and streamlines (16:30, 0.5 min)

- **Message:** {viz_answer}
- **Figure or table:** Cp contours and speed with streamlines for design 0 at 14 degrees (whole section and leading edge); the 6 degree case is named with the reason it is not shown.
- **Source:** `runs/viz/airfoil2d-0ae85f2779/flow.dat.gz` (14 degrees, volume output of design 0, coarse mesh); `runs/viz/airfoil2d-731806baea/result.json` (6 degrees, result only: its volume file is unreadable)
- **Speaker notes:** At 14 degrees the upper surface is separated, with reversed flow at the wall from x/c 0.013, the first upper-surface point behind the leading edge, to 0.96 on pool design 0's 14 degree surface record: this is the stall the 14 degree pool cases record and the closed form cannot show. The 6 degree volume file came back unreadable twice, the second time written on local disk, so the cause is in the writer and is not yet established; I show only the file that reads cleanly.

## Section 3: Automation layer: MCP tools, gates, queue (4 minutes)

### D25. The tools and the gates (17:00, 1 min)

- **Message:** The MCP server exposes {n_tools} tools and never runs SU2; a drone design passes {n_gates} gates of the spec before any solver, and an airfoil case passes the mesh-quality gate.
- **Figure or table:** Left: the tools with the first line of each docstring. Right: the drone gates as the code names them.
- **Source:** `mcp_server/server.py`; `drone/evaluate.py`; `physics/gates.py`; `worker/make_case.py`
- **Speaker notes:** Each gate fails with the offending value in its message, in the inlet's form. The same gate function runs when a case is created and again on the worker before SU2 starts.

### D26. Where each gate sits: the Drive queue and the Colab worker (18:00, 1 min)

- **Message:** Every request passes the same ordered checks before SU2 starts, and every result passes more before it becomes a record; the numbered marks show where.
- **Figure or table:** Diagram from the request through the MCP tools, the Drive queue folder and the Colab worker to the ingested record, with the gates numbered.
- **Source:** `mcp_server/queue.py`; `mcp_server/schemas.py`; `worker/run_worker.py`; `analysis/drone_polar.py`; `postprocess/history.py`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** Colab cannot take inbound connections, so jobs go through a Drive folder and come back as files with a digest. The worker rebuilds the mesh and config from the uploaded parameters and refuses a mismatch. Stage and step names in the drawing are checked against the code at build time.

### D27. Two workers on one queue, and ingestion with sha256 (19:00, 1 min)

- **Message:** With --shard K/N each worker takes the cases whose id hash is K modulo N, so two Colab sessions split the {pool_cases} pool cases {shard_split} with no claim race; every result is ingested against its sha256, and the pool table's own hash checks: {results_sha_ok}.
- **Figure or table:** Left: the shard rule and the split of the case table computed from it. Right: the ingestion chain, the per-design aggregator and the counts of the results table.
- **Source:** `worker/run_worker.py`; `designs/pool_af_cases.csv`; `mcp_server/queue.py`; `analysis/pool_af_results.py`; `runs/pool_af/2026-11-09/record.json`; `runs/pool_af/2026-11-09/results.csv`
- **Speaker notes:** Before the shard flag two workers on one queue would both have started the same job, so only one ran. The worker ids in the pool records so far: {n_pool_workers}. The aggregator keeps Cauchy-stopped cases with their drift as flags and forms a design only when at least three angles are kept.

### D28. What the gated process caught (20:00, 1 min)

- **Message:** Each of these was found by a check or a recorded run before it could reach a result.
- **Figure or table:** Table of six items from the task record: what was caught, by what, and the fix.
- **Source:** `docs/specs/task10_tasks.md`; `runs/smoke/airfoil2d-96a9dd0f51/error.json`; `drone/vlm.py`
- **Speaker notes:** The list holds only items recorded in the task file. Fix and cause are in the record each row names.

## Section 4: Surrogate and active learning (8 minutes)

### D29. One Gaussian process per objective, and who chooses (21:00, 1.5 min)

- **Message:** An exact GP on endurance and one on log take-off mass give a mean and an interval at every candidate; EHVI or max-variance picks the next design, random and LHS are the baselines, and the language model chooses nothing.
- **Figure or table:** The five strategies compared on the next slides, one line each, beside the GP and acquisition relations.
- **Equations:** $k(r)=\sigma_f^{2}\left(1+\sqrt{5}\,r+\dfrac{5}{3}r^{2}\right)e^{-\sqrt{5}\,r},\quad r=\sqrt{\sum_d\dfrac{(x_d-x_d')^{2}}{\ell_d^{2}}}$; $\mu(x)=c+k_{*}^{T}(K+\sigma_n^{2}I)^{-1}(y-c)$; $\sigma^{2}(x)=k_{**}-k_{*}^{T}(K+\sigma_n^{2}I)^{-1}k_{*}$; $f(x)=\left(-t(x),\ \ln m_{TO}(x)\right)$; $\mathrm{HVI}(y)=HV(P\cup\{y\})-HV(P)$; $\mathrm{EHVI}(x)\approx\dfrac{1}{S}\sum_{s=1}^{S}\mathrm{HVI}(y_s),\quad y_s\sim\mathcal{N}(\mu,\mathrm{diag}\,\sigma^{2})$; $\mathrm{score}(x)=\tilde\sigma_1^{2}(x)+\tilde\sigma_2^{2}(x)$
- **Source:** `surrogate/gp.py`; `surrogate/acquisition.py`; `surrogate/replay.py`; `analysis/replay_drone_online.py`; `surrogate/feasibility.py`
- **Speaker notes:** This is the inlet's GP and acquisition code with the drone bounds, a Matern 5/2 kernel with one length per input fitted by marginal likelihood. Every strategy is deterministic given a seed, so each run reproduces from its record. Max-variance is in the comparison so that the audience can see what the hypervolume term adds.

### D30. What the GP learned about the box (22:30, 1 min)

- **Message:** Endurance changes fastest with aspect ratio and span, which is why the design map uses them; in this projection {n_front_edge} of the {n_front} observed front designs lie within one cell of a gated cell.
- **Figure or table:** The six inputs ranked by the GP length scale of endurance, and the gate-feasible region over aspect ratio and span with the observed front overlaid.
- **Source:** `runs/drone_pareto_lf/2026-11-09/design_map.csv`; `runs/drone_pareto_lf/2026-11-09/notes.json`; `runs/drone_pool_lf/2026-11-08/front.csv`; `docs/talk/build_deck_drone.py`
- **Speaker notes:** The map holds the other four inputs at one base point while the front designs have their own values, so the overlay is a projection. The count says how close the front comes to the cheap gates in this view, and no more.

### D31. The pool replay (23:30, 1.5 min)

- **Message:** On the 192-point low pool, EHVI reaches regret {ehvi_32} at 32 evaluations while random is at {rand_40} after 40.
- **Figure or table:** Figure b and a table of mean regret at five budgets for four strategies.
- **Equations:** $\mathrm{regret}=1-\dfrac{HV(\mathrm{observed})}{HV(\mathrm{front})}$
- **Source:** `docs/validation/figures/task10/b_pool_replay.png`; `runs/replay_drone_pool/2026-11-08/replay.csv`
- **Speaker notes:** Every strategy draws from the same pool, so the ground truth is shared and no extra run is needed. This is the easy case: a smooth, gate-free pool. The online replay is the test that matters.

### D32. Online replay: plain EHVI loses, weighted EHVI wins (25:00, 2 min)

- **Message:** On the unrestricted box plain EHVI ends at regret {ehvi_on_40} against random's {rand_on_40} and wastes {ehvi_gated} of 32 picks on gated designs; weighted by P(feasible) it ends at {feas_on_40}.
- **Figure or table:** Figure c and a table of regret and gated picks at the last budget for six strategies.
- **Equations:** $\mathrm{EHVI}_{\mathrm{feas}}(x)=\mathrm{EHVI}(x)\cdot p(\mathrm{feasible}\mid x)$; $p(x)=\dfrac{1}{1+e^{-(w\cdot z(x)+b)}}$
- **Source:** `docs/validation/figures/task10/c_online_regret.png`; `runs/replay_drone_online/2026-11-08/online.csv`; `runs/replay_drone_online/2026-11-08_feas/online.csv`; `runs/replay_drone_online/2026-11-08/record.json`
- **Speaker notes:** The front lies against the gated edge of the box, and the two GPs know nothing about the gates. Active learning beats space-filling sampling only when the acquisition knows where the design is buildable. Both runs are published, and the full tables are in backup DB9.

### D33. The two-level model (27:00, 2 min)

- **Message:** Does the two-level model reach a given held-out error with fewer SU2 designs than SU2 alone? {mf_answer}
- **Figure or table:** Sketch of y_H = rho y_L + d beside the E387 lift-slope values at Re 203,800 that d has to absorb; when the analysis exists, a table of held-out error against the number of SU2 designs for both models.
- **Equations:** $y_H(x)=\rho\,y_L(x)+d(x),\quad d\sim\mathcal{GP}$; $\mu_H=\rho\,\mu_L+\mu_d,\quad \sigma_H^{2}=\rho^{2}\sigma_L^{2}+\sigma_d^{2}$; $(\rho,c)^{T}=(A^{T}K^{-1}A)^{-1}A^{T}K^{-1}y_H$
- **Source:** `runs/drone/validation/2026-11-08/v6.json`; `docs/talk/build_deck_drone.py`; `surrogate/mf_gp.py`; PENDING: `runs/drone_mf/2026-11-09/mf.csv` (multi-fidelity analysis, T10.10c)
- **Speaker notes:** The known bias of the high level is recorded beside every SU2 number, so the correction term absorbs a known offset. The inlet's Task 9 found that a cheap level helps most at small budgets, and this is the same measurement on a new problem. Whether that pays here is the measurement this slide is waiting for, if it says PENDING.

## Section 5: Results and the inverse query (6 minutes)

### D34. The low-fidelity grid and its exact front (29:00, 1 min)

- **Message:** Because the low level is cheap, the exact front over the whole box exists: {front_n} designs out of {grid_n} grid points, {gated_n} of which were gated.
- **Figure or table:** Figure a: the exact front and the 192-point pool's front, endurance against take-off mass.
- **Source:** `docs/validation/figures/task10/a_front_lowfi.png`; `runs/drone_grid/2026-11-08/record.json`; `runs/drone_grid/2026-11-08/front.csv`; `runs/drone_pool_lf/2026-11-08/front.csv`
- **Speaker notes:** The exact front is the reference against which both replays measure regret. The pool's front has {pool_front_n} designs. It is a low-fidelity front and carries every low-fidelity bias on the limitations slide.

### D35. The SU2 pool as it stands (30:00, 1.5 min)

- **Message:** Of the {pool_designs} SU2 pool designs, {pool_complete} are complete and {pool_incomplete} incomplete ({pool_landed} of {pool_cases} cases landed); on the complete ones the high-level endurance is {hf_lf_end_range} against the low level's.
- **Figure or table:** Table, one row per complete design: angles kept, endurance and take-off mass at both levels and their ratio; the status counts of the results table.
- **Source:** `runs/pool_af/2026-11-09/results.csv`; `runs/pool_af/2026-11-09/record.json`; `runs/drone_pool_lf/2026-11-08/grid.csv`; `designs/pool_af_cases.csv`
- **Speaker notes:** The table is read from the hourly-ingested results at build time, so it grows as the pool lands. Every high-level number carries the decision-8 flags, and a design with fewer than three kept angles is not evaluated. The difference between the levels is the discrepancy the two-level model has to learn, design by design.

### D36. The high-fidelity front with its band (31:30, 1 min)

- **Message:** {hf_front_answer}
- **Figure or table:** The SU2-pool front, the predicted front and the GP band, endurance against take-off mass, when the analysis exists; until then a box naming the file.
- **Source:** PENDING: `runs/drone_pareto_hf/2026-11-09/pareto.csv` (front on the SU2 pool, T10.10a)
- **Speaker notes:** The band is the posterior uncertainty of the two GPs, sampled jointly, and it is shown beside the observed designs rather than instead of them. Every point of this front carries the V6e bias of decision 8. The low-fidelity front on the previous slides is drawn beside it once both exist.

### D37. The inverse query under the 4 kg cap (32:30, 1 min)

- **Message:** On the low model the answer is a box corner with {inv_n_bound} of six inputs at a bound, {inv_end} h at {inv_mtow} kg with P(mass at most cap) = {inv_p}, so the cap never binds there; {hf_inverse_answer}
- **Figure or table:** Table: the query, the low-fidelity answer with its intervals and its direct evaluation on the low model, and the high-fidelity answer when it exists.
- **Equations:** $x^{*}=\arg\max_{x}\ \mathrm{E}\left[t(x)\right]\quad\mathrm{subject\ to}\quad P\left(m_{TO}(x)\leq m_{\mathrm{cap}}\right)\geq p_{\min}$; $P\left(m_{TO}\leq m_{\mathrm{cap}}\right)=\Phi\!\left(\dfrac{\ln m_{\mathrm{cap}}-\mu_{\ln m}(x)}{\sigma_{\ln m}(x)}\right)$
- **Source:** `runs/drone_inverse_lf/2026-11-09/inverse.json`; `drone/evaluate.py`; PENDING: `runs/drone_inverse_hf/2026-11-09/inverse.json` (inverse query on the SU2 pool, T10.10a)
- **Speaker notes:** The cap and the probability were fixed in the spec before any run. The low-fidelity answer is a diagnostic: the GP extrapolates to a corner the Sobol pool never sampled, and the direct evaluation lands inside its intervals. The query is a computation on the fitted surrogate, never a choice by the language model.

### D38. The confirmation run (33:30, 0.5 min)

- **Message:** {confirm_answer}
- **Figure or table:** Table: predicted endurance and take-off mass with their 90 % intervals against the SU2-level evaluation of the answer, and the C2 verdict, when the run exists.
- **Source:** PENDING: `runs/drone_confirm/2026-11-09/confirm.json` (confirmation run, T10.10d)
- **Speaker notes:** The check passes if both simulated objectives fall inside their predicted 90 % intervals. A miss is documented and explained, as in the inlet study.

### D39. Which fixed quantities move the answer (34:00, 0.5 min)

- **Message:** At the low-fidelity answer the largest of the {bias_n} banded quantities are {bias_top}; {bias_hf_answer}
- **Figure or table:** Bars of the endurance change at the band's two ends for the eight largest quantities, ranked; the full table is backup DB8.
- **Source:** `runs/drone_bias_lf/2026-11-09/bias_sweep.csv`; PENDING: `runs/drone_bias_hf/2026-11-09/bias_sweep.csv` (bias sweep at the SU2 answer, T10.10d)
- **Speaker notes:** Each quantity is moved alone to its band ends with everything else at the ledger value. The ranking is for one design and is not a global sensitivity.

### D40. Coarse against medium on the pool (34:30, 0.5 min)

- **Message:** On the {bias_pairs} pool cases with both meshes, medium over coarse is {mc_cl_range} in cl and {mc_cd_range} in cd: the coarse mesh the pool runs on is checked case by case.
- **Figure or table:** Table of the recorded bias check: design, angle, cl and cd at both levels and their ratios.
- **Source:** `runs/pool_af/2026-11-09/bias.csv`; `designs/pool_af_cases.csv`
- **Speaker notes:** Decision 7 put the pool on the coarse mesh for cost and kept the first four designs at three angles on the medium mesh as this check. A pair where either case ran out of budget is not in the table, because the aggregator does not keep it.

## Section 6: Limitations and conclusions (5 minutes)

### D41. Biases that travel with every number (35:00, 1.5 min)

- **Message:** The model's named biases stay beside every figure; the high level carries the V6e miss (at Re {e387_re} SU2's cl is {su2_cl_range} and its cd {su2_cd_range}) and a drift band of {pool_cl_drift} in cl and {pool_cd_drift} in cd over the kept pool cases.
- **Figure or table:** Two lists: section 13 of the spec with the drift band and the open ledger finding, and the decision-8 flags read from the validation record.
- **Source:** `docs/specs/task10_drone_sizing.md` (section 13); `runs/drone/validation/2026-11-08/v6.json`; `runs/e387/airfoil2d-498b156761/result.json`; `analysis/high_level_bias.py`; `runs/pool_af/2026-11-09/results.csv`
- **Speaker notes:** The flags are generated from the validation record, so they cannot drift from it. A reader of any single design record sees the miss without opening this deck. The drift band is the size of the movement the stopping rule tolerates, which is the floor of what the pool can resolve.

### D42. What the record keeps that was wrong first (36:30, 1 min)

- **Message:** Each of these was wrong at its first recording and is kept on the record beside its correction: the corrections were made on evidence, and none moved a tolerance after a verdict.
- **Figure or table:** Table: what was first recorded, what the record now says, and what found it.
- **Source:** `docs/specs/task10_tasks.md`; `docs/specs/task10_drone_sizing.md` (addendum 2); `runs/drone/validation/2026-11-08/v6.json`; `runs/replay_drone_online/2026-11-08/online.csv`; `runs/mesh/airfoil2d-e161fb7e6b.first_attempt/error.json`; `runs/drone_inverse_lf/2026-11-09/inverse.json`
- **Speaker notes:** The first online replay is the most useful entry, because it is the result the plan asked to publish if active learning lost. Two of the corrections were references and not the solver, which the solver's own convergence study showed. Any row the builder adds itself is a statement in the task file that the record contradicts.

### D43. Limits of the model (37:30, 1 min)

- **Message:** The study sizes one cruise point at sea level with a fixed propeller efficiency and closed-form structure; what the spec puts out of scope bounds what the front means.
- **Figure or table:** List of what is out of scope, read from section 13 of the spec, and the open ledger and validation items.
- **Source:** `docs/specs/task10_drone_sizing.md` (section 13); `docs/validation/2026-11-08_task10_report.md` (section 9); `runs/drone/validation/2026-11-08/v6.json`
- **Speaker notes:** Wind, altitude and the take-off phase are the first things a real sizing study would add, and the inlet's Task 9 shows the form an envelope study takes. Nothing here claims more than one cruise point.

### D44. Conclusions: the four questions as far as the records go (38:30, 1.5 min)

- **Message:** Active learning wins on this problem only with a feasibility model; the two-level model beats SU2 alone on the mean at small SU2 budgets, with intervals that are over-confident; the inverse query is answered on the SU2 pool and waits on its confirmation run, and the front on the SU2 pool on its analysis, each stated as the records stand at build time.
- **Figure or table:** Table: each question, its answer from the records, the evidence file, and what is still pending.
- **Source:** `runs/drone_grid/2026-11-08/record.json`; `runs/replay_drone_online/2026-11-08/online.csv`; `runs/replay_drone_online/2026-11-08_feas/online.csv`; `runs/drone_inverse_lf/2026-11-09/inverse.json`; `runs/pool_af/2026-11-09/record.json`; `runs/drone_mf/2026-11-09/mf.csv`; `runs/drone_inverse_hf/2026-11-09/inverse.json`; PENDING: `runs/drone_pareto_hf/2026-11-09/pareto.csv`, `runs/drone_confirm/2026-11-09/confirm.json` (pool analyses)
- **Speaker notes:** The pipeline carried over with its gates, queue and replay unchanged, and the new parts are the airfoil family, the two-level model and the sharded workers. The method's answer on question 2 is the result I would lead with, because it includes a loss. Anything still PENDING on this slide is a run in progress, not an estimate.

## Discussion (about 20 minutes, outside the 40)

### D45. Questions, and where the answers are (40:00 onward, about 20 min)

- **Message:** The discussion is open; these are the questions the study invites, and the backup slides that answer them.
- **Figure or table:** Left: discussion prompts. Right: index of DB1 to DB17.
- **Source:** none (no number)
- **Speaker notes:** Start with the limit that matters to the person asking, then open the matching backup slide. Do not quote a number that is not on a slide.

## Backup slides (not timed)

### DB1. Backup: the V6 table, part 1 (V6a to V6d)

- **Message:** Every V6a to V6d row of the validation record, report rows included.
- **Figure or table:** Table: row, measured, reference, deviation, tolerance, verdict.
- **Source:** `runs/drone/validation/2026-11-08/v6.json`
- **Speaker notes:** Report rows have no tolerance and show the lattice convergence the toleranced rows rest on. The Warren-12 moment row stays pending until the benchmark's reference point is sourced.

### DB2. Backup: the V6 table, part 2 (V6e to V6g)

- **Message:** Every V6e and V6f row, and the rows not run with their reason.
- **Figure or table:** Table: row, measured, reference, deviation, tolerance, verdict; then the not-run list.
- **Source:** `runs/drone/validation/2026-11-08/v6.json`
- **Speaker notes:** The V6e fails are kept as fails under decision 8. The not-run rows are shown, not hidden.

### DB3. Backup: E387 point by point at both Reynolds numbers

- **Message:** At every matched angle SU2 lifts more than the tunnel, and its drag runs from below to slightly above it.
- **Figure or table:** Two tables, one per Reynolds number: angle, SU2 cl and cd, tunnel cl and cd, and the two ratios.
- **Source:** `runs/e387/airfoil2d-498b156761/result.json`; `data/validation/e387_uiuc.yaml`
- **Speaker notes:** The comparison is at the tunnel's own angles with no interpolation. The lift offset is nearly uniform, so most of the slope miss is an offset plus a slightly steeper line.

### DB4. Backup: the mesh table (coarse, medium, fine)

- **Message:** On the nominal section the three meshes differ by less than the fine run's own drift, so the table resolves the drift band and not the mesh.
- **Figure or table:** Table: level, cells, iterations and how the run stopped, wall time, cl, cd, cm, drifts, and the shift against fine.
- **Source:** `runs/mesh/airfoil2d-59cd4287e9/result.json`; `runs/smoke2/airfoil2d-51d551f2cc/result.json`; `runs/mesh/airfoil2d-e161fb7e6b/result.json`
- **Speaker notes:** The cost per iteration per cell is the same at all three levels, so cost scales with cells and iterations together. The pool runs coarse on this evidence, with the medium bias check on D40.

### DB5. Backup: the budget-exhausted runs

- **Message:** Every SU2 run that used its whole budget, with its drift: which to accept is an open ruling, and one large drift is a division by a lift coefficient near zero.
- **Figure or table:** Table of the runs whose iterations equal the budget: tag, design and angle, cl, cd, cl and cd drift, kept or not.
- **Source:** `runs/pool_af_bias/airfoil2d-5bfe6fe9ef/result.json`; `runs/pool_af/airfoil2d-0b9023e0fd/result.json`; `runs/nominal/airfoil2d-a41849e173/result.json`; `runs/mesh/airfoil2d-e161fb7e6b/result.json`; `designs/pool_af_cases.csv`
- **Speaker notes:** The drift rule divides the range over the window by the final value, so a case near zero lift reports a huge relative drift on a tiny absolute one. The aggregator drops budget-exhausted runs today and the record keeps them; accepting some of them is ruling 1 on DB16.

### DB6. Backup: the low-pool Pareto record

- **Message:** The Pareto analysis exists end to end on the low pool as a diagnostic: candidates, gates, observed and predicted fronts, band and length scales.
- **Figure or table:** Table of the record's counts and the observed front's ends; the length scales by input.
- **Source:** `runs/drone_pareto_lf/2026-11-09/notes.json`; `runs/drone_pareto_lf/2026-11-09/pareto.csv`
- **Speaker notes:** This run was made so that the analysis is proven before the SU2 pool lands. It is not a study answer, because the questions are asked of the high level.

### DB7. Backup: the 21^6 inverse record

- **Message:** The inverse query walks the whole 21^6 grid in chunks; on the low model the answer is a box corner and the cap never binds.
- **Figure or table:** Table of the inverse record: grid size, points passing the cheap gates, answer, intervals, probability, and the lightest observed design.
- **Source:** `runs/drone_inverse_lf/2026-11-09/inverse.json`
- **Speaker notes:** The closed-form gates are applied to the whole grid and the closure gates to the best candidates. The GP extrapolates to the corner, which is why the direct evaluation is shown on D37.

### DB8. Backup: the bias sweep, full table

- **Message:** All banded ledger quantities, moved one at a time to their band ends at the low-fidelity answer, ranked by the largest endurance change.
- **Figure or table:** Table: rank, quantity, value, band, endurance and take-off mass change at both ends, effect.
- **Source:** `runs/drone_bias_lf/2026-11-09/bias_sweep.csv`
- **Speaker notes:** Quantities with no effect at this design are read by the model but do not bind here. The sweep is repeated at the SU2 answer when that exists.

### DB9. Backup: the online replays, full tables

- **Message:** Mean regret and gated picks at every budget for both online runs, on the same seeds and candidate sets.
- **Figure or table:** Two tables: regret by budget for six strategies, and gated picks by budget.
- **Source:** `runs/replay_drone_online/2026-11-08/online.csv`; `runs/replay_drone_online/2026-11-08_feas/online.csv`; `runs/replay_drone_online/2026-11-08/record.json`; `runs/replay_drone_online/2026-11-08_feas/record.json`
- **Speaker notes:** Equal regret at the first budget is the shared initial design, which makes the rows comparable. The first run's loss and the second run's win are both on the record.

### DB10. Backup: the decision log

- **Message:** The three rulings that shaped the SU2 level, as recorded with their dates.
- **Figure or table:** Table: decision, who and when, the ruling as recorded, and what it changed.
- **Source:** `docs/specs/task10_tasks.md` (decisions 6, 7 and 8)
- **Speaker notes:** Each ruling was put with a recommendation and its evidence, and each is recorded verbatim where the person gave words. Decision 8 is also why no SST with Langtry-Menter attempt was run.

### DB11. Backup: the ledger provenance

- **Message:** Every fixed quantity carries a source and a grade; every assumed one carries a band.
- **Figure or table:** Table by ledger set: quantities, published, derived, assumed, with a band.
- **Source:** `data/drone/air.yaml`; `data/drone/battery.yaml`; `data/drone/propulsion.yaml`; `data/drone/structure.yaml`; `data/drone/rules.yaml`
- **Speaker notes:** The counts are computed from the YAML files at build time. The bands are what the bias sweep moves.

### DB12. Backup: the cost ledger

- **Message:** Wall time per SU2 case by mesh level and the worker-hours spent so far, from every result record.
- **Figure or table:** Table by mesh level: cases, median and range of wall seconds and iterations; worker-hours by tag; the low-fidelity runs' wall time.
- **Source:** `runs/pool_af/airfoil2d-2862718ac9/result.json`; `runs/e387/airfoil2d-498b156761/result.json`; `runs/drone_grid/2026-11-08/record.json`; `runs/drone_pool_lf/2026-11-08/record.json`; `runs/replay_drone_online/2026-11-08/record.json`
- **Speaker notes:** SU2 cases ran on four Colab ranks until the two sharded workers started on 2026-11-09; each sharded worker runs two, and the slide counts the cases at each rank count from the records. The worker-hours count only the cases that have landed, so the pool total grows with every ingest.

### DB13. Backup: the equations index

- **Message:** Every equation on the talk slides, with the module that implements it.
- **Figure or table:** Table: slide, relation, module.
- **Source:** `docs/talk/build_deck_drone.py`; `docs/talk/outline_drone.md`
- **Speaker notes:** The index is generated from the same constants the slides render. A relation the code does not implement does not appear on a slide.

### DB14. Backup: the study guide

- **Message:** The drone study guide has 31 entries in four blocks, in the same form as the inlet guide.
- **Figure or table:** The four blocks of the drone study guide with their entry titles, read from the file.
- **Source:** `docs/talk/study_guide_drone.html`
- **Speaker notes:** Blocks: the problem and the low-fidelity model, airfoil RANS at low Reynolds number, surrogates and the study's answers, and the automation layer. Every number in an entry names the file it comes from.

### DB15. Backup: carried over from the inlet study, and new

- **Message:** The queue, the gates, the GP, EHVI, the replay and the feasibility model carried over unchanged; the two-level model on section polars, the Cauchy stop and the sharded workers are new.
- **Figure or table:** Two-column table: carried over (with the module), new (with the module).
- **Source:** `worker/run_worker.py`; `surrogate/gp.py`; `surrogate/feasibility.py`; `surrogate/mf_gp.py`; `analysis/drone_polar.py`; `cases/templates/inc_rans_airfoil.cfg`
- **Speaker notes:** The inlet study took seven days with the tools built along the way, and this study reused them from the first day. The feasibility model failed to help in the inlet's Task 9 and decided the result here, for the reason on D32.

### DB16. Backup: the open rulings

- **Message:** Three rulings are open for Éder, each with the evidence that frames it.
- **Figure or table:** Table: the ruling, the evidence, and what changes either way.
- **Source:** `docs/validation/2026-11-08_task10_report.md` (section 9); `runs/drone/validation/2026-11-08/v6.json`; `data/drone/rules.yaml`
- **Speaker notes:** None of these is decided by the deck. Each one moves a number only after it is ruled, and the record keeps both states.

### DB17. Backup: record status, what exists and what is pending

- **Message:** Every file this deck reads or waits for, with whether it exists at build time.
- **Figure or table:** Status table: file, what writes it, exists or PENDING.
- **Source:** `runs/pool_af/2026-11-09/record.json`; `runs/drone/validation/2026-11-08/v6.json`; PENDING: `runs/drone_mf/2026-11-09/mf.csv`, `runs/drone_pareto_hf/2026-11-09/pareto.csv`, `runs/drone_inverse_hf/2026-11-09/inverse.json`, `runs/drone_confirm/2026-11-09/confirm.json`, `runs/drone_bias_hf/2026-11-09/bias_sweep.csv` (pool analyses)
- **Speaker notes:** The status column is computed when the deck is built. The talk claims nothing beyond what the existing files show.

## Coverage of the inlet deck

Every slide id of `docs/talk/outline.md` and where its role is covered in this deck. "not applicable"
gives the reason; nothing of the inlet structure is dropped silently.

| Inlet slide | Inlet role | Drone counterpart |
|---|---|---|
| S1 | Title | D1 |
| S1b | A clean exit is not a correct result | D2 |
| S1c | What stopped each injected fault | D3 |
| S1d | Why MCP, and what it does not add | D4 |
| S1a | The questions the study answers | D5 |
| S2 | The design question | D6 |
| S3 | The design box | D7 |
| S4 | Flight condition and why laminar | D7 (sea-level ISA, the only condition); D14 (SA with BCM transition) |
| S5 | The validation ladder | D12, DB1, DB2 |
| S6 | Oblique shock and laminar heating (analytic checks) | D11 |
| S7 | The hard check failed first | D19 |
| S8 | The design point | D10, D13 |
| S9 | The pipeline on one slide | D9, D26 |
| S10 | Gates reject before any CFD | D25, D30 |
| S11 | Queue over Google Drive and a restart-safe worker | D26, D27 |
| S12 | The first live agent call | D4 (no agent-call transcript was recorded for this study; the slide says so) |
| S13 | One exact Gaussian process per objective | D29 |
| S14 | Acquisition, and who chooses | D29 |
| S15 | Active learning against random and Latin hypercube | D31, D32 |
| S16 | Calibration | not applicable: no held-out coverage record exists for this study yet; the one interval check is the direct evaluation on D37 and the confirmation on D38 |
| S18 | Pareto front with uncertainty | D34, D36 |
| S19 | Inverse query and its confirmation | D37, D38 |
| S20a | The three-ramp inlet over a flight envelope | not applicable: Task 9 is the inlet study's second case; this deck's whole study is the new case, and DB15 states what carried over |
| S20b | Active learning in six dimensions | D32 |
| S20c | Cheap physics as a first level | D33 |
| S20d | What did not work: learned feasibility and the robust query | D32 (here the feasibility model decided the result); D37 (the cap does not bind on the low model) |
| S21 | What failed, in order | D42 |
| S22 | Limits of the model | D43, D41 |
| S24 | Questions, and where the answers are | D45 |
| B1 | Turbulence model | DB10 (decision 8: why no second turbulence and transition model was run) |
| B2 | Wall boundary condition | not applicable: this study has no wall-heating objective, so the wall temperature question does not arise |
| B3 | Mesh convergence | DB4 |
| B4 | The numerics story | DB5, D15 |
| B5 | Design-box trim | D30 (the gated region is mapped; no box trim was made in this study) |
| B6 | Full validation table | DB1, DB2 |
| B7 | A neural-network ensemble against the GP | not applicable: no ensemble was run for this study |
| B8 | A neural operator for the heat-flux profile | not applicable: the section outputs are scalars per angle, and no profile model was run |
| B9 | Faults through real SU2 | D28, DB5 (no fault-injection campaign was run for the airfoil family) |
| S17 | The pool across the box | D35 |
| S20 | Design maps over the box | D30 |
| S23 | What is still to be recorded | DB17 |

# Development runs, 2026-11-01: numerics selection and V1 on the Fable cloud container

These are not the official Task 1 records (those come from Colab, `runs/task1/`). They were run
with the SU2 v8.2.0 linux64 serial release binary (statically linked; sha256 of the outer zip
recorded in `solver_version.txt` of each case) on the Claude Code cloud container (4 cores, one
process per run), from this repository's `worker.make_case` and `worker.run_case` at commit
0131a09 (variants: at a6d1f49-era config edited by hand as listed below).

## variants/ (Euler wedge, theta 10 deg, medium mesh, 17 664 cells, ITER 800)

All start from the Task 0 config (AUSMPLUSUP2, Venkatakrishnan-Wang, CFL adapt 0.5/1.2/0.5/100)
and change only what the name says; see each `case.cfg`.

| Variant | Change | log10 rms(rho) start -> end | Outcome |
|---|---|---|---|
| A_fixedcfl5 | CFL 5 fixed, no adaptation | -2.17 -> diverged | Error Exit at iteration 50 |
| B_adapt_max20 | CFL adapt (0.5, 1.05, 1.0, 20) | -2.49 -> -2.48 (min -3.75) | stalled, 800 iterations |
| C_roe | ROE, entropy fix 0.1, CFL adapt (0.5, 1.05, 1.0, 20) | -3.45 -> -12.05 | converged in 603 iterations |
| D_venkat | VENKATAKRISHNAN limiter, CFL adapt (0.5, 1.05, 1.0, 20) | -2.55 -> -2.40 | stalled, 800 iterations |

Decision: ROE with entropy fix 0.1 and CFL adapt (0.5, 1.05, 1.0, 20) is the default (commit 0131a09).

## wedge-a7fe022d68 (Euler, 10 deg, medium) and wedge-381c48d17f (laminar, 300 K wall)

Run with the new defaults. Euler: 417 iterations to log10 rms(rho) = -10, 41.6 s on one core.
Laminar: 910 iterations to -10, 99.1 s on one core. V1 evaluated from the Euler volume output
(pressure and Mach derived from the conservative variables): beta 22.366 deg (analytic 22.234,
error +0.132 deg, tolerance 0.5), p2/p1 2.5030 (analytic 2.5060, -0.12 percent, tolerance 2),
M2 3.2799 (analytic 3.2861, -0.19 percent, tolerance 2): PASS. Freestream density 0.018410
and velocity 1206.8 m/s match the specified state. Volume and surface data of these runs are
not committed (CSV output held only conservative variables; the output format was changed to
Tecplot ASCII afterwards).

# Development runs, 2026-11-01: inlet design point theta1 = theta2 = 8 deg, medium mesh (30 600 cells)

Run on the Fable cloud container (SU2 v8.2.0 serial release binary, one core each), built with
`mcp_server.queue.build_case` at commit 9d5a0b4 (config output switched to Tecplot by hand, as the
committed templates now do). Not the official Task 2 records (those come from Colab); numbers
below were evaluated by Fable directly from `surface_flow.dat` with the definitions of
`docs/specs/00_decisions.md` section 3 (the `postprocess.metrics` module reproduces them later).

| Case | Iterations | Wall time (1 core) | Status |
|---|---|---|---|
| inlet88_euler | 650 | 129.6 s | converged (rms rho -3.20 -> -10.02) |
| inlet88_navier_stokes | 1574 | 376.7 s | converged (rms rho -3.06 -> -10.0 ) |

## V4e (Euler): PASS
- Throat area-averaged p0/p0_inf 0.9284 vs two-shock 0.9316 (-0.34 percent, tolerance 2).
- Throat area-averaged Mach 2.958 vs 2.962 (-0.14 percent, tolerance 2).
- Per-streamtube recovery with terminal normal shock 0.3158 vs analytic 0.3160; capture ratio 0.9994.
- Note: a few wall-adjacent throat nodes carry low p0 (minimum 0.39) from the numerical entropy
  layer of the sharp leading edge and corner in the Euler solution; mass averaging makes this
  immaterial (mass-averaged 0.9292).

## V4v (laminar): PASS (soft, 5 percent)
- Core (middle 50 percent of the throat height) p0/p0_inf 0.9351 vs 0.9316 (+0.38 percent).
- Whole-throat area average 0.8824; mass-averaged recovery_throat 0.9114 (boundary-layer loss
  about 2 percent); recovery_total 0.3166 (the lower mass-averaged Mach 2.907 weakens the
  terminal shock, which slightly more than compensates the viscous loss); capture 0.984.
- Peak heat flux on ramp 2: 28.61 kW/m^2 at x = 0.1171 m, at reattachment behind a laminar
  separation bubble at the compression corner (negative streamwise skin friction from
  x = 0.095 to 0.105 m); ramp-1 heating at x = 0.05 is 24.9 kW/m^2; the heat flux drops to
  4.7 kW/m^2 inside the bubble and decays to 17 kW/m^2 at the throat.

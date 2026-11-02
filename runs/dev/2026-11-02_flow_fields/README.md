# Flow-field pictures (2026-11-02): three development runs with volume output

Purpose: contour pictures for the talk (Mach, p/p_inf, T/T_inf, numerical schlieren, bow shock) and
the V3 stand-off check against Billig, which needs a volume file that the production runs do not
save. Run serially with the SU2 v8.2.0 Linux release binary (`SU2-v8.2.0-linux64.zip`, sha256
`9956c921fcf507c52db1a8895a70fcf26ab2e8e81f84e5a000f1870a7702c472`) on the Fable cloud container,
1 core, through `worker.run_case` on cases staged by `mcp_server.queue.create` (schema, gates, mesh
quality and config checks as for every production case; `save_volume: true`, tag `dev-flowfield`).
Same templates, numerics and meshes as the production runs; only `OUTPUT_FILES` adds `TECPLOT_ASCII`.

| case | design | mesh | cells | iterations | log10 rms(rho) | wall [s] | status |
|---|---|---|---|---|---|---|---|
| inlet2r-92352faad1 | inlet 8/8 | medium | 30 600 | 1230 | -3.07 to -10.00 | 357 | converged |
| inlet2r-ef324f2106 | inlet 11.965/7.115 (inverse answer) | medium | 28 800 | 1248 | -3.02 to -10.00 | 343 | converged |
| cylinder-04b6b912c5 | cylinder R = 10 mm | fine | 12 544 | 3090 | -3.66 to -10.00 | 319 | converged |

Each folder holds `params.json`, `geometry.json`, `case.cfg`, `mesh_quality.json`,
`mesh_markers.json`, `job.json`, `result.json` (run, solver, history summary, metrics), and gzipped
`history.csv`, `log.txt`, `surface_flow.dat` and `flow.dat` (the volume file, about 1.4 MB each
compressed). The mesh is not stored; `worker.make_case` rebuilds it from `params.json`.

## Reproducibility check against the records

The serial container runs give the same metrics as the 4-rank Colab records to every printed digit:

| quantity | this run | reference record |
|---|---|---|
| 8/8 recovery_total | 0.316340 | 0.316340 (`runs/val/inlet2r-d4d29884be`, Colab) |
| 8/8 q_peak | 29 725.42 W/m2 | 29 725.42 (same) |
| 11.965/7.115 recovery_total | 0.345128 | 0.345128 (`runs/confirm/inlet2r-374dad241f`, Colab) |
| 11.965/7.115 q_peak | 31 461.94 W/m2 | 31 461.94 (same) |
| cylinder fine q_stag | 233 223 W/m2 | 233 300 (`runs/dev/2026-11-01_cylinder_v3_attempt3/cyl_fine_ef03_cfl5`, CFL max 5; this run uses the production CFL max 20) |

## Figures (`figures/`, made by `python -m postprocess.plot_flowfield`)

- `inlet_8_8.png`, `inlet_confirm.png`: four panels each, Mach, p/p_inf, T/T_inf, numerical
  schlieren (|grad rho| on a uniform grid, saturated at its 98th percentile).
- `inlet_8_8_mach.png`, `inlet_8_8_schlieren.png`, `inlet_confirm_mach.png`,
  `inlet_confirm_schlieren.png`: single panels for the slides (`--only`).
- `cylinder.png`: Mach contours with the measured stand-off and Billig's line, and the stagnation-line
  density profile.

What the inlet pictures show: the two oblique shocks meet at the cowl lip (the shock-on-lip rule
holds in the viscous solution), the cowl shock and its reflections inside the duct, and the thin
laminar boundary layer on both ramps. Freestream p/p_inf = 0.969 in the colorbar is the freestream
state as SU2 initialises it from `FREESTREAM_OPTION= TEMPERATURE_FS`; the throat static pressure
is about 4.1 p_inf at 8/8 and about 5.1 p_inf at 11.965/7.115, both as the two-shock relations give
(`geometry.json`, `p_th_over_p_inf_inviscid`).

## V3 stand-off against Billig (report item of the tolerance table)

`cylinder-04b6b912c5/standoff.json`: the shock on the stagnation line is placed where the linearly
interpolated density first exceeds the mean of the freestream and the normal-shock density (the
cold-wall layer, where the density is largest, is left out). Measured delta/R = 0.546; Billig
0.386 exp(4.67/M^2) = 0.517 at Mach 4; deviation +5.6 percent, inside the 15 percent report
tolerance of `docs/specs/00_decisions.md`, section 4. The captured shock is 2 to 3 cells thick at
this radius, which is about 0.05 R, so the measurement carries an uncertainty of that order.
`runs/dev/2026-11-01_cylinder_v3_attempt3/README.md` lists 0.541 for the CFL-5 fine run.

# V5c diagnosis: why the nominal inlet3r fine-mesh laminar run diverged (2026-11-03)

Case: `runs/dev/2026-11-03_inlet3r_v5/nominal_ns_fine` (7/7/7 deg, Mach 4.0, 30 km, 300 K, fine mesh),
which diverged at iteration 4498 after its residual fell to about -8.3. Script:
`python -m analysis.diag_fine_v5c` (SU2 v8.2.0 release binary on the container). Both runs use the
recorded params and one config edit each (`edits.json`); neither changes a tolerance and neither
replaces the failed V5c record.

| Run | Edit | Result |
|---|---|---|
| `snapshots/` | volume output every 250 iterations, one file per write | diverged at iteration 4498, the same iteration as the original (the run is deterministic) |
| `cfl5/` | CFL cap 5 instead of 20 | residual down to -8.18 at iteration 5500, then the same turnaround; diverged at iteration 11017 |

Findings, from `history.csv.gz` and the four kept snapshots (iterations 1500, 2000, 2500, 3000;
the others stayed in the scratch folder):

1. The turnaround happens at the same flow state in both runs, not at the same iteration or step
   size: the throat AVG_TOTALPRESS has settled to about 167,620 Pa (167,620.4 Pa at iteration 1500
   with cap 20; 167,619.6 Pa at iteration 5500 with cap 5) when the residual starts to rise. The CFL
   cap delays the divergence and does not remove it.
2. Where it starts: comparing density with the iteration-1500 field, the largest change at
   iteration 2000 (4.6 percent) and 2500 (43 percent) is at (0.2768 to 0.2769, 0.0731 to 0.0733) m,
   the corner E_body = (0.2769, 0.0730) m where the body wall meets the duct outlet. The local Mach
   number there is 0.28 at iteration 2000 and 0.06 at 2500: the subsonic part of the wall boundary
   layer at the outflow boundary. By iteration 3000 the largest change is at x = 0.270 m, by 3250 at
   x = 0.259 m: the disturbance moves upstream along the body wall from the outlet.
3. The duct outlet is `MARKER_SUPERSONIC_OUTLET` (00_decisions.md section 2: "all boundaries are
   supersonic"), which extrapolates every variable from the interior. In the subsonic layer at the
   wall this condition is ill-posed. It did not matter for inlet2r on any mesh run so far. Why it
   matters here is not shown; the candidate explanation is that inlet3r has a lower throat Mach
   number (2.72 against 2.96 at the inlet2r design point) and a smaller first cell (12 um against
   20 um at medium), so the fine mesh resolves more of the subsonic layer at the outlet.

Conclusion: the divergence is a boundary-condition problem at the duct outlet, not a property of
the inlet flow at the nominal point. Fix tried next (Task 9 spec addendum): `MARKER_OUTLET` for the
duct outlet of inlet3r, which SU2 applies node by node (extrapolation where the outflow is
supersonic, static pressure imposed where it is subsonic), with the back pressure set to the
inviscid static pressure behind the three shocks at the flight condition.

# NS pool failure diagnosis: case inlet3r-fe9cd9771d (2026-11-03)

By the time this was run, 4 of the first 56 container NS pool runs had diverged (3 of them below
Mach 3.8). The case diagnosed is the easiest-looking of the four: 3.77/3.42/3.48 deg (10.7 deg
total turning), Mach 3.59, 29.08 km, 452.8 K. The pool record
(`runs/pool3r/ns/inlet3r-fe9cd9771d`) diverged at iteration 1774. Script:
`python -m analysis.diag_pool3r_fail --case inlet3r-fe9cd9771d` (SU2 v8.2.0 release binary on the
container). Each run is the recorded params plus the config edits in its `edits.json`.

| Run | Duct outlet | Result |
|---|---|---|
| `snapshots/` | `MARKER_OUTLET`, back pressure 3360.08 Pa (as in the pool), volume output every 100 iterations | diverged at iteration 1774, the same iteration as the pool record |
| `supersonic/` | `MARKER_SUPERSONIC_OUTLET` (the Euler and inlet2r condition) | residual -8.33 at iteration 1000, then a slow rise to about -6.7 while the duct total pressure drifts down (115,785 Pa at 2000 to 114,295 Pa at 7500); breakdown from iteration 7500 (-3.72 at 7900); not converged at max_iter 8000, metrics unphysical (recovery_throat -719) |

Findings (from `snapshots/`, fields kept at iterations 100, 200, 300, 500 and the last write; the
others stayed in the scratch folder):

1. Onset: the largest density change between iterations 100 and 200 (a factor 13.9) is at
   (0.4158, 0.1194) m, next to E_cowl = (0.4153, 0.1218) m, where the cowl inner wall meets the duct
   outlet; local Mach 0.17. Through iteration 400 the largest change stays within 7 mm of that corner;
   from 500 to 1700 it moves upstream through the duct and along the body to x = 0.09 m.
2. Backflow at the outlet: at iteration 100, 22 of the 79 outlet nodes, all on the cowl side, have
   flow into the domain (normal velocity down to -514 m/s), with static pressure about 1950 Pa against
   the imposed 3360 Pa. At iteration 200 the inflow reaches -1276 m/s (Mach 1.86). The body side of
   the outlet flows out normally at about 3280 Pa.
3. With the supersonic outlet the run does not blow up early but does not hold its converged state:
   the same slow drift and late breakdown as the first V5c fine-mesh run
   (`runs/dev/2026-11-03_inlet3r_v5c_diag/README.md`).

Conclusion: for this case both duct outlet conditions fail, in different ways, at the place where
the outlet cuts through the subsonic wall layers at the end of the 0.05 m duct. The failure is a
property of where the outflow boundary sits, not of the inlet flow at this point of the envelope.
The likely remedy (a longer duct or a buffer region before the outlet) changes the geometry of every
run and was not tried: the pool is half run and the schedule has no room to re-run it.

Decision (2026-11-03): the pool keeps its settings; the failed runs stay failed records. The
feasibility classifier (spec question 3) therefore learns where this solver set-up converges, which
is what the question asks; the report must say that the failures diagnosed so far are outflow-boundary
numerics and not an inlet operating limit. The other three failures were not diagnosed.

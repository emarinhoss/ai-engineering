# V3 attempt 3 (2026-11-01): entropy-fix / CFL split, V3 grid study at entropy fix 0.3, wedge sensitivity

Same cylinder meshes as attempt 1; wedge = the laminar wedge of runs/dev/2026-11-01_numerics. All
Roe + MUSCL (Venkatakrishnan-Wang); SU2 v8.2.0 serial on the Fable cloud container. Reference
q_FR = 244.3 kW/m^2, Billig stand-off 0.517 R. Evaluated with postprocess.validation (commit 2efdabe).

| Run | Change vs attempt 1 | log10 rms(rho) | q_stag [kW/m^2] | vs FR | q(0,10,20,30,45,60,90 deg) | Stand-off/R |
|---|---|---|---|---|---|---|
| cyl_coarse_ef01_cfl5 | CFL max 5 | -3.22 -> -4.21, stalled (6000) | 494 | +102 percent | 494 247 183 173 139 101 34 | 0.533 |
| cyl_coarse_ef03_cfl20 | entropy fix 0.3 | -3.22 -> -10.00 in 897 | 243.6 | -0.3 percent | 244 231 214 189 148 100 35 | 0.539 |
| cyl_medium_ef03_cfl5 | entropy fix 0.3, CFL 5 | -3.45 -> -10.00 in 4464 | 241.7 | -1.1 percent | 242 236 218 193 148 102 33 | 0.542 |
| cyl_fine_ef03_cfl5 | entropy fix 0.3, CFL 5 | -3.66 -> -9.09 at 8000 (5.4 orders) | 233.3 | -4.5 percent | 233 231 220 194 150 103 34 | 0.541 |

Conclusion: the entropy fix is the cure, the CFL cap is not. V3 PASSES at entropy fix 0.3: fine mesh
within 15 percent of Fay-Riddell (-4.5), medium-to-fine change -3.5 percent (tolerance 5), stand-off
within 15 percent of Billig (+4.6, report). The sequence moves away from Fay-Riddell with refinement
(243.6, 241.7, 233.3), i.e. the discretisation error and the correlation error have opposite signs
on the coarse mesh; the fine value is the one to quote. The variant of q_FR with the CFD velocity
gradient returned nothing on these files (edge-finding rule not robust); it is a diagnostic only.

Wedge sensitivity (Eckert window, V2b): entropy fix 0.1 mean 0.75 percent max 1.10; entropy fix 0.3
mean 1.60 percent max 1.95 (identical at CFL 20 and CFL 5; 903 vs 3350 iterations to -10).
Decision: ENTROPY_FIX_COEFF = 0.3 and CFL adapt (0.5, 1.05, 1.0, 20) for every family.

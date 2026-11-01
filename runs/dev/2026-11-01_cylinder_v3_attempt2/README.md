# V3 Fay-Riddell cylinder, attempt 2 (2026-11-01): convective-scheme comparison on the coarse mesh

Same case and mesh as attempt 1 coarse (3136 cells, first cell 8 um), ITER 4000, each run changes
only what the name says relative to attempt 1 (Roe, entropy fix 0.1, MUSCL Venkatakrishnan-Wang,
CFL adapt max 20). Reference q_FR = 244.3 kW/m^2. Heat flux listed at 0, 10, 20, 30, 45, 60, 90 deg
from the stagnation point.

| Scheme | log10 rms(rho) start -> end | q_stag [kW/m^2] | vs FR | q(phi) [kW/m^2] | Verdict |
|---|---|---|---|---|---|
| HLLC | -3.22 -> -3.94 (stalled) | 549 | +125 percent | 549 301 199 169 131 93 31 | no |
| AUSM+-up2 | -3.05 -> -3.09 (stalled) | 363 | +49 percent | 363 158 82 163 189 145 53 | no (carbuncle pattern) |
| SLAU2 | -3.12 -> -3.43 (stalled) | 158 | -35 percent | 158 48 89 279 240 108 -32 | no (carbuncle pattern) |
| JST, first order | -3.22 -> -9.78 (converged) | 23 | -91 percent | 23 174 225 207 160 107 37 | no (stagnation point smeared) |
| Roe, first order (no MUSCL) | -3.22 -> -3.38 (stalled) | 374 | +53 percent | 374 445 374 288 205 131 44 | no |
| **Roe, entropy fix 0.3, CFL max 5** | **-3.22 -> -10.00 in 2353 iterations** | **243.6** | **-0.3 percent** | 244 231 214 189 148 100 35 | **yes** |

The winning setting is being split (entropy fix alone, CFL cap alone), run at the medium and fine
levels for the V3 grid study, and checked on the laminar wedge against Eckert, in
`../2026-11-01_cylinder_v3_attempt3/` (pending at the time of this commit).

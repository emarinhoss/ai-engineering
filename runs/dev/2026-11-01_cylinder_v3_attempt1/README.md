# V3 Fay-Riddell cylinder, attempt 1 (2026-11-01): FAILED, not tuned away

Cylinder R = 10 mm, laminar, isothermal 300 K, Mach 4 at 30 km, Roe (entropy fix 0.1), MUSCL with
Venkatakrishnan-Wang, CFL adapt (0.5, 1.05, 1.0, 20), ITER 8000, SU2 v8.2.0 serial on the Fable
cloud container, meshes from `geometry/cylinder.py` at commit 9d5a0b4 (quality gate passed at all
three levels). Reference: Fay-Riddell q = 244.3 kW/m^2; Billig stand-off 0.517 R.

| Level | Cells | Iterations | log10 rms(rho) start -> end | q_stag [kW/m^2] | vs FR | Stand-off/R | Wall T at stagnation |
|---|---|---|---|---|---|---|---|
| coarse | 3136 | 8000 (cap) | -3.22 -> -4.17 (stalled) | 369 | +51 percent | 0.530 (+2.6 percent) | 329 K |
| medium | 6400 | 4212 (diverged, Error Exit) | -3.45 -> +14.3 | meaningless | - | - | - |
| fine | 12544 | 8000 (cap) | -3.66 -> -3.47 (stalled) | 774 | +217 percent | 0.492 (-4.8 percent) | 299 K |

The coarse heating distribution is not monotonic along the body (369, 251, 168, 182, 146 kW/m^2 at
0, 10, 20, 30, 45 deg), the medium run blew up, and the fine run has negative heat flux near
the shoulder: the signature of the carbuncle instability of the Roe scheme on a bow shock aligned
with the grid. The stagnation pressure (20.9 p_inf on coarse vs the pitot value 21.07) and the
stand-off distance are right, so the freestream, geometry and mesh are not the cause.

Conclusion: V3 is a hard gate and it FAILED with the Task 0 numerics (Roe). Next step, recorded
in `../2026-11-01_cylinder_v3_attempt2/` when done: a convective-scheme comparison on the coarse
cylinder (HLLC, AUSM+-up2, SLAU2, Roe with entropy fix 0.3 and CFL <= 5, JST, first-order Roe).
The wedge and inlet cases keep Roe unless the comparison shows a scheme that works for both.

# Task 10 flow figures: captions

- `cp_e387.png`: Cp against x/c for E387 at Re 203,800 and five angles, medium mesh. Sources: `runs/e387/airfoil2d-{498b156761,a1edd0dc9d,7de8a51345,f575890d77,69bc668e06}/surface_flow.dat.gz` and `result.json`.
- `cp_design0.png`: Cp against x/c for pool design 0 (coarse mesh, Re 121,945) at five angles; the 14 degree case is the stalled one. Sources: `runs/pool_af/airfoil2d-{fd72a75766,7eb76bdca4,e91b498c69,f2c50f8e25,2862718ac9}/surface_flow.dat.gz` and `result.json`.
- `cp_mesh_pair.png`: Cp of the nominal section (4 % camber, 12 % thick, Re 200,000, 6 deg) on the coarse, medium and fine meshes with a leading-edge zoom. Sources: `runs/mesh/airfoil2d-59cd4287e9/`, `runs/smoke2/airfoil2d-51d551f2cc/`, `runs/mesh/airfoil2d-e161fb7e6b/` (`surface_flow.dat.gz`, `result.json`).
- `cf_e387.png`: Skin friction Cf_x (SU2 Skin_Friction_Coefficient_x) on the E387 section at five angles. Sources: the five `runs/e387/*/surface_flow.dat.gz` listed for cp_e387.png.
- `section_polars.png`: cl(alpha) and cd(cl) of SU2, the model's low-fidelity section and, for E387, the UIUC tunnel. Sources: `runs/e387/*/result.json`, `runs/pool_af/*/result.json`, `runs/pool_af/2026-11-09/results.csv`, `data/validation/e387_uiuc.yaml`, and `drone/section.py` (low_fidelity).
- `convergence_smoke2.png`: rms[P], CL and CD against iteration for the medium-mesh nominal case. Sources: `runs/smoke2/airfoil2d-51d551f2cc/history.csv.gz` and `result.json`.

Pressure contours need a volume file; see `python -m postprocess.plot_flowfield airfoil`.

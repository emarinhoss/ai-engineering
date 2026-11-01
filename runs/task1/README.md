# Task 1 official records (Colab, 2026-11-01)

Run by Éder with notebooks/00_su2_colab.ipynb at commit f8ac079 on a Colab runtime with 8 vCPU and
51 GB (reported by the notebook; the earlier smoke test showed 2 vCPU and 12 GB). SU2 v8.2.0
"Harrier" release binaries (serial zip sha256 9956c921..., mpi zip 038db2a8...). The notebook's own
summary is README_colab.md; the JSON reports (budget, V1, V2a, heat-flux sign, first light) are
beside it. Per case: params, geometry, job, mesh_quality, case.cfg, result_partial.json,
solver_version.txt. Large files stay on Drive (su2queue/runs/task1/<case_id>/) and are referenced
by Drive file id below; they were not pulled through the connector.

| Case | Content | Result |
|---|---|---|
| wedge-3c92249afa | Euler wedge 10 deg, medium, 2 MPI ranks | converged, 417 iterations, 40.3 s; V1 PASS: beta 22.366 (ref 22.234, +0.132 deg), p2/p1 2.5030 (-0.12 percent), M2 3.2799 (-0.19 percent) |
| wedge-db7ce9974a | laminar wedge, 300 K wall, 2 MPI ranks | converged, 910 iterations, 95.6 s; V2a +1.69 percent; heat flux positive into the wall (integral 4573 W/m) |
| wedge-fff1623e77 | laminar, 200 iterations, 2 MPI ranks | timing: 0.107 s per iteration |
| wedge-c1f497b16b | laminar, 200 iterations, serial | timing: 0.120 s per iteration (MPI speed-up 1.12) |

Gate T1: GO (medium mesh, pool 96). 25k-cell estimate 114 s per run at 770 iterations; the medium
inlet mesh (30.6k cells, about 1570 iterations) therefore comes to about 4 minutes on this runtime.
First light (SU2 tutorial wedge) exited with code 1 immediately (download or sed step); no physics
claim depends on it and it is not repeated. These runs used entropy fix 0.1 (the setting at
f8ac079); the identical numbers were obtained on the Fable cloud container (runs/dev).

Drive file ids: Euler history.csv 1MOrSnDS1CtXEKjwHqNRUHQESAgHCY_AE, flow.dat 1kJpLPw8-kHFk1brPEj8yFEjscRN7EMI7,
surface_flow.dat.gz 1qg9gWpwZU3QQd2SVuJvGtfYvOtOVoCUx, log 1m-0W9EVdNxYDQXjiqC9SvY7tuwsDWwSh; laminar history.csv
1--bhdrysNfVIint57_S-xpXo8Sb0Kevv, flow.dat 1EFqo4IkrHGpMDwh_WXLHctmDo3PacIP6, surface_flow.dat.gz
1lA6onA9HUCuZDheJmgCsEOlMBnxIBRVd, log 1QLhN7xWfMh0XE3WVYCewbbJ7KbUH6YBq; mesh.su2 (same for all four)
1Sjvc2ZmJpPvk2z0aSNCOxa83-GE44M_z. Note: the mesh.su2 generated on Colab hashes to 500f26a4e168...,
the same params at the same commit hash to ba614d0379f1... here (last floating-point digit differs
between platforms); the worker's regeneration check therefore uses a rounded-coordinate fingerprint.

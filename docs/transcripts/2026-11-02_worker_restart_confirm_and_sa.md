# Worker log: second Colab start, confirmation run and Spalart-Allmaras sensitivity (2026-11-02)

Pasted by Éder from the Colab worker cell (notebook `01_worker_colab.ipynb`, main at e310bbc, worker
`colab-a83ef64abf32`, 4 MPI ranks). The four jobs had been staged and uploaded as single job files
at 11:52 UTC (confirmation) and 14:33 UTC (sensitivity); the worker took them in upload order. Every
line agrees with the ingested records in `runs/confirm/` and `runs/sensitivity/` (start and finish
times, convergence status; wall times 334, 125, 310 and 126 s).

```
/content/ai-engineering
[2026-11-02T14:37:31+00:00] worker colab-a83ef64abf32 on /content/drive/MyDrive/su2queue, SU2 command: mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T14:37:40+00:00] 0 failed job(s) made pending again (config_mismatch)
[2026-11-02T14:38:21+00:00] inlet2r-374dad241f: regenerating mesh and config at commit e310bbce62
[2026-11-02T14:38:22+00:00] inlet2r-374dad241f: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T14:43:57+00:00] inlet2r-374dad241f: done, convergence converged
[2026-11-02T14:43:57+00:00] inlet2r-1731bdea74: regenerating mesh and config at commit e310bbce62
[2026-11-02T14:43:58+00:00] inlet2r-1731bdea74: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T14:46:04+00:00] inlet2r-1731bdea74: done, convergence converged
[2026-11-02T14:46:04+00:00] inlet2r-8a09596911: regenerating mesh and config at commit e310bbce62
[2026-11-02T14:46:06+00:00] inlet2r-8a09596911: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T14:51:17+00:00] inlet2r-8a09596911: done, convergence converged
[2026-11-02T14:51:17+00:00] inlet2r-d7e3815b57: regenerating mesh and config at commit e310bbce62
[2026-11-02T14:51:18+00:00] inlet2r-d7e3815b57: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T14:53:24+00:00] inlet2r-d7e3815b57: done, convergence converged
```

Reading: the restart carried `--retry-reason config_mismatch` from the earlier incident and found
nothing to retry ("0 failed job(s)"); the worker regenerated mesh and config for each job and the
fingerprints and the config hashes matched (the sensitivity jobs carry the `RANS_SA` hash
`2f21e77d...`, the confirmation job the pool hash `b0c231e7...`); no job was repeated. The one
regeneration step per job took one to two seconds. The queue was empty after 14:53 UTC.

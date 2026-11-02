# Worker log: restart with `--retry-reason config_mismatch`, re-failure, re-staged jobs running

Pasted by Éder from the Colab worker cell on 2026-11-02 (worker colab-03fd494d7144, commit
45c3805d1d). Kept verbatim except that the 63 identical "cleared by --retry-reason" lines and the
63 "regenerating ... FAILED (config_mismatch)" pairs between 01:46:59 and 01:50:47 are shown as
their first and last three. What it shows, in order:

1. 01:46 to 01:50: the restart clears the 63 refused jobs and re-runs them; every one fails
   again in about 3 seconds (mesh regenerated, hash compared, no SU2 started). The job files on
   Drive still carried the whole-file hash, which cannot match on Colab for these jobs
   (`PLAN.md`, Day 1 status, 2026-11-02 entry).
2. 01:50 to 04:01: idle, nothing pending.
3. From 04:01: the same worker, without a restart, picks up the re-staged single job files
   (line-based hash) whose run folders were moved to the Drive trash, and runs SU2 on each:
   5 to 7.5 minutes per case, all `convergence converged` so far.

```
/content/ai-engineering
[2026-11-02T01:46:08+00:00] worker colab-03fd494d7144 on /content/drive/MyDrive/su2queue, SU2 command: mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T01:46:59+00:00] inlet2r-029b302750: 2-failed (config_mismatch) cleared by --retry-reason, will be re-run
[2026-11-02T01:46:59+00:00] inlet2r-0bc11adc67: 2-failed (config_mismatch) cleared by --retry-reason, will be re-run
[2026-11-02T01:46:59+00:00] inlet2r-0c0990b14f: 2-failed (config_mismatch) cleared by --retry-reason, will be re-run
... (57 more identical lines) ...
[2026-11-02T01:47:00+00:00] inlet2r-eda4e60b76: 2-failed (config_mismatch) cleared by --retry-reason, will be re-run
[2026-11-02T01:47:00+00:00] inlet2r-fc098c90d9: 2-failed (config_mismatch) cleared by --retry-reason, will be re-run
[2026-11-02T01:47:00+00:00] inlet2r-fd8bbe1147: 2-failed (config_mismatch) cleared by --retry-reason, will be re-run
[2026-11-02T01:47:00+00:00] inlet2r-fe1f4b9b0c: 2-failed (config_mismatch) cleared by --retry-reason, will be re-run
[2026-11-02T01:47:00+00:00] 63 failed job(s) made pending again (config_mismatch)
[2026-11-02T01:47:03+00:00] inlet2r-80c68564df: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T01:47:06+00:00] inlet2r-80c68564df: FAILED (config_mismatch)
[2026-11-02T01:47:06+00:00] inlet2r-0f6d6f25a5: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T01:47:09+00:00] inlet2r-0f6d6f25a5: FAILED (config_mismatch)
[2026-11-02T01:47:09+00:00] inlet2r-b6d1ece6b7: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T01:47:12+00:00] inlet2r-b6d1ece6b7: FAILED (config_mismatch)
... (57 more regenerate/FAILED pairs, about 3.5 s each) ...
[2026-11-02T01:50:36+00:00] inlet2r-eda4e60b76: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T01:50:40+00:00] inlet2r-eda4e60b76: FAILED (config_mismatch)
[2026-11-02T01:50:40+00:00] inlet2r-0c0990b14f: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T01:50:44+00:00] inlet2r-0c0990b14f: FAILED (config_mismatch)
[2026-11-02T01:50:44+00:00] inlet2r-e643166375: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T01:50:47+00:00] inlet2r-e643166375: FAILED (config_mismatch)
[2026-11-02T04:01:05+00:00] inlet2r-0f6d6f25a5: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T04:01:06+00:00] inlet2r-0f6d6f25a5: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T04:06:41+00:00] inlet2r-0f6d6f25a5: done, convergence converged
[2026-11-02T04:06:47+00:00] inlet2r-74c8255f21: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T04:06:48+00:00] inlet2r-74c8255f21: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T04:11:56+00:00] inlet2r-74c8255f21: done, convergence converged
[2026-11-02T04:12:03+00:00] inlet2r-80c68564df: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T04:12:04+00:00] inlet2r-80c68564df: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T04:16:56+00:00] inlet2r-80c68564df: done, convergence converged
[2026-11-02T04:16:57+00:00] inlet2r-b6d1ece6b7: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T04:16:57+00:00] inlet2r-b6d1ece6b7: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T04:23:58+00:00] inlet2r-b6d1ece6b7: done, convergence converged
[2026-11-02T04:23:58+00:00] inlet2r-d9368a016d: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T04:23:59+00:00] inlet2r-d9368a016d: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
[2026-11-02T04:31:27+00:00] inlet2r-d9368a016d: done, convergence converged
[2026-11-02T04:31:27+00:00] inlet2r-7d87d8922e: regenerating mesh and config at commit 45c3805d1d
[2026-11-02T04:31:28+00:00] inlet2r-7d87d8922e: running mpirun -n 4 --allow-run-as-root /content/su2mpi/bin/SU2_CFD
```

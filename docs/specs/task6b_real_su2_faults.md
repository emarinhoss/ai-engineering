# Task 6b spec: fault injection through real SU2 (2026-11-03)

Requested by Éder on 2026-11-03. Written before any run. Closes the README item "injected faults
through real SU2: not run".

## Question

`tests/test_faults.py` shows that the gates and failure records work with the fake solver
(`tests/fake_su2.py`). Does the same chain hold when the solver is the real SU2 v8.2.0 binary, and
what does real SU2 do when a gate is bypassed? The answer is recorded whichever way it goes; a fault
that is not caught is a finding, and its guard (if any) is added after, as a separate change.

## Setup

- Solver: the SU2 v8.2.0 release binary on the container (the one used for the Task 4c re-runs),
  one process, no MPI.
- Case: the wedge family, coarse mesh, laminar (`{"family": "wedge", "theta1_deg": 10.0,
  "solver": "NAVIER_STOKES", "mesh_level": "coarse", "max_iter": 3000, "tag": "fault"}`), the
  cheapest real case in the repo. R4 and R5 need a run long enough to be interrupted; the wedge is
  used for them too, interrupted after a fixed number of history rows.
- Path: the real worker (`worker.run_worker.main`, in process or as a subprocess) against a local
  queue folder made by `worker.make_case.make`, exactly as the Colab worker sees the Drive folder.
  R6 and R7 bypass the gates on purpose and call `worker.run_case.run` on an edited case folder.
- Harness: `analysis/real_faults.py`. One function per fault. Every fault writes its run folder
  (log, history, error.json or result.json, flags) under `runs/faults/2026-11-03/<fault>/` and one row
  to `docs/faults/real_fault_matrix.md` (fault, injected how, caught by, what the user sees,
  observed). Large files are gzipped.

## Faults

| Id | Injected how | Expected (to be checked, not assumed) |
|---|---|---|
| R0 | none: the clean control case | 2-done, result.json with metrics; gives the reference metrics and the run time |
| R1 | a bad template edit seen by both staging and the worker (CFL_NUMBER 1e4, CFL_ADAPT NO), so the hashes agree and the job is accepted | SU2 diverges; worker flags 2-failed with reason nan or nonzero_exit and keeps the history |
| R2 | SIGKILL sent to the SU2 process only, mid-run (as an out-of-memory kill would) | 2-failed, reason nonzero_exit, exit code -9, partial history kept |
| R3 | worker timeout 10 s | 2-failed, reason timeout; no SU2 process left alive afterwards |
| R4 | runtime restart: worker and SU2 both killed mid-run; worker restarted with --stale-minutes 0 | job re-run once; metrics equal R0 |
| R5 | worker killed alone (SU2 left running, as when the worker process dies but the solver does not); worker restarted with --stale-minutes 0 while the old SU2 still runs | unknown: the question is whether two SU2 processes write in the same folder |
| R6 | gate F4 bypassed: an unknown key (BOGUS_SU2_KEY= 1) added to case.cfg, then run | SU2's own reaction (message, exit code), compared with what gate F4 says before staging |
| R7 | gate F3 bypassed: one mesh element's node order reversed in mesh.su2, then run | SU2's own reaction, whatever it is |
| R8 | gate F9 with the real worker: job file with an edited mesh_fingerprint | mesh_mismatch, SU2 never started (no log.txt) |

Agent part: the two input faults F1 (theta2 = 20) and F2 (12/14) are also sent through the live MCP
tool `validate_config` from Claude Code, and the tool replies are saved as a transcript in
`docs/transcripts/`.

## Acceptance

Every fault R0 to R8 is run once and its row is generated from its run folder, not typed. Each row
states what caught the fault or that nothing did. A fault whose outcome is unsafe (for example a
corrupted record, or two solvers in one folder) is reported with its root cause; a guard, if added,
comes with a test and its own commit, and the fault is then run again and both outcomes are kept.

## Addendum (2026-11-03, after the first run of R0 to R8)

Added after seeing results, and labeled so in the matrix and in `docs/faults/README.md`:

- R7b: R7 showed that SU2 repairs a reversed element; R7b moves one node past the opposite corner of
  its cell, a tangle that re-ordering cannot fix.
- R9: R1 did not diverge, and staging a 12/14 job with `worker.make_case.make` showed that the worker
  does not re-check the physics gates. R9 sends that job to the real worker (the real divergence of
  `runs/dev/2026-11-01_inlet_grid_study_ef03/12_14_medium`).
- Guards from R5 and R9 (worker stops leftover solvers in the run folder; worker re-checks the gates),
  each with a test, then R5g and R9g repeat the two faults. The first outcomes are kept.


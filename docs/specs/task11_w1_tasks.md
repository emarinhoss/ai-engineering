# Task 11, experiment W1: work breakdown (DRAFT 2026-11-12, not approved)

Companion to the W1 block of `docs/specs/task11_fno_exploration.md` (the rule; read it first). This
file turns the rule into tasks, names what closes each one, and gives the order. Nothing here
changes the rule. Nothing here has run. No task starts before Éder approves the rule.

## Roles (CLAUDE.md allocation)

| Model | Does |
|---|---|
| **Fable** | The rule, the tests of the judging code, the review of every diff, the verdict text |
| **Sonnet** | The modules and scripts below, from this file and the rule |
| **Haiku** | Docstrings, the result table, one figure, lint |

Rules for every task: the test named under "Closes" passes and nothing else breaks; `ruff check .`
is clean; every run writes a record under `runs/` with params, commit and timing; agents do not
commit.

## Order and gates

```
W1.1 start-file writer ──► W1.2 control run (GATE A) ──┐
W1.3 campaign staging ──► W1.4 campaign runs ──► W1.5 field store ──► W1.6 model, frozen (GATE B)
W1.7 judging code and tests (no SU2)                                          │
W1.8 timed batch staging ◄────────────────────────────────────────────────────┘
W1.9 timed runs ──► W1.10 analysis, verdict, record
```

- **Gate A:** the control of the rule. If it fails, the writer is wrong and nothing else is staged.
- **Gate B:** at least 90 training fields, and the fitted model committed with its hash, before any
  timed run is staged.

W1.1, W1.3 and W1.7 need no SU2 and can be written at once. W1.4 can start as soon as W1.3 is
reviewed; it does not wait for Gate A, because cold runs with `save_restart` use only recorded code.

## Tasks

### W1.1 Start-file writer (Sonnet)

`worker/startfile.py`, about 40 lines.

- `read_restart(path) -> (header, ids, xy, fields)`: reads SU2's `restart_flow.csv`.
- `scale(fields, u_inf, rho, nu)` and `unscale(...)`: velocity by U∞, pressure by ρU∞², ν̃ by ν.
- `write_solution(path, header, ids, xy, fields)`: writes `solution_flow.csv` with the donor's own
  header and column order, one row per node, ν̃ clipped at zero.
- The worker gets one new optional param, `start_file`, a file in the queue's `starts/` folder that
  is copied to `solution_flow.csv`. It uses the restart config lines that `restart_from` already
  uses. A case without it renders the same `case.cfg` as today.

Closes: `tests/test_startfile.py`. Read then write returns the same text for a recorded E0 restart
file; scale then unscale returns the fields; a row-count mismatch against the mesh raises; the
rendered config of a case without `start_file` is byte-identical to the recorded one.

### W1.2 Control run, Gate A (Fable reviews)

Two runs of pool design 1, coarse, 6 deg, tag `w1_control`: one with `restart_from` the E0 case, one
with `start_file` made by W1.1 from the same restart file.

Closes: both give the E0 cold cl and cd within that run's recorded drift. The iteration counts are
recorded as the least a restart can take here. Record: `runs/w1_control/`.

### W1.3 Campaign staging (Sonnet)

`designs/make_w1_field.py`, after the pattern of `designs/make_s2r.py`. The 30 pool designs other
than 1 and 4, at −2, 2, 6 and 10 deg, coarse, `save_restart`, tag `w1_field`, budget 6,000. Also the
three design 4 references (tag `w1_ref`, the S1/S2 reference settings). Writes
`designs/w1_field_cases.csv` and one batch file.

Closes: a test that the csv has 120 field rows and 3 reference rows, that no row is design 1 or 4
except the references, and that every section equals its `pool_af` record.

### W1.4 Campaign runs

Two Colab runtimes, two jobs each (timing does not matter here). Fetch and ingest to
`runs/w1_field/` and `runs/w1_ref/`.

Closes: every job is done or failed with a recorded reason; the three references are checked with
`reference_valid`; the counts are written in the note.

### W1.5 Field store (Sonnet)

`analysis/w1_fields.py`: for each `w1_field` run that exited 0 and stopped on the Cauchy rule, read
its restart file with W1.1, check the node count is the same for all, scale by its free stream, and
write one array file `runs/w1_fields/<date>/fields.npz` (inputs, scaled fields, case ids) with its
sha256. Restart files stay on Drive; the array file is committed only if it is small enough for the
repo, otherwise its hash and Drive path are recorded.

Closes: a test on three small synthetic restart files; the real count of training fields is printed
and compared with the 90 of Gate B.

### W1.6 The model, frozen, Gate B (Sonnet writes, Fable reviews)

`surrogate/field_pca_gp.py`, about 50 lines, on `surrogate/gp.py`: principal components of the
stacked scaled fields, one GP per component over (camber, thickness, log Reynolds, angle).
`analysis/w1_fit.py` runs leave-one-design-out on the training set for the component counts named in
its header, picks the one with the least mean field error, fits on all training fields, and writes
`runs/w1_model/<date>/` (model file, settings, leave-one-out errors, sha256).

Closes: a test that the model reproduces a synthetic field family that has two components; the
leave-one-design-out table is in the record; the model hash is written into the W1 block of the note
and committed. After this commit the model does not change.

### W1.7 Judging code and its tests (Fable writes the tests first, Sonnet the code)

`analysis/w1_warmstart.py`, after `analysis/s2r_numerics.py`, reusing `clean`, `distance`, `load`
and `reference_valid`. `judge_start(cold, warm, ref)` per case and start; `judge(...)` for the two
verdicts and the "does the learning add anything" result; the one-worker check.

Closes: `tests/test_w1_warmstart.py`, one test per condition of the rule: an exhausted run fails
condition 1; a 2.1 % miss fails condition 2 and a 1.9 % miss does not; a 25 % saving fails; a saving
of 40 % with 40 % spread fails; two workers void the timing; a learned start 5 points better than
the nearest case is "no better"; fewer than five valid references gives "not evaluated".

### W1.8 Timed batch staging (Sonnet)

`designs/make_w1.py`: for each of the seven cases, find the nearest training case (scaled inputs),
write its start file and the learned start file with W1.1 and W1.6, record the preparation time of
each, and stage the six runs in the order cold, nearest, learned, learned, nearest, cold with a
second between stagings. Writes `designs/w1_cases.csv` (with the donor case id and both file
hashes) and one batch file.

Closes: a test of the order and tags; a check on Drive that the queue holds exactly the 42 jobs and
that the batch file hash matches the local one.

### W1.9 Timed runs

One runtime, one worker, `--shard 0/1`. Poll, fetch and ingest to `runs/w1_*`.

Closes: 42 records, one `worker_id`.

### W1.10 Analysis, verdict and record (Fable; Haiku for the table and figure)

`python -m analysis.w1_warmstart --out runs/w1_analysis/<date>`. The result block goes into the note
exactly as the rule gives it, for each start, with the reported-not-judged items. One figure:
iterations and wall time per case for the three starts. Runtimes stopped; credits before and after
written down.

Closes: the result block committed; `main` fast-forwarded.

## Cost and time (estimates from the rule, not measured)

| Part | Solver time | Elapsed |
|---|---|---|
| Code (W1.1, W1.3, W1.5 to W1.8) | none | about half a day |
| Control (W1.2) | under 1 hour | under 1 hour |
| Campaign and references (W1.4) | about 20 hours | 5 to 7 hours on two runtimes |
| Timed runs (W1.9) | at most 7 hours | at most 7 hours on one runtime |

About 5 compute units. About a day of elapsed time if nothing fails, so the verdict is unlikely
before the talk on Friday 13 November. What can be shown on Friday without a result: the rule, the
E0 numbers that motivate it, and the published range for learned warm starts, said as published and
not as ours.

## What is deliberately left out

- **A neural operator.** One learned model enters the test. A 2D operator on the C-mesh is new code
  that needs its own explanation; it can be a fourth start if Éder names it before approval.
- **The medium mesh.** E0's coarse-to-medium start already saved about 80 % of the iterations; a
  learned start for the medium mesh is a different test.
- **14 deg.** Outside the tested range. The 8 deg reference of S2R (design 1) did not settle, so 8 deg is not a test angle either.

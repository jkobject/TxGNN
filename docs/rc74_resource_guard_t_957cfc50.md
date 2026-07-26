# Generation-37 rc74 resource-guard correction (`t_957cfc50`)

Status: local correction, review-required. No writer relaunch, VM/GCP/GCS/LaminDB access, canonical write, or product delta was performed.

## Evidence boundary

The failed payload is the immutable local artifact
`artifacts/cache/t_b257f671/rearm-runtime/remote_payload.py`, SHA-256
`9a964004ec6730452d252645104e424b37e9a143f2df506ebbc3180a4a6bbb38`.
Its terminal report is
`artifacts/staged/t_b257f671/fail-closed-rearm-report.json`. The last recovered
preflight heartbeat recorded 9,730,965,504 cumulative SQLite read bytes and
zero durable product rows/windows. The available evidence does not identify
which threshold triggered, so this correction does not reconstruct or claim
one.

## Diagnosis

The generation-37 heartbeat thread measured four operands sequentially:

- process RSS, with termination when `rss_bytes > 8 GiB`;
- `/proc/meminfo` availability, with termination when
  `MemAvailable_bytes < 6 GiB`;
- root filesystem free bytes, with termination when `root_free_bytes < 50 GiB`;
- task-directory size, with termination when `task_growth_bytes > 20 GiB`.

It then evaluated the four predicates in one combined boolean and called
`os._exit(74)`. Equality was intentionally safe for all four thresholds.
Although a generic local product heartbeat was written immediately before the
combined test, it neither named the triggered predicate(s) nor bound the raw
values to an intended exit code. During preflight the GCS heartbeat client was
not initialized, and the task's remote probe retrieved only
`lifecycle-heartbeat.json`. Consequently the abrupt exit left the recovered
handoff with an attributable exit class (`74`) but no attributable operand.

The measurements were also not simultaneous: four probes ran in sequence and
task-directory traversal could overlap SQLite I/O. The old payload recorded no
measurement-window boundary. This is a measurement ambiguity, not evidence
that any particular operand fired.

## Correction

`manage_db/fail_closed_resource_guard.py` provides a reusable guard contract:

1. `ResourceSnapshot` binds all four observed byte values to an explicit
   measurement start and finish time, making the sampling window visible.
2. `evaluate_resource_guard` records every observed value, comparison
   operator, named threshold, threshold value, and triggered result. It also
   records decision timestamp, phase, task identity, full lifecycle identity,
   all triggered predicates, and intended exit code.
3. `enforce_resource_guard` atomically persists a dedicated decision record
   before invoking exit `74`.
4. Persistence uses file fsync, atomic rename, and parent-directory fsync.
5. Any persistence exception invokes distinct fail-closed exit `75`; it cannot
   be reported as an attributed resource-limit exit.
6. Termination is injected, so tests exercise ordering without killing pytest.

The helper deliberately accepts thresholds from the caller rather than
hard-coding one task's values. A future payload using this correction must pass
the unchanged generation-37 values (8 GiB, 6 GiB, 50 GiB, and 20 GiB). The
immutable failed payload was not edited and no retry is authorized.

## Focused verification

Strict TDD evidence:

- RED: `uv run pytest -q tests/test_fail_closed_resource_guard.py` failed during
  collection with `ModuleNotFoundError: manage_db.fail_closed_resource_guard`.
- GREEN: the same command passed all 9 tests.

The focused tests cover every guard independently, exact equality at all four
boundaries, multiple simultaneous triggers, complete identity/operand schema,
persistence-before-exit ordering, distinct persistence-failure exit, and the
no-trigger path.

Focused lint and compilation also pass:

- `uv run python -m py_compile manage_db/fail_closed_resource_guard.py tests/test_fail_closed_resource_guard.py`;
- `uvx ruff check manage_db/fail_closed_resource_guard.py tests/test_fail_closed_resource_guard.py`.

The unmodified project-wide suite is not green on this checkout. A plain
`uv run pytest -q` stops at collection because the optional `torch` dependency
is absent. Re-running without that collection target produced 459 passes,
7 skips, and 15 failures in pre-existing embedding/notebook/watchdog tests;
none imports or exercises this new guard module. No unrelated failures were
changed under this bounded card.

The existing 20-minute no-I/O-progress limit and 4-hour absolute quick-check
ceiling live in the immutable task payload and were not relaxed or replaced by
this local correction.

## Residual risk

The failed payload was assembled as a task-local artifact rather than from a
tracked project generator. There is therefore no existing tracked call site to
patch without mutating prior evidence. Independent review should require the
next separately authorized payload generator/call site to use this helper and
to preserve the exact threshold and quick-check ceiling values before any
future execution is considered. This task itself authorizes no execution.

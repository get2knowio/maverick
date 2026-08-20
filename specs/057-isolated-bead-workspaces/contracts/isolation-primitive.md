# Contract: The Isolation Primitive

**Feature**: 057-isolated-bead-workspaces
**Module**: `src/maverick/workspace/`
**Consumers**: `maverick fly` (isolated mode), `maverick spec` (headless chain)

This is the internal API contract. It is a **library** contract, not a CLI or
wire contract — the audience is the two workflows that consume it and the
tests that hold it in place. SC-008 requires exactly one implementation of
provisioning, fold-back, and teardown; this is it.

---

## Public surface

```python
from maverick.workspace import (
    CheckoutPath,          # NewType('CheckoutPath', Path)
    FoldBackOutcome,       # enum: APPLIED | EMPTY | CONFLICT | DISCARDED | REJECTED
    FoldBackResult,
    IsolationBoundaryError,
    IsolationLease,
    IsolationPolicy,
    IsolationSession,
    UnitOfWork,
    assert_checkout,       # runtime boundary guard (FR-021)
)
```

### `IsolationSession`

```python
class IsolationSession:
    def __init__(
        self,
        *,
        checkout: CheckoutPath,
        policy: IsolationPolicy,
        jj_client: JjClient,
        run_id: str,
        now: Callable[[], datetime],
        home: Path | None = None,      # tests only
    ) -> None: ...

    async def __aenter__(self) -> IsolationSession: ...   # acquires the run lock
    async def __aexit__(self, *exc) -> None: ...          # releases it, sweeps

    @asynccontextmanager
    async def lease(self, unit: UnitOfWork) -> AsyncIterator[IsolationLease]: ...

    async def fold_back(self, lease: IsolationLease) -> FoldBackResult: ...
    async def undo(self, lease: IsolationLease, result: FoldBackResult) -> None: ...
    async def sweep(self, *, keep: Container[str]) -> None: ...
```

---

## Behavioral contract

### C1 — Session entry acquires exclusivity (FR-048)

`__aenter__` acquires `<checkout>/.maverick/runs/isolation.lock`. A live holder
raises `IsolationLockedError` naming the holding pid. A malformed lockfile or
one naming a dead pid is reclaimed. `__aexit__` releases it.

### C2 — Session entry refuses on a stale journal (FR-049)

If `<checkout>/.maverick/runs/isolation-journal.json` exists on entry,
`__aenter__` raises `IsolationRecoveryRequiredError` carrying the record's
`unit_key`, `operation`, `workspace_path`, and `restore_operation_id`. The
session performs **no** automatic rollback and **no** inference from the
checkout's contents.

### C3 — `lease()` provisions before the agent runs (FR-002, FR-003, FR-004)

- Creates `root/<project>/<workflow>/<key>/` via
  `jj workspace add -r @ <dir>`, so the workspace's working-copy commit is a
  child of the checkout's `@` and **uncommitted checkout work is visible**.
- `workspace_forget(<name>)` runs first, unconditionally — including when the
  directory is already absent — then `rmtree`, unless `policy.reuse` and the
  directory exists.
- Copies `unit.seed_inputs` into the workspace.
- Two units never share a workspace: the path is keyed by `(workflow, key)`.
- Provisioning failure raises `IsolationProvisioningError` **before** any agent
  runs, and its message distinguishes "could not isolate" from "the work
  failed".

### C4 — `fold_back()` snapshots the workspace first (R3, FR-005)

**Mandatory ordering, and the single most failure-prone step:**

1. Force a working-copy snapshot *inside the workspace* (a jj command bound to
   `lease.workspace_path`). Skipping this yields a successful, **empty**
   fold-back with no error.
2. Capture `snapshot_operation()` in the checkout → `restore_operation_id`.
3. Write the `ApplicationRecord` (`operation="fold-back"`).
4. `jj squash --from '<workspace_name>@' --into @ <fold_scope> <fold_exclusions>`
   from the checkout.
5. Query `conflicts()`. Non-empty → restore the operation, return
   `outcome=CONFLICT` with `conflicting_paths` populated and no partial delta
   left behind.
6. Clear the `ApplicationRecord`.

Returns `EMPTY` (a success) when the delta was genuinely empty, `APPLIED`
otherwise, with `applied_paths` filled from the checkout's post-squash status.

### C5 — `undo()` restores byte-identically (FR-014, FR-017, FR-018)

Writes an `ApplicationRecord` with `operation="undo"`, calls
`restore_operation(result.restore_operation_id)`, clears the record.

Postconditions:
- The checkout is byte-identical to its pre-fold-back state, **including
  unrelated uncommitted work the user had there**.
- The workspace still holds the rejected delta, so a fix round resumes in place.
- On failure: the record is **left in place**, `IsolationUndoFailedError` is
  raised naming what the checkout now contains and how to recover, and the
  caller must halt the run. It is never swallowed, never silently retried, and
  no further unit may begin.

### C6 — The boundary is enforced (FR-020–023)

- `assert_checkout(path)` raises `IsolationBoundaryError` when `path` resolves
  inside any live workspace root. Every bd, ledger, and commit-graph entry
  point calls it.
- `CheckoutPath` is a distinct `NewType`, so passing a workspace path where a
  checkout is required is a mypy error under strict mode.
- An agent executing under a lease receives only `lease.workspace_path`.

### C7 — Teardown and sweep (FR-024–029)

- Success → `workspace_forget` then `rmtree`. Forget **always** precedes
  removal: reversing them leaves jj tracking the name, blocking the next
  `workspace_add` and stranding an anonymous head in the user's `jj log`.
- Failure → torn down, unless `policy.retain_on_failure`.
- Teardown is best-effort: every error is logged and swallowed. A completed unit
  is never reported as failed because cleanup could not finish.
- `sweep(keep=...)` collects this checkout's workspaces under this workflow
  only. Per-entry isolated — one undeletable workspace cannot strand the rest,
  and no sweep failure fails the run.

### C8 — Overhead budget (FR-050)

Provision + fold-back + teardown ≤ 5 s per unit, asserted by an integration test
against this repository. `FoldBackResult.duration_seconds` carries the
measurement.

---

## Contract tests

Each maps to a requirement, and each is written before the implementation.

| # | Test | Requirement |
| --- | --- | --- |
| T1 | Agent writes in the workspace are invisible in the checkout until fold-back | FR-007, SC-002 |
| T2 | Workspace sees the checkout's uncommitted work at provision time | FR-003 |
| T3 | Create + modify + delete all fold back in one application | FR-005 |
| T4 | **Fold-back without the workspace snapshot returns EMPTY** — the regression test for R3 | FR-005 |
| T5 | Genuinely empty delta returns `EMPTY`, not an error | FR-006 |
| T6 | Ignored paths (`.beads/`, `*.jsonl`, `.venv/`) never fold back | FR-010 |
| T7 | `.maverick/**` never folds back even when modified in the workspace | FR-011 |
| T8 | Divergent edit to the same file → `CONFLICT`, paths named, checkout unchanged | FR-008, SC-005 |
| T9 | Undo restores the checkout byte-identically, unrelated uncommitted work included | FR-014, SC-003 |
| T10 | After undo, the workspace still holds the rejected delta | FR-017 |
| T11 | Undo failure raises, leaves the journal in place, and halts | FR-018 |
| T12 | Second session in the same checkout refuses, naming the pid | FR-048 |
| T13 | Stale journal on entry refuses with recovery detail and no rollback | FR-049 |
| T14 | bd/ledger/commit call with a workspace path raises `IsolationBoundaryError` | FR-021 |
| T15 | Every bd/ledger/jj call site takes its directory from the checkout | FR-020, SC-006 |
| T16 | Forget precedes removal; no stray head in `jj log` after teardown | FR-029 |
| T17 | Sweep leaves only `keep` entries; one undeletable entry does not strand others | FR-025–027 |
| T18 | Overhead stays within budget | FR-050, SC-012 |

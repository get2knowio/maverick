# Phase 1 Data Model: Isolated Bead Workspaces

**Feature**: 057-isolated-bead-workspaces | **Date**: 2026-08-20

All types are frozen dataclasses with `to_dict()` (Guardrail X.3 — no ad-hoc
`dict[str, Any]` on a public surface). Persisted types carry `schema_version`.

---

## `IsolationPolicy`

How a consumer wants isolation to behave. Constructed once per run and reused
per unit; the only place fly and the spec chain genuinely differ.

| Field | Type | Notes |
| --- | --- | --- |
| `workflow` | `str` | Path segment and log field: `"fly"`, `"spec-chain"`. |
| `root` | `Path` | Workspace root. From `WorkspaceConfig.root`; `~/.maverick/workspaces` by default. |
| `reuse` | `bool` | Reuse an existing workspace for the same key instead of recreating (chain: yes; fly: no). |
| `retain_on_failure` | `bool` | Keep the workspace when the unit fails — it is the only copy of the partial output (chain: yes; fly: no). |
| `fold_scope` | `tuple[str, ...]` | jj filesets bounding what may fold back. Empty means "everything not excluded". The chain passes `("specs/<feature-dir>",)`. |
| `fold_exclusions` | `tuple[str, ...]` | Always applied, always includes `~.maverick` and the protected set (R11). |

**Validation**: `workflow` must be a non-empty path-safe slug; `root` must be
absolute; a `fold_scope` entry may not escape the workspace root (the same
traversal guard `spec_chain/workflow.py` already applies to feature slugs).

---

## `UnitOfWork`

The smallest thing isolated and folded back as one — a bead in fly, a chain step
in the spec chain. Not persisted; it exists for the duration of one lease.

| Field | Type | Notes |
| --- | --- | --- |
| `key` | `str` | Workspace identity within the workflow. Bead id / feature slug. Path-safe. |
| `label` | `str` | Human-readable, for progress output. |
| `seed_inputs` | `tuple[Path, ...]` | Files copied in that are absent from committed history (FR-004) — e.g. the chain's PRD. |

---

## `IsolationLease`

A live, provisioned workspace. Yielded by `IsolationSession.lease()` and invalid
after that context exits.

| Field | Type | Notes |
| --- | --- | --- |
| `unit` | `UnitOfWork` | The unit this backs. |
| `workspace_path` | `Path` | Where the agent works. |
| `workspace_name` | `str` | jj workspace name (directory basename) — the `<name>@` revset the fold-back reads. |
| `checkout` | `CheckoutPath` | `NewType('CheckoutPath', Path)`. Distinct type so a workspace path cannot be passed where a checkout is required (R9, FR-022). |
| `created_at` | `datetime` | Injected, never `datetime.now()` inside the primitive — the clock seam 054 established. |

**State transitions**:

```
(none) --provision--> PROVISIONED --fold_back--> FOLDED --commit(consumer)--> (teardown)
                           |                        |
                           |                        +--undo--> PROVISIONED   (delta intact, R5)
                           |
                           +--teardown--> (none)      [failure, retain_on_failure=False]
                           +--retained--> (on disk)   [failure, retain_on_failure=True]
```

`FOLDED` is the only state in which unverified work sits in the checkout. No
other unit may enter it (FR-015), and the journal (below) is non-empty for its
entire duration.

---

## `FoldBackResult`

The typed outcome FR-009 requires — success, discard, conflict, and verification
rejection must be distinguishable, and `applied_paths` must be reported.

| Field | Type | Notes |
| --- | --- | --- |
| `outcome` | `FoldBackOutcome` | `APPLIED` / `EMPTY` / `CONFLICT` / `DISCARDED` / `REJECTED` |
| `applied_paths` | `tuple[str, ...]` | Repo-relative posix paths written to the checkout. |
| `conflicting_paths` | `tuple[str, ...]` | Populated only on `CONFLICT`; never empty when it is (SC-005). |
| `restore_operation_id` | `str` | The jj operation captured before the application — the undo handle. |
| `diagnostic` | `str` | Human-readable; names conflicting paths on `CONFLICT`. |
| `duration_seconds` | `float` | Feeds the FR-050 budget assertion. |

`EMPTY` is a **success** (FR-006's empty-delta case), separate from `APPLIED` so
the R3 silent-empty-fold-back failure is visible in logs rather than looking
like an ordinary no-op.

`REJECTED` is set by the consumer after environment-level checks fail and the
undo completes — it is what FR-019 requires be distinguishable from `CONFLICT`
(fold-back mechanics) and `DISCARDED` (agent failure).

---

## `ApplicationRecord` — persisted

The in-progress marker (FR-049). Written before a fold-back or an undo begins,
cleared once it completes.

**Location**: `<cwd>/.maverick/runs/isolation-journal.json` (gitignored —
`/.maverick/runs` already is). Atomic write (temp + rename), same as
`notify/state.py`.

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `int` | `1`. |
| `run_id` | `str` | Owning run. |
| `workflow` | `str` | `"fly"` / `"spec-chain"`. |
| `unit_key` | `str` | Which unit was mid-application. |
| `operation` | `"fold-back" \| "undo"` | Which direction was in flight. |
| `restore_operation_id` | `str` | The jj operation to rewind to — the recovery handle handed to the user. |
| `workspace_path` | `str` | Where the delta still lives. |
| `started_at` | `datetime` | Injected. |

**Invariant**: at most one record exists at a time — a direct consequence of
FR-015 and FR-048. A run that finds one on startup refuses (FR-049) and never
rolls back automatically.

---

## `IsolationLock` — persisted

**Location**: `<cwd>/.maverick/runs/isolation.lock`, pid-stamped plain text,
identical in shape and reclamation rules to
`workflows/reconcile/state.py`'s lock (R8).

Held for the whole isolated run, not per unit. A live holder is a hard refusal
naming the pid (FR-048); a malformed file or a dead pid is reclaimed.

---

## `WorkspaceRegistry` — derived, not stored

Which workspaces exist and which are collectable. Deliberately **not** a
persisted file: FR-028 says correctness must not depend on any workspace
surviving, and a registry file is precisely the thing that goes stale against
the filesystem.

Derived from two sources at sweep time, exactly as `sweep_stale_workspaces` does
today:

- the on-disk directory listing under `root/<project>/<workflow>/`
- a `keep` set the caller supplies (fly: the live bead; chain:
  `state.resumable_features(cwd)` plus the current feature)

---

## Config: `WorkspaceConfig` (repurposed)

`config.py:365`. Fields marked *removed* are dead today — nothing reads them
(R10).

| Field | Type | Default | Status |
| --- | --- | --- | --- |
| `root` | `Path` | `~/.maverick/workspaces` | kept |
| `enabled` | `bool` | `False` | **new** — isolated mode opt-in (FR-030, SC-011) |
| `setup` | `str \| None` | `None` | *removed* — clone-era bootstrap hook |
| `teardown` | `str \| None` | `None` | *removed* |
| `env_files` | `list[str]` | `[".env"]` | *removed* — superseded by `UnitOfWork.seed_inputs` |
| `reuse` | `bool` | `True` | *removed* — this draft's original plan to keep it turned out wrong at implementation time: `IsolationPolicy.reuse` (above) is a correctness-critical value each consumer sets programmatically (chain: always `True`; fly: always `False`, load-bearing for G1-G9), and neither ever read it from `WorkspaceConfig`. Left in config it was dead, and a user setting it for fly would have been actively dangerous (a reused, possibly-dirty workspace breaks G2/G3) — removed rather than wired through. |

---

## Events and log fields

Every lifecycle transition logs with `unit_key`, `workflow`, and
`workspace_path` (FR-051). Fold-backs, undos, conflicts, and rejections also
emit a `ProgressEvent` so they appear in the run's user-visible output; the
progress surface is otherwise unchanged (spec Assumptions).

| Log event | Emitted when |
| --- | --- |
| `isolation_provisioned` | workspace created or reused |
| `isolation_seeded` | `seed_inputs` copied |
| `isolation_fold_back_started` / `_completed` | around the squash; `_completed` carries `outcome` and `duration_seconds` |
| `isolation_conflict` | `conflicts()` non-empty; carries `conflicting_paths` |
| `isolation_undo_started` / `_completed` | around `op restore` |
| `isolation_undo_failed` | FR-018 — accompanied by a hard halt, never swallowed |
| `isolation_torn_down` / `isolation_retained` | end of lease |
| `isolation_swept` | per collected entry |
| `isolation_journal_stale` | uncleared record found at startup (FR-049) |
| `isolation_lock_held` | another run holds the lock (FR-048) |

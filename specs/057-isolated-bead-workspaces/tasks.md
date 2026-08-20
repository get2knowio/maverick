---

description: "Task list for 057-isolated-bead-workspaces"
---

# Tasks: Isolated Bead Workspaces

**Input**: Design documents from `/specs/057-isolated-bead-workspaces/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included and mandatory. Constitution Principle V (Test-First,
Anti-Deferral) requires TDD red-green-refactor for every public class and
function; Guardrail 4 requires resilience features be real rather than stubs.
The undo path in particular gets direct coverage — it is on the normal failure
path here, not an exceptional one.

**Organization**: Grouped by user story. Unlike a typical feature, these stories
are **layered rather than independent** — US2 needs US1's primitive, US3 needs
both. That is stated honestly in Dependencies below rather than papered over.
US4, US5, and US7 are genuinely independent of each other once US1 lands.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Exact file paths are included in every task

## Path Conventions

Single project. Source at `src/maverick/`, tests at `tests/`. Integration tests
that touch jj need a real `jj` binary and a temporary colocated repository —
this repository itself is **not** jj-colocated, so fixtures must create their
own.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and the test fixture everything else depends on

- [X] T001 Create the primitive package skeleton at `src/maverick/workspace/` — add `models.py`, `session.py`, `foldback.py`, `lifecycle.py`, `journal.py`, `cwd_scope.py` as empty modules with docstrings, and leave `spec_chain.py` untouched for now
- [X] T002 Create test package directories `tests/unit/workspace/` and `tests/integration/workspace/` with `__init__.py` and a directory-scoped `conftest.py` in each
- [X] T003 Add a `colocated_repo` pytest fixture in `tests/integration/workspace/conftest.py` that builds a temporary git repo, runs `jj git init --colocate`, seeds tracked files plus a gitignored path, and yields a `JjClient` bound to it
- [X] T004 [P] Add an `isolation_home` fixture in `tests/integration/workspace/conftest.py` that supplies a temporary `home=` override so no test writes to the developer's real `~/.maverick/workspaces`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: jj wrapper extensions, typed models, and the cwd seam. Nothing in
any user story can be built until these land.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### jj wrapper extensions (Guardrail X.5 — extend the canonical wrapper, never add a second one)

- [X] T005 Add a failing test in `tests/unit/jj/test_client_squash.py` asserting `JjClient.squash(from_=..., into=..., filesets=...)` emits `jj squash --from <rev> --into <rev> <filesets>` and that `from_` and `revision` are mutually exclusive (jj rejects `-r` with `--from`)
- [X] T006 Extend `JjClient.squash` in `src/maverick/jj/client.py` with `from_: str | None` and `filesets: tuple[str, ...]` parameters to make T005 pass
- [X] T007 [P] Add a failing test in `tests/unit/jj/test_client_workspace.py` asserting `JjClient.workspace_add(target, revision="@")` emits `jj workspace add -r @ <target>`
- [X] T008 Extend `JjClient.workspace_add` in `src/maverick/jj/client.py` with a `revision: str | None` parameter to make T007 pass
- [X] T009 [P] Add `JjClient.snapshot_working_copy()` to `src/maverick/jj/client.py` — runs a cheap status-only jj command bound to this client's cwd purely to force jj's working-copy snapshot, with a docstring naming research.md R3 as the reason it exists
- [X] T010 Add typed actions `jj_fold_back` and `jj_workspace_snapshot` to `src/maverick/library/actions/jj.py` returning frozen dataclasses, following the existing `jj_snapshot_operation` shape

### Typed models and exceptions

- [X] T011 [P] Define `CheckoutPath` (`NewType`), `IsolationPolicy`, `UnitOfWork`, `IsolationLease`, `FoldBackOutcome`, and `FoldBackResult` as frozen dataclasses with `to_dict()` in `src/maverick/workspace/models.py` per [data-model.md](./data-model.md)
- [X] T012 [P] Add `IsolationError` and its subclasses `IsolationProvisioningError`, `IsolationBoundaryError`, `IsolationLockedError`, `IsolationRecoveryRequiredError`, and `IsolationUndoFailedError` to `src/maverick/exceptions/`, rooted at `MaverickError`
- [X] T013 [P] Add unit tests in `tests/unit/workspace/test_models.py` covering `to_dict()` round-trips, `IsolationPolicy` validation (absolute root, path-safe workflow slug, no `fold_scope` entry escaping the workspace root)

### The cwd seam and config

- [X] T014 Move the `os.chdir` scope and its module-level `asyncio.Lock` out of `src/maverick/agents/spec_chain.py` into `src/maverick/workspace/cwd_scope.py` as a reusable async context manager, documenting the airframe `ClaudeOptions` gap (research.md R1) and the exit criterion
- [X] T015 Update `src/maverick/agents/spec_chain.py` to call `workspace/cwd_scope.py`, keeping its behavior byte-identical, and add `tests/unit/workspace/test_cwd_scope.py` asserting the working directory is restored even when the body raises
- [X] T016 Repurpose `WorkspaceConfig` in `src/maverick/config.py` — add `enabled: bool = False`, keep `root` and `reuse`, remove the dead `setup`, `teardown`, and `env_files` fields (research.md R10 — nothing reads them today). **Correction (US6/polish pass)**: `reuse` was later removed too — neither consumer's `IsolationPolicy` ever read it from config (each hardcodes its own value; fly's is load-bearing for G1-G9), so it was dead exactly like `setup`/`teardown`/`env_files`, just not caught at authoring time. See `data-model.md`'s `WorkspaceConfig` table.
- [X] T017 [P] Add `tests/unit/test_config_workspace.py` asserting `enabled` defaults to `False`, an absent `workspace:` block yields defaults, and a malformed block does not fail config load

**Checkpoint**: jj can squash across workspaces, models are typed, the cwd seam is shared. User story work can begin.

---

## Phase 3: User Story 1 - A workflow runs an agent step in isolation (Priority: P1) 🎯 MVP

**Goal**: A reusable primitive that provisions an isolated copy of the
repository, lets an agent mutate files there, folds the delta into the checkout
as one application on success, and discards everything on failure.

**Independent Test**: Drive `IsolationSession` directly with a stub unit that
writes known files. Assert the checkout is untouched during the agent step,
contains exactly the expected delta after success, and is byte-identical after
a forced failure.

### Tests for User Story 1 ⚠️ Write first, confirm they fail

- [X] T018 [P] [US1] Integration test in `tests/integration/workspace/test_provision.py` — provisioning creates the workspace at `root/<project>/<workflow>/<key>/`, and two units never share a directory (contract T1 prerequisite, FR-002)
- [X] T019 [P] [US1] Integration test in `tests/integration/workspace/test_provision.py` — the workspace sees the checkout's **uncommitted** work at provision time (contract T2, FR-003)
- [X] T020 [P] [US1] Integration test in `tests/integration/workspace/test_provision.py` — `seed_inputs` files absent from committed history are readable inside the workspace (FR-004)
- [X] T021 [P] [US1] Integration test in `tests/integration/workspace/test_foldback.py` — the checkout shows no changes while the unit's agent step is executing (contract T1, FR-007, SC-002)
- [X] T022 [P] [US1] Integration test in `tests/integration/workspace/test_foldback.py` — create, modify, and delete all fold back in one application, and `applied_paths` lists exactly them (contract T3, FR-005, FR-009)
- [X] T023 [P] [US1] Integration test in `tests/integration/workspace/test_foldback.py` — **fold-back without the workspace snapshot returns `EMPTY`**; this is the research.md R3 regression test and must assert the silent-empty failure mode explicitly (contract T4)
- [X] T024 [P] [US1] Integration test in `tests/integration/workspace/test_foldback.py` — a genuinely empty delta returns `EMPTY` as a success with zero applied paths, not an error (contract T5, FR-006)
- [X] T025 [P] [US1] Integration test in `tests/integration/workspace/test_foldback.py` — ignored paths (`.beads/`, `*.jsonl`, a gitignored build dir) never fold back (contract T6, FR-010)
- [X] T026 [P] [US1] Integration test in `tests/integration/workspace/test_foldback.py` — `.maverick/**` never folds back even when modified inside the workspace (contract T7, FR-011)
- [X] T027 [P] [US1] Integration test in `tests/integration/workspace/test_conflict.py` — a divergent edit to the same file yields `CONFLICT` with every conflicting path named and the checkout left unchanged (contract T8, FR-008, SC-005)
- [X] T028 [P] [US1] Integration test in `tests/integration/workspace/test_provision.py` — provisioning failure raises `IsolationProvisioningError` before the agent runs, with a message distinguishing "could not isolate" from "the work failed" (FR-001 edge case)
- [X] T029 [P] [US1] Integration test in `tests/integration/workspace/test_foldback.py` — an agent-step error discards the delta and leaves the checkout byte-identical (FR-006)

### Implementation for User Story 1

- [X] T030 [US1] Implement `provision`, `teardown`, and the path derivation `root/<project>/<workflow>/<key>/` in `src/maverick/workspace/lifecycle.py`, generalizing `workspace/spec_chain.py` and preserving its two load-bearing rules: `workspace_forget` runs before `rmtree` **always**, including when the directory is already gone
- [X] T031 [US1] Implement `seed_inputs` copying in `src/maverick/workspace/lifecycle.py`
- [X] T032 [US1] Implement `fold_back()` in `src/maverick/workspace/foldback.py` following contract C4's mandatory ordering: snapshot the workspace → capture the checkout operation → squash with `fold_scope` and `fold_exclusions` → query `conflicts()` → restore on conflict
- [X] T033 [US1] Implement conflict-path extraction in `src/maverick/workspace/foldback.py` (from `jj resolve --list` / the status warning block), so `conflicting_paths` is never empty when the outcome is `CONFLICT`
- [X] T034 [US1] Handle jj's stale-working-copy error in `src/maverick/workspace/foldback.py` (research.md R5 caveat) rather than letting an opaque `JjError` escape
- [X] T035 [US1] Implement `IsolationSession` with its `lease()` async context manager in `src/maverick/workspace/session.py`, wiring lifecycle and fold-back and injecting `now` rather than calling `datetime.now()` internally
- [X] T036 [US1] Export the public surface from `src/maverick/workspace/__init__.py` exactly as [contracts/isolation-primitive.md](./contracts/isolation-primitive.md) lists it
- [X] T037 [US1] Add structured logging for `isolation_provisioned`, `isolation_seeded`, `isolation_fold_back_started`, `isolation_fold_back_completed`, and `isolation_conflict` in `src/maverick/workspace/lifecycle.py` and `src/maverick/workspace/foldback.py` via `maverick.logging.get_logger`, per [data-model.md](./data-model.md)

**Checkpoint**: The primitive works standalone. Scenario 1 of [quickstart.md](./quickstart.md) passes.

---

## Phase 4: User Story 2 - A unit of work is verified before it is kept (Priority: P2)

**Goal**: Two check placements — artifact-level inside isolation before
fold-back, environment-level against the checkout after it — with undo on
failure, and a hard halt if the undo itself fails.

**Independent Test**: Run a unit whose environment verification is rigged to
fail; assert the checkout is byte-identical afterwards, nothing was committed,
and the failure is attributed to verification rather than to the agent.

**Depends on**: US1 (needs `fold_back` to have something to undo)

### Tests for User Story 2 ⚠️ Write first, confirm they fail

- [X] T038 [P] [US2] Integration test in `tests/integration/workspace/test_undo.py` — undo restores the checkout byte-identically, **including unrelated uncommitted work the user had there before the unit started** (contract T9, FR-014, SC-003)
- [X] T039 [P] [US2] Integration test in `tests/integration/workspace/test_undo.py` — after undo the workspace still holds the rejected delta, so a fix round resumes in place (contract T10, FR-017)
- [X] T040 [P] [US2] Integration test in `tests/integration/workspace/test_undo.py` — an undo failure raises `IsolationUndoFailedError`, leaves the journal record in place, and names both what the checkout contains and how to recover (contract T11, FR-018)
- [X] T041 [P] [US2] Unit test in `tests/unit/workspace/test_journal.py` — the `ApplicationRecord` is written before the application and cleared after, is atomic (temp + rename), and carries `schema_version`
- [X] T042 [P] [US2] Integration test in `tests/integration/workspace/test_journal.py` — a session that finds an uncleared record refuses with `IsolationRecoveryRequiredError` carrying unit, operation, workspace path, and restore operation id, and performs **no** automatic rollback (contract T13, FR-049)
- [X] T043 [P] [US2] Integration test in `tests/integration/workspace/test_lock.py` — a second session in the same checkout refuses with `IsolationLockedError` naming the holding pid; a dead pid or malformed lockfile is reclaimed (contract T12, FR-048)
- [X] T044 [P] [US2] Unit test in `tests/unit/workspace/test_models.py` — `FoldBackOutcome.REJECTED` is distinguishable from `CONFLICT` and `DISCARDED` in the result projection (FR-019)
- [X] T045 [P] [US2] Integration test in `tests/integration/workspace/test_verification.py` — a unit whose **artifact-level** checks fail has its delta discarded without ever reaching the checkout (FR-013, US2 acceptance scenario 1)
- [X] T046 [P] [US2] Integration test in `tests/integration/workspace/test_verification.py` — after an environment-level rejection the **verification output** is available to the fix round alongside the rejected delta, not just the delta (FR-017, US2 acceptance scenario 4)

### Implementation for User Story 2

- [X] T047 [US2] Implement the `ApplicationRecord` read/write/clear cycle in `src/maverick/workspace/journal.py` with atomic writes, mirroring `src/maverick/assumptions/schedule/state.py`'s pattern
- [X] T048 [US2] Implement the pid-stamped advisory lock in `src/maverick/workspace/journal.py`, mirroring `src/maverick/workflows/reconcile/state.py` byte-for-byte — hard refusal on a live holder, reclamation of stale or malformed files (research.md R8)
- [X] T049 [US2] Wire lock acquisition and stale-journal refusal into `IsolationSession.__aenter__`/`__aexit__` in `src/maverick/workspace/session.py` per contract C1 and C2
- [X] T050 [US2] Implement `undo()` in `src/maverick/workspace/session.py` per contract C5 — journal, `restore_operation`, clear; on failure leave the record, raise, and never swallow or silently retry
- [X] T051 [US2] Add the check-placement surface to `src/maverick/workspace/models.py` and `session.py`: artifact-level checks run inside the lease before fold-back, environment-level checks are the caller's responsibility after it, with `REJECTED` set on undo (FR-012, FR-013)
- [X] T052 [US2] Add structured logging for `isolation_undo_started`, `isolation_undo_completed`, `isolation_undo_failed` in `src/maverick/workspace/session.py`, and `isolation_journal_stale`/`isolation_lock_held` in `src/maverick/workspace/journal.py`

**Checkpoint**: Rejection and undo are real, exercised paths. Scenarios 3 and 6 of [quickstart.md](./quickstart.md) pass.

---

## Phase 5: User Story 3 - `maverick fly` runs each bead in isolation (Priority: P3)

**Goal**: An opt-in isolated mode where each bead is implemented, reviewed, and
fixed inside its own workspace, and only complete verified work stays in the
checkout.

**Independent Test**: Run the same beads twice from equivalent starting states —
once normally, once isolated — and compare commit history and file contents.

**Depends on**: US1 and US2

### Tests for User Story 3 ⚠️ Write first, confirm they fail

- [X] T053 [P] [US3] Integration test in `tests/integration/fly/test_isolated_equivalence.py` — isolated and normal runs over the same beads produce identical commit subjects, trailers, ordering, and final file contents (contract F1, SC-001, FR-033)
- [X] T054 [P] [US3] Integration test in `tests/integration/fly/test_isolated_visibility.py` — the checkout polled throughout an isolated run never contains an in-flight bead's changes (contract F2, FR-007, SC-002)
- [X] T055 [P] [US3] Integration test in `tests/integration/fly/test_isolated_default_off.py` — without the flag or config every observable behavior matches today (contract F3, FR-035, SC-011)
- [X] T056 [P] [US3] Integration test in `tests/integration/fly/test_isolated_gate_failure.py` — gate fails → undo → fix in the workspace → refold → gate passes → commit (contract F4)
- [X] T057 [P] [US3] Integration test in `tests/integration/fly/test_isolated_gate_failure.py` — gate fails with fix attempts exhausted → undo → bead abandoned → checkout byte-identical (contract F5, SC-003)
- [X] T058 [P] [US3] Integration test in `tests/integration/fly/test_isolated_gate_failure.py` — undo failure halts the run and starts no further bead (contract F10, FR-018)
- [X] T059 [P] [US3] Integration test in `tests/integration/fly/test_isolated_conflict.py` — a fold-back conflict fails exactly that bead; the next bead proceeds (contract F6, FR-034)
- [X] T060 [P] [US3] Integration test in `tests/integration/fly/test_isolated_ledger.py` — assumptions recorded during an isolated bead land in the **checkout's** ledger and are stamped with the commit's change id (contract F7, FR-020)
- [X] T061 [P] [US3] Integration test in `tests/integration/fly/test_isolated_protection.py` — a protected-path write inside the workspace is blocked and drains to `protection_blocks` (contract F8, FR-036)
- [X] T062 [P] [US3] Unit test in `tests/unit/cli/test_fly_isolated_options.py` — resolution order `--isolated`/`--no-isolated` > `workspace.enabled` > `false`, and each precondition refuses with an actionable message and no silent fallback (contract F9, FR-030, FR-037)
- [X] T063 [P] [US3] Integration test in `tests/integration/fly/test_isolated_no_premature_commit.py` — **zero commits** are produced for a bead that failed any declared check, at every failure point: agent error, artifact check, fold-back conflict, and environment check (FR-016, SC-004)
- [X] T064 [P] [US3] Integration test in `tests/integration/fly/test_isolated_serialization.py` — beads remain strictly serial: at most one workspace is live at a time, and no bead begins while another's unverified delta sits in the checkout (FR-015, FR-031)

### Implementation for User Story 3

- [X] T065 [US3] Add `--isolated` / `--no-isolated` to `src/maverick/cli/commands/fly/_group.py` and resolve them against `workspace.enabled` at the CLI boundary
- [X] T066 [US3] Add the isolated-mode preconditions (`.jj/` present, `jj` available, lock free, journal clear) at the CLI boundary in `src/maverick/cli/commands/fly/_group.py`, refusing with a non-zero exit and never falling back silently
- [X] T067 [US3] Create `src/maverick/workflows/fly_beads/_isolation.py` holding per-bead lease handling and the fold-back/undo action bodies — deliberately **not** in `actions.py`, which is already 1,887 lines, past Principle XI's 1,000-line hard stop; this module is the carve-out that hard stop requires
- [X] T068 [US3] Add the `isolated`, `workspace_path`, `fold_back_result`, `unverified_in_checkout`, and `isolation_halt_reason` state slots to `.with_state(...)` in `src/maverick/workflows/fly_beads/burr_graph.py`, and to the `reads`/`writes` of every consuming action
- [X] T069 [US3] Add `provision_workspace`, `fold_back`, and `undo_fold_back` actions in `src/maverick/workflows/fly_beads/_isolation.py`, keeping `fold_back_result` out of every fixer-feeding slot (Guardrail X.10 corollary)
- [X] T070 [US3] Wire the isolated-mode transitions in `src/maverick/workflows/fly_beads/burr_graph.py` per [contracts/fly-isolated-mode.md](./contracts/fly-isolated-mode.md): `implement → ac_check → spec_check → review → fold_back → gate → commit`, with the gate-failure edge routing through `undo_fold_back` back to a fix round
- [X] T071 [US3] Extract the agent-step invocation (prompt build → cwd scope → runtime call) into a helper in `src/maverick/workflows/fly_beads/_isolation.py`, so the following three tasks change `actions.py` by delegation only — `actions.py` is 1,887 lines and Principle XI forbids adding features to it without carving out a submodule first
- [X] T072 [US3] Point the agent steps (`implement`, `review`, `_run_fix`) at the lease's workspace in `src/maverick/workflows/fly_beads/actions.py` by calling the helper from T071 — **delegation only**, no isolation logic in this file (Principle XI) — leaving the non-isolated path untouched (FR-032)
- [X] T073 [US3] Point `ac_check` and `spec_check` at the workspace in `src/maverick/workflows/fly_beads/actions.py` and `src/maverick/workflows/fly_beads/_verification.py`, threading the workspace path explicitly rather than defaulting (Guardrail X.7) — again delegation only in `actions.py`
- [X] T074 [US3] Keep `gate` bound to the checkout in `src/maverick/workflows/fly_beads/actions.py` and confirm `run_independent_gate` still receives the checkout path in isolated mode
- [X] T075 [US3] Build the `ProtectionPolicy` from the lease's workspace root for isolated agent steps in `src/maverick/squadron/fly.py` (research.md R11), leaving the `BlockCollector` on the squadron so `protection_blocks` drains unchanged
- [X] T076 [US3] Add the protected set to `fold_exclusions` in `src/maverick/workflows/fly_beads/_isolation.py` as the second protection layer
- [X] T077 [US3] Emit `ProgressEvent`s for fold-back, undo, conflict, and verification rejection in `src/maverick/workflows/fly_beads/_isolation.py`, and add labels for the new actions to `FLY_ACTION_LABELS`
- [X] T078 [US3] Halt the run on `IsolationUndoFailedError` in `src/maverick/workflows/fly_beads/workflow.py`, writing `isolation_halt_reason` and printing the recovery instructions through `maverick.cli.console` (FR-018)

**Checkpoint**: Isolated fly works end to end. Scenarios 2, 3, and 6 of [quickstart.md](./quickstart.md) pass.

---

## Phase 6: User Story 4 - The bd-stays-out invariant is structurally enforced (Priority: P4)

**Goal**: A contributor has to actively defeat the boundary, not merely forget a
convention.

**Independent Test**: Attempt a bead, ledger, or commit operation scoped to an
isolated workspace and assert it is refused with a clear error rather than
silently producing wrong state.

**Depends on**: US1 (needs a live workspace to guard against)

### Tests for User Story 4 ⚠️ Write first, confirm they fail

- [X] T079 [P] [US4] Unit test in `tests/unit/workspace/test_boundary.py` — `assert_checkout` raises `IsolationBoundaryError` for a path inside a live workspace root and passes for the checkout (contract T14, FR-021)
- [X] T080 [P] [US4] Test in `tests/unit/workspace/test_boundary.py` — an agent under a lease receives only the workspace path and never the checkout path (FR-023)
- [X] T081 [P] [US4] Repository-wide test in `tests/unit/workspace/test_call_sites.py` — every bd, ledger, and commit-graph call site takes its directory from the checkout, satisfying FR-020 and SC-006 by inspection

### Implementation for User Story 4

- [X] T082 [US4] Implement `assert_checkout` in `src/maverick/workspace/session.py`, resolving candidates against the session's live workspace roots rather than a path-shape heuristic (FR-021, FR-022)
- [X] T083 [US4] Call `assert_checkout` from the bd, ledger, and commit-graph entry points — `src/maverick/library/actions/beads.py`, `src/maverick/assumptions/ledger.py`, and `src/maverick/library/actions/jj.py`'s `jj_commit_bead`
- [X] T084 [US4] Adopt `CheckoutPath` in the entry-point signatures in `src/maverick/library/actions/beads.py`, `src/maverick/assumptions/ledger.py`, and `src/maverick/library/actions/jj.py` so mypy rejects a workspace path at authoring time (research.md R9 layer 1, FR-022), and run `make typecheck` to confirm strict mode catches it

**Checkpoint**: The invariant is enforced by types, at runtime, and by test. Scenario 4 of [quickstart.md](./quickstart.md) passes.

---

## Phase 7: User Story 5 - Isolation never accumulates garbage (Priority: P5)

**Goal**: Interrupted and abandoned runs do not fill the machine with orphaned
workspaces or the commit graph with stray anonymous heads.

**Independent Test**: Create workspaces, abandon them by simulating
interruption, run the sweep, and assert only workspaces backing genuinely
resumable work survive.

**Depends on**: US1

### Tests for User Story 5 ⚠️ Write first, confirm they fail

- [X] T085 [P] [US5] Integration test in `tests/integration/workspace/test_sweep.py` — a successful unit's workspace is torn down and no longer jj-registered (FR-024)
- [X] T086 [P] [US5] Integration test in `tests/integration/workspace/test_sweep.py` — `workspace_forget` precedes removal and no stray anonymous head appears in `jj log` afterwards (contract T16, FR-029)
- [X] T087 [P] [US5] Integration test in `tests/integration/workspace/test_sweep.py` — the sweep collects abandoned workspaces, preserves `keep` entries, and one undeletable entry strands neither the others nor the run (contract T17, FR-025, FR-026, FR-027)
- [X] T088 [P] [US5] Integration test in `tests/integration/workspace/test_sweep.py` — the sweep never touches another checkout's workspace root (FR-026)
- [X] T089 [P] [US5] Integration test in `tests/integration/workspace/test_sweep.py` — with every workspace deleted between runs the next run still behaves correctly, and after a sequence of interrupted runs no orphans remain (FR-028, SC-007)

### Implementation for User Story 5

- [X] T090 [US5] Implement `sweep()` in `src/maverick/workspace/lifecycle.py`, generalizing `sweep_stale_workspaces` — scoped to this checkout and workflow, per-entry isolated, never failing the run
- [X] T091 [US5] Implement the `retain_on_failure` policy branch in `src/maverick/workspace/session.py` so a failed unit's workspace is kept only when its consumer asked for it
- [X] T092 [US5] Call `sweep()` at isolated-fly startup from `src/maverick/workflows/fly_beads/workflow.py`, passing the live bead as `keep`
- [X] T093 [US5] Add `isolation_torn_down`, `isolation_retained`, and `isolation_swept` structured logging in `src/maverick/workspace/lifecycle.py` and `src/maverick/workspace/session.py`

**Checkpoint**: No leaks. Scenario 5 of [quickstart.md](./quickstart.md) passes.

---

## Phase 8: User Story 6 - The headless spec chain runs on the shared primitive (Priority: P6)

**Goal**: `maverick spec` behaves identically while its own workspace and
landing implementation disappears.

**Independent Test**: Run a full chain and a resumed halted chain before and
after migration; compare landed artifacts, checkpoint contents, and terminal
output.

**Depends on**: US1, US2, US5. Ranked last before governance deliberately — it
puts a shipped, resumable workflow at risk and should follow a primitive already
proven by fly.

### Tests for User Story 6 ⚠️ Write first, confirm they fail

- [X] T094 [US6] Capture a **pre-migration baseline** before touching the chain: run a full chain and a resumed halted chain, and commit the landed artifacts and a real checkpoint file as fixtures under `tests/fixtures/spec_chain_pre_migration/` (this task must complete before T098)
- [X] T095 [P] [US6] Integration test in `tests/integration/spec_chain/test_migration_parity.py` — landed artifacts are byte-identical to the pre-migration baseline (contract M1, FR-040, SC-009)
- [X] T096 [P] [US6] Integration test in `tests/integration/spec_chain/test_migration_parity.py` — a halted chain resumes from the first incomplete step; a failed step lands no partial artifacts; a halted chain's workspace is retained while a completed one's is torn down (contracts M2, M3, M4, FR-041, FR-042)
- [X] T097 [P] [US6] Integration test in `tests/integration/spec_chain/test_migration_parity.py` — fold-back is scoped to `specs/<feature-dir>`, so a workspace change outside it does not land (contract M7)
- [X] T098 [P] [US6] Integration test in `tests/integration/spec_chain/test_checkpoint_compat.py` — the **real** pre-migration checkpoint fixture from T094 either resumes correctly or refuses with an explicit, actionable message (contract M6, FR-043)
- [X] T099 [P] [US6] Test in `tests/integration/spec_chain/test_migration_parity.py` — protection blocks still drain per step into `ChainState.protection_blocks` and survive checkpoint and resume (contract S6)

### Implementation for User Story 6

- [X] T100 [US6] Add `schema_version` to `ChainState` in `src/maverick/workflows/spec_chain/state.py`, treating an absent version as 0 and accepting it only when its landed artifacts still verify on disk
- [X] T101 [US6] Replace `prepare_workspace`/`teardown_workspace`/`sweep_stale_workspaces` calls in `src/maverick/workflows/spec_chain/workflow.py` with an `IsolationSession` using `reuse=True`, `retain_on_failure=True`, key = feature slug, and `fold_scope=("specs/<feature-dir>",)` (FR-038)
- [X] T102 [US6] Replace `land_step_artifacts` in `src/maverick/workflows/spec_chain/landing.py` with a scoped `fold_back()` call (FR-038), keeping `resolve_feature_dir` and `verify_step_artifacts` where they are — they are chain logic, not workspace mechanics
- [X] T103 [US6] Delete `_strip_protected_paths` from `src/maverick/workflows/spec_chain/landing.py`, superseded by `policy.fold_exclusions`
- [X] T104 [US6] Delete `src/maverick/workspace/spec_chain.py` and its shim re-exports once nothing imports them, and confirm no chain-specific provisioning, fold-back, or teardown implementation remains (FR-039, SC-008)
- [X] T105 [US6] Update the chain's per-step protection-block drain in `src/maverick/workflows/spec_chain/workflow.py` to read from the lease

**Checkpoint**: One primitive, two consumers. Scenario 7 of [quickstart.md](./quickstart.md) passes.

---

## Phase 9: User Story 7 - The constitution describes the system that exists (Priority: P7)

**Goal**: A contributor reading Guardrail X.0 can correctly answer "may my
workflow run an agent in an isolated workspace?" without consulting source or
spec history.

**Independent Test**: Read the amended Guardrail X.0 and Appendix E cold and
check them against delivered behavior for contradictions and for the removed
"one documented exception" framing.

**Depends on**: US1–US6 — it depends on the final shape of everything above.

- [X] T106 [US7] Amend Guardrail X.0 in `.specify/memory/constitution.md` to state the single-repo model, the **bd-stays-out** invariant, and that isolated agent-side execution is permitted under this feature's contract; remove the "one documented exception" framing entirely (FR-044, FR-045)
- [X] T107 [US7] Rewrite Appendix E of `.specify/memory/constitution.md` to describe the general primitive and its two consumers rather than one workflow's mechanism, carrying forward the `os.chdir` deviation and its exit criterion (FR-046)
- [X] T108 [US7] Determine the version increment for `.specify/memory/constitution.md` from its own Governance section's criteria — a guardrail redefinition reads as MAJOR under "backward-incompatible principle changes, removals, or redefinitions" — and write the Sync Impact Report, `**Version**`, and `**Last Amended**` fields accordingly (FR-047)
- [X] T109 [US7] Propagate the same change to `CLAUDE.md`'s Guardrail 0 section and its `### fly` / `### spec` command documentation, keeping guardrail numbering aligned between the two files
- [X] T110 [US7] Add a test in `tests/unit/test_constitution_sync.py` asserting the constitution no longer contains the "one documented exception" phrasing and that Guardrail 0's numbering still matches `CLAUDE.md` (SC-010)

**Checkpoint**: Governance describes the system that exists.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T111 [P] Add the overhead-budget integration test in `tests/integration/workspace/test_overhead.py` asserting provision + fold-back + teardown stays within 5 s per unit **on this repository** (FR-050, SC-012)
- [X] T112 [P] Add a test in `tests/integration/workspace/test_observability.py` asserting every lifecycle transition logs `unit_key`, `workflow`, and `workspace_path`, and that an operator can reconstruct an interruption, a refused concurrent run, and an undo from log and progress output alone (FR-051, SC-013)
- [X] T113 [P] Document isolated mode in `README.md` — the flag, the config key, the preconditions, and the recovery path when a run refuses on a stale journal
- [X] T114 [P] Add an `isolation` section to `docs/` covering the two check placements and why the split exists, linking [research.md](./research.md) R6
- [X] T115 Run the full validation in `specs/057-isolated-bead-workspaces/quickstart.md`, all eight scenarios, and record the measured per-unit overhead in the PR description
- [X] T116 Run `make format-fix && make ci` from the repository root and fix everything it surfaces, including anything pre-existing the change touched (Principle XII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: needs Setup — **blocks every user story**
- **US1 (Phase 3)**: needs Foundational
- **US2 (Phase 4)**: needs US1
- **US3 (Phase 5)**: needs US1 and US2
- **US4 (Phase 6)**: needs US1 — independent of US2, US3, US5
- **US5 (Phase 7)**: needs US1 — independent of US2, US3, US4
- **US6 (Phase 8)**: needs US1, US2, US5
- **US7 (Phase 9)**: needs US1–US6
- **Polish (Phase 10)**: needs the stories it covers

### An honest note on story independence

The template's usual promise — that stories can proceed in parallel — does not
hold here, and pretending otherwise would produce a broken plan. US2 has nothing
to undo without US1's fold-back; US3 is a consumer of both. What **is** true:

- **US4, US5, and US7 are genuinely parallel** with each other once US1 lands.
- Every story remains independently *testable* at its checkpoint, which is what
  the incremental-delivery strategy actually needs.
- The MVP is US1 alone: a working primitive with no consumer.

### Within Each User Story

- Tests are written first and must fail before implementation
- Models before services; services before actions; actions before graph wiring
- T094 (baseline capture) must complete before T098 (checkpoint compatibility)

### Parallel Opportunities

- T004 alongside T001–T003
- T005/T007/T009 (different jj methods, different test files) together
- T011/T012/T013 (models, exceptions, model tests) together
- All of T018–T029 (US1 tests) together
- All of T038–T046 (US2 tests) together
- All of T053–T064 (US3 tests) together
- T079–T081, T085–T089, T095–T099 within their stories
- T111–T114 in Polish

---

## Parallel Example: User Story 1

```bash
# Write all US1 tests together, confirm they fail:
Task: "Provisioning creates a per-unit workspace in tests/integration/workspace/test_provision.py"
Task: "Workspace sees uncommitted checkout work in tests/integration/workspace/test_provision.py"
Task: "Create/modify/delete fold back as one application in tests/integration/workspace/test_foldback.py"
Task: "Fold-back without workspace snapshot returns EMPTY in tests/integration/workspace/test_foldback.py"
Task: "Ignored paths never fold back in tests/integration/workspace/test_foldback.py"
Task: "Divergent edit yields CONFLICT with paths named in tests/integration/workspace/test_conflict.py"

# Then implement, in dependency order:
Task: "lifecycle.py provision/teardown"   # T030
Task: "foldback.py fold_back()"           # T032  (needs T030)
Task: "session.py IsolationSession"       # T035  (needs T030, T032)
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup
2. Phase 2: Foundational — **critical, blocks everything**
3. Phase 3: US1
4. **STOP and VALIDATE**: drive the primitive with a stub unit; run quickstart Scenario 1
5. The primitive is useful on its own — it is what US3 and US6 both consume

### Incremental Delivery

1. Setup + Foundational → jj can squash across workspaces
2. US1 → the primitive works standalone (MVP)
3. US2 → rejection and undo are real → quickstart Scenarios 3 and 6
4. US3 → `maverick fly --isolated` → quickstart Scenario 2, and SC-001 equivalence
5. US4 + US5 in parallel → the invariant is enforced, nothing leaks
6. US6 → one primitive, two consumers → SC-008 satisfied
7. US7 → governance matches reality

### Risk Notes Carried From Planning

- **T023 is the highest-value test in the feature.** A fold-back that skips the
  workspace snapshot silently moves nothing and looks exactly like a legitimate
  empty delta. Write it first.
- **Undo (T038–T040, T050) is on the normal failure path**, not an exceptional
  one. Treat it as a first-class feature with direct coverage, not best-effort
  cleanup. T040's state — unverified work stranded in the checkout — is the
  worst this feature can produce.
- **T094 must run before the chain is touched.** A parity baseline captured
  after migration proves nothing.
- **FR-015 serializes on the verification window** and the `os.chdir` seam
  serializes agent execution process-wide. Both are correct for this feature's
  serial scope and both are hard blockers for the concurrent dispatcher
  (roadmap prompt 9), which needs airframe to grow a universal
  working-directory parameter first.

---

## Notes

- `[P]` = different files, no dependencies on incomplete tasks
- Every jj integration test needs a real `jj` binary and its own colocated
  fixture — this repository is not itself jj-colocated
- Commit after each task or logical group
- Guardrail X.7: every new step takes its directory explicitly; no
  `Path.cwd()` inside `src/maverick/workflows/`

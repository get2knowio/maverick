# Implementation Plan: Isolated Bead Workspaces

**Branch**: `057-isolated-bead-workspaces` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/057-isolated-bead-workspaces/spec.md`

## Summary

Generalize the spec-chain's hidden jj workspace into a shared isolated-execution
primitive (`src/maverick/workspace/`), give `maverick fly` an opt-in isolated
mode that runs every agent step for a bead inside its own workspace, migrate the
headless spec chain onto the same primitive, and amend Guardrail X.0 from "no
hidden workspaces, one documented exception" to its actual load-bearing
constraint: **bd never runs inside a workspace**.

The mechanism is jj-native and was validated empirically before this plan was
written (see [research.md](./research.md) R2):

- **Provision** — `jj workspace add -r @ <dir>`, so the workspace's working-copy
  commit is a child of the checkout's `@` and the agent sees the checkout's
  uncommitted work (FR-003).
- **Fold back** — snapshot the workspace (`jj status` inside it — load-bearing,
  R3), capture the checkout's operation id, then
  `jj squash --from '<ws>@' --into @ '~.maverick'` from the checkout. jj's
  fileset argument gives FR-010/FR-011 (ignored paths, orchestrator state) for
  free.
- **Detect conflicts** — jj materializes conflicts rather than failing; the
  existing `jj_list_conflicts` action reads the `conflicts()` revset (FR-008).
- **Undo** — `jj op restore <captured-op>` restores the checkout byte-identically
  *and* rewinds the workspace's working-copy commit, so the rejected delta is
  still in the workspace for the fix round (FR-014, FR-017 — one mechanism, both
  requirements).

Verification splits by placement exactly as the spec's FR-012 requires: fly's
`ac_check`/`spec_check` are artifact-level and run inside the workspace; fly's
`gate` (format/lint/test) is environment-level and runs against the checkout
after fold-back, with undo on failure.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: jj 0.44+ (via `maverick.jj.client.JjClient`), Burr
(state machines), airframe 0.9.2 (agent runtime), Pydantic (config), pathspec
(protection matching) — no new external dependency

**Storage**: Filesystem. Workspaces under
`~/.maverick/workspaces/<project>/<workflow>/<key>/`; the in-progress
application journal and cross-run lock under `<cwd>/.maverick/runs/`
(gitignored). Durable outcomes live only in the user's checkout.

**Testing**: pytest + pytest-asyncio + xdist. Integration tests need a real jj
binary and a temporary colocated repo (the `jj git init --colocate` fixture
pattern already used by the jj/spec-chain suites).

**Target Platform**: Linux/macOS developer checkouts, jj-colocated

**Project Type**: Single project — Python CLI

**Performance Goals**: ≤5 s isolation overhead per unit of work (SC-012,
FR-050). `jj workspace add` measured at ~0.02 s on a small scratch repo; the
cost that matters is materializing the tree, so the budget is validated on this
repository, not a synthetic one.

**Constraints**: No bd, ledger, or commit-graph write may target a workspace
(FR-020–023). One isolated run per checkout (FR-048). Agent steps are pointed at
a workspace through a process-global `os.chdir` seam, because airframe 0.9.2's
`ClaudeOptions` still exposes no working-directory field — see Complexity
Tracking.

**Scale/Scope**: One workspace live at a time per checkout; beads remain strictly
serial. Two consumers (fly, spec chain). ~7 new modules, one Burr graph variant,
one constitution amendment.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Verdict | Notes |
| --- | --- | --- |
| I. Async-First | PASS | Every primitive operation is `async def` over `JjClient`, which runs jj through `CommandRunner` with timeouts. No `subprocess.run` on an async path. Filesystem work (`shutil.rmtree`) follows the existing `workspace/spec_chain.py` precedent. |
| II. Separation of Concerns | PASS | The primitive is a library under `src/maverick/workspace/`; Burr actions own control flow; agents keep providing judgment only. Fold-back, undo, and commit are orchestrator-owned deterministic side effects (Guardrail X.2). |
| III. Dependency Injection | PASS | `IsolationSession` receives `cwd`, `jj_client`, and its policy; nothing is global. `home=` override retained for tests. |
| IV. Fail Gracefully | PASS | Fold-back conflict fails one bead; sweep failures are per-entry isolated; the only hard halt is a failed undo (FR-018), which is deliberate. |
| V. Test-First | PASS | Contract tests per [contracts/](./contracts/) precede implementation; the undo path gets direct coverage rather than best-effort treatment. |
| VI. Type Safety | PASS | Frozen dataclasses (`FoldBackResult`, `IsolationLease`, `ApplicationRecord`) with `to_dict()`; no `dict[str, Any]` on the primitive's public surface (Guardrail X.3). |
| VII. Simplicity & DRY | PASS | SC-008 is the point: one provisioning/fold-back/teardown implementation, two consumers. `workspace/spec_chain.py` becomes a shim, then goes away. |
| IX. Hardening by Default | PASS | jj calls inherit `JjClient`'s timeouts and tenacity retries. New failure modes (stale lock, uncleared journal) have explicit handling. |
| X.0 Single-repo model | **AMENDED** | This feature changes the guardrail rather than violating it. See Complexity Tracking row 1 and FR-044–047. |
| X.2 Deterministic ops not agents | PASS | Agents never fold back, commit, or touch bd. |
| X.5 One canonical wrapper | PASS | `JjClient.squash` gains a `from_` parameter; `workspace_add` gains `revision`. No new VCS wrapper. |
| X.7 Explicit cwd threading | **DEVIATION** | Two directories now flow through fly (checkout and workspace), both explicit. The `os.chdir` seam is process-global by necessity. See Complexity Tracking row 2. |
| X.8 Canonical libraries | PASS | jj writes via `JjClient`, logging via `maverick.logging`, retries via tenacity, no `subprocess.run("git ...")`. |
| X.10 Determinism over inference | PASS | Zero model calls added. Conflict detection, ignore filtering, and undo are all deterministic jj operations. |
| XI. Modularize Early | PASS *(with a constraint)* | The primitive is split across six focused modules rather than growing `spec_chain.py`. `fly_beads/actions.py` is **1,887 lines** — past the 1,000-line hard stop, which forbids adding features to it without first carving out a submodule. `fly_beads/_isolation.py` is that carve-out, and every change to `actions.py` in this feature is constrained to delegation into it. |

**Post-Phase-1 re-check**: unchanged. The design added no new external
dependency, no new subprocess wrapper, and no model call. The two flagged rows
below remain the only deviations, both deliberate and both documented.

## Project Structure

### Documentation (this feature)

```text
specs/057-isolated-bead-workspaces/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
├── contracts/           # Phase 1 output
│   ├── isolation-primitive.md
│   ├── fly-isolated-mode.md
│   └── spec-chain-migration.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/maverick/
├── workspace/                     # the shared primitive (grown in place)
│   ├── __init__.py                # public surface: IsolationSession, results
│   ├── models.py                  # IsolationPolicy, IsolationLease, FoldBackResult, ApplicationRecord
│   ├── session.py                 # IsolationSession: provision → run → fold_back → undo → teardown
│   ├── foldback.py                # squash/conflict-detect/op-restore mechanics
│   ├── lifecycle.py               # prepare / teardown / sweep (generalized from spec_chain.py)
│   ├── journal.py                 # in-progress application record + cross-run lock (FR-048, FR-049)
│   ├── cwd_scope.py               # the os.chdir seam, hoisted out of agents/spec_chain.py
│   └── spec_chain.py              # shim re-exporting lifecycle during migration, deleted once US6 lands
├── jj/client.py                   # + squash(from_=...), workspace_add(revision=...), workspace snapshot
├── library/actions/jj.py          # + jj_fold_back / jj_workspace_snapshot typed actions
├── config.py                      # WorkspaceConfig repurposed: root / enabled / reuse (dead fields removed)
├── cli/commands/fly/_group.py     # + --isolated / --no-isolated
├── workflows/fly_beads/
│   ├── _isolation.py              # per-bead lease handling, fold-back action bodies
│   ├── actions.py                 # agent steps become workspace-aware; gate stays checkout-side
│   └── burr_graph.py              # isolated-mode transitions (gate after review) + new state slots
├── workflows/spec_chain/
│   ├── workflow.py                # consumes IsolationSession instead of its own lifecycle
│   └── landing.py                 # scoped fold-back via fileset; chain-specific logic only
└── agents/spec_chain.py           # chdir logic moves to workspace/cwd_scope.py

tests/
├── unit/workspace/                # models, journal, lifecycle, policy
├── integration/workspace/         # real jj repo: provision/fold-back/conflict/undo/sweep
├── integration/fly/               # isolated-vs-normal history equivalence (SC-001)
└── integration/spec_chain/        # pre/post-migration parity (SC-009)
```

**Structure Decision**: Single project, existing layout. The primitive grows
`src/maverick/workspace/` — the package the constitution already names as
Guardrail X.0's exception home — rather than introducing a parallel
`isolation/` package. `workspace/spec_chain.py` is kept as a re-exporting shim
through the migration (Debt Prevention #4) and removed in the same feature once
US6 lands, satisfying FR-039.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Guardrail X.0 amended: hidden workspaces are no longer exceptional | The guardrail's stated rule ("there is no hidden workspace") is not the constraint that actually failed twice — bd's gitignored `.beads/`+`embeddeddolt/` not travelling into `jj workspace add` is. Spec 050 shipped a workspace that works precisely because bd stays in the checkout. Leaving the text as-is makes every future workspace consumer either look like a violation or need its own "documented exception" paragraph. | Keeping the current text and adding a second exception was rejected: two exceptions is the point at which the rule is wrong, not the exceptions. Amending states the real invariant (FR-044) and makes it enforceable in code (FR-021). |
| `os.chdir` seam extended from the spec chain to fly | airframe 0.9.2 exposes `working_directory` on `CopilotOptions` and `OpenCodeServerOptions` but **not** `ClaudeOptions` (verified against the installed package). A provider-blind way to point an agent at a workspace does not exist today, and pointing only some providers at it would make isolated mode silently wrong on the default provider. | Per-provider `working_directory` was rejected: it leaves the `claude` provider — the default — unable to isolate at all. Upstreaming a `cwd` field to airframe is the real fix but blocks this feature on an external release. The seam is bounded by FR-031 (serial beads), FR-048 (one isolated run per checkout), and an `asyncio.Lock`, exactly as Appendix E already documents for the chain. **Exit criterion**: when airframe grows a universal working-directory parameter, `workspace/cwd_scope.py` becomes a one-line adapter call and the lock disappears. The concurrent dispatcher (roadmap prompt 9) cannot ship until then. |

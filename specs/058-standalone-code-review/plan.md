# Implementation Plan: Standalone Code Review

**Branch**: `058-standalone-code-review` | **Date**: 2026-08-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/058-standalone-code-review/spec.md`

## Summary

Add `maverick critique` — a read-only CLI command that runs the existing
reviewer pair over one of three scopes (working-copy diff, an epic's commits,
or explicit paths), renders findings grouped by file, persists a
json+markdown artifact, and offers a `--json` mode through the shared
envelope.

The whole feature is an assembly of parts that already exist. The only new
agent-facing surface is one additional prompt builder on `ReviewerAgent`; the
only new shared surface is a reviewer-pair factory extracted from
`FlySquadron` so the pair is built in one place rather than two.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: Click, Rich, GitPython (read-only), airframe,
Pydantic, `pathspec` (unused here), `atomicwrites` via `utils/atomic.py`
**Storage**: `.maverick/runs/<run-id>/critique-report.{json,md}`
**Testing**: pytest + pytest-asyncio + xdist; `CliRunner` via the `cli_runner`
fixture
**Target Platform**: local developer checkout, jj-colocated
**Project Type**: single project (CLI)
**Performance Goals**: scope resolution completes without a model call; an
empty scope short-circuits before any agent is constructed (SC-004)
**Constraints**: read-only with respect to the repository on every path
(FR-012); zero new `ErrorKind` values (FR-021); no second reviewer
implementation (FR-007)
**Scale/Scope**: one new command, one new package (~6 modules), one extracted
shared factory, one new agent method, one fly defect fix

## Constitution Check

| Principle | Status | Note |
| --- | --- | --- |
| I. Async-first | PASS | `@async_command`; `AsyncGitRepository` for VCS reads; no `subprocess.run` on an async path |
| II. Dependency injection | PASS | `cwd`, config, and both agents are injected; the squadron is opened by the command and passed down |
| III. Fail gracefully | PASS | FR-011 — one lens failing degrades to a warning; only both failing is a failure |
| IV. Test-first | PASS | Every task below pairs implementation with its tests; contract tests precede the CLI wiring |
| V. Type safety | PASS | Frozen dataclasses throughout (data-model.md); no `dict[str, Any]` |
| VI. Simplicity | PASS | No new abstraction beyond `CritiqueSquadron`, which exists to avoid a duplicated construction sequence |
| VII. Complete work | PASS | No deferrals; R8's discovered defect is fixed in-slice rather than filed |
| VIII. Determinism over inference | PASS | Scope resolution, ordering, and severity counting are pure functions; the model is called exactly once per lens |

**Guardrail check**:

- **0 (single-repo, bd stays out of isolation)**: PASS — `critique` runs in
  the checkout, provisions no workspace, and its only `bd` contact is a
  read (`children(epic_id)`).
- **1 (no blocking on the event loop)**: PASS — `AsyncGitRepository`
  wraps every GitPython call in `asyncio.to_thread`.
- **2 (deterministic ops belong to workflows, not agents)**: PASS — the
  agent supplies judgment only; scope resolution, ordering, rendering, and
  persistence are all command-side.
- **3 (single typed contract)**: PASS.
- **5 (one canonical wrapper per external system)**: PASS — GitPython for
  reads, `BeadClient` for beads, no new subprocess wrapper. This is why R3
  reuses `curation.extract_bead_ids` rather than writing a second regex.
- **7 (explicit cwd threading)**: PASS — resolved once in the command body,
  passed explicitly to every layer. No `Path.cwd()` below the CLI boundary.
- **8 (deterministic ingestion over model inference)**: PASS.

No entry needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```
specs/058-standalone-code-review/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R11
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-critique.md          # command surface + human output
│   ├── cli-critique-json.md     # --json verb contract
│   └── critique-report-schema.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```
src/maverick/
├── critique/                    # NEW package
│   ├── __init__.py              # public surface: run_critique, CritiqueReport
│   ├── models.py                # CritiqueScopeKind, ResolvedScope, ScopedCommit,
│   │                            #   LensOutcome, CritiqueReport
│   ├── scope.py                 # resolve_diff_scope / resolve_epic_scope /
│   │                            #   resolve_paths_scope  (pure + VCS reads)
│   ├── runner.py                # opens CritiqueSquadron, runs both lenses,
│   │                            #   builds the report
│   ├── render.py                # terminal rendering (grouped by file)
│   └── report.py                # to_dict / render_markdown / persist
├── squadron/
│   ├── reviewers.py             # NEW — build_reviewer_pair(), extracted from fly
│   ├── fly.py                   # MODIFIED — delegates to reviewers.py
│   └── critique.py              # NEW — CritiqueSquadron (one reviewer pair)
├── agents/reviewer.py           # MODIFIED — + critique() method
├── payloads.py                  # MODIFIED — + review_payload_approved()
├── cli/commands/critique.py     # NEW — the Click command
├── main.py                      # MODIFIED — one _LAZY_COMMANDS entry
└── workflows/fly_beads/
    └── actions.py               # MODIFIED — _safe_diff_stat uses the shared
                                 #   epic resolver (R8)

tests/
├── unit/
│   ├── critique/
│   │   ├── test_models.py
│   │   ├── test_scope.py
│   │   ├── test_runner.py
│   │   ├── test_render.py
│   │   └── test_report.py
│   ├── squadron/test_reviewers.py
│   ├── agents/test_reviewer_agent.py        # MODIFIED — critique() cases
│   ├── cli/test_critique_command.py
│   └── cli/commands/test_critique_json.py
└── integration/
    └── critique/
        ├── test_read_only.py                # SC-002
        ├── test_scope_resolution.py         # epic + paths against a real repo
        └── test_fly_aggregate_diff.py       # R8 regression
```

**Structure Decision**: single project. The new `critique/` package follows
the Debt Prevention split rule (models / logic / render / report as separate
modules from the start) rather than starting as one file and splitting later.
`cli/commands/critique.py` stays thin — dispatch and rendering only, per the
CLI split convention.

## Design

### Flow

```
critique CLI
  ├─ resolve cwd, config                        (no I/O beyond config load)
  ├─ validate flags  ──────────── conflicting scopes → VALIDATION
  ├─ resolve scope   ──────────── epic missing     → NOT_FOUND
  │                               bad path         → VALIDATION
  │                               git read failure → VCS
  ├─ if scope.is_empty ─────────► report(reviewed=False), exit 0   ← zero model calls
  ├─ open CritiqueSquadron  ───── missing agents.review binding → the existing
  │                                                              binding error
  ├─ gather(correctness.critique, completeness.critique,
  │         return_exceptions=True)
  │        ├─ one fails → LensOutcome(error=...), warn, continue
  │        └─ both fail → INTERNAL
  ├─ build CritiqueReport (ordering per data-model.md)
  ├─ persist artifact ──────────── OSError → warn, degraded_persistence=True
  ├─ render (terminal or single JSON envelope)
  └─ exit 0, unless --fail-on is engaged and met
```

### Key decisions (rationale in research.md)

1. **`CritiqueSquadron`, not `FlySquadron`** (R1) — reusing `FlySquadron`
   would demand an `agents.implement` binding a review-only repository has no
   reason to configure.
2. **A third prompt on the one reviewer** (R2) — `critique()` alongside
   `review()` and `aggregate()`. Same class, same result model, same personas.
3. **Epic commits by subject prefix** (R3) — `extract_bead_ids` is the
   existing reader; the `Bead:` trailer has no reader and no full-body log
   accessor to read it with.
4. **Concatenated per-commit diffs** (R4) — a range diff would silently
   attribute unrelated interleaved commits to the epic.
5. **Explicit truncation, never refusal** (R5) — the agent always gets the
   complete changed-file list and can read what the embedded diff omits.
6. **`--base` defaults to `main`** (R6) — identical to `land --base`.
7. **Structured findings, no cross-lens dedupe** (R7).
8. **Fix fly's aggregate diff stat** (R8) — this feature builds the resolver
   whose absence caused it.

### What this feature does *not* touch

- No Burr graph, no `@action`, no state slots. `critique` is a single-shot
  command, not a workflow; wiring it into Burr would add a state machine with
  one path through it.
- No `ErrorKind` additions (R11).
- No assumption-ledger contact, no land-frontier contact (FR-014).
- No changes to `review()` or `aggregate()` behavior — only an addition
  beside them.

## Testing Strategy

- **Read-only proof (SC-002)** is an integration test that snapshots the jj
  operation log, the git object count, the full bead list, and a content hash
  of every tracked file, runs `critique` on each scope *and* on each failure
  path, and asserts every snapshot is byte-identical. This is the test that
  makes FR-012 real rather than aspirational.
- **Shape equivalence (SC-003)** is asserted by constructing a
  `SubmitReviewPayload` and checking that `critique`'s findings are the same
  `ReviewFindingPayload` objects, unmodified — not a parallel type.
- **Zero-model-call proof (SC-004)** patches `runtime_for_agent` to raise and
  asserts an empty scope still exits 0.
- **JSON single-document proof (SC-005)** parses `result.stdout` with
  `json.loads` and asserts nothing else was written to that stream, on both
  success and every failure kind.

## Complexity Tracking

No constitutional violations require justification.

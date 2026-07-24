# Research: Transactional Reconcile of Changed Human Answers

All decisions below are grounded in codebase exploration (2026-07-24) of
`src/maverick/jj/`, `src/maverick/assumptions/`, `src/maverick/workflows/fly_beads/`,
`src/maverick/squadron/`, `src/maverick/config.py`, and the local jj binary
(0.43.0). File:line references are to the tree at commit `dac2b67`.

## R1. Changed-answer detection & the linkage that makes reconcile possible

**Decision**: Detect changed answers deterministically from existing ledger
storage. An entry qualifies when: it carries the `assumption` label, its
`assumption_status` state is `answered`, it has no terminal
`assumption_reconcile_status`, and `normalize(assumption_answer state)` ≠
`normalize(## Adopted Answer section of the bead description)`. Normalization =
`" ".join(text.split()).casefold()`.

**Rationale**: Everything needed already exists and is preserved separately:
the adopted answer lives in the bead description (`_build_description`,
`ledger.py:129`) and is never overwritten; the human answer lands in the
`assumption_answer` state key (`ledger.answer()`, `ledger.py:741`); and the jj
change ID is stamped append-only into `assumption_change_ids`
(`stamp_change_id`, `ledger.py:704`, called from fly's `commit` action,
`fly_beads/actions.py:1364`). Zero model calls, per clarification Q1.

**Caveat found in exploration**: `ledger.answer()` closes the bead
(`client.close`), and every existing ledger query filters `status=open`
(`open_blocking_entries`, `ledger.py:812`). The new query
`answered_unreconciled_entries()` must query closed/done beads too — it cannot
reuse the open-only queries. Legacy escalation beads (`assumption-review` label
without `assumption` label) have no adopted-answer/change-id structure and are
**not reconcilable**; they are excluded from detection entirely.

**Alternatives considered**: agent-judged semantic comparison (rejected: cost,
nondeterminism — clarification Q1); explicit "needs reconcile" flag at review
time (rejected: changes review UX, redundant with deterministic comparison).

## R2. Correction target when an entry has multiple stamped change IDs

**Decision**: The correction target is the **earliest stamped change that still
exists**, resolved by ordering the entry's `assumption_change_ids` by their
position in `::@` (topological). Later stamped changes are descendants of the
target by construction (append-only stamps across fix rounds of the same or
later beads) and are handled by auto-rebase plus the semantic-dependents pass.
If **no** stamped change resolves (`_resolve_change_id` returns empty /
revset misses), the answer is marked needs-interactive-review (FR-015).

**Rationale**: Stamps accumulate when the same entry is touched across fix
rounds (`stamp_change_id` is append-only, `ledger.py:710`). The assumption was
*introduced* in the earliest change; that is where history should read as
corrected.

**Alternatives considered**: correcting the latest stamp (rejected: leaves the
introduction point wrong — exactly the fixup-at-tip smell FR-003 bans);
correcting every stamp independently (rejected: one delta, one fold point;
`jj absorb` covers genuinely multi-change deltas — see R3).

## R3. Correction mechanism: child → delta → squash-into, absorb as the multi-target path

**Decision**: Primary path per answer:
1. `JjClient.new(parents=[target])` (client.py:413) — working copy becomes an
   empty child of the target.
2. ReconcilerAgent edits files in `cwd` (judgment only — same contract as fly's
   implementer) and returns a `SubmitCorrectionPayload` (summary + touched
   files + `no_change_required` flag).
3. Workflow verifies the delta with `diff_stat(revision="@")`; if empty and
   `no_change_required`, terminal-mark the entry reconciled (empty-delta edge
   case) after restoring the working copy.
4. `JjClient.squash(revision=<child>, into=<target>)` (client.py:707) — jj
   folds the delta and **auto-rebases all descendants** in the same operation.

`jj absorb` (client.py:735) is used **instead of squash** only when the entry
has multiple stamped changes and the delta spans them: absorb routes each hunk
to the mutable ancestor that last touched those lines. It is *not* the default
because absorb routes by blame, and a hunk on lines last modified by a
*descendant* would be folded into the descendant — silently misattributing the
correction. `squash --into` is deterministic targeting; absorb is the
explicitly-scoped fallback FR-003 allows ("when hunk routing suffices").

**Rationale**: Both primitives already exist on `JjClient`; jj 0.43 confirmed
locally to support both plus auto-rebase-on-squash. No `jj edit` needed — the
child-then-squash idiom avoids adding new client surface for moving `@`.

**Alternatives considered**: `jj edit <target>` + amend in place (rejected:
`edit` not on the client; child+squash is equivalent and keeps the delta
inspectable pre-fold); generating a patch file and `git apply` (rejected:
Guardrail X.8 — no git writes).

## R4. Conflict and mutability queries: reuse `log(revset=...)`, no new client methods

**Decision**: All revset queries go through the existing
`JjClient.log(revset=..., limit=...)` (client.py:535), wrapped in typed actions
in `library/actions/jj.py`:
- Conflicted descendants: `log(revset=f"descendants({target}) & conflicts()")`.
- Mutability guard (pre-flight per answer): assert
  `log(revset=f"(::{target} & immutable() & {target}) | (descendants({target}) & immutable())")`
  is empty — i.e., neither the target nor any descendant the rebase would
  rewrite is immutable. Implemented as `jj_check_mutability` action.
- Stack ordering (R2, FR-002): one `log(revset="::@", limit=1000)` and index
  the targets by position (reversed → earliest first).

**Rationale**: jj's `immutable()` revset *is* the project-configurable
immutability boundary (`revset-aliases."immutable_heads()"` covers trunk, tags,
and untracked remote bookmarks by default) — this directly implements FR-011/
FR-012's "immutability configuration bounds the blast radius" with zero custom
pushed-state tracking. Exploration confirmed the client has **no** conflict
listing, `resolve --list`, or immutability helpers today, but `log()` accepts
arbitrary revsets, so thin action-layer wrappers suffice; no `JjClient` API
additions beyond none — only `library/actions/jj.py` gains typed wrappers
(`jj_new_child`, `jj_squash_into`, `jj_list_conflicts`, `jj_check_mutability`).

**Alternatives considered**: adding first-class `JjClient.is_immutable()` /
`conflicted_revisions()` methods (acceptable; deferred — wrappers over `log`
keep the client small; promote later if a second consumer appears, per
Principle VII); parsing `jj resolve --list` (rejected: file-level detail not
needed for the resolution loop, which works change-by-change).

## R5. Conflict resolution loop: rounds over conflicted changes, budget = 3

**Decision**: After the fold, list conflicted descendants (R4). Resolution
runs in **rounds** (default `reconcile.resolution_rounds = 3`, per
clarification Q2). Each round: for each conflicted change in topological
order — `new(parents=[conflicted_change])` (conflict markers materialize in
the working copy), ReconcilerAgent resolves markers given {question, old
adopted answer, new human answer, conflicted file contents}, workflow squashes
the resolution into the conflicted change (jj propagates the resolution to
downstream conflicts automatically). Re-list conflicts; empty → proceed;
non-empty after the final round → fail the answer (rollback + escalation bead
per FR-006).

**Rationale**: Mirrors fly's bounded-round precedent (`MAX_REVIEW_ROUNDS = 3`,
`fly_beads/actions.py:63`; exhaustion → `create_human_bead`,
`actions.py:1158`). Round-based budgets are enforced deterministically by the
workflow (constitution X.3) — no token/cost accounting dependency. jj's
conflict propagation means resolving the earliest conflicted change often
clears descendants, so topological order minimizes agent calls.

**Alternatives considered**: per-conflict (not per-round) budget (rejected:
count varies wildly with stack shape; rounds bound total agent invocations at
`rounds × conflicted-changes`, and the round re-list handles propagation);
tenacity retry wrapper (not applicable — this is a work loop with fresh input
per round, not a retry of an identical operation; fly's `for round in range`
pattern is the codebase precedent).

## R6. Semantic-dependents pass: workflow fans out diffs, review-lens agent judges

**Decision**: Workflow enumerates
`log(revset=f"descendants({target}) & mutable() & ~{target}")`, captures the
correction diff (`diff(revision=target_after_fold)` limited to the folded
hunks — in practice the child's pre-squash diff, captured at R3 step 3) and
each descendant's `diff(revision=...)`. `SemanticDependentsAgent` (review
binding) receives {question, old answer, new answer, correction diff,
descendant diff} per descendant and returns findings
(`SubmitSemanticDependentsPayload`: per-descendant `dependent: bool`,
`reason`, `fix_instructions`). For each flagged descendant, the
ReconcilerAgent applies the fix via the same child→edit→squash-into mechanism
(R3), targeted at that descendant. The pass is budgeted
(`reconcile.semantic_rounds`, default 3, clarification Q5): a round =
analyze-all + fix-flagged; a follow-up round re-analyzes only previously
flagged descendants to verify the fix; exhaustion → rollback + escalation
bead, same semantics as FR-006.

**Rationale**: Analysis is judgment (review lens); application is a
deterministic fold the workflow owns — clean X.3 split. Capturing the
correction diff *before* squash gives the precise delta even when the target's
full diff is much larger than the correction.

**Alternatives considered**: one mega-prompt over the whole stack (rejected:
context size scales with stack, per-descendant fan-out is bounded and
parallelizable later); having the semantic agent also edit files (rejected:
mixes lenses; reuse of ReconcilerAgent keeps fix mechanics in one persona).

## R7. Gate suite: reuse `run_independent_gate` with full stages

**Decision**: Per answer, after the semantic pass:
`run_independent_gate(stages=("format","lint","typecheck","test"), cwd=cwd,
validation_commands=_build_validation_commands(config.validation))`
(`library/actions/validation.py:40`, commands via
`fly_beads/_plan_parsing.py:20`). Failure → answer fails (rollback +
needs-interactive-review). Gate stages run on the working copy positioned at
the rebased head.

**Rationale**: This is the exact suite fly's baseline gate runs
(`fly_beads/workflow.py:313`); "the gate suite" in the spec maps to it
directly. Full stages (including typecheck, unlike fly's per-bead gate) because
reconcile rewrites arbitrary history and must prove the head green, not just a
bead's slice.

## R8. Transaction boundary: jj op restore + deferred bd writes

**Decision**: Per answer: capture `snapshot_operation()` (client.py:653) →
restore point. All jj mutations for the answer happen after it. On any stage
failure: `restore_operation(op_id)` (client.py:681), **then** write bd terminal
state (`assumption_reconcile_status=needs-interactive-review` + escalation
bead if budget-exhaustion). On success: write
`assumption_reconcile_status=reconciled` (+ metadata, see data-model). **No bd
writes occur between the restore point and the terminal write** — bd's store
(`.beads/`) is outside the jj op log, so mid-application bd writes would
survive a rollback and violate all-or-nothing. Escalation beads are therefore
created only after the repo restore completes.

**Rationale**: `execute_curation_plan` (`library/actions/jj.py:598`) already
proves the snapshot→execute→restore pattern. The bd-outside-op-log hazard was
identified during exploration; sequencing terminal writes after the jj
restore is the only ordering that keeps FR-009 honest.

**Alternatives considered**: `jj op undo` (rejected: not on the client, and
restore-to-snapshot is idempotent where undo is relative); transactional bd
(doesn't exist).

## R9. Resumable run state & interrupted-run recovery

**Decision**: Persist `ReconcileRunState` to
`.maverick/runs/<run-id>/reconcile.json` after every per-answer transition,
using the spec-chain pattern (`workflows/spec_chain/state.py`: atomic
temp+rename via `maverick.utils.atomic`, `discover_resumable` scanning by
`updated_at` + status). State records per-answer: entry id, target change id,
restore-point op id, stage reached, terminal status. On startup, if a
discovered run has an answer in a non-terminal stage, first
`restore_operation(that answer's op id)`, mark it needs-interactive-review
(interrupted), then process remaining pending answers (FR-016). A run-scoped
lockfile (`.maverick/runs/reconcile.lock`, pid-stamped, stale-detected)
plus a clean-working-copy check (`diff_stat(revision="@")` must report zero
files) implements FR-014's refuse-to-start guards.

**Rationale**: Direct reuse of the established checkpoint pattern (Principle
VIII); the op-log restore makes crash recovery a one-call repair.

## R10. Orchestration: sequential async workflow package, not Burr

**Decision**: `workflows/reconcile/workflow.py` is a plain sequential async
workflow (spec-chain style), emitting `ProgressEvent`/`StepOutput` events,
executed from the CLI via the existing `execute_python_workflow` path. No Burr
graph.

**Rationale**: The control flow is a deterministic nested loop with explicit
transaction boundaries; resumability comes from R9 + the op log, not from
graph state. Fly needed Burr for its many-action per-bead cycle with
mid-graph branching; reconcile's five stages per answer don't. Simplicity
(Principle VII) and the spec-chain precedent both point the same way.

**Alternatives considered**: Burr application like fly (`build_fly_application`,
`burr_graph.py:81`) — rejected as indirection without payoff at this shape;
xoscar supervisor/actor pool — legacy path, being migrated away from.

## R11. Agents, squadron, and role bindings: reuse `implement` and `review` roles

**Decision**: Two new agents, one new squadron:
- `ReconcilerAgent` — `provider_tier = "implement"`, persona
  `maverick.reconciler`, methods `correct(...)` and `resolve_conflicts(...)`;
  result models `SubmitCorrectionPayload` / `SubmitConflictResolutionPayload`.
- `SemanticDependentsAgent` — `provider_tier = "review"`, persona
  `maverick.semantic-reviewer`, method `analyze(...)`; result model
  `SubmitSemanticDependentsPayload`.
- `ReconcileSquadron(Squadron)` — builds both via
  `runtime_for_agent("implement"/"review", agents_config=config.agents)`,
  exposes `.reconciler` / `.semantic`, `_all_agents` yields both;
  `rotate_for_new_bead()` called between answers for fresh sessions.

No new entry in `KNOWN_ROLES` (`runtime/agent_factory.py:45`).

**Rationale**: Exploration showed the legacy `provider_tiers:`/`DEFAULT_TIERS`
cascade is gone; roles now map 1:1 to `AgentsConfig` fields, and adding a role
forces every user config to bind it. Correction/resolution is implement-shaped
work; semantic analysis is review-shaped. Personas differentiate behavior
without new binding surface. (CLAUDE.md's provider-tier narrative predates
this — the plan follows the code, not the stale doc.)

**Alternatives considered**: new `reconcile` role in `KNOWN_ROLES` (rejected:
config burden, no evidence a distinct binding is needed; revisit if usage
shows resolver needs a different model class than implementers).

## R12. Ledger lifecycle extension & FR-017 exclusion

**Decision**: New state keys (constants in `assumptions/models.py`):
`assumption_reconcile_status` (`reconciled` | `needs-interactive-review`),
`assumption_reconciled_at` (UTC ISO), `assumption_reconciled_answer` (the
normalized answer text that was applied), `assumption_reconcile_change_id`
(the target change after fold). New ledger functions:
`answered_unreconciled_entries()`, `mark_reconciled()`,
`mark_needs_interactive_review()`. `ledger.answer()` gains one line: clear
`assumption_reconcile_status` when a human re-answers — this is the FR-017
re-arm mechanism (an entry stuck in needs-interactive-review re-enters
detection only after a human edits the answer via `maverick review`).
Idempotence (SC-008): a reconciled entry whose `assumption_reconciled_answer`
equals the current normalized answer is excluded by detection.

**Rationale**: Follows the established two-axis pattern (bd status vs ledger
state keys); no schema migration, legacy entries unaffected.

## R13. Working-copy discipline

**Decision**: Precondition: `@` is empty (zero-file `diff_stat`) — else refuse
(FR-014). The run records the original `@` parent; after the batch completes,
the workflow leaves the working copy as a fresh empty change on the final
rebased head (`new(parents=[head])`). Per-answer rollback restores `@` via the
op log automatically.

**Rationale**: jj always has a working-copy change; "clean" must be defined as
empty-@. Ending on a fresh empty child of the new head matches what jj users
expect after history surgery.

## R14. CLI surface & config

**Decision**: `cli/commands/reconcile.py` — `maverick reconcile [--dry-run]`,
registered in `_LAZY_COMMANDS` and `commands_needing_git_gh` (`main.py:43`,
`:180`). Uses `verify_bd_ready`, `cli_error_handler`, `async_command`,
`cwd = Path.cwd().resolve()` at the boundary (Guardrail 7). Output: Rich
per-answer summary table (ID / severity / target change / status / reason),
red-panel style matching land's gate table. Exit codes per FR-019:
`SUCCESS(0)` when all terminal states are `reconciled` (or nothing to do);
`FAILURE(1)` when any answer ended skipped/needs-interactive-review.
`--dry-run`: detection + ordering + mutability checks only, zero mutations,
always exit 0 unless preconditions fail. Config: `ReconcileConfig(BaseModel)`
with `resolution_rounds: int = 3`, `semantic_rounds: int = 3`; field
`reconcile: ReconcileConfig` on `MaverickConfig` (`config.py:577` block);
export in `__all__`. Env override via existing `MAVERICK_RECONCILE__*` prefix
mechanics for free.

**Rationale**: Every element mirrors an audited existing command (land/refuel);
nothing novel at the CLI boundary.

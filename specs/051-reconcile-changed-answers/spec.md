# Feature Specification: Transactional Reconcile of Changed Human Answers

**Feature Branch**: `051-reconcile-changed-answers`
**Created**: 2026-07-24
**Status**: Draft
**Input**: User description: "Add a transactional maverick reconcile command that applies changed human answers retroactively. For each changed answer, processed in stack order (earliest change first): create a correction against the ledger-recorded jj change (new child, apply the delta, squash into the target — or absorb when hunk routing suffices), letting jj auto-rebase all descendants; walk the resulting conflicts with a budget-capped resolution agent that receives the question, old assumption, and new answer as context, escalating to a new human bead on budget exhaustion instead of looping; then run a semantic-dependents pass in which an agent compares the correction diff against each descendant change's diff to flag and fix code written because of the old assumption; finally re-run the gate suite on the new heads. Each answer's application is all-or-nothing: any failure restores the repo to the pre-reconcile operation via the jj operation log and marks the answer as needing interactive review. Only mutable (unpushed) changes may ever be touched; immutability configuration bounds the blast radius. Reconciles batch per human sweep rather than per answer."

## Context

Maverick's assumption ledger (spec 049) records the assumptions agents adopt while
implementing beads: the question that arose, the answer the agent adopted, the
alternatives it rejected, and — stamped at commit time — the jj change in which the
assumption-driven code landed. Humans later resolve these entries with
`maverick review <id> --answer` or `--waive`. Today, when a human's answer differs
from what the agent adopted, nothing happens to the code: the wrong assumption is
already baked into a committed change and every change stacked on top of it. The
human's correction is recorded but never applied.

`maverick reconcile` closes that loop: it takes every answered ledger entry whose
human answer contradicts the adopted assumption and retroactively repairs history —
fixing the code *in the original change where the assumption landed*, rippling the
fix through every descendant change, catching code that was written *because of* the
old assumption even where it doesn't textually conflict, and proving the result with
the project's gate suite. Because rewriting committed history is dangerous, every
answer's application is transactional: it either fully succeeds or the repository is
restored exactly as it was, and only unpushed (mutable) history may ever be touched.

## Clarifications

### Session 2026-07-24

- Q: What makes an answer "changed"? → A: Deterministic detection — any answered,
  un-reconciled entry whose normalized human answer text differs from the adopted
  assumption text; the empty-delta path absorbs paraphrase false positives.
- Q: What unit is the resolution budget expressed in? → A: Resolution rounds — a
  configurable maximum number of agent resolution attempts per answer (default 3).
- Q: Are "needs interactive review" answers re-attempted on later runs? → A: No —
  they are excluded from future reconcile runs until a human edits or re-confirms
  the answer (or resolves the escalation bead).
- Q: Should reconcile offer a preview mode? → A: Yes — `--dry-run` reports changed
  answers, target changes, mutability status, and processing order with zero
  repository mutations.
- Q: Is the semantic-dependents pass also budget-capped? → A: Yes — its own
  configurable per-answer budget with identical exhaustion semantics (rollback plus
  escalation bead).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retroactively apply a changed answer (Priority: P1)

A developer runs `maverick fly`, which implements several beads and records an
assumption ("Assumed pagination page size of 50; alternatives: 20, 100" — severity
medium) against the change where it landed. Later, during a review sweep, the
developer answers the entry: "Page size must be 20." They run `maverick reconcile`.
The command finds the changed answer, produces a correction against the original
recorded change (so history reads as if the right answer had been used from the
start), lets all stacked descendant changes rebase on top of the fix, re-runs the
gate suite on the resulting head, and marks the ledger entry as reconciled.

**Why this priority**: This is the core value: a human answer actually changes the
code it invalidated, in place, without the developer manually hunting down every
spot the assumption touched. Without this, the command does not exist.

**Independent Test**: In a repository with a stack of unpushed changes where an
assumption-bearing change has descendants, change the answer on its ledger entry and
run reconcile. Verify the original change now reflects the new answer, no separate
"fixup" change remains at the tip, descendants still apply, gates pass, and the
entry is marked reconciled.

**Acceptance Scenarios**:

1. **Given** an answered ledger entry whose human answer differs from the adopted
   assumption, with a recorded mutable change and clean-rebasing descendants,
   **When** the developer runs `maverick reconcile`, **Then** the correction is
   folded into the recorded change, all descendants are automatically rebased, the
   gate suite passes on the new head, and the entry is marked reconciled.
2. **Given** a ledger entry whose human answer matches the adopted assumption (or
   was waived), **When** reconcile runs, **Then** that entry is not touched and no
   history is modified for it.
3. **Given** no changed answers exist, **When** reconcile runs, **Then** the command
   reports nothing to do and exits successfully without modifying the repository.
4. **Given** a correction whose edits map cleanly into the recorded change without
   manual routing, **When** reconcile applies it, **Then** the result is identical
   to the explicit fold path: the fix lives in the original change and descendants
   are rebased.

---

### User Story 2 - All-or-nothing safety with automatic restore (Priority: P2)

While reconciling an answer, something fails partway through — the correction can't
be produced, conflict resolution gives up, or the gate suite fails on the rewritten
stack. The developer's repository is restored to exactly the state it was in before
that answer's application began, the answer is marked as needing interactive review,
and reconcile moves on to the remaining answers.

**Why this priority**: Reconcile rewrites committed history autonomously. Without a
hard transactional guarantee, a half-applied correction could leave the repository
in a state worse than the wrong assumption — this guarantee is what makes the
command safe to run unattended.

**Independent Test**: Force a failure mid-application (e.g., a gate suite that fails
on the rewritten stack). Verify the repository state — commit graph, working copy,
and conflict markers — is identical to the pre-application snapshot, the answer is
flagged for interactive review, and previously reconciled answers in the same run
remain applied.

**Acceptance Scenarios**:

1. **Given** an answer whose application fails at any stage (correction, conflict
   resolution, semantic pass, or gate suite), **When** the failure occurs, **Then**
   the repository is restored to its state immediately before that answer's
   application began, via the repository's operation history.
2. **Given** a failed answer application, **When** the restore completes, **Then**
   the answer is marked as needing interactive review with the failure reason, and
   the run continues with the next changed answer.
3. **Given** three changed answers where the second fails, **When** the run
   completes, **Then** the first answer's application is preserved, the second is
   rolled back and flagged, and the third was still attempted.
4. **Given** a completed reconcile run, **When** the developer inspects the summary,
   **Then** every answer shows exactly one terminal status: reconciled, skipped
   (immutable/unlocatable), or needs interactive review — never a partial state.

---

### User Story 3 - Conflict resolution with a capped budget and human escalation (Priority: P3)

A correction rebases descendants and some of them conflict with the fix. A
resolution agent walks each conflicted change with full context — the original
question, the old (wrong) assumption, and the new human answer — and resolves the
conflicts in favor of the new answer. The agent operates under a hard budget; if the
budget is exhausted before all conflicts are resolved, the answer's application is
rolled back and a new human-review bead is created describing what remains, instead
of the agent looping indefinitely.

**Why this priority**: Real stacks conflict. Without automated resolution the
command only handles trivial cases; without a budget and escalation path it can burn
unbounded cost or spin forever — both unacceptable for unattended operation.

**Independent Test**: Construct a stack where a descendant edits the same lines the
correction changes. Run reconcile and verify the conflict is resolved consistently
with the new answer. Then constrain the budget below what resolution needs and
verify the application rolls back and a human bead is filed with the question, both
answers, and the unresolved conflict locations.

**Acceptance Scenarios**:

1. **Given** descendant changes that conflict after the correction is applied,
   **When** the resolution agent runs, **Then** it receives the ledger question, the
   old adopted assumption, and the new human answer as context, and resolves
   conflicts in favor of the new answer.
2. **Given** a resolution budget that is exhausted before all conflicts are
   resolved, **When** the budget limit is hit, **Then** the agent stops immediately,
   the answer's application is rolled back per User Story 2, and a new human-review
   bead is created capturing the question, old and new answers, and remaining
   conflicts.
3. **Given** all conflicts resolved within budget, **When** the pass completes,
   **Then** no conflict markers remain anywhere in the rewritten stack before the
   semantic-dependents pass begins.

---

### User Story 4 - Semantic dependents: fixing code built on the old assumption (Priority: P4)

A descendant change doesn't textually conflict with the correction, but it contains
code written *because of* the old assumption — e.g., a test asserting the old page
size, or a buffer sized to the old limit. After conflicts are settled, a semantic
pass compares the correction's diff against each descendant change's diff, flags
code that depends on the old assumption, and fixes it within that descendant change.

**Why this priority**: Textual conflict resolution alone leaves the stack
*mechanically* consistent but *semantically* wrong. This pass is what makes
reconcile trustworthy rather than merely convenient — but it builds on P1–P3 and is
meaningless without them.

**Independent Test**: Create a descendant change that hard-codes a value derived
from the old assumption in a location the correction does not touch. Run reconcile
and verify the semantic pass flags and fixes the derived value in that descendant
change, and that a descendant with no assumption-derived code is left byte-identical.

**Acceptance Scenarios**:

1. **Given** a descendant change containing code semantically dependent on the old
   assumption but not textually conflicting, **When** the semantic-dependents pass
   runs, **Then** the dependent code is identified and corrected within that
   descendant change.
2. **Given** a descendant change with no relationship to the assumption, **When**
   the semantic pass evaluates it, **Then** the change is left unmodified.
3. **Given** the semantic pass fixed one or more dependents, **When** the answer's
   application finishes, **Then** the gate suite runs against the final heads and
   its result determines whether the answer commits or rolls back.

---

### User Story 5 - Batched sweeps, stack order, and a bounded blast radius (Priority: P5)

A developer answers five ledger entries in one review sweep, then runs
`maverick reconcile` once. The run processes all five changed answers in stack order
— the answer whose recorded change sits earliest in the stack first — so later
corrections apply against already-repaired history. Any answer whose recorded change
is immutable (already pushed, or protected by the project's immutability
configuration) is never touched: it is reported as not reconcilable and flagged for
interactive review instead.

**Why this priority**: Ordering and batching determine correctness when answers
interact, and the immutability boundary is the outer safety wall — but each is only
observable once P1–P4 exist.

**Independent Test**: Answer multiple entries whose recorded changes sit at
different stack depths; run reconcile once and verify processing order is earliest-
first and all answers are handled in the single run. Separately, push the branch so
a recorded change becomes immutable and verify reconcile refuses to touch it and
flags the answer.

**Acceptance Scenarios**:

1. **Given** multiple changed answers from one review sweep, **When** the developer
   runs reconcile once, **Then** all changed answers are processed in that single
   run, ordered earliest recorded change first.
2. **Given** two changed answers where the earlier one's correction changes the
   content the later one's correction applies to, **When** processed in stack order,
   **Then** the later correction applies against the already-corrected history.
3. **Given** a changed answer whose recorded change is immutable, **When** reconcile
   evaluates it, **Then** no history it belongs to is modified, the answer is marked
   as needing interactive review with the reason, and the run continues.
4. **Given** the project's immutability configuration, **When** any reconcile
   operation would modify a change outside the mutable set, **Then** the operation
   is refused before any mutation occurs.

---

### Edge Cases

- **Ledger entry has no recorded change** (legacy entry, or the assumption was
  recorded but never committed): the answer cannot be located in history — mark it
  as needing interactive review and continue.
- **Recorded change no longer exists** (abandoned, or folded away by `maverick
  land` curation): mark as needing interactive review with the stale reference
  noted; never guess at a substitute target.
- **Human answer confirms the adopted assumption**: not a changed answer; the entry
  is left as answered with no history modification.
- **Answer changed more than once before reconcile runs**: the latest human answer
  is the one applied; intermediate answers are not replayed.
- **Working copy has uncommitted work when reconcile starts**: the run must not
  silently mix the developer's in-flight edits into corrections; it refuses to start
  until the working copy is clean.
- **Gate suite fails on the rewritten stack**: treated as any other failure — roll
  back per User Story 2, flag the answer; the gate result before reconcile is
  irrelevant.
- **Two changed answers recorded against the same change**: processed sequentially
  in sweep order; the second applies against the result of the first.
- **Correction produces an empty delta** (the new answer happens to produce
  identical code): the entry is marked reconciled with a note that no code change
  was required; descendants are untouched.
- **Interrupted mid-run** (process killed, machine crash): on the next invocation,
  reconcile detects the incomplete application via the operation history, restores
  the pre-application state for the in-flight answer, and resumes with the
  remaining answers.
- **Concurrent Maverick workflow running in the same checkout**: reconcile refuses
  to start rather than race another workflow's history mutations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a `maverick reconcile` command that operates
  on the current checkout and processes, in a single run, every changed answer.
  Detection MUST be deterministic (no model calls): a changed answer is any
  answered, not-yet-reconciled ledger entry whose human answer text, after
  normalization (whitespace and case), differs from the adopted assumption text.
  Paraphrase false positives are tolerated: they flow through the empty-delta path
  and terminate as no-op reconciliations.
- **FR-002**: The system MUST process changed answers in stack order: the answer
  whose ledger-recorded change is earliest (closest to the immutable base) is
  applied first, and each subsequent answer is applied against the history as
  already repaired by prior answers in the run.
- **FR-003**: For each changed answer, the system MUST produce a correction whose
  end state folds the code delta implied by the new answer into the ledger-recorded
  change itself — creating a child of the recorded change, applying the delta, and
  squashing it into the target, or routing the delta's hunks directly into the
  target when automatic routing suffices — so that history reads as if the new
  answer had been used originally, with no residual fixup change at the tip.
- **FR-004**: The system MUST rely on the version-control system's automatic rebase
  of all descendant changes after the correction is folded in; it MUST NOT
  duplicate, re-create, or manually re-apply descendant changes.
- **FR-005**: When the rebase leaves conflicts, the system MUST resolve them with a
  resolution agent that is given, at minimum: the ledger question, the old adopted
  assumption, the new human answer, and the conflicted content. Resolution MUST
  favor the new answer.
- **FR-006**: The resolution agent MUST operate under an explicit budget expressed
  as a configurable maximum number of resolution rounds per answer (default 3),
  enforced deterministically by the workflow. On budget exhaustion the system MUST
  stop resolution immediately, roll back the answer's application (per FR-009),
  and create a new human-review bead containing the question, old and new answers,
  and the remaining conflict locations. The system MUST NOT retry resolution in a
  loop beyond the budget.
- **FR-007**: After all conflicts are resolved, the system MUST run a
  semantic-dependents pass that compares the correction's diff against each
  descendant change's diff, flags code written because of the old assumption even
  where no textual conflict occurred, and fixes such code within the descendant
  change that introduced it. Descendants with no semantic dependency MUST be left
  unmodified. The semantic-dependents pass MUST operate under its own configurable
  per-answer budget with the same exhaustion semantics as FR-006: on exhaustion,
  roll back the answer's application and create a human-review bead describing the
  remaining unexamined or unfixed dependents.
- **FR-008**: After the semantic-dependents pass, the system MUST re-run the
  project's gate suite against the resulting head(s). A gate failure is a failure
  of the answer's application.
- **FR-009**: Each answer's application MUST be all-or-nothing. Before beginning an
  answer, the system MUST record a restore point in the repository's operation
  history; on any failure during that answer's application (correction, conflict
  resolution, semantic pass, or gate suite), the system MUST restore the repository
  to that restore point and mark the answer as needing interactive review with the
  failure reason. Successfully applied earlier answers in the same run MUST remain
  applied.
- **FR-010**: A failure or rollback of one answer MUST NOT abort the run; the
  system MUST continue with the remaining changed answers.
- **FR-011**: The system MUST modify only mutable (unpushed) changes. Before
  touching any answer, it MUST verify that the recorded change and every descendant
  the application would rewrite are mutable under the project's immutability
  configuration; if any are not, the answer MUST be skipped, marked as needing
  interactive review with the reason, and no mutation performed for it.
- **FR-012**: The system MUST honor the project's immutability configuration as the
  boundary of the blast radius: no reconcile operation may rewrite, rebase, or
  otherwise alter any change outside the mutable set, under any code path
  (including rollback).
- **FR-013**: On successful application, the system MUST update the ledger entry to
  a reconciled state that records what was applied (the answer version applied and
  the resulting change identity), so re-running reconcile does not reprocess it.
- **FR-014**: The system MUST refuse to start when the working copy has uncommitted
  modifications or another Maverick workflow is operating in the same checkout, and
  MUST say why.
- **FR-015**: If a changed answer's recorded change cannot be located (missing
  reference, abandoned change), the system MUST report the answer as skipped,
  mark it as needing interactive review, and continue, without guessing an
  alternative target.
- **FR-016**: On an invocation that finds an interrupted prior run, the system MUST
  first restore the in-flight answer's restore point before processing anything
  else.
- **FR-017**: Answers marked as needing interactive review MUST be excluded from
  subsequent reconcile runs until a human edits or re-confirms the answer (or
  resolves the associated escalation bead); reconcile MUST never re-attempt them
  automatically.
- **FR-018**: The command MUST support a `--dry-run` mode that reports the changed
  answers it would process, each answer's target change, mutability status, and
  the processing order, performing zero repository, ledger, or bead mutations.
  Dry-run exits successfully (zero) whenever preconditions hold, regardless of
  predicted per-answer statuses.
- **FR-019**: At the end of a run, the system MUST report a per-answer summary in
  which every processed answer has exactly one terminal status — reconciled,
  skipped (with reason), or needs interactive review (with reason) — plus the gate
  suite outcome for applied answers. Skipped means no mutation was attempted
  (immutable or unlocatable target); needs interactive review means the
  application was attempted and rolled back. Both non-reconciled statuses record
  the needs-interactive-review ledger state, so the re-arm rule (FR-017) applies
  to both. The command MUST exit non-zero if any answer
  ended in a non-reconciled state, and zero otherwise (including the nothing-to-do
  case).
- **FR-020**: All agent involvement (conflict resolution, semantic-dependents
  analysis and fixes) MUST be limited to judgment over content; deterministic
  operations — history rewrites, rebases, rollback, gate execution, ledger updates,
  bead creation — MUST be owned by the workflow, not the agents.

### Key Entities

- **Changed Answer**: An answered assumption-ledger entry, not yet reconciled and
  not awaiting interactive review, whose normalized human answer text differs from
  the adopted assumption text. Carries the question, old adopted assumption, new
  human answer, severity, and the ledger-recorded change identity.
- **Correction**: The code delta that transforms the recorded change's content from
  the old assumption's behavior to the new answer's behavior, folded into the
  recorded change itself.
- **Reconcile Run**: One invocation processing the full batch of changed answers
  from a review sweep, in stack order, producing a per-answer summary.
- **Restore Point**: The repository operation-history snapshot captured immediately
  before an answer's application begins; the target of rollback for that answer.
- **Resolution Budget**: The configured cap on agent effort per answer, expressed
  as a maximum number of rounds — one cap for conflict resolution (default 3
  rounds) and one for the semantic-dependents pass; exhaustion of either triggers
  rollback and human escalation, never retry loops.
- **Escalation Bead**: A new human-review work item created when resolution budget
  is exhausted (or an application otherwise needs a human), containing the
  question, both answers, and what remains unresolved.
- **Semantic Dependent**: Code in a descendant change written because of the old
  assumption without textually conflicting with the correction; identified by
  comparing the correction diff against the descendant's diff.
- **Mutable Set**: The changes reconcile is permitted to rewrite — unpushed changes
  within the bounds of the project's immutability configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a changed answer whose correction rebases cleanly, reconcile
  completes end-to-end with zero human intervention, and inspection of history
  shows the fix inside the originally recorded change with no separate fixup
  change at the tip.
- **SC-002**: After any failed answer application, the repository (commit graph,
  working copy, and ledger code state) is indistinguishable from its state at that
  answer's restore point — verified byte-for-byte on the affected files — in 100%
  of failure scenarios exercised.
- **SC-003**: Zero reconcile operations modify pushed or otherwise immutable
  history, across every code path including rollback, in 100% of runs.
- **SC-004**: Conflict resolution cost per answer never exceeds the configured
  budget; every budget exhaustion produces exactly one human-review bead and one
  rolled-back answer, never an unbounded retry.
- **SC-005**: A single reconcile invocation after a review sweep handles all
  changed answers from that sweep; developers never need one invocation per
  answer.
- **SC-006**: Every answer reported as reconciled has a passing gate suite on the
  resulting head at the moment of that answer's completion.
- **SC-007**: In a seeded evaluation where descendant changes contain known
  semantically dependent code (values or logic derived from the old assumption),
  the semantic-dependents pass identifies and fixes at least 80% of the seeded
  dependents while leaving unrelated descendants unmodified.
- **SC-008**: Re-running reconcile immediately after a fully successful run makes
  zero history modifications (idempotence).

## Assumptions

- **"Changed answer" definition**: resolved by clarification — deterministic
  normalized text comparison (see FR-001). Waived entries and answers whose
  normalized text matches the adopted assumption never trigger reconciliation.
- **Restore-point granularity**: "restores the repo to the pre-reconcile
  operation" is interpreted per answer — the snapshot taken immediately before
  that answer's application — so a batch preserves earlier answers' successful
  applications (consistent with per-answer all-or-nothing and the constitution's
  partial-progress principle). A full-run restore would make "each answer's
  application is all-or-nothing" meaningless for batches.
- **Trigger model**: reconcile is an explicit developer-invoked command run after
  a review sweep; nothing runs it automatically. `maverick review` may hint that
  reconciliation is pending.
- **Budget shape**: resolved by clarification — round-based caps enforced
  deterministically by the workflow: a configurable maximum number of resolution
  rounds per answer (default 3) for conflict resolution, and a separate
  configurable cap for the semantic-dependents pass (see FR-006, FR-007).
- **Gate suite**: "the gate suite" is the project's existing configured gate
  checks (the same suite the fly workflow runs after implementing a bead), run
  against the post-reconcile head(s).
- **Sweep scoping**: "batch per human sweep" means one invocation drains all
  currently pending changed answers; there is no persistent sweep identity beyond
  the set of pending changed answers at invocation time.
- **Severity-agnostic**: any changed answer is reconcilable regardless of severity
  (low/medium/high); severity continues to govern land-gating, not reconcile
  eligibility.
- **Latest answer wins**: if an answer is edited multiple times before reconcile
  runs, only the most recent answer is applied.

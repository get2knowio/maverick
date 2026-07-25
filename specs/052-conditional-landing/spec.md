# Feature Specification: Conditional Landing on the Assumption Frontier

**Feature Branch**: `052-conditional-landing`
**Created**: 2026-07-24
**Status**: Draft
**Input**: User description: "Extend land with a first-class \"verified conditional on unresolved assumptions\" state. A spec may land (curation, push to git, PR creation) only when its assumption frontier is empty or every remaining entry has been explicitly waived; medium- and high-severity entries enforce the blocking semantics defined by the ledger. The land report enumerates resolved, waived, and open assumptions with their provenance (question, adopted answer, final answer, affected changes). Additionally, answers arriving while fly is running trigger reconcile without stopping the drain loop (mid-flight answering), so a returning human can unblock earlier specs while later ones are still being implemented."

## Overview

Today, `maverick land` blocks on open medium/high assumption-ledger entries
(spec 049) and `maverick reconcile` retroactively folds changed human answers
back into history (spec 051), but landing itself is a binary pass/fail with no
record of *what risk posture the landed work carries*. This feature makes that
posture first-class: every land outcome is classified as **verified** (every
assumption the spec adopted was answered), **conditionally verified** (the
human explicitly waived what remains — accepted, audited risk), or **blocked**
(open questions remain; landing refuses to proceed). The land report becomes
the audit trail: every assumption the spec adopted is enumerated with its
question, the answer the agent adopted, the final human answer, and the
changes that embody it.

Separately, the feedback loop between human answers and running work is
closed: a human who returns mid-run and answers assumptions from earlier specs
no longer waits for the run to finish — their answers are detected and
reconciled while later beads are still being implemented, without stopping the
drain loop.

## Clarifications

### Session 2026-07-24

- Q: Do open low-severity entries block landing, or remain advisory at land as
  in spec 049? → A: They block — every open entry must be answered or waived
  to land, regardless of severity; low remains non-blocking everywhere outside
  the land boundary.
- Q: Does an answered entry whose changed answer is not yet reconciled block
  landing? → A: Yes — it blocks until reconciled or terminally marked;
  entries in a terminal reconcile state are annotated in the report instead
  of blocking.
- Q: What timing guarantee applies to mid-flight answer detection and
  processing? → A: Detection at least at every bead boundary; every answer
  detected before the run's final bead completes is reconciled or escalated
  before the run completes.
- Q: Is there a bulk waive path to keep the stricter gate workable? → A: Yes —
  waiving supports one invocation scoped to a spec and filtered by severity
  (default low), with the shared reason and waiver metadata recorded on each
  affected entry individually.
- Q: Are mid-flight reconcile candidates scoped to the run's specs or
  repo-wide? → A: Repo-wide — the same detection predicate as standalone
  reconcile, so there is exactly one notion of "pending changed answer".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Land is gated on the assumption frontier with an explicit verification state (Priority: P1)

A developer finishes a spec's implementation and runs `maverick land`. Before
any curation, push, or PR creation happens, the system evaluates the spec's
assumption frontier — every ledger entry the spec owns that has been neither
answered nor waived. If the frontier is non-empty, landing refuses entirely:
nothing is curated, pushed, or opened as a PR, and the developer is shown
exactly which entries stand in the way and how to resolve each one. If the
frontier is empty, landing proceeds and the outcome is explicitly classified:
**verified** when every entry the spec adopted was answered, or
**conditionally verified on unresolved assumptions** when one or more entries
were waived rather than answered. The classification is durable — it appears
in the land output and travels with the landed result (including the PR
description when one is created), so reviewers downstream know whether they
are looking at fully-resolved work or work carrying explicitly accepted risk.

**Why this priority**: This is the core contract of the feature — landing is
the moment assumption debt either gets settled or gets explicitly accepted,
and today that moment is invisible. Without the gate and the state, the report
(US2) has nothing authoritative to describe and mid-flight answering (US3) has
no destination that honors it.

**Independent Test**: Create a spec with three ledger entries (one low, one
medium, one high). Attempt to land with all three open — landing must refuse.
Answer two and waive one — landing must succeed and be classified
"conditionally verified". Answer all three — landing must succeed as
"verified". No flag or environment variable may bypass the gate at any point.

**Acceptance Scenarios**:

1. **Given** a spec with at least one open (unanswered, unwaived) assumption
   entry of any severity, **When** the user runs `maverick land`, **Then** the
   command performs no curation, no push, and no PR creation, lists each open
   entry with a resolution hint (`maverick review <id>`), and exits non-zero.
2. **Given** a spec whose every owned entry is answered, **When** the user
   lands, **Then** landing completes and the outcome is classified
   **verified**, visible in the command output.
3. **Given** a spec whose remaining entries are all explicitly waived (at
   least one waived, none open), **When** the user lands, **Then** landing
   completes and the outcome is classified **conditionally verified on
   unresolved assumptions**, visible in the command output and in the PR
   description when landing creates a PR.
4. **Given** a spec with an answered entry whose current answer has changed
   and has not yet been reconciled into history (and is not terminally marked
   by reconcile), **When** the user lands, **Then** landing refuses and
   directs the user to run `maverick reconcile` first — because landing would
   make the affected changes immutable and permanently strand the correction.
5. **Given** a spec with zero assumption entries, **When** the user lands,
   **Then** landing completes as **verified** and the report states that no
   assumptions were adopted.
6. **Given** a blocked land, **When** the user resolves every listed entry via
   `maverick review` (answers and/or waivers) and re-runs land, **Then**
   landing proceeds with the appropriate classification and no other step is
   required.

---

### User Story 2 - Land report enumerates every assumption with full provenance (Priority: P2)

Whenever land evaluates a spec — whether it proceeds, proceeds conditionally,
or blocks — it produces a report enumerating every assumption entry the spec
owns, grouped into **resolved**, **waived**, and **open**. Each entry shows
its provenance: the question the agent faced, the answer it adopted to keep
working, the final human answer (where one was given), the severity, and the
affected changes (the change identifiers where the assumption was embodied,
including any reconciliation correction). Waived entries additionally show
who waived, when, and why. A reviewer reading the report alone — without
querying any other tool — can understand exactly what risk was accepted and
where it lives in the history.

**Why this priority**: The verification state from US1 is only trustworthy if
its evidence is inspectable. The report is what turns "conditionally verified"
from a label into an auditable statement, and it is what PR reviewers and
returning humans actually read.

**Independent Test**: Land a spec that has one answered entry (whose final
answer differs from the adopted answer and was reconciled), one waived entry,
and — in a separate blocked-land attempt — one open entry. Verify the report
groups them correctly and that each row carries question, adopted answer,
final answer, and affected-change identifiers, with waiver metadata on the
waived row.

**Acceptance Scenarios**:

1. **Given** a spec with answered, waived, and open entries, **When** land
   runs (and blocks on the open entry), **Then** the report shows all three
   groups with each entry's question, adopted answer, final answer (if any),
   severity, and affected changes.
2. **Given** an entry whose human answer differed from the adopted answer and
   was reconciled into history, **When** the land report is produced, **Then**
   the entry appears as resolved and its affected changes include both the
   original change(s) and the reconciliation correction.
3. **Given** a conditional land that creates a PR, **When** the PR is opened,
   **Then** its description contains the conditional classification and the
   enumeration of waived entries with their provenance.
4. **Given** any land evaluation (including `--dry-run`), **When** the report
   is produced, **Then** it is also persisted with the run's metadata so the
   audit trail survives the terminal session.

---

### User Story 3 - Mid-flight answers trigger reconcile without stopping the drain loop (Priority: P3)

A long `maverick fly` run is implementing beads across several specs. While it
runs, a human returns, reviews the assumption queue, and answers (or waives)
entries recorded against earlier specs using `maverick review`. The running
fly detects these resolutions on its own — the human issues no additional
command — and, for answers that change what the code embodies, triggers the
same reconcile behavior that `maverick reconcile` performs: same detection
rules, same ordering, same safety guards, same escalation on failure. The
drain loop never stops or pauses waiting for this: later beads keep being
implemented while the earlier specs' corrections are folded in, and a
high-severity resolution releases its downstream block so a later spec's work
can become ready within the same run. By the time the run completes, the
earlier specs are landable without a separate reconcile pass.

**Why this priority**: This closes the human-latency loop — today an answer
given mid-run sits inert until someone runs reconcile after the fact. It is
last in priority because US1/US2 define the landing contract it feeds, and
because a standalone `maverick reconcile` already provides a manual fallback
for the same outcome.

**Independent Test**: Start a fly run over two specs' beads. While later beads
are still implementing, answer a changed-answer entry and waive another from
the earlier spec. Verify the run does not stop, the changed answer is
reconciled before run completion, the earlier spec subsequently lands
without a manual reconcile, and later beads continued to completion.

**Acceptance Scenarios**:

1. **Given** a running fly and a human answer to an earlier spec's entry whose
   answer changed, **When** the answer is recorded, **Then** the run detects
   it and reconciles it before the run completes, with no operator action
   beyond `maverick review` and no pause in bead implementation.
2. **Given** a high-severity entry blocking a later spec's epic, **When** the
   human answers or waives it mid-run, **Then** the downstream work becomes
   ready and the same run picks it up.
3. **Given** a mid-flight reconcile attempt that fails or exhausts its
   budgets, **When** the failure occurs, **Then** it escalates exactly as
   standalone reconcile does (human-triage bead, terminal marking) and the
   fly run continues unharmed.
4. **Given** answers arriving while a mid-flight reconcile pass is already in
   progress, **When** the pass completes, **Then** the newly arrived answers
   are processed in a subsequent pass within the same run — none are dropped.
5. **Given** a graceful stop (first Ctrl-C) during a run with unprocessed
   mid-flight answers, **When** the run exits, **Then** repository and ledger
   state are consistent (any in-progress reconcile completed or fully rolled
   back) and the unprocessed answers are picked up by the next reconcile or
   fly run.
6. **Given** an entry reconciled mid-flight, **When** land or a later
   standalone reconcile runs, **Then** the entry is not reconciled a second
   time.

---

### Edge Cases

- **All entries waived, none answered**: the spec lands as conditionally
  verified; the report makes the fully-waived posture explicit.
- **Answer arrives for the spec currently being implemented** (not an earlier
  one): reconcile safety rules still apply — the correction must never
  interleave with in-progress bead work on the same spec; it waits for a safe
  point or falls to the next pass.
- **Entry answered after its spec already landed**: the affected changes are
  now immutable; the standalone reconcile mutability guard handles it
  (skip + terminal mark). The land gate's pending-reconciliation check
  (US1, scenario 4) exists precisely to make this rare.
- **Legacy escalation beads** (pre-ledger, treated as medium severity): they
  are part of the frontier and the report, in a legacy bucket consistent with
  existing brief reporting.
- **Waiver of a high-severity entry mid-run**: releases the downstream block
  just as an answer does; no reconcile is triggered (nothing changed in what
  the code embodies), but the frontier and report reflect the waiver.
- **Reconcile terminally marked an entry** (`skipped` /
  `needs-interactive-review`): the entry does not block landing on
  reconciliation grounds — but the report annotates its terminal state so the
  unresolved correction is visible to reviewers.
- **Multiple fly runs or a fly run plus a standalone reconcile overlapping**:
  detection and idempotence guards (existing ledger reconcile state) must
  prevent double-application; the second processor sees the entry already
  reconciled or in a terminal state.
- **Run with no assumptions at all**: land reports "no assumptions adopted"
  and classifies verified; fly's mid-flight detection idles at zero cost to
  throughput.
- **Bulk waive sweeps up an entry the human meant to answer**: bulk waiving
  is severity-filtered and spec-scoped precisely to bound this risk; each
  entry still records the shared reason individually, and a waived entry
  that is later answered re-enters reconcile detection per spec 051's
  re-answer behavior.

## Requirements *(mandatory)*

### Functional Requirements

**Frontier & gate**

- **FR-001**: The system MUST compute a spec's assumption frontier at land
  time: every ledger entry owned by that spec (including legacy escalation
  beads, treated as medium severity) that is neither answered nor waived.
- **FR-002**: Land MUST proceed to curation, push, or PR creation only when
  the frontier is empty — i.e., every owned entry is answered or explicitly
  waived (a spec with no entries trivially qualifies). An open entry of any
  severity blocks landing. There is no bypass flag; answering or waiving via
  `maverick review` is the only path through. (This extends the existing gate:
  low-severity entries, previously advisory at land, now require an explicit
  waiver or answer to land — they remain non-blocking everywhere else.)
- **FR-003**: Medium- and high-severity entries MUST retain the blocking
  semantics defined by the assumption ledger (spec 049): review-only
  resolution, and high severity's blocking dependency on the next spec's epic.
- **FR-004**: A blocked land MUST perform no partial landing work — no
  curation, no push, no PR — MUST present the report (FR-008) with a
  per-entry resolution hint, and MUST exit non-zero. `--dry-run` MUST evaluate
  and display the same result while deferring the non-zero exit to the end of
  the preview, consistent with the existing gate's behavior.
- **FR-005**: Land MUST classify every successful landing as exactly one of:
  **verified** — every owned entry answered (or no entries exist); or
  **conditionally verified on unresolved assumptions** — no open entries, at
  least one waived. The classification MUST be recorded durably with the land
  outcome, shown in the command output, and included in the PR description
  when landing creates a PR.
- **FR-006**: Land MUST treat an answered entry whose current answer is
  detected as pending reconciliation (per spec 051's detection rules, with no
  terminal reconcile state) as unresolved for gating purposes: landing blocks
  and directs the user to reconcile first, because landing would make the
  affected changes immutable. Entries in a terminal reconcile state
  (`skipped`, `needs-interactive-review`) MUST NOT block on these grounds but
  MUST be annotated in the report.

**Land report**

- **FR-007**: The land report MUST enumerate every entry owned by the spec,
  grouped as **resolved** (answered, including reconciled), **waived**, and
  **open**, with per-entry provenance: question, adopted answer, final human
  answer (where given), severity, and affected changes — the change
  identifier(s) stamped on the entry plus any reconciliation correction's
  identifier. Waived entries MUST include who waived, when, and why.
- **FR-008**: The report MUST be produced on every land evaluation — blocked,
  verified, conditional, and `--dry-run` — displayed in the command output,
  persisted with the run's land metadata, and (for the waived/resolved
  enumeration and classification) included in the PR description when landing
  creates a PR.

**Mid-flight answering**

- **FR-009**: A running fly MUST detect answers and waivers recorded while
  the run is in progress, without any operator action beyond `maverick
  review` and without stopping or restarting the run. Detection MUST occur at
  least at every bead boundary, and every answer detected before the run's
  final bead completes MUST be processed (reconciled or escalated) before the
  run completes.
- **FR-010**: For detected answers that qualify as changed under spec 051's
  detection rules, the run MUST trigger reconcile with behavior equivalent to
  standalone `maverick reconcile`: same repo-wide detection predicate (not
  scoped to the run's specs), same earliest-first ordering, same mutability
  guard, same transactional rollback-on-failure, and same escalation
  (human-triage bead plus terminal marking) on exhausted budgets or failure.
- **FR-011**: Mid-flight reconcile MUST NOT stop, pause, or starve the drain
  loop: bead implementation continues and the run completes all otherwise
  reachable work. Reconcile MUST NOT mutate history in a way that can corrupt
  an in-progress bead's work; corrections apply only at points where the two
  cannot interleave destructively.
- **FR-012**: When a mid-flight answer or waiver resolves a high-severity
  entry that blocks a later spec's epic, the downstream work MUST become
  ready and be eligible for pickup within the same run.
- **FR-013**: A mid-flight reconcile failure MUST NOT crash or abort the fly
  run; after escalation the drain loop proceeds.
- **FR-014**: Answers arriving while a mid-flight reconcile pass is in
  progress MUST be processed in a subsequent pass within the same run; no
  detected answer is ever dropped. Answers left unprocessed at run exit
  (including graceful stop) MUST remain detectable by subsequent reconcile or
  fly runs.
- **FR-015**: Reconciliation MUST be applied at most once per answered entry
  across mid-flight and standalone paths: an entry reconciled mid-flight is
  not re-reconciled at land time or by a later `maverick reconcile`, and
  concurrent processors observe each other's terminal/reconciled markings.

**Waiving at scale**

- **FR-016**: Waiving MUST support a single invocation that waives all open
  entries owned by one spec, filtered by severity (defaulting to
  low-severity only), with one shared reason supplied once and the full
  waiver metadata (who, when, why) recorded on each affected entry
  individually. Bulk-waived entries appear in the land report identically to
  individually waived ones. Per-entry waiving remains available.

### Key Entities

- **Assumption frontier**: the set of ledger entries standing between the
  work and a landable state: entries that are neither answered nor waived,
  plus answered entries whose changed answer is still pending reconciliation
  (FR-006). Empty frontier is the precondition for landing.
- **Verification state**: the classification attached to a land outcome —
  *verified*, *conditionally verified on unresolved assumptions*, or
  *blocked* (evaluation-only; nothing landed). Durable, human-visible, and
  attached to the PR when one is created.
- **Land report entry**: the per-assumption provenance record — question,
  adopted answer, final answer, severity, status (resolved / waived / open),
  waiver metadata, affected change identifiers (including reconciliation
  corrections).
- **Mid-flight answer event**: a human answer or waiver recorded while a fly
  run is active, which the run detects and routes to reconcile (answers with
  changed content) and/or readiness updates (high-severity resolutions).
- **Reconcile pass**: one batch of mid-flight reconciliation processing —
  detection through correction/escalation — scheduled so it never destructively
  interleaves with in-progress bead work.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero specs land with an open assumption entry: in any state
  where at least one owned entry is unanswered and unwaived, 100% of land
  attempts refuse before any curation, push, or PR creation, and no
  flag-based bypass exists.
- **SC-002**: Every successful land is classified verified or conditionally
  verified, and 100% of the spec's owned entries appear in the land report
  with question, adopted answer, final answer (where given), and affected
  changes — verifiable from the report alone with no other tool.
- **SC-003**: A reviewer can determine the complete accepted-risk posture of a
  conditionally verified landing (which questions were waived, by whom, why,
  and where the assumption lives in history) from the land report or PR
  description alone.
- **SC-004**: A human who answers an earlier spec's assumptions during a fly
  run needs zero commands beyond `maverick review`: any answer recorded
  before the run's final bead completes is reconciled (or explicitly
  escalated) before the run completes, and the earlier spec lands afterward
  without a standalone reconcile invocation.
- **SC-005**: Mid-flight reconciliation costs no forward progress: in a run
  where answers arrive mid-flight, every bead that would have completed
  without them still completes, and the run does not stop or restart.
- **SC-006**: No answer is lost or double-applied: across any combination of
  mid-flight processing, run interruption, and standalone reconcile, each
  changed answer is folded into history exactly once or carries an explicit
  terminal escalation.

## Assumptions

- **Gate strictness for low severity** *(confirmed, Clarifications
  2026-07-24)*: at land time, *every* open entry blocks regardless of
  severity, so low-severity entries must be answered or waived to land. This
  deliberately supersedes spec 049's low-is-advisory behavior *at the land
  boundary only*; low entries remain non-blocking for bead readiness and
  implementation. The clause about medium/high refers to their additional
  ledger semantics (review-only resolution, high's downstream blocking edge),
  which are unchanged. FR-016's bulk waive keeps this workable at scale.
- **Meaning of "conditionally verified"**: the state applies when landing
  succeeds with at least one waived (unanswered) entry; a spec whose entries
  are all answered lands as plain "verified". Waivers are the audited
  mechanism that makes remaining uncertainty acceptable.
- **Pending-reconciliation blocks landing** *(confirmed, Clarifications
  2026-07-24)*: an answered-but-changed entry not yet reconciled (and not
  terminally marked) blocks land (FR-006). Rationale: pushing makes changes
  immutable, which would permanently strand the correction; blocking here is
  what keeps "affected changes" in the report truthful. Terminal reconcile
  states do not block, since reconcile has already concluded human
  intervention is required.
- **Mid-flight scheduling** *(cadence confirmed, Clarifications 2026-07-24)*:
  detection happens at least at every bead boundary, and everything detected
  before the final bead completes is processed before the run exits; within
  those bounds, the exact scheduling mechanism is left to planning, provided
  reconcile never stops the drain loop and never destructively interleaves
  with in-progress bead work.
- **Report persistence**: the land report is persisted alongside existing
  per-run land metadata; no new user-facing storage surface is introduced.
- **PR creation remains manual this slice**: landing does not itself push or
  open PRs today (all land modes print next-step hints). The "included in
  the PR description" requirements are satisfied by generating a PR-ready
  report artifact and referencing it from the mode hints (e.g.
  `gh pr create --body-file …`), so the classification and provenance travel
  with the PR the user opens; if landing later automates PR creation, the
  same artifact becomes the PR body directly.
- **Waivers mid-flight**: a waiver never triggers reconcile (the code embodies
  the adopted answer, which stands), but it updates the frontier and releases
  high-severity downstream blocks identically to an answer.
- **Scope**: this feature does not change how assumptions are recorded (spec
  049) or how reconcile corrects history (spec 051); it changes when landing
  is permitted, how the outcome is described, and when reconcile is triggered.

## Dependencies

- **Spec 049 (assumption ledger)**: entry data model, severity policy, waiver
  mechanism, `maverick review` resolution flow, legacy escalation-bead
  handling.
- **Spec 051 (reconcile changed answers)**: changed-answer detection,
  ordering, mutability guard, transaction model, escalation, and the
  per-entry reconcile lifecycle states this feature keys on (FR-006, FR-010,
  FR-015).

# Feature Specification: Assumption Ledger

**Feature Branch**: `049-assumption-ledger`
**Created**: 2026-07-23
**Status**: Draft
**Input**: User description: "Extend Maverick's assumption beads into an assumption ledger. Each entry records the question, the adopted answer, the alternatives considered, a severity (low, medium, high), the owning spec, and the jj change ID(s) embodying the assumption — stamped when the bead's work is committed. Severity drives escalation: low is advisory only; medium blocks the owning spec's land until answered or waived; high additionally becomes a blocking dependency of the next spec's epic, pausing the run at the spec boundary. The human's queue is surfaced through bd (bd ready), with discovered-from edges linking each assumption to the work that spawned it. Reporting includes per-spec assumption counts as a spec-quality signal. This spec covers the data model, recording path, severity policy wiring, and queue surfacing — not the reconcile mechanics."

## Clarifications

### Session 2026-07-23

- Q: How is the owning spec determined for a recorded assumption? → A: Derived automatically from the bead's parent epic via the epic↔spec mapping created at refuel; agents never state it.
- Q: How does a high-severity assumption "pause the run at the spec boundary"? → A: Dependency-only — the next spec's epic gets a bd blocking dependency on the assumption, so work past the boundary never becomes ready; no separate in-run pause machinery.
- Q: Can land bypass an assumption block (e.g., a force flag)? → A: No bypass flag; answering or waiving each blocking entry is the only way past — the waiver is the audited escape hatch.
- Q: How do assumptions travel from agent to ledger? → A: Batch-at-step-end — assumptions are fields in the agent's structured result payload; the workflow creates the ledger entries deterministically after the step completes.
- Q: Where do per-spec assumption counts surface? → A: Extend `maverick brief` (the existing bead-status surface) with a per-spec assumption counts section; no new reporting command.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assumptions become structured ledger entries (Priority: P1)

During an autonomous run, an agent hits a decision it cannot resolve from the spec
or the code — for example, "should the retry limit apply per bead or per run?" It
adopts the most defensible answer and keeps working. Instead of that decision
evaporating into a prose escalation note, the system records a structured ledger
entry: the question, the adopted answer, the alternatives it considered, a
severity, and the spec that owns the decision. When the bead's work is committed,
the entry is stamped with the change identifier(s) that embody the assumption. A
discovered-from edge links the entry back to the work item that spawned it.

**Why this priority**: The ledger entry is the feature's atom. Every other
behavior — escalation policy, queue surfacing, reporting — reads from it. Without
structured entries there is nothing to escalate, surface, or count.

**Independent Test**: Run a workflow where an agent adopts at least one
assumption, then inspect the resulting work-item store: a ledger entry exists
with all six fields populated, a discovered-from edge to the spawning work item,
and (after commit) the change identifier(s) of the commits that embody it.

**Acceptance Scenarios**:

1. **Given** an agent implementing a bead adopts an assumption, **When** it
   records the assumption, **Then** a ledger entry is created containing the
   question, the adopted answer, at least one alternative considered, a severity
   of low, medium, or high, and the owning spec.
2. **Given** a ledger entry recorded against a bead, **When** that bead's work is
   committed, **Then** the entry is stamped with the change identifier(s) of the
   commit(s) embodying the assumption.
3. **Given** a ledger entry, **When** a user inspects it, **Then** a
   discovered-from edge identifies the work item whose execution spawned the
   assumption.
4. **Given** an assumption whose bead's work is never committed (bead fails or
   run is cancelled), **When** the run ends, **Then** the ledger entry still
   exists with its question/answer/severity fields but carries no change stamp,
   and is identifiable as unstamped.

---

### User Story 2 - Severity drives escalation policy (Priority: P2)

A run may adopt many assumptions; not all deserve to stop the line. The recording
agent assigns a severity, and the workflow enforces a graduated policy: low
severity is advisory only — visible in the ledger and reports, never blocking.
Medium severity blocks the owning spec's land step until a human answers or
waives the assumption. High severity additionally becomes a blocking dependency
of the next spec's epic, so the run pauses at the spec boundary rather than
compounding a risky guess across specs.

**Why this priority**: Severity policy is the behavioral payoff of the ledger —
it converts recorded doubt into proportionate friction. It depends on User
Story 1's data model existing.

**Independent Test**: Create three assumptions (one per severity) against a spec,
then attempt to land that spec and start the next one. Land is blocked by the
medium and high entries but not the low one; the next spec's epic cannot start
while the high entry is open.

**Acceptance Scenarios**:

1. **Given** a spec with only low-severity open assumptions, **When** the user
   lands the spec, **Then** the land proceeds and the assumptions are reported as
   advisories.
2. **Given** a spec with an open medium-severity assumption, **When** the user
   attempts to land it, **Then** the land is blocked with a message identifying
   the blocking assumption(s), and succeeds once each is answered or waived.
3. **Given** a spec with an open high-severity assumption, **When** the run
   reaches the boundary to the next spec, **Then** the next spec's epic carries a
   blocking dependency on the assumption, so none of that spec's work becomes
   ready until the assumption is answered or waived.
4. **Given** a medium-severity assumption a human decides is acceptable risk,
   **When** they waive it, **Then** the waiver (who/when/why) is recorded on the
   entry and the entry stops blocking land.
5. **Given** a high-severity assumption recorded against the final spec of a run
   (no next spec exists), **When** the run completes, **Then** the entry behaves
   like a medium-severity entry: it blocks that spec's land but there is no
   next epic to block.

---

### User Story 3 - The human's queue surfaces through the work-item tool (Priority: P3)

The human tending an autonomous run should not need a new inbox. Open assumptions
addressed to them appear in their existing ready-work queue (`bd ready`), each
entry navigable to its question, adopted answer, alternatives, severity, and the
discovered-from work that spawned it — enough context to answer or waive without
archaeology.

**Why this priority**: Queue surfacing makes the ledger actionable. It builds
directly on the entries from User Story 1 and gives the escalation policy of
User Story 2 its resolution path.

**Independent Test**: Record assumptions of each severity, then list the human's
ready queue: medium and high entries appear as ready human work items; each shows
enough context (or links to it) to decide; resolving one removes it from the
queue and unblocks whatever it was blocking.

**Acceptance Scenarios**:

1. **Given** open medium- or high-severity assumptions, **When** the human lists
   their ready work, **Then** each open assumption appears as a ready work item
   assigned to them.
2. **Given** an assumption in the queue, **When** the human opens it, **Then**
   they can see the question, adopted answer, alternatives considered, severity,
   owning spec, and follow the discovered-from edge to the spawning work.
3. **Given** the human answers an assumption from the queue, **When** the answer
   is recorded, **Then** the entry leaves the ready queue and any land or epic it
   was blocking becomes unblocked.

---

### User Story 4 - Per-spec assumption counts as a quality signal (Priority: P4)

A spec that generated eleven assumptions was underspecified; one that generated
zero was either crisp or trivially small. Reporting surfaces per-spec assumption
counts (total and by severity) so the team can treat assumption volume as a
spec-quality signal and improve their specification practice over time.

**Why this priority**: Pure read-side value on top of data the earlier stories
already persist. Useful, but nothing else depends on it.

**Independent Test**: After runs over two specs with differing assumption
volumes, request the report: each spec shows its assumption count broken down by
severity and open/resolved status.

**Acceptance Scenarios**:

1. **Given** completed work across multiple specs, **When** the user views the
   assumption report, **Then** each spec shows its total assumption count and a
   breakdown by severity.
2. **Given** a spec with zero assumptions, **When** the report is viewed,
   **Then** the spec appears with a zero count (absence is itself a signal).

---

### Edge Cases

- **Work spanning multiple commits**: an assumption embodied by several commits
  is stamped with every relevant change identifier, not just the last one.
- **Commit succeeds but stamping fails**: stamping must not lose the commit;
  the entry remains unstamped and the gap is reported rather than silently
  dropped.
- **Duplicate recording**: an agent recording the same question twice within one
  bead should not create two open queue items for the human; re-recording
  updates or references the existing entry.
- **Severity omitted or invalid at recording time**: the entry is not rejected
  (losing the assumption is worse); it defaults to medium — the
  blocks-owning-spec level — and the defaulting is visible on the entry.
- **High-severity assumption on the last spec**: no next epic exists to block;
  degrades to medium behavior (blocks land only) — see US2 scenario 5.
- **Assumption answered mid-run**: if the human answers a high-severity entry
  while a run is stopped at the spec boundary, the blocking dependency clears
  and the next ready-work query serves the next spec's work — no manual
  dependency surgery or run-state repair is required.
- **Pre-existing escalation beads**: today's review-exhaustion escalation beads
  continue to work; entries lacking the new structured fields must not break
  queue listing or reporting.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record each adopted assumption as a structured
  ledger entry containing: the question, the adopted answer, the alternatives
  considered, a severity (one of low, medium, high), and the owning spec. The
  owning spec is derived automatically from the bead's parent epic (via the
  epic↔spec mapping established at refuel); recording agents do not declare it.
- **FR-002**: The system MUST stamp each ledger entry with the change
  identifier(s) embodying the assumption at the time the associated bead's work
  is committed, supporting multiple identifiers per entry.
- **FR-003**: The system MUST link each ledger entry to the work item that
  spawned it via a discovered-from edge.
- **FR-004**: The system MUST allow agents to record assumptions during
  autonomous execution without interrupting the current bead's work — recording
  is non-blocking for the recording agent. Assumptions are carried as part of
  the agent's structured result for the step; the workflow (not the agent)
  creates the ledger entries deterministically after the step completes.
- **FR-005**: The system MUST treat low-severity entries as advisory only: they
  never block land, never block a subsequent spec, and appear in reporting.
- **FR-006**: The system MUST block the owning spec's land while any
  medium- or high-severity entry owned by that spec is neither answered nor
  waived, and MUST identify the blocking entries in the land failure message.
  No bypass flag exists: answering or waiving each blocking entry is the only
  way to proceed (the waiver is the audited escape hatch).
- **FR-007**: For each open high-severity entry, the system MUST additionally
  register a blocking dependency from the next spec's epic onto the entry in the
  work-item store. The pause is dependency-only: work past the spec boundary
  simply never becomes ready while the entry is open — no separate in-run pause
  state is introduced, and the behavior is identical whether the next spec is
  worked in the same run or a later one. When no next spec exists, high severity
  behaves as medium.
- **FR-008**: The system MUST surface open medium- and high-severity entries as
  ready work items in the human's existing work queue (`bd ready`), assigned to
  the human.
- **FR-009**: The system MUST let a human answer an entry (recording the answer)
  or waive it (recording who waived, when, and the stated reason), and MUST
  release any blocks held by that entry upon either resolution.
- **FR-010**: The system MUST report per-spec assumption counts, broken down by
  severity and by open/resolved status, including zero counts for specs with no
  assumptions. The report surfaces as a section of the existing status command
  (`maverick brief`); no new reporting command is introduced.
- **FR-011**: The system MUST default an entry with a missing or invalid
  severity to medium and make the defaulting visible on the entry, rather than
  rejecting the recording.
- **FR-012**: The system MUST preserve ledger entries whose work was never
  committed, identifiable as unstamped, and MUST NOT fail a commit because
  stamping failed (the gap is surfaced as a warning instead).
- **FR-013**: The system MUST remain compatible with pre-existing escalation
  beads that lack the structured fields: listing, queue surfacing, and reporting
  MUST NOT error on them.
- **FR-014**: Re-recording a question already open for the same bead MUST NOT
  create a duplicate open queue item for the human.

### Key Entities

- **Assumption Ledger Entry**: The record of one adopted assumption. Attributes:
  question, adopted answer, alternatives considered, severity (low | medium |
  high, defaulted to medium when absent/invalid), owning spec, change
  identifier stamp(s), resolution state (open | answered | waived), resolution
  details (answer text, or waiver with who/when/why). Extends today's
  assumption bead rather than introducing a parallel store.
- **Discovered-from Edge**: Directed link from a ledger entry to the work item
  whose execution spawned the assumption; the traceability path from doubt back
  to work.
- **Change Stamp**: The set of change identifier(s) embodying the assumption,
  applied when the bead's work is committed; absence marks an entry as
  unstamped.
- **Severity Policy**: The mapping from severity to enforcement — low: advisory;
  medium: blocks owning spec's land until answered/waived; high: medium plus a
  blocking dependency from the next spec's epic onto the entry (dependency-only:
  work past the spec boundary never becomes ready while the entry is open).
- **Owning Spec**: The specification a ledger entry is attributed to; the unit
  over which land-blocking applies and report counts aggregate. Attribution is
  derived from the bead's parent epic (epic↔spec mapping from refuel), never
  self-declared by the recording agent.
- **Assumption Report**: Per-spec aggregation of entries — totals and breakdowns
  by severity and resolution state — used as a spec-quality signal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of assumptions adopted during an autonomous run exist as
  ledger entries with question, adopted answer, alternatives, severity, and
  owning spec populated — zero prose-only escalations for adopted assumptions.
- **SC-002**: For every assumption whose bead's work was committed, the entry
  carries at least one change identifier; a reviewer can go from any entry to
  the embodying change(s) in under a minute without searching history manually.
- **SC-003**: In no run does a spec with an open (unanswered, unwaived) medium-
  or high-severity assumption complete its land; in no run does work on a next
  spec's epic begin while a prior spec's high-severity assumption is open.
- **SC-004**: Low-severity assumptions cause zero blocked lands and zero run
  pauses across all runs.
- **SC-005**: A human can enumerate every assumption awaiting them with a single
  ready-queue listing, and can reach full decision context (question, answer,
  alternatives, spawning work) from any queue item without leaving their
  existing tooling.
- **SC-006**: Resolving (answering or waiving) a blocking assumption releases
  the affected land block or epic dependency with no manual dependency surgery;
  the next land attempt or ready-work query proceeds normally.
- **SC-007**: Per-spec assumption counts are available for 100% of specs
  processed after this feature ships, including explicit zero counts.

## Assumptions

- **Ledger entries are extended assumption beads**, not a parallel store: the
  existing work-item system (beads) already provides identity, assignment,
  labels, dependencies, and the ready queue, and the user description names
  `bd ready` as the surfacing mechanism. The "ledger" is the queryable set of
  these structured entries.
- **Recording is agent-initiated during execution**: any agent role that adopts
  an assumption while working a bead (implementer, reviewer, fixer) may record
  one; the existing review-exhaustion escalation path becomes one producer among
  several rather than the only one. Agents surface assumptions in their
  structured step results; ledger-entry creation is the workflow's
  deterministic responsibility (agents own judgment, workflows own side
  effects).
- **"Next spec" means the next spec in the run's execution order** (for
  multi-spec runs); a high-severity entry blocks the epic of whichever spec
  follows the owning spec in that order.
- **Waiving is a human-only action** performed through the existing human
  review/queue tooling, and is always recorded (who, when, why) — a waiver is an
  auditable decision, not a silent dismissal.
- **Severity is assigned by the recording agent** based on blast radius of being
  wrong; humans can see (and future reconcile work may revise) severities, but
  initial assignment is autonomous so recording never blocks on a human.
- **Reconcile mechanics are out of scope** per the user description: this spec
  covers recording, stamping, severity enforcement, queue surfacing, and
  counting — not how answered assumptions get folded back into code or specs.
- **Reporting surfaces through `maverick brief`**, the existing status surface,
  rather than a new standalone reporting tool.

## Out of Scope

- Reconcile mechanics: applying a human's answer back to the code, revising
  commits, or re-running affected beads after an assumption is answered.
- Automatic severity re-classification or severity escalation over time.
- Cross-run or cross-repository assumption aggregation.
- Any change to how non-assumption escalations (e.g., generic
  needs-human-review items) are created or resolved.

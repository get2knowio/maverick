# Feature Specification: Assumption Review Console

**Feature Branch**: `053-assumption-review-console`
**Created**: 2026-07-25
**Status**: Draft
**Input**: User description: "Provide a Claude Code skill that serves as the human review console for assumption sweeps. The skill reads the pending-assumption queue and presents each entry one at a time using AskUserQuestion — options are the adopted answer and the recorded alternatives, plus free-form input — then translates each decision into a headless CLI verb invocation. It never performs history surgery itself: all jj mechanics stay deterministic in Maverick, and the LLM only chooses which verb to call. The CLI side exposes thin plumbing verbs with machine-readable JSON output suitable for skill consumption: list the pending queue with full provenance (question, adopted answer, alternatives, severity, owning spec, affected change IDs, current status), answer an entry, waive an entry, bulk-waive a spec's entries by severity, report reconcile and land status, run reconcile, and land. Each verb is transactional and reports success or a structured error; none of them require a TTY or interactive confirmation. Where a verb already exists (maverick review, maverick reconcile, maverick land, maverick brief), add a --json output mode rather than a parallel command. The skill's flow is: read the queue, sweep it with the human, then — once the sweep is complete — trigger a single batched reconcile rather than one per answer, surface the resulting frontier state (verified, conditionally-verified, or still blocked), and offer to land when the frontier is clear. It reports reconcile failures and entries marked needing interactive review back to the human rather than retrying blindly. The existing structured maverick review command remains the bare-terminal fallback for humans without Claude Code; no further interactive review UX is built into the CLI."

## Clarifications

### Session 2026-07-25

- Q: Does the listing verb return only open entries or the full ledger? → A: All ledger entries with their current status, filterable by status / owning spec / severity; default selection is open entries (the sweep population).
- Q: What is the output-stream contract in machine-readable mode? → A: The structured document is the only content on standard output; all diagnostics, warnings, and progress go to standard error.
- Q: In what order does the sweep present entries? → A: Grouped by owning spec; within a spec, severity high→low; stable ledger order within severity.
- Q: Are the reconcile and land verbs synchronous or job-based? → A: Synchronous — the invocation blocks until completion and returns the final outcome; no background-job or polling protocol.
- Q: Does the skill use bulk-waive during a sweep? → A: Yes, as an optional shortcut — when multiple open low-severity entries share an owning spec, the skill may offer a spec-level bulk-waive mapped to the bulk-waive verb; per-entry presentation remains the default.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Headless review verbs with machine-readable output (Priority: P1)

An automation client (the review-console skill, a script, or any agent) drives the
entire assumption-review lifecycle through headless command invocations: list the
pending queue with full provenance, answer an entry, waive an entry, bulk-waive a
spec's entries by severity, check reconcile and land status, run reconcile, and
land. Every invocation returns machine-readable structured output — on success and
on failure — and never prompts, requires a TTY, or asks for interactive
confirmation.

**Why this priority**: Every other part of this feature is a consumer of these
verbs. Without a headless, machine-readable command surface there is no way for
the skill (or any other client) to act on the queue. Delivered alone, it is
already a viable product: scripts and CI can inspect and resolve assumptions
without a human at a terminal.

**Independent Test**: From a repository with pending assumption entries, invoke
each verb in machine-readable mode from a non-interactive shell (no TTY). Verify
each returns parseable structured output containing the documented fields, that
answer/waive/reconcile/land actually change ledger and repository state, and that
failure cases (unknown entry id, blocked land, concurrent conflict) return a
structured error and a non-zero exit code instead of a prompt or a stack trace.

**Acceptance Scenarios**:

1. **Given** a repository with pending assumption entries, **When** the client
   requests the queue in machine-readable mode, **Then** it receives one record
   per open entry containing the entry id, question, adopted answer, recorded
   alternatives, severity, owning spec, affected change identifiers, and current
   status.
2. **Given** a pending entry, **When** the client invokes the answer verb with an
   answer text, **Then** the entry is recorded as answered, the response reports
   success with the entry's updated state, and no interactive confirmation is
   requested.
3. **Given** a pending entry, **When** the client invokes the waive verb with a
   reason, **Then** the entry is recorded as waived with that reason and the
   response reports the updated state.
4. **Given** a spec with several open entries of mixed severity, **When** the
   client invokes bulk-waive for that spec with a severity filter and a reason,
   **Then** exactly the matching entries are waived in one invocation and the
   response lists which entries were affected.
5. **Given** answered-but-unreconciled entries, **When** the client invokes the
   reconcile verb in machine-readable mode, **Then** reconcile runs to completion
   and the response reports a per-entry outcome (reconciled, skipped, escalated to
   interactive review, or failed) plus an overall result.
6. **Given** any verb invocation that fails (nonexistent entry id, land blocked by
   the frontier gate, reconcile blocked by a concurrent run), **When** the failure
   occurs, **Then** the client receives a structured error with a stable,
   machine-distinguishable error kind and a human-readable message, the process
   exits non-zero, and repository/ledger state is left consistent (no partial
   mutation without a reported outcome).
7. **Given** an existing command already covers a verb's action (review,
   reconcile, land, brief), **When** machine-readable output is requested, **Then**
   it is available as an output mode of that existing command — not as a new
   parallel command.

---

### User Story 2 - Guided sweep in the review console (Priority: P2)

A developer working in Claude Code asks to review pending assumptions. The
review-console skill reads the pending queue and walks them through it one entry
at a time. For each entry it shows the question with its provenance (owning spec,
severity, affected changes) and offers a choice: confirm the adopted answer,
select one of the recorded alternatives, supply a free-form answer, or waive the
entry. Each decision is applied immediately by invoking the corresponding
headless verb. The skill itself never edits history, files, or ledger state
directly — it only chooses which verb to call.

**Why this priority**: This is the headline experience — the human review console
that turns an assumption backlog into a fast guided sweep. It depends on the P1
verbs but delivers the feature's core value: humans resolve assumptions without
memorizing entry ids or CLI syntax.

**Independent Test**: With the P1 verbs available and a queue of pending entries,
invoke the skill. Verify every entry is presented exactly once with its adopted
answer and alternatives as selectable options plus a free-form path, that each
decision results in exactly one verb invocation, and that afterwards the ledger
reflects each decision. Verify by inspection that the skill performed no direct
repository or history mutation.

**Acceptance Scenarios**:

1. **Given** a queue of pending entries, **When** the developer starts the sweep,
   **Then** the skill presents entries one at a time, each showing the question,
   owning spec, severity, and affected changes, with the adopted answer and each
   recorded alternative as selectable options plus a free-form input path.
2. **Given** an entry is presented, **When** the developer selects the adopted
   answer, an alternative, or provides a free-form answer, **Then** the skill
   records it via the answer verb and moves to the next entry.
3. **Given** an entry is presented, **When** the developer chooses to waive it
   with a reason, **Then** the skill records the waive via the waive verb.
4. **Given** an entry is presented, **When** the developer chooses to skip it,
   **Then** the entry is left open and untouched, and the sweep continues.
5. **Given** a sweep is interrupted partway through, **When** the developer later
   restarts it, **Then** already-decided entries do not reappear (their decisions
   were applied immediately) and the sweep resumes over the remaining open
   entries.
6. **Given** the queue is empty, **When** the developer starts the sweep, **Then**
   the skill reports there is nothing pending and shows the current frontier and
   land status instead of presenting questions.

---

### User Story 3 - Batched reconcile, frontier report, and landing offer (Priority: P3)

When the sweep is complete, the skill triggers exactly one batched reconcile run
covering all answers given during the sweep — never one reconcile per answer. It
then reports the resulting frontier state — verified, conditionally verified, or
still blocked — in plain language. If the frontier is clear, it offers to land and
proceeds only on the developer's explicit confirmation. Reconcile failures and
entries escalated to interactive review are reported back to the developer with
the entry and reason; the skill never retries them blindly.

**Why this priority**: Closes the loop from "answers recorded" to "history
corrected and work landed", which is the end state the sweep exists to reach. It
builds on P1 and P2 but is separable: without it, a developer can still finish a
sweep and run reconcile and land by hand.

**Independent Test**: Complete a sweep with multiple answers, then verify exactly
one reconcile run occurred, that the skill's frontier report matches the status
verb's output, that landing is offered only when the frontier is clear and only
proceeds after explicit confirmation, and that a forced reconcile failure is
reported once with its reason rather than retried.

**Acceptance Scenarios**:

1. **Given** a completed sweep in which several entries were answered, **When**
   the sweep ends, **Then** the skill triggers a single reconcile run covering all
   of them, and no reconcile is triggered per individual answer.
2. **Given** reconcile completes, **When** the skill reports the outcome, **Then**
   the developer sees the frontier state (verified, conditionally verified, or
   still blocked) and, when blocked, the list of entries still standing in the way
   with the suggested next step for each.
3. **Given** the frontier is clear, **When** the skill offers to land, **Then**
   landing proceeds only after the developer explicitly confirms, and the landing
   outcome (including its verified / conditionally-verified classification) is
   reported back.
4. **Given** reconcile fails for an entry or marks it as needing interactive
   review, **When** the skill reports results, **Then** that entry is surfaced to
   the developer with its reason and is not silently retried.
5. **Given** the sweep ended with only waives and no changed answers, **When**
   there is nothing to reconcile, **Then** the skill skips the reconcile run,
   reports the frontier state directly, and still offers to land if clear.

---

### Edge Cases

- Queue changes underneath the sweep (another session resolves an entry
  mid-sweep): if the entry was waived or closed, the verb invocation returns a
  structured "already resolved" error carrying the entry's current state; the
  skill reports it and continues with the remaining entries rather than
  aborting. If the entry was concurrently *answered*, a new answer proceeds as
  a re-answer — it supersedes the earlier answer and re-arms the entry for
  reconciliation (consistent with the ledger's existing re-answer lifecycle).
- An entry has no recorded alternatives: the choice presented is the adopted
  answer, free-form input, waive, or skip.
- An entry has more recorded alternatives than the presentation surface can offer
  at once: the skill still makes every alternative reachable (e.g., across a
  follow-up choice or via free-form), never silently dropping options.
- Reconcile is blocked because another workflow run is active: the verb reports a
  structured error; the skill tells the developer to retry after the run finishes
  rather than looping.
- Land is invoked headlessly while the frontier is non-empty: the command exits
  non-zero with a structured report of the blocking entries — the same gate the
  interactive command enforces, with no bypass introduced by the machine-readable
  mode.
- Free-form answer is empty or whitespace-only: rejected before any verb is
  invoked; the developer is re-prompted.
- A verb's structured output must remain parseable even when the underlying
  operation partially succeeded (e.g., bulk-waive where one entry was already
  resolved): the response enumerates per-entry outcomes.
- The developer declines the landing offer: nothing is landed; the sweep ends
  with the frontier report and the state remains ready for a later manual land.

## Requirements *(mandatory)*

### Functional Requirements

#### Headless verb surface

- **FR-001**: The CLI MUST provide a headless way to list assumption-ledger
  entries in machine-readable form, where each entry includes: entry identifier,
  question, adopted answer, recorded alternatives, severity, owning spec,
  affected change identifiers, and current status. The listing MUST be
  filterable by status, owning spec, and severity; its default selection is the
  open entries that constitute the sweep population.
- **FR-002**: The CLI MUST provide headless, machine-readable verbs to: answer an
  entry, waive an entry with a reason, bulk-waive a spec's open entries filtered
  by severity, report reconcile status, report land/frontier status, run
  reconcile, and land. All verbs — including the long-running reconcile and land
  — execute synchronously: the invocation blocks until completion and returns
  the final outcome; no background-job or polling protocol is introduced.
- **FR-003**: Where an existing command already performs a verb's action
  (reviewing, reconciling, landing, briefing/status), the machine-readable
  behavior MUST be added as an output mode of that existing command; no parallel
  duplicate commands may be introduced.
- **FR-004**: No verb in machine-readable mode may require a TTY, prompt for
  input, or ask for interactive confirmation; all inputs MUST be expressible as
  invocation arguments.
- **FR-005**: Every verb MUST report either success with the resulting state or a
  structured error carrying a stable, machine-distinguishable error kind and a
  human-readable message, and MUST exit non-zero on failure. Raw stack traces or
  unstructured log noise MUST NOT be the failure contract. In machine-readable
  mode the structured document MUST be the only content on standard output;
  diagnostics, warnings, and progress MUST go to standard error.
- **FR-006**: Each verb MUST be transactional: on failure, ledger and repository
  state are left consistent, and any partial effects (e.g., in a bulk operation)
  are enumerated in the response rather than left silent.
- **FR-007**: Machine-readable land MUST enforce the same assumption-frontier
  gate as the existing land command, with no bypass introduced by the output
  mode; when blocked it MUST report the blocking entries in structured form.
- **FR-008**: The machine-readable output schema for each verb MUST be documented
  and treated as a public interface for automation clients.

#### Review-console skill

- **FR-009**: A Claude Code skill MUST act as the human review console: it reads
  the pending queue via the listing verb and presents each entry one at a time,
  showing the question and its provenance (owning spec, severity, affected
  changes). Entries are presented grouped by owning spec; within a spec,
  severity high to low; within a severity, stable ledger order.
- **FR-010**: For each entry, the presented choices MUST include the adopted
  answer, each recorded alternative, and a free-form input path; the developer
  MUST also be able to waive the entry with a reason or skip it (leaving it
  open). When multiple open low-severity entries share an owning spec, the skill
  MAY additionally offer a spec-level bulk-waive shortcut that maps to the
  bulk-waive verb; per-entry presentation remains the default.
- **FR-011**: The skill MUST translate every decision into exactly one
  corresponding headless verb invocation, applied immediately when the decision
  is made. The skill MUST NOT mutate repository history, files, or ledger state
  through any other means — all history mechanics remain deterministic inside
  Maverick.
- **FR-012**: The skill MUST tolerate mid-sweep interruption: because decisions
  are applied immediately, restarting the sweep operates only on the entries
  still open.
- **FR-013**: When the queue is empty at sweep start, the skill MUST say so and
  present the current frontier and land status instead of questions.

#### Post-sweep flow

- **FR-014**: On sweep completion, the skill MUST trigger at most one reconcile
  run covering all answers from the sweep; it MUST NOT trigger reconcile per
  individual answer. If no answers require reconciliation, the reconcile run is
  skipped.
- **FR-015**: After reconcile (or its skip), the skill MUST surface the frontier
  state to the developer as one of: verified, conditionally verified, or still
  blocked — including, when blocked, the blocking entries and the suggested next
  step for each.
- **FR-016**: When the frontier is clear, the skill MUST offer to land and
  proceed only on explicit developer confirmation, then report the landing
  outcome and its classification.
- **FR-017**: Reconcile failures and entries marked as needing interactive review
  MUST be reported back to the developer with the entry and reason; the skill
  MUST NOT retry them automatically.

#### Fallback boundary

- **FR-018**: The existing interactive review command MUST remain available and
  behaviorally unchanged as the bare-terminal fallback for humans without Claude
  Code; this feature MUST NOT add any further interactive review UX to the CLI.

### Key Entities

- **Pending assumption entry**: A unit of the review queue. Attributes surfaced
  to clients: identifier, question, adopted answer, recorded alternatives,
  severity, owning spec, affected change identifiers, current status.
- **Decision**: The human's resolution of one entry during a sweep — confirm
  adopted answer, choose an alternative, free-form answer, waive (with reason),
  or skip. Every non-skip decision maps to exactly one verb invocation.
- **Verb result**: The structured outcome of a headless invocation — success with
  resulting state, or a structured error (stable kind + message); bulk operations
  enumerate per-entry outcomes.
- **Frontier report**: The post-reconcile summary of landability — verified,
  conditionally verified, or still blocked, with blocking entries and suggested
  next steps.
- **Sweep**: One guided pass over the open queue in the review console, ending in
  at most one batched reconcile and an optional landing offer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can take a queue of 10 pending assumptions from unseen
  to fully resolved (answered or waived) in a single guided sweep without leaving
  their Claude Code session and without typing any entry identifier or command
  syntax by hand.
- **SC-002**: 100% of the review-lifecycle verbs (list, answer, waive,
  bulk-waive, reconcile status, land status, reconcile, land) complete from a
  non-interactive environment with no TTY, and every invocation — success or
  failure — yields parseable structured output.
- **SC-003**: A sweep with any number of answered entries results in exactly one
  reconcile run (zero when nothing needs reconciliation), verifiable from run
  records.
- **SC-004**: After a sweep that resolves every entry and a successful reconcile,
  the developer reaches a completed landing with zero manual history-manipulation
  commands issued by them or by the skill.
- **SC-005**: 100% of reconcile failures and interactive-review escalations that
  occur during a sweep's reconcile are surfaced to the developer with the
  affected entry and reason, and zero automatic retries occur.
- **SC-006**: A human without Claude Code can still complete the same
  answer/waive lifecycle using the existing interactive command, unchanged from
  its pre-feature behavior.

## Assumptions

- The pending queue for a sweep is the set of open (unanswered, unwaived)
  assumption-ledger entries across specs in the current repository — the same
  population the existing land gate counts as blocking, including open legacy
  escalation entries.
- Skipping an entry during a sweep is allowed and leaves it open; a skipped entry
  simply remains in the queue for a future sweep and continues to block landing.
- Decisions are applied immediately (per entry) rather than batched at sweep end;
  only reconcile is batched. This is what makes interruption-safe sweeps and
  concurrent-session tolerance possible.
- Bulk-waive defaults to the lowest severity when no severity filter is given,
  matching the existing bulk-waive behavior; the machine-readable mode changes
  output shape only, not semantics.
- Landing through the skill uses the standard landing flow in its default mode;
  preview/finalize variants remain available through the CLI directly and are
  out of scope for the skill's offer.
- The skill's landing offer constitutes the explicit human approval for that
  landing; the headless land verb itself never asks for confirmation (FR-004),
  so consent is gathered by the caller.
- Machine-readable error kinds are stable identifiers (safe to branch on), while
  human-readable messages may change freely.

## Out of Scope

- Any new interactive (TTY) review experience in the CLI beyond what already
  exists.
- Reviewing or editing assumption entries' provenance (question text,
  alternatives, severity) — the console resolves entries; it does not author or
  reclassify them.
- Automatic retry policies for failed reconciles or landings.
- Driving the sweep from any surface other than the Claude Code skill (e.g., web
  UI, editor plugins); the headless verbs are the extension point for such future
  clients.

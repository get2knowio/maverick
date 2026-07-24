# Feature Specification: Headless Spec Kit Chain (`maverick spec`)

**Feature Branch**: `050-headless-spec-chain`
**Created**: 2026-07-24
**Status**: Draft
**Input**: User description: "Add maverick spec <feature> --from-prd <file>, which runs the Spec Kit chain — specify, clarify, plan, tasks, analyze — headlessly in the hidden workspace, each step invoking the target repo's own /speckit.* command through airframe. Clarify questions never block: where the agent surface supports AskUserQuestion interception, the harness answers programmatically by adopting the recommended option and filing an assumption-ledger entry (question, adopted, alternatives, severity); otherwise it uses Spec Kit's documented non-interactive convention (informed defaults recorded in the spec's Assumptions section) and upgrades those into ledger entries. Ordering is strict: clarify completes before plan and tasks; a failed or blocked clarify halts that spec's chain rather than falling through. Analyze runs read-only and its findings become remediation beads, not blockers. Artifacts land in specs/NNN/ as ordinary git-native markdown. maverick init verifies Spec Kit is installed in the target repo and offers to install it."

## Clarifications

### Session 2026-07-24

- Q: Where should the Spec Kit chain execute, given the tension between the described "hidden workspace" and Guardrail 0's single-repo CWD model? → A: Hidden workspace — the chain runs in an isolated hidden workspace and only completed artifacts land in the repo's `specs/` tree; Guardrail 0 gains a documented exception for this markdown-only flow (the bd impedance mismatch that retired workspaces does not apply).
- Q: How does re-running `maverick spec <feature>` behave after a halted chain? → A: Auto-resume — a re-run detects the halted chain for that feature and continues from the failed step, reusing artifacts from completed steps; per-run chain state is persisted to make this possible.
- Q: Where do analyze remediation beads live, given the feature's epic doesn't exist until `refuel --speckit`? → A: Standalone at creation — beads are created immediately, labeled/linked with the spec ID but parentless; when `refuel --speckit` later creates the epic, its delta logic adopts them under it.
- Q: What severity do clarify-derived ledger entries default to when the harness has no clear signal? → A: Assessed per question, default low — impactful questions (scope, security) escalate to medium/high and gate `maverick land`; unclear cases default to low (advisory), keeping headless runs unobstructed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - PRD to complete spec artifacts, hands-off (Priority: P1)

A developer has a product requirements document for a new feature. They run `maverick spec <feature> --from-prd <file>` and walk away. Maverick runs the full Spec Kit chain — specify, clarify, plan, tasks, analyze — end to end with no interactive prompts, using the target repository's own Spec Kit commands and templates so the output matches what the developer would have produced by running each step by hand. When they return, a new numbered spec directory (`specs/NNN-<feature>/`) contains the specification, plan, and task list as ordinary markdown files reviewable with normal git tooling.

**Why this priority**: This is the core value proposition — turning a PRD into implementation-ready Spec Kit artifacts without a human babysitting five sequential interactive steps. Everything else in this feature qualifies or hardens this flow.

**Independent Test**: In a Spec Kit-initialized repository, run the command against a sample PRD and verify a new `specs/NNN-<feature>/` directory appears containing spec, plan, and tasks artifacts, with no interactive prompt having been shown at any point.

**Acceptance Scenarios**:

1. **Given** a Spec Kit-initialized repository and a readable PRD file, **When** the user runs `maverick spec <feature> --from-prd <file>`, **Then** the chain runs specify, clarify, plan, tasks, and analyze in that order and produces spec, plan, and tasks artifacts in a new `specs/NNN-<feature>/` directory without requesting any user input.
2. **Given** a completed run, **When** the user inspects the artifacts, **Then** they are plain markdown files tracked like any other repository content (diffable, committable, reviewable in a PR) with no proprietary or binary formats.
3. **Given** a completed run, **When** the user compares the artifacts to those produced by manually running the repository's own Spec Kit commands, **Then** the structure and conventions match, because each chain step invoked the target repository's own Spec Kit command rather than a Maverick reimplementation.
4. **Given** the chain runs, **When** steps execute, **Then** they execute in Maverick's isolated (hidden) workspace so the user's working checkout is not disturbed mid-run, and the finished artifacts land in the repository's `specs/` tree.

---

### User Story 2 - Clarify questions answered programmatically, on the record (Priority: P2)

During the clarify step, Spec Kit generates targeted questions about underspecified areas. Instead of blocking on a human, the harness answers each question by adopting the recommended option, and files an assumption-ledger entry recording the question, the adopted answer, the alternatives that were not chosen, and a severity. Where programmatic question interception is not available on the agent surface, the chain falls back to Spec Kit's documented non-interactive convention — informed defaults recorded in the spec's Assumptions section — and then upgrades each of those recorded defaults into an equivalent assumption-ledger entry. Either way, every automated decision is durable, attributable, and visible to the existing review workflow (`maverick brief`, `maverick review`, the land gate).

**Why this priority**: Headless operation is only safe if no decision is silently made. The assumption ledger (established in spec 049) is the existing contract for "an agent adopted an answer a human should be able to audit"; clarify decisions must flow into it or the hands-off chain trades away trust for convenience.

**Independent Test**: Run the chain against a deliberately vague PRD that provokes clarify questions; verify the chain completes without prompting and that each clarify question appears as an assumption-ledger entry with question, adopted answer, alternatives, and severity populated.

**Acceptance Scenarios**:

1. **Given** the clarify step asks a question and question interception is available, **When** the harness answers it, **Then** it adopts the recommended option and files an assumption-ledger entry containing the question, the adopted answer, the alternatives, and a severity.
2. **Given** question interception is not available on the agent surface in use, **When** the clarify step runs, **Then** it runs under Spec Kit's documented non-interactive convention, defaults are recorded in the spec's Assumptions section, and each recorded default is subsequently upgraded into an assumption-ledger entry.
3. **Given** a completed run that answered N clarify questions, **When** the user runs `maverick brief`, **Then** the assumption counts for the new spec reflect those N entries, and each is resolvable via the existing `maverick review <id>` answer/waive flow.
4. **Given** the chain answered clarify questions, **When** any question was answered, **Then** at no point did the run pause waiting for human input.

---

### User Story 3 - Strict ordering with halt-on-failed-clarify (Priority: P2)

The chain enforces strict step ordering: clarify must complete successfully before plan and tasks run. If clarify fails or is blocked, the chain for that spec halts with a clear error — it never "falls through" to planning against an unclarified spec. The user gets an unambiguous report of which step failed, why, and what artifacts (if any) were produced up to that point.

**Why this priority**: Falling through a failed clarify would produce plans and tasks built on an unvetted spec — worse than no output, because it looks complete. Halting preserves the integrity guarantee that makes the headless chain trustworthy. It shares P2 with the ledger story because both are the safety half of the P1 flow.

**Independent Test**: Force the clarify step to fail (e.g., unusable spec input or induced step error) and verify the run exits non-zero, reports clarify as the failed step, and no plan or tasks artifacts exist for that spec.

**Acceptance Scenarios**:

1. **Given** the specify step succeeded, **When** clarify fails or is blocked, **Then** the chain halts, exits with a failure status identifying clarify as the failed step, and does not run plan, tasks, or analyze for that spec.
2. **Given** a halted chain, **When** the user inspects the spec directory, **Then** artifacts produced by completed steps are present and the report states which steps did not run.
3. **Given** any run, **When** steps execute, **Then** plan never starts before clarify has completed successfully, and tasks never starts before plan has completed successfully.

---

### User Story 4 - Analyze findings become remediation beads (Priority: P3)

After tasks are generated, the analyze step runs as a read-only cross-artifact consistency check. Its findings never block the chain or fail the run; instead each finding is captured as a remediation bead so the issues enter the normal beads workflow and can be picked up by `maverick fly` or reviewed by a human later.

**Why this priority**: Analyze adds quality assurance on top of an already-useful chain. The chain delivers its core value without it, but converting findings into actionable, tracked work items (rather than a report nobody reads or a blocker nobody wants) closes the loop with Maverick's existing bead-driven workflow.

**Independent Test**: Run the chain on a PRD engineered to produce artifact inconsistencies; verify the run still completes successfully and each analyze finding exists as a bead associated with the new spec.

**Acceptance Scenarios**:

1. **Given** tasks were generated, **When** analyze runs, **Then** it makes no modifications to the spec, plan, or tasks artifacts.
2. **Given** analyze reports findings, **When** the chain finishes, **Then** the run is reported as successful and each finding has been recorded as a remediation bead linked to the spec that produced it.
3. **Given** analyze itself errors, **When** the chain finishes, **Then** the spec, plan, and tasks artifacts are intact and the run reports the analyze failure as a warning rather than failing the chain.

---

### User Story 5 - `maverick init` verifies Spec Kit availability (Priority: P3)

When a user initializes a Maverick project, init checks whether Spec Kit is installed in the target repository. If it is missing, init offers to install it. This ensures `maverick spec` has its prerequisite in place before anyone attempts a chain run, with a clear path to remediation instead of a mid-run failure.

**Why this priority**: A prerequisite check improves first-run experience but the chain can also detect the missing prerequisite itself; init integration is a convenience layer.

**Independent Test**: Run `maverick init` in a repository without Spec Kit; verify the missing installation is detected and an install offer is presented. Accept it and verify Spec Kit is then present.

**Acceptance Scenarios**:

1. **Given** a repository without Spec Kit installed, **When** the user runs `maverick init`, **Then** init reports Spec Kit as missing and offers to install it.
2. **Given** the user accepts the install offer, **When** init completes, **Then** Spec Kit is installed in the target repository and a subsequent `maverick spec` run can proceed.
3. **Given** the user declines the install offer, **When** init completes, **Then** init succeeds with a notice that `maverick spec` will be unavailable until Spec Kit is installed.
4. **Given** a repository with Spec Kit already installed, **When** the user runs `maverick init`, **Then** no install offer is shown.

### Edge Cases

- PRD file does not exist, is unreadable, or is empty: the command fails fast with a clear error before any chain step runs.
- Spec Kit is not installed in the target repository at `maverick spec` time (init was skipped or declined): the command fails fast with guidance to install, rather than failing mid-chain.
- Clarify asks zero questions: the chain proceeds normally with no ledger entries filed.
- Clarify produces a question with no recommended option: the harness must still make a recorded choice (adopting an informed default) or treat the question as blocking and halt — it must never silently skip the question.
- A mid-chain step (plan or tasks) fails: the chain halts at that step; earlier artifacts remain; the failure report identifies the step, and analyze does not run.
- The feature name collides with an existing spec directory that is not a halted run of the same feature: the run must not overwrite it; it reports the conflict (numbering allocation follows the repository's existing Spec Kit convention).
- The isolated workspace cannot be created or the target repository state prevents landing artifacts: the run fails with a report and does not leave partial artifacts in the user's `specs/` tree.
- Interrupted run (user cancellation or crash): no half-written artifacts land in `specs/`; a re-run resumes from the first step that did not complete, exactly as with a halted chain.
- Analyze produces zero findings: no remediation beads are created; the run reports a clean analysis.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a `maverick spec <feature> --from-prd <file>` command that accepts a feature name and a path to a PRD file, and validates both (readable, non-empty PRD; usable feature name) before starting any chain step.
- **FR-002**: The system MUST execute the Spec Kit chain in the strict order specify → clarify → plan → tasks → analyze, exactly once per invocation, for exactly one feature.
- **FR-003**: Each chain step MUST invoke the target repository's own corresponding Spec Kit command (its `/speckit.*` surface), so that the repository's installed Spec Kit version, templates, and conventions govern the output — the chain orchestrates, it does not reimplement.
- **FR-004**: The chain MUST run headlessly end to end: no step may block on interactive human input under any circumstance.
- **FR-005**: When the agent surface supports programmatic interception of interactive questions, the system MUST answer each clarify question by adopting the recommended option and MUST file an assumption-ledger entry recording the question, the adopted answer, the alternatives presented, and a severity.
- **FR-006**: When programmatic question interception is not available, the system MUST run clarify under Spec Kit's documented non-interactive convention (informed defaults recorded in the spec's Assumptions section) and MUST afterwards upgrade each recorded default into an assumption-ledger entry equivalent to those filed under FR-005.
- **FR-007**: Assumption-ledger entries filed by the chain MUST participate in the existing assumption workflows: counted by `maverick brief`, resolvable via `maverick review <id>` (answer or waive), and subject to the existing severity-based `maverick land` gate.
- **FR-007a**: The harness MUST assess severity per question based on its impact (scope- or security-affecting adoptions escalate to medium or high); when no clear signal exists, severity defaults to low (advisory, never blocking).
- **FR-008**: The system MUST NOT start plan before clarify has completed successfully, and MUST NOT start tasks before plan has completed successfully.
- **FR-009**: If clarify fails or is blocked, the system MUST halt that spec's chain with a non-zero exit and a report identifying the failed step; it MUST NOT proceed to plan or tasks for that spec.
- **FR-010**: If any other chain step fails, the system MUST halt at that step, preserve artifacts from completed steps, and report which steps ran, which failed, and which were skipped.
- **FR-011**: The analyze step MUST run read-only: it MUST NOT modify the spec, plan, or tasks artifacts.
- **FR-012**: Each analyze finding MUST be recorded as a remediation bead associated with the spec that produced it; analyze findings (or an analyze failure) MUST NOT cause the run to fail.
- **FR-012a**: Remediation beads are created standalone (no parent epic), carrying a label/link identifying the originating spec; a later `refuel --speckit` run for that spec MUST adopt them under the epic it creates.
- **FR-013**: All chain artifacts MUST land in the repository's `specs/` tree under a numbered feature directory (`specs/NNN-<feature>/`), as plain git-native markdown files, following the repository's existing Spec Kit numbering and layout conventions.
- **FR-014**: The chain MUST execute in Maverick's isolated (hidden) workspace so the user's working checkout is not modified while steps run; only completed artifacts land in the repository.
- **FR-015**: The system MUST NOT overwrite an existing completed spec directory; a feature-name or numbering collision with unrelated content is reported as an error.
- **FR-016**: An interrupted or failed run MUST NOT leave partially written artifacts in the repository's `specs/` tree; artifacts from fully completed steps are preserved.
- **FR-020**: The system MUST persist per-run chain state such that re-running `maverick spec <feature>` after a halted or interrupted chain automatically resumes from the first step that did not complete, reusing artifacts from completed steps rather than regenerating them.
- **FR-017**: `maverick init` MUST verify that Spec Kit is installed in the target repository; when missing, it MUST offer to install it, honor the user's acceptance or decline, and succeed either way (with a notice when declined).
- **FR-018**: `maverick spec` MUST fail fast with actionable guidance when Spec Kit is not installed in the target repository.
- **FR-019**: The command MUST report progress per step as it runs and finish with a summary: steps completed, artifacts produced, clarify questions answered (ledger entry count), and remediation beads created.

### Key Entities

- **Spec chain run**: One invocation of `maverick spec` for one feature — the ordered sequence of five steps, its per-step outcomes, and its final status (completed, or halted at a named step).
- **Chain step**: A single stage (specify, clarify, plan, tasks, analyze) delegating to the target repository's own Spec Kit command; has a strict position, a success/failure outcome, and produced artifacts.
- **PRD (input document)**: The user-supplied requirements document that seeds the specify step.
- **Spec artifact set**: The markdown outputs landing in `specs/NNN-<feature>/` — specification, plan, tasks, and any supporting files the repository's Spec Kit templates produce.
- **Clarify decision**: A question raised during clarify plus the answer adopted on the user's behalf — question text, adopted answer, alternatives, severity — persisted as an assumption-ledger entry regardless of which answering path (interception or non-interactive convention) produced it.
- **Remediation bead**: A work item created from one analyze finding, linked to the originating spec, entering the normal beads workflow. Created standalone (parentless) at chain time; adopted under the feature's epic when `refuel --speckit` runs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from a PRD file to a complete, reviewable spec artifact set (specification, plan, tasks) with a single command and zero interactive inputs.
- **SC-002**: 100% of clarify questions raised during a chain run have a corresponding assumption-ledger entry with question, adopted answer, alternatives, and severity — no decision is made off the record, on either answering path.
- **SC-003**: Zero plans or task lists are ever produced from a spec whose clarify step failed or was blocked.
- **SC-004**: 100% of analyze findings from a completed run exist as remediation beads linked to the spec, and no analyze outcome ever causes an otherwise-successful run to fail.
- **SC-005**: All produced artifacts are reviewable with standard git tooling (diff, blame, PR review) with no extra tooling required.
- **SC-006**: After `maverick init` on a repository without Spec Kit, the user has either a working Spec Kit installation or an explicit recorded notice — no user first discovers the missing prerequisite via a mid-chain failure.
- **SC-007**: A failed run leaves the repository's `specs/` tree either untouched or containing only complete artifacts from successfully finished steps — never half-written files.

## Assumptions

- **Numbering and layout**: The `NNN` spec-directory number is allocated by the target repository's existing Spec Kit convention (next sequential number), matching how manually created specs are numbered today.
- **One feature per invocation**: `maverick spec` processes exactly one feature per run; batch/multi-spec orchestration is out of scope for this feature.
- **Assumption ledger contract**: The ledger established by spec 049 (entry shape, severity semantics, `brief`/`review`/`land` integration) is the destination for clarify decisions; this feature files entries into it rather than defining a new mechanism.
- **Severity assignment**: The severity on a clarify-derived ledger entry is assigned by the answering harness based on the question's apparent impact; absent a clear signal, severity defaults to low (advisory) so headless runs stay unobstructed, with scope- and security-impacting questions escalated to medium/high (clarified 2026-07-24).
- **Recommended option exists**: Spec Kit clarify questions conventionally present a recommended/first option; when none exists, the harness adopts an informed default and records it identically (see edge case) rather than skipping.
- **Isolated workspace**: The chain runs in a hidden isolated workspace (clarified 2026-07-24). This is a documented exception to the single-repo CWD guardrail: the spec chain produces only markdown artifacts, so the bd state-portability mismatch that retired the general workspace model does not apply. The constitution's Guardrail 0 must be amended with this exception as part of the feature.
- **Spec Kit installation check**: "Installed in the target repo" means the repository has been initialized with Spec Kit (its command surface and templates are present), not merely that a Spec Kit binary exists on the machine.
- **Remediation bead granularity**: One bead per analyze finding, deduplicated within a single run if analyze reports the same finding twice.
- **PRD format**: The PRD is a text/markdown document; no specific internal structure is required beyond what the specify step can consume.

# Feature Specification: Standalone Code Review

**Feature Branch**: `058-standalone-code-review`

**Created**: 2026-08-22

**Status**: Draft

**Input**: User description: "Add a standalone agentic code-review command that reviews a diff, an epic's accumulated changes, or a set of paths on demand — outside the fly loop. Today the reviewer agent only runs inside `maverick fly` as part of the per-bead gate. Its judgment is useful on demand: before pushing a manual change, after landing an epic, or on a colleague's branch. Scope selection: review the working-copy diff against a base revision, review everything an epic's beads committed (located via bead commit trailers), or review explicit paths. The command reuses the existing reviewer agent and tier routing; it must not fork a second review implementation. Output: findings rendered to the terminal grouped by file with severity, and a persisted findings artifact under the run directory. A --json mode emits the findings through the shared JSON verb envelope so the command is scriptable and skill-callable. The command is read-only with respect to the repository: no commits, no bead writes, no fix loop — findings are for the human. Naming needs care: `maverick review` is taken by the assumption-review console. The spec should choose a name that will not collide or confuse (candidates: `maverick inspect`, `maverick critique`, `maverick review-code`). Out of scope: automated fixing of findings; CI integration; review of revisions not reachable from the current repository."

## Clarifications

### Session 2026-08-22

- Q: What should the command be called, given `maverick review` is taken by the assumption-review console? → A: `maverick critique`. `inspect` reads as a state/metadata dump in established CLI vocabulary (`docker inspect`, `git cat-file`) and would collide semantically with `brief` and `land --status`, which genuinely are state dumps. `review-code` is a hyphenated near-duplicate of an existing command and invites tab-completion confusion with `review`. `critique` is unambiguously a judgment, has no existing meaning in the Maverick surface, and shares no completion prefix with `review`.
- Q: Should the aggregate (epic-level) reviewer lens be reachable, or only the per-change correctness/completeness lenses? → A: Both lenses run for every scope, in parallel, exactly as the fly gate runs them; the epic scope additionally frames the prompt as a cross-change review. The command never exposes a lens-selection flag — a reviewer whose judgment the user must configure is a second implementation in disguise.
- Q: What is the exit code when findings exist? → A: Findings are information, not failure. Exit 0 whenever the review completed, regardless of finding count or severity. Only an inability to *perform* the review (bad scope, unavailable agent, unreadable repository) is a non-zero exit. A `--fail-on <severity>` flag provides opt-in gating for users who want a non-zero exit for scripting, defaulting to off.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review my uncommitted work before I push (Priority: P1)

A developer has made a set of changes by hand — or accepted an agent's changes and edited them — and wants Maverick's reviewer judgment before pushing. They run the command with no arguments in their checkout. The command reviews everything that differs between the working copy and the default base revision, prints findings grouped by file with severity, and exits without touching the repository.

**Why this priority**: This is the single most common on-demand review moment and the one with no workaround today. A developer's only current path to reviewer judgment is to manufacture a bead and run `maverick fly`, which commits work and mutates the bead graph — a wildly disproportionate side effect for "tell me if this is any good". Delivering only this story is already a complete, useful product.

**Independent Test**: Can be fully tested by making a change in a scratch repository, running the command with no scope flags, and verifying that findings referencing the changed file are printed and that `jj log`/`git status` are byte-identical before and after.

**Acceptance Scenarios**:

1. **Given** a checkout with uncommitted modifications to two files, **When** the developer runs the command with no scope arguments, **Then** the review covers both modified files and findings are printed grouped by file.
2. **Given** a checkout with no changes against the base revision, **When** the developer runs the command, **Then** the command reports that there is nothing to review and exits successfully without invoking any agent.
3. **Given** any completed review, **When** the command exits, **Then** no commit exists that did not exist before, no bead was created, updated, or closed, and no tracked file's content changed.

---

### User Story 2 - Review everything an epic produced (Priority: P2)

After a `maverick fly` run drains an epic, or after landing it, a developer wants one cross-cutting read of everything the epic's beads committed — the review that catches inconsistency *between* beads rather than within one. They name the epic; the command locates every commit the epic's beads produced and reviews their combined change.

**Why this priority**: `fly` already runs an aggregate review at loop exit, but it is unreachable after the fact — a developer who wants it again, or who wants it after `land` reorganized history, has no way to ask. Valuable, but it presupposes an epic exists, so it serves a narrower moment than Story 1.

**Independent Test**: Can be fully tested by creating an epic with two beads whose commits carry bead trailers, running the command scoped to that epic, and verifying the review covers the union of both commits' changes and no unrelated commit.

**Acceptance Scenarios**:

1. **Given** an epic whose beads produced three commits, **When** the developer scopes the review to that epic, **Then** the reviewed change is the combined difference those three commits introduced.
2. **Given** an epic identifier that does not exist, **When** the developer scopes the review to it, **Then** the command fails with a "not found" classification naming the identifier, and no agent is invoked.
3. **Given** an epic whose beads produced no commits yet, **When** the developer scopes the review to it, **Then** the command reports there is nothing to review and exits successfully.

---

### User Story 3 - Review specific paths regardless of what changed (Priority: P2)

A developer wants judgment on a subsystem as it stands — not on a diff. They name one or more paths; the command reviews the current content of those paths.

**Why this priority**: This is the "review a colleague's branch" and "audit this module" case. It is the only scope that answers a question about the code's present state rather than about a change, which makes it distinct rather than redundant — but it is also the least frequently needed of the three.

**Independent Test**: Can be fully tested by pointing the command at a directory containing a known defect and verifying a finding references a file inside that directory and none outside it.

**Acceptance Scenarios**:

1. **Given** a repository, **When** the developer scopes the review to a single directory, **Then** every finding's file reference falls inside that directory.
2. **Given** a path that does not exist in the repository, **When** the developer scopes the review to it, **Then** the command fails with a validation classification naming the path, and no agent is invoked.

---

### User Story 4 - Consume findings from a script or a skill (Priority: P2)

A tool — a Claude Code skill, a shell pipeline, another Maverick command — needs the findings as data. The developer adds the machine-readable output flag; the command emits a single structured document carrying every finding with its severity, file, line, and originating lens, in the same envelope shape every other machine-readable Maverick verb uses.

**Why this priority**: Without it the command is human-only and cannot be composed, which forecloses the review console's natural next step (a skill that reviews and then walks the findings interactively). It rides on Story 1's machinery rather than adding its own, so it is cheap once Story 1 exists.

**Independent Test**: Can be fully tested by running the command with the machine-readable flag against a change with a known defect and parsing the emitted document without any tolerance for extraneous output on the same stream.

**Acceptance Scenarios**:

1. **Given** any scope, **When** the command runs in machine-readable mode, **Then** exactly one structured document is written to the primary output stream and all progress and diagnostic prose goes elsewhere.
2. **Given** a failure to perform the review, **When** the command runs in machine-readable mode, **Then** the emitted document reports failure with a stable machine-branchable classification, and the process exit code is non-zero.
3. **Given** a successful review with findings, **When** the command runs in machine-readable mode, **Then** each finding carries its severity, file, line where known, the lens that raised it, and its issue text.

---

### User Story 5 - Findings persist for later reference (Priority: P3)

A developer runs a review, closes the terminal, and later wants the findings back — to paste into a pull-request description, to compare against a later review, or to hand to another agent.

**Why this priority**: Recoverability is genuinely useful and cheap, but a developer who loses the terminal output can simply re-run the review. It improves the feature rather than defining it.

**Independent Test**: Can be fully tested by running a review, verifying an artifact appears under the run directory, and confirming the artifact's findings match what was printed.

**Acceptance Scenarios**:

1. **Given** a completed review, **When** the command exits, **Then** a findings artifact exists under this run's directory containing every finding that was rendered.
2. **Given** a review that could not persist its artifact (unwritable directory), **When** the command exits, **Then** the findings are still rendered, a warning names the persistence failure, and the exit code still reflects the review outcome rather than the persistence failure.

---

### Edge Cases

- **Nothing to review**: an empty scope — no diff, an epic with no commits, or paths that exist but hold no reviewable content — must be reported as an empty result and exit successfully. It must never be reported as an error, and must never spend a model call.
- **Enormous scope**: a scope whose change is too large to review in one pass must be handled deterministically — either bounded with an explicit, reported truncation, or refused with a message naming the size — never silently partially reviewed. Silent truncation would present a partial review as a complete one.
- **Both lenses disagree**: the two reviewer lenses may raise findings on the same file and line. Both are retained and attributed; the command never merges or de-duplicates across lenses in a way that loses provenance.
- **Dirty working copy with an epic scope**: reviewing an epic's committed changes while uncommitted edits exist must review the committed change, not the working copy, and must say which it reviewed.
- **Conflicting scopes**: naming more than one scope (a base revision *and* an epic, for instance) is a validation failure with a message naming both, not a silent precedence rule.
- **Agent role unconfigured**: a repository with no reviewer binding must fail before any scope resolution work, with a message naming the missing configuration — the same failure mode every other agent-backed command already has.
- **Interruption**: interrupting mid-review must leave the repository untouched and must not leave a partial findings artifact that a later run would mistake for a complete one.
- **A protected context file inside the scope**: the review reads such files freely; only writes are protected. A review must never be degraded or blocked because a protected path is in scope.

## Requirements *(mandatory)*

### Functional Requirements

#### Command surface

- **FR-001**: The system MUST provide a standalone code-review command whose name is distinct from the existing assumption-review command in both spelling and completion prefix.
- **FR-002**: The command MUST accept exactly one scope selection per invocation, from three alternatives: a change against a base revision (the default), an epic's accumulated committed changes, or an explicit set of paths.
- **FR-003**: The command MUST default, when given no scope arguments, to the change between the working copy and a default base revision, so the most common invocation requires no arguments.
- **FR-004**: The command MUST reject an invocation naming more than one scope with a validation failure that names the conflicting selections.
- **FR-005**: The command MUST support a machine-readable output mode that emits exactly one structured document on the primary output stream, using the same envelope shape and failure taxonomy as every other machine-readable Maverick verb.
- **FR-006**: The command MUST support an opt-in flag that makes the process exit non-zero when findings at or above a named severity are present, defaulting to off.

#### Review execution

- **FR-007**: The command MUST perform its review using the existing reviewer agent, including its existing lens split and its existing per-complexity routing configuration. It MUST NOT introduce a second reviewer implementation, a second review prompt family, or a second result shape.
- **FR-008**: The command MUST run both reviewer lenses for every scope and retain the originating lens on every finding.
- **FR-009**: The command MUST detect an empty scope before invoking any agent and report an empty result without a model call.
- **FR-010**: The command MUST resolve an epic scope by locating the commits its beads produced through the bead identity recorded on those commits, and MUST fail with a "not found" classification when the named epic does not exist.
- **FR-011**: The command MUST tolerate a single lens failing: findings from the surviving lens are reported, and the failure is surfaced as a warning naming the lens. Only both lenses failing is a review failure.

#### Read-only guarantee

- **FR-012**: The command MUST NOT create, amend, or move any commit, MUST NOT create, update, or close any bead, and MUST NOT modify any tracked file. This holds on every path including every failure path.
- **FR-013**: The command MUST NOT run any fix loop, and MUST NOT re-invoke the reviewer after a first pass.
- **FR-014**: The command MUST NOT create assumption-ledger entries, and its findings MUST NOT affect the landing frontier gate.

#### Output

- **FR-015**: The command MUST render findings to the terminal grouped by file, showing each finding's severity, line where known, originating lens, and issue text, and MUST report the total finding count by severity.
- **FR-016**: The command MUST render an explicit "no findings" outcome distinguishable from "nothing was reviewed".
- **FR-017**: The command MUST persist a findings artifact under the current run's directory containing every rendered finding plus the resolved scope that produced them.
- **FR-018**: The command MUST treat a persistence failure as a warning that never changes the review outcome or the exit code.
- **FR-019**: The command MUST report the resolved scope it actually reviewed — which revision range, which epic and how many commits, or which paths — so a reader can tell what the findings do and do not cover.

#### Failure behavior

- **FR-020**: The command MUST exit successfully whenever the review completed, regardless of finding count or severity, unless the opt-in severity gate is engaged.
- **FR-021**: The command MUST classify each failure it can produce into the existing stable failure taxonomy, adding no new classification where an existing one fits.

### Key Entities

- **Review scope**: the resolved answer to "what is being reviewed" — one of a revision range, an epic with its located commits, or a path set. Carries enough detail to be reported back to the user verbatim.
- **Finding**: a single reviewer observation — severity, file, optional line, issue text, and the lens that raised it. Identical in shape to the findings the fly gate already produces.
- **Review report**: the complete outcome of one invocation — the resolved scope, the findings, per-severity counts, any lens that failed, and the identity of the run that produced it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer with uncommitted changes can obtain reviewer findings with a single argument-free invocation, with no prior setup beyond an already-configured repository.
- **SC-002**: Across every invocation, including every failure path and an interrupted run, the repository's commit graph, bead state, and tracked file contents are unchanged — verifiable by comparing complete before/after snapshots.
- **SC-003**: The findings a review produces for a given change are the same findings the existing per-change review path produces for that change, in the same shape — verifiable by comparing the two on identical input.
- **SC-004**: An empty scope completes with zero model calls, verifiable by asserting no agent invocation occurred.
- **SC-005**: The machine-readable mode's output parses as a single structured document on 100% of invocations, success and failure alike, with no extraneous output interleaved on that stream.
- **SC-006**: Every finding rendered to the terminal is present in the persisted artifact, and vice versa — verifiable by comparing the two for any invocation.
- **SC-007**: A user reading the command's output can state which revisions, epic, or paths the findings cover without consulting any other source.

## Assumptions

- The command name is `maverick critique`, per the clarification above. Where this spec says "the command", it means that.
- The default base revision for the change scope is the same base the repository's existing change-detection surfaces use, so a developer's mental model of "my changes" carries over unchanged. A flag allows naming a different base.
- Both reviewer lenses run in parallel, as they already do in the fly gate; this is a reuse of existing behavior rather than new concurrency.
- Epic scope locates commits through the bead identity already recorded on bead commits. No new commit metadata is introduced.
- The reviewer agent's existing per-complexity tier configuration applies unchanged. Because a standalone review has no decomposer-assigned complexity, it uses the role's base binding unless the user's configuration says otherwise.
- The run directory convention is the existing one; this feature introduces a new artifact within it, not a new location.
- Reviews are single-pass. There is no interactive follow-up, no clarification round, and no state carried between invocations.
- The existing context-file protection applies to this command's agent as it does to every other, at no additional cost — a read-only command has nothing to protect against, but the wiring is uniform rather than special-cased.

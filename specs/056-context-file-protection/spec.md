# Feature Specification: Context File Protection

**Feature Branch**: `056-context-file-protection`

**Created**: 2026-08-07

**Status**: Draft

**Input**: User description: "Add a safety hook that prevents agents from modifying agent-context files — AGENTS.md, CLAUDE.md, and the Spec Kit constitution — anywhere in the repository, unless the human has explicitly allowed it. Field data shows LLM-generated context files measurably reduce task success and raise cost, while human-curated ones compound in value. Maverick's own constitution and CLAUDE.md are load-bearing; an implementer agent 'helpfully' rewriting them mid-bead is silent corruption of the fleet's operating instructions. Behavior: any agent-initiated write (create, edit, delete, rename) targeting a protected path is blocked before it happens, the block is recorded as a structured event on the run, and the bead continues — a blocked context-file write is not a bead failure. The protected set defaults to AGENTS.md, CLAUDE.md, and .specify/memory/** at any depth, and is extensible via maverick.yaml (additional globs, or an explicit allowlist for repositories where agents are supposed to maintain such files). The hook applies to every agent role on every workflow, including inside isolated workspaces. The hook must fail closed for the protected set but must not degrade anything else: if the hook infrastructure itself errors, agent writes to unprotected paths proceed normally. Out of scope: protecting arbitrary user-designated files beyond the config mechanism; reviewing or reverting historical agent edits to context files."

## Clarifications

### Session 2026-08-07

- Q: When an agent writes through a channel that cannot be intercepted before the write happens, should the system fall back to detecting and restoring the file after the step, or simply document that channel as unprotected? → A: Pre-write blocking where the channel supports interception, plus a post-step detect-and-restore backstop on every agent step — an unauthorized mutation that slips through any channel is reverted and recorded as a block event.
- Q: Should a blocked context-file write ever create an assumption-ledger entry (and thereby interact with the land gate), or stay purely a run-scoped event plus warning? → A: Run-scoped structured events and a run summary warning only; blocks never create assumption-ledger entries and never affect the land gate.
- Q: How should protection treat symlinks — is a write matched against the path the agent names, or against the resolved target path? → A: Match resolved repository-relative paths; a write through a symlink whose resolved target is protected is blocked, and creating or replacing a symlink at a protected path is blocked.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Protected files survive an implementer's helpful rewrite (Priority: P1)

A developer runs a Maverick workflow (e.g. `maverick fly`) on a repository whose CLAUDE.md and Spec Kit constitution are carefully human-curated. Mid-bead, the implementer agent decides to "update the project documentation" and attempts to edit CLAUDE.md. The write is blocked before any byte changes on disk, the bead continues to completion, and the developer's context files are byte-identical to their pre-run state.

**Why this priority**: This is the core safety property. Silent corruption of the fleet's operating instructions degrades every subsequent run and is the entire motivation for the feature. Everything else (configurability, observability) is secondary to writes actually being prevented.

**Independent Test**: Can be fully tested by running any agent-driven workflow with an agent prompted (or induced in a test harness) to modify a default-protected file, and verifying the file's content hash is unchanged after the run while the run itself completes normally.

**Acceptance Scenarios**:

1. **Given** a repository with default protection and an unmodified CLAUDE.md, **When** an agent attempts to edit CLAUDE.md during a workflow, **Then** the edit is blocked before it occurs, the file is unchanged, and the workflow continues.
2. **Given** default protection, **When** an agent attempts to create a new AGENTS.md in a subdirectory, **Then** the creation is blocked (protection matches the default names at any depth) and the workflow continues.
3. **Given** default protection, **When** an agent attempts to delete or rename a file under `.specify/memory/`, **Then** the operation is blocked and the workflow continues.
4. **Given** default protection, **When** an agent attempts to rename an unprotected file *to* a protected name (e.g. `notes.md` → `CLAUDE.md`), **Then** the operation is blocked, because it would create or overwrite a protected path.
5. **Given** a blocked write, **When** the bead's remaining work needs no change to the protected file, **Then** the bead completes with its normal outcome — a blocked context-file write is never, by itself, a bead failure.

---

### User Story 2 - Every block is visible and auditable (Priority: P2)

After a run, the developer wants to know whether any agent tried to touch protected files. Each blocked attempt is recorded as a structured event on the run — which agent role, which workflow, which path, which operation (create/edit/delete/rename), and when — and the run's user-facing output surfaces that blocks happened, so silent prevention never becomes silent ignorance.

**Why this priority**: A block the human never learns about hides a signal: the agent believed the context files needed changing. The audit trail is what turns prevention into insight, and it is required for the human to decide whether to extend the allowlist.

**Independent Test**: Trigger a blocked write in a test workflow and verify a structured event is recorded on the run with role, workflow, path, and operation, and that the run summary output mentions the block count.

**Acceptance Scenarios**:

1. **Given** an agent's write to a protected path is blocked, **When** the run's events are inspected, **Then** a structured event exists identifying the agent role, the workflow, the target path, the attempted operation, and the time.
2. **Given** a run in which one or more blocks occurred, **When** the run completes, **Then** the user-facing output includes a warning summarizing the blocked attempts.
3. **Given** a run with no blocked attempts, **When** the run completes, **Then** no block-related output or events appear.

---

### User Story 3 - Repositories that want agents to maintain context files can opt in (Priority: P3)

A team maintains a repository where agents are *supposed* to keep AGENTS.md up to date. The team configures an explicit allowlist in the project configuration; agent writes to the allowed paths proceed normally while everything else in the protected set stays protected. Another team adds extra globs to protect additional context files beyond the defaults.

**Why this priority**: Configurability keeps the default strict without making the feature wrong for repositories with different conventions. It builds on P1's enforcement and is meaningless without it.

**Independent Test**: Configure an allowlist entry for AGENTS.md, run a workflow where an agent edits it, and verify the edit lands; simultaneously verify CLAUDE.md remains protected. Separately, add a custom glob and verify a matching file is now blocked.

**Acceptance Scenarios**:

1. **Given** configuration explicitly allowing agent writes to AGENTS.md, **When** an agent edits AGENTS.md, **Then** the edit proceeds and no block event is recorded.
2. **Given** configuration adding a custom protected glob (e.g. `docs/agent-rules/**`), **When** an agent writes to a matching path, **Then** the write is blocked exactly as for the default set.
3. **Given** an allowlist entry for one file, **When** an agent writes to a different default-protected file, **Then** that write is still blocked — allowlisting is per-path, not a global off-switch.
4. **Given** malformed protection configuration, **When** a workflow starts, **Then** the defaults remain in force (misconfiguration can never widen agent write access) and the user is warned.

---

### Edge Cases

- Agent writes a protected file inside an isolated workspace (the spec-chain's hidden workspace, or any future isolated execution): the block applies there too — otherwise the fold-back would land the corruption in the user's checkout.
- The hook infrastructure itself fails (internal error while evaluating a path): writes to protected paths remain blocked (fail closed for the protected set), while writes to unprotected paths proceed normally (no collateral degradation).
- Case-variant names (`claude.md`, `Agents.MD`): matching of the default protected names is case-insensitive, so trivially case-shifted paths can't bypass protection.
- Indirect mutation (an agent running a shell command like `sed -i` or `mv` against a protected file, rather than using a file-editing tool): where the channel cannot be intercepted pre-write, the post-step detect-and-restore backstop reverts the mutation and records it as a block event — no channel is silently unprotected.
- Symlink evasion (writing through a symlink that resolves to a protected file, or planting a symlink at a protected path): blocked — matching operates on resolved repository-relative paths.
- A rename where the *source* is protected and the destination is not (moving CLAUDE.md away) is blocked as a delete of a protected path.
- The human's own edits (outside any agent) are never affected: protection applies only to agent-initiated writes.
- A repeated blocked attempt within one bead (agent retries the same write): each attempt is blocked and recorded; the run summary reports them without spamming one warning line per retry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST block any agent-initiated write operation — create, edit, delete, or rename — targeting a protected path, before the operation mutates the file system, on every write channel that supports pre-write interception.
- **FR-002**: The default protected set MUST be: files named `AGENTS.md` and `CLAUDE.md` at any depth in the repository, and everything under `.specify/memory/` at any depth. Matching of these default names MUST be case-insensitive.
- **FR-003**: A rename or move MUST be treated as a write to both its source and destination paths; it is blocked if either side is protected.
- **FR-004**: A blocked write MUST NOT fail the bead or the workflow: the agent's unit of work continues, and its outcome is determined by its remaining work as usual.
- **FR-005**: Every blocked attempt MUST be recorded as a structured event on the run, carrying at minimum: agent role, workflow, target path (and destination path for renames), attempted operation (including restore, for backstop reverts), and timestamp. Block events are run-scoped only: they MUST NOT create assumption-ledger entries and MUST NOT affect the land gate.
- **FR-006**: A run in which one or more blocks occurred MUST surface a user-facing warning summarizing the blocked attempts; a run with none MUST stay silent on the topic.
- **FR-007**: The protected set MUST be extensible via project configuration with additional glob patterns, evaluated with the same semantics as the defaults.
- **FR-008**: Project configuration MUST support an explicit allowlist that exempts specific paths or globs from protection, for repositories where agents are intended to maintain such files. Allowlist entries exempt only what they match; all other protected paths remain protected.
- **FR-009**: Protection MUST apply to every agent role on every workflow, including agent execution inside isolated workspaces.
- **FR-010**: Protection MUST apply only to agent-initiated writes; deterministic workflow-owned operations and direct human edits are unaffected.
- **FR-011**: The hook MUST fail closed for the protected set: if protection evaluation itself errors for a given write, a write to a protected path is blocked. It MUST NOT degrade anything else: writes to unprotected paths proceed normally even when the hook infrastructure errors.
- **FR-012**: Malformed protection configuration MUST degrade to the default protected set with a user-facing warning — misconfiguration can never result in less protection than the defaults.
- **FR-013**: In addition to pre-write blocking, the system MUST run a post-step detect-and-restore backstop after every agent execution step: protected paths are compared against their pre-step state, any unauthorized mutation is restored to that state, and the restore is recorded as a block event. The protection guarantee is therefore universal across write channels — channels without pre-write interception are covered by the backstop, and documentation states which channels rely on it.
- **FR-014**: Path matching MUST operate on resolved, repository-relative paths: a write whose resolved target (after following symlinks) is protected is blocked regardless of the path the agent named, and creating or replacing a symlink at a protected path is itself blocked.

### Key Entities

- **Protected path set**: The effective set of path rules in force for a run — default rules (AGENTS.md, CLAUDE.md, `.specify/memory/**`) plus configured additional globs, minus configured allowlist entries.
- **Block event**: A structured record of one prevented write — agent role, workflow, operation, target path(s), timestamp — attached to the run's event stream and available for post-run audit.
- **Protection configuration**: The project-level settings controlling extension globs and the allowlist; absent configuration means defaults; malformed configuration means defaults plus a warning.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across a test matrix covering all four operations (create, edit, delete, rename) on all three default-protected targets, at every directory depth tried, and on both interceptable and non-interceptable write channels, 100% of agent write attempts leave the target files byte-identical to their pre-step state after the step completes (blocked pre-write, or restored by the backstop).
- **SC-002**: 100% of blocked attempts produce a structured, per-attempt audit record retrievable after the run, and every run containing at least one block surfaces a visible warning to the user.
- **SC-003**: Zero blocked context-file writes cause a bead or workflow failure by themselves: in tests where the agent's remaining work is otherwise valid, the bead completes successfully despite the block.
- **SC-004**: With an allowlist configured, 100% of allowed writes proceed and 100% of non-allowlisted protected writes remain blocked in the same run.
- **SC-005**: With protection active, workflows that never touch protected paths show no observable behavior change — no new warnings, no blocked events, no failures attributable to the hook.
- **SC-006**: In fault-injection tests where protection evaluation errors, writes to protected paths are still blocked and writes to unprotected paths still succeed, in 100% of trials.

## Assumptions

- "Agent-initiated write" means a file mutation performed by an agent through the write channels the platform gives it (file-editing tools and equivalent); deterministic file writes performed by the orchestrating workflows themselves (plans, run metadata, spec landing) are not agent-initiated and are out of scope for blocking.
- Protection scope is the repository the workflow operates on (and any isolated workspace mirroring it); files outside the repository tree are out of scope.
- The default protected name set is exactly `AGENTS.md`, `CLAUDE.md`, and `.specify/memory/**`; other context conventions (e.g. `.cursorrules`, `GEMINI.md`) are covered only via the configuration mechanism, not by default.
- Read access to protected files is unaffected — agents keep reading context files; only writes are controlled.
- The allowlist is configuration-file-based ("the human has explicitly allowed it" means an entry in project configuration), not an interactive per-run prompt — Maverick workflows run autonomously with no human watching.
- Blocking an agent's write surfaces to the agent as an ordinary failed tool operation with a reason, so the agent can continue its work without treating the block as a fatal error; the exact feedback wording is a design decision for the plan phase. A backstop restore happens after the step, so the agent learns of it (if at all) only from subsequent reads.
- Shell-command write channels (an agent invoking `sed`, `mv`, etc.) may not be pre-interceptable on every provider; per FR-013 those channels are covered by the post-step detect-and-restore backstop, and the plan phase determines which channels rely on it.

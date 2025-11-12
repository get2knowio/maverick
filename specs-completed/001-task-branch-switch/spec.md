# Feature Specification: Per-Task Branch Switching

**Feature Branch**: `001-task-branch-switch`  
**Created**: 2025-11-10  
**Status**: Draft  
**Input**: User description: "Per-task branch switching for Temporal AI workflow"

## Clarifications

### Session 2025-11-10
- Q: How should branch slugs be derived from task file names when no explicit branch is provided in the descriptor? → A: Branch name is specs subdir
- Q: When should `checkout_task_branch` fetch remote branch references before checking out? → A: Always fetch targeted branch first
- Q: How should `checkout_main` synchronize with the remote main branch? → A: Fast-forward only pull from origin
- Q: How should `delete_task_branch` behave if the branch is already missing? → A: Treat missing branch as success with log

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Branch context prepared (Priority: P1)

As an automation orchestrator, I need the workflow to ensure the repository is on the correct task branch before running any phase so that each task's changes stay isolated.

**Why this priority**: Running phases on the wrong branch will corrupt other task work and invalidate generated artifacts.

**Independent Test**: Trigger the workflow with a sample task descriptor and confirm phases start only after branch checkout succeeds and the branch matches the descriptor.

**Acceptance Scenarios**:

1. **Given** the workflow receives a task descriptor referencing an existing branch and the working tree is clean, **When** `checkout_task_branch` runs, **Then** the repository is on that branch and phase activities start only after the branch is verified.
2. **Given** the workflow is already on the target branch because of a retry, **When** `checkout_task_branch` runs again, **Then** the activity exits without altering the working tree and returns success.

---

### User Story 2 - Post-merge reset (Priority: P2)

As a release operator, I need the workflow to return the repository to main and clean up the task branch after the PR merges so the next task begins from a clean baseline.

**Why this priority**: Without a guaranteed reset to main, subsequent tasks may run on stale commits or conflict with leftover branches.

**Independent Test**: After simulating a merged PR, execute `checkout_main` and `delete_task_branch` within the workflow and confirm main is current and the task branch is removed locally.

**Acceptance Scenarios**:

1. **Given** the task PR merges successfully, **When** `checkout_main` runs, **Then** the working tree moves to main, syncs with remote, and is left clean for the next task.
2. **Given** the task branch was already deleted by an external process, **When** `delete_task_branch` runs, **Then** it completes without error and the workflow proceeds.

---

### User Story 3 - Branch naming transparency (Priority: P3)

As a workflow maintainer, I need clear rules that tie task files to branch names so automation can locate the correct branch and operators can audit task runs.

**Why this priority**: Transparent mapping prevents drift between specifications and Git branches, reducing manual investigation time.

**Independent Test**: Provide varied task file names and confirm the workflow derives deterministic branch slugs, logs the chosen branch, and honors explicit overrides.

**Acceptance Scenarios**:

1. **Given** a task descriptor pointing to `specs/005-sample-task/tasks.md`, **When** branch derivation runs, **Then** it resolves the branch name from the `specs` subdirectory (`005-sample-task`) and records it in workflow logs.
2. **Given** a task descriptor that explicitly specifies branch `005-sample-task`, **When** derivation runs, **Then** it honors the explicit branch value over the filename and records the decision.

### Edge Cases

- Branch named in the task descriptor does not exist locally or remotely; the workflow must halt with an actionable error before any phase activity runs.
- The working tree contains uncommitted changes when `checkout_task_branch` executes; the activity must report failure and avoid switching branches.
- Remote cleanup fails because the branch was already deleted or the network request times out; deletion activity must retry safely without corrupting the local repository.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Workflow MUST obtain a branch identifier for each task either from the task descriptor metadata or by resolving the `specs/<branch-name>/` directory that contains the task file, preserving the existing folder slug exactly.
- **FR-002**: Before any phase activity executes, workflow MUST call `checkout_task_branch(branch_name)` activity that ensures the working tree is clean, fetches `origin <branch_name>` to update remote refs, checks out the target branch, and confirms the resulting branch matches `branch_name`.
- **FR-003**: `checkout_task_branch` activity MUST be idempotent: if the repository is already on `branch_name` with a clean working tree, the activity MUST exit successfully without creating new commits or altering staged files.
- **FR-004**: Workflow MUST record the branch chosen for the task in workflow logs and task tracking context so auditors can verify which branch hosted each phase execution.
- **FR-005**: After the PR for the task merges, workflow MUST invoke `checkout_main()` activity that switches to the main branch, performs `git pull --ff-only origin main` to synchronize without divergent history, and verifies the working tree is clean before the next task starts.
- **FR-006**: Workflow MUST execute `delete_task_branch(branch_name)` after switching to main to remove the local branch safely; if the branch is already missing locally or remotely the activity MUST return success while recording the reason. The activity MUST NOT attempt remote branch deletion—policy dictates logging the remote status only—and it MUST remain idempotent so repeated calls never raise errors.
- **FR-007**: Branch management activities MUST surface explicit error messages and retry-safe exit codes when preconditions fail (e.g., dirty working tree, missing branch) so Temporal retry logic can either resolve on retry or escalate.
- **FR-008**: Workflow orchestration MUST follow the defined order: derive branch name → `checkout_task_branch` → run all phase activities → open/monitor PR → merge PR → `checkout_main` → `delete_task_branch` → proceed to the next task.

### Key Entities *(include if feature involves data)*

- **Task Descriptor**: Metadata object describing the automation task, including task file path, optional explicit branch name, task identifier, and phase list.
- **Branch Execution Context**: Runtime state captured per task run, containing resolved branch name, checkout status flags, and audit notes consumed by logging and monitoring.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of phase executions occur on the branch recorded in the task descriptor or derived slug, verified by comparing workflow branch logs against git history across a sample of at least 10 tasks.
- **SC-002**: After each merged PR, the main branch is restored and clean within 2 minutes, confirmed by workflow telemetry showing `checkout_main` completion timestamps relative to merge events.
- **SC-003**: Local task branches are absent after workflow completion in 95% of task runs, with remaining cases providing logged reason codes (e.g., manual inspection requested).
- **SC-004**: Operators report zero incidents of tasks running on the wrong branch during a two-week pilot, measured via incident tracking reviews.

## Assumptions

- Task descriptors always include either an explicit branch name or a pointer to a `specs/<branch-name>/tasks.md` file whose parent directory name is the authoritative branch slug.
- Remote deletion of branches may also be handled by existing PR tooling; local deletion remains necessary for cleanliness but does not enforce remote deletion.
- Temporal workflow has permissions to execute git or gh CLI commands with necessary credentials on the worker host.

# Feature Specification: Automated Review & Fix Loop for AI-Generated Rust Changes

**Feature Branch**: `001-automate-review-fix`  
**Created**: 2025-11-08  
**Status**: Draft  
**Input**: Temporal activity orchestrates CodeRabbit CLI review and OpenCode remediation for AI-generated Rust updates, ensuring repeatable runs, safe prompt handling, and test-verified outcomes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automation flags review outcome (Priority: P1)

Continuous delivery automation triggers the review loop after AI-generated Rust changes land on a feature branch so that it knows whether the branch is ready for human review without manual inspection.

**Why this priority**: Without an automated decision, the pipeline stalls or ships unreviewed code, directly impacting delivery speed and quality.

**Independent Test**: Run the activity on a branch with recent AI changes and verify it returns a structured "clean" or "issues-found" outcome without needing the fix portion.

**Acceptance Scenarios**:

1. **Given** a branch with AI-generated changes and no CodeRabbit findings, **When** the activity runs, **Then** it exits with status "clean" and records the CodeRabbit summary for audit use.
2. **Given** a branch where CodeRabbit detects blocking issues, **When** the activity runs, **Then** it marks status "issues-found" and prepares a sanitized remediation prompt.

---

### User Story 2 - Automation applies guided fixes (Priority: P2)

Release automation requests the loop to remediate CodeRabbit issues using OpenCode so that obvious regressions are resolved before human review.

**Why this priority**: Auto-fixing common review issues removes manual toil and keeps the branch in a testable state.

**Independent Test**: Provide a branch where CodeRabbit flags fixable issues and confirm the activity re-invokes OpenCode with the sanitized prompt, applies fixes, and re-runs validation.

**Acceptance Scenarios**:

1. **Given** CodeRabbit returns actionable items, **When** the activity invokes OpenCode with that prompt, **Then** the resulting changes address all listed issues without adding unrelated edits.
2. **Given** OpenCode fixes the issues but introduces a regression caught by tests, **When** the activity rechecks test status, **Then** it reports failure and provides artifacts for manual follow-up.

---

### User Story 3 - Automation supports safe retries (Priority: P3)

An orchestration service reruns the loop after a failure so that previously applied fixes are not duplicated and the next attempt focuses only on unresolved findings.

**Why this priority**: Temporal retries and later CI replays must be idempotent to avoid conflicting edits or prompt loops.

**Independent Test**: Execute the activity twice in succession against the same branch when no new commits were added and confirm the second run does not reapply the same fix attempt.

**Acceptance Scenarios**:

1. **Given** the first run stored a fingerprint of CodeRabbit findings, **When** a retry sees the identical fingerprint, **Then** it skips launching a duplicate OpenCode fix and surfaces the stored result instead.
2. **Given** new commits land between runs, **When** the activity detects a different fingerprint, **Then** it proceeds with a fresh review and fix cycle.

---

### Edge Cases

- CodeRabbit CLI fails, times out, or returns malformed output that cannot be parsed.
- CodeRabbit produces sensitive text that must be redacted before forwarding to OpenCode or logs.
- OpenCode returns no changes or refuses the prompt, leaving issues unresolved.
- `cargo test` fails due to environmental issues unrelated to the recent changes.
- A retry occurs after partial success where tests passed but logging of the prompt failed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The activity MUST accept the target branch identifier, prior implementation summary, and optional retry metadata as structured input.
- **FR-002**: The activity MUST invoke CodeRabbit CLI in plain-text prompt mode, capture its findings, and normalize them into structured issues plus the generated remediation prompt.
- **FR-003**: The activity MUST sanitize CodeRabbit output (e.g., remove secrets, enforce length limits) before storing it or passing it to downstream AI tools.
- **FR-004**: If CodeRabbit reports no actionable findings, the activity MUST end the run immediately with a "clean" status while preserving the CodeRabbit transcript.
- **FR-005**: When findings exist, the activity MUST invoke OpenCode with a task description that includes the branch context and the sanitized CodeRabbit prompt, and it MUST ensure the invocation is traceable in logs.
- **FR-006**: After OpenCode completes, the activity MUST run `cargo test` (or the configured validation command) and classify the outcome as pass, fail, or incomplete.
- **FR-007**: The activity MUST emit a final result object indicating whether the branch is "clean" or "fixed <issue-count> issues" along with test status, artifacts, and timestamps.
- **FR-008**: The activity MUST record a deterministic fingerprint of the reviewed commit(s) and CodeRabbit findings so retries can detect prior identical attempts and skip redundant fixes.
- **FR-009**: The activity MUST expose the sanitized CodeRabbit prompt and resulting OpenCode summary so that downstream tooling can attach them to a pull request without recomputation.
- **FR-010**: The activity MUST escalate with a failure status when CodeRabbit, OpenCode, or tests fail in a way that prevents confident review readiness, providing actionable diagnostics.

### Key Entities *(include if feature involves data)*

- **ReviewLoopInput**: Contains branch identifier, implementation summary, validation command, retry counters, and flags controlling fix attempts.
- **CodeReviewFindings**: Captures normalized issue list, raw transcript hash, sanitized prompt text, severity counts, and timestamps.
- **FixAttemptRecord**: Stores OpenCode request metadata, commit/patch identifiers produced by the fix, and test outcomes tied to the attempt fingerprint.
- **ReviewLoopOutcome**: Aggregates final status (`clean`, `fixed`, `failed`), counts of issues addressed, test summary, and references to stored prompts/logs for audit.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 95% of runs where CodeRabbit reports no findings, the activity completes within 2 minutes and returns status "clean" with preserved audit artifacts.
- **SC-002**: For branches with CodeRabbit findings deemed actionable, at least 80% of runs reach status "fixed" after a single OpenCode invocation without manual intervention.
- **SC-003**: 100% of runs produce an accessible record of the sanitized CodeRabbit prompt and validation results for downstream review tools.
- **SC-004**: Repeated runs against an unchanged branch do not trigger duplicate OpenCode fixes more than once per unique findings fingerprint, ensuring idempotent behavior in 100% of tested retries.

## Assumptions

- CodeRabbit CLI and OpenCode tooling are available on the worker with required authentication and rate limits managed externally.
- The activity receives permission to run `cargo test` or an equivalent validation command in the branch workspace.
- Branches include deterministic metadata (e.g., commit SHAs) that can be hashed to detect identical runs.
- Downstream systems handle persistence of prompts and artifacts once returned by the activity.

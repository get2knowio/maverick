# Feature Specification: Review-Fix Accountability Loop

**Feature Branch**: `029-review-fix-accountability`
**Created**: 2025-01-05
**Status**: Draft

## Motivation

The current review-fix workflow has an accountability gap. After parallel code reviews identify issues, the fixer agent can:

1. Silently skip issues without explanation
2. Defer issues with weak excuses ("not my change", "out of scope", "takes too long")
3. Claim to fix issues without actually addressing them
4. Leave no audit trail of what was attempted vs. what remains

This results in technical debt accumulating invisibly. Developers finish a workflow thinking everything is resolved, but issues remain untracked.

## Goals

1. **Complete visibility**: Every review finding is tracked from discovery through resolution or issue creation
2. **Fixer accountability**: The fixer must report on every issue - no silent skipping
3. **Pressure to fix**: Deferred issues return to the fixer on subsequent iterations
4. **Audit trail**: Full history of fix attempts and justifications preserved
5. **Automatic issue creation**: Unresolved items become GitHub issues labeled as tech-debt

## Non-Goals

1. Re-running reviewers after each fix iteration (single review pass is sufficient)
2. Forcing infinite fix loops (max iterations prevents runaway)
3. Verifying that "fixed" claims are actually correct (trust but track)
4. Blocking PR creation on unresolved issues (issues are created, not blockers)

## User Scenarios & Testing

### User Story 1 - Transparent Fix Progress (Priority: P1)

A developer runs the feature workflow. After the review-fix loop completes, they see exactly what was fixed, what's blocked, and what became GitHub issues.

**Why this priority**: Core value proposition - without visibility, there's no accountability. This enables all other stories.

**Independent Test**: Can be tested by running a workflow with known issues and verifying the summary output matches reality.

**Acceptance Scenarios**:

1. **Given** a codebase with 5 critical issues found by reviewers, **When** the fixer resolves 3 and marks 2 as blocked, **Then** the developer sees a summary showing "3 fixed, 2 blocked → issues created" and can view the created issues.

2. **Given** a fixer that provides no status for an issue, **When** the iteration completes, **Then** that issue is automatically marked as "deferred" with justification "Agent did not provide status" and re-queued for next iteration.

3. **Given** the workflow completes, **When** the developer views PR #X, **Then** any created tech-debt issues reference the PR in their body.

---

### User Story 2 - Fixer Accountability (Priority: P1)

The fixer agent cannot escape responsibility for issues by using weak excuses. Deferred items return until fixed or max iterations reached.

**Why this priority**: Prevents the primary failure mode - weak excuses allowing issues to slip through. Equal priority to transparency since both are essential.

**Independent Test**: Can be tested by simulating a fixer that uses known weak excuses and verifying re-queue behavior.

**Acceptance Scenarios**:

1. **Given** the fixer defers an issue with "this is a pre-existing issue", **When** the next iteration runs, **Then** the fixer receives that same issue again with its previous excuse shown.

2. **Given** the fixer defers the same issue 3 times (max iterations), **When** the loop exits, **Then** a GitHub issue is created with all 3 justifications listed in the body.

3. **Given** 5 critical issues, **When** the fixer marks all as "deferred" on iteration 1, **Then** all 5 are re-sent on iteration 2 with "Previous deferrals were not accepted" warning.

---

### User Story 3 - Blocked vs Deferred Distinction (Priority: P2)

Genuine blockers are accepted and become issues immediately. Weak deferrals are rejected and retried.

**Why this priority**: Enhances accountability by distinguishing legitimate blockers from excuses. Lower priority because system works without it (all non-fixed items would just retry).

**Independent Test**: Can be tested by providing blocked items with valid vs invalid justifications and checking routing behavior.

**Acceptance Scenarios**:

1. **Given** the fixer marks an issue as "blocked" with "Requires AWS credentials not in codebase", **When** the next iteration runs, **Then** that issue is NOT re-sent to the fixer.

2. **Given** the fixer marks a critical issue as "blocked" with "Would take too long", **When** validation runs, **Then** the justification is flagged as invalid (matches known weak excuse patterns).

3. **Given** 2 blocked and 3 deferred issues after iteration 1, **When** iteration 2 runs, **Then** only the 3 deferred issues are sent to the fixer.

---

### User Story 4 - Tech Debt Issue Creation (Priority: P1)

All unresolved findings become properly formatted GitHub issues with full context.

**Why this priority**: Ensures nothing is lost - unresolved items become tracked work items. Critical for the "complete visibility" goal.

**Independent Test**: Can be tested by running workflow to completion and verifying issue creation with correct labels and content.

**Acceptance Scenarios**:

1. **Given** a blocked finding with severity "critical", **When** the issue is created, **Then** it has labels ["tech-debt", "critical"] and title "[CRITICAL] {finding title}".

2. **Given** a finding with 3 fix attempts, **When** its GitHub issue is created, **Then** the body includes a "Fix Attempts" section listing all 3 attempts with their justifications.

3. **Given** a minor finding that was never sent to fixer, **When** the workflow completes, **Then** it becomes a GitHub issue labeled ["tech-debt", "minor"].

---

### User Story 5 - Structured Review Output (Priority: P2)

Reviewers output structured findings that can be tracked through the system.

**Why this priority**: Enables tracking but is implementation detail. System could work with unstructured output (with reduced tracking quality).

**Independent Test**: Can be tested by running reviewers against known code and verifying structured output format.

**Acceptance Scenarios**:

1. **Given** a spec reviewer analyzing a PR, **When** it finds issues, **Then** each issue has: id, severity, category, title, description, file_path, line range, and suggested_fix.

2. **Given** both spec and tech reviewers find the same issue, **When** findings are merged, **Then** duplicates are detected and consolidated (same file + overlapping lines + similar description).

3. **Given** a reviewer output missing required fields, **When** parsing occurs, **Then** validation fails with specific error messages about missing fields.

---

### Edge Cases

- What happens when a reviewer returns no findings? (Empty registry, skip fix loop)
- What happens when all findings are minor severity? (Skip fix loop, create issues directly)
- What happens when the fixer deletes a file referenced by a finding? → System auto-marks as "blocked" with justification "Referenced file deleted" (no fixer action required)
- What happens when max iterations is set to 0? (Skip fix loop entirely, all findings become issues)
- What happens when issue creation fails due to rate limits? (Retry with exponential backoff, warn user on persistent failure)
- What happens when duplicate findings span different files? (Consolidate only within same file)

## Requirements

### Functional Requirements

- **FR-001**: System MUST track every review finding from discovery through resolution or issue creation
- **FR-002**: System MUST require the fixer to report status on every issue assigned to it
- **FR-003**: System MUST automatically re-queue deferred issues for subsequent fix iterations
- **FR-004**: System MUST distinguish between "blocked" (legitimate) and "deferred" (weak excuse) statuses
- **FR-005**: System MUST create tracked work items for all unresolved findings at workflow end
- **FR-006**: System MUST preserve full attempt history (iterations, justifications, outcomes) for each finding
- **FR-007**: System MUST detect and consolidate duplicate findings from multiple reviewers
- **FR-008**: System MUST exit the fix loop when no actionable items remain OR max iterations reached
- **FR-009**: System MUST label created work items with severity level and "tech-debt" category
- **FR-010**: System MUST auto-defer findings when fixer provides no status (with explanatory justification)

### Key Entities

- **ReviewFinding**: A single issue discovered by a reviewer (severity, category, location, description)
- **TrackedFinding**: A finding with status tracking and attempt history through the fix loop
- **FixAttempt**: A record of one iteration's outcome for a finding (iteration, outcome, justification)
- **IssueRegistry**: Collection of tracked findings with query methods for workflow orchestration

## Technical Design

### Data Models

```
ReviewFinding
├── id: str (RS001, RT001, etc.)
├── severity: critical | major | minor
├── category: security | correctness | performance | ...
├── title: str
├── description: str
├── file_path: str?
├── line_start: int?
├── line_end: int?
├── suggested_fix: str?
└── source: str (spec_reviewer | tech_reviewer)

TrackedFinding
├── finding: ReviewFinding
├── status: open | fixed | blocked | deferred
├── attempts: list[FixAttempt]
└── github_issue_number: int?

FixAttempt
├── iteration: int
├── timestamp: datetime
├── outcome: fixed | blocked | deferred
├── justification: str?
└── changes_made: str?

IssueRegistry
├── findings: list[TrackedFinding]
├── current_iteration: int
└── max_iterations: int
```

### Workflow Flow

```
┌─────────────────────────────────────────────┐
│ REVIEW PHASE (once)                         │
│                                             │
│   Spec Reviewer ──┐                         │
│                   ├──▶ Merge ──▶ Registry   │
│   Tech Reviewer ──┘                         │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ FIX LOOP (up to N iterations)               │
│                                             │
│   Filter: severity in (critical, major)     │
│           AND status in (open, deferred)    │
│                     ▼                       │
│   Fixer Agent (must report on ALL)          │
│                     ▼                       │
│   Update Registry                           │
│                     ▼                       │
│   Exit if: no actionable OR iteration == N  │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ ISSUE CREATION                              │
│                                             │
│ blocked + deferred + minor → GitHub issues  │
│ Labels: tech-debt, {severity}               │
└─────────────────────────────────────────────┘
```

### Fixer Accountability Rules

**Invalid justifications** (result in re-queue):
- "This is unrelated to the current changes"
- "This would take too long"
- "This is out of scope"
- "This is a pre-existing issue"
- "This requires significant refactoring"

**Valid justifications for blocked**:
- Requires external credentials/access
- Depends on human decision about intended behavior
- Referenced file/module does not exist
- Fixing would break X and correct behavior is ambiguous

### Exit Conditions

The fix loop exits when:
1. No findings with `status in (open, deferred)` AND `severity in (critical, major)`, OR
2. `current_iteration >= max_iterations`

## Configuration

```yaml
# In workflow inputs
max_fix_iterations: 3        # Default: 3
create_issues: true          # Default: true
issue_labels: ["tech-debt"]  # Default: ["tech-debt"]
```

## Dependencies

- Existing reviewer agents (spec_reviewer, tech_reviewer) - need structured output
- Existing fixer agent (review_fixer) - needs accountability prompt
- GitHub CLI (gh) for issue creation
- DSL loop construct with break_when support

## Success Metrics

1. **Zero silent skips**: Every finding has a recorded status at workflow end
2. **Reduced deferrals over iterations**: Iteration 2 should have fewer deferrals than iteration 1
3. **Issue coverage**: 100% of unresolved findings become GitHub issues
4. **Audit completeness**: Every created issue includes full attempt history

## Clarifications

### Session 2025-01-05

- Q: Should "fixed" claims be validated by re-running tests/linters? → A: No, trust fixer claims without verification (aligns with "trust but track" non-goal)
- Q: Should we support "partial fix" status? → A: No, use "deferred" with justification explaining what remains
- Q: How to handle findings referencing deleted files? → A: Auto-mark as "blocked" with system justification "Referenced file deleted"
- Q: Should blocked critical issues require human approval before becoming issues? → A: No, create issues automatically (approval gate deferred to future iteration)

## Alternatives Considered

### Re-review after each fix iteration
**Rejected**: Adds latency and cost. New issues found mid-loop complicate tracking. The goal is accountability for known issues, not continuous discovery.

### Force loop until all issues fixed (no max iterations)
**Rejected**: Risk of infinite loops. Diminishing returns after 2-3 attempts. Some issues may genuinely require human intervention.

### User approval gate before issue creation
**Considered**: Could add optional `require_approval: true` flag. Deferred to future iteration to keep initial implementation simple.

# Implementation Plan: Review-Fix Accountability Loop

**Branch**: `029-review-fix-accountability` | **Date**: 2025-01-05 | **Spec**: [spec.md](spec.md)

## Summary

Implement an accountability-focused review-fix loop that tracks every finding from discovery through resolution or issue creation. The system requires fixers to report on all issues, re-queues weak deferrals, and creates GitHub issues for unresolved items with full attempt history.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK, Pydantic, PyYAML, GitHub CLI (`gh`)
**Storage**: In-memory during workflow; optional JSON checkpoints under `.maverick/checkpoints/`
**Testing**: pytest + pytest-asyncio
**Target Platform**: CLI/TUI (Linux, macOS, Windows)
**Project Type**: Single project (extension to existing Maverick codebase)
**Performance Goals**: N/A (workflow orchestration, not high-throughput)
**Constraints**: Must integrate with existing DSL loop construct, reviewer agents, fixer agent
**Scale/Scope**: Typical review yields 5-20 findings per PR

## Constitution Check

*GATE: All principles verified compliant*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ | All actions are async; workflow yields progress updates |
| II. Separation of Concerns | ✅ | Agents provide judgment; workflows own execution/retries |
| III. Dependency Injection | ✅ | Registry passed to actions; no global state |
| IV. Fail Gracefully | ✅ | Missing fixer output auto-defers; rate limit retry |
| V. Test-First | ✅ | Unit + integration tests in Phase 6 |
| VI. Type Safety | ✅ | Frozen dataclasses with `to_dict()` for all models |
| VII. Simplicity & DRY | ✅ | Single registry module; no duplication |
| VIII. Relentless Progress | ✅ | Loop exits on max iterations; partial results preserved |
| IX. Hardening by Default | ✅ | GitHub API calls have retry with exponential backoff |
| X. Architectural Guardrails | ✅ | Actions return typed contracts, not dicts |
| XI. Modularize Early | ✅ | Models in dedicated module; actions in registry.py |
| XII. Ownership | ✅ | All findings tracked to resolution |

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Workflow Layer                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  review-and-fix-with-registry.yaml                          │    │
│  │  (orchestrates the full flow)                               │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│    Agent Layer       │ │   Model Layer    │ │   Action Layer       │
│                      │ │                  │ │                      │
│ • SpecReviewer       │ │ • ReviewFinding  │ │ • create_registry    │
│   (structured out)   │ │ • TrackedFinding │ │ • prepare_fixer_input│
│ • TechReviewer       │ │ • FixAttempt     │ │ • update_registry    │
│   (structured out)   │ │ • IssueRegistry  │ │ • check_exit         │
│ • ReviewFixer        │ │ • FixerInput     │ │ • create_issues      │
│   (accountability)   │ │ • FixerOutput    │ │ • detect_deleted_files│
└──────────────────────┘ └──────────────────┘ └──────────────────────┘
```

### File Structure

```
src/maverick/
├── models/
│   ├── review_registry.py      # NEW: Registry and finding models
│   └── fixer_io.py             # NEW: Fixer input/output models
├── agents/
│   ├── prompts/
│   │   ├── review_fixer.py     # NEW: Accountability-focused prompt
│   │   └── reviewer_output.py  # NEW: Structured output schema
│   ├── review_fixer.py         # MODIFY: Add accountability logic
│   ├── spec_reviewer.py        # MODIFY: Structured output
│   └── tech_reviewer.py        # MODIFY: Structured output
├── library/
│   ├── actions/
│   │   ├── review_registry.py  # NEW: Registry management actions
│   │   └── types.py            # MODIFY: Add TechDebtIssueResult
│   └── fragments/
│       └── review-and-fix-with-registry.yaml  # NEW: Main workflow
└── dsl/
    └── context_builders.py     # MODIFY: Add review_fixer_context
```

## Implementation Phases

### Phase 1: Data Models

Create the core data structures for tracking findings.

**Files**:
- `src/maverick/models/review_registry.py`
- `src/maverick/models/fixer_io.py`

**Key Classes**:
```python
# Enums
Severity: critical | major | minor
FindingStatus: open | fixed | blocked | deferred
FindingCategory: security | correctness | performance | ...

# Core Models
ReviewFinding      # Immutable finding from reviewer
FixAttempt         # Record of single fix attempt
TrackedFinding     # Finding + status + attempt history
IssueRegistry      # Collection with query methods

# I/O Models
FixerInputItem     # Single item sent to fixer
FixerInput         # Complete fixer input with metadata
FixerOutputItem    # Single item in fixer response
FixerOutput        # Complete fixer response with validation
```

**Validation Rules**:
- FixerOutput must have entry for every FixerInput item
- blocked/deferred outcomes require justification
- Severity must be valid enum value

### Phase 2: Registry Actions

Implement the workflow actions for registry management.

**Files**:
- `src/maverick/library/actions/review_registry.py`
- `src/maverick/library/actions/types.py`

**Actions**:

| Action | Purpose | Input | Output |
|--------|---------|-------|--------|
| `create_issue_registry` | Initialize registry from reviews | spec_findings, tech_findings | IssueRegistry |
| `prepare_fixer_input` | Filter and format for fixer | registry | FixerInput |
| `update_issue_registry` | Apply fixer results | registry, fixer_output | IssueRegistry |
| `check_fix_loop_exit` | Determine if loop continues | registry | {should_exit, reason, ...} |
| `create_tech_debt_issues` | Create GitHub issues | registry, labels | list[TechDebtIssueResult] |
| `detect_deleted_files` | Auto-block findings for deleted files | registry | IssueRegistry |

**Deduplication Logic** (in `create_issue_registry`):
- Same file + overlapping line range (±5 lines)
- Levenshtein distance on title < 0.3
- Keep higher severity, merge descriptions

**Deleted File Handling** (from clarifications):
- Before each fix iteration, check if referenced files exist
- Auto-mark as "blocked" with system justification "Referenced file deleted"
- No fixer action required for deleted file findings

### Phase 3: Reviewer Structured Output

Modify reviewers to output structured JSON findings.

**Files**:
- `src/maverick/agents/prompts/reviewer_output.py`
- `src/maverick/agents/spec_reviewer.py`
- `src/maverick/agents/tech_reviewer.py`

**Changes**:
1. Add output schema to system prompts
2. Parse JSON from agent response
3. Validate required fields
4. Convert to ReviewFinding objects

**Output Schema**:
```json
{
  "findings": [
    {
      "severity": "critical",
      "category": "security",
      "title": "SQL injection in user search",
      "description": "...",
      "file_path": "src/api/users.py",
      "line_start": 87,
      "line_end": 92,
      "suggested_fix": "Use parameterized queries"
    }
  ],
  "summary": "Found 3 issues: 1 critical, 2 major"
}
```

### Phase 4: Fixer Accountability

Implement the accountability-focused fixer agent.

**Files**:
- `src/maverick/agents/prompts/review_fixer.py`
- `src/maverick/agents/review_fixer.py`
- `src/maverick/dsl/context_builders.py`

**System Prompt Key Points**:
1. Must report on EVERY issue
2. List of invalid justifications
3. List of valid blocked reasons
4. Warning that deferred items return
5. Show previous attempts in prompt

**Fixer Flow**:
```
1. Receive FixerInput with all open/deferred items
2. For each item:
   a. Read the file/context
   b. Make code changes (Edit/Write tools)
   c. Record what was done
3. Output JSON with status for EVERY item
4. Validate output completeness
5. Auto-defer any missing items
```

**Clarification: No Fix Verification**
- Per spec clarifications, "fixed" claims are trusted without re-running tests/linters
- Aligns with "trust but track" non-goal
- Full attempt history preserved for audit

**Clarification: No Partial Fix Status**
- Use "deferred" with justification explaining what remains
- Keeps status enum simple: open | fixed | blocked | deferred

### Phase 5: Workflow Integration

Create the workflow fragment that ties everything together.

**Files**:
- `src/maverick/library/fragments/review-and-fix-with-registry.yaml`

**Workflow Structure**:
```yaml
steps:
  - gather_context      # Existing action
  - parallel_reviews    # Spec + Tech in parallel
  - create_registry     # New: Initialize tracking
  - detect_deleted      # New: Auto-block deleted file findings
  - fix_loop           # Loop with break_when
    - prepare_input
    - run_fixer
    - update_registry
    - check_exit
  - create_issues      # New: GitHub issue creation
```

**Integration Points**:
- Replace existing `review-and-fix.yaml` usage in `feature.yaml`
- Ensure registry state persists across loop iterations
- Handle empty actionable list (skip fixer, exit loop)

**Clarification: No Human Approval Gate**
- Per spec clarifications, blocked critical issues become GitHub issues automatically
- Approval gate deferred to future iteration

### Phase 6: Testing

**Unit Tests**:
- `tests/unit/models/test_review_registry.py`
- `tests/unit/models/test_fixer_io.py`
- `tests/unit/library/actions/test_review_registry_actions.py`

**Integration Tests**:
- `tests/integration/workflows/test_review_fix_accountability.py`

**Test Scenarios**:
1. Registry correctly filters actionable items
2. Deferred items re-queue on next iteration
3. Blocked items don't re-queue
4. Missing fixer output auto-defers
5. Issue creation includes attempt history
6. Loop exits at max iterations
7. Loop exits when no actionable items
8. Deleted file findings auto-blocked (new from clarifications)

## Migration Strategy

### Backward Compatibility

The existing `review-and-fix.yaml` fragment will remain available. The new `review-and-fix-with-registry.yaml` is opt-in.

### Gradual Rollout

1. **Phase 1-4**: Build components without changing existing workflows
2. **Phase 5**: Create new workflow fragment
3. **Test**: Validate with manual `maverick fly` runs
4. **Phase 6**: Update `feature.yaml` to use new fragment by default
5. **Deprecate**: Mark old fragment as deprecated after 2 releases

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Fixer output parsing fails | Auto-defer missing items, log warning |
| Infinite loop on stubborn issues | Hard max_iterations limit (default: 3) |
| GitHub API rate limits on issue creation | Batch issues, add retry with backoff |
| Reviewer output not structured | Graceful fallback to unstructured parsing |
| Registry state lost mid-workflow | Checkpoint registry after each iteration |
| Referenced file deleted during fix | Auto-block with system justification (clarification) |

## Dependencies

### Required Before Implementation

1. DSL loop `break_when` support (verify exists)
2. Parallel step output access syntax (verify `steps.parallel.child.output`)
3. Registry serialization for checkpoints

### External Dependencies

- `gh` CLI for issue creation
- GitHub API permissions for issue creation

## Success Criteria

1. All unit tests pass
2. Integration test demonstrates full flow
3. Manual test with real codebase shows:
   - Findings tracked from review to resolution
   - Deferred items returned to fixer
   - GitHub issues created with full history
   - Deleted file findings auto-blocked
4. No regression in existing workflow behavior

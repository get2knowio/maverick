# Data Model: Flight Plan and Work Unit

**Feature**: 037-flight-plan-models
**Date**: 2026-02-27

## Entity Relationship Diagram

```text
FlightPlan (1) ──────< WorkUnit (*)
    │                      │
    ├── SuccessCriterion    ├── AcceptanceCriterion ──> SuccessCriterion (trace ref)
    │   (*)                 │   (*)
    ├── Scope (1)           ├── FileScope (1)
    │   ├── in_scope        │   ├── create
    │   ├── out_of_scope    │   ├── modify
    │   └── boundaries      │   └── protect
    │                       │
    └── CompletionStatus    └── VerificationStep (*)
        (computed)
```

## Entities

### FlightPlan

Frozen Pydantic model representing a Flight Plan document.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `name` | `str` | Yes | Non-empty | YAML frontmatter `name` |
| `version` | `str` | Yes | Non-empty | YAML frontmatter `version` |
| `created` | `date` | Yes | Valid date | YAML frontmatter `created` |
| `tags` | `tuple[str, ...]` | Yes | Any strings | YAML frontmatter `tags` |
| `objective` | `str` | Yes | - | `## Objective` section |
| `success_criteria` | `tuple[SuccessCriterion, ...]` | Yes | - | `## Success Criteria` section |
| `scope` | `Scope` | Yes | - | `## Scope` section |
| `context` | `str` | No | - | `## Context` section |
| `constraints` | `tuple[str, ...]` | No | - | `## Constraints` section |
| `notes` | `str` | No | - | `## Notes` section |
| `source_path` | `Path \| None` | No | - | Set by loader |

**Computed properties**:
- `completion` → `CompletionStatus`: Returns checked/total/percentage from success criteria.

**Pydantic config**: `model_config = ConfigDict(frozen=True)`

### SuccessCriterion

Frozen Pydantic model for a single success criterion with checkbox state.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `text` | `str` | Yes | Non-empty | Checkbox line text |
| `checked` | `bool` | Yes | - | `[x]` = True, `[ ]` = False |

### CompletionStatus

Frozen Pydantic model representing completion state (computed, not stored).

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `checked` | `int` | Yes | `>= 0` | Count of checked criteria |
| `total` | `int` | Yes | `>= 0` | Total criteria count |
| `percentage` | `float \| None` | Yes | `0.0-100.0` or None | `checked/total*100`, None if total=0 |

### Scope

Frozen Pydantic model for the Scope section with three subsections.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `in_scope` | `tuple[str, ...]` | Yes | - | `### In` subsection bullets |
| `out_of_scope` | `tuple[str, ...]` | Yes | - | `### Out` subsection bullets |
| `boundaries` | `tuple[str, ...]` | Yes | - | `### Boundaries` subsection bullets |

### WorkUnit

Frozen Pydantic model representing a Work Unit document.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `id` | `str` | Yes | Kebab-case: `^[a-z0-9]+(-[a-z0-9]+)*$` | YAML frontmatter `work-unit` |
| `flight_plan` | `str` | Yes | Non-empty | YAML frontmatter `flight-plan` |
| `sequence` | `int` | Yes | Positive integer (`>= 1`) | YAML frontmatter `sequence` |
| `parallel_group` | `str \| None` | No | - | YAML frontmatter `parallel-group` |
| `depends_on` | `tuple[str, ...]` | No | Each must be kebab-case | YAML frontmatter `depends-on` |
| `task` | `str` | Yes | - | `## Task` section |
| `acceptance_criteria` | `tuple[AcceptanceCriterion, ...]` | Yes | - | `## Acceptance Criteria` section |
| `file_scope` | `FileScope` | Yes | - | `## File Scope` section |
| `instructions` | `str` | Yes | - | `## Instructions` section |
| `verification` | `tuple[str, ...]` | Yes | - | `## Verification` section |
| `provider_hints` | `str \| None` | No | - | `## Provider Hints` section |
| `source_path` | `Path \| None` | No | - | Set by loader |

### AcceptanceCriterion

Frozen Pydantic model for a single acceptance criterion with optional traceability.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `text` | `str` | Yes | Non-empty | Bullet line text |
| `trace_ref` | `str \| None` | No | `SC-\d+` format | `[SC-###]` suffix |

### FileScope

Frozen Pydantic model for the File Scope section with three file lists.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `create` | `tuple[str, ...]` | Yes | - | `### Create` subsection |
| `modify` | `tuple[str, ...]` | Yes | - | `### Modify` subsection |
| `protect` | `tuple[str, ...]` | Yes | - | `### Protect` subsection |

### ExecutionOrder

Frozen Pydantic model representing resolved execution order.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `batches` | `tuple[ExecutionBatch, ...]` | Yes | Non-empty | Resolver output |

### ExecutionBatch

Frozen Pydantic model for a group of Work Units eligible for concurrent execution.

| Field | Type | Required | Validation | Source |
|-------|------|----------|------------|--------|
| `units` | `tuple[WorkUnit, ...]` | Yes | Non-empty | Topological sort batch |
| `parallel_group` | `str \| None` | No | - | Shared group ID, if any |

## State Transitions

Flight Plan and Work Unit models are **immutable** (frozen Pydantic). State changes produce new instances via `model_copy(update={...})`.

```text
FlightPlan lifecycle:
  Created (all criteria unchecked)
    → In Progress (some criteria checked)
      → Complete (all criteria checked)

State is introspected via completion property, not stored as a field.
```

## Validation Rules

| Rule | Entity | Field | Error Type |
|------|--------|-------|------------|
| Required field missing | FlightPlan | name, version, created, tags | `FlightPlanValidationError` |
| Required field missing | WorkUnit | id, flight-plan, sequence | `WorkUnitValidationError` |
| Invalid ID format | WorkUnit | id | `WorkUnitValidationError` |
| Non-positive sequence | WorkUnit | sequence | `WorkUnitValidationError` |
| Invalid frontmatter | Both | - | `FlightPlanParseError` |
| Missing `---` delimiters | Both | - | `FlightPlanParseError` |
| Circular dependency | Resolver | depends_on | `WorkUnitDependencyError` |
| Missing dependency | Resolver | depends_on | `WorkUnitDependencyError` |
| File not found | Loader | path | `FlightPlanNotFoundError` |

# Data Model: Flight Plan CLI Command Group

**Branch**: `040-flight-plan-cli` | **Date**: 2026-02-28

## Entities

### ValidationIssue (new)

A single structural problem found during flight plan file validation.

| Field    | Type | Required | Description                                    |
|----------|------|----------|------------------------------------------------|
| location | str  | Yes      | Where the issue was found (e.g., "frontmatter.name", "section.objective") |
| message  | str  | Yes      | Human-readable description of the problem      |

**Implementation**: `@dataclass(frozen=True, slots=True)` in `maverick.flight.validator`

**Lifecycle**: Created during validation, consumed by CLI for rendering, then discarded. No persistence.

### FlightPlan (existing — no changes)

Master plan model from `maverick.flight.models`. Used by the `validate` subcommand via the existing parser primitives. The `create` subcommand generates content compatible with this model's expected format.

Key fields relevant to validation:
- `name` (str, required, non-empty)
- `version` (str, required, non-empty)
- `created` (date, required)
- `tags` (tuple[str, ...], required, can be empty)
- `objective` (str, required, non-empty)
- `success_criteria` (tuple[SuccessCriterion, ...], required)
- `scope` (Scope, required — has in_scope, out_of_scope, boundaries)

### Flight Plan File Format (existing — no changes)

Markdown+YAML format on disk:

```
---
name: <kebab-case-name>
version: "1"
created: YYYY-MM-DD
tags: []
---

## Objective
<text>

## Success Criteria
- [ ] <criterion 1>
- [ ] <criterion 2>

## Scope

### In
- <item>

### Out
- <item>

### Boundaries
- <item>

## Context
<text>

## Constraints
- <item>

## Notes
<text>
```

## Relationships

```
ValidationIssue  ←──  validate_flight_plan_file()  ←── parse_frontmatter() + parse_flight_plan_sections()
                                                          (existing parser primitives)

FlightPlan model ←──  FlightPlanFile.load()         ←── same parser primitives
                                                          (existing loader — not modified)

Skeleton content ←──  generate_skeleton()            ──→ writes to .maverick/flight-plans/<name>.md
```

## Validation Rules

The validator checks these rules (producing one `ValidationIssue` per failure):

| Rule | Location | Condition |
|------|----------|-----------|
| V1 | frontmatter | Document must start with `---` delimiter |
| V2 | frontmatter | Must have closing `---` delimiter |
| V3 | frontmatter | YAML must be parseable |
| V4 | frontmatter.name | Must be present and non-empty |
| V5 | frontmatter.version | Must be present and non-empty |
| V6 | frontmatter.created | Must be present |
| V7 | section.objective | `## Objective` section must exist and be non-empty |
| V8 | section.success_criteria | `## Success Criteria` section must contain at least one checkbox item |
| V9 | section.scope | `## Scope` section must exist |

Rules V1-V3 are blocking — if frontmatter parsing fails, section checks are skipped (the parser can't extract sections without valid frontmatter separation).

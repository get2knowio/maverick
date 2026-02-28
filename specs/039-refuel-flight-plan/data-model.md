# Data Model: Refuel Flight-Plan Subcommand

**Feature Branch**: `039-refuel-flight-plan`
**Date**: 2026-02-28

## Summary

No new data models are introduced by this feature. The `refuel flight-plan` subcommand reuses all existing models from spec 037 (flight plan/work unit models) and spec 038 (decomposition/workflow models).

## Reused Models

### From `maverick.flight.models` (spec 037)

| Model | Purpose | Used By |
|-------|---------|---------|
| `FlightPlan` | Parsed flight plan with name, objective, success criteria, scope | Workflow step 1 (parse) |
| `WorkUnit` | Discrete work slice with task, acceptance criteria, file scope | Workflow step 5 (write) |
| `SuccessCriterion` | Individual success criterion with checked state | Workflow step 4 (validate coverage) |
| `Scope` | In-scope, out-of-scope, boundaries | Workflow step 2 (gather context) |
| `FileScope` | Create/modify/protect file lists | Agent decomposition output |
| `AcceptanceCriterion` | Criterion text with optional SC-### trace ref | Agent decomposition output |

### From `maverick.workflows.refuel_maverick.models` (spec 038)

| Model | Purpose | Used By |
|-------|---------|---------|
| `DecompositionOutput` | Agent structured output (work units + rationale) | Workflow step 3 (decompose) |
| `WorkUnitSpec` | Lightweight work unit from agent | Workflow step 3 → step 4/5 |
| `RefuelMaverickResult` | Final workflow result (frozen dataclass) | Workflow → CLI |

### From `maverick.cli.workflow_executor`

| Model | Purpose | Used By |
|-------|---------|---------|
| `PythonWorkflowRunConfig` | CLI → workflow configuration | CLI command |

### From `maverick.library.actions.types`

| Model | Purpose | Used By |
|-------|---------|---------|
| `BeadCreationResult` | Epic + task bead creation results | Workflow step 6 |
| `DependencyWiringResult` | Dependency wiring results | Workflow step 7 |

## Entity Relationships

```
PythonWorkflowRunConfig
  ├── workflow_class → RefuelMaverickWorkflow
  ├── inputs.flight_plan_path → FlightPlan (via FlightPlanFile.aload)
  └── inputs.dry_run → bool

RefuelMaverickWorkflow._run()
  ├── FlightPlan
  │     ├── SuccessCriterion[] (coverage validation)
  │     └── Scope (gather context)
  ├── DecompositionOutput
  │     └── WorkUnitSpec[] → WorkUnit[] (conversion)
  ├── BeadCreationResult (step 6, skipped if dry_run)
  ├── DependencyWiringResult (step 7, skipped if dry_run)
  └── RefuelMaverickResult (final output)
```

## New Models

None.

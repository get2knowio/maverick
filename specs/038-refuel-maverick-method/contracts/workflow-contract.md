# Workflow Contract: RefuelMaverickWorkflow

**Branch**: `038-refuel-maverick-method` | **Date**: 2026-02-27

## Input Contract

```python
inputs: dict[str, Any] = {
    "flight_plan_path": str,   # Required. Absolute or relative path to flight-plan.md
    "dry_run": bool,           # Optional, default False. Skip bead creation and commits.
}
```

## Output Contract

```python
RefuelMaverickResult.to_dict() -> {
    "work_units_written": int,              # Count of work unit files written
    "work_units_dir": str,                  # Absolute path to output directory
    "epic": dict | None,                    # Epic bead info (None on dry-run or failure)
    "work_beads": list[dict],               # List of created work bead infos
    "dependencies": list[dict],             # List of wired dependency infos
    "errors": list[str],                    # Collected non-fatal errors
    "coverage_warnings": list[str],         # SC-### coverage warnings
    "dry_run": bool,                        # Whether dry-run mode was active
}
```

## Workflow Steps

| # | Step Name | Type | Description | Skippable |
|---|-----------|------|-------------|-----------|
| 1 | `parse_flight_plan` | PYTHON | Parse flight plan file via FlightPlanFile.aload() | No |
| 2 | `gather_context` | PYTHON | Read in-scope files from codebase | No |
| 3 | `decompose` | AGENT | Agent decomposes flight plan into work units (via StepExecutor) | No |
| 4 | `validate` | PYTHON | Validate dependency graph (acyclic), unique IDs, SC coverage | No |
| 5 | `write_work_units` | PYTHON | Write work unit files to .maverick/work-units/<name>/ | No |
| 6 | `create_beads` | PYTHON | Create epic + task beads via BeadClient | dry_run |
| 7 | `wire_deps` | PYTHON | Wire bead dependencies from depends_on fields | dry_run |

## Step Contracts

### 1. parse_flight_plan

**Input**: `inputs["flight_plan_path"]` (str)
**Output**: `FlightPlan` model instance
**Errors**: `FlightPlanNotFoundError`, `FlightPlanParseError`, `FlightPlanValidationError`

### 2. gather_context

**Input**: `FlightPlan.scope.in_scope` (tuple of file/dir paths)
**Output**: `CodebaseContext` (files read, missing files noted)
**Errors**: None (missing files logged as warnings, not errors)

### 3. decompose

**Input**: Flight plan content (str) + codebase context (formatted str)
**Output**: `DecompositionOutput` (validated via output_schema)
**Retry**: 2 retries with exponential backoff on transient errors
**Errors**: `OutputSchemaValidationError` (immediate failure), API errors (retried)

### 4. validate

**Input**: List of `WorkUnitSpec` from decomposition + `FlightPlan.success_criteria`
**Output**: Validated list + coverage warnings
**Errors**: Circular dependency error (blocking), dangling reference error (blocking)

### 5. write_work_units

**Input**: List of `WorkUnit` models, output directory path
**Output**: Count of files written
**Side effects**: Clears output directory, creates .maverick/work-units/<name>/, writes ###-id.md files

### 6. create_beads (skipped on dry_run)

**Input**: Epic definition dict, work unit definition dicts
**Output**: `BeadCreationResult` (epic, work_beads, created_map, errors)
**Side effects**: Creates beads via `bd` CLI

### 7. wire_deps (skipped on dry_run)

**Input**: Work unit definitions, created_map, dependency relationships
**Output**: `DependencyWiringResult` (dependencies, errors, success)
**Side effects**: Wires dependencies via `bd dep add`

## Agent Step Contract (decompose)

### Prompt Template

```
You are a software decomposition expert. Given a flight plan and codebase context,
produce an ordered set of small, focused work units.

## Flight Plan
{flight_plan_content}

## Codebase Context
{codebase_context}

## Instructions
- Produce 3-15 work units (exceed only with justification)
- Each work unit = one logical change
- File scopes must include ALL protect boundaries from the flight plan
- Every acceptance criterion should trace to a flight plan success criterion (SC-###)
- Verification commands must be concrete and runnable
- Use depends_on to express ordering constraints
- Assign parallel_group labels to work units that can execute concurrently
- IDs must be kebab-case
- Sequence numbers must be sequential starting from 1
```

### Output Schema

```python
class DecompositionOutput(BaseModel):
    work_units: list[WorkUnitSpec]
    rationale: str
```

## Event Emissions

| Step | Events |
|------|--------|
| All steps | `StepStarted(name)`, `StepCompleted(name, output)` or `StepCompleted(name, success=False)` |
| gather_context | `StepOutput(message="Reading N in-scope files...")` |
| decompose | `AgentStreamChunk` (via StepExecutor streaming) |
| validate | `StepOutput(message="Warning: SC-### not covered by any work unit")` |
| write_work_units | `StepOutput(message="Wrote N work unit files to ...")` |
| create_beads | `StepOutput(message="Created epic: ...")`, `StepOutput(message="Created N task beads")` |
| wire_deps | `StepOutput(message="Wired N dependencies")` |

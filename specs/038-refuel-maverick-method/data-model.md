# Data Model: Refuel Maverick Method

**Branch**: `038-refuel-maverick-method` | **Date**: 2026-02-27

## Existing Models (Unchanged)

### FlightPlan (`maverick.flight.models`)

```
FlightPlan (frozen Pydantic)
├── name: str                           # Flight plan identifier
├── version: str                        # Semantic version
├── created: date                       # Creation date
├── tags: tuple[str, ...]              # Categorization tags
├── objective: str                      # High-level goal
├── success_criteria: tuple[SuccessCriterion, ...]
│   ├── text: str                       # Criterion description
│   └── checked: bool                   # Completion status
├── scope: Scope
│   ├── in_scope: tuple[str, ...]      # Files/dirs in scope
│   ├── out_of_scope: tuple[str, ...]  # Excluded items
│   └── boundaries: tuple[str, ...]    # Scope boundaries
├── context: str                        # Additional context
├── constraints: tuple[str, ...]       # Implementation constraints
├── notes: str                          # Free-form notes
└── source_path: Path | None            # Loader-set file path
```

### WorkUnit (`maverick.flight.models`)

```
WorkUnit (frozen Pydantic)
├── id: str                             # Kebab-case identifier
├── flight_plan: str                    # Parent flight plan name
├── sequence: int                       # Execution order (>= 1)
├── parallel_group: str | None          # Concurrent group label
├── depends_on: tuple[str, ...]        # Work unit IDs this depends on
├── task: str                           # Task description
├── acceptance_criteria: tuple[AcceptanceCriterion, ...]
│   ├── text: str                       # Criterion description
│   └── trace_ref: str | None          # SC-### trace reference
├── file_scope: FileScope
│   ├── create: tuple[str, ...]        # Files to create
│   ├── modify: tuple[str, ...]        # Files to modify
│   └── protect: tuple[str, ...]       # Files to protect
├── instructions: str                   # Implementation instructions
├── verification: tuple[str, ...]      # Verification commands
├── provider_hints: str | None          # Optional agent hints
└── source_path: Path | None            # Loader-set file path
```

### BeadDefinition (`maverick.beads.models`)

```
BeadDefinition (frozen Pydantic)
├── title: str                          # Bead title (min 1 char)
├── bead_type: BeadType                 # EPIC | TASK
├── priority: int                       # 0 (highest) to 4
├── category: BeadCategory              # FOUNDATION | USER_STORY | CLEANUP | VALIDATION | REVIEW
├── description: str                    # Optional description
├── phase_names: list[str]             # Phase labels
├── user_story_id: str | None          # Story ID reference
└── task_ids: list[str]                # Task ID references
```

## New Models

### DecompositionOutput (`maverick.workflows.refuel_maverick.models`)

Agent output schema — the structured result from the decomposition agent step. Used as `output_schema` parameter to StepExecutor.

```
DecompositionOutput (frozen Pydantic)
├── work_units: list[WorkUnitSpec]      # Ordered list of work unit specifications
└── rationale: str                      # Agent's reasoning for the decomposition
```

Validation rules:
- `work_units` must be non-empty
- All work unit IDs must be unique
- `depends_on` references must point to IDs within the same list

### WorkUnitSpec (`maverick.workflows.refuel_maverick.models`)

Lightweight work unit specification produced by the agent. Subset of WorkUnit fields — excludes loader-specific fields (`source_path`, `flight_plan`) and `provider_hints` (set by downstream consumers, not the decomposition agent).

```
WorkUnitSpec (frozen Pydantic)
├── id: str                             # Kebab-case, validated regex
├── sequence: int                       # >= 1
├── parallel_group: str | None          # Optional group label
├── depends_on: list[str]              # IDs of dependencies (list for JSON compat)
├── task: str                           # Task description
├── acceptance_criteria: list[AcceptanceCriterionSpec]
│   ├── text: str                       # Criterion text
│   └── trace_ref: str | None          # SC-### reference
├── file_scope: FileScopeSpec
│   ├── create: list[str]              # Files to create
│   ├── modify: list[str]              # Files to modify
│   └── protect: list[str]             # Files to protect
├── instructions: str                   # Implementation guidance
└── verification: list[str]            # Verification commands
```

Validation rules:
- `id` must match `^[a-z0-9]+(-[a-z0-9]+)*$`
- `sequence` must be >= 1
- `verification` must be non-empty (FR-008)

### RefuelMaverickResult (`maverick.workflows.refuel_maverick.models`)

Workflow result — frozen dataclass with `to_dict()` method (Constitution VI.4).

```
RefuelMaverickResult (frozen dataclass, slots=True)
├── work_units_written: int             # Count of files written
├── work_units_dir: str                 # Output directory path
├── epic: dict[str, Any] | None        # Created epic bead info
├── work_beads: tuple[dict[str, Any], ...]  # Created work bead infos
├── dependencies: tuple[dict[str, Any], ...]  # Wired dependencies
├── errors: tuple[str, ...]            # Collected errors
├── coverage_warnings: tuple[str, ...] # Uncovered success criteria
├── dry_run: bool                       # Whether this was a dry run
```

### CodebaseContext (`maverick.library.actions.decompose`)

Context gathered from in-scope files for the decomposition agent.

```
CodebaseContext (frozen dataclass, slots=True)
├── files: tuple[FileContent, ...]     # File contents
├── missing_files: tuple[str, ...]     # Files that couldn't be read
└── total_size: int                     # Total bytes of content
```

### FileContent (`maverick.library.actions.decompose`)

Single file's content for context.

```
FileContent (frozen dataclass, slots=True)
├── path: str                           # Relative file path
└── content: str                        # File text content
```

## Entity Relationships

```
FlightPlan ──1:N──> WorkUnit (via flight_plan name reference)
FlightPlan ──1:1──> Epic Bead (one epic per decomposition)
WorkUnit   ──1:1──> Task Bead (one bead per work unit)
WorkUnit   ──N:M──> WorkUnit (via depends_on references)
WorkUnit   ──N:1──> SuccessCriterion (via acceptance_criteria.trace_ref)
```

## State Transitions

### Workflow Execution Flow

```
INIT → PARSE_FLIGHT_PLAN → GATHER_CONTEXT → DECOMPOSE → VALIDATE
  → WRITE_WORK_UNITS → CREATE_BEADS → WIRE_DEPS → DONE
```

- `DECOMPOSE` may retry up to 2 times on transient failure
- `VALIDATE` checks: acyclic deps, unique IDs, coverage warnings
- `CREATE_BEADS` and `WIRE_DEPS` skipped in dry-run mode
- Failure at any step emits `StepCompleted(success=False)` and raises

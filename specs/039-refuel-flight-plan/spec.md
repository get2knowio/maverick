# Feature Specification: Refuel Flight-Plan Subcommand

**Feature Branch**: `039-refuel-flight-plan`
**Created**: 2026-02-28
**Status**: Draft
**Input**: User description: "Add a maverick refuel flight-plan subcommand to the existing refuel command group. This subcommand takes a required path argument pointing to a Maverick Flight Plan Markdown file. It instantiates and executes the NativeMaverickDecomposer workflow (from the previous spec), which reads the flight plan, produces WorkUnit files in .maverick/work-units/{plan-name}/, and creates beads via BeadClient (one epic for the flight plan, one task bead per work unit with dependencies wired). Follow the exact pattern of the existing refuel speckit subcommand."

## Clarifications

### Session 2026-02-28

- Q: Does `refuel flight-plan` coexist alongside the existing `refuel maverick` command, or replace it? → A: Coexist — both commands remain; `flight-plan` is a distinct new entry point.
- Q: When the AI agent fails to decompose after all retries, should the command fail completely or save partial results? → A: Fail completely — no work units written, no beads created. Partial results would be misleading.
- Q: When re-running against the same flight plan, should stale work unit files from a previous run be removed? → A: Clean slate — remove all prior files in the output directory before writing new ones.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Decompose a Flight Plan into Beads (Priority: P1)

A developer has authored a Maverick Flight Plan Markdown file describing a feature to be built. They want to decompose this plan into individual work beads so that Maverick can execute them sequentially via `maverick fly`. The developer runs `maverick refuel flight-plan <path>` from their project root. The system reads the flight plan, uses an AI agent to decompose it into work units, writes work unit files to disk, and creates beads (one epic bead for the plan, one task bead per work unit with correct dependencies wired).

**Why this priority**: This is the core purpose of the command — converting a flight plan into actionable beads. Without this, the subcommand has no value.

**Independent Test**: Can be fully tested by providing a valid flight plan file and verifying that work unit files appear in `.maverick/work-units/{plan-name}/` and beads are created with correct dependencies. Delivers the ability to go from plan to executable beads in a single command.

**Acceptance Scenarios**:

1. **Given** a valid Maverick Flight Plan Markdown file exists on disk, **When** the user runs `maverick refuel flight-plan ./path/to/plan.md`, **Then** work unit files are written to `.maverick/work-units/{plan-name}/`, one epic bead is created for the flight plan, one task bead is created per work unit, and dependencies between beads match the work unit dependency graph.
2. **Given** a valid flight plan file, **When** the command completes successfully, **Then** the user sees a summary showing how many work units were created and how many beads were wired.
3. **Given** a flight plan with work units that have inter-dependencies specified, **When** the command runs, **Then** each task bead correctly blocks on its prerequisite beads, matching the `depends_on` relationships from the work units.

---

### User Story 2 - Preview Decomposition Without Creating Beads (Priority: P2)

A developer wants to preview what work units and beads would be created from a flight plan without actually creating any beads. They run `maverick refuel flight-plan ./plan.md --dry-run`. The system performs decomposition and writes work unit files to disk but skips bead creation and dependency wiring. This lets the developer review the generated work units before committing to bead creation.

**Why this priority**: Dry-run is essential for safe iteration. Developers need to review AI-generated decompositions before creating beads, which are harder to undo.

**Independent Test**: Can be tested by running with `--dry-run`, verifying work unit files are written but no beads are created. Delivers safe preview capability.

**Acceptance Scenarios**:

1. **Given** a valid flight plan file, **When** the user runs `maverick refuel flight-plan ./plan.md --dry-run`, **Then** work unit files are written to `.maverick/work-units/{plan-name}/` but no beads are created and no dependencies are wired.
2. **Given** dry-run mode, **When** the command completes, **Then** the output clearly indicates that bead creation was skipped due to dry-run mode.

---

### User Story 3 - Diagnose Issues via Session Log (Priority: P3)

A developer encounters unexpected decomposition results and wants to debug what happened. They run the command with `--session-log ./log.jsonl` to capture a detailed journal of the workflow execution for later analysis.

**Why this priority**: Debugging support is important but secondary to core functionality. Most runs will not need a session log.

**Independent Test**: Can be tested by running with `--session-log` and verifying a JSONL file is written with workflow events. Delivers diagnostic capability.

**Acceptance Scenarios**:

1. **Given** a valid flight plan and a `--session-log` path, **When** the command runs, **Then** a JSONL session log file is created at the specified path containing workflow step events.

---

### Edge Cases

- What happens when the flight plan path does not exist? The command reports a clear error indicating the file was not found.
- What happens when the flight plan file is malformed (invalid Markdown/YAML frontmatter)? The command reports a parse error with context about what was invalid.
- What happens when the flight plan file is valid but has validation issues (e.g., missing required fields)? The command reports validation errors with details.
- What happens when the AI decomposition produces work units that fail validation (e.g., missing acceptance criteria)? The command reports validation warnings and proceeds with the valid units.
- What happens when bead creation fails mid-way (e.g., `bd` CLI not available)? The command fails gracefully with an error message indicating what went wrong; work unit files that were already written remain on disk.
- What happens when `.maverick/work-units/{plan-name}/` directory already exists from a previous run? The command removes all existing files in the directory first (clean slate), then writes the new work unit files. This prevents stale files from a previous decomposition that produced more work units.
- What happens when the AI decomposition agent fails after all retries? The command fails completely — no work unit files are written and no beads are created. Partial results are not saved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a `refuel flight-plan` subcommand within the existing `maverick refuel` command group.
- **FR-002**: The subcommand MUST accept a required positional argument specifying the path to a Maverick Flight Plan Markdown file.
- **FR-003**: The subcommand MUST read and parse the flight plan file, producing a structured representation of the plan.
- **FR-004**: The subcommand MUST use an AI agent to decompose the flight plan into individual work units, each with a task description, acceptance criteria, file scope, and verification steps.
- **FR-005**: The subcommand MUST write work unit files to `.maverick/work-units/{plan-name}/` where `{plan-name}` is the name field from the flight plan.
- **FR-006**: The subcommand MUST create one epic bead representing the overall flight plan.
- **FR-007**: The subcommand MUST create one task bead per work unit, with dependencies wired to match the `depends_on` graph from the work units.
- **FR-008**: The subcommand MUST support a `--dry-run` flag that writes work unit files but skips bead creation and dependency wiring.
- **FR-009**: The subcommand MUST support a `--session-log` option that writes a JSONL session journal to the specified file path.
- **FR-010**: The subcommand MUST display real-time progress as each workflow step starts, completes, or fails.
- **FR-011**: The subcommand MUST report a clear error if the flight plan file does not exist, is malformed, or fails validation.
- **FR-012**: The existing `refuel speckit` and `refuel maverick` subcommands MUST remain unchanged and fully functional.
- **FR-013**: The subcommand MUST support a `--list-steps` flag that prints the workflow step names and exits without executing.
- **FR-014**: When the AI decomposition fails after all retries, the subcommand MUST fail completely without writing work unit files or creating beads.
- **FR-015**: Before writing new work unit files, the subcommand MUST remove all existing files in the `.maverick/work-units/{plan-name}/` directory to ensure a clean slate (no stale files from previous runs).

### Key Entities

- **Flight Plan**: A Markdown document with YAML frontmatter describing a feature to be built, including objectives, success criteria, scope, and constraints.
- **Work Unit**: A discrete, implementable slice of work derived from a flight plan, with its own task description, acceptance criteria, file scope, instructions, and verification steps.
- **Bead**: A tracked unit of work managed by the `bd` CLI tool. Beads come in two types relevant here: epic beads (representing the whole plan) and task beads (representing individual work units).
- **Dependency Graph**: The directed acyclic graph of `depends_on` relationships between work units, which determines the order beads can be executed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can convert a flight plan into executable beads in a single command invocation.
- **SC-002**: The generated work units cover all success criteria defined in the input flight plan (validated by the decomposition step).
- **SC-003**: Bead dependencies accurately reflect the work unit dependency graph, enabling correct execution ordering by `maverick fly`.
- **SC-004**: Dry-run mode allows users to review all generated work units before committing to bead creation.
- **SC-005**: The command follows the same interaction patterns (flags, progress display, error reporting) as the existing `refuel speckit` subcommand, ensuring a consistent user experience across the refuel command group.
- **SC-006**: All new functionality is covered by automated tests following the existing test patterns for the refuel command group.

## Assumptions

- The `bd` CLI tool is available on the user's system for bead creation (consistent with the existing `refuel speckit` requirement).
- The NativeMaverickDecomposer workflow from spec 038 (`RefuelMaverickWorkflow`) is complete and available for reuse.
- Flight plan files follow the format defined in spec 037 (Markdown with YAML frontmatter, structured sections).
- The `.maverick/work-units/` directory structure is the established convention for storing decomposed work units.

# Feature Specification: Refuel Maverick Method — Native Flight Plan Decomposition

**Feature Branch**: `038-refuel-maverick-method`
**Created**: 2026-02-27
**Status**: Draft
**Input**: User description: "Implement refuel --method maverick as the native Maverick decomposition strategy. This is an agentic workflow (PythonWorkflow subclass) that reads a Maverick Flight Plan file and produces an ordered set of Maverick Work Unit files."

## Clarifications

### Session 2026-02-27

- Q: What happens to existing beads when re-running for the same flight plan? → A: Clear the work unit directory and create fresh beads without checking for prior existence (stateless, matches existing refuel speckit pattern).
- Q: How should the system handle agent decomposition failures? → A: Retry up to 2 times with exponential backoff for transient errors (API timeouts, rate limits); fail immediately on structured output validation errors.
- Q: Should codebase context include only explicitly scoped files or also discover related files? → A: Read only files explicitly listed in the flight plan's in_scope field (predictable, author-controlled context).
- Q: What severity when success criteria coverage validation fails? → A: Warning — log uncovered criteria but proceed with bead creation. Some criteria may be cross-cutting and implicitly covered.
- Q: Should the agent prompt include work unit count guidance? → A: Soft guideline of 3-15 work units per flight plan; agent may exceed with justification.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Decompose a Flight Plan into Work Units (Priority: P1)

A developer has written a Flight Plan describing a feature they want to build. They run `maverick refuel maverick <flight-plan-path>` to have the system automatically decompose the flight plan into an ordered set of small, focused work units. Each work unit has a clear task description, file scope, acceptance criteria traced back to the flight plan's success criteria, and verification commands. The work unit files are written to disk and beads are created so that `maverick fly` can pick them up.

**Why this priority**: This is the core value proposition — transforming a high-level flight plan into actionable, dependency-ordered work units that Maverick can execute. Without this, the entire feature has no purpose.

**Independent Test**: Can be fully tested by providing a sample flight plan file and verifying that work unit files are produced with correct structure, that beads are created in the bead system, and that dependencies between beads match the work unit ordering.

**Acceptance Scenarios**:

1. **Given** a valid flight plan file at a known path, **When** the user runs `maverick refuel maverick <path>`, **Then** the system parses the flight plan, analyzes the codebase, decomposes it into work units, writes work unit files to `.maverick/work-units/<flight-plan-name>/`, and creates corresponding beads with dependencies wired.
2. **Given** a flight plan with 5 success criteria and a defined scope, **When** decomposition completes, **Then** every work unit has acceptance criteria that trace back to at least one flight plan success criterion, and every success criterion is covered by at least one work unit.
3. **Given** a flight plan with a Protect boundary listing files that must not be modified, **When** decomposition completes, **Then** every work unit's file scope includes those protected files in its protect list.
4. **Given** a flight plan, **When** decomposition completes, **Then** each work unit contains runnable verification commands that can validate the work unit's acceptance criteria.

---

### User Story 2 - Dry Run Preview (Priority: P2)

A developer wants to preview what work units would be generated without actually creating beads or commits. They run `maverick refuel maverick <path> --dry-run` to see the decomposition plan — work unit files are still written for inspection, but the bead system is untouched.

**Why this priority**: Dry run provides confidence before committing to bead creation. It lets developers iterate on their flight plan by seeing what decomposition the system would produce.

**Independent Test**: Can be tested by running with `--dry-run` and verifying that work unit files are still written (for inspection) but no beads are created and no commits are made.

**Acceptance Scenarios**:

1. **Given** a valid flight plan, **When** the user runs with `--dry-run`, **Then** work unit files are written to disk for inspection but no beads are created in the bead system and no commits are made.
2. **Given** a dry run, **When** decomposition completes, **Then** the output clearly indicates it was a dry run and shows what beads would have been created.

---

### User Story 3 - Complex Flight Plan with Parallel Groups (Priority: P2)

A developer has a large flight plan for a complex feature. The decomposition produces work units organized into parallel groups — units within the same group can be worked on concurrently, while groups execute sequentially based on dependencies.

**Why this priority**: Real-world features often have parallelizable work. Supporting parallel groups enables Maverick to execute multiple beads concurrently via `maverick fly`, improving throughput.

**Independent Test**: Can be tested with a flight plan that naturally has independent components, verifying that the decomposition produces work units with `parallel_group` assignments and that dependency wiring allows concurrent execution within groups.

**Acceptance Scenarios**:

1. **Given** a complex flight plan with multiple independent components, **When** decomposition completes, **Then** work units are organized into parallel groups where independent units share a group number and dependent units are in sequential groups.
2. **Given** work units with `depends_on` references, **When** beads are created, **Then** bead dependencies are wired such that a bead cannot start until all beads it depends on are complete.

---

### User Story 4 - Codebase-Aware Decomposition (Priority: P3)

The decomposition agent considers the current state of the codebase when producing work units. It reads the files mentioned in the flight plan's Scope section to understand existing code structure, patterns, and conventions, producing work units that are grounded in the actual codebase rather than being purely theoretical.

**Why this priority**: Codebase awareness produces more accurate and actionable work units. Without it, the agent might suggest work that conflicts with existing code or misses opportunities to reuse existing patterns.

**Independent Test**: Can be tested by providing a flight plan that references existing files and verifying that the decomposition agent receives codebase context and produces work units that reference actual file paths and existing patterns.

**Acceptance Scenarios**:

1. **Given** a flight plan whose Scope section lists files that exist in the repository, **When** decomposition runs, **Then** the agent receives the current content of those files as context for its decomposition decisions.
2. **Given** codebase context, **When** the agent produces work units, **Then** the file scopes reference actual existing file paths (not hypothetical ones) and create/modify lists are consistent with the project's directory structure.

---

### Edge Cases

- What happens when the flight plan file does not exist or is malformed? The system reports a clear parsing error and exits without creating any artifacts.
- What happens when the flight plan references files in its Scope that do not exist in the repository? The system proceeds with available context and notes missing files in the output.
- What happens when the agent produces work units with circular dependencies? The system detects the cycle during dependency validation and reports an error before creating beads.
- What happens when a work unit ID in a `depends_on` reference does not match any other work unit? The system reports the dangling reference as an error.
- What happens when the output directory `.maverick/work-units/<name>/` already contains files from a previous run? The system clears the entire directory first, then writes new work unit files. Fresh beads are created without checking for prior bead existence (stateless re-run).
- What happens when the `bd` bead system is unavailable? The system reports the prerequisite failure clearly and stops before attempting bead creation.
- What happens when the decomposition agent fails (API error, rate limit)? The system retries up to 2 times with exponential backoff for transient failures. Structured output validation errors (malformed WorkUnit output) fail immediately without retry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a flight plan file path as input and parse it using the existing FlightPlanFile parser.
- **FR-002**: System MUST gather codebase context for files explicitly listed in the flight plan's `in_scope` field before running the decomposition agent. The system reads only the specified files — it does not discover related files (imports, tests) beyond what is explicitly scoped.
- **FR-003**: System MUST execute an agent step that receives the flight plan content and codebase context and produces a structured decomposition output. On transient failures (API errors, rate limits), the system retries up to 2 times with exponential backoff. Structured output validation errors fail immediately without retry.
- **FR-004**: System MUST parse the agent's output into validated WorkUnit model instances.
- **FR-005**: System MUST write work unit files to `.maverick/work-units/<flight-plan-name>/` in the standard Maverick work unit Markdown format.
- **FR-006**: System MUST create one epic bead for the flight plan and one task bead per work unit.
- **FR-007**: System MUST wire bead dependencies based on the `depends_on` fields in work units.
- **FR-008**: Each generated work unit MUST contain a task description, file scope (create/modify/protect lists), acceptance criteria with trace references to flight plan success criteria, and verification commands.
- **FR-009**: The decomposition agent MUST produce small, focused work units where each represents one logical change. The agent prompt includes a soft guideline of 3-15 work units per flight plan; the agent may exceed this range with justification when the flight plan scope genuinely requires it.
- **FR-010**: The decomposition agent MUST propagate Protect boundaries from the flight plan's file scope to every work unit.
- **FR-011**: System MUST support `--dry-run` mode that writes work unit files but skips bead creation and commits.
- **FR-012**: System MUST validate that all flight plan success criteria are covered by at least one work unit's acceptance criteria. Uncovered criteria are logged as warnings but do not block bead creation — some criteria may be cross-cutting and implicitly covered without explicit tracing.
- **FR-013**: System MUST validate work unit dependency graph is acyclic before creating beads.
- **FR-014**: System MUST emit progress events for each workflow step (parse flight plan, gather context, decompose, validate, write work units, create beads, wire deps).
- **FR-015**: System MUST support `--list-steps` to display the workflow steps without executing.

### Key Entities

- **Flight Plan**: A high-level feature description with objective, success criteria, scope (in-scope files, out-of-scope boundaries, protect boundaries), and constraints. Parsed from a Markdown file with YAML frontmatter.
- **Work Unit**: An atomic unit of work derived from a flight plan. Contains an ID (kebab-case), sequence number, optional parallel group, dependency references, task description, file scope, acceptance criteria (with success criteria trace references), instructions, and verification commands.
- **Execution Order**: A topologically sorted sequence of execution batches, where each batch contains work units that can run concurrently.
- **Bead**: An external work tracking entity (epic or task) managed by the `bd` CLI tool. One epic per flight plan, one task bead per work unit.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a simple flight plan (single scope area, 3-5 expected work units), the system produces a valid set of work units with correct dependency ordering in a single invocation.
- **SC-002**: Given a complex flight plan (multiple scope areas, 10+ expected work units with parallel groups), the system produces work units with correct parallel group assignments and dependency wiring.
- **SC-003**: 100% of flight plan success criteria are traceable to at least one work unit's acceptance criteria in every decomposition.
- **SC-004**: 100% of generated work units have non-empty verification commands that reference concrete, runnable checks.
- **SC-005**: Protected files from the flight plan appear in every work unit's protect list, ensuring no work unit inadvertently modifies protected files.
- **SC-006**: Dry run mode produces identical work unit files to normal mode but creates zero beads and zero commits.
- **SC-007**: The workflow completes without blocking errors for both simple and complex flight plans when the bead system is available (non-blocking warnings such as SC coverage gaps are acceptable).

## Assumptions

- The `bd` CLI tool is installed and available on the system PATH for bead creation.
- Flight plan files follow the existing Maverick flight plan Markdown format with YAML frontmatter, as defined by the FlightPlanFile parser.
- Work unit files follow the existing Maverick work unit Markdown format, as defined by the WorkUnit model.
- The codebase context gathering reads only files explicitly listed in the flight plan's `in_scope` field. It does not perform import/dependency discovery or recursive directory traversal beyond what is explicitly specified.
- The decomposition agent is invoked via StepExecutor, consistent with how other agentic steps are executed in Maverick workflows.
- The `.maverick/work-units/` directory is created automatically if it does not exist.
- Work unit IDs are generated by the decomposition agent and must be unique within a flight plan's decomposition.

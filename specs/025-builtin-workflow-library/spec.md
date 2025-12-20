# Feature Specification: Built-in Workflow Library

**Feature Branch**: `025-builtin-workflow-library`  
**Created**: 2025-12-14  
**Status**: Draft  
**Input**: User description: "this is spec 25: Create a spec for the built-in workflow library that ships with Maverick."

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Use built-in workflows out of the box (Priority: P1)

As a Maverick user, I can run a set of built-in workflows (fly, refuel, review, validate, quick_fix) with documented inputs so I can accomplish common tasks without writing custom workflows.

**Why this priority**: Built-in workflows provide immediate value and establish canonical examples for the DSL.

**Independent Test**: Can be fully tested by listing available workflows, showing details for one workflow, and validating that each built-in workflow declares the required inputs and step sequence.

**Acceptance Scenarios**:

1. **Given** Maverick is installed, **When** I list workflows, **Then** I can see the built-in workflows `fly`, `refuel`, `review`, `validate`, and `quick_fix`.
2. **Given** a built-in workflow name, **When** I show its details, **Then** I can see its inputs (names, types, defaults) and its ordered steps at a level sufficient to understand what it does.

---

### User Story 2 - Override built-ins with user/project workflows (Priority: P2)

As a Maverick user, I can define a workflow in my user or project workflow locations that overrides a built-in workflow of the same name so I can customize behavior while keeping consistent commands and conventions.

**Why this priority**: Override behavior is key to extensibility and avoids forks/patches for simple customizations.

**Independent Test**: Can be fully tested by defining a workflow with the same name in project scope and confirming it is the one used at runtime.

**Acceptance Scenarios**:

1. **Given** a built-in workflow named `fly` and a project-defined workflow also named `fly`, **When** workflows are discovered, **Then** the project-defined workflow takes precedence over the built-in workflow.
2. **Given** a user-defined workflow and a built-in workflow with the same name, **When** workflows are discovered without a project override, **Then** the user-defined workflow takes precedence.

---

### User Story 3 - Scaffold new workflows from templates (Priority: P3)

As a workflow author, I can scaffold a new workflow using provided templates so I can quickly start from a best-practice structure and customize it for my project.

**Why this priority**: Templates reduce friction and promote consistent, high-quality workflow definitions.

**Independent Test**: Can be fully tested by generating workflows from each template and verifying the output file is created with the expected structure and documentation content.

**Acceptance Scenarios**:

1. **Given** a workflow name and a template choice, **When** I run the workflow new command, **Then** a workflow file is created in the project workflows directory using the chosen template.
2. **Given** a generated workflow, **When** I open it, **Then** it includes documentation sufficient for a user to understand inputs, step intent, and how to customize the workflow.

---

### Edge Cases

- Two discovered workflows share the same name at the same precedence level (e.g., two project workflows named `fly`).
- A workflow file in a discovery directory is unreadable or invalid.
- A built-in workflow references a workflow fragment that is missing or overridden incompatibly.
- Template generation target path already exists.
- A user tries to run `refuel` with `parallel=true` but the environment does not support parallel execution (if parallel is optional/future-facing).

## Requirements *(mandatory)*

### Functional Requirements

#### Built-in workflow library

- **FR-001**: The system MUST ship with a built-in workflow library containing the workflows: `fly`, `refuel`, `review`, `validate`, and `quick_fix`.
- **FR-002**: Built-in workflows MUST be defined using the Maverick workflow DSL and serve as canonical, readable examples for users.
- **FR-003**: Built-in workflows MUST include comprehensive documentation in their source (docstrings and inline documentation) describing purpose, inputs, and customization points.

#### Built-in workflows: definitions and required shape

- **FR-004**: The `fly` workflow MUST support inputs: `branch_name` (string), `task_file` (optional path), `skip_review` (boolean) and MUST implement the step sequence: init → implement → validate/fix loop → commit → review → create_pr, with review being skippable when configured.
- **FR-005**: The `refuel` workflow MUST support inputs: `label` (string), `limit` (integer), `parallel` (boolean) and MUST implement the step sequence: fetch_issues → for each issue: branch → fix → validate → commit → pr.
- **FR-006**: The `review` workflow MUST support inputs: `pr_number` (optional integer), `base_branch` (string) and MUST implement the step sequence: gather_context → run_coderabbit → agent_review → combine_results.
- **FR-007**: The `validate` workflow MUST support inputs: `fix` (boolean), `max_attempts` (integer) and MUST implement the step sequence: run_validation → fix loop (when enabled) → report.
- **FR-008**: The `quick_fix` workflow MUST support inputs: `issue_number` (integer) and MUST implement the step sequence: fetch_issue → branch → fix → validate → commit → pr.

#### Workflow fragments (reusable sub-workflows)

- **FR-009**: The system MUST provide reusable workflow fragments that can be invoked by workflows as sub-workflows.
- **FR-010**: The `validate_and_fix` fragment MUST support inputs: `stages`, `max_attempts`, `fixer_agent` and MUST implement a validation-with-retry loop; it MUST be used by `fly`, `refuel`, and `validate`.
- **FR-011**: The `commit_and_push` fragment MUST generate a commit message, commit changes, and push; it MUST be used by `fly`, `refuel`, and `quick_fix`.
- **FR-012**: The `create_pr_with_summary` fragment MUST generate a PR body and create a PR; it MUST support inputs: `base_branch`, `draft` and MUST be used by `fly`, `refuel`, and `quick_fix`.
- **FR-012a**: Workflow fragments MUST follow the same override precedence as workflows (project > user > built-in), allowing users to customize common patterns.

#### Workflow locations and discovery

- **FR-013**: The system MUST support workflow discovery from three locations: built-in library (packaged with Maverick), user-defined workflows (`~/.config/maverick/workflows/`), and project-specific workflows (`.maverick/workflows/` in project root).
- **FR-014**: The system MUST scan all workflow locations on startup and register discovered workflows in the workflow registry.
- **FR-015**: When workflows share the same name, later definitions MUST override earlier by precedence order: project > user > built-in.
- **FR-016**: If two workflows of the same name exist at the same precedence level, the system MUST fail discovery with a clear error listing both conflicting file paths.
- **FR-016a**: If a workflow file is unreadable or invalid during discovery, the system MUST log a warning with the file path and error details, skip the file, and continue discovering remaining workflows.

#### Workflow templates (scaffolding)

- **FR-017**: The CLI MUST support scaffolding a new workflow definition via `maverick workflow new <name>`.
- **FR-018**: The workflow new command MUST support selecting a template: `basic`, `full`, or `parallel`.
- **FR-019**: The `basic` template MUST generate a single linear workflow with a small number of Python/agent steps and explanatory documentation.
- **FR-020**: The `full` template MUST generate a complete workflow that includes validation, review, and PR creation patterns and explanatory documentation.
- **FR-021**: The `parallel` template MUST generate a workflow that demonstrates the parallel step interface and explanatory documentation.
- **FR-022**: Workflow scaffolding MUST support generating either a Python workflow file or a YAML workflow file based on a user-provided option; YAML MUST be the default format when unspecified.
- **FR-023**: Generated workflows MUST be placed in the project workflow directory by default.

### Assumptions

- This spec defines the product-facing library and discovery behavior; the specific internal code organization is secondary to the user-visible locations and override semantics.
- “Parallel” behavior in `refuel` is treated as an author-facing toggle; if full parallel execution is not available, the workflow may operate in a compatible sequential mode while preserving the interface.

### Key Entities *(include if feature involves data)*

- **Built-in Workflow**: A workflow shipped with Maverick for common tasks and maintained as part of the product.
- **Workflow Fragment**: A reusable sub-workflow invoked by other workflows to share common patterns (validation/fix loop, commit/push, PR creation).
- **Workflow Location**: A discovery source for workflows (built-in, user, or project).
- **Workflow Discovery Result**: The registered set of workflows available to run, including which source each workflow came from and which overrides applied.
- **Workflow Template**: A scaffold blueprint for generating a new workflow file with documentation and an initial step structure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can list and run each built-in workflow using documented inputs without creating custom workflows.
- **SC-002**: Workflow discovery deterministically applies override precedence (project > user > built-in) and surfaces which workflow definition is active for a given name.
- **SC-003**: Users can scaffold a new workflow from each template (`basic`, `full`, `parallel`) in under 1 minute and immediately validate or run the generated workflow after filling required inputs.
- **SC-004**: Built-in workflow sources serve as effective examples: a user can create a custom workflow by modifying a generated template and successfully run it with minimal trial-and-error (measured by completion in ≤2 edit-run iterations for a basic workflow).

## Clarifications

### Session 2025-12-20

- Q: When two workflows share the same name at the same precedence level, should discovery fail with an error or apply a deterministic tie-breaker? → A: Fail discovery with clear error listing conflicting files.
- Q: What should be the default format for workflow scaffolding when the user doesn't specify Python or YAML? → A: YAML as default.
- Q: Can users override built-in workflow fragments with their own versions? → A: Yes, fragments use same override precedence (project > user > built-in).
- Q: Where should user-defined workflows be stored? → A: `~/.config/maverick/workflows/` (XDG-consistent).
- Q: What should happen when discovery encounters an invalid or unreadable workflow file? → A: Log warning with file path and error, skip file, continue discovery.

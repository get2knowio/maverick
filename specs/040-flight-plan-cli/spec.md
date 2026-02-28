# Feature Specification: Flight Plan CLI Command Group

**Feature Branch**: `040-flight-plan-cli`
**Created**: 2026-02-28
**Status**: Draft
**Input**: User description: "Add a maverick flight-plan command group to the CLI with two subcommands: create and validate."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create a New Flight Plan (Priority: P1)

A developer starting a new feature wants to quickly scaffold a flight plan file with all the required sections pre-populated as stubs, so they can focus on filling in the content rather than remembering the file format.

**Why this priority**: This is the primary authoring workflow. Without a way to create flight plans from the CLI, users must manually construct the Markdown+YAML format, which is error-prone and slow.

**Independent Test**: Can be fully tested by running `maverick flight-plan create my-plan` and verifying a well-formed skeleton file is written to disk with all required sections.

**Acceptance Scenarios**:

1. **Given** a developer in a project directory, **When** they run `maverick flight-plan create my-feature`, **Then** a file `my-feature.md` is created at `.maverick/flight-plans/my-feature.md` containing valid YAML frontmatter (name, version, created, tags) and all required Markdown sections (Objective, Success Criteria, Scope with In/Out/Boundaries, Context, Constraints, Notes) stubbed out for editing.
2. **Given** the output directory does not exist, **When** the user runs `maverick flight-plan create my-plan`, **Then** the directory is created automatically and the file is written successfully.
3. **Given** a user wants to store flight plans in a custom location, **When** they run `maverick flight-plan create my-plan --output-dir ./plans`, **Then** the file is created at `./plans/my-plan.md`.
4. **Given** a flight plan file already exists at the target path, **When** the user runs `maverick flight-plan create my-plan`, **Then** the command refuses to overwrite and displays an error message indicating the file already exists.

---

### User Story 2 - Validate a Flight Plan (Priority: P1)

A developer who has filled in a flight plan wants to check that the file is structurally correct before using it with other Maverick commands (e.g., `maverick refuel flight-plan`), so they can catch formatting issues early.

**Why this priority**: Validation prevents silent failures downstream. A malformed flight plan that is only caught during `refuel` wastes time and creates confusion.

**Independent Test**: Can be fully tested by running `maverick flight-plan validate path/to/plan.md` against both valid and invalid flight plan files and verifying the output reports pass/fail with specific issue descriptions.

**Acceptance Scenarios**:

1. **Given** a valid, fully filled-in flight plan file, **When** the user runs `maverick flight-plan validate plan.md`, **Then** the command reports success with a confirmation message.
2. **Given** a flight plan file with missing required sections (e.g., no Objective), **When** the user runs `maverick flight-plan validate plan.md`, **Then** the command reports each missing section as a distinct issue.
3. **Given** a flight plan file with malformed YAML frontmatter (e.g., missing `name` field, invalid `created` date format), **When** the user runs `maverick flight-plan validate plan.md`, **Then** the command reports the specific frontmatter errors.
4. **Given** a flight plan file with empty success criteria (no checkbox items), **When** the user runs `maverick flight-plan validate plan.md`, **Then** the command reports that success criteria must contain at least one item.
5. **Given** a file path that does not exist, **When** the user runs `maverick flight-plan validate missing.md`, **Then** the command exits with a non-zero exit code and displays an error that the file was not found.

---

### User Story 3 - Discover Flight Plan Commands (Priority: P2)

A developer unfamiliar with flight plan authoring wants to discover available subcommands and their usage, so they can learn the workflow without consulting external documentation.

**Why this priority**: Discoverability supports self-service adoption, but is secondary to the core create/validate functionality.

**Independent Test**: Can be tested by running `maverick flight-plan --help` and verifying both subcommands are listed with descriptions.

**Acceptance Scenarios**:

1. **Given** a developer, **When** they run `maverick flight-plan --help`, **Then** both `create` and `validate` subcommands are listed with brief descriptions.
2. **Given** a developer, **When** they run `maverick flight-plan create --help`, **Then** the help text shows the plan name argument, the `--output-dir` option with its default, and usage examples.
3. **Given** a developer, **When** they run `maverick flight-plan` with no subcommand, **Then** the help text is displayed (same as `--help`).

---

### Edge Cases

- What happens when the plan name is not valid kebab-case (e.g., contains spaces, uppercase, slashes, unicode)? The command MUST reject it with a descriptive error explaining the required format (lowercase alphanumeric + hyphens, starting with a letter).
- What happens when the user lacks write permissions to the output directory? The command should report a clear permission error.
- What happens when the flight plan file contains valid YAML frontmatter but uses unexpected section heading levels (e.g., `###` instead of `##`)? The validator should detect missing top-level sections.
- What happens when the flight plan file is empty (0 bytes)? The validator should report both missing frontmatter and missing sections.
- What happens when the `--output-dir` path is an existing file (not a directory)? The command should report that the path is not a directory.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CLI MUST expose a `flight-plan` command group under the top-level `maverick` command with `create` and `validate` subcommands.
- **FR-002**: The `create` subcommand MUST accept a required positional argument for the plan name (used as the filename stem and the `name` field in frontmatter).
- **FR-003**: The `create` subcommand MUST accept an optional `--output-dir` flag that defaults to `.maverick/flight-plans/`.
- **FR-004**: The `create` subcommand MUST create the output directory (including parents) if it does not exist.
- **FR-005**: The `create` subcommand MUST write a Markdown file with YAML frontmatter containing: `name` (from argument), `version` (set to `1`), `created` (current date in ISO format), and `tags` (empty list).
- **FR-006**: The `create` subcommand MUST include all required flight plan sections as stubs: Objective, Success Criteria (with placeholder checkboxes), Scope (with `### In`, `### Out`, and `### Boundaries` subsections matching the parser's expected heading text), Context, Constraints, and Notes. Each stub section MUST contain an HTML comment with a brief editing instruction describing what the user should fill in (consistent with the existing spec template pattern).
- **FR-007**: The `create` subcommand MUST refuse to overwrite an existing file and display an error message.
- **FR-008**: The `validate` subcommand MUST accept a required positional argument for the file path to validate.
- **FR-009**: The `validate` subcommand MUST parse the file using the existing parser primitives (`parse_frontmatter`, `parse_flight_plan_sections`) and report any structural issues found. It MUST collect all issues in a single pass rather than failing on the first error.
- **FR-010**: The `validate` subcommand MUST detect and report: missing required sections, empty success criteria (no items), and malformed YAML frontmatter (missing required fields, invalid types).
- **FR-011**: The `validate` subcommand MUST exit with code 0 on success and non-zero on validation failure or file-not-found errors.
- **FR-012**: Both subcommands MUST use Rich for console output formatting (success messages, error messages, validation reports).
- **FR-013**: The `create` subcommand MUST enforce kebab-case plan names (lowercase alphanumeric characters and hyphens only, must start with a letter, e.g., `my-feature-plan`). Names violating this format MUST be rejected with a descriptive error explaining the required format.
- **FR-014**: Running `maverick flight-plan` with no subcommand MUST display the group help text.

### Key Entities

- **Flight Plan File**: A Markdown document with YAML frontmatter containing metadata (name, version, created date, tags) and structured sections (Objective, Success Criteria, Scope, Context, Constraints, Notes). Parsed by the existing `FlightPlanFile` model.
- **Validation Issue**: A discrete structural problem found during validation, characterized by a location (frontmatter or section name) and a description of the issue. All issues are treated as errors (single severity level, pass/fail model). No warning/info distinction in v1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can scaffold a new flight plan file with a single command in under 5 seconds, without needing to know the file format.
- **SC-002**: Users can validate a flight plan file and receive actionable feedback on all structural issues in a single invocation.
- **SC-003**: 100% of validation issues identified by `validate` include the specific section or field where the problem was found, enabling users to fix issues without guessing.
- **SC-004**: The generated skeleton file is immediately parseable by the existing `FlightPlanFile` model (zero validation errors on a freshly created file once stub content is replaced with valid content).
- **SC-005**: Both subcommands complete within 1 second for typical flight plan files (no network calls, no agent invocations).

## Clarifications

### Session 2026-02-28

- Q: What format should the skeleton stub content use? → A: HTML comments with brief editing instructions (matches existing spec template pattern in the codebase).
- Q: How strictly should plan names be validated? → A: Enforce kebab-case (lowercase alphanumeric + hyphens, must start with a letter). Matches codebase naming conventions.
- Q: Should validation distinguish between warnings and errors? → A: Single severity (errors only, pass/fail). Keeps v1 simple; warnings can be added later if needed.

## Assumptions

- The flight plan Markdown format and YAML frontmatter schema are defined by the existing `FlightPlan` Pydantic model in `src/maverick/flight/models.py` and the `FlightPlanFile` loader in `src/maverick/flight/loader.py`. This feature does not introduce a new format.
- The `create` subcommand produces a skeleton that matches the format expected by `FlightPlanFile.load()`, so users can validate their filled-in plans after editing.
- Plan names are used directly as filename stems (with `.md` extension appended). Names are expected to be kebab-case identifiers (e.g., `my-feature-plan`).
- This is a synchronous, local-only command. No agent calls, no network requests, no workspace creation.
- The `validate` subcommand reuses the existing `FlightPlanFile` parsing logic rather than reimplementing validation from scratch.

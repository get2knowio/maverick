# Feature Specification: Flight Plan and Work Unit Data Models

**Feature Branch**: `037-flight-plan-models`
**Created**: 2026-02-27
**Status**: Draft
**Input**: User description: "Implement the Maverick Flight Plan and Work Unit data models with Pydantic schemas, Markdown+YAML parsers/serializers, and file classes for loading, introspection, and dependency resolution."

## Clarifications

### Session 2026-02-27

- Q: What format should Work Unit IDs follow? → A: Kebab-case slugs (e.g., `setup-database`, `add-auth-middleware`). Must match regex `^[a-z0-9]+(-[a-z0-9]+)*$`.
- Q: What file naming convention should Flight Plans and Work Units follow on disk? → A: `flight-plan.md` for the Flight Plan; `###-slug.md` for Work Units (e.g., `001-setup-database.md`) where `###` is the zero-padded sequence number.
- Q: Should the Pydantic models be frozen (immutable) or mutable? → A: Frozen (immutable) with `model_copy(update={...})` for programmatic modifications.
- Q: Where should these models be placed in the codebase? → A: `src/maverick/flight/` as a dedicated top-level package (analogous to `jj/`, `vcs/`, `workspace/`).
- Q: What YAML frontmatter parsing approach should be used? → A: Manual split on `---` delimiters with PyYAML (no new dependency).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Author a Flight Plan (Priority: P1)

A workflow author creates a Flight Plan document describing a development objective. The system reads this document, validates its structure, and makes it available as structured data for downstream workflow steps. The author can query the plan's completion status (how many success criteria are checked off) without manually counting checkboxes.

**Why this priority**: Flight Plans are the foundational planning artifact. Without the ability to read and validate them, no downstream work unit processing can occur.

**Independent Test**: Can be fully tested by creating a sample Flight Plan Markdown file, loading it into the system, and verifying all fields and sections are accessible as structured data.

**Acceptance Scenarios**:

1. **Given** a valid Flight Plan Markdown file with YAML frontmatter and all required sections, **When** the system loads the file, **Then** all frontmatter fields (plan name, version, created date, tags) and section contents (Objective, Success Criteria, Scope, Context, Constraints, Notes) are accessible as structured data.
2. **Given** a Flight Plan with some Success Criteria checkboxes checked and others unchecked, **When** the system inspects the plan's status, **Then** it reports the number of completed criteria, total criteria, and an overall completion percentage.
3. **Given** a Flight Plan Markdown file missing a required frontmatter field, **When** the system attempts to load it, **Then** a clear validation error is raised identifying the missing field.
4. **Given** a structured Flight Plan data object, **When** the system serializes it back to Markdown+YAML, **Then** the resulting file is a valid Flight Plan that can be re-loaded without data loss. *(Cross-ref: Tested as part of User Story 4 — Round-Trip Serialization. US1 is independently testable without this scenario.)*

---

### User Story 2 - Define and Load Work Units (Priority: P1)

A workflow author breaks a Flight Plan into individual Work Units, each describing a discrete task with acceptance criteria, file scope, instructions, and verification steps. The system reads these documents, validates their structure, and links them back to their parent Flight Plan.

**Why this priority**: Work Units are the actionable counterpart to Flight Plans. Both models are needed together to form a complete planning-to-execution pipeline.

**Independent Test**: Can be fully tested by creating sample Work Unit Markdown files, loading them, and verifying all fields are accessible and linked to a Flight Plan reference.

**Acceptance Scenarios**:

1. **Given** a valid Work Unit Markdown file with YAML frontmatter (work-unit ID, flight-plan reference, sequence number, parallel-group, depends-on list) and all sections, **When** the system loads the file, **Then** all frontmatter fields and section contents (Task, Acceptance Criteria, File Scope, Instructions, Verification, Provider Hints) are accessible as structured data.
2. **Given** a Work Unit with Acceptance Criteria referencing specific Flight Plan Success Criteria, **When** the system loads the Work Unit, **Then** the traceability links between Work Unit acceptance criteria and Flight Plan success criteria are preserved and queryable.
3. **Given** a Work Unit with File Scope lists (Create, Modify, Protect), **When** the system loads the Work Unit, **Then** each list is separately accessible and files are categorized correctly.
4. **Given** a Work Unit with Verification commands, **When** the system loads the Work Unit, **Then** the verification commands are available as an ordered list of executable command strings.

---

### User Story 3 - Resolve Work Unit Dependencies and Ordering (Priority: P2)

A workflow system needs to determine the correct execution order for a set of Work Units. The system loads all Work Units from a directory, resolves their dependency relationships (using depends-on lists and sequence numbers), and provides a topologically sorted execution order that respects parallel groups.

**Why this priority**: Correct execution ordering is essential for automated workflow execution but builds on the foundational loading capability from User Stories 1 and 2.

**Independent Test**: Can be fully tested by creating a directory of Work Unit files with various dependency relationships and verifying the resolved order respects all constraints.

**Acceptance Scenarios**:

1. **Given** a directory containing multiple Work Unit files with declared dependencies, **When** the system loads and resolves them, **Then** it returns an execution order where every Work Unit appears after all its dependencies.
2. **Given** Work Units that share the same parallel-group identifier, **When** the system resolves execution order, **Then** those Work Units are grouped together as eligible for concurrent execution.
3. **Given** Work Units with circular dependencies, **When** the system attempts to resolve order, **Then** a clear error is raised identifying the cycle.
4. **Given** a Work Unit that depends on a non-existent Work Unit ID, **When** the system attempts to resolve order, **Then** a clear error is raised identifying the missing dependency.

---

### User Story 4 - Round-Trip Serialization (Priority: P2)

A workflow system modifies Flight Plans or Work Units programmatically (e.g., checking off success criteria, updating status) and writes them back to disk. The system serializes the structured data back to Markdown+YAML format, preserving the document structure and human readability.

**Why this priority**: Enables programmatic updates to planning documents while keeping them human-editable, which is required for the iterative planning-execution cycle.

**Independent Test**: Can be fully tested by loading a document, modifying it, serializing it, and verifying the output is valid and preserves all data.

**Acceptance Scenarios**:

1. **Given** a Flight Plan data object, **When** the system serializes it to Markdown+YAML, **Then** the output contains valid YAML frontmatter and properly structured Markdown sections with correct headings.
2. **Given** a Work Unit data object, **When** the system serializes it to Markdown+YAML, **Then** the output contains valid YAML frontmatter and properly structured Markdown sections.
3. **Given** any valid Flight Plan or Work Unit file, **When** the system loads and then re-serializes it, **Then** the re-serialized output can be loaded again with identical structured data (round-trip fidelity).

---

### Edge Cases

- What happens when a Flight Plan file has no Success Criteria section? The system treats completion as 0/0 (undefined) and reports it accordingly.
- What happens when a Work Unit has an empty depends-on list? It is treated as having no dependencies and is eligible for immediate execution.
- What happens when the YAML frontmatter contains unexpected extra fields? The system ignores unrecognized fields without error, preserving forward compatibility.
- What happens when a Work Unit directory is empty? The system returns an empty ordered list with no error.
- What happens when Markdown section content contains YAML-like syntax? The parser correctly distinguishes frontmatter boundaries (delimited by `---`) from section content.
- What happens when a Flight Plan file does not exist at the specified path? The system raises a clear file-not-found error.
- What happens when parallel-group is not specified on a Work Unit? The system treats it as a standalone unit not part of any parallel group.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST parse Flight Plan documents consisting of YAML frontmatter and structured Markdown sections into validated, structured data.
- **FR-002**: System MUST validate that Flight Plan frontmatter contains all required fields: plan name, version, created date, and tags list.
- **FR-003**: System MUST extract and structure Flight Plan sections: Objective (free text), Success Criteria (checkbox list), Scope (with In/Out/Boundaries subsections), Context (free text), Constraints (list), and Notes (free text).
- **FR-004**: System MUST parse Success Criteria as individual items with checked/unchecked state for status introspection.
- **FR-005**: System MUST provide completion status for a Flight Plan as: count of checked criteria, total criteria count, and completion percentage.
- **FR-006**: System MUST parse Work Unit documents consisting of YAML frontmatter and structured Markdown sections into validated, structured data.
- **FR-007**: System MUST validate that Work Unit frontmatter contains all required fields: work-unit ID (kebab-case slug matching `^[a-z0-9]+(-[a-z0-9]+)*$`), flight-plan reference, and sequence number (positive integer). Optional fields: parallel-group and depends-on list.
- **FR-008**: System MUST extract and structure Work Unit sections: Task (free text), Acceptance Criteria (list with flight plan trace references), File Scope (with Create/Modify/Protect sublists), Instructions (free text), Verification (list of executable commands), and Provider Hints (free text).
- **FR-009**: System MUST serialize Flight Plan data back to valid Markdown+YAML format that preserves document structure.
- **FR-010**: System MUST serialize Work Unit data back to valid Markdown+YAML format that preserves document structure.
- **FR-011**: System MUST support round-trip fidelity: loading a document and re-serializing it produces output that, when loaded again, yields identical structured data.
- **FR-012**: System MUST load all Work Unit files from a specified directory, discovering files matching the `###-slug.md` naming pattern (e.g., `001-setup-database.md`).
- **FR-013**: System MUST resolve Work Unit execution order using topological sorting based on depends-on declarations.
- **FR-014**: System MUST detect and report circular dependencies among Work Units.
- **FR-015**: System MUST detect and report references to non-existent Work Unit IDs in depends-on lists.
- **FR-016**: System MUST identify Work Units that share a parallel-group as eligible for concurrent execution.
- **FR-017**: System MUST raise clear, descriptive validation errors when documents are malformed, missing required fields, or contain invalid data.
- **FR-018**: System MUST ignore unrecognized fields in YAML frontmatter without raising errors (forward compatibility).
- **FR-019**: System MUST support both synchronous and asynchronous file loading operations.

### Key Entities

- **Flight Plan**: A planning document that defines a development objective, success criteria (with completion tracking), scope boundaries, context, and constraints. Identified by a plan name and version. Contains a tags list for categorization. Stored as `flight-plan.md` in the feature directory.
- **Success Criterion**: An individual success criterion within a Flight Plan. Has a text description and a checked/unchecked state for completion tracking.
- **Scope**: A structured section within a Flight Plan containing three subsections: In (what is included), Out (what is excluded), and Boundaries (limits and constraints on scope).
- **Work Unit**: An actionable task document linked to a Flight Plan. Identified by a unique work-unit ID (kebab-case slug, e.g., `setup-database`). Stored as `###-slug.md` (e.g., `001-setup-database.md`). Has a sequence number for ordering, an optional parallel-group for concurrency, and a depends-on list for dependency management.
- **Acceptance Criterion**: An individual acceptance criterion within a Work Unit. Contains a text description and a trace reference linking it to a specific Flight Plan Success Criterion.
- **File Scope**: A structured section within a Work Unit containing three file lists: Create (new files), Modify (existing files to change), and Protect (files that must not be altered).
- **Verification Step**: An executable command string within a Work Unit used to verify that the task was completed correctly. Stored as plain strings in a tuple (not a separate model class), interpreted by the executing system.

## Assumptions

- Flight Plan and Work Unit documents follow a Markdown format with YAML frontmatter delimited by `---` markers, consistent with common Markdown+YAML conventions (e.g., Jekyll, Hugo, Obsidian).
- Work Unit IDs are kebab-case slugs (matching `^[a-z0-9]+(-[a-z0-9]+)*$`), unique within a directory of Work Units belonging to the same Flight Plan.
- The depends-on field in Work Units references Work Unit IDs within the same directory/flight plan scope, not across different Flight Plans.
- Sequence numbers are positive integers used for default ordering when no explicit dependencies are declared.
- Tags in Flight Plan frontmatter are a flat list of strings.
- The version field in Flight Plan frontmatter is a string (e.g., "1.0", "2.1") rather than a structured semantic version.
- Provider Hints is an optional free-text section that may or may not be present in every Work Unit.
- Verification commands are plain strings (not structured objects), to be interpreted by the executing system.
- All Pydantic models are frozen (immutable). Programmatic updates use `model_copy(update={...})`.
- Flight Plan file is named `flight-plan.md`. Work Unit files follow `###-slug.md` naming (e.g., `001-setup-database.md`).
- YAML frontmatter is parsed by manually splitting on `---` delimiters and passing to PyYAML (no `python-frontmatter` dependency).
- Models are located in `src/maverick/flight/` package, following the same top-level package pattern as `jj/`, `vcs/`, and `workspace/`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid Flight Plan documents (conforming to the defined structure) are loaded without errors and all fields are accessible.
- **SC-002**: 100% of valid Work Unit documents are loaded without errors and all fields are accessible, including traceability links to Flight Plan criteria.
- **SC-003**: Round-trip serialization (load then save then reload) produces identical structured data for all valid documents.
- **SC-004**: Dependency resolution correctly orders 100% of acyclic Work Unit sets, verified by checking that every Work Unit appears after all its declared dependencies.
- **SC-005**: Circular dependency detection catches 100% of cycles and produces error messages that identify the involved Work Unit IDs.
- **SC-006**: All validation errors include the specific field or section that failed and a human-readable description of the issue.
- **SC-007**: Comprehensive automated test coverage for all functional requirements, including positive paths, validation failures, edge cases, and round-trip fidelity.

# Feature Specification: Remove Dead YAML DSL Infrastructure

**Feature Branch**: `041-remove-yaml-dsl`
**Created**: 2026-03-03
**Status**: Draft
**Input**: User description: "Remove the dead YAML DSL infrastructure from Maverick. All active CLI commands use execute_python_workflow exclusively. Extract still-needed modules from maverick.dsl to proper top-level locations and delete everything else."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extract Live Modules to Proper Locations (Priority: P1)

As a Maverick developer, I need the actively-used modules currently buried under `maverick.dsl` to live at proper top-level package locations so that import paths reflect their actual role (events, executor, results, registry, checkpoint) rather than implying they belong to a defunct YAML DSL system.

**Why this priority**: Every active CLI command (`fly`, `refuel`, `land`, `flight-plan`) depends on these modules. They must be safely relocated before any dead code can be deleted. This is the foundation that all subsequent work depends on.

**Independent Test**: Can be verified by running the full test suite after the move. All existing Python workflow tests pass with the new import paths, and no `maverick.dsl` imports remain in active source code.

**Acceptance Scenarios**:

1. **Given** the modules `events.py`, `executor/`, `results.py`, `types.py`, `checkpoint/`, and `registry/` currently live under `maverick.dsl`, **When** they are extracted to `maverick.events`, `maverick.executor`, `maverick.results`, `maverick.types`, `maverick.checkpoint`, and `maverick.registry` respectively, **Then** all existing tests that exercise the Python workflow path continue to pass with zero behavior changes.
2. **Given** active error classes (`ReferenceResolutionError`, `DuplicateComponentError`, `DSLWorkflowError`, `CheckpointNotFoundError`, `InputMismatchError`) exist in `dsl/errors.py`, **When** they are merged into the project's exception hierarchy, **Then** all code that catches or raises these errors continues to function identically. `DSLWorkflowError` is renamed to `WorkflowStepError` to reflect its actual purpose.
3. **Given** active configuration constants (`CHECKPOINT_DIR`, `COMMAND_TIMEOUT`, `DEFAULT_RETRY_ATTEMPTS`, `DEFAULT_RETRY_DELAY`, etc.) exist in `dsl/config.py` as a dataclass, **When** they are moved to a proper constants module as module-level constants, **Then** all code referencing these values works identically with the new import paths.
4. **Given** the registry contains `WorkflowRegistry` and `ContextBuilderRegistry` that are only used by dead YAML code, **When** the registry is extracted to its new location, **Then** those dead registries and their type aliases are removed, and `ComponentRegistry` only manages agents, actions, and generators.

---

### User Story 2 - Delete Dead YAML DSL Code (Priority: P2)

As a Maverick maintainer, I need all dead YAML DSL infrastructure removed from the codebase so that contributors are not confused by ~16,300 lines of unused source code, CI runs faster without linting dead modules, and the dependency footprint is smaller.

**Why this priority**: Once the live modules are safely extracted (P1), the dead code can be deleted in bulk. This delivers the primary value of the feature: a dramatically smaller, more focused codebase.

**Independent Test**: Can be verified by confirming: (a) no `maverick.dsl` package exists after deletion, (b) all active tests still pass, (c) static analysis reports no broken imports, (d) the `lark` dependency is no longer installed.

**Acceptance Scenarios**:

1. **Given** the YAML parser, schema models, writer, editor, validation, expression language, visualization, discovery, step definitions, context builders, streaming, and protocols are all unused, **When** the entire `maverick.dsl` package is deleted after extraction, **Then** no remaining source code imports from `maverick.dsl` and all CLI commands function normally.
2. **Given** YAML workflow files (`fly-beads.yaml`, `refuel-speckit.yaml`), fragment files (`validate_and_fix.yaml`, `commit_and_push.yaml`, `create_pr_with_summary.yaml`, `review_and_fix.yaml`), and the builtin workflow library loader are unused by any active code path, **When** these files are deleted, **Then** no functionality is lost.
3. **Given** the `lark` parser library is only imported by the dead expression parser, **When** it is removed from project dependencies, **Then** the project installs and runs correctly without it.

---

### User Story 3 - Clean Up CLI Entry Points (Priority: P2)

As a Maverick developer, I need the CLI modules cleaned of dead YAML references so that the code I read and maintain accurately reflects what the system actually does.

**Why this priority**: Same priority as deletion since it's part of the same cleanup sweep, but separated because it involves surgical edits to active files rather than bulk deletion.

**Independent Test**: Can be verified by confirming: (a) dead functions no longer exist in CLI modules, (b) dead imports are removed, (c) all CLI commands still work normally.

**Acceptance Scenarios**:

1. **Given** `execute_workflow_run()` in the CLI workflow executor is defined but never called by any CLI command, **When** it and its dead imports are removed, **Then** the active `execute_python_workflow()` function continues to work identically.
2. **Given** `execute_dsl_workflow()` in CLI helpers is exported but never imported elsewhere, **When** it and its associated imports are removed, **Then** no other module is affected.
3. **Given** CLI common setup calls functions that populate dead registry sections (context builders, workflow discovery), **When** these calls and imports are removed, **Then** the registry still correctly provides agents, actions, and generators to active workflows.

---

### User Story 4 - Delete Dead Tests (Priority: P3)

As a Maverick maintainer, I need the ~33,400 lines of dead test code removed so that CI runs significantly faster and test reports only show results for code that actually exists.

**Why this priority**: Dead tests are low-risk to remove since they test deleted code, but this is sequenced last because it depends on the source code changes being complete first. Tests for the extracted modules must be preserved and moved to match new source locations.

**Independent Test**: Can be verified by confirming: (a) dead test directories are removed, (b) executor and checkpoint tests are moved to their new locations, (c) `make test` passes with the remaining test suite.

**Acceptance Scenarios**:

1. **Given** test directories for serialization, expressions, visualization, discovery, steps, and prerequisites all test dead YAML code, **When** they are deleted along with dead integration tests and dead library tests, **Then** `make test` passes and only tests for live code remain.
2. **Given** tests for the executor and checkpoint modules test actively-used code, **When** they are moved to new directories matching the new source locations with imports updated, **Then** they continue to pass at their new locations.

---

### Edge Cases

- What happens if any active code has a transitive import through a dead module? All imports must be traced through the full dependency graph, not just direct imports.
- How does the system handle checkpoint files created by the old code path that reference old module paths in serialized data? Checkpoint data uses simple JSON formats, not pickled class references, so this should not be an issue.
- What if a third-party plugin or user configuration references old import paths? No backwards-compatibility shims are maintained; this is an internal restructuring with no external API guarantees.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST relocate all actively-used modules from `maverick.dsl` to proper top-level locations (`maverick.events`, `maverick.executor`, `maverick.results`, `maverick.types`, `maverick.checkpoint`, `maverick.registry`) with zero behavior changes.
- **FR-002**: System MUST merge active error classes from `dsl/errors.py` into the project's exception hierarchy, renaming `DSLWorkflowError` to `WorkflowStepError`.
- **FR-003**: System MUST move active configuration constants from `dsl/config.py` to a proper constants module as module-level constants (not wrapped in a dataclass).
- **FR-004**: System MUST remove `WorkflowRegistry`, `ContextBuilderRegistry`, and their type aliases from the registry, retaining only agent, action, and generator registries.
- **FR-005**: System MUST remove all dead functions and dead imports from CLI modules without affecting active functionality.
- **FR-006**: System MUST delete the entire `maverick.dsl` package after extraction, along with dead YAML workflow files, fragment files, and the builtin workflow library loader.
- **FR-007**: System MUST remove the `lark` parser library from project dependencies.
- **FR-008**: System MUST delete all test code that exclusively tests dead YAML DSL modules (~33,400 lines).
- **FR-009**: System MUST preserve and relocate tests for the extracted modules (executor tests and checkpoint tests) to directories matching their new source locations.
- **FR-010**: System MUST update all imports across the entire source and test trees so no references to `maverick.dsl` remain.
- **FR-011**: System MUST NOT change any behavior of the Python workflow base class, step executor protocol, Claude step executor, executor results, the CLI workflow execution function, any concrete workflow implementation, any agent class, the project configuration schema, hooks modules, or flight plan models.

### Key Entities

- **Live Modules**: The ~3,700 lines of actively-used code under `maverick.dsl` that must be extracted before deletion (events, executor, results, types, errors, checkpoint, registry, config constants).
- **Dead Modules**: The ~16,300 lines of YAML-only code (parser, schema, writer, editor, validation, expression language, visualization, discovery, step definitions, context builders, streaming, protocols, executor handlers).
- **Dead Tests**: The ~33,400 lines of test code that exclusively exercise dead YAML modules (~28,000 unit + ~5,400 integration).
- **Dead Dependencies**: The `lark` parser library, used only by the dead expression parser.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero references to `maverick.dsl` remain anywhere in source or test trees after completion.
- **SC-002**: All existing tests that exercise the Python workflow path continue to pass with no modifications beyond import path updates.
- **SC-003**: Source code is reduced by approximately 20,000 lines (the entire `maverick.dsl` package, of which ~16,300 is dead modules and the rest is live code relocated to new locations).
- **SC-004**: Test code is reduced by approximately 33,400 lines (dead YAML DSL tests: ~28,000 unit + ~5,400 integration).
- **SC-005**: Static analysis (linter and type checker) passes cleanly with no broken import errors.
- **SC-006**: The `lark` package is no longer a dependency and is not installed in the project environment.
- **SC-007**: All CLI commands (`fly`, `land`, `refuel maverick`, `refuel speckit`, `flight-plan generate`) function identically after the change.
- **SC-008**: The project installs cleanly from a fresh dependency sync with no missing dependencies.

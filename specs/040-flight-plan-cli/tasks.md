# Tasks: Flight Plan CLI Command Group

**Input**: Design documents from `/specs/040-flight-plan-cli/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/cli-interface.md, quickstart.md

**Tests**: Included — the project constitution mandates Test-First (TDD) for all public functions. Tests are written before implementation within each user story phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root
- CLI commands: `src/maverick/cli/commands/<group>/`
- Domain logic: `src/maverick/flight/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the CLI command group package and register it with the top-level CLI. Both US1 and US2 depend on this phase.

- [x] T001 Create the flight_plan CLI command group package: `_group.py` with `@click.group("flight-plan", invoke_without_command=True)` that shows help when invoked without a subcommand, and `__init__.py` that re-exports the group in src/maverick/cli/commands/flight_plan/
- [x] T002 Register the flight_plan command group in src/maverick/main.py (add import from `maverick.cli.commands.flight_plan` and `cli.add_command(flight_plan)` call, following the existing workspace/refuel pattern)
- [ ] T003 [P] Create shared CLI test fixtures (CliRunner setup, temporary directories for flight plan files) in tests/unit/cli/commands/flight_plan/conftest.py

**Checkpoint**: `maverick flight-plan` shows help text; `maverick flight-plan --help` works. Test infrastructure ready.

---

## Phase 2: User Story 1 — Create a New Flight Plan (Priority: P1) :dart: MVP

**Goal**: A developer can run `maverick flight-plan create my-feature` to scaffold a skeleton flight plan file with all required sections stubbed out with HTML comment editing instructions.

**Independent Test**: Run `maverick flight-plan create my-plan` and verify a well-formed skeleton file is written to `.maverick/flight-plans/my-plan.md` with valid YAML frontmatter and all required Markdown sections.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T004 [P] [US1] Write unit tests for `generate_skeleton(name, created)` covering: YAML frontmatter fields (name, version "1", created date, empty tags), all required Markdown sections present (Objective, Success Criteria, Scope with In/Out/Boundaries subsections, Context, Constraints, Notes), HTML comment editing instructions in each section, and placeholder checkbox items in Success Criteria in tests/unit/flight/test_template.py
- [ ] T005 [P] [US1] Write unit tests for `create` subcommand covering: happy-path file creation with default output dir, custom `--output-dir` option, auto-creation of output directory and parents, overwrite guard (refuse if file exists), kebab-case name validation (reject uppercase, spaces, leading digits, trailing hyphens, slashes, unicode), and `--output-dir` pointing to an existing file (not a directory) in tests/unit/cli/commands/flight_plan/test_create.py

### Implementation for User Story 1

- [ ] T006 [US1] Implement `generate_skeleton(name: str, created: date) -> str` in src/maverick/flight/template.py — build YAML frontmatter via `yaml.dump()` and Markdown body with all required sections containing HTML comment editing instructions (per FR-005, FR-006, and the data-model.md file format)
- [ ] T007 [US1] Implement `create` subcommand in src/maverick/cli/commands/flight_plan/create.py: `@flight_plan.command("create")` with NAME argument and `--output-dir` option (default `.maverick/flight-plans/`), kebab-case validation regex `^[a-z]([a-z0-9-]*[a-z0-9])?$` (per D3 in plan.md), directory auto-creation via `Path.mkdir(parents=True, exist_ok=True)`, overwrite guard, Rich-formatted success/error output, and register the import in src/maverick/cli/commands/flight_plan/__init__.py

**Checkpoint**: `maverick flight-plan create my-feature` creates a valid skeleton file. All T004-T005 tests pass.

---

## Phase 3: User Story 2 — Validate a Flight Plan (Priority: P1)

**Goal**: A developer can run `maverick flight-plan validate plan.md` to check structural correctness of a flight plan file and receive a report of all issues found in a single invocation.

**Independent Test**: Run `maverick flight-plan validate path/to/plan.md` against both valid and invalid flight plan files and verify the output reports pass/fail with specific issue descriptions and correct exit codes.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T008 [P] [US2] Write unit tests for `validate_flight_plan_file(path)` covering: valid file returns empty list, missing frontmatter delimiters, malformed YAML, missing required frontmatter fields (name, version, created), missing required sections (Objective, Success Criteria, Scope), empty objective text, empty success criteria (no checkbox items), empty file (0 bytes), and valid frontmatter with wrong section heading levels (### instead of ##) in tests/unit/flight/test_validator.py
- [ ] T009 [P] [US2] Write unit tests for `validate` subcommand covering: valid file prints success message and exits 0, validation failures print Rich-formatted issue list and exit 1, file-not-found prints error and exits 1, and each issue includes its location field in tests/unit/cli/commands/flight_plan/test_validate_cmd.py

### Implementation for User Story 2

- [ ] T010 [US2] Implement `ValidationIssue` frozen dataclass (location: str, message: str) and `validate_flight_plan_file(path: Path) -> list[ValidationIssue]` in src/maverick/flight/validator.py — use `parse_frontmatter()` and `parse_flight_plan_sections()` from `maverick.flight.parser` in a try/collect pattern to check all validation rules (V1-V9 from data-model.md), re-raise FileNotFoundError for CLI layer
- [ ] T011 [US2] Implement `validate` subcommand in src/maverick/cli/commands/flight_plan/validate_cmd.py: `@flight_plan.command("validate")` with FILE_PATH argument (plain string, not click.Path(exists=True) per R5 in research.md), call `validate_flight_plan_file()`, render Rich-formatted success/failure output, set `sys.exit(1)` on validation failure or file-not-found, and register the import in src/maverick/cli/commands/flight_plan/__init__.py

**Checkpoint**: `maverick flight-plan validate plan.md` reports all issues with locations. All T008-T009 tests pass.

---

## Phase 4: User Story 3 — Discover Flight Plan Commands (Priority: P2)

**Goal**: A developer can discover available subcommands and their usage by running `maverick flight-plan --help` or `maverick flight-plan` without arguments.

**Independent Test**: Run `maverick flight-plan --help` and verify both `create` and `validate` subcommands are listed with descriptions.

- [x] T012 [US3] Write tests verifying: `maverick flight-plan --help` output lists both `create` and `validate` subcommands with brief descriptions, `maverick flight-plan create --help` shows NAME argument and `--output-dir` option with default, and `maverick flight-plan` with no subcommand displays help text (same as --help) in tests/unit/cli/commands/flight_plan/test_help.py
- [x] T013 [US3] Review and polish docstrings and help text on the flight_plan group, create command, and validate command to ensure Click-generated help is clear and matches the CLI interface contract in specs/040-flight-plan-cli/contracts/cli-interface.md

**Checkpoint**: All help text acceptance scenarios pass. Commands are self-documenting.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Integration testing, public API exports, and final validation across all user stories.

- [x] T014 [P] Write end-to-end integration tests covering the full create-then-validate workflow (create a plan, edit stub content, validate it passes; also validate an unedited skeleton reports expected issues) in tests/integration/cli/test_flight_plan_commands.py
- [x] T015 [P] Export `ValidationIssue`, `validate_flight_plan_file`, and `generate_skeleton` from the public API in src/maverick/flight/__init__.py
- [x] T016 Run `make check` to verify lint (ruff), typecheck (mypy), and all tests pass across the entire test suite

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **User Story 1 (Phase 2)**: Depends on Setup (Phase 1) completion
- **User Story 2 (Phase 3)**: Depends on Setup (Phase 1) completion — can run in parallel with US1
- **User Story 3 (Phase 4)**: Depends on US1 (Phase 2) AND US2 (Phase 3) — needs both subcommands registered to verify help output
- **Polish (Phase 5)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Setup (Phase 1) — no dependencies on other stories
- **User Story 2 (P1)**: Can start after Setup (Phase 1) — no dependencies on other stories
- **User Story 3 (P2)**: Depends on US1 and US2 (needs both commands registered to verify help listing)

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Domain module (template/validator) before CLI subcommand
- CLI subcommand includes registration in `__init__.py`

### Parallel Opportunities

- T002 and T003 can run in parallel (after T001)
- T004 and T005 can run in parallel (different files, both US1 tests)
- T008 and T009 can run in parallel (different files, both US2 tests)
- **US1 (Phase 2) and US2 (Phase 3) can run in parallel** after Setup completes — they touch entirely different files
- T014 and T015 can run in parallel (different files, both Polish)

---

## Parallel Example: User Story 1

```bash
# Launch all tests for US1 together (TDD — write tests first):
Task: "Unit tests for generate_skeleton() in tests/unit/flight/test_template.py"
Task: "Unit tests for create subcommand in tests/unit/cli/commands/flight_plan/test_create.py"

# Then implement (domain before CLI):
Task: "Implement generate_skeleton() in src/maverick/flight/template.py"
Task: "Implement create subcommand in src/maverick/cli/commands/flight_plan/create.py"
```

## Parallel Example: User Story 1 + User Story 2

```bash
# After Setup completes, both stories can start simultaneously:
# Developer A works on US1 (create):
Task: "Tests for template → Implement template → Tests for create cmd → Implement create cmd"

# Developer B works on US2 (validate):
Task: "Tests for validator → Implement validator → Tests for validate cmd → Implement validate cmd"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: User Story 1 — Create (T004-T007)
3. **STOP and VALIDATE**: `maverick flight-plan create test-plan` works end-to-end
4. The create command alone delivers immediate value

### Incremental Delivery

1. Complete Setup → Command group registered and working
2. Add User Story 1 (Create) → Test independently → Developers can scaffold flight plans
3. Add User Story 2 (Validate) → Test independently → Developers can validate flight plans
4. Add User Story 3 (Discover) → Verify help text → Self-documenting CLI
5. Polish → Integration tests, API exports, full suite green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- This is a synchronous, local-only feature — no async, no agents, no network calls
- All tests are synchronous (no pytest-asyncio needed)
- Follow existing CLI command group patterns from `workspace/` and `refuel/` packages
- Kebab-case regex for plan names: `^[a-z]([a-z0-9-]*[a-z0-9])?$` (stricter than `_KEBAB_RE` in models.py — requires starting with a letter per FR-013)
- Validate subcommand uses `parse_frontmatter()` and `parse_flight_plan_sections()` directly (not `FlightPlanFile.load()`) to enable multi-error collection
- Commit after each task or logical group

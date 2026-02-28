# Implementation Plan: Flight Plan CLI Command Group

**Branch**: `040-flight-plan-cli` | **Date**: 2026-02-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/040-flight-plan-cli/spec.md`

## Summary

Add a `maverick flight-plan` CLI command group with `create` and `validate` subcommands. The `create` subcommand scaffolds a skeleton flight plan Markdown file with YAML frontmatter and all required sections stubbed out with HTML comment instructions. The `validate` subcommand parses a flight plan file using the existing parser primitives and collects all structural issues (missing sections, empty criteria, malformed frontmatter) into a typed report rendered with Rich. This is a synchronous, local-only feature with no agent calls or network requests.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Click (CLI), Rich (output formatting), Pydantic (models)
**Storage**: Markdown+YAML files on disk (`.maverick/flight-plans/`)
**Testing**: pytest (synchronous tests — no pytest-asyncio needed for this feature)
**Target Platform**: Linux/macOS/Windows CLI
**Project Type**: Single project — extends existing CLI
**Performance Goals**: < 1 second for both subcommands (local file I/O only)
**Constraints**: No async, no agents, no network calls. Reuse existing `maverick.flight` parser primitives.
**Scale/Scope**: 2 CLI subcommands, 1 validator module, 1 template module, ~6 new files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Status | Notes |
|-----------|----------|--------|-------|
| I. Async-First | No | N/A | Synchronous CLI tool, no agents or event loop |
| II. Separation of Concerns | Yes | Pass | CLI commands delegate to `flight.validator` and `flight.template` modules |
| III. Dependency Injection | Minimal | Pass | No agents/workflows; console is module-level singleton (existing pattern) |
| IV. Fail Gracefully | Minimal | Pass | Single-user CLI; errors reported directly to console |
| V. Test-First | Yes | Pass | Unit tests for validator, template, and CLI commands planned |
| VI. Type Safety | Yes | Pass | `ValidationIssue` frozen dataclass; all functions typed |
| VII. Simplicity & DRY | Yes | Pass | Reuses existing parser primitives; no duplication |
| VIII. Relentless Progress | No | N/A | Not a long-running/unattended operation |
| IX. Hardening | No | N/A | No external calls requiring retries |
| X. Guardrails | Partial | Pass | #6 (canonical wrappers): no new subprocess wrappers; #8 (canonical libs): uses structlog for logging |
| XI. Modularize Early | Yes | Pass | CLI command group as package; validator and template as separate modules |
| XII. Ownership | Yes | Pass | Full test coverage planned |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/040-flight-plan-cli/
├── plan.md              # This file
├── research.md          # Phase 0 output (minimal — no unknowns)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/
├── cli/commands/
│   └── flight_plan/              # NEW: Command group package
│       ├── __init__.py           # Re-exports flight_plan group; imports subcommands
│       ├── _group.py             # @click.group("flight-plan") definition
│       ├── create.py             # create subcommand
│       └── validate_cmd.py       # validate subcommand (avoid shadowing builtins)
├── flight/
│   ├── template.py               # NEW: Skeleton flight plan generation
│   └── validator.py              # NEW: Multi-error validation with typed results
├── main.py                       # MODIFY: Register flight_plan command group

tests/
├── unit/
│   ├── cli/commands/flight_plan/
│   │   ├── conftest.py           # Shared fixtures (cli_runner setup, temp dirs)
│   │   ├── test_create.py        # Create subcommand tests
│   │   └── test_validate_cmd.py  # Validate subcommand tests
│   └── flight/
│       ├── test_template.py      # Template generation tests
│       └── test_validator.py     # Validator logic tests
└── integration/cli/
    └── test_flight_plan_commands.py  # End-to-end CLI tests
```

**Structure Decision**: Follows the CLI split pattern from Constitution Appendix A — command group as a package under `src/maverick/cli/commands/flight_plan/` with the same `_group.py` + `__init__.py` pattern used by the `refuel` and `workspace` command groups. Domain logic (template generation, validation) lives in the `flight` package alongside the existing models, loader, parser, and serializer.

## Design Decisions

### D1: Multi-error validation via parser primitives

The `validate` subcommand needs to report multiple issues at once (FR-010, acceptance scenario US2-2). The existing `FlightPlanFile.load()` raises on the first error encountered, so it cannot collect all issues in one pass.

**Decision**: Create `flight/validator.py` that uses the same parser primitives (`parse_frontmatter`, `parse_flight_plan_sections`) directly, but wraps each check in a try/collect pattern. This reuses the canonical parsing logic without duplicating it, and returns a `list[ValidationIssue]` with all problems found.

**Alternative rejected**: Wrapping `FlightPlanFile.load()` and calling it repeatedly — this would require modifying the file between attempts, which doesn't make sense. Also rejected adding multi-error collection to the loader itself, as that would change the loader's established fail-fast contract.

### D2: Template as a string-building function

**Decision**: Create `flight/template.py` with a `generate_skeleton(name: str, created: date) -> str` function that builds the Markdown+YAML content as a string. This is simpler than constructing a `FlightPlan` model instance and serializing it, because the skeleton contains HTML comments (editing instructions) that the model and serializer don't support.

**Alternative rejected**: Using the existing `serialize_flight_plan()` — the serializer omits empty optional sections and doesn't support HTML comment stubs. The template needs instructional comments in every section.

### D3: Kebab-case validation regex

The `_KEBAB_RE` pattern already exists in `maverick.flight.models` (`^[a-z0-9]+(-[a-z0-9]+)*$`). The spec additionally requires "must start with a letter" (FR-013).

**Decision**: Define a slightly stricter regex `^[a-z]([a-z0-9-]*[a-z0-9])?$` in the create command or a shared constant, which ensures the name starts with a letter and doesn't end with a hyphen. This is stricter than `_KEBAB_RE` (which allows starting with a digit) but matches the spec requirement.

### D4: CLI subcommand file naming

**Decision**: Name the validate subcommand file `validate_cmd.py` instead of `validate.py` to avoid shadowing Python's built-in `validate` and potential import confusion with the `validator.py` module in the flight package.

## Module Contracts

### `maverick.flight.validator`

```python
@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single structural issue found during flight plan validation."""
    location: str   # e.g., "frontmatter.name", "section.objective", "section.success_criteria"
    message: str    # Human-readable description

def validate_flight_plan_file(path: Path) -> list[ValidationIssue]:
    """Validate a flight plan file and return all structural issues found.

    Uses the existing parse_frontmatter() and parse_flight_plan_sections()
    primitives to check:
    - File readability
    - YAML frontmatter structure and required fields (name, version, created)
    - Required sections (Objective, Success Criteria, Scope)
    - Non-empty success criteria (at least one checkbox item)
    - Non-empty objective text

    Returns:
        Empty list if valid; list of ValidationIssue for each problem found.

    Raises:
        FileNotFoundError: Re-raised as-is for the CLI layer to handle.
    """
```

### `maverick.flight.template`

```python
def generate_skeleton(name: str, created: date) -> str:
    """Generate a skeleton flight plan Markdown file.

    Returns Markdown+YAML content with:
    - YAML frontmatter: name, version "1", created date, empty tags
    - All required sections with HTML comment editing instructions
    - Placeholder checkbox items in Success Criteria
    - Scope subsections (In/Out/Boundaries) with placeholder bullets

    Args:
        name: Plan name (used in frontmatter, assumed already validated).
        created: Creation date for the frontmatter.

    Returns:
        Complete Markdown string ready to write to disk.
    """
```

### `maverick.cli.commands.flight_plan`

```python
# _group.py
@click.group("flight-plan", invoke_without_command=True)
@click.pass_context
def flight_plan(ctx: click.Context) -> None:
    """Create and validate flight plan files."""

# create.py
@flight_plan.command("create")
@click.argument("name")
@click.option("--output-dir", default=".maverick/flight-plans/", ...)
def create_cmd(name: str, output_dir: str) -> None:
    """Create a new flight plan from a template."""

# validate_cmd.py
@flight_plan.command("validate")
@click.argument("file_path", type=click.Path())
def validate_cmd(file_path: str) -> None:
    """Validate a flight plan file for structural issues."""
```

## Complexity Tracking

No constitution violations requiring justification. All modules are well under size thresholds.

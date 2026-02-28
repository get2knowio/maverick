# Research: Flight Plan CLI Command Group

**Branch**: `040-flight-plan-cli` | **Date**: 2026-02-28

## Summary

No critical unknowns required external research. This feature is a synchronous CLI tool
that composes existing, well-documented components (Click, Rich, existing `maverick.flight`
parser primitives). All decisions were resolved through codebase exploration.

## Findings

### R1: Multi-error validation approach

**Decision**: Use existing parser primitives (`parse_frontmatter`, `parse_flight_plan_sections`)
in a try/collect pattern rather than `FlightPlanFile.load()` which fails fast.

**Rationale**: The spec requires reporting multiple issues at once (FR-010, US2 acceptance
scenario 2). The parser primitives are pure functions with no side effects, making them
safe to call independently for each validation stage. This reuses canonical parsing logic
without duplicating it.

**Alternatives considered**:
- `FlightPlanFile.load()` with exception handling — only reports first error
- Adding multi-error mode to loader — changes established fail-fast contract
- Custom parser from scratch — violates DRY principle

### R2: Template content format

**Decision**: Build template as a string with `yaml.dump()` for frontmatter and string
concatenation for Markdown sections. Include HTML comments as editing instructions.

**Rationale**: The existing `serialize_flight_plan()` serializer omits empty optional
sections and doesn't support HTML comments. The template needs instructional stubs in
every section. A standalone template function is simpler and doesn't fight the serializer's
design.

**Alternatives considered**:
- Construct a FlightPlan model instance and serialize — model validators reject empty
  required fields (objective, name), so we can't create a "stub" instance
- External template file (Jinja2, etc.) — over-engineering for a single string

### R3: CLI command group pattern

**Decision**: Follow the `refuel/` package pattern exactly: `_group.py` for Click group,
`__init__.py` for re-exports and subcommand registration, individual files per subcommand.

**Rationale**: Established pattern in the codebase. Constitution Appendix A explicitly
prescribes this structure for CLI commands.

### R4: Kebab-case validation

**Decision**: Use regex `^[a-z]([a-z0-9-]*[a-z0-9])?$` — must start with letter, allows
lowercase alphanumeric and hyphens, must not end with hyphen.

**Rationale**: Spec FR-013 requires "must start with a letter". The existing `_KEBAB_RE`
in `maverick.flight.models` (`^[a-z0-9]+(-[a-z0-9]+)*$`) allows starting with a digit.
The stricter pattern aligns with the spec while remaining compatible with all existing
plan names (which are kebab-case identifiers starting with letters).

### R5: validate subcommand — click.Path(exists=True) consideration

**Decision**: Do NOT use `click.Path(exists=True)` for the validate command's file path
argument. Instead, accept a plain string and handle FileNotFoundError explicitly.

**Rationale**: `click.Path(exists=True)` produces Click's generic error message
("Path 'X' does not exist.") which doesn't match our Rich-formatted output style. By
handling it ourselves, we can provide a consistent, Rich-formatted error message that
matches the rest of the validation output.

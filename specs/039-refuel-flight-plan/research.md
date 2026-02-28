# Research: Refuel Flight-Plan Subcommand

**Feature Branch**: `039-refuel-flight-plan`
**Date**: 2026-02-28

## Research Summary

This feature adds a thin CLI entry point (`maverick refuel flight-plan`) that delegates to the existing `RefuelMaverickWorkflow`. Research focused on confirming reuse viability and identifying the exact patterns to follow.

## Findings

### 1. RefuelMaverickWorkflow Reusability

**Decision**: Full reuse — no modifications needed.

**Evidence**:
- The `RefuelMaverickWorkflow._run()` accepts `flight_plan_path` (str) and `dry_run` (bool) as inputs
- The 7-step pipeline (parse → gather context → decompose → validate → write → create beads → wire deps) matches all functional requirements (FR-001 through FR-015)
- Clean slate behavior (FR-015) is already implemented via `shutil.rmtree()` before writing
- Failure-on-error behavior (FR-014) is already implemented — decomposition failures raise without writing
- Session log support (FR-009) is handled by `execute_python_workflow()`, not the workflow itself

**Alternatives Rejected**:
- New workflow class: Would duplicate ~400 LOC with zero behavioral difference
- Workflow wrapper: Unnecessary indirection; `PythonWorkflowRunConfig` already provides the abstraction

### 2. CLI Command Pattern Analysis

**Pattern source**: `src/maverick/cli/commands/refuel/maverick_cmd.py` (113 LOC)

The existing `refuel maverick` command demonstrates the exact pattern:

| Aspect | Pattern | Reusable? |
|--------|---------|-----------|
| Decorator stack | `@refuel.command()` → `@click.argument()` → `@click.option()` → `@click.pass_context` → `@async_command` | Yes |
| `--list-steps` handling | Early exit with step name display | Yes (copy pattern) |
| Workflow delegation | `execute_python_workflow(ctx, PythonWorkflowRunConfig(...))` | Yes |
| `--dry-run` | Passed as input to workflow | Yes |
| `--session-log` | Passed to `PythonWorkflowRunConfig.session_log_path` | Yes |

### 3. Subcommand Registration Pattern

**Pattern source**: `src/maverick/cli/commands/refuel/__init__.py`

Subcommands register by being imported in `__init__.py`. The import triggers the `@refuel.command()` decorator:

```python
# isort: off
from maverick.cli.commands.refuel._group import refuel
from maverick.cli.commands.refuel import speckit as _speckit  # noqa: F401
from maverick.cli.commands.refuel import maverick_cmd as _maverick_cmd  # noqa: F401
# New:
from maverick.cli.commands.refuel import flight_plan as _flight_plan  # noqa: F401
# isort: on
```

### 4. Test Pattern Analysis

**Pattern source**: `tests/unit/cli/commands/refuel/test_maverick_cmd.py` (216 LOC)

Tests mock `execute_python_workflow` and verify:
- Command registration (appears in `--help`)
- Required arguments (missing arg → non-zero exit)
- Flag forwarding (dry-run, session-log)
- Workflow class selection (correct workflow used)
- Step list display (all step names present in output)

### 5. Naming Conventions

| Item | Convention | Value |
|------|-----------|-------|
| CLI command name | Hyphenated | `flight-plan` |
| Python module name | Underscored | `flight_plan.py` |
| Python function name | Underscored with suffix | `flight_plan_cmd` |
| Click metavar | Uppercase hyphenated | `FLIGHT-PLAN-PATH` |
| Workflow name constant | Reuse existing | `WORKFLOW_NAME` from `refuel_maverick.constants` |

## Open Questions

None — all unknowns resolved through codebase research. The feature is a straightforward CLI addition with no architectural decisions required.

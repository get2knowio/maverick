# Implementation Plan: CLI Entry Point

**Branch**: `014-cli-entry-point` | **Date**: 2025-12-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/014-cli-entry-point/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement the complete CLI entry point for Maverick using Click, providing a main CLI group with global options (`--config`, `--verbose`, `--quiet`, `--no-tui`, `--version`, `--help`) and subcommands for `fly`, `refuel`, `review`, `config`, and `status`. The CLI bridges user commands to existing workflows and TUI, supporting both interactive TUI mode and headless CI/CD operation.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Click (CLI), Textual (TUI), Pydantic (config validation), existing workflows (FlyWorkflow, RefuelWorkflow)
**Storage**: YAML config files (project: `maverick.yaml`, user: `~/.config/maverick/config.yaml`)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Linux, macOS, Windows (terminal environments)
**Project Type**: Single project (CLI application)
**Performance Goals**: CLI startup time under 500ms before command execution begins (NFR-001)
**Constraints**: Auto-detect non-TTY environments, graceful keyboard interrupt handling, standard exit codes (0/1/2)
**Scale/Scope**: 5 main commands + 4 config subcommands, ~10-15 CLI options total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Status | Notes |
|-----------|-------------|--------|-------|
| I. Async-First | All workflow interactions MUST be async | ✅ PASS | CLI will use `asyncio.run()` to bridge sync Click to async workflows |
| II. Separation of Concerns | CLI knows WHEN, workflows know HOW | ✅ PASS | CLI dispatches to existing workflows, no business logic in CLI |
| III. Dependency Injection | Configuration passed, not global state | ✅ PASS | Config loaded at startup, passed via Click context |
| IV. Fail Gracefully | Errors MUST NOT crash workflows | ✅ PASS | CLI catches MaverickError hierarchy, reports actionable messages |
| V. Test-First | All public functions MUST have tests | ⏳ GATE | Tests required for all CLI commands |
| VI. Type Safety | Complete type hints required | ✅ PASS | All parameters and returns will be typed |
| VII. Simplicity | No premature abstractions | ✅ PASS | Building on existing main.py, extending not replacing |
| VIII. Relentless Progress | Forward progress at all costs | ✅ PASS | CLI exits cleanly, workflows handle recovery internally |

**Technology Stack Compliance**:
- ✅ Click for CLI (per constitution)
- ✅ Textual for TUI (per constitution)
- ✅ Pydantic for configuration (per constitution)
- ✅ pytest + pytest-asyncio for testing (per constitution)

## Project Structure

### Documentation (this feature)

```text
specs/014-cli-entry-point/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── __init__.py          # Version, public API exports
├── main.py              # CLI entry point (EXTENDED - all commands here)
├── config.py            # Pydantic configuration models (existing)
├── exceptions.py        # Custom exception hierarchy (existing)
├── cli/                 # NEW: CLI-specific utilities
│   ├── __init__.py
│   ├── context.py       # CLIContext dataclass for global options
│   ├── output.py        # Output formatting (JSON, markdown, TUI)
│   └── validators.py    # CLI argument validators (branch exists, etc.)
├── workflows/           # Existing workflow orchestration
│   ├── fly.py           # FlyWorkflow (existing)
│   └── refuel.py        # RefuelWorkflow (existing)
└── tui/                 # Existing TUI application
    └── app.py           # MaverickApp (existing)

tests/
├── unit/
│   └── cli/             # NEW: CLI unit tests
│       ├── test_main.py          # Test CLI commands
│       ├── test_context.py       # Test CLIContext
│       ├── test_output.py        # Test output formatting
│       └── test_validators.py    # Test validators
└── integration/
    └── cli/             # NEW: CLI integration tests
        └── test_cli_commands.py  # End-to-end CLI tests
```

**Structure Decision**: Extending existing `src/maverick/main.py` with new commands, adding a `cli/` subdirectory for CLI-specific utilities (context, output formatting, validators). Tests follow the existing pattern under `tests/unit/` and `tests/integration/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. All principles pass:
- Single project structure maintained
- Building on existing patterns (main.py, config.py, exceptions.py)
- No new abstractions beyond what's needed for CLI utilities

---

## Post-Design Constitution Check

*Re-evaluation after Phase 1 design completion.*

| Principle | Status | Design Verification |
|-----------|--------|---------------------|
| I. Async-First | ✅ PASS | `@async_command` decorator bridges sync Click to async workflows. All workflow calls use `asyncio.run()`. |
| II. Separation of Concerns | ✅ PASS | CLI module only handles argument parsing and dispatch. No business logic. Workflows handle execution. |
| III. Dependency Injection | ✅ PASS | `CLIContext` dataclass passed via Click context. `MaverickConfig` injected at startup. |
| IV. Fail Gracefully | ✅ PASS | All commands catch `MaverickError` hierarchy. `ExitCode` enum provides standard codes. Keyboard interrupts handled. |
| V. Test-First | ⏳ GATE | Test files defined in structure. Implementation must follow TDD. |
| VI. Type Safety | ✅ PASS | `CLIContext`, `ExitCode`, `OutputFormat`, `DependencyStatus` all fully typed. `@dataclass(frozen=True, slots=True)` used. |
| VII. Simplicity | ✅ PASS | 3 new files in `cli/` module. Extends existing `main.py`. No over-engineering. |
| VIII. Relentless Progress | ✅ PASS | CLI exits with appropriate codes. Workflows handle their own recovery. |

**Design Artifacts Produced**:
- `research.md` - Click best practices, async handling patterns
- `data-model.md` - Entity definitions (CLIContext, ExitCode, OutputFormat, etc.)
- `contracts/cli-interface.md` - Full CLI interface specification
- `quickstart.md` - Implementation guide

**Ready for Phase 2**: Yes - all gates pass, design complete.

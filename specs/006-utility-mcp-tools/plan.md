# Implementation Plan: Utility MCP Tools

**Branch**: `006-utility-mcp-tools` | **Date**: 2025-12-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-utility-mcp-tools/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create custom MCP tools for notifications (ntfy.sh), git utilities (commit, push, branch, diff), and validation (format, lint, build, test) for Maverick agents. Tools follow established patterns from `maverick.tools.github` using Claude Agent SDK's `@tool` decorator and `create_sdk_mcp_server()` factory. Three factory functions (`create_notification_tools_server()`, `create_git_tools_server()`, `create_validation_tools_server()`) return configured MCP servers that agents can use for workflow automation.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI, ntfy.sh (HTTP API)
**Storage**: N/A (tools interact with external systems: git, ntfy.sh, validation commands)
**Testing**: pytest + pytest-asyncio, mocking external dependencies
**Target Platform**: Linux/macOS CLI environment with git installed
**Project Type**: Single project (existing Maverick structure)
**Performance Goals**: Simple operations (git_current_branch, send_notification) complete within 2s; validation supports up to 10 minute timeout
**Constraints**: Graceful degradation when ntfy.sh unavailable; structured error responses for all failure modes
**Scale/Scope**: 9 tools across 3 MCP servers; integrates with existing FlyWorkflow and RefuelWorkflow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Compliance | Notes |
|-----------|-------------|------------|-------|
| I. Async-First | All tools must be async | ✅ PASS | All `@tool` decorated functions are `async def`, following `github.py` patterns |
| II. Separation of Concerns | Tools wrap external systems only | ✅ PASS | Tools wrap git CLI, ntfy.sh HTTP API, and validation commands - no business logic |
| III. Dependency Injection | Config passed in, not global state | ✅ PASS | Factory functions accept config parameters; no module-level mutable state |
| IV. Fail Gracefully | Errors captured with context | ✅ PASS | Structured error responses with `isError`, `error_code`, retry hints; graceful degradation for ntfy.sh |
| V. Test-First | Tests required for all public functions | ✅ PLANNED | Unit tests with mocked subprocesses and HTTP calls |
| VI. Type Safety | Complete type hints required | ✅ PASS | Pydantic models for config; full type annotations per existing patterns |
| VII. Simplicity | No premature abstractions | ✅ PASS | Direct implementation; reuse existing `_run_git_command` pattern from `utils/git.py` |
| VIII. Relentless Progress | Retry with backoff, graceful degradation | ✅ PASS | Notification tools retry 1-2 times; validation tools support timeout; never block workflow |

**Gate Status**: ✅ ALL GATES PASS - Ready for Phase 0

### Post-Phase 1 Re-Check

After completing Phase 1 design artifacts (research.md, data-model.md, contracts/, quickstart.md):

| Principle | Re-Check | Status |
|-----------|----------|--------|
| I. Async-First | Tools use aiohttp for HTTP, asyncio.subprocess for CLI | ✅ CONFIRMED |
| II. Separation | No business logic in tools; workflow orchestration stays in workflows | ✅ CONFIRMED |
| III. DI | Factory functions accept optional config; no global state | ✅ CONFIRMED |
| IV. Fail Gracefully | Error responses documented with codes; notification graceful degradation designed | ✅ CONFIRMED |
| V. Test-First | Test files mapped in project structure | ✅ CONFIRMED |
| VI. Type Safety | Pydantic models defined for ValidationConfig; TypeScript-style contracts | ✅ CONFIRMED |
| VII. Simplicity | Reusing existing patterns from github.py and utils/git.py | ✅ CONFIRMED |
| VIII. Relentless Progress | Retry logic for notifications; timeout handling for validation | ✅ CONFIRMED |

**Post-Design Gate Status**: ✅ ALL GATES PASS - Ready for Phase 2 (Tasks)

## Project Structure

### Documentation (this feature)

```text
specs/006-utility-mcp-tools/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── tool-responses.md  # MCP tool response schemas
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── tools/
│   ├── __init__.py          # Updated: exports new factory functions
│   ├── github.py            # Existing: GitHub MCP tools (reference pattern)
│   ├── notification.py      # NEW: send_notification, send_workflow_update
│   ├── git.py               # NEW: git_current_branch, git_create_branch, git_commit, git_push, git_diff_stats
│   └── validation.py        # NEW: run_validation, parse_validation_output
├── config.py                # Updated: ValidationConfig if needed
└── exceptions.py            # Updated: NotificationToolsError, GitToolsError, ValidationToolsError

tests/
├── tools/
│   ├── test_notification.py # NEW: unit tests for notification tools
│   ├── test_git_tools.py    # NEW: unit tests for git tools
│   └── test_validation.py   # NEW: unit tests for validation tools
└── conftest.py              # Updated: fixtures for mocking subprocess/HTTP
```

**Structure Decision**: Single project structure following existing Maverick layout. New tool modules follow the established pattern from `src/maverick/tools/github.py`. Tests mirror source structure under `tests/tools/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Implementation follows established patterns from `github.py` with minimal complexity.

# Implementation Plan: GitHub MCP Tools Integration

**Branch**: `005-github-mcp-tools` | **Date**: 2025-12-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-github-mcp-tools/spec.md`

## Summary

Create custom MCP tools for GitHub integration using Claude Agent SDK's in-process MCP server pattern. The feature provides 7 GitHub tools (`github_create_pr`, `github_list_issues`, `github_get_issue`, `github_get_pr_diff`, `github_pr_status`, `github_add_labels`, `github_close_issue`) wrapped around the `gh` CLI, exposed via a factory function `create_github_tools_server()` that returns a configured MCP server for use with Maverick agents.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), GitHub CLI (`gh`)
**Storage**: N/A (tools interact with GitHub API via CLI)
**Testing**: pytest + pytest-asyncio with mocked subprocess calls
**Target Platform**: Linux/macOS (wherever `gh` CLI is available)
**Project Type**: Single project (existing Maverick codebase)
**Performance Goals**: Tools execute within 5 seconds for typical operations (SC-002)
**Constraints**: GitHub API rate limits (5000 req/hr authenticated), diff truncation at 100KB
**Scale/Scope**: 7 tools, single MCP server factory function

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | Tools are async functions using `asyncio.create_subprocess_exec` |
| II. Separation of Concerns | PASS | Tools wrap `gh` CLI only; agents orchestrate usage |
| III. Dependency Injection | PASS | Server factory returns injectable MCP server |
| IV. Fail Gracefully | PASS | Tools return `isError: true` responses, never raise |
| V. Test-First | PASS | Unit tests with mocked subprocess required |
| VI. Type Safety | PASS | Complete type hints, Pydantic not needed (simple dicts) |
| VII. Simplicity | PASS | No abstractions - direct tool implementations |
| VIII. Relentless Progress | PASS | Error responses include retry info for rate limits |

**Gate Status**: PASSED - No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/005-github-mcp-tools/
├── plan.md              # This file
├── research.md          # Phase 0: SDK patterns, gh CLI commands
├── data-model.md        # Phase 1: Tool input/output schemas
├── quickstart.md        # Phase 1: Usage examples
├── contracts/           # Phase 1: Tool parameter schemas
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/
├── tools/
│   ├── __init__.py      # Exports create_github_tools_server
│   └── github.py        # NEW: GitHub MCP tools implementation
├── exceptions.py        # Add GitHubToolsError if needed
└── utils/
    └── github.py        # EXISTING: Low-level gh CLI helpers (reuse)

tests/
├── unit/
│   └── tools/
│       ├── __init__.py
│       └── test_github.py  # NEW: Unit tests for all 7 tools
└── integration/
    └── tools/
        ├── __init__.py
        └── test_github.py  # NEW: Integration tests (requires gh auth)
```

**Structure Decision**: Follows existing Maverick structure. New GitHub MCP tools go in `src/maverick/tools/github.py` alongside the existing (empty) `tools/__init__.py`. Reuses low-level helpers from `utils/github.py` for subprocess execution and rate limit parsing.

## Complexity Tracking

> No violations - table not needed.

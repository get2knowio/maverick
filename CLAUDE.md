# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Maverick is a Python CLI/TUI application that automates AI-powered development workflows using the Claude Agent SDK and Textual. It orchestrates multi-phase workflows: feature implementation from task lists, parallel code review, convention updates, and PR management.

## Technology Stack

| Category | Technology | Notes |
|----------|------------|-------|
| Language | Python 3.10+ | Use `from __future__ import annotations` |
| AI/Agents | Claude Agent SDK | `claude-agent-sdk` package |
| TUI | Textual | `textual` package |
| CLI | Click | `click` package |
| Validation | Pydantic | For configuration and data models |
| Testing | pytest + pytest-asyncio | All tests async-compatible |
| Linting | Ruff | Fast, comprehensive Python linter |
| Type Checking | MyPy | Strict mode recommended |

## Architecture

```
src/maverick/
├── __init__.py          # Version, public API exports
├── main.py              # CLI entry point (Click commands)
├── config.py            # Pydantic configuration models
├── exceptions.py        # Custom exception hierarchy (MaverickError base)
├── agents/              # Agent implementations
│   ├── base.py          # MaverickAgent abstract base class
│   └── *.py             # Concrete agents (CodeReviewerAgent, etc.)
├── workflows/           # Workflow orchestration
│   ├── fly.py           # FlyWorkflow - full spec-based workflow
│   └── refuel.py        # RefuelWorkflow - tech-debt resolution
├── tools/               # MCP tool definitions
├── hooks/               # Safety and logging hooks
├── tui/                 # Textual application
│   ├── app.py           # Main Textual App
│   ├── screens/         # Screen components
│   └── widgets/         # Reusable widgets
└── utils/               # Shared utilities
```

### Separation of Concerns

- **Agents**: Know HOW to do a task (system prompts, tool selection, Claude SDK interaction)
- **Workflows**: Know WHAT to do and WHEN (orchestration, state management, sequencing)
- **TUI**: Presents state and captures input (no business logic)
- **Tools**: Wrap external systems (GitHub CLI, git, notifications)

## Core Principles

See `.specify/memory/constitution.md` for the authoritative reference.

1. **Async-First**: All agent interactions and workflows MUST be async. Use `asyncio` patterns; no threading for I/O. Workflows yield progress updates as async generators for TUI consumption.

2. **Dependency Injection**: Agents and workflows receive configuration and dependencies, not global state. MCP tool servers are passed in, not created internally.

3. **Fail Gracefully**: One agent/issue failing MUST NOT crash the entire workflow. Capture and report errors with context.

4. **Test-First**: Every public class and function MUST have tests. TDD with Red-Green-Refactor.

5. **Type Safety**: Complete type hints required. Use `@dataclass` or Pydantic `BaseModel` over plain dicts.

6. **Simplicity**: No global mutable state, no god-classes, no premature abstractions.

## Claude Agent SDK Patterns

- Always specify `allowed_tools` explicitly (principle of least privilege)
- Use `ClaudeSDKClient` for stateful/multi-turn interactions
- Use `query()` for one-shot, stateless interactions
- Custom tools use the `@tool` decorator and `create_sdk_mcp_server()`
- Hooks are async functions matching the SDK's hook signature
- Extract and structure agent outputs; do not return raw text

## Code Style

| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `CodeReviewerAgent`, `FlyWorkflow` |
| Functions | snake_case | `execute_review`, `create_pr` |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Private | Leading underscore | `_build_prompt`, `_validate_input` |

- Docstrings: Google-style format with Args, Returns, Raises sections
- Exceptions: Hierarchy from `MaverickError` → `AgentError`, `WorkflowError`, `ConfigError`
- No `print()` for output; use logging or TUI updates
- No `shell=True` in subprocess calls without explicit security justification

## Workflows

### FlyWorkflow
Full spec-based development workflow:
1. **Setup**: Sync branch with origin/main, validate spec directory
2. **Implementation**: Parse tasks.md, execute tasks (parallel for "P:" marked)
3. **Code Review**: Parallel CodeRabbit + architecture review
4. **Validation**: Format/lint/build/test with iterative fixes
5. **Convention Update**: Update CLAUDE.md if significant learnings
6. **PR Management**: Generate PR body, create/update via GitHub CLI

### RefuelWorkflow
Tech-debt resolution workflow:
1. **Discovery**: List open issues with target label
2. **Selection**: Analyze and select up to 3 non-conflicting issues
3. **Implementation**: Execute fixes in parallel
4. **Review & Validation**: Same as FlyWorkflow
5. **Finalize**: Mark PR ready, close issues

## Dependencies

- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- Optional: [CodeRabbit CLI](https://coderabbit.ai/) for enhanced code review
- Optional: [ntfy](https://ntfy.sh) for push notifications

## Legacy Plugin Reference

The `plugins/maverick/` directory contains the legacy Claude Code plugin implementation being migrated. Reference for workflow logic:
- `plugins/maverick/commands/` - Slash command definitions
- `plugins/maverick/scripts/` - Shell scripts (sync, validation, PR management)

## Active Technologies
- Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, textual, click, pyyaml, pydantic (001-maverick-foundation)
- YAML config files (project: `maverick.yaml`, user: `~/.config/maverick/config.yaml`) (001-maverick-foundation)
- Claude Agent SDK (`claude-agent-sdk`), Pydantic for MaverickAgent base class (002-base-agent)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI (003-code-reviewer-agent)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI, GitHub CLI (`gh`) (004-implementer-issue-fixer-agents)
- N/A (file system for task files, Git for commits) (004-implementer-issue-fixer-agents)

## Recent Changes
- 003-code-reviewer-agent: Added Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI
- 002-base-agent: Added MaverickAgent abstract base class with Claude Agent SDK integration
- 001-maverick-foundation: Added Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, textual, click, pyyaml, pydantic

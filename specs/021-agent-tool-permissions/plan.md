# Implementation Plan: Agent Tool Permissions

**Branch**: `021-agent-tool-permissions` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/021-agent-tool-permissions/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Reduce tool permissions across all agents to enforce the orchestration pattern where agents focus on their core judgment tasks while the Python orchestration layer handles external system interactions. This involves creating a centralized tool set constants module, updating each agent's allowed_tools, creating a new minimal FixerAgent, and updating system prompts to reflect constrained roles.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic
**Storage**: N/A (no persistence changes)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Linux/macOS CLI
**Project Type**: Single project (existing Maverick codebase)
**Performance Goals**: N/A (no performance impact expected)
**Constraints**: Must maintain backward compatibility with existing workflow orchestration
**Scale/Scope**: 5 agent classes to modify, 1 new module to create, ~10 test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Async-First ✅
- No changes to async patterns required
- Agent tool configuration is synchronous at construction time
- All agent execution remains async via existing `execute()` and `query()` methods

### II. Separation of Concerns ✅
- **REINFORCED**: This feature explicitly enforces separation
- Agents: Constrained to judgment tasks (code reading/writing, analysis)
- Workflows: Handle orchestration (git, GitHub API, test execution)
- Tools: External system wrappers (already isolated)

### III. Dependency Injection ✅
- Tool sets injected via constructor parameters
- No global mutable state introduced
- ToolSet constants are immutable frozensets

### IV. Fail Gracefully ✅
- Claude Agent SDK automatically rejects unauthorized tool calls
- No additional error handling required (SDK built-in behavior)
- Agent behavior remains predictable

### V. Test-First ✅
- FR-010 requires unit tests verifying each agent's allowed_tools
- Tests will verify tool set constants match agent configurations
- Existing test infrastructure supports this

### VI. Type Safety ✅
- Tool sets as `frozenset[str]` with clear type annotations
- Pydantic models unchanged
- No new complex types required

### VII. Simplicity ✅
- Centralized constants module reduces duplication
- No new abstractions beyond frozenset constants
- Minimal code changes per agent

### VIII. Relentless Progress ✅
- No impact on workflow resilience
- Constrained agents are more predictable, not less resilient
- Orchestration layer handles retries/recovery (unchanged)

## Project Structure

### Documentation (this feature)

```text
specs/021-agent-tool-permissions/
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
├── agents/
│   ├── __init__.py          # Update exports to include tools module
│   ├── base.py              # Update BUILTIN_TOOLS reference
│   ├── tools.py             # NEW: Centralized tool set constants (FR-001)
│   ├── implementer.py       # Update allowed_tools (FR-002)
│   ├── code_reviewer.py     # Update allowed_tools (FR-003)
│   ├── issue_fixer.py       # Update allowed_tools (FR-004)
│   ├── fixer.py             # NEW: Minimal FixerAgent (FR-005)
│   └── generators/
│       ├── base.py          # Verify no tools (FR-006)
│       ├── commit_message.py
│       └── pr_description.py

tests/
├── unit/
│   └── agents/
│       ├── test_tools.py    # NEW: Tests for tool set constants
│       ├── test_implementer.py  # Add tool permission tests
│       ├── test_code_reviewer.py
│       ├── test_issue_fixer.py
│       └── test_fixer.py    # NEW: Tests for FixerAgent
```

**Structure Decision**: Single project structure. All changes are within the existing `src/maverick/agents/` directory. New files: `tools.py` (constants module) and `fixer.py` (new agent). Test files in `tests/unit/agents/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. All changes align with constitution principles.

---

## Constitution Re-Check (Post-Design)

*GATE: Verify design decisions comply with constitution.*

### Design Decisions Validated

| Decision | Principle | Status |
|----------|-----------|--------|
| `frozenset` for tool sets | VI. Type Safety | ✅ Immutable, typed |
| Centralized `tools.py` module | VII. Simplicity | ✅ Single source of truth |
| FixerAgent minimal tools | VII. Simplicity | ✅ Smallest viable set |
| No new abstractions | VII. Simplicity | ✅ Constants only |
| Agent constructor injection | III. Dependency Injection | ✅ Tools passed in |
| System prompt updates | II. Separation of Concerns | ✅ Clear boundaries |

### Research Findings Impact

| Finding | Impact | Compliance |
|---------|--------|------------|
| MultiEdit doesn't exist | Removed from requirements | ✅ Simplified |
| SDK handles tool filtering | No custom error handling | ✅ Simpler |
| allowed_tools issue resolved | Standard SDK usage | ✅ No workarounds |

**Post-Design Status**: ✅ All principles satisfied. No violations.

---

## Generated Artifacts

| Artifact | Location | Purpose |
|----------|----------|---------|
| research.md | `specs/021-agent-tool-permissions/research.md` | Research findings and decisions |
| data-model.md | `specs/021-agent-tool-permissions/data-model.md` | Entity definitions and relationships |
| tools-module.md | `specs/021-agent-tool-permissions/contracts/tools-module.md` | Tool constants API contract |
| fixer-agent.md | `specs/021-agent-tool-permissions/contracts/fixer-agent.md` | FixerAgent API contract |
| quickstart.md | `specs/021-agent-tool-permissions/quickstart.md` | Developer guide |

---

## Next Steps

Run `/speckit.tasks` to generate the implementation task list (`tasks.md`).

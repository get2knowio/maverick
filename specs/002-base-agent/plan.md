# Implementation Plan: Base Agent Abstraction Layer

**Branch**: `002-base-agent` | **Date**: 2025-12-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-base-agent/spec.md`

## Summary

Create the `MaverickAgent` abstract base class that wraps Claude Agent SDK interactions, providing a standardized interface for all agents in the system. Includes `AgentResult` and `AgentContext` dataclasses for structured I/O, an `AgentRegistry` for dynamic agent discovery, utility functions for message extraction, and a comprehensive error hierarchy. All interactions are async-first with streaming support.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic
**Storage**: N/A (stateless abstraction layer)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Linux server (dev containers), macOS (local dev)
**Project Type**: Single project (library module within `src/maverick/agents/`)
**Performance Goals**: <100ms overhead beyond Claude response time (SC-002), <500ms to first stream chunk (SC-003)
**Constraints**: No automatic retries at base layer, no blocking I/O in async contexts
**Scale/Scope**: Foundation layer supporting 5-10 concrete agent implementations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check (Phase 0 Gate)

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Async-First | ✅ PASS | FR-013 mandates all I/O methods async; `query()` returns AsyncIterator |
| II. Separation of Concerns | ✅ PASS | Agents know HOW (base class), Workflows know WHEN (caller responsibility) |
| III. Dependency Injection | ✅ PASS | MCP servers passed at construction (FR-002), config injected via AgentContext |
| IV. Fail Gracefully | ✅ PASS | FR-007 defines error wrapping; no retries at base layer per clarifications |
| V. Test-First | ✅ PASS | All acceptance scenarios designed for independent testing |
| VI. Type Safety | ✅ PASS | Pydantic/dataclass for all structured data (FR-008, FR-009) |
| VII. Simplicity | ✅ PASS | Single abstract base class, no complex inheritance hierarchies |

**Gate Result**: ✅ PASS - Proceed to Phase 0

### Post-Design Check (Phase 1 Gate)

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Async-First | ✅ PASS | `execute()` and `query()` are async; `ClaudeSDKClient` uses async context manager |
| II. Separation of Concerns | ✅ PASS | Data model separates: Agent (behavior), Result (outcome), Context (runtime), Registry (discovery) |
| III. Dependency Injection | ✅ PASS | `AgentContext` injects config; constructor accepts `mcp_servers` dict |
| IV. Fail Gracefully | ✅ PASS | 8 specific error types defined; `StreamingError` yields partial content first |
| V. Test-First | ✅ PASS | Protocols enable test doubles; `quickstart.md` includes test examples |
| VI. Type Safety | ✅ PASS | All entities are `@dataclass(frozen=True, slots=True)`; Protocols for interfaces |
| VII. Simplicity | ✅ PASS | 6 source files; no god-classes; composition via registry pattern |

**Gate Result**: ✅ PASS - Proceed to Phase 2 (Tasks)

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
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
├── __init__.py              # Package exports
├── exceptions.py            # MaverickError hierarchy (add new error types)
└── agents/
    ├── __init__.py          # Public API: MaverickAgent, AgentResult, AgentContext, registry
    ├── base.py              # MaverickAgent abstract base class
    ├── result.py            # AgentResult dataclass
    ├── context.py           # AgentContext dataclass
    ├── registry.py          # AgentRegistry singleton
    └── utils.py             # Message extraction utilities

tests/
├── unit/
│   └── agents/
│       ├── test_base.py         # MaverickAgent tests
│       ├── test_result.py       # AgentResult tests
│       ├── test_context.py      # AgentContext tests
│       ├── test_registry.py     # AgentRegistry tests
│       └── test_utils.py        # Utility function tests
└── integration/
    └── agents/
        └── test_agent_execution.py  # End-to-end agent tests (mocked Claude)
```

**Structure Decision**: Single project structure following constitution's File Organization. Agent-related code lives in `src/maverick/agents/` module with corresponding test structure in `tests/unit/agents/` and `tests/integration/agents/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations - all constitution principles satisfied.*

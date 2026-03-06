# Implementation Plan: ACP Integration

**Branch**: `042-acp-integration` | **Date**: 2026-03-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/042-acp-integration/spec.md`

## Summary

Replace Maverick's `claude-agent-sdk` dependency with `agent-client-protocol` (ACP) as the execution layer between workflows and coding agents. The ACP executor manages subprocess lifecycle (spawn, initialize, session, prompt, cleanup), streams events to the TUI, supports configurable multi-provider agent selection, and preserves the existing `StepExecutor` protocol so workflow code is unchanged. The `MaverickAgent` base class is refactored into a pure prompt-construction container.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: `agent-client-protocol` v0.8.1+ (new), Click, Rich, Pydantic, structlog, tenacity, GitPython
**Storage**: N/A (no persistence changes)
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: macOS / Linux (Node.js 18+ required for Claude Code ACP agent)
**Project Type**: Single (existing `src/maverick/` layout)
**Performance Goals**: Connection reuse across sequential steps (1 subprocess per provider per workflow run)
**Constraints**: `StepExecutor` protocol, `ExecutorResult`, `UsageMetadata`, workflow call sites, safety hooks, flight plan models, and workflow logic MUST NOT change
**Scale/Scope**: ~25 files modified, ~5 new files, ~17 agent classes refactored (7 MaverickAgent, 2 reviewers, 1 GeneratorAgent base, 7 concrete generators)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | ACP SDK is fully async; `spawn_agent_process` is async context manager; `prompt()` is async |
| II. Separation of Concerns | PASS | Agents → prompt construction only; Executor → ACP interaction; Workflows unchanged |
| III. Dependency Injection | PASS | `AcpStepExecutor` receives `AgentProviderRegistry` and `ComponentRegistry` at construction |
| IV. Fail Gracefully | PASS | ACP errors mapped to Maverick hierarchy; retry with fresh sessions; circuit breaker preserved |
| V. Test-First | PASS | All new code requires tests; ACP interactions mocked (no real subprocesses in tests) |
| VI. Type Safety | PASS | `AgentProviderConfig` is frozen Pydantic; contracts use typed protocols; no `dict[str, Any]` returns |
| VII. Simplicity & DRY | PASS | Single `AcpStepExecutor` replaces `ClaudeStepExecutor`; no new abstractions beyond what's needed |
| VIII. Relentless Progress | PASS | Reconnect on connection drop; retry with fresh sessions; graceful degradation |
| IX. Hardening by Default | PASS | Timeouts on `prompt()`; tenacity retries; explicit error handling |
| X.1. TUI display-only | N/A | No TUI changes |
| X.2. No blocking on event loop | PASS | All ACP calls are async |
| X.3. Deterministic ops in workflows | PASS | Executor handles agent interaction; no side effects in agents |
| X.4. Typed contracts | PASS | `AgentProviderConfig`, `CachedConnection`, `AgentPromptBuilder` protocol |
| X.5. Real resilience | PASS | Retry creates fresh ACP sessions; circuit breaker cancels via `conn.cancel()` |
| X.6. One canonical wrapper | PASS | `AcpStepExecutor` is the single ACP wrapper |
| X.8. Canonical libraries | PASS | structlog for logging, tenacity for retries |
| X.9. TUI streaming | PASS | ACP events mapped to existing `AgentStreamChunk` format |
| XI. Modularize Early | PASS | New code split across focused modules (`acp.py`, `acp_client.py`, `provider_registry.py`) |
| XII. Ownership | PASS | Full migration including SDK removal, test updates, and dependency cleanup |

**Post-Design Re-Check**: All gates still pass. No new violations introduced by the design.

## Project Structure

### Documentation (this feature)

```text
specs/042-acp-integration/
├── plan.md              # This file
├── research.md          # Phase 0 output (ACP SDK research, mapping decisions)
├── data-model.md        # Phase 1 output (entity definitions)
├── quickstart.md        # Phase 1 output (developer guide)
├── contracts/           # Phase 1 output (typed interfaces)
│   └── acp-step-executor.py
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/
├── config.py                          # MODIFY: Add AgentProviderConfig, agent_providers field
├── executor/
│   ├── __init__.py                    # MODIFY: Export AcpStepExecutor, remove ClaudeStepExecutor
│   ├── acp.py                         # NEW: AcpStepExecutor implementation
│   ├── acp_client.py                  # NEW: MaverickAcpClient (acp.Client subclass)
│   ├── provider_registry.py           # NEW: AgentProviderRegistry
│   ├── claude.py                      # DELETE: ClaudeStepExecutor (replaced by acp.py)
│   ├── protocol.py                    # UNCHANGED
│   ├── config.py                      # MODIFY: provider field type str | None
│   ├── result.py                      # UNCHANGED
│   └── errors.py                      # UNCHANGED
├── agents/
│   ├── base.py                        # MODIFY: Remove SDK coupling, add build_prompt()
│   ├── implementer.py                 # MODIFY: Replace execute() with build_prompt()
│   ├── code_reviewer/
│   │   └── agent.py                   # MODIFY: Replace execute() with build_prompt()
│   ├── fixer.py                       # MODIFY: Replace execute() with build_prompt()
│   ├── issue_fixer.py                 # MODIFY: Replace execute() with build_prompt()
│   ├── decomposer.py                  # MODIFY: Replace execute() with build_prompt()
│   ├── curator.py                     # MODIFY: Refactor from GeneratorAgent to prompt-builder
│   ├── flight_plan_generator.py       # MODIFY: Replace execute() with build_prompt()
│   ├── reviewers/
│   │   ├── unified_reviewer.py        # MODIFY: Replace execute() with build_prompt()
│   │   └── simple_fixer.py            # MODIFY: Replace execute() with build_prompt()
│   ├── generators/
│   │   ├── base.py                    # MODIFY: Remove SDK coupling, refactor to prompt-builder
│   │   ├── commit_message.py          # MODIFY: Replace generate() with build_prompt()
│   │   ├── bead_enricher.py           # MODIFY: Replace generate() with build_prompt()
│   │   ├── pr_description.py          # MODIFY: Replace generate() with build_prompt()
│   │   ├── pr_title.py               # MODIFY: Replace generate() with build_prompt()
│   │   ├── dependency_extractor.py    # MODIFY: Replace generate() with build_prompt()
│   │   ├── code_analyzer.py           # MODIFY: Replace generate() with build_prompt()
│   │   └── error_explainer.py         # MODIFY: Replace generate() with build_prompt()
│   ├── context.py                     # UNCHANGED
│   ├── result.py                      # MODIFY: Remove SDK-specific extraction utils
│   ├── utils.py                       # MODIFY: Remove SDK-specific extraction utils
│   └── contracts.py                   # UNCHANGED
├── cli/
│   └── workflow_executor.py           # MODIFY: Instantiate AcpStepExecutor instead of ClaudeStepExecutor
└── workflows/                         # UNCHANGED (call sites use StepExecutor protocol)

tests/
├── unit/
│   ├── executor/
│   │   ├── test_acp_executor.py       # NEW: AcpStepExecutor unit tests
│   │   ├── test_acp_client.py         # NEW: MaverickAcpClient unit tests
│   │   ├── test_provider_registry.py  # NEW: AgentProviderRegistry unit tests
│   │   └── test_claude_executor.py    # DELETE: Old executor tests
│   └── agents/
│       └── test_base.py               # MODIFY: Update for build_prompt() pattern
└── conftest.py                        # MODIFY: Add ACP mock fixtures
```

**Structure Decision**: Single project layout (existing). New ACP files live in `src/maverick/executor/` alongside the existing protocol. The executor package grows from 5 to 7 files, well within the ~500 LOC soft limit per module.

## Complexity Tracking

No constitution violations to justify. The design stays within all guardrails.

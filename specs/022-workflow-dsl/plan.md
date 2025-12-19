# Implementation Plan: Core Workflow DSL

**Branch**: `022-workflow-dsl` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/022-workflow-dsl/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement a core Workflow DSL for Maverick that provides a `@workflow` decorator and typed step definitions (Python, Agent, Generate, Validate, Sub-workflow). The DSL enables workflow authors to define named steps, execute them in sequence with a `WorkflowContext`, and receive structured `WorkflowResult` objects containing per-step results, overall success, and final output. The execution engine handles progress events for TUI integration and fail-fast behavior with human-readable errors.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Pydantic (BaseModel for configuration/results), dataclasses (frozen/slots for events), asyncio (async workflow execution), Claude Agent SDK (for agent/generate steps)
**Storage**: N/A (in-memory state during workflow execution; results are returned to caller)
**Testing**: pytest + pytest-asyncio (async tests), mock agents/validators
**Target Platform**: Linux/macOS (CLI/TUI development tool)
**Project Type**: Single project (Python package under `src/maverick/`)
**Performance Goals**: Workflow step execution overhead <10ms per step; progress events emitted within 1ms of step state change
**Constraints**: No blocking I/O in async paths; step execution must be cancellable; all step types must be serializable for logging
**Scale/Scope**: Workflows with 1-50 steps typical; sub-workflows nested 1-2 levels deep

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Async-First | All workflow execution and step handlers MUST be async. Progress events MUST be yielded via async generators. | PASS |
| II. Separation of Concerns | Workflow DSL defines WHAT/WHEN (orchestration); steps delegate to agents for HOW. Step definitions MUST NOT contain business logic. | PASS |
| III. Dependency Injection | Agents, validators, and configuration MUST be injected into workflow context—not accessed globally. | PASS |
| IV. Fail Gracefully | Step failures MUST be captured with human-readable errors; workflow stops but does not crash. Per FR-022: catch exceptions, record failed StepResult. | PASS |
| V. Test-First | Every public class (WorkflowContext, StepResult, WorkflowResult, step types) MUST have tests. TDD required. | PASS |
| VI. Type Safety | Complete type hints required. Use frozen dataclasses/Pydantic for StepResult, WorkflowResult. Use TypeVar for generic step execution. | PASS |
| VII. Simplicity | Avoid premature abstraction. Start with 5 step types per FR-006-011. No plugin system—steps are explicit classes. | PASS |
| VIII. Relentless Progress | For this DSL spec, fail-fast behavior is intentional per FR-018/FR-022. Retry logic is delegated to ValidateStep (FR-010). Constitution compliance via delegation. | PASS |

## Project Structure

### Documentation (this feature)

```text
specs/022-workflow-dsl/
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
├── dsl/                           # NEW: Workflow DSL module
│   ├── __init__.py                # Public API exports
│   ├── types.py                   # StepType enum, TypeAliases
│   ├── context.py                 # WorkflowContext, WorkflowInputs
│   ├── results.py                 # StepResult, WorkflowResult, SubWorkflowInvocationResult
│   ├── steps/                     # Step definition classes
│   │   ├── __init__.py
│   │   ├── base.py                # StepDefinition ABC
│   │   ├── python.py              # PythonStep
│   │   ├── agent.py               # AgentStep
│   │   ├── generate.py            # GenerateStep
│   │   ├── validate.py            # ValidateStep
│   │   └── subworkflow.py         # SubWorkflowStep
│   ├── decorator.py               # @workflow decorator
│   ├── builder.py                 # step() builder function
│   ├── engine.py                  # WorkflowEngine (execution)
│   └── events.py                  # Progress events (StepStarted, StepCompleted, etc.)
├── workflows/                     # Existing: concrete workflow implementations
│   ├── fly.py                     # Will migrate to use DSL (future)
│   └── refuel.py                  # Will migrate to use DSL (future)
└── ...

tests/
├── unit/
│   └── dsl/                       # NEW: DSL unit tests
│       ├── test_context.py
│       ├── test_results.py
│       ├── test_decorator.py
│       ├── test_builder.py
│       ├── test_engine.py
│       └── steps/
│           ├── test_python_step.py
│           ├── test_agent_step.py
│           ├── test_generate_step.py
│           ├── test_validate_step.py
│           └── test_subworkflow_step.py
└── integration/
    └── dsl/                       # NEW: DSL integration tests
        └── test_workflow_execution.py
```

**Structure Decision**: Single project structure. The DSL module is added as `src/maverick/dsl/` to keep workflow authoring primitives separate from concrete workflow implementations in `src/maverick/workflows/`. This allows the existing FlyWorkflow and RefuelWorkflow to optionally migrate to the DSL in future iterations while maintaining backward compatibility.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. All constitution principles are satisfied by the design.
